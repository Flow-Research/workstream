//! Opt-in Linux qualification executable. Never a production admission service.
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::os::fd::AsRawFd;
use std::os::unix::{
    fs::{DirBuilderExt, MetadataExt, OpenOptionsExt},
    process::CommandExt,
};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use workstream_smol_lifecycle_probe::{Control, Runtime};

type Result<T> = std::result::Result<T, &'static str>;
const OUTPUT_LIMIT: u64 = 1024 * 1024;
const CLEANUP_SECONDS: u64 = 15;

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Config {
    smolvm: PathBuf,
    expected_version: String,
    smolvm_sha256: String,
    image: String,
    image_archive_sha256: String,
    cpus: u8,
    memory_mib: u32,
    disk_gib: u64,
    deadline_seconds: u64,
    archive_sha256: String,
    archive_bytes: u64,
    maximum_expanded_bytes: u64,
    maximum_entries: u64,
    checker: Vec<String>,
    request: Value,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Lease {
    name: String,
    owner: String,
    expires_ms: u64,
    smolvm: PathBuf,
}

struct Smol {
    root: PathBuf,
    lease: Lease,
    config: Config,
    sequence: AtomicUsize,
}

fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("system clock")
        .as_millis() as u64
}

fn write_new(path: &Path, bytes: &[u8]) -> Result<()> {
    let mut f = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(path)
        .map_err(|_| "evidence_write_failed")?;
    f.write_all(bytes)
        .and_then(|_| f.sync_all())
        .map_err(|_| "evidence_write_failed")
}

fn json_bytes(value: &impl Serialize) -> Result<Vec<u8>> {
    serde_json::to_vec(value).map_err(|_| "invalid_json")
}

impl Smol {
    /// GNU timeout remains alive if the probe is killed. The expiry watcher
    /// waits beyond that deadline before removing this attempt's exact VM.
    fn call(&self, args: &[&str], control: &Control, stdin: Option<&Path>) -> Result<Vec<u8>> {
        let remaining = control.remaining()?;
        let seq = self.sequence.fetch_add(1, Ordering::Relaxed);
        let tag = format!("{}-{seq}", std::process::id());
        let out = self.root.join(format!("command-{tag}.stdout"));
        let err = self.root.join(format!("command-{tag}.stderr"));
        let stdout = OpenOptions::new()
            .create_new(true)
            .write(true)
            .mode(0o600)
            .open(&out)
            .map_err(|_| "evidence_write_failed")?;
        let stderr = OpenOptions::new()
            .create_new(true)
            .write(true)
            .mode(0o600)
            .open(&err)
            .map_err(|_| "evidence_write_failed")?;
        let mut command = Command::new("/usr/bin/timeout");
        command
            .args(["--signal=KILL", &format!("{:.3}s", remaining.as_secs_f64())])
            .arg(&self.lease.smolvm)
            .args(args)
            .env_clear()
            .env("HOME", std::env::var_os("HOME").ok_or("home_unavailable")?)
            .env("PATH", "/usr/local/bin:/usr/bin:/bin")
            .stdout(stdout)
            .stderr(stderr)
            .process_group(0);
        command.stdin(match stdin {
            Some(path) => Stdio::from(File::open(path).map_err(|_| "input_unavailable")?),
            None => Stdio::null(),
        });
        let mut child = command.spawn().map_err(|_| "runtime_unavailable")?;
        loop {
            let too_large = fs::metadata(&out)
                .map(|m| m.len())
                .unwrap_or(OUTPUT_LIMIT + 1)
                + fs::metadata(&err)
                    .map(|m| m.len())
                    .unwrap_or(OUTPUT_LIMIT + 1)
                > OUTPUT_LIMIT;
            if too_large || control.remaining().is_err() {
                // Only our freshly spawned command group. No machine-name or
                // global process matching is used to terminate a subprocess.
                unsafe {
                    libc::kill(-(child.id() as i32), libc::SIGKILL);
                }
                let _ = child.wait();
                return Err(if too_large {
                    "output_limit"
                } else {
                    "deadline_or_cancelled"
                });
            }
            match child.try_wait() {
                Ok(Some(status)) => {
                    return if status.success() {
                        fs::read(out).map_err(|_| "output_unavailable")
                    } else {
                        Err("runtime_command_failed")
                    }
                }
                Ok(None) => std::thread::sleep(Duration::from_millis(10)),
                Err(_) => {
                    unsafe {
                        libc::kill(-(child.id() as i32), libc::SIGKILL);
                    }
                    let _ = child.wait();
                    return Err("runtime_unavailable");
                }
            }
        }
    }

