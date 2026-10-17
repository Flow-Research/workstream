//! Closed offline build/oracle continuation for the one approved project checker.

use super::*;
#[cfg(test)]
use serde_json::json;
use std::collections::BTreeSet;
use std::ffi::CString;
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
use std::os::unix::ffi::OsStrExt;
use workstream_checker_sdk::{completed_result, Finding, TerminalBenchmarkPlan};

const BASE_MANIFEST: &str =
    "sha256:6e13e65c55e33adf203d77ee371cf8bf5d81bd4902ef07565721f46bf44917af";
const PROFILE_VERSION: &str = "terminal_benchmark_build_oracle.v1";
const TEMPORARY_REPOSITORY: &str = "workstream.local/terminal-benchmark-candidate";
const OWNER_LABEL: &str = "workstream.owner=terminal-benchmark-checker-service-v1";
const BUILDER_WRITABLE_BYTES: u64 = 384 * 1024 * 1024;
const BUILDER_INTERNAL_TMPFS: &str = "/busybox:rw,noexec,nosuid,nodev,size=16777216";

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct TerminalBenchmarkProfile {
    profile_version: String,
    registry_entry_id: String,
    registry_entry_digest: String,
    checker_image_digest: String,
    builder: CacheEntry,
    approved_base: CacheEntry,
    sealed_cache: SealedCache,
    temporary_repository: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct SealedCache {
    root: PathBuf,
    uid: u32,
    gid: u32,
    mode: u32,
    entries: Vec<SealedCacheEntry>,
    total_count: u64,
    total_bytes: u64,
    inventory_digest: String,
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct SealedCacheEntry {
    path: String,
    kind: String,
    mode: u32,
    byte_count: u64,
    sha256: Option<String>,
}

impl TerminalBenchmarkProfile {
    pub(super) fn authorizes(&self, request: &ValidatedRequest) -> bool {
        request.phase == "post_submit"
            && self.profile_version == PROFILE_VERSION
            && self.registry_entry_id == request.registry_entry_id
            && self.registry_entry_digest == request.registry_entry_digest
            && self.checker_image_digest == request.image_digest
    }

    #[cfg(test)]
    pub(super) fn authorization_fixture(request: &ValidatedRequest) -> Self {
        let image = |repository: &str, manifest: &str, config: char| CacheEntry {
            repository: repository.into(),
            platform_manifest_digest: manifest.into(),
            platform_manifest_media_type: "application/vnd.oci.image.manifest.v1+json".into(),
            platform_manifest_byte_count: 1,
            operating_system: "linux".into(),
            architecture: "amd64".into(),
            config_image_id: format!("sha256:{}", config.to_string().repeat(64)),
        };
        Self {
            profile_version: PROFILE_VERSION.into(),
            registry_entry_id: request.registry_entry_id.clone(),
            registry_entry_digest: request.registry_entry_digest.clone(),
            checker_image_digest: request.image_digest.clone(),
            builder: image(
                "registry.example/workstream/builder",
                &format!("sha256:{}", "3".repeat(64)),
                '4',
            ),
            approved_base: image("docker.io/library/python", BASE_MANIFEST, '5'),
            sealed_cache: SealedCache {
                root: PathBuf::from("/tmp/cache"),
                uid: 1,
                gid: 1,
                mode: 0o555,
                entries: Vec::new(),
                total_count: 0,
                total_bytes: 0,
                inventory_digest: canonical_hash(&serde_json::json!([])).unwrap(),
            },
            temporary_repository: TEMPORARY_REPOSITORY.into(),
        }
    }
}

pub(super) fn cleanup_stale_resources(
    config: &ServiceConfig,
    profile: &TerminalBenchmarkProfile,
) -> Result<(), String> {
    let deadline = Instant::now() + CLEANUP_TIMEOUT;
    let listed = run_bounded_command(
        &config.docker_binary,
        &[
            "ps",
            "-aq",
            "--no-trunc",
            "--filter",
            &format!("label={OWNER_LABEL}"),
        ],
        deadline,
        1024 * 1024,
    )
    .map_err(|_| "terminal benchmark container recovery unavailable")?;
    if !listed.status.success() {
        return Err("terminal benchmark container recovery unavailable".into());
    }
    let ids = String::from_utf8(listed.stdout)
        .map_err(|_| "terminal benchmark container recovery invalid")?;
    for id in ids.lines().filter(|line| !line.is_empty()) {
        if !valid_full_container_id(id) {
            return Err("terminal benchmark container recovery invalid".into());
        }
        let inspected = run_bounded_command(
            &config.docker_binary,
            &["container", "inspect", id],
            deadline,
            1024 * 1024,
        )
        .map_err(|_| "terminal benchmark container recovery unavailable")?;
        if !inspected.status.success() || !owned_container(&inspected.stdout) {
            return Err("terminal benchmark container recovery identity differs".into());
        }
        if !remove_container_until(config, id, deadline) {
            return Err("terminal benchmark container recovery failed".into());
        }
    }

    let images = run_bounded_command(
        &config.docker_binary,
        &[
            "image",
            "ls",
            "--no-trunc",
            "--format",
            "{{.Repository}} {{.Tag}} {{.ID}}",
            &format!("{}:*", profile.temporary_repository),
        ],
        deadline,
        1024 * 1024,
    )
    .map_err(|_| "terminal benchmark image recovery unavailable")?;
    if !images.status.success() {
        return Err("terminal benchmark image recovery unavailable".into());
    }
    let images = String::from_utf8(images.stdout)
        .map_err(|_| "terminal benchmark image recovery invalid")?;
    for line in images.lines().filter(|line| !line.is_empty()) {
        let parts: Vec<&str> = line.split_ascii_whitespace().collect();
        if parts.len() != 3
            || parts[0] != profile.temporary_repository
            || !valid_attempt(parts[1])
            || !valid_digest(parts[2])
        {
            return Err("terminal benchmark image recovery identity differs".into());
        }
        let tag = format!("{}:{}", parts[0], parts[1]);
        let inspected = run_bounded_command(
            &config.docker_binary,
            &["image", "inspect", &tag],
            deadline,
            1024 * 1024,
        )
        .map_err(|_| "terminal benchmark image recovery unavailable")?;
        if !inspected.status.success() || !image_has_identity(&inspected.stdout, &tag, parts[2]) {
            return Err("terminal benchmark image recovery identity differs".into());
        }
        if !remove_image_until(config, &tag, deadline) {
            return Err("terminal benchmark image recovery failed".into());
        }
    }
    Ok(())
}

fn valid_attempt(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 32
        && value
            .chars()
            .all(|item| item.is_ascii_hexdigit() && !item.is_ascii_uppercase())
}

fn owned_container(bytes: &[u8]) -> bool {
    let Ok(value) = serde_json::from_slice::<Value>(bytes) else {
        return false;
    };
    let Some(containers) = value.as_array().filter(|items| items.len() == 1) else {
        return false;
    };
    let container = &containers[0];
    let Some(name) = container.get("Name").and_then(Value::as_str) else {
        return false;
    };
    let Some(labels) = container
        .pointer("/Config/Labels")
        .and_then(Value::as_object)
    else {
        return false;
    };
    let kind = labels
        .get("workstream.resource-kind")
        .and_then(Value::as_str);
    let Some(attempt) = labels
        .get("workstream.attempt")
        .and_then(Value::as_str)
        .filter(|attempt| valid_attempt(attempt))
    else {
        return false;
    };
    let name_matches_attempt = match kind {
        Some("builder") => name == format!("/ws-terminal-builder-{attempt}"),
        Some("candidate") => name == format!("/ws-terminal-candidate-{attempt}"),
        Some("reference") => [0, 1, 2]
            .into_iter()
            .any(|iteration| name == format!("/ws-terminal-reference-{attempt}-{iteration}")),
        _ => return false,
    };
    labels.get("workstream.owner").and_then(Value::as_str)
        == Some("terminal-benchmark-checker-service-v1")
        && labels
            .get("workstream.request-digest")
            .and_then(Value::as_str)
            .is_some_and(valid_digest)
        && labels
            .get("workstream.grant-id")
            .and_then(Value::as_str)
            .is_some_and(valid_grant_id)
        && name_matches_attempt
}

fn image_has_identity(bytes: &[u8], tag: &str, listed_id: &str) -> bool {
    serde_json::from_slice::<Value>(bytes)
        .ok()
        .and_then(|value| value.as_array().cloned())
        .is_some_and(|images| {
            images.len() == 1
                && images[0]
                    .get("Id")
                    .and_then(Value::as_str)
                    .filter(|id| valid_digest(id))
                    == Some(listed_id)
                && images[0]
                    .get("RepoTags")
                    .and_then(Value::as_array)
                    .is_some_and(|tags| tags.iter().any(|item| item.as_str() == Some(tag)))
        })
}

pub(super) fn validate_profile(
    config: &ServiceConfig,
    profile: &TerminalBenchmarkProfile,
) -> Result<(), String> {
    if config.isolation_mode != "gvisor" || config.runtime != "runsc" {
        return Err("terminal benchmark profile requires gvisor".into());
    }
    if profile.profile_version != PROFILE_VERSION
        || !valid_grant_id_value(&profile.registry_entry_id)
        || !valid_digest(&profile.registry_entry_digest)
        || !valid_digest(&profile.checker_image_digest)
        || profile.approved_base.platform_manifest_digest != BASE_MANIFEST
        || profile.temporary_repository != TEMPORARY_REPOSITORY
        || !valid_repository(&profile.temporary_repository)
        || profile.builder.platform_manifest_digest
            == profile.approved_base.platform_manifest_digest
        || !config
            .cache
            .iter()
            .any(|entry| cache_entry_matches(entry, &profile.builder))
        || !config
            .cache
            .iter()
            .any(|entry| cache_entry_matches(entry, &profile.approved_base))
        || profile.sealed_cache.mode & 0o222 != 0
        || profile.sealed_cache.root.starts_with(&config.material_root)
        || config.material_root.starts_with(&profile.sealed_cache.root)
        || config
            .socket_path
            .parent()
            .is_some_and(|parent| profile.sealed_cache.root.starts_with(parent))
    {
        return Err("terminal benchmark profile identity invalid".into());
    }
    for image in [&profile.builder, &profile.approved_base] {
        if !valid_repository(&image.repository)
            || !valid_digest(&image.platform_manifest_digest)
            || !valid_digest(&image.config_image_id)
            || image.operating_system != config.operating_system
            || image.architecture != config.architecture
        {
            return Err("terminal benchmark image identity invalid".into());
        }
    }
    verify_sealed_cache(&profile.sealed_cache)
}

fn cache_entry_matches(left: &CacheEntry, right: &CacheEntry) -> bool {
    left.repository == right.repository
        && left.platform_manifest_digest == right.platform_manifest_digest
        && left.platform_manifest_media_type == right.platform_manifest_media_type
        && left.platform_manifest_byte_count == right.platform_manifest_byte_count
        && left.operating_system == right.operating_system
        && left.architecture == right.architecture
        && left.config_image_id == right.config_image_id
}

fn valid_grant_id_value(value: &str) -> bool {
    value.len() == 36
        && value.as_bytes()[8] == b'-'
        && value.as_bytes()[13] == b'-'
        && value.as_bytes()[18] == b'-'
        && value.as_bytes()[23] == b'-'
        && value.char_indices().all(|(index, item)| {
            matches!(index, 8 | 13 | 18 | 23)
                || (item.is_ascii_hexdigit() && !item.is_ascii_uppercase())
        })
}

struct ScratchMeter {
    remaining_bytes: u64,
    remaining_entries: u64,
}

impl ScratchMeter {
    fn entry(&mut self) -> Result<(), &'static str> {
        if self.remaining_entries == 0 {
            return Err("capacity_exceeded");
        }
        self.remaining_entries -= 1;
        Ok(())
    }

    fn bytes(&mut self, count: u64) -> Result<(), &'static str> {
        self.remaining_bytes = self
            .remaining_bytes
            .checked_sub(count)
            .ok_or("capacity_exceeded")?;
        Ok(())
    }

    fn reserve_remaining_bytes(&mut self) -> Result<u64, &'static str> {
        if self.remaining_bytes == 0 {
            return Err("capacity_exceeded");
        }
        let reserved = self.remaining_bytes;
        self.remaining_bytes = 0;
        Ok(reserved)
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
struct OracleObservation {
    status: i32,
    output_digest: String,
}

enum BuilderOutcome {
    Succeeded,
    WorkFailure,
    CapacityFailure,
}

pub(super) struct TerminalBenchmarkExecution<'a> {
    pub(super) config: &'a ServiceConfig,
    pub(super) profile: &'a TerminalBenchmarkProfile,
    pub(super) request: &'a ValidatedRequest,
    pub(super) grant: &'a VerifiedGrant,
    pub(super) client: &'a UnixStream,
    pub(super) deadline: Instant,
    pub(super) output: &'a mut OutputMeter,
    pub(super) cleanup: &'a mut EmergencyCleanupBudget,
}

