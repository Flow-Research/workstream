//! In-guest PRE handoff. The source-derived worker owns defaults; only this
//! supervisor can turn its manifest into a project mount and launch a project.
use super::*;
use serde::Deserialize;
use serde_json::{json, Value};
use std::os::unix::fs::MetadataExt;
use workstream_checker_sdk::{canonical_hash, infrastructure_result, validate_result};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct WorkerFrame {
    protocol_version: String,
    operation: String,
    request_digest: String,
    lease_id: String,
    lease_generation: u64,
    payload: ProjectPayload,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ProjectPayload {
    request: Value,
    manifest: Value,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Manifest {
    schema_version: String,
    entries: Vec<Entry>,
}

#[derive(Deserialize)]
#[serde(tag = "entry_type", rename_all = "snake_case", deny_unknown_fields)]
enum Entry {
    Directory {
        normalized_path: String,
    },
    File {
        normalized_path: String,
        sha256: String,
        byte_count: u64,
        executable: bool,
    },
}

impl Entry {
    fn path(&self) -> &str {
        match self {
            Self::Directory { normalized_path }
            | Self::File {
                normalized_path, ..
            } => normalized_path,
        }
    }
}

/// Derived from the validated PRE bootstrap, never from project stdout.
pub(super) struct ProjectBinding<'a> {
    pub project_id: &'a str,
    pub task_id: &'a str,
    pub assignment_id: &'a str,
    pub attempt_id: &'a str,
    pub effective_plan_sha256: &'a str,
    pub requirement_id: &'a str,
    pub request_digest: &'a str,
    pub lease_id: &'a str,
    pub lease_generation: u64,
    pub operation_id: &'a str,
    pub source_sha256: &'a str,
    pub archive_sha256: &'a str,
    pub archive_byte_count: u64,
    pub image_digest: &'a str,
    pub configuration_digest: &'a str,
    pub registry_entry_digest: &'a str,
    pub maximum_control_bytes: usize,
    pub maximum_entries: usize,
    pub maximum_expanded_bytes: u64,
}

fn open_at(parent: &File, name: &str, directory: bool) -> Result<File> {
    if name.is_empty() || name.contains('/') || matches!(name, "." | "..") {
        return Err("PRE tree component invalid".into());
    }
    let descriptor = unsafe {
        libc::openat(
            parent.as_raw_fd(),
            c(name)?.as_ptr(),
            libc::O_RDONLY
                | libc::O_NOFOLLOW
                | libc::O_CLOEXEC
                | libc::O_NONBLOCK
                | if directory { libc::O_DIRECTORY } else { 0 },
        )
    };
    if descriptor < 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    Ok(unsafe { File::from_raw_fd(descriptor) })
}

fn own_readonly(file: &File, owner: u32, mode: u32) -> Result<()> {
    syscall_ok(unsafe { libc::fchown(file.as_raw_fd(), owner, u32::MAX) })?;
    syscall_ok(unsafe { libc::fchmod(file.as_raw_fd(), mode) })
}

fn seal_tree(
    root: &File,
    manifest: &Manifest,
    maximum_entries: usize,
    maximum_bytes: u64,
    owner: u32,
    check: &impl Fn() -> Result<()>,
) -> Result<()> {
    check()?;
    if manifest.schema_version != "workstream.submission_bundle_manifest.v1"
        || manifest.entries.len() > maximum_entries
        || maximum_entries == 0
    {
        return Err("PRE manifest bound invalid".into());
    }
    let mut entries = BTreeMap::new();
    let mut previous: Option<&str> = None;
    let mut total = 0u64;
    for entry in &manifest.entries {
        check()?;
        let path = entry.path();
        if path.len() > 4096
            || !material_path_is_relative(path)
            || path
                .split('/')
                .any(|part| part.is_empty() || matches!(part, "." | ".."))
            || previous.is_some_and(|value| value >= path)
        {
            return Err("PRE manifest path invalid".into());
        }
        if let Entry::File { byte_count, .. } = entry {
            total = total
                .checked_add(*byte_count)
                .ok_or("PRE expanded bytes overflow")?;
            if total > maximum_bytes {
                return Err("PRE expanded bytes exceeded".into());
            }
        }
        previous = Some(path);
        entries.insert(path, entry);
    }
    for path in entries.keys() {
        if let Some((parent, _)) = path.rsplit_once('/') {
            if !matches!(entries.get(parent), Some(Entry::Directory { .. })) {
                return Err("PRE manifest parent missing".into());
            }
        }
    }
    if !root.metadata()?.is_dir() {
        return Err("PRE tree root invalid".into());
    }
    own_readonly(root, owner, 0o555)?;
    // Directory handles anchor every lookup. No tree byte copy or host export.
    let mut directories = BTreeMap::new();
    directories.insert(String::new(), root.try_clone()?);
    let mut seen = HashSet::new();
    for (path, entry) in &entries {
        check()?;
        let (parent, name) = path.rsplit_once('/').unwrap_or(("", path));
        let directory = directories
            .get(parent)
            .ok_or("PRE tree parent unavailable")?;
        let mut file = open_at(directory, name, matches!(entry, Entry::Directory { .. }))?;
        let metadata = file.metadata()?;
        match entry {
            Entry::Directory { .. } => {
                own_readonly(&file, owner, 0o555)?;
                directories.insert((*path).to_owned(), file);
            }
            Entry::File {
                sha256,
                byte_count,
                executable,
                ..
            } => {
                if !metadata.is_file() || metadata.nlink() != 1 || metadata.len() != *byte_count {
                    return Err("PRE tree file identity differs".into());
                }
                own_readonly(&file, owner, if *executable { 0o555 } else { 0o444 })?;
                let mut hash = Sha256::new();
                let mut remaining = *byte_count;
                let mut buffer = [0; 65536];
                while remaining > 0 {
                    check()?;
                    let count = remaining.min(buffer.len() as u64) as usize;
                    file.read_exact(&mut buffer[..count])?;
                    hash.update(&buffer[..count]);
                    remaining -= count as u64;
                }
                if format!("sha256:{:x}", hash.finalize()) != *sha256
                    || file.read(&mut buffer[..1])? != 0
                {
                    return Err("PRE tree file content differs".into());
                }
            }
        }
        seen.insert((*path).to_owned());
    }
    // Exact inventory: otherwise an unmanifested file could enter the mount.
    for (parent, directory) in &directories {
        for child in fs::read_dir(format!("/proc/self/fd/{}", directory.as_raw_fd()))? {
            check()?;
            let name = child?
                .file_name()
                .into_string()
                .map_err(|_| "PRE tree name invalid")?;
            let path = if parent.is_empty() {
                name
            } else {
                format!("{parent}/{name}")
            };
            if !seen.remove(&path) {
                return Err("PRE tree has unmanifested entry".into());
            }
        }
    }
    if !seen.is_empty() {
        return Err("PRE tree inventory differs".into());
    }
    check()
}

fn project_request(
    binding: &ProjectBinding<'_>,
    frame: &[u8],
) -> Result<(workstream_checker_sdk::ValidatedRequest, Manifest)> {
    if frame.is_empty() || frame.len() > binding.maximum_control_bytes.min(64 * 1024 * 1024) {
        return Err("PRE worker control frame unbounded".into());
    }
    let frame: WorkerFrame = serde_json::from_slice(frame)?;
    if frame.protocol_version != "workstream.pre_submit_worker.v1"
        || frame.operation != "project"
        || frame.request_digest != binding.request_digest
        || frame.lease_id != binding.lease_id
        || frame.lease_generation != binding.lease_generation
    {
        return Err("PRE worker project binding differs".into());
    }
    let request = parse_request(&serde_json::to_vec(&frame.payload.request)?)?;
    let manifest_digest = canonical_hash(&frame.payload.manifest)?;
    let manifest: Manifest = serde_json::from_value(frame.payload.manifest)?;
    let input_entries: Vec<Value> = manifest
        .entries
        .iter()
        .map(|entry| match entry {
            Entry::Directory { normalized_path } => json!({"normalized_path":normalized_path,
            "entry_type":"directory", "byte_count":0,"sha256":null,"executable":null}),
            Entry::File {
                normalized_path,
                sha256,
                byte_count,
                executable,
            } => json!({
            "normalized_path":normalized_path,"entry_type":"file","byte_count":byte_count,
            "sha256":sha256,"executable":executable}),
        })
        .collect();
    let input = &request.value["input"];
    let identity = &request.value["identity"];
    let materials = request.value["materials"]
        .as_array()
        .ok_or("PRE material missing")?;
    if request.phase != "pre_submit"
        || request.image_digest != binding.image_digest
        || request.configuration_digest != binding.configuration_digest
        || request.registry_entry_digest != binding.registry_entry_digest
        || identity["project_id"] != binding.project_id
        || identity["task_id"] != binding.task_id
        || identity["assignment_id"] != binding.assignment_id
        || identity["attempt_id"] != binding.attempt_id
        || identity["effective_plan_sha256"] != binding.effective_plan_sha256
        || input["schema_version"] != "workstream.external_checker_pre_submit_input.v1"
        || input["project_id"] != binding.project_id
        || input["task_id"] != binding.task_id
        || input["assignment_id"] != binding.assignment_id
        || input["requirement_id"] != binding.requirement_id
        || input["archive_sha256"] != binding.archive_sha256
        || input["archive_byte_count"] != binding.archive_byte_count
        || input["semantic_manifest_sha256"] != manifest_digest
        || input["manifest"] != Value::Array(input_entries)
        || identity["operation_id"] != binding.operation_id
        || identity["attempt_request_digest"] != binding.request_digest
        || identity["source_sha256"] != binding.source_sha256
        || identity["lease_id"] != binding.lease_id
        || identity["lease_generation"] != binding.lease_generation
        || materials.len() != 1
        || materials[0]["archive_sha256"] != binding.archive_sha256
        || materials[0]["archive_byte_count"] != binding.archive_byte_count
        || materials[0]["semantic_manifest_sha256"] != manifest_digest
    {
        return Err("PRE derived project identity differs".into());
    }
    Ok((request, manifest))
}

/// The worker is waiting on its private control pipe when this phase runs.
/// `workspace` is the supervisor's private directory containing its projection;
/// the caller retains that directory until the project and worker are stopped.
#[allow(dead_code)] // PRE bootstrap dispatch is the remaining caller; ordinary Project is unchanged.
pub(super) fn run_project_phase(
    binding: &ProjectBinding<'_>,
    frame: &[u8],
    workspace: &Path,
    mut job: GuestJob,
    mut limits: ProjectLimits,
) -> Result<Value> {
    limits.validate(GuestCapabilities {
        model: false,
        execution: false,
    })?;
    let (request, manifest) = project_request(binding, frame)?;
    if request.cpu_millis > limits.cpu_millis || request.memory_bytes > limits.memory_bytes {
        return Err("PRE selected project resources exceed partition".into());
    }
    limits.cpu_millis = request.cpu_millis;
    limits.memory_bytes = request.memory_bytes;
    limits.maximum_output_bytes = limits
        .maximum_output_bytes
        .min(request.maximum_output_bytes);
    let selected_deadline = Instant::now()
        .checked_add(Duration::from_millis(request.deadline_ms))
        .ok_or("PRE selected deadline overflow")?;
    limits.deadline = Some(
        limits
            .deadline
            .ok_or("PRE deadline missing")?
            .min(selected_deadline),
    );
    let parent = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(workspace.parent().ok_or("PRE workspace parent missing")?)?;
    let metadata = parent.metadata()?;
    if !workspace.is_absolute() || metadata.uid() != 0 || metadata.mode() & 0o777 != 0o700 {
        return Err("PRE workspace custody invalid".into());
    }
    let name = workspace
        .file_name()
        .and_then(|name| name.to_str())
        .ok_or("PRE workspace name invalid")?;
    let root = open_at(&parent, name, true)?;
    seal_tree(
        &root,
        &manifest,
        binding.maximum_entries,
        binding.maximum_expanded_bytes,
        0,
        &|| limits.check_run_deadline(),
    )?;
    // The open directory descriptor keeps the exact verified inode as mount source.
    let root_path = PathBuf::from(format!("/proc/self/fd/{}", root.as_raw_fd()));
    let descriptor = unsafe {
        libc::openat(
            parent.as_raw_fd(),
            c("project-request.json")?.as_ptr(),
            libc::O_WRONLY | libc::O_CREAT | libc::O_EXCL | libc::O_NOFOLLOW | libc::O_CLOEXEC,
            0o400,
        )
    };
    if descriptor < 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    let mut writer = unsafe { File::from_raw_fd(descriptor) };
    writer.write_all(&serde_json::to_vec(&request.value)?)?;
    // Reopen the same inode read-only; never give the project a writable stdin.
    let request_file = File::open(format!("/proc/self/fd/{}", writer.as_raw_fd()))?;
    drop(writer);
    job.request = request.value.clone();
    let staged = StagedJob {
        request: request_file,
        roots: BTreeMap::from([("current".into(), root_path)]),
    };
    let outcome = run_project(
        job,
        GuestCapabilities {
            model: false,
            execution: false,
        },
        staged,
        File::open("/dev/null")?,
        limits,
    )?;
    let result = if outcome.oom_kills > 0 {
        infrastructure_result(&request, "capacity_exceeded")?
    } else if outcome.exit_code() != 0 {
        infrastructure_result(&request, "implementation_unavailable")?
    } else {
        match serde_json::from_slice::<Value>(&outcome.stdout) {
            Ok(value) if validate_result(&value, &request).is_ok() => value,
            _ => infrastructure_result(&request, "invalid_output")?,
        }
    };
    limits.check_run_deadline()?;
    Ok(
        json!({"request_digest": binding.request_digest, "lease_id": binding.lease_id,
        "lease_generation": binding.lease_generation, "result": result}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU64, Ordering};
    static NEXT: AtomicU64 = AtomicU64::new(0);
    const ABC_SHA: &str = "sha256:ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";

    struct Tree(PathBuf);
    impl Tree {
        fn new() -> Self {
            let path = std::env::temp_dir().join(format!(
                "ws-pre-tree-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            fs::create_dir(&path).unwrap();
            fs::set_permissions(&path, fs::Permissions::from_mode(0o700)).unwrap();
            fs::create_dir(path.join("d")).unwrap();
            fs::write(path.join("d/a"), b"abc").unwrap();
            Self(path)
        }
        fn open(&self) -> File {
            File::open(&self.0).unwrap()
        }
    }
    impl Drop for Tree {
        fn drop(&mut self) {
            fn writable(path: &Path) {
                fs::set_permissions(path, fs::Permissions::from_mode(0o700)).unwrap();
                for child in fs::read_dir(path).unwrap() {
                    let child = child.unwrap();
                    if child.file_type().unwrap().is_dir() {
                        writable(&child.path());
                    }
                }
            }
            writable(&self.0);
            fs::remove_dir_all(&self.0).unwrap();
        }
    }
    fn manifest() -> Manifest {
        serde_json::from_value(json!({"schema_version":"workstream.submission_bundle_manifest.v1",
            "entries":[{"normalized_path":"d","entry_type":"directory"},
            {"normalized_path":"d/a","entry_type":"file","byte_count":3,"sha256":ABC_SHA,"executable":false}]})).unwrap()
    }
    fn seal(tree: &Tree, manifest: &Manifest) -> Result<()> {
        // Exercise the real inode operations as the local owner. Root ownership
        // and denial to a distinct project UID require native qualification.
        seal_tree(
            &tree.open(),
            manifest,
            10,
            1024,
            unsafe { libc::geteuid() },
            &|| Ok(()),
        )
    }

    #[test]
    fn exact_tree_seals_readable_bytes_and_permissions() {
        let tree = Tree::new();
        seal(&tree, &manifest()).unwrap();
        assert_eq!(fs::read(tree.0.join("d/a")).unwrap(), b"abc");
        for (path, mode) in [
            (&tree.0, 0o555),
            (&tree.0.join("d"), 0o555),
            (&tree.0.join("d/a"), 0o444),
        ] {
            assert_eq!(fs::metadata(path).unwrap().mode() & 0o777, mode);
        }
        if unsafe { libc::geteuid() } != 0 {
            assert_eq!(
                OpenOptions::new()
                    .write(true)
                    .open(tree.0.join("d/a"))
                    .unwrap_err()
                    .kind(),
                std::io::ErrorKind::PermissionDenied
            );
        }
    }

    #[test]
    fn projected_tree_rejects_substitution_links_and_unmanifested_files() {
        for case in [
            "bytes",
            "length",
            "symlink",
            "directory_link",
            "hardlink",
            "extra",
            "missing",
        ] {
            let tree = Tree::new();
            match case {
                "bytes" => fs::write(tree.0.join("d/a"), b"abd").unwrap(),
                "length" => fs::write(tree.0.join("d/a"), b"abcd").unwrap(),
                "symlink" => {
                    fs::remove_file(tree.0.join("d/a")).unwrap();
                    std::os::unix::fs::symlink("../../outside", tree.0.join("d/a")).unwrap();
                }
                "directory_link" => {
                    fs::rename(tree.0.join("d"), tree.0.join("real")).unwrap();
                    std::os::unix::fs::symlink("real", tree.0.join("d")).unwrap();
                }
                "hardlink" => fs::hard_link(tree.0.join("d/a"), tree.0.join("alias")).unwrap(),
                "extra" => fs::write(tree.0.join("extra"), b"hidden").unwrap(),
                "missing" => fs::remove_file(tree.0.join("d/a")).unwrap(),
                _ => unreachable!(),
            }
            assert!(seal(&tree, &manifest()).is_err(), "accepted {case}");
        }
    }

    #[test]
    fn manifest_rejects_missing_parents_order_and_resource_overflow() {
        let tree = Tree::new();
        let mut value = manifest();
        value.entries.remove(0);
        assert!(seal(&tree, &value).is_err());
        let mut value = manifest();
        value.entries.reverse();
        assert!(seal(&tree, &value).is_err());
        let value = manifest();
        assert!(seal_tree(
            &tree.open(),
            &value,
            1,
            1024,
            unsafe { libc::geteuid() },
            &|| Ok(())
        )
        .is_err());
        assert!(seal_tree(
            &tree.open(),
            &value,
            10,
            2,
            unsafe { libc::geteuid() },
            &|| Ok(())
        )
        .is_err());
        assert!(seal_tree(
            &tree.open(),
            &value,
            10,
            1024,
            unsafe { libc::geteuid() },
            &|| Err("expired".into())
        )
        .is_err());
    }
    #[test]
    fn worker_project_request_binds_source_fence_manifest_and_selected_configuration() {
        let mut request: Value =
            serde_json::from_str(include_str!("../../fixtures/request.json")).unwrap();
        let manifest = json!({"schema_version":"workstream.submission_bundle_manifest.v1", "entries":[
                {"normalized_path":"d","entry_type":"directory"},
                {"normalized_path":"d/a","entry_type":"file","byte_count":3,"sha256":ABC_SHA,"executable":false}]});
        request["materials"][0]["semantic_manifest_sha256"] =
            json!(canonical_hash(&manifest).unwrap());
        request["input"] = json!({
            "schema_version":"workstream.external_checker_pre_submit_input.v1",
            "project_id":request["identity"]["project_id"],
            "task_id":request["identity"]["task_id"],
            "assignment_id":request["identity"]["assignment_id"],
            "requirement_id":"selected_requirement",
            "archive_sha256":request["materials"][0]["archive_sha256"],
            "archive_byte_count":request["materials"][0]["archive_byte_count"],
            "semantic_manifest_sha256":request["materials"][0]["semantic_manifest_sha256"],
            "manifest":[
                {"normalized_path":"d","entry_type":"directory","byte_count":0,"sha256":null,"executable":null},
                {"normalized_path":"d/a","entry_type":"file","byte_count":3,"sha256":ABC_SHA,"executable":false}
            ], "packet":{"summary":"fixture","contributor_attestation":"fixture"},
        });
        request["input_sha256"] = json!(canonical_hash(&request["input"]).unwrap());
        request.as_object_mut().unwrap().remove("request_digest");
        request["request_digest"] = json!(canonical_hash(&request).unwrap());
        let validated = parse_request(&serde_json::to_vec(&request).unwrap()).unwrap();
        let identity = &request["identity"];
        let material = &request["materials"][0];
        let binding = ProjectBinding {
            project_id: identity["project_id"].as_str().unwrap(),
            task_id: identity["task_id"].as_str().unwrap(),
            assignment_id: identity["assignment_id"].as_str().unwrap(),
            attempt_id: identity["attempt_id"].as_str().unwrap(),
            effective_plan_sha256: identity["effective_plan_sha256"].as_str().unwrap(),
            requirement_id: "selected_requirement",
            request_digest: identity["attempt_request_digest"].as_str().unwrap(),
            lease_id: identity["lease_id"].as_str().unwrap(),
            lease_generation: identity["lease_generation"].as_u64().unwrap(),
            operation_id: identity["operation_id"].as_str().unwrap(),
            source_sha256: identity["source_sha256"].as_str().unwrap(),
            archive_sha256: material["archive_sha256"].as_str().unwrap(),
            archive_byte_count: material["archive_byte_count"].as_u64().unwrap(),
            image_digest: &validated.image_digest,
            registry_entry_digest: &validated.registry_entry_digest,
            configuration_digest: &validated.configuration_digest,
            maximum_control_bytes: 1024 * 1024,
            maximum_entries: 10,
            maximum_expanded_bytes: 1024,
        };
        let valid = json!({"protocol_version":"workstream.pre_submit_worker.v1", "operation":"project",
            "request_digest":binding.request_digest, "lease_id":binding.lease_id,
            "lease_generation":binding.lease_generation,
            "payload":{"request":request,"manifest":manifest}});
        project_request(&binding, &serde_json::to_vec(&valid).unwrap()).unwrap();
        for field in [
            "request_digest",
            "lease_id",
            "lease_generation",
            "operation",
            "extra",
        ] {
            let mut changed = valid.clone();
            changed[field] = json!("foreign");
            assert!(
                project_request(&binding, &serde_json::to_vec(&changed).unwrap()).is_err(),
                "accepted {field}"
            );
        }
        let mut changed = valid.clone();
        changed["payload"]["manifest"]["schema_version"] = json!("foreign");
        assert!(project_request(&binding, &serde_json::to_vec(&changed).unwrap()).is_err());
        // Re-sign a valid foreign nested request: failure must be the locked
        // binding, not a stale request hash rejected by the shared SDK.
        for field in ["archive_sha256", "archive_byte_count"] {
            let mut changed = valid.clone();
            changed["payload"]["request"]["materials"][0][field] = if field == "archive_byte_count"
            {
                json!(binding.archive_byte_count + 1)
            } else {
                json!(ABC_SHA)
            };
            let nested = &mut changed["payload"]["request"];
            nested.as_object_mut().unwrap().remove("request_digest");
            nested["request_digest"] = json!(canonical_hash(nested).unwrap());
            parse_request(&serde_json::to_vec(nested).unwrap()).unwrap();
            assert!(project_request(&binding, &serde_json::to_vec(&changed).unwrap()).is_err());
        }
        for field in [
            "archive_sha256",
            "archive_byte_count",
            "semantic_manifest_sha256",
            "manifest",
            "project_id",
            "task_id",
            "assignment_id",
            "requirement_id",
        ] {
            let mut changed = valid.clone();
            let nested = &mut changed["payload"]["request"];
            nested["input"][field] = match field {
                "archive_byte_count" => json!(binding.archive_byte_count + 1),
                "manifest" => {
                    json!([{"normalized_path":"foreign","entry_type":"directory","byte_count":0,"sha256":null,"executable":null}])
                }
                "archive_sha256" | "semantic_manifest_sha256" => json!(ABC_SHA),
                "project_id" | "task_id" | "assignment_id" => {
                    json!("019b0000-0000-7000-8000-000000000099")
                }
                _ => json!("foreign"),
            };
            nested["input_sha256"] = json!(canonical_hash(&nested["input"]).unwrap());
            nested.as_object_mut().unwrap().remove("request_digest");
            nested["request_digest"] = json!(canonical_hash(nested).unwrap());
            parse_request(&serde_json::to_vec(nested).unwrap()).unwrap();
            assert!(
                project_request(&binding, &serde_json::to_vec(&changed).unwrap()).is_err(),
                "accepted input {field}"
            );
        }
        for field in [
            "project_id",
            "task_id",
            "assignment_id",
            "effective_plan_sha256",
        ] {
            let mut changed = valid.clone();
            let nested = &mut changed["payload"]["request"];
            nested["identity"][field] = if field == "effective_plan_sha256" {
                json!(ABC_SHA)
            } else {
                json!("019b0000-0000-7000-8000-000000000099")
            };
            nested.as_object_mut().unwrap().remove("request_digest");
            nested["request_digest"] = json!(canonical_hash(nested).unwrap());
            parse_request(&serde_json::to_vec(nested).unwrap()).unwrap();
            assert!(
                project_request(&binding, &serde_json::to_vec(&changed).unwrap()).is_err(),
                "accepted identity {field}"
            );
        }
        let mut trailing = serde_json::to_vec(&valid).unwrap();
        trailing.extend_from_slice(b"{}");
        assert!(project_request(&binding, &trailing).is_err());
        let narrow = ProjectBinding {
            maximum_control_bytes: 1,
            ..binding
        };
        assert!(project_request(&narrow, &serde_json::to_vec(&valid).unwrap()).is_err());
    }
}
