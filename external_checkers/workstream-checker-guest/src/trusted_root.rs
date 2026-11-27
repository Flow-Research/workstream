//! Independently pinned platform-root staging. This does not execute a workload.
//! The caller owns a private bounded spool and charges spool plus expanded root.
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::HashSet;
use std::fs::{self, File, OpenOptions};
use std::io::{self, Read, Seek, SeekFrom, Write};
use std::os::fd::AsRawFd;
use std::os::unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt};
use std::path::Path;

const MAGIC: &[u8] = b"WSROOT1\n";
const MAX_HEADER: usize = 16384;
type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RootDescriptor {
    pub schema_version: String,
    pub platform_manifest_digest: String,
    pub config_image_id: String,
    pub default_behavior_sha256: String,
    pub expanded_bytes: u64,
    pub entries: u64,
    pub bundle_sha256: String,
    pub bundle_byte_count: u64,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RootLimits {
    pub maximum_bundle_bytes: u64,
    pub maximum_root_bytes: u64,
    pub maximum_entries: u64,
}

#[derive(Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
enum Record {
    Identity {
        platform_manifest_digest: String,
        config_image_id: String,
        default_behavior_sha256: String,
    },
    Directory {
        path: String,
    },
    File {
        path: String,
        byte_count: u64,
        executable: bool,
    },
    Symlink {
        path: String,
        target: String,
    },
    End,
}

fn digest_valid(value: &str) -> bool {
    value.len() == 71
        && value.starts_with("sha256:")
        && value[7..]
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn path_valid(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 4096
        && !value.contains(['\\', '\0'])
        && value
            .split('/')
            .all(|part| !part.is_empty() && part != "." && part != "..")
}

fn link_valid(path: &str, target: &str) -> bool {
    if target.is_empty() || target.len() > 4096 || target.contains(['\\', '\0']) {
        return false;
    }
    let mut depth = if target.starts_with('/') {
        0
    } else {
        path.matches('/').count()
    };
    for part in target.split('/') {
        match part {
            ".." if depth == 0 => return false,
            ".." => depth -= 1,
            "" | "." => (),
            _ => depth += 1,
        }
    }
    true
}

fn remove_owned_root(path: &Path) -> Result<()> {
    // Restore directory write access after a late permission/cancellation error.
    // The private held parent prevents an untrusted process replacing this tree.
    fs::set_permissions(path, fs::Permissions::from_mode(0o700))?;
    for entry in fs::read_dir(path)? {
        let entry = entry?;
        if entry.file_type()?.is_dir() {
            remove_owned_root(&entry.path())?;
        } else {
            fs::remove_file(entry.path())?;
        }
    }
    fs::remove_dir(path)?;
    Ok(())
}

struct Hashed<'a> {
    file: &'a mut File,
    digest: Sha256,
    count: u64,
    maximum: u64,
}
impl Read for Hashed<'_> {
    fn read(&mut self, bytes: &mut [u8]) -> io::Result<usize> {
        let size = self.file.read(bytes)?;
        self.count = self
            .count
            .checked_add(size as u64)
            .ok_or_else(|| io::Error::other("root bundle count overflow"))?;
        if self.count > self.maximum {
            return Err(io::Error::other("root bundle exceeds pinned count"));
        }
        self.digest.update(&bytes[..size]);
        Ok(size)
    }
}

fn frame(reader: &mut impl Read) -> Result<Record> {
    let mut prefix = [0; 4];
    reader.read_exact(&mut prefix)?;
    let size = u32::from_be_bytes(prefix) as usize;
    if size == 0 || size > MAX_HEADER {
        return Err("root frame exceeds limit".into());
    }
    let mut body = vec![0; size];
    reader.read_exact(&mut body)?;
    Ok(serde_json::from_slice(&body)?)
}

fn check_digest(reader: Hashed<'_>, expected: &RootDescriptor) -> Result<()> {
    if reader.count != expected.bundle_byte_count
        || format!("sha256:{:x}", reader.digest.finalize()) != expected.bundle_sha256
    {
        return Err("root bundle identity differs".into());
    }
    Ok(())
}