struct ExecutionContext<'a> {
    config: &'a ServiceConfig,
    profile: &'a TerminalBenchmarkProfile,
    request: &'a ValidatedRequest,
    grant: &'a VerifiedGrant,
    client: &'a UnixStream,
    deadline: Instant,
}

struct BuilderInputs<'a> {
    context: &'a Path,
    runtime: &'a Path,
    name: &'a str,
    tag: &'a str,
    attempt_id: &'a str,
    candidate_tar_byte_limit: u64,
}

pub(super) fn execute_terminal_benchmark(
    execution: TerminalBenchmarkExecution<'_>,
    plan: &TerminalBenchmarkPlan,
) -> Result<Value, &'static str> {
    let TerminalBenchmarkExecution {
        config,
        profile,
        request,
        grant,
        client,
        deadline,
        output,
        cleanup,
    } = execution;
    if !profile.authorizes(request) || plan.external_task_id != configured_task(request)? {
        return Err("invalid_output");
    }
    let (runtime, limits) = grant.runtime.as_ref().ok_or("material_unavailable")?;
    if grant.binding_digest.is_empty() || grant.root.join("runtime") != *runtime {
        return Err("material_unavailable");
    }
    verify_sealed_cache(&profile.sealed_cache).map_err(|_| "implementation_unavailable")?;
    inspect_profile_image(config, &profile.builder, client, deadline, output, cleanup)?;
    inspect_profile_image(
        config,
        &profile.approved_base,
        client,
        deadline,
        output,
        cleanup,
    )?;
    let execution = ExecutionContext {
        config,
        profile,
        request,
        grant,
        client,
        deadline,
    };
    let mut scratch = ScratchMeter {
        remaining_bytes: limits.byte_allowance,
        remaining_entries: limits.entry_allowance,
    };
    let context = project_build_context(grant, runtime, &mut scratch)?;
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|_| "implementation_unavailable")?
        .as_nanos();
    let tag = format!("{}:{nonce:x}", profile.temporary_repository);
    let attempt_id = format!("{nonce:x}");
    let tar = runtime.join("candidate.tar");
    scratch.entry()?;
    OpenOptions::new()
        .create_new(true)
        .write(true)
        .mode(0o600)
        .open(&tar)
        .and_then(|file| file.sync_all())
        .map_err(|_| "implementation_unavailable")?;
    let candidate_tar_byte_limit = scratch.reserve_remaining_bytes()?;

    let mut containers = Vec::new();
    let attempt = (|| {
        let builder = format!("ws-terminal-builder-{nonce:x}");
        containers.push(builder.clone());
        let builder_outcome = run_builder(
            &execution,
            BuilderInputs {
                context: &context,
                runtime,
                name: &builder,
                tag: &tag,
                attempt_id: &attempt_id,
                candidate_tar_byte_limit,
            },
            output,
            cleanup,
        )?;
        match remove_container_work(config, &builder, client, deadline, output, cleanup) {
            RemovalOutcome::Confirmed => {}
            RemovalOutcome::Recovered => {
                containers.retain(|item| item != &builder);
                return Err("implementation_unavailable");
            }
            RemovalOutcome::Unsettled => return Err("implementation_unavailable"),
        }
        containers.retain(|item| item != &builder);
        if let Some(result) = builder_result(request, builder_outcome)? {
            return Ok(result);
        }
        let tar_size = fs::metadata(&tar)
            .map_err(|_| "implementation_unavailable")?
            .len();
        if tar_size == 0 || tar_size > candidate_tar_byte_limit {
            return Err("capacity_exceeded");
        }
        let tar_text = tar.to_str().ok_or("implementation_unavailable")?;
        let loaded = command(
            &execution,
            &["load".into(), "--input".into(), tar_text.into()],
            output,
            cleanup,
        )?;
        if !loaded.status.success() {
            return Err("implementation_unavailable");
        }
        let image_id = inspect_loaded_image(&execution, &tag, output, cleanup)?;

        let candidate = format!("ws-terminal-candidate-{nonce:x}");
        containers.push(candidate.clone());
        let candidate_status = run_oracle(
            &execution,
            &candidate,
            &image_id,
            false,
            &attempt_id,
            output,
            cleanup,
        )?;
        match remove_container_work(config, &candidate, client, deadline, output, cleanup) {
            RemovalOutcome::Confirmed => {}
            RemovalOutcome::Recovered => {
                containers.retain(|item| item != &candidate);
                return Err("implementation_unavailable");
            }
            RemovalOutcome::Unsettled => return Err("implementation_unavailable"),
        }
        containers.retain(|item| item != &candidate);
        if let Some(result) = candidate_result(request, &candidate_status)? {
            return Ok(result);
        }
        let mut stable = None;
        for repetition in 0..3 {
            let name = format!("ws-terminal-reference-{nonce:x}-{repetition}");
            containers.push(name.clone());
            let status = run_oracle(
                &execution,
                &name,
                &image_id,
                true,
                &attempt_id,
                output,
                cleanup,
            )?;
            match remove_container_work(config, &name, client, deadline, output, cleanup) {
                RemovalOutcome::Confirmed => {}
                RemovalOutcome::Recovered => {
                    containers.retain(|item| item != &name);
                    return Err("implementation_unavailable");
                }
                RemovalOutcome::Unsettled => return Err("implementation_unavailable"),
            }
            containers.retain(|item| item != &name);
            if let Some(result) = reference_result(request, &mut stable, status)? {
                return Ok(result);
            }
        }
        completed_result(request, Vec::new()).map_err(|_| "invalid_output")
    })();
    let attempt = attempt.and_then(|result| {
        output.bytes(
            serde_json::to_vec(&result)
                .map_err(|_| "invalid_output")?
                .len(),
        )?;
        Ok(result)
    });

    let mut cleanup_ok = true;
    for name in containers.iter().rev() {
        cleanup_ok &= remove_container_cleanup(config, name, cleanup);
    }
    cleanup_ok &= remove_image_cleanup(config, &tag, cleanup);
    if !cleanup_ok {
        return Err(UNSETTLED_RESOURCE_ERROR);
    }
    verify_sealed_cache(&profile.sealed_cache).map_err(|_| "implementation_unavailable")?;
    attempt
}