    fn inventory(&self, c: &Control) -> Result<Option<Value>> {
        let bytes = self.call(&["machine", "ls", "--json"], c, None)?;
        let value: Value = serde_json::from_slice(&bytes).map_err(|_| "inventory_invalid")?;
        let rows = value
            .as_array()
            .or_else(|| value.get("machines").and_then(Value::as_array))
            .ok_or("inventory_invalid")?;
        let matches: Vec<_> = rows
            .iter()
            .filter(|v| v.get("name").and_then(Value::as_str) == Some(&self.lease.name))
            .collect();
        if matches.len() > 1 {
            return Err("inventory_invalid");
        }
        if let Some(row) = matches.first() {
            if row
                .get("labels")
                .and_then(|v| v.get("workstream-probe-owner"))
                .and_then(Value::as_str)
                != Some(&self.lease.owner)
            {
                return Err("ownership_mismatch");
            }
            return Ok(Some((*row).clone()));
        }
        Ok(None)
    }

    fn copy(&self, source: &Path, destination: &str, c: &Control) -> Result<()> {
        self.call(
            &[
                "machine",
                "cp",
                source.to_str().ok_or("path_invalid")?,
                &format!("{}:{destination}", self.lease.name),
            ],
            c,
            None,
        )
        .map(|_| ())
    }

    fn remove(&self, c: &Control) -> Result<()> {
        let lock = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .mode(0o600)
            .custom_flags(libc::O_NOFOLLOW)
            .open(self.root.join("cleanup.lock"))
            .map_err(|_| "cleanup_unconfirmed")?;
        loop {
            c.remaining()?;
            if unsafe { libc::flock(lock.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } == 0 {
                break;
            }
            let error = std::io::Error::last_os_error();
            if error.raw_os_error() != Some(libc::EWOULDBLOCK) {
                return Err("cleanup_unconfirmed");
            }
            std::thread::sleep(Duration::from_millis(10));
        }
        if self.inventory(c)?.is_some() {
            self.call(
                &["machine", "delete", "--name", &self.lease.name, "--force"],
                c,
                None,
            )?;
        }
        if self.inventory(c)?.is_some() {
            return Err("cleanup_unconfirmed");
        }
        Ok(())
    }

    fn settle(&self, message: &[u8]) -> Result<()> {
        match fs::remove_file(self.root.join("submission.zip")) {
            Ok(()) => (),
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => (),
            Err(_) => return Err("scratch_cleanup_failed"),
        }
        if !self.root.join("cleanup-confirmed").exists() {
            match write_new(&self.root.join("cleanup-confirmed"), message) {
                Ok(()) => (),
                Err(_) if self.root.join("cleanup-confirmed").is_file() => (),
                Err(e) => return Err(e),
            }
        }
        Ok(())
    }
}

impl Runtime for Smol {
    fn prepare(&self, c: &Control) -> Result<()> {
        let action = || -> Result<()> {
            // No host volumes, published ports, credentials or network flag.
            self.call(
                &[
                    "machine",
                    "create",
                    "--name",
                    &self.lease.name,
                    "--label",
                    &format!("workstream-probe-owner={}", self.lease.owner),
                    "--image",
                    &self.config.image,
                    "--cpus",
                    &self.config.cpus.to_string(),
                    "--mem",
                    &self.config.memory_mib.to_string(),
                    "--storage",
                    &self.config.disk_gib.to_string(),
                    "--overlay",
                    "1",
                ],
                c,
                None,
            )?;
            // Boot without invoking the image's checker before input is ready.
            self.call(
                &[
                    "machine",
                    "start",
                    "--name",
                    &self.lease.name,
                    "--no-workload",
                ],
                c,
                None,
            )?;
            self.call(
                &[
                    "machine",
                    "exec",
                    "--name",
                    &self.lease.name,
                    "--",
                    "python",
                    "-I",
                    "-c",
                    "pass",
                ],
                c,
                None,
            )?;
            Ok(())
        };
        action().map_err(|error| match error {
            // Only a failed CLI exit during create/start/readiness is retried.
            // Cancellation, output limits, custody and local I/O errors are final.
            "runtime_command_failed" => "preparation_unavailable",
            other => other,
        })
    }