/// Verify the pinned spool, then stage only into an exclusively created root.
/// `check` must enforce the invocation's aggregate deadline/cancellation fence.
/// The parent must be private and owned by the supervisor. A held no-follow
/// descriptor anchors writes even if an ancestor path is renamed concurrently.
pub fn stage_root(
    source: &mut File,
    target: &Path,
    expected: &RootDescriptor,
    limits: &RootLimits,
    check: impl Fn() -> Result<()>,
) -> Result<()> {
    if expected.schema_version != "workstream.trusted_root.v1"
        || ![
            &expected.platform_manifest_digest,
            &expected.config_image_id,
            &expected.default_behavior_sha256,
            &expected.bundle_sha256,
        ]
        .into_iter()
        .all(|value| digest_valid(value))
        || expected.bundle_byte_count == 0
        || expected.entries == 0
        || expected.bundle_byte_count > limits.maximum_bundle_bytes
        || expected.expanded_bytes > limits.maximum_root_bytes
        || expected.entries > limits.maximum_entries
    {
        return Err("root descriptor invalid".into());
    }
    source.seek(SeekFrom::Start(0))?;
    let mut reader = Hashed {
        file: source,
        digest: Sha256::new(),
        count: 0,
        maximum: expected.bundle_byte_count,
    };
    let mut chunk = [0; 65536];
    loop {
        check()?;
        if reader.read(&mut chunk)? == 0 {
            break;
        }
    }
    check_digest(reader, expected)?;
    check()?;
    source.seek(SeekFrom::Start(0))?;
    if !target.is_absolute() {
        return Err("root target must be absolute".into());
    }
    let parent = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(target.parent().ok_or("root parent missing")?)?;
    let metadata = parent.metadata()?;
    if metadata.uid() != unsafe { libc::geteuid() } || metadata.mode() & 0o077 != 0 {
        return Err("root parent is not supervisor-private".into());
    }
    let anchored = std::path::PathBuf::from(format!("/proc/self/fd/{}", parent.as_raw_fd()))
        .join(target.file_name().ok_or("root name missing")?);
    fs::create_dir(&anchored)?;
    let result = (|| {
        check()?;
        fs::set_permissions(&anchored, fs::Permissions::from_mode(0o700))?;
        unpack(source, &anchored, expected, &check)
    })();
    if result.is_err() {
        remove_owned_root(&anchored)?;
    }
    result
}