fn configured_task(request: &ValidatedRequest) -> Result<&str, &'static str> {
    let configuration = request
        .value
        .get("configuration")
        .and_then(Value::as_object)
        .ok_or("invalid_output")?;
    if configuration.len() != 2
        || configuration.get("schema_version").and_then(Value::as_str)
            != Some("terminal_benchmark_project.v1")
    {
        return Err("invalid_output");
    }
    configuration
        .get("external_task_id")
        .and_then(Value::as_str)
        .ok_or("invalid_output")
}

fn work_failure(
    request: &ValidatedRequest,
    code: &str,
    message: &str,
) -> Result<Value, &'static str> {
    completed_result(
        request,
        vec![Finding {
            check_id: "terminal.execution".into(),
            code: code.into(),
            level: "error".into(),
            message: message.into(),
            path: None,
            line: None,
        }],
    )
    .map_err(|_| "invalid_output")
}

fn builder_result(
    request: &ValidatedRequest,
    outcome: BuilderOutcome,
) -> Result<Option<Value>, &'static str> {
    match outcome {
        BuilderOutcome::Succeeded => Ok(None),
        BuilderOutcome::WorkFailure => work_failure(
            request,
            "build_failed",
            "Submitted Dockerfile did not build.",
        )
        .map(Some),
        BuilderOutcome::CapacityFailure => Err("capacity_exceeded"),
    }
}

fn candidate_result(
    request: &ValidatedRequest,
    observation: &OracleObservation,
) -> Result<Option<Value>, &'static str> {
    match observation.status {
        0 => work_failure(
            request,
            "starter_unexpectedly_passed",
            "Unchanged starter passed the project tests.",
        )
        .map(Some),
        1 => Ok(None),
        _ => Err("implementation_unavailable"),
    }
}

fn reference_result(
    request: &ValidatedRequest,
    stable: &mut Option<OracleObservation>,
    observation: OracleObservation,
) -> Result<Option<Value>, &'static str> {
    if observation.status != 0 {
        return work_failure(
            request,
            "reference_failed",
            "Reference solution did not pass the project tests.",
        )
        .map(Some);
    }
    if stable
        .as_ref()
        .is_some_and(|previous| previous != &observation)
    {
        return work_failure(
            request,
            "reference_unstable",
            "Reference result changed across fresh isolated runs.",
        )
        .map(Some);
    }
    *stable = Some(observation);
    Ok(None)
}

fn project_build_context(
    grant: &VerifiedGrant,
    runtime: &Path,
    meter: &mut ScratchMeter,
) -> Result<PathBuf, &'static str> {
    let context = runtime.join("build-context");
    create_directory(&context, meter)?;
    copy_verified(grant, &context, ".dockerignore", meter)?;
    create_directory(&context.join("environment"), meter)?;
    copy_verified(grant, &context, "environment/Dockerfile", meter)?;
    create_directory(&context.join("workspace"), meter)?;
    copy_verified(grant, &context, "workspace/program.py", meter)?;
    seal_projection(&context)?;
    let inventory = inspect_workspace(
        &context,
        fs::metadata(runtime)
            .map_err(|_| "material_unavailable")?
            .uid(),
        fs::metadata(runtime)
            .map_err(|_| "material_unavailable")?
            .gid(),
    )
    .map_err(|_| "material_unavailable")?;
    let expected: BTreeSet<_> = [
        ".dockerignore",
        "environment/Dockerfile",
        "workspace/program.py",
    ]
    .into_iter()
    .collect();
    if inventory
        .files
        .iter()
        .map(|item| item.normalized_path.as_str())
        .collect::<BTreeSet<_>>()
        != expected
    {
        return Err("material_unavailable");
    }
    Ok(context)
}

fn create_directory(path: &Path, meter: &mut ScratchMeter) -> Result<(), &'static str> {
    meter.entry()?;
    fs::create_dir(path).map_err(|_| "implementation_unavailable")?;
    fs::set_permissions(path, fs::Permissions::from_mode(0o700))
        .map_err(|_| "implementation_unavailable")
}

fn copy_verified(
    grant: &VerifiedGrant,
    target_root: &Path,
    relative: &str,
    meter: &mut ScratchMeter,
) -> Result<(), &'static str> {
    let expected = grant
        .files
        .iter()
        .find(|item| item.normalized_path == relative)
        .ok_or("material_unavailable")?;
    let mut source = open_workspace_file(&grant.workspace, relative)?;
    let before = source.metadata().map_err(|_| "material_unavailable")?;
    if !before.file_type().is_file()
        || before.file_type().is_symlink()
        || before.len() != expected.byte_count
        || (before.mode() & 0o777) != if expected.executable { 0o500 } else { 0o400 }
    {
        return Err("material_unavailable");
    }
    meter.entry()?;
    meter.bytes(before.len())?;
    let mut bytes = Vec::with_capacity(before.len() as usize);
    source
        .read_to_end(&mut bytes)
        .map_err(|_| "material_unavailable")?;
    if bytes.len() as u64 != expected.byte_count
        || format!("sha256:{:x}", Sha256::digest(&bytes)) != expected.sha256
    {
        return Err("material_unavailable");
    }
    let target = target_root.join(relative);
    let mut target_file = OpenOptions::new()
        .create_new(true)
        .write(true)
        .mode(0o600)
        .open(&target)
        .map_err(|_| "implementation_unavailable")?;
    target_file
        .write_all(&bytes)
        .map_err(|_| "implementation_unavailable")?;
    target_file
        .sync_all()
        .map_err(|_| "implementation_unavailable")?;
    fs::set_permissions(&target, fs::Permissions::from_mode(before.mode() & 0o777))
        .map_err(|_| "implementation_unavailable")?;
    let after = source.metadata().map_err(|_| "material_unavailable")?;
    if (before.dev(), before.ino(), before.len(), before.mode())
        != (after.dev(), after.ino(), after.len(), after.mode())
    {
        return Err("material_unavailable");
    }
    Ok(())
}

fn open_workspace_file(root: &Path, relative: &str) -> Result<File, &'static str> {
    if !safe_relative_path(relative) {
        return Err("material_unavailable");
    }
    let root = File::open(root).map_err(|_| "material_unavailable")?;
    let mut directory = OwnedFd::from(root);
    let parts: Vec<&str> = relative.split('/').collect();
    for part in &parts[..parts.len() - 1] {
        directory = openat(
            directory.as_raw_fd(),
            part,
            libc::O_RDONLY | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC,
        )?;
    }
    let file = openat(
        directory.as_raw_fd(),
        parts.last().ok_or("material_unavailable")?,
        libc::O_RDONLY | libc::O_NOFOLLOW | libc::O_CLOEXEC,
    )?;
    Ok(File::from(file))
}

fn openat(parent: i32, name: &str, flags: i32) -> Result<OwnedFd, &'static str> {
    let name = CString::new(name).map_err(|_| "material_unavailable")?;
    // SAFETY: `parent` is a live owned directory descriptor and `name` is NUL terminated.
    let descriptor = unsafe { libc::openat(parent, name.as_ptr(), flags) };
    if descriptor < 0 {
        return Err("material_unavailable");
    }
    // SAFETY: `openat` returned a new descriptor whose ownership transfers here.
    Ok(unsafe { OwnedFd::from_raw_fd(descriptor) })
}