    fn execute(&self, c: &Control) -> Result<()> {
        self.copy(&self.root.join("submission.zip"), "/tmp/submission.zip", c)?;
        self.copy(&self.root.join("guest.py"), "/tmp/probe-guest.py", c)?;
        self.copy(
            &self.root.join("guest-input.json"),
            "/tmp/probe-input.json",
            c,
        )?;
        let output = self.call(
            &[
                "machine",
                "exec",
                "--name",
                &self.lease.name,
                "--user=0:0",
                "--interactive",
                "--",
                "python",
                "-I",
                "/tmp/probe-guest.py",
            ],
            c,
            Some(&self.root.join("checker-request.json")),
        )?;
        let value: Value = serde_json::from_slice(&output).map_err(|_| "checker_output_invalid")?;
        if value.get("request_digest") != self.config.request.get("request_digest")
            || value.get("registry_entry_id")
                != self.config.request["registry"].get("registry_entry_id")
            || value.get("registry_entry_digest")
                != self.config.request["registry"].get("entry_digest")
            || value.get("schema_version").and_then(Value::as_str)
                != Some("external_checker_result.v1")
            || value.get("phase").and_then(Value::as_str) != Some("pre_submit")
            || !matches!(
                value.get("outcome").and_then(Value::as_str),
                Some("completed" | "infrastructure_failed")
            )
        {
            return Err("checker_output_invalid");
        }
        let mut unsigned = value.clone();
        unsigned
            .as_object_mut()
            .ok_or("checker_output_invalid")?
            .remove("result_digest");
        let expected = format!("sha256:{:x}", Sha256::digest(json_bytes(&unsigned)?));
        if value.get("result_digest").and_then(Value::as_str) != Some(expected.as_str())
            || (value["outcome"] == "completed"
                && !matches!(
                    value.get("verdict").and_then(Value::as_str),
                    Some("passed" | "failed")
                ))
        {
            return Err("checker_output_invalid");
        }
        write_new(&self.root.join("checker-result.json"), &output)?;
        if value["outcome"] == "infrastructure_failed" {
            return Err("checker_infrastructure_failed");
        }
        // A failed WORK verdict is still a successfully executed probe.
        Ok(())
    }

    fn cleanup(&self, c: &Control) -> Result<()> {
        self.remove(c).map_err(|_| "cleanup_unconfirmed")
    }
}

fn receive(runtime: &Smol, c: &Control) -> Result<()> {
    let stdin = std::io::stdin();
    let mut input = stdin.lock();
    let fd = input.as_raw_fd();
    let flags = unsafe { libc::fcntl(fd, libc::F_GETFL) };
    if flags < 0 || unsafe { libc::fcntl(fd, libc::F_SETFL, flags | libc::O_NONBLOCK) } < 0 {
        return Err("upload_unavailable");
    }
    let outcome = (|| {
        let mut output = OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(runtime.root.join("submission.zip"))
            .map_err(|_| "upload_unavailable")?;
        let mut buffer = [0; 65536];
        let mut bytes = 0u64;
        let mut hash = Sha256::new();
        loop {
            c.remaining()?;
            match input.read(&mut buffer) {
                Ok(0) => break,
                Ok(n) => {
                    bytes += n as u64;
                    if bytes > runtime.config.archive_bytes {
                        return Err("upload_size_mismatch");
                    }
                    output
                        .write_all(&buffer[..n])
                        .map_err(|_| "upload_unavailable")?;
                    hash.update(&buffer[..n]);
                }
                Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                    std::thread::sleep(Duration::from_millis(10))
                }
                Err(_) => return Err("upload_disconnected"),
            }
        }
        if bytes != runtime.config.archive_bytes {
            return Err("upload_size_mismatch");
        }
        if format!("{:x}", hash.finalize()) != runtime.config.archive_sha256 {
            return Err("upload_digest_mismatch");
        }
        output.sync_all().map_err(|_| "upload_unavailable")
    })();
    unsafe {
        libc::fcntl(fd, libc::F_SETFL, flags);
    }
    outcome
}