fn unpack(
    source: &mut File,
    target: &Path,
    expected: &RootDescriptor,
    check: &impl Fn() -> Result<()>,
) -> Result<()> {
    let mut reader = Hashed {
        file: source,
        digest: Sha256::new(),
        count: 0,
        maximum: expected.bundle_byte_count,
    };
    let mut magic = [0; 8];
    reader.read_exact(&mut magic)?;
    if magic != MAGIC {
        return Err("root magic invalid".into());
    }
    match frame(&mut reader)? {
        Record::Identity {
            platform_manifest_digest,
            config_image_id,
            default_behavior_sha256,
        } if platform_manifest_digest == expected.platform_manifest_digest
            && config_image_id == expected.config_image_id
            && default_behavior_sha256 == expected.default_behavior_sha256 => {}
        _ => return Err("root platform identity differs".into()),
    }
    let (mut paths, mut directories) = (HashSet::new(), HashSet::new());
    let (mut bytes, mut phase) = (0_u64, 0);
    loop {
        check()?;
        let record = frame(&mut reader)?;
        let (name, next_phase) = match &record {
            Record::Directory { path } => (path, 0),
            Record::File { path, .. } => (path, 1),
            Record::Symlink { path, .. } => (path, 2),
            Record::End => break,
            _ => return Err("unexpected root identity".into()),
        };
        if !path_valid(name)
            || next_phase < phase
            || !paths.insert(name.clone())
            || paths.len() as u64 > expected.entries
        {
            return Err("root path or sequence invalid".into());
        }
        phase = next_phase;
        if let Some((parent, _)) = name.rsplit_once('/') {
            if !directories.contains(parent) {
                return Err("root parent is not a directory".into());
            }
        }
        let path = target.join(name);
        match record {
            Record::Directory { path: name } => {
                fs::create_dir(&path)?;
                fs::set_permissions(&path, fs::Permissions::from_mode(0o700))?;
                directories.insert(name);
            }
            Record::File {
                byte_count,
                executable,
                ..
            } => {
                bytes = bytes.checked_add(byte_count).ok_or("root size overflow")?;
                if bytes > expected.expanded_bytes {
                    return Err("root expansion exceeds limit".into());
                }
                let mut file = OpenOptions::new()
                    .write(true)
                    .create_new(true)
                    .mode(0o600)
                    .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
                    .open(&path)?;
                let mut remaining = byte_count;
                let mut chunk = [0; 65536];
                while remaining > 0 {
                    check()?;
                    let length = remaining.min(chunk.len() as u64) as usize;
                    reader.read_exact(&mut chunk[..length])?;
                    file.write_all(&chunk[..length])?;
                    remaining -= length as u64;
                }
                file.set_permissions(fs::Permissions::from_mode(if executable {
                    0o555
                } else {
                    0o444
                }))?;
            }
            Record::Symlink {
                path: name,
                target: link,
            } => {
                if !link_valid(&name, &link) {
                    return Err("root symlink invalid".into());
                }
                std::os::unix::fs::symlink(link, path)?;
            }
            _ => unreachable!(),
        }
    }
    if bytes != expected.expanded_bytes || paths.len() as u64 != expected.entries {
        return Err("root observed bounds differ".into());
    }
    if reader.read(&mut [0])? != 0 {
        return Err("root trailing bytes".into());
    }
    check_digest(reader, expected)?;
    check()?;
    // The caller still mounts this root read-only before any child runs.
    for directory in directories {
        fs::set_permissions(target.join(directory), fs::Permissions::from_mode(0o555))?;
    }
    fs::set_permissions(target, fs::Permissions::from_mode(0o555))?;
    check()?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::{json, Value};
    use std::cell::Cell;
    use std::path::PathBuf;
    use std::sync::atomic::{AtomicU64, Ordering};

    static NEXT: AtomicU64 = AtomicU64::new(0);
    struct Fixture(PathBuf);
    impl Fixture {
        fn new() -> Self {
            let path = std::env::temp_dir().join(format!(
                "workstream-root-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            fs::create_dir(&path).unwrap();
            fs::set_permissions(&path, fs::Permissions::from_mode(0o700)).unwrap();
            Self(path)
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            fn writable(path: &Path) {
                fs::set_permissions(path, fs::Permissions::from_mode(0o700)).unwrap();
                for entry in fs::read_dir(path).unwrap() {
                    let entry = entry.unwrap();
                    if entry.file_type().unwrap().is_dir() {
                        writable(&entry.path());
                    }
                }
            }
            writable(&self.0);
            fs::remove_dir_all(&self.0).unwrap();
        }
    }
    fn sha(bytes: &[u8]) -> String {
        format!("sha256:{:x}", Sha256::digest(bytes))
    }
    fn frame_bytes(bytes: &mut Vec<u8>, value: Value) {
        let body = serde_json::to_vec(&value).unwrap();
        bytes.extend_from_slice(&(body.len() as u32).to_be_bytes());
        bytes.extend(body);
    }
    fn bundle(records: Vec<(Value, &[u8])>) -> (Vec<u8>, RootDescriptor) {
        let mut bytes = MAGIC.to_vec();
        frame_bytes(
            &mut bytes,
            json!({"kind":"identity", "platform_manifest_digest":sha(b"platform"),
            "config_image_id":sha(b"config"), "default_behavior_sha256":sha(b"behavior")}),
        );
        let mut expanded = 0;
        let count = records.len() as u64;
        for (value, data) in records {
            frame_bytes(&mut bytes, value);
            bytes.extend_from_slice(data);
            expanded += data.len() as u64;
        }
        frame_bytes(&mut bytes, json!({"kind":"end"}));
        let descriptor = RootDescriptor {
            schema_version: "workstream.trusted_root.v1".into(),
            platform_manifest_digest: sha(b"platform"),
            config_image_id: sha(b"config"),
            default_behavior_sha256: sha(b"behavior"),
            expanded_bytes: expanded,
            entries: count,
            bundle_sha256: sha(&bytes),
            bundle_byte_count: bytes.len() as u64,
        };
        (bytes, descriptor)
    }
    fn limits() -> RootLimits {
        RootLimits {
            maximum_bundle_bytes: 10000,
            maximum_root_bytes: 1000,
            maximum_entries: 20,
        }
    }
    fn valid() -> (Vec<u8>, RootDescriptor) {
        bundle(vec![
            (json!({"kind":"directory", "path":"usr"}), b""),
            (
                json!({"kind":"file", "path":"usr/python", "byte_count":4, "executable":true}),
                b"code",
            ),
            (
                json!({"kind":"symlink", "path":"python", "target":"/usr/python"}),
                b"",
            ),
        ])
    }
    fn source(fixture: &Fixture, bytes: &[u8]) -> File {
        let path = fixture.0.join("bundle");
        fs::write(&path, bytes).unwrap();
        File::open(path).unwrap()
    }
    #[test]
    fn stages_exact_files_and_links_without_following_absolute_targets() {
        let fixture = Fixture::new();
        let (bytes, descriptor) = valid();
        let root = fixture.0.join("root");
        stage_root(
            &mut source(&fixture, &bytes),
            &root,
            &descriptor,
            &limits(),
            || Ok(()),
        )
        .unwrap();
        assert_eq!(fs::read(root.join("usr/python")).unwrap(), b"code");
        assert_eq!(
            fs::read_link(root.join("python")).unwrap(),
            Path::new("/usr/python")
        );
        assert_eq!(
            fs::metadata(root.join("usr/python"))
                .unwrap()
                .permissions()
                .mode()
                & 0o7777,
            0o555
        );
    }
    #[test]
    fn rejects_digest_truncation_identity_bounds_and_trailing_content() {
        for defect in 0..6 {
            let fixture = Fixture::new();
            let (mut bytes, mut descriptor) = valid();
            match defect {
                0 => descriptor.bundle_sha256 = sha(b"other"),
                1 => {
                    bytes.pop();
                }
                2 => descriptor.config_image_id = sha(b"other config"),
                3 => descriptor.expanded_bytes = 3,
                4 => descriptor.entries = 2,
                5 => {
                    bytes.push(0);
                    descriptor.bundle_byte_count = bytes.len() as u64;
                    descriptor.bundle_sha256 = sha(&bytes);
                }
                _ => unreachable!(),
            }
            let root = fixture.0.join("root");
            assert!(
                stage_root(
                    &mut source(&fixture, &bytes),
                    &root,
                    &descriptor,
                    &limits(),
                    || Ok(())
                )
                .is_err(),
                "defect {defect}"
            );
            assert!(!root.exists());
        }
    }
    #[test]
    fn rejects_paths_duplicates_link_parent_and_unknown_fields() {
        for records in [
            vec![(
                json!({"kind":"directory", "path":"../outside"}),
                b"".as_slice(),
            )],
            vec![(
                json!({"kind":"directory", "path":"/outside"}),
                b"".as_slice(),
            )],
            vec![
                (json!({"kind":"directory", "path":"a"}), b"".as_slice()),
                (json!({"kind":"directory", "path":"a"}), b"".as_slice()),
            ],
            vec![
                (
                    json!({"kind":"symlink", "path":"a", "target":"/outside"}),
                    b"".as_slice(),
                ),
                (
                    json!({"kind":"file", "path":"a/code", "byte_count":0, "executable":false}),
                    b"".as_slice(),
                ),
            ],
            vec![(
                json!({"kind":"directory", "path":"a", "uid":0}),
                b"".as_slice(),
            )],
        ] {
            let fixture = Fixture::new();
            let (bytes, descriptor) = bundle(records);
            let root = fixture.0.join("root");
            assert!(stage_root(
                &mut source(&fixture, &bytes),
                &root,
                &descriptor,
                &limits(),
                || Ok(())
            )
            .is_err());
            assert!(!root.exists());
        }
    }
    #[test]
    fn changed_spool_after_first_hash_cannot_publish_root() {
        let fixture = Fixture::new();
        let (bytes, descriptor) = valid();
        let root = fixture.0.join("root");
        let calls = Cell::new(0);
        let mut file = source(&fixture, &bytes);
        assert!(stage_root(&mut file, &root, &descriptor, &limits(), || {
            calls.set(calls.get() + 1);
            if calls.get() == 3 {
                let mut changed = bytes.clone();
                let offset = changed.windows(4).position(|part| part == b"code").unwrap();
                changed[offset..offset + 4].copy_from_slice(b"evil");
                fs::write(fixture.0.join("bundle"), changed)?;
            }
            Ok(())
        })
        .is_err());
        assert!(calls.get() >= 3);
        assert!(!root.exists());
    }
    #[test]
    fn cancellation_removes_partial_root_and_existing_target_is_preserved() {
        let fixture = Fixture::new();
        let (bytes, descriptor) = valid();
        let root = fixture.0.join("root");
        let calls = Cell::new(0);
        assert!(stage_root(
            &mut source(&fixture, &bytes),
            &root,
            &descriptor,
            &limits(),
            || {
                calls.set(calls.get() + 1);
                if calls.get() == 6 {
                    Err("cancelled".into())
                } else {
                    Ok(())
                }
            }
        )
        .is_err());
        assert!(!root.exists());
        fs::create_dir(&root).unwrap();
        fs::write(root.join("existing"), b"retained").unwrap();
        assert!(stage_root(
            &mut source(&fixture, &bytes),
            &root,
            &descriptor,
            &limits(),
            || Ok(())
        )
        .is_err());
        assert_eq!(fs::read(root.join("existing")).unwrap(), b"retained");
    }
    #[test]
    fn rejects_escaping_links_and_accepts_contained_relative_links() {
        assert!(link_valid("usr/link", "../usr/python"));
        for target in ["../../outside", "/../outside"] {
            let fixture = Fixture::new();
            let (bytes, descriptor) = bundle(vec![
                (json!({"kind":"directory", "path":"safe"}), b""),
                (
                    json!({"kind":"symlink", "path":"safe/escape", "target":target}),
                    b"",
                ),
            ]);
            let root = fixture.0.join("root");
            assert!(stage_root(
                &mut source(&fixture, &bytes),
                &root,
                &descriptor,
                &limits(),
                || Ok(())
            )
            .is_err());
            assert!(!root.exists());
        }
    }

    #[test]
    fn errors_immediately_after_create_and_after_sealing_remove_owned_root() {
        for early in [true, false] {
            let fixture = Fixture::new();
            let (bytes, descriptor) = valid();
            let root = fixture.0.join("root");
            let calls = Cell::new(0);
            let result = stage_root(
                &mut source(&fixture, &bytes),
                &root,
                &descriptor,
                &limits(),
                || {
                    calls.set(calls.get() + 1);
                    let sealed = fs::metadata(&root)
                        .map(|info| info.permissions().mode() & 0o777 == 0o555)
                        .unwrap_or(false);
                    if (early && calls.get() == 4) || (!early && sealed) {
                        Err("cancelled at permission boundary".into())
                    } else {
                        Ok(())
                    }
                },
            );
            assert!(result.is_err());
            assert!(!root.exists());
        }
    }

    #[test]
    fn requires_private_nofollow_parent_and_pins_its_identity() {
        let fixture = Fixture::new();
        let (bytes, descriptor) = valid();
        let parent = fixture.0.join("private");
        fs::create_dir(&parent).unwrap();
        let target = parent.join("root");
        fs::set_permissions(&parent, fs::Permissions::from_mode(0o755)).unwrap();
        assert!(stage_root(
            &mut source(&fixture, &bytes),
            &target,
            &descriptor,
            &limits(),
            || Ok(())
        )
        .is_err());
        fs::set_permissions(&parent, fs::Permissions::from_mode(0o700)).unwrap();
        let alias = fixture.0.join("alias");
        std::os::unix::fs::symlink(&parent, &alias).unwrap();
        assert!(stage_root(
            &mut source(&fixture, &bytes),
            &alias.join("root"),
            &descriptor,
            &limits(),
            || Ok(())
        )
        .is_err());
        let moved = fixture.0.join("moved");
        let outside = fixture.0.join("outside");
        fs::create_dir(&outside).unwrap();
        let calls = Cell::new(0);
        stage_root(
            &mut source(&fixture, &bytes),
            &target,
            &descriptor,
            &limits(),
            || {
                calls.set(calls.get() + 1);
                if calls.get() == 4 {
                    fs::rename(&parent, &moved)?;
                    std::os::unix::fs::symlink(&outside, &parent)?;
                }
                Ok(())
            },
        )
        .unwrap();
        assert_eq!(fs::read(moved.join("root/usr/python")).unwrap(), b"code");
        assert!(!outside.join("root").exists());
    }
}