fn seal_projection(path: &Path) -> Result<(), &'static str> {
    for entry in fs::read_dir(path).map_err(|_| "implementation_unavailable")? {
        let entry = entry.map_err(|_| "implementation_unavailable")?;
        let metadata =
            fs::symlink_metadata(entry.path()).map_err(|_| "implementation_unavailable")?;
        if metadata.file_type().is_symlink() {
            return Err("implementation_unavailable");
        }
        if metadata.file_type().is_dir() {
            seal_projection(&entry.path())?;
        } else if !metadata.file_type().is_file() {
            return Err("implementation_unavailable");
        }
    }
    fs::set_permissions(path, fs::Permissions::from_mode(0o500))
        .map_err(|_| "implementation_unavailable")?;
    File::open(path)
        .and_then(|directory| directory.sync_all())
        .map_err(|_| "implementation_unavailable")
}

fn run_builder(
    execution: &ExecutionContext<'_>,
    inputs: BuilderInputs<'_>,
    output: &mut OutputMeter,
    cleanup: &mut EmergencyCleanupBudget,
) -> Result<BuilderOutcome, &'static str> {
    let ExecutionContext {
        config,
        profile,
        request,
        grant,
        ..
    } = execution;
    let BuilderInputs {
        context,
        runtime,
        name,
        tag,
        attempt_id,
        candidate_tar_byte_limit,
    } = inputs;
    let image = format!(
        "{}@{}",
        profile.builder.repository, profile.builder.platform_manifest_digest
    );
    let cpus = format!("{:.3}", request.cpu_millis as f64 / 1000.0);
    let memory = request.memory_bytes.to_string();
    let context_mount = format!("type=bind,src={},dst=/project,readonly", context.display());
    let cache_mount = format!(
        "type=bind,src={},dst=/cache,readonly",
        profile.sealed_cache.root.display()
    );
    let output_mount = format!(
        "type=bind,src={},dst=/out/candidate.tar",
        runtime.join("candidate.tar").display()
    );
    let file_size_limit = docker_file_size_limit(candidate_tar_byte_limit);
    let labels = labels(request, grant, attempt_id, "builder");
    let mut arguments = vec![
        "create".into(),
        "--pull=never".into(),
        "--name".into(),
        name.into(),
        "--runtime".into(),
        config.runtime.clone(),
        "--network".into(),
        "none".into(),
        "--user".into(),
        "0:0".into(),
        "--cap-drop".into(),
        "ALL".into(),
        "--cap-add".into(),
        "CHOWN".into(),
        "--cap-add".into(),
        "DAC_OVERRIDE".into(),
        "--cap-add".into(),
        "FOWNER".into(),
        "--cap-add".into(),
        "SYS_CHROOT".into(),
        "--security-opt".into(),
        "no-new-privileges".into(),
        "--pids-limit".into(),
        "128".into(),
        "--memory".into(),
        memory,
        "--cpus".into(),
        cpus,
        "--storage-opt".into(),
        format!("size={BUILDER_WRITABLE_BYTES}"),
        "--ulimit".into(),
        file_size_limit,
        "--tmpfs".into(),
        BUILDER_INTERNAL_TMPFS.into(),
        "--mount".into(),
        context_mount,
        "--mount".into(),
        cache_mount,
        "--mount".into(),
        output_mount,
        image,
        "--dockerfile=/project/environment/Dockerfile".into(),
        "--context=dir:///project".into(),
        "--cache=true".into(),
        "--cache-dir=/cache".into(),
        "--cache-run-layers=false".into(),
        "--cache-copy-layers=false".into(),
        "--no-push".into(),
        "--no-push-cache".into(),
        "--tar-path=/out/candidate.tar".into(),
        format!("--destination={tag}"),
        "--force".into(),
        "--log-format=text".into(),
    ];
    for label in labels {
        arguments.splice(4..4, ["--label".into(), label]);
    }
    let created = command(execution, &arguments, output, cleanup)?;
    if !created.status.success() {
        return Err("implementation_unavailable");
    }
    let started = command(
        execution,
        &["start".into(), "--attach".into(), name.into()],
        output,
        cleanup,
    )?;
    if started.status.success() {
        return Ok(BuilderOutcome::Succeeded);
    }
    if container_oom(execution, name, output, cleanup)? || output_indicates_capacity(&started) {
        return Ok(BuilderOutcome::CapacityFailure);
    }
    Ok(BuilderOutcome::WorkFailure)
}

fn docker_file_size_limit(limit: u64) -> String {
    format!("fsize={limit}:{limit}")
}

fn run_oracle(
    execution: &ExecutionContext<'_>,
    name: &str,
    image_id: &str,
    reference: bool,
    attempt_id: &str,
    output: &mut OutputMeter,
    cleanup: &mut EmergencyCleanupBudget,
) -> Result<OracleObservation, &'static str> {
    let ExecutionContext {
        config,
        request,
        grant,
        ..
    } = execution;
    let tests = format!(
        "type=bind,src={},dst=/tests,readonly",
        grant.workspace.join("tests").display()
    );
    let mut arguments = vec![
        "create".into(),
        "--pull=never".into(),
        "--name".into(),
        name.into(),
        "--runtime".into(),
        config.runtime.clone(),
        "--network".into(),
        "none".into(),
        "--read-only".into(),
        "--user".into(),
        "65532:65532".into(),
        "--cap-drop".into(),
        "ALL".into(),
        "--security-opt".into(),
        "no-new-privileges".into(),
        "--pids-limit".into(),
        "32".into(),
        "--memory".into(),
        request.memory_bytes.to_string(),
        "--cpus".into(),
        format!("{:.3}", request.cpu_millis as f64 / 1000.0),
        "--tmpfs".into(),
        "/tmp:rw,noexec,nosuid,nodev,size=16777216".into(),
        "--mount".into(),
        tests,
    ];
    for label in labels(
        request,
        grant,
        attempt_id,
        if reference { "reference" } else { "candidate" },
    ) {
        arguments.push("--label".into());
        arguments.push(label);
    }
    if reference {
        arguments.push("--mount".into());
        arguments.push(format!(
            "type=bind,src={},dst=/workspace/program.py,readonly",
            grant.workspace.join("solution/program.py").display()
        ));
    }
    arguments.extend([
        image_id.into(),
        "python".into(),
        "/tests/test_task.py".into(),
        "/workspace/program.py".into(),
    ]);
    let created = command(execution, &arguments, output, cleanup)?;
    if !created.status.success() {
        return Err("implementation_unavailable");
    }
    let result = command(
        execution,
        &["start".into(), "--attach".into(), name.into()],
        output,
        cleanup,
    )?;
    if !result.status.success()
        && (container_oom(execution, name, output, cleanup)? || output_indicates_capacity(&result))
    {
        return Err("capacity_exceeded");
    }
    let mut observed = Sha256::new();
    observed.update((result.stdout.len() as u64).to_be_bytes());
    observed.update(&result.stdout);
    observed.update((result._stderr.len() as u64).to_be_bytes());
    observed.update(&result._stderr);
    Ok(OracleObservation {
        status: result.status.code().unwrap_or(125),
        output_digest: format!("sha256:{:x}", observed.finalize()),
    })
}

fn container_oom(
    execution: &ExecutionContext<'_>,
    name: &str,
    output: &mut OutputMeter,
    cleanup: &mut EmergencyCleanupBudget,
) -> Result<bool, &'static str> {
    let inspected = command(
        execution,
        &[
            "container".into(),
            "inspect".into(),
            "--format".into(),
            "{{.State.OOMKilled}}".into(),
            name.into(),
        ],
        output,
        cleanup,
    )?;
    if !inspected.status.success() {
        return Err("implementation_unavailable");
    }
    match inspected.stdout.as_slice() {
        b"true\n" | b"true" => Ok(true),
        b"false\n" | b"false" => Ok(false),
        _ => Err("implementation_unavailable"),
    }
}

fn output_indicates_capacity(output: &BoundedCommandOutput) -> bool {
    [&output.stdout, &output._stderr].into_iter().any(|bytes| {
        String::from_utf8_lossy(bytes)
            .to_ascii_lowercase()
            .contains("no space left on device")
            || String::from_utf8_lossy(bytes)
                .to_ascii_lowercase()
                .contains("resource temporarily unavailable")
    })
}

fn labels(
    request: &ValidatedRequest,
    grant: &VerifiedGrant,
    attempt_id: &str,
    kind: &str,
) -> [String; 5] {
    [
        OWNER_LABEL.into(),
        format!("workstream.request-digest={}", request.request_digest),
        format!("workstream.grant-id={}", grant.grant_id),
        format!("workstream.attempt={attempt_id}"),
        format!("workstream.resource-kind={kind}"),
    ]
}

fn command(
    execution: &ExecutionContext<'_>,
    arguments: &[String],
    output: &mut OutputMeter,
    cleanup: &mut EmergencyCleanupBudget,
) -> Result<BoundedCommandOutput, &'static str> {
    let borrowed: Vec<&str> = arguments.iter().map(String::as_str).collect();
    let result = run_bounded_command_cancellable(
        &execution.config.docker_binary,
        &borrowed,
        execution.deadline,
        output.remaining,
        execution.client,
        cleanup,
    )
    .map_err(map_command_error)?;
    output.charge(&result)?;
    Ok(result)
}