fn file_digest(path: &Path) -> Result<String> {
    let mut file = File::open(path).map_err(|_| "digest_input_unavailable")?;
    let mut hasher = Sha256::new();
    let mut bytes = [0; 65536];
    loop {
        let n = file
            .read(&mut bytes)
            .map_err(|_| "digest_input_unavailable")?;
        if n == 0 {
            break;
        }
        hasher.update(&bytes[..n]);
    }
    Ok(format!("{:x}", hasher.finalize()))
}

fn load(root: PathBuf) -> Result<Smol> {
    let meta = fs::symlink_metadata(&root).map_err(|_| "trial_directory_invalid")?;
    if !meta.is_dir() || meta.uid() != unsafe { libc::geteuid() } || meta.mode() & 0o077 != 0 {
        return Err("trial_directory_invalid");
    }
    for name in ["config.json", "lease.json"] {
        let meta = fs::symlink_metadata(root.join(name)).map_err(|_| "lease_invalid")?;
        if !meta.is_file()
            || meta.uid() != unsafe { libc::geteuid() }
            || meta.mode() & 0o077 != 0
            || meta.len() > 1024 * 1024
        {
            return Err("lease_invalid");
        }
    }
    let config: Config = serde_json::from_slice(
        &fs::read(root.join("config.json")).map_err(|_| "config_unavailable")?,
    )
    .map_err(|_| "config_invalid")?;
    let lease: Lease = serde_json::from_slice(
        &fs::read(root.join("lease.json")).map_err(|_| "lease_unavailable")?,
    )
    .map_err(|_| "lease_invalid")?;
    if lease.owner.len() != 32
        || !lease.owner.bytes().all(|b| b.is_ascii_hexdigit())
        || lease.name != format!("ws-smol-probe-{}", lease.owner)
        || lease.smolvm
            != config
                .smolvm
                .canonicalize()
                .map_err(|_| "runtime_unavailable")?
        || file_digest(&lease.smolvm)? != config.smolvm_sha256
    {
        return Err("lease_invalid");
    }
    Ok(Smol {
        root,
        config,
        lease,
        sequence: AtomicUsize::new(0),
    })
}

fn watch(root: PathBuf) -> Result<()> {
    let runtime = load(root)?;
    // CLI timeout has a separate process lifetime; leave two seconds for it
    // to terminate in-flight creation before the crash sweeper examines ownership.
    while now_ms() < runtime.lease.expires_ms + 2000 {
        if runtime.root.join("cleanup-confirmed").exists() {
            return Ok(());
        }
        std::thread::sleep(Duration::from_millis(100));
    }
    runtime.cleanup(&Control::new(Duration::from_secs(CLEANUP_SECONDS)))?;
    runtime.settle(b"expiry watcher\n")?;
    Ok(())
}