fn map_command_error(error: String) -> &'static str {
    if error == "process deadline exceeded" {
        "deadline_exceeded"
    } else if error == "process output unbounded" {
        "invalid_output"
    } else {
        "implementation_unavailable"
    }
}

fn inspect_profile_image(
    config: &ServiceConfig,
    image: &CacheEntry,
    client: &UnixStream,
    deadline: Instant,
    output: &mut OutputMeter,
    cleanup: &mut EmergencyCleanupBudget,
) -> Result<(), &'static str> {
    let reference = format!("{}@{}", image.repository, image.platform_manifest_digest);
    let result = run_bounded_command_cancellable(
        &config.docker_binary,
        &["image", "inspect", "--format", "{{json .}}", &reference],
        deadline,
        output.remaining,
        client,
        cleanup,
    )
    .map_err(map_command_error)?;
    output.charge(&result)?;
    validate_inspected_image(image, &result).map_err(|_| "implementation_unavailable")
}

fn inspect_loaded_image(
    execution: &ExecutionContext<'_>,
    tag: &str,
    output: &mut OutputMeter,
    cleanup: &mut EmergencyCleanupBudget,
) -> Result<String, &'static str> {
    let result = command(
        execution,
        &[
            "image".into(),
            "inspect".into(),
            "--format".into(),
            "{{.Id}}".into(),
            tag.into(),
        ],
        output,
        cleanup,
    )?;
    if !result.status.success() {
        return Err("implementation_unavailable");
    }
    let id = String::from_utf8(result.stdout).map_err(|_| "implementation_unavailable")?;
    let id = id.trim();
    if !valid_digest(id) {
        return Err("implementation_unavailable");
    }
    Ok(id.into())
}

fn remove_image_until(config: &ServiceConfig, tag: &str, deadline: Instant) -> bool {
    if Instant::now() >= deadline {
        return false;
    }
    if run_bounded_command(
        &config.docker_binary,
        &["image", "rm", "-f", tag],
        deadline,
        64 * 1024,
    )
    .is_err()
    {
        return false;
    }
    matches!(
        run_bounded_command(
            &config.docker_binary,
            &["image", "ls", "--no-trunc", "--quiet", tag],
            deadline,
            64 * 1024,
        ),
        Ok(output) if successful_empty_inventory(&output)
    )
}

fn remove_image_cleanup(
    config: &ServiceConfig,
    tag: &str,
    cleanup: &mut EmergencyCleanupBudget,
) -> bool {
    let deadline = cleanup.deadline();
    let removed = run_bounded_command(
        &config.docker_binary,
        &["image", "rm", "-f", tag],
        deadline,
        cleanup.remaining_output,
    );
    let Ok(removed) = removed else {
        return false;
    };
    if cleanup.charge(&removed).is_err() {
        return false;
    }
    let inventory = run_bounded_command(
        &config.docker_binary,
        &["image", "ls", "--no-trunc", "--quiet", tag],
        deadline,
        cleanup.remaining_output,
    );
    matches!(inventory, Ok(output) if cleanup.charge(&output).is_ok() && successful_empty_inventory(&output))
}

fn verify_sealed_cache(cache: &SealedCache) -> Result<(), String> {
    if !cache.root.is_absolute()
        || cache
            .root
            .components()
            .any(|part| matches!(part, Component::ParentDir))
        || !valid_digest(&cache.inventory_digest)
        || cache.entries.len() as u64 != cache.total_count
        || cache.entries.iter().any(|entry| {
            entry.mode & 0o222 != 0
                || !matches!(entry.kind.as_str(), "directory" | "file")
                || (entry.kind == "directory" && (entry.byte_count != 0 || entry.sha256.is_some()))
                || (entry.kind == "file"
                    && (entry
                        .sha256
                        .as_deref()
                        .is_none_or(|digest| !valid_digest(digest))))
        })
    {
        return Err("sealed cache configuration invalid".into());
    }
    let canonical = fs::canonicalize(&cache.root).map_err(|_| "sealed cache missing")?;
    let configured_root =
        CString::new(cache.root.as_os_str().as_bytes()).map_err(|_| "sealed cache root invalid")?;
    // SAFETY: the configured path is a NUL-free absolute path and the descriptor is owned below.
    let descriptor = unsafe {
        libc::open(
            configured_root.as_ptr(),
            libc::O_RDONLY | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC,
        )
    };
    if descriptor < 0 {
        return Err("sealed cache missing".into());
    }
    // SAFETY: `open` returned a new descriptor whose ownership transfers here.
    let root_descriptor = unsafe { OwnedFd::from_raw_fd(descriptor) };
    let root_file = File::from(root_descriptor);
    let root = root_file.metadata().map_err(|_| "sealed cache missing")?;
    if canonical != cache.root
        || !root.file_type().is_dir()
        || root.file_type().is_symlink()
        || root.uid() != cache.uid
        || root.gid() != cache.gid
        || root.mode() & 0o777 != cache.mode
    {
        return Err("sealed cache root differs".into());
    }
    let mut observed = Vec::new();
    walk_cache(
        &root_file,
        Path::new(""),
        cache.uid,
        cache.gid,
        &mut observed,
    )?;
    observed.sort_by(|left, right| left.path.cmp(&right.path));
    if observed != cache.entries
        || observed.iter().map(|item| item.byte_count).sum::<u64>() != cache.total_bytes
        || canonical_hash(&serde_json::to_value(&observed).map_err(|_| "sealed cache invalid")?)
            .map_err(|_| "sealed cache invalid")?
            != cache.inventory_digest
    {
        return Err("sealed cache inventory differs".into());
    }
    Ok(())
}

fn walk_cache(
    directory: &File,
    relative: &Path,
    uid: u32,
    gid: u32,
    output: &mut Vec<SealedCacheEntry>,
) -> Result<(), String> {
    let mut names = fs::read_dir(format!("/proc/self/fd/{}", directory.as_raw_fd()))
        .map_err(|_| "sealed cache unreadable")?
        .map(|item| item.map(|entry| entry.file_name()))
        .collect::<Result<Vec<_>, _>>()
        .map_err(|_| "sealed cache unreadable")?;
    names.sort();
    for name in names {
        let name = name.to_str().ok_or("sealed cache path invalid")?;
        if !safe_relative_path(name) {
            return Err("sealed cache path invalid".into());
        }
        let name_c = CString::new(name).map_err(|_| "sealed cache path invalid")?;
        // SAFETY: the parent descriptor is live and the child name is NUL terminated.
        let descriptor = unsafe {
            libc::openat(
                directory.as_raw_fd(),
                name_c.as_ptr(),
                libc::O_RDONLY | libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK,
            )
        };
        if descriptor < 0 {
            return Err("sealed cache entry unavailable".into());
        }
        // SAFETY: `openat` returned a new descriptor whose ownership transfers here.
        let opened = File::from(unsafe { OwnedFd::from_raw_fd(descriptor) });
        let metadata = opened
            .metadata()
            .map_err(|_| "sealed cache entry missing")?;
        if metadata.uid() != uid || metadata.gid() != gid || metadata.file_type().is_symlink() {
            return Err("sealed cache entry identity differs".into());
        }
        let next = relative.join(name);
        let normalized = next
            .to_str()
            .ok_or("sealed cache path invalid")?
            .replace('\\', "/");
        if !safe_relative_path(&normalized) {
            return Err("sealed cache path invalid".into());
        }
        if metadata.file_type().is_dir() {
            output.push(SealedCacheEntry {
                path: normalized,
                kind: "directory".into(),
                mode: metadata.mode() & 0o777,
                byte_count: 0,
                sha256: None,
            });
            walk_cache(&opened, &next, uid, gid, output)?;
        } else if metadata.file_type().is_file() {
            let before = (
                metadata.dev(),
                metadata.ino(),
                metadata.len(),
                metadata.mode(),
                metadata.uid(),
                metadata.gid(),
            );
            let mut file = opened;
            let mut digest = Sha256::new();
            let count = std::io::copy(&mut file, &mut digest)
                .map_err(|_| "sealed cache file unreadable")?;
            let after = file
                .metadata()
                .map_err(|_| "sealed cache file unavailable")?;
            if before
                != (
                    after.dev(),
                    after.ino(),
                    after.len(),
                    after.mode(),
                    after.uid(),
                    after.gid(),
                )
            {
                return Err("sealed cache file changed".into());
            }
            output.push(SealedCacheEntry {
                path: normalized,
                kind: "file".into(),
                mode: metadata.mode() & 0o777,
                byte_count: count,
                sha256: Some(format!("sha256:{:x}", digest.finalize())),
            });
        } else {
            return Err("sealed cache special entry rejected".into());
        }
    }
    Ok(())
}