fn start(config_path: &Path, root: &Path) -> Result<()> {
    if !cfg!(target_os = "linux") {
        return Err("linux_probe_required");
    }
    let config: Config =
        serde_json::from_slice(&fs::read(config_path).map_err(|_| "config_unavailable")?)
            .map_err(|_| "config_invalid")?;
    if !Path::new(&config.image).is_absolute()
        || file_digest(Path::new(&config.image))? != config.image_archive_sha256
    {
        return Err("image_archive_digest_mismatch");
    }
    if !config.smolvm.is_absolute()
        || !config.smolvm.is_file()
        || config.archive_sha256.len() != 64
        || !config.archive_sha256.bytes().all(|b| b.is_ascii_hexdigit())
        || config.smolvm_sha256.len() != 64
        || !config.smolvm_sha256.bytes().all(|b| b.is_ascii_hexdigit())
        || config.archive_bytes == 0
        || config.archive_bytes > 512 * 1024 * 1024
        || config.deadline_seconds == 0
        || config.deadline_seconds > 300
        || config.cpus == 0
        || config.cpus > 4
        || config.memory_mib < 128
        || config.memory_mib > 4096
        || config.disk_gib == 0
        || config.disk_gib > 8
        || config.checker.is_empty()
        || config.maximum_entries == 0
        || config.maximum_entries > 100_000
        || config.maximum_expanded_bytes == 0
        || config.maximum_expanded_bytes > 1024 * 1024 * 1024
    {
        return Err("probe_config_invalid");
    }
    if file_digest(&config.smolvm)? != config.smolvm_sha256 {
        return Err("runtime_digest_mismatch");
    }
    let kvm = File::open("/dev/kvm").map_err(|_| "kvm_unavailable")?;
    if unsafe { libc::ioctl(kvm.as_raw_fd(), 0xae00) } != 12 {
        return Err("kvm_unavailable");
    }
    fs::DirBuilder::new()
        .mode(0o700)
        .create(root)
        .map_err(|_| "trial_directory_must_be_new")?;
    let root = root.canonicalize().map_err(|_| "trial_directory_invalid")?;
    let mut random = [0u8; 16];
    File::open("/dev/urandom")
        .and_then(|mut f| f.read_exact(&mut random))
        .map_err(|_| "entropy_unavailable")?;
    let owner: String = random.iter().map(|b| format!("{b:02x}")).collect();
    let lease = Lease {
        name: format!("ws-smol-probe-{owner}"),
        owner,
        expires_ms: now_ms() + config.deadline_seconds * 1000,
        smolvm: config
            .smolvm
            .canonicalize()
            .map_err(|_| "runtime_unavailable")?,
    };
    write_new(&root.join("config.json"), &json_bytes(&config)?)?;
    write_new(&root.join("lease.json"), &json_bytes(&lease)?)?;
    write_new(&root.join("guest.py"), include_bytes!("../guest.py"))?;
    write_new(
        &root.join("guest-input.json"),
        &json_bytes(&json!({
            "archive_sha256": config.archive_sha256, "maximum_expanded_bytes": config.maximum_expanded_bytes,
            "maximum_entries": config.maximum_entries, "checker": config.checker,
        }))?,
    )?;
    write_new(
        &root.join("checker-request.json"),
        &json_bytes(&config.request)?,
    )?;
    let runtime = Smol {
        root,
        lease,
        config,
        sequence: AtomicUsize::new(0),
    };
    let version = runtime.call(&["--version"], &Control::new(Duration::from_secs(5)), None)?;
    if String::from_utf8_lossy(&version).trim() != runtime.config.expected_version {
        return Err("runtime_version_mismatch");
    }
    if runtime
        .inventory(&Control::new(Duration::from_secs(5)))?
        .is_some()
    {
        return Err("machine_already_exists");
    }
    let watch_output = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(runtime.root.join("watcher.log"))
        .map_err(|_| "evidence_write_failed")?;
    let mut watcher = Command::new(std::env::current_exe().map_err(|_| "probe_unavailable")?)
        .arg("watch")
        .arg(&runtime.root)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(watch_output)
        .process_group(0)
        .spawn()
        .map_err(|_| "watcher_unavailable")?;
    let budget = Duration::from_millis(runtime.lease.expires_ms.saturating_sub(now_ms()));
    let report = workstream_smol_lifecycle_probe::run(
        &runtime,
        Control::new(budget),
        Duration::from_secs(CLEANUP_SECONDS),
        |c| receive(&runtime, c),
    );
    if report.cleanup_confirmed {
        runtime.settle(b"request owner\n")?;
        let _ = watcher.wait();
    }
    write_new(&runtime.root.join("report.json"), &json_bytes(&report)?)?;
    println!(
        "{}",
        serde_json::to_string(&report).map_err(|_| "report_invalid")?
    );
    if report.outcome == "completed" {
        Ok(())
    } else {
        Err("probe_failed_see_report")
    }
}

fn main() {
    let args: Vec<_> = std::env::args_os().collect();
    let result = match args.as_slice() {
        [_, mode, root] if mode == "watch" => watch(PathBuf::from(root)),
        [_, config, root] => start(Path::new(config), Path::new(root)),
        _ => Err("usage: workstream-smol-lifecycle-probe CONFIG_JSON NEW_TRIAL_DIRECTORY < submission.zip"),
    };
    if let Err(error) = result {
        eprintln!("{error}");
        std::process::exit(1);
    }
}

#[cfg(test)]
mod process_tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;

    static FIXTURE_ID: AtomicUsize = AtomicUsize::new(0);
    struct Fixture(Smol);
    impl Drop for Fixture {
        fn drop(&mut self) {
            fs::remove_dir_all(&self.0.root).unwrap();
        }
    }
    fn fixture(owner: &str, body: &str) -> Fixture {
        let root = std::env::temp_dir().join(format!(
            "ws-smol-test-{}-{}",
            std::process::id(),
            FIXTURE_ID.fetch_add(1, Ordering::Relaxed)
        ));
        fs::DirBuilder::new().mode(0o700).create(&root).unwrap();
        let binary = root.join("runtime");
        let inventory = json!([{"name": "ws-smol-probe-11111111111111111111111111111111",
            "labels": {"workstream-probe-owner": owner}}]);
        fs::write(root.join("inventory"), json_bytes(&inventory).unwrap()).unwrap();
        fs::write(
            &binary,
            format!("#!/bin/sh\ncd '{}'\n{}\n", root.display(), body),
        )
        .unwrap();
        fs::set_permissions(&binary, fs::Permissions::from_mode(0o700)).unwrap();
        Fixture(Smol {
            root,
            lease: Lease {
                name: "ws-smol-probe-11111111111111111111111111111111".into(),
                owner: "11111111111111111111111111111111".into(),
                expires_ms: now_ms() + 5000,
                smolvm: binary.clone(),
            },
            config: Config {
                smolvm: binary,
                expected_version: "fake".into(),
                smolvm_sha256: String::new(),
                image: String::new(),
                image_archive_sha256: String::new(),
                cpus: 1,
                memory_mib: 128,
                disk_gib: 1,
                deadline_seconds: 5,
                archive_sha256: String::new(),
                archive_bytes: 1,
                maximum_expanded_bytes: 1,
                maximum_entries: 1,
                checker: vec![],
                request: json!({}),
            },
            sequence: AtomicUsize::new(0),
        })
    }

    #[test]
    fn foreign_label_prevents_delete_even_when_name_matches() {
        let f = fixture(
            "foreign",
            "if [ \"$2\" = ls ]; then cat inventory; else touch deleted; fi",
        );
        assert_eq!(
            f.0.remove(&Control::new(Duration::from_secs(2))),
            Err("ownership_mismatch")
        );
        assert!(!f.0.root.join("deleted").exists());
    }

    #[test]
    fn successful_delete_exit_is_not_confirmed_absence() {
        let f = fixture(
            "11111111111111111111111111111111",
            "if [ \"$2\" = ls ]; then cat inventory; else touch deleted; fi",
        );
        assert_eq!(
            f.0.remove(&Control::new(Duration::from_secs(2))),
            Err("cleanup_unconfirmed")
        );
        assert!(f.0.root.join("deleted").exists());
    }

    #[test]
    fn stalled_cli_is_bounded_by_work_deadline() {
        let f = fixture("owner", "sleep 30");
        let started = std::time::Instant::now();
        assert!(f
            .0
            .call(&[], &Control::new(Duration::from_millis(40)), None)
            .is_err());
        assert!(started.elapsed() < Duration::from_secs(2));
    }
}