fn safe_relative_path(path: &str) -> bool {
    !path.is_empty()
        && !path.starts_with('/')
        && path.split('/').all(|part| !matches!(part, "" | "." | ".."))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn scratch_meter_admits_exact_limit_and_rejects_next_entry_before_creation() {
        let mut meter = ScratchMeter {
            remaining_bytes: 1,
            remaining_entries: 1,
        };
        assert!(meter.entry().is_ok());
        assert_eq!(meter.entry(), Err("capacity_exceeded"));
        assert!(meter.bytes(1).is_ok());
        assert_eq!(meter.bytes(1), Err("capacity_exceeded"));

        let mut reserved = ScratchMeter {
            remaining_bytes: 4096,
            remaining_entries: 0,
        };
        assert_eq!(reserved.reserve_remaining_bytes(), Ok(4096));
        assert_eq!(reserved.reserve_remaining_bytes(), Err("capacity_exceeded"));
        assert_eq!(reserved.bytes(1), Err("capacity_exceeded"));
        assert_eq!(docker_file_size_limit(4096), "fsize=4096:4096");
    }

    #[test]
    fn build_and_oracle_work_failures_are_distinct_completed_results() {
        let request = request("post_submit");
        let finding_code = |result: &Value| {
            result["findings"][0]["code"]
                .as_str()
                .expect("work failure has one coded finding")
                .to_owned()
        };

        let build = builder_result(&request, BuilderOutcome::WorkFailure)
            .unwrap()
            .unwrap();
        let starter = candidate_result(
            &request,
            &OracleObservation {
                status: 0,
                output_digest: format!("sha256:{}", "1".repeat(64)),
            },
        )
        .unwrap()
        .unwrap();
        let reference = reference_result(
            &request,
            &mut None,
            OracleObservation {
                status: 1,
                output_digest: format!("sha256:{}", "2".repeat(64)),
            },
        )
        .unwrap()
        .unwrap();
        let mut stable = Some(OracleObservation {
            status: 0,
            output_digest: format!("sha256:{}", "3".repeat(64)),
        });
        let unstable = reference_result(
            &request,
            &mut stable,
            OracleObservation {
                status: 0,
                output_digest: format!("sha256:{}", "4".repeat(64)),
            },
        )
        .unwrap()
        .unwrap();

        assert_eq!(
            [build, starter, reference, unstable].map(|result| finding_code(&result)),
            [
                "build_failed",
                "starter_unexpectedly_passed",
                "reference_failed",
                "reference_unstable",
            ]
        );
        assert!(builder_result(&request, BuilderOutcome::Succeeded)
            .unwrap()
            .is_none());
        assert_eq!(
            builder_result(&request, BuilderOutcome::CapacityFailure)
                .err()
                .as_deref(),
            Some("capacity_exceeded")
        );
        assert!(candidate_result(
            &request,
            &OracleObservation {
                status: 1,
                output_digest: format!("sha256:{}", "5".repeat(64)),
            },
        )
        .unwrap()
        .is_none());
    }

    #[test]
    fn kernel_file_size_limit_allows_exact_bytes_and_rejects_plus_one() {
        const LIMIT: usize = 4096;
        let root = temporary_directory("file-size-limit");
        fs::create_dir(&root).unwrap();
        let path = root.join("candidate.tar");
        let file = OpenOptions::new()
            .create_new(true)
            .write(true)
            .mode(0o600)
            .open(&path)
            .unwrap();
        let descriptor = file.as_raw_fd();
        // SAFETY: the child performs only libc calls on inherited storage and
        // descriptors before `_exit`; the parent waits for that exact child.
        let pid = unsafe { libc::fork() };
        assert!(pid >= 0);
        if pid == 0 {
            let limit = libc::rlimit {
                rlim_cur: LIMIT as libc::rlim_t,
                rlim_max: LIMIT as libc::rlim_t,
            };
            unsafe {
                libc::signal(libc::SIGXFSZ, libc::SIG_IGN);
                if libc::setrlimit(libc::RLIMIT_FSIZE, &limit) != 0 {
                    libc::_exit(10);
                }
                let exact = [b'x'; LIMIT];
                if libc::write(descriptor, exact.as_ptr().cast(), exact.len()) != LIMIT as isize {
                    libc::_exit(11);
                }
                let extra = [b'y'; 1];
                if libc::write(descriptor, extra.as_ptr().cast(), extra.len()) != -1 {
                    libc::_exit(12);
                }
                libc::_exit(0);
            }
        }
        drop(file);
        let mut status = 0;
        // SAFETY: `pid` is the positive PID returned by fork and `status` is writable.
        assert_eq!(unsafe { libc::waitpid(pid, &mut status, 0) }, pid);
        assert!(libc::WIFEXITED(status));
        assert_eq!(libc::WEXITSTATUS(status), 0);
        assert_eq!(fs::metadata(&path).unwrap().len(), LIMIT as u64);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn builder_command_applies_the_reserved_file_size_limit() {
        let root = temporary_directory("builder-fsize-command");
        let context = root.join("context");
        let runtime = root.join("runtime");
        let capture = root.join("arguments");
        fs::create_dir_all(&context).unwrap();
        fs::create_dir(&runtime).unwrap();
        let docker = root.join("docker");
        fs::write(
            &docker,
            format!(
                r#"#!/bin/sh
if test "$1" = create; then
  printf '%s\n' "$@" > "{capture}"
  previous=
  fsize_matched=
  tmpfs_matched=
  for argument in "$@"; do
    if test "$previous" = --ulimit && test "$argument" = fsize=4096:4096; then
      fsize_matched=yes
    fi
    if test "$previous" = --tmpfs && test "$argument" = /busybox:rw,noexec,nosuid,nodev,size=16777216; then
      tmpfs_matched=yes
    fi
    previous="$argument"
  done
  test "$fsize_matched" = yes || exit 64
  test "$tmpfs_matched" = yes || exit 65
  exit 0
fi
test "$1 $2" = "start --attach" && exit 0
exit 2
"#,
                capture = capture.display(),
            ),
        )
        .unwrap();
        fs::set_permissions(&docker, fs::Permissions::from_mode(0o700)).unwrap();
        let profile = test_profile();
        let request = request("post_submit");
        let grant = test_grant(&root);
        let config = test_service_config(&root, docker);
        let (_peer, client) = UnixStream::pair().unwrap();
        let execution = ExecutionContext {
            config: &config,
            profile: &profile,
            request: &request,
            grant: &grant,
            client: &client,
            deadline: Instant::now() + Duration::from_secs(10),
        };
        let mut output = OutputMeter::new(4096);
        let mut cleanup = EmergencyCleanupBudget::new();

        assert!(matches!(
            run_builder(
                &execution,
                BuilderInputs {
                    context: &context,
                    runtime: &runtime,
                    name: "ws-terminal-builder-a1",
                    tag: "workstream.local/terminal-benchmark-candidate:a1",
                    attempt_id: "a1",
                    candidate_tar_byte_limit: 4096,
                },
                &mut output,
                &mut cleanup,
            ),
            Ok(BuilderOutcome::Succeeded)
        ));
        let captured = fs::read_to_string(&capture).unwrap();
        assert!(captured.contains("--ulimit\nfsize=4096:4096\n"));
        assert!(captured.contains("--tmpfs\n/busybox:rw,noexec,nosuid,nodev,size=16777216\n"));

        assert!(run_builder(
            &execution,
            BuilderInputs {
                context: &context,
                runtime: &runtime,
                name: "ws-terminal-builder-a2",
                tag: "workstream.local/terminal-benchmark-candidate:a2",
                attempt_id: "a2",
                candidate_tar_byte_limit: 4095,
            },
            &mut output,
            &mut cleanup,
        )
        .is_err());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn profile_authority_is_exact_and_post_only() {
        let profile = TerminalBenchmarkProfile {
            profile_version: PROFILE_VERSION.into(),
            registry_entry_id: "019a0000-0000-7000-8000-000000000001".into(),
            registry_entry_digest: format!("sha256:{}", "1".repeat(64)),
            checker_image_digest: format!("sha256:{}", "2".repeat(64)),
            builder: image_entry(),
            approved_base: image_entry(),
            sealed_cache: empty_cache(),
            temporary_repository: TEMPORARY_REPOSITORY.into(),
        };
        let post = request("post_submit");
        assert!(profile.authorizes(&post));
        let mut pre = request("pre_submit");
        pre.registry_entry_id = profile.registry_entry_id.clone();
        assert!(!profile.authorizes(&pre));
        let mut substituted = post.clone();
        substituted.image_digest = format!("sha256:{}", "9".repeat(64));
        assert!(!profile.authorizes(&substituted));
        substituted = post;
        substituted.registry_entry_digest = format!("sha256:{}", "8".repeat(64));
        assert!(!profile.authorizes(&substituted));
    }

    #[test]
    fn terminal_profile_refuses_docker_dev_before_cache_or_runtime_use() {
        let request = request("post_submit");
        let profile = TerminalBenchmarkProfile::authorization_fixture(&request);
        let config = test_service_config(
            Path::new("/tmp/workstream-terminal-profile-test"),
            PathBuf::from("/bin/false"),
        );

        assert_eq!(
            validate_profile(&config, &profile).unwrap_err(),
            "terminal benchmark profile requires gvisor"
        );
    }

    #[test]
    fn sealed_cache_rehash_rejects_mutation_and_inventory_substitution() {
        let root = temporary_directory("cache");
        fs::create_dir(&root).unwrap();
        let blob = root.join("blob");
        fs::write(&blob, b"abc").unwrap();
        fs::set_permissions(&blob, fs::Permissions::from_mode(0o400)).unwrap();
        fs::set_permissions(&root, fs::Permissions::from_mode(0o500)).unwrap();
        let cache = cache_snapshot(&root);
        verify_sealed_cache(&cache).unwrap();

        fs::set_permissions(&blob, fs::Permissions::from_mode(0o600)).unwrap();
        fs::write(&blob, b"abd").unwrap();
        fs::set_permissions(&blob, fs::Permissions::from_mode(0o400)).unwrap();
        assert!(verify_sealed_cache(&cache).is_err());
        fs::write(&blob, b"abc").unwrap_err();

        let mut wrong_owner = cache_snapshot(&root);
        wrong_owner.uid = wrong_owner.uid.saturating_add(1);
        assert!(verify_sealed_cache(&wrong_owner).is_err());

        fs::set_permissions(&blob, fs::Permissions::from_mode(0o600)).unwrap();
        fs::write(&blob, b"abc").unwrap();
        fs::set_permissions(&blob, fs::Permissions::from_mode(0o400)).unwrap();
        verify_sealed_cache(&cache).unwrap();
        fs::set_permissions(&root, fs::Permissions::from_mode(0o700)).unwrap();
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn sealed_cache_rejects_extra_missing_link_special_and_wrong_mode_entries() {
        for kind in ["extra", "missing", "link", "special", "mode"] {
            let root = temporary_directory(kind);
            fs::create_dir(&root).unwrap();
            let blob = root.join("blob");
            fs::write(&blob, b"abc").unwrap();
            fs::set_permissions(&blob, fs::Permissions::from_mode(0o400)).unwrap();
            fs::set_permissions(&root, fs::Permissions::from_mode(0o500)).unwrap();
            let cache = cache_snapshot(&root);
            fs::set_permissions(&root, fs::Permissions::from_mode(0o700)).unwrap();
            match kind {
                "extra" => {
                    fs::write(root.join("extra"), b"x").unwrap();
                    fs::set_permissions(root.join("extra"), fs::Permissions::from_mode(0o400))
                        .unwrap();
                }
                "missing" => fs::remove_file(&blob).unwrap(),
                "link" => std::os::unix::fs::symlink(&blob, root.join("link")).unwrap(),
                "special" => {
                    let fifo = CString::new(root.join("fifo").as_os_str().as_bytes()).unwrap();
                    // SAFETY: `fifo` is a NUL-terminated path below the test directory.
                    assert_eq!(unsafe { libc::mkfifo(fifo.as_ptr(), 0o400) }, 0);
                }
                "mode" => fs::set_permissions(&blob, fs::Permissions::from_mode(0o600)).unwrap(),
                _ => unreachable!(),
            }
            fs::set_permissions(&root, fs::Permissions::from_mode(0o500)).unwrap();
            assert!(verify_sealed_cache(&cache).is_err(), "{kind}");
            fs::set_permissions(&root, fs::Permissions::from_mode(0o700)).unwrap();
            fs::remove_dir_all(root).unwrap();
        }
    }

    #[test]
    fn projected_builder_context_contains_only_rehashed_build_inputs() {
        let root = temporary_directory("projection");
        let workspace = root.join("workspace");
        let runtime = root.join("runtime");
        for directory in [
            workspace.clone(),
            workspace.join("environment"),
            workspace.join("workspace"),
            workspace.join("solution"),
            workspace.join("tests"),
            runtime.clone(),
        ] {
            fs::create_dir_all(directory).unwrap();
        }
        for (path, bytes) in [
            (".dockerignore", b"solution/\ntests/\n".as_slice()),
            ("environment/Dockerfile", b"FROM fixed\n".as_slice()),
            ("workspace/program.py", b"raise SystemExit(1)\n".as_slice()),
            ("solution/program.py", b"print('private')\n".as_slice()),
            ("tests/test_task.py", b"print('private')\n".as_slice()),
        ] {
            fs::write(workspace.join(path), bytes).unwrap();
            fs::set_permissions(workspace.join(path), fs::Permissions::from_mode(0o400)).unwrap();
        }
        for directory in ["environment", "workspace", "solution", "tests"] {
            fs::set_permissions(workspace.join(directory), fs::Permissions::from_mode(0o500))
                .unwrap();
        }
        fs::set_permissions(&workspace, fs::Permissions::from_mode(0o500)).unwrap();
        fs::set_permissions(&runtime, fs::Permissions::from_mode(0o700)).unwrap();
        let files = [
            ".dockerignore",
            "environment/Dockerfile",
            "workspace/program.py",
            "solution/program.py",
            "tests/test_task.py",
        ]
        .into_iter()
        .map(|path| {
            let bytes = fs::read(workspace.join(path)).unwrap();
            GrantFile {
                normalized_path: path.into(),
                byte_count: bytes.len() as u64,
                sha256: format!("sha256:{:x}", Sha256::digest(bytes)),
                executable: false,
            }
        })
        .collect();
        let grant = VerifiedGrant {
            grant_id: "extract_0123456789abcdef0123456789abcdef".into(),
            root: root.clone(),
            workspace: workspace.clone(),
            files,
            runtime: None,
            binding_digest: format!("sha256:{}", "1".repeat(64)),
        };
        let mut meter = ScratchMeter {
            remaining_bytes: 1024,
            remaining_entries: 6,
        };
        let context = project_build_context(&grant, &runtime, &mut meter).unwrap();
        let metadata = fs::metadata(&context).unwrap();
        let observed = inspect_workspace(&context, metadata.uid(), metadata.gid()).unwrap();
        assert_eq!(
            observed
                .files
                .iter()
                .map(|item| item.normalized_path.as_str())
                .collect::<BTreeSet<_>>(),
            BTreeSet::from([
                ".dockerignore",
                "environment/Dockerfile",
                "workspace/program.py",
            ])
        );
        assert!(!context.join("solution").exists());
        assert!(!context.join("tests").exists());
        assert_eq!(meter.remaining_entries, 0);

        make_tree_writable(&workspace);
        fs::set_permissions(&runtime, fs::Permissions::from_mode(0o700)).unwrap();
        make_tree_writable(&context);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn projected_builder_context_rejects_a_source_symlink_without_following_it() {
        let root = temporary_directory("projection-link");
        let workspace = root.join("workspace");
        fs::create_dir_all(workspace.join("workspace")).unwrap();
        let outside = root.join("outside.py");
        fs::write(&outside, b"private\n").unwrap();
        std::os::unix::fs::symlink(&outside, workspace.join("workspace/program.py")).unwrap();
        assert_eq!(
            open_workspace_file(&workspace, "workspace/program.py")
                .unwrap_err()
                .to_string(),
            "material_unavailable"
        );
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn recovery_image_identity_binds_the_listed_id_and_exact_tag() {
        let tag = "workstream.local/terminal-benchmark-candidate:a1";
        let metadata = serde_json::to_vec(&json!([{
            "Id": format!("sha256:{}", "b".repeat(64)),
            "RepoTags": [tag],
        }]))
        .unwrap();
        let listed_id = format!("sha256:{}", "b".repeat(64));
        assert!(image_has_identity(&metadata, tag, &listed_id));
        assert!(!image_has_identity(
            &metadata,
            tag,
            &format!("sha256:{}", "c".repeat(64)),
        ));
        assert!(!image_has_identity(
            &metadata,
            "workstream.local/terminal-benchmark-candidate:a2",
            &listed_id,
        ));
    }

    #[test]
    fn recovered_container_name_is_bound_to_attempt_and_reference_iteration() {
        let metadata = |name: &str, attempt: &str, kind: &str| {
            serde_json::to_vec(&json!([{
                "Name": name,
                "Config": {"Labels": {
                    "workstream.owner": "terminal-benchmark-checker-service-v1",
                    "workstream.request-digest": format!("sha256:{}", "1".repeat(64)),
                    "workstream.grant-id": "extract_0123456789abcdef0123456789abcdef",
                    "workstream.attempt": attempt,
                    "workstream.resource-kind": kind,
                }}
            }]))
            .unwrap()
        };

        assert!(owned_container(&metadata(
            "/ws-terminal-builder-a1",
            "a1",
            "builder"
        )));
        assert!(!owned_container(&metadata(
            "/ws-terminal-builder-a1",
            "b2",
            "builder"
        )));
        assert!(!owned_container(&metadata(
            "/foreign-ws-terminal-builder-a1",
            "a1",
            "builder"
        )));
        for iteration in 0..3 {
            assert!(owned_container(&metadata(
                &format!("/ws-terminal-reference-a1-{iteration}"),
                "a1",
                "reference"
            )));
        }
        assert!(!owned_container(&metadata(
            "/ws-terminal-reference-a1-3",
            "a1",
            "reference"
        )));
    }

    #[test]
    fn startup_recovery_removes_only_labeled_and_prefixed_resources() {
        let root = temporary_directory("recovery");
        fs::create_dir(&root).unwrap();
        let container = root.join("container");
        let image = root.join("image");
        let control = root.join("unowned-control");
        fs::write(&container, b"owned").unwrap();
        fs::write(&image, b"owned").unwrap();
        fs::write(&control, b"preserved").unwrap();
        let docker = root.join("docker");
        let script = format!(
            r#"#!/bin/sh
case "$1 $2" in
  "ps -aq") test -e "{container}" && printf '{container_id}\n'; exit 0;;
  "container inspect")
    test -e "{container}" || exit 1
    printf '%s\n' '[{{"Name":"/ws-terminal-builder-a1","Config":{{"Labels":{{"workstream.owner":"terminal-benchmark-checker-service-v1","workstream.request-digest":"sha256:{digest}","workstream.grant-id":"extract_0123456789abcdef0123456789abcdef","workstream.attempt":"a1","workstream.resource-kind":"builder"}}}}}}]'
    exit 0;;
  "rm -f") rm -f "{container}"; exit 0;;
  "container ls") test -e "{container}" && printf '{container_id}\n'; exit 0;;
  "image ls") test -e "{image}" && printf 'workstream.local/terminal-benchmark-candidate a1 sha256:{image_id}\n'; exit 0;;
  "image inspect")
    test -e "{image}" || exit 1
    printf '%s\n' '[{{"Id":"sha256:{image_id}","RepoTags":["workstream.local/terminal-benchmark-candidate:a1"]}}]'
    exit 0;;
  "image rm") rm -f "{image}"; exit 0;;
esac
exit 2
"#,
            container = container.display(),
            container_id = "a".repeat(64),
            image = image.display(),
            image_id = "b".repeat(64),
            digest = "1".repeat(64),
        );
        fs::write(&docker, script).unwrap();
        fs::set_permissions(&docker, fs::Permissions::from_mode(0o700)).unwrap();
        let profile = TerminalBenchmarkProfile {
            profile_version: PROFILE_VERSION.into(),
            registry_entry_id: "019a0000-0000-7000-8000-000000000001".into(),
            registry_entry_digest: format!("sha256:{}", "1".repeat(64)),
            checker_image_digest: format!("sha256:{}", "2".repeat(64)),
            builder: image_entry(),
            approved_base: image_entry(),
            sealed_cache: empty_cache(),
            temporary_repository: TEMPORARY_REPOSITORY.into(),
        };
        let config = ServiceConfig {
            socket_path: root.join("checker.sock"),
            material_root: root.clone(),
            docker_binary: docker,
            runtime: "runc".into(),
            isolation_mode: "docker-dev".into(),
            operating_system: "linux".into(),
            architecture: "amd64".into(),
            sandbox_uid: 65532,
            sandbox_gid: 65532,
            cache: vec![image_entry()],
            terminal_benchmark: None,
        };
        cleanup_stale_resources(&config, &profile).unwrap();
        assert!(!container.exists());
        assert!(!image.exists());
        assert_eq!(fs::read(&control).unwrap(), b"preserved");
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn ambiguous_startup_and_image_cleanup_preserve_resource_markers() {
        let root = temporary_directory("ambiguous-cleanup");
        fs::create_dir(&root).unwrap();
        let container = root.join("container");
        let image = root.join("image");
        fs::write(&container, b"live").unwrap();
        fs::write(&image, b"live").unwrap();
        let docker = root.join("docker");
        fs::write(
            &docker,
            b"#!/bin/sh\ncase \"$1 $2\" in\n  \"rm -f\"|\"container ls\"|\"image rm\"|\"image ls\") exit 125;;\nesac\nexit 2\n",
        )
        .unwrap();
        fs::set_permissions(&docker, fs::Permissions::from_mode(0o700)).unwrap();
        let config = test_service_config(&root, docker);
        let deadline = Instant::now() + Duration::from_secs(2);
        let container_id = "a".repeat(64);
        let tag = "workstream.local/terminal-benchmark-candidate:a1";

        assert!(!remove_container_until(&config, &container_id, deadline));
        assert!(container.exists());
        assert!(!remove_image_until(&config, tag, deadline));
        assert!(image.exists());
        let mut cleanup = EmergencyCleanupBudget::new();
        assert!(!remove_image_cleanup(&config, tag, &mut cleanup));
        assert!(image.exists());
        fs::remove_dir_all(root).unwrap();
    }

    fn make_tree_writable(path: &Path) {
        if let Ok(entries) = fs::read_dir(path) {
            for entry in entries.flatten() {
                if entry.path().is_dir() {
                    make_tree_writable(&entry.path());
                }
            }
        }
        if path.is_dir() {
            fs::set_permissions(path, fs::Permissions::from_mode(0o700)).unwrap();
        }
    }

    fn temporary_directory(suffix: &str) -> PathBuf {
        std::env::temp_dir().join(format!(
            "ws-terminal-{suffix}-{}",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ))
    }

    fn cache_snapshot(root: &Path) -> SealedCache {
        let metadata = fs::metadata(root).unwrap();
        let directory = File::open(root).unwrap();
        let mut entries = Vec::new();
        walk_cache(
            &directory,
            Path::new(""),
            metadata.uid(),
            metadata.gid(),
            &mut entries,
        )
        .unwrap();
        entries.sort_by(|left, right| left.path.cmp(&right.path));
        SealedCache {
            root: fs::canonicalize(root).unwrap(),
            uid: metadata.uid(),
            gid: metadata.gid(),
            mode: metadata.mode() & 0o777,
            total_count: entries.len() as u64,
            total_bytes: entries.iter().map(|entry| entry.byte_count).sum(),
            inventory_digest: canonical_hash(&serde_json::to_value(&entries).unwrap()).unwrap(),
            entries,
        }
    }

    fn image_entry() -> CacheEntry {
        CacheEntry {
            repository: "example/image".into(),
            platform_manifest_digest: format!("sha256:{}", "3".repeat(64)),
            platform_manifest_media_type: "application/vnd.oci.image.manifest.v1+json".into(),
            platform_manifest_byte_count: 1,
            operating_system: "linux".into(),
            architecture: "amd64".into(),
            config_image_id: format!("sha256:{}", "4".repeat(64)),
        }
    }

    fn test_profile() -> TerminalBenchmarkProfile {
        TerminalBenchmarkProfile {
            profile_version: PROFILE_VERSION.into(),
            registry_entry_id: "019a0000-0000-7000-8000-000000000001".into(),
            registry_entry_digest: format!("sha256:{}", "1".repeat(64)),
            checker_image_digest: format!("sha256:{}", "2".repeat(64)),
            builder: image_entry(),
            approved_base: image_entry(),
            sealed_cache: empty_cache(),
            temporary_repository: TEMPORARY_REPOSITORY.into(),
        }
    }

    fn test_service_config(root: &Path, docker_binary: PathBuf) -> ServiceConfig {
        ServiceConfig {
            socket_path: root.join("checker.sock"),
            material_root: root.to_path_buf(),
            docker_binary,
            runtime: "runc".into(),
            isolation_mode: "docker-dev".into(),
            operating_system: "linux".into(),
            architecture: "amd64".into(),
            sandbox_uid: 65532,
            sandbox_gid: 65532,
            cache: vec![image_entry()],
            terminal_benchmark: None,
        }
    }

    fn test_grant(root: &Path) -> VerifiedGrant {
        VerifiedGrant {
            grant_id: "extract_0123456789abcdef0123456789abcdef".into(),
            root: root.to_path_buf(),
            workspace: root.join("workspace"),
            files: Vec::new(),
            runtime: None,
            binding_digest: format!("sha256:{}", "1".repeat(64)),
        }
    }

    fn empty_cache() -> SealedCache {
        SealedCache {
            root: PathBuf::from("/tmp/cache"),
            uid: 1,
            gid: 1,
            mode: 0o555,
            entries: Vec::new(),
            total_count: 0,
            total_bytes: 0,
            inventory_digest: canonical_hash(&json!([])).unwrap(),
        }
    }

    fn request(phase: &str) -> ValidatedRequest {
        ValidatedRequest {
            value: json!({"configuration":{"schema_version":"terminal_benchmark_project.v1","external_task_id":"terminal-ledger-reconcile"}}),
            request_digest: format!("sha256:{}", "0".repeat(64)),
            registry_entry_id: "019a0000-0000-7000-8000-000000000001".into(),
            registry_entry_digest: format!("sha256:{}", "1".repeat(64)),
            image_digest: format!("sha256:{}", "2".repeat(64)),
            configuration_digest: format!("sha256:{}", "5".repeat(64)),
            phase: phase.into(),
            cpu_millis: 1000,
            memory_bytes: 256 * 1024 * 1024,
            deadline_ms: 1000,
            maximum_output_bytes: 65536,
        }
    }
}
