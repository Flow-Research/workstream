//! Trusted long-lived Unix-socket boundary for digest-pinned checker containers.

use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::os::fd::AsRawFd;
use std::os::unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt};
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::{Component, Path, PathBuf};
use std::process::{Child, Command, ExitStatus, Stdio};
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};
use workstream_checker_sdk::{
    canonical_hash, infrastructure_result, parse_request, validate_result, ValidatedRequest,
    MAX_REQUEST_BYTES, MAX_RESULT_BYTES,
};

const PROTOCOL: &str = "external_checker_service.v1";
const GRANT_PROTOCOL: &str = "workstream.external_checker_material_grant.v1";
const MAX_ENVELOPE_BYTES: usize = MAX_REQUEST_BYTES + 16_384;
const MAX_RESPONSE_BYTES: usize = 65_536 + 16_384;
const SOCKET_IO_TIMEOUT: Duration = Duration::from_secs(2);
const DOCKER_CONTROL_TIMEOUT: Duration = Duration::from_secs(10);
const CLEANUP_TIMEOUT: Duration = Duration::from_secs(10);

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ServiceConfig {
    socket_path: PathBuf,
    material_root: PathBuf,
    docker_binary: PathBuf,
    runtime: String,
    isolation_mode: String,
    operating_system: String,
    architecture: String,
    sandbox_uid: u32,
    sandbox_gid: u32,
    cache: Vec<CacheEntry>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
struct CacheEntry {
    repository: String,
    platform_manifest_digest: String,
    platform_manifest_media_type: String,
    platform_manifest_byte_count: u64,
    operating_system: String,
    architecture: String,
    config_image_id: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ExecuteEnvelope {
    protocol_version: String,
    operation: String,
    request: Value,
    grant: GrantReference,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct HealthEnvelope {
    protocol_version: String,
    operation: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct GrantReference {
    grant_id: String,
    binding_digest: String,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct GrantManifest {
    protocol_version: String,
    grant_id: String,
    request_digest: String,
    prepared_generation_id: String,
    attempt_id: String,
    attempt_request_digest: String,
    archive_sha256: String,
    archive_byte_count: u64,
    semantic_manifest_sha256: String,
    directories: Vec<String>,
    files: Vec<GrantFile>,
    binding_digest: String,
}

#[derive(Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct GrantFile {
    normalized_path: String,
    byte_count: u64,
    sha256: String,
    executable: bool,
}

#[derive(Debug, Serialize)]
struct IsolationReceipt<'a> {
    repository: &'a str,
    platform_manifest_digest: &'a str,
    platform_manifest_media_type: &'a str,
    platform_manifest_byte_count: u64,
    operating_system: &'a str,
    architecture: &'a str,
    config_image_id: &'a str,
    runtime: &'a str,
    isolation_mode: &'a str,
    sandbox_uid: u32,
    sandbox_gid: u32,
}

#[derive(Debug, Serialize)]
struct HealthReceipt<'a> {
    protocol_version: &'static str,
    operation: &'static str,
    status: &'static str,
    operating_system: &'a str,
    architecture: &'a str,
    runtime: &'a str,
    isolation_mode: &'a str,
    cached_platform_manifests: usize,
    sandbox_uid: u32,
    sandbox_gid: u32,
}

#[derive(Debug, PartialEq, Eq)]
struct WorkspaceInventory {
    directories: Vec<String>,
    files: Vec<GrantFile>,
}

struct BoundedCommandOutput {
    status: ExitStatus,
    stdout: Vec<u8>,
    _stderr: Vec<u8>,
}

fn main() {
    if let Err(error) = run() {
        eprintln!("external checker service unavailable: {error}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), String> {
    let path = std::env::args_os()
        .nth(1)
        .ok_or("configuration path missing")?;
    let bytes = fs::read(path).map_err(|_| "configuration unavailable")?;
    let config: ServiceConfig =
        serde_json::from_slice(&bytes).map_err(|_| "configuration invalid")?;
    validate_config(&config)?;
    if config.socket_path.exists() {
        return Err("socket path already exists".into());
    }
    let listener = UnixListener::bind(&config.socket_path).map_err(|_| "socket bind failed")?;
    fs::set_permissions(&config.socket_path, fs::Permissions::from_mode(0o600))
        .map_err(|_| "socket permission failed")?;
    for connection in listener.incoming() {
        match connection {
            Ok(stream) => serve_connection(&config, stream, SOCKET_IO_TIMEOUT),
            Err(_) => continue,
        }
    }
    Ok(())
}

fn serve_connection(config: &ServiceConfig, mut stream: UnixStream, timeout: Duration) {
    if stream.set_nonblocking(true).is_err() {
        return;
    }
    let response = read_frame_until(&mut stream, MAX_ENVELOPE_BYTES, Instant::now() + timeout)
        .and_then(|bytes| handle_frame(config, &stream, &bytes));
    if let Ok(bytes) = response {
        let _ = write_frame_until(&mut stream, &bytes, Instant::now() + timeout);
    }
}

fn validate_config(config: &ServiceConfig) -> Result<(), String> {
    if !config.socket_path.is_absolute()
        || !config.material_root.is_absolute()
        || !config.docker_binary.is_absolute()
        || !matches!(config.isolation_mode.as_str(), "gvisor" | "docker-dev")
        || !matches!(config.runtime.as_str(), "runsc" | "runc")
        || (config.isolation_mode == "gvisor") != (config.runtime == "runsc")
        || config.operating_system.is_empty()
        || config.architecture.is_empty()
        || config.sandbox_uid == 0
        || config.sandbox_gid == 0
        || config.cache.is_empty()
    {
        return Err("configuration values invalid".into());
    }
    let metadata =
        fs::symlink_metadata(&config.material_root).map_err(|_| "material root missing")?;
    if !metadata.file_type().is_dir()
        || metadata.file_type().is_symlink()
        || metadata.mode() & 0o777 != 0o700
    {
        return Err("material root is not private".into());
    }
    let canonical = fs::canonicalize(&config.material_root).map_err(|_| "material root invalid")?;
    if canonical != config.material_root {
        return Err("material root is not canonical".into());
    }
    let socket_parent = config.socket_path.parent().ok_or("socket parent missing")?;
    let socket_parent_metadata =
        fs::symlink_metadata(socket_parent).map_err(|_| "socket parent missing")?;
    if !socket_parent_metadata.file_type().is_dir()
        || socket_parent_metadata.file_type().is_symlink()
        || socket_parent_metadata.mode() & 0o777 != 0o700
        || fs::canonicalize(socket_parent).map_err(|_| "socket parent invalid")? != socket_parent
    {
        return Err("socket parent is not private".into());
    }
    let docker =
        fs::symlink_metadata(&config.docker_binary).map_err(|_| "docker binary missing")?;
    if !docker.file_type().is_file()
        || docker.file_type().is_symlink()
        || docker.mode() & 0o111 == 0
        || fs::canonicalize(&config.docker_binary).map_err(|_| "docker binary invalid")?
            != config.docker_binary
    {
        return Err("docker binary invalid".into());
    }
    let mut identities = std::collections::BTreeSet::new();
    let mut manifests = std::collections::BTreeSet::new();
    for entry in &config.cache {
        if !valid_repository(&entry.repository)
            || !valid_digest(&entry.platform_manifest_digest)
            || !valid_digest(&entry.config_image_id)
            || !matches!(
                entry.platform_manifest_media_type.as_str(),
                "application/vnd.oci.image.manifest.v1+json"
                    | "application/vnd.docker.distribution.manifest.v2+json"
            )
            || entry.platform_manifest_byte_count == 0
            || entry.platform_manifest_byte_count > 10 * 1024 * 1024
            || entry.operating_system != config.operating_system
            || entry.architecture != config.architecture
            || !identities.insert((
                entry.repository.clone(),
                entry.platform_manifest_digest.clone(),
            ))
            || !manifests.insert(entry.platform_manifest_digest.clone())
        {
            return Err("cache identity invalid".into());
        }
    }
    runtime_ready(config)
}

fn handle(config: &ServiceConfig, stream: &mut UnixStream) -> Result<Vec<u8>, String> {
    let bytes = read_frame(stream, MAX_ENVELOPE_BYTES)?;
    handle_frame(config, stream, &bytes)
}

fn handle_frame(
    config: &ServiceConfig,
    stream: &UnixStream,
    bytes: &[u8],
) -> Result<Vec<u8>, String> {
    let value: Value = serde_json::from_slice(&bytes).map_err(|_| "request envelope invalid")?;
    if value.get("operation").and_then(Value::as_str) == Some("health") {
        let envelope: HealthEnvelope =
            serde_json::from_value(value).map_err(|_| "health envelope invalid")?;
        if envelope.protocol_version != PROTOCOL || envelope.operation != "health" {
            return Err("request operation invalid".into());
        }
        runtime_ready(config)?;
        return serde_json::to_vec(&HealthReceipt {
            protocol_version: PROTOCOL,
            operation: "health",
            status: "ready",
            operating_system: &config.operating_system,
            architecture: &config.architecture,
            runtime: &config.runtime,
            isolation_mode: &config.isolation_mode,
            cached_platform_manifests: config.cache.len(),
            sandbox_uid: config.sandbox_uid,
            sandbox_gid: config.sandbox_gid,
        })
        .map_err(|_| "health encoding failed".into());
    }
    let envelope: ExecuteEnvelope =
        serde_json::from_value(value).map_err(|_| "request envelope invalid")?;
    if envelope.protocol_version != PROTOCOL || envelope.operation != "execute" {
        return Err("request operation invalid".into());
    }
    let request_bytes = serde_json::to_vec(&envelope.request).map_err(|_| "request invalid")?;
    let request = parse_request(&request_bytes).map_err(|_| "request contract invalid")?;
    let Some(cache) = config
        .cache
        .iter()
        .find(|entry| entry.platform_manifest_digest == request.image_digest)
    else {
        let result = infrastructure_result(&request, "implementation_unavailable")
            .map_err(|_| "result construction failed")?;
        return encode_response(result, None);
    };
    let isolation = IsolationReceipt {
        repository: &cache.repository,
        platform_manifest_digest: &cache.platform_manifest_digest,
        platform_manifest_media_type: &cache.platform_manifest_media_type,
        platform_manifest_byte_count: cache.platform_manifest_byte_count,
        operating_system: &cache.operating_system,
        architecture: &cache.architecture,
        config_image_id: &cache.config_image_id,
        runtime: &config.runtime,
        isolation_mode: &config.isolation_mode,
        sandbox_uid: config.sandbox_uid,
        sandbox_gid: config.sandbox_gid,
    };
    let execution_deadline = Instant::now() + Duration::from_millis(request.deadline_ms);
    let (result, isolation) = match verify_grant(config, &request, &envelope.grant) {
        Ok(workspace) => match inspect_image(config, cache, execution_deadline) {
            Ok(()) => match execute_container(
                config,
                cache,
                &request,
                &workspace,
                stream,
                execution_deadline,
            ) {
                Ok(result) => (result, Some(isolation)),
                Err((code, launched)) => (
                    infrastructure_result(&request, code)
                        .map_err(|_| "result construction failed")?,
                    launched.then_some(isolation),
                ),
            },
            Err(_) => (
                infrastructure_result(&request, "implementation_unavailable")
                    .map_err(|_| "result construction failed")?,
                None,
            ),
        },
        Err(_) => (
            infrastructure_result(&request, "material_unavailable")
                .map_err(|_| "result construction failed")?,
            None,
        ),
    };
    validate_result(&result, &request).map_err(|_| "result contract invalid")?;
    encode_response(result, isolation)
}

fn runtime_ready(config: &ServiceConfig) -> Result<(), String> {
    let status = run_bounded_command(
        &config.docker_binary,
        &["info", "--format", "{{json .Runtimes}}"],
        Instant::now() + DOCKER_CONTROL_TIMEOUT,
        64 * 1024,
    )
    .map_err(|_| "runtime health unavailable")?;
    let runtimes: Value =
        serde_json::from_slice(&status.stdout).map_err(|_| "runtime health invalid")?;
    if !status.status.success()
        || !runtimes.is_object()
        || (config.isolation_mode == "gvisor" && runtimes.get("runsc").is_none())
    {
        return Err("configured runtime unavailable".into());
    }
    Ok(())
}

fn set_nonblocking<T: AsRawFd>(value: &T) -> Result<(), String> {
    let descriptor = value.as_raw_fd();
    // SAFETY: fcntl only reads and replaces status flags on this owned descriptor.
    let flags = unsafe { libc::fcntl(descriptor, libc::F_GETFL) };
    if flags < 0 || unsafe { libc::fcntl(descriptor, libc::F_SETFL, flags | libc::O_NONBLOCK) } < 0
    {
        return Err("process descriptor unavailable".into());
    }
    Ok(())
}

fn read_available<R: Read>(
    reader: &mut R,
    bytes: &mut Vec<u8>,
    maximum: usize,
) -> Result<bool, String> {
    let mut buffer = [0_u8; 8 * 1024];
    loop {
        match reader.read(&mut buffer) {
            Ok(0) => return Ok(true),
            Ok(count) => {
                if bytes.len().saturating_add(count) > maximum {
                    return Err("process output unbounded".into());
                }
                bytes.extend_from_slice(&buffer[..count]);
            }
            Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => return Ok(false),
            Err(_) => return Err("process output unavailable".into()),
        }
    }
}

fn reap_child(child: &mut Child, deadline: Instant) -> Result<ExitStatus, String> {
    loop {
        if let Some(status) = child.try_wait().map_err(|_| "process wait failed")? {
            return Ok(status);
        }
        if Instant::now() >= deadline {
            return Err("process wait timed out".into());
        }
        thread::sleep(Duration::from_millis(5));
    }
}

fn stop_child(child: &mut Child, deadline: Instant) -> Result<ExitStatus, String> {
    if let Some(status) = child.try_wait().map_err(|_| "process wait failed")? {
        return Ok(status);
    }
    if child.kill().is_err() {
        return reap_child(child, deadline);
    }
    reap_child(child, deadline)
}

fn run_bounded_command(
    binary: &Path,
    arguments: &[&str],
    deadline: Instant,
    maximum_output: usize,
) -> Result<BoundedCommandOutput, String> {
    if Instant::now() >= deadline {
        return Err("process deadline exceeded".into());
    }
    let mut child = Command::new(binary)
        .args(arguments)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|_| "process launch failed")?;
    let mut stdout = match child.stdout.take() {
        Some(stdout) => stdout,
        None => {
            let _ = stop_child(&mut child, Instant::now() + CLEANUP_TIMEOUT);
            return Err("process stdout unavailable".into());
        }
    };
    let mut stderr = match child.stderr.take() {
        Some(stderr) => stderr,
        None => {
            let _ = stop_child(&mut child, Instant::now() + CLEANUP_TIMEOUT);
            return Err("process stderr unavailable".into());
        }
    };
    if set_nonblocking(&stdout).is_err() || set_nonblocking(&stderr).is_err() {
        let _ = stop_child(&mut child, Instant::now() + CLEANUP_TIMEOUT);
        return Err("process descriptor unavailable".into());
    }
    let mut stdout_bytes = Vec::new();
    let mut stderr_bytes = Vec::new();
    loop {
        if read_available(&mut stdout, &mut stdout_bytes, maximum_output).is_err()
            || read_available(&mut stderr, &mut stderr_bytes, maximum_output).is_err()
        {
            let _ = stop_child(&mut child, Instant::now() + CLEANUP_TIMEOUT);
            return Err("process output unbounded".into());
        }
        let status = match child.try_wait() {
            Ok(status) => status,
            Err(_) => {
                let _ = stop_child(&mut child, Instant::now() + CLEANUP_TIMEOUT);
                return Err("process wait failed".into());
            }
        };
        if let Some(status) = status {
            read_available(&mut stdout, &mut stdout_bytes, maximum_output)?;
            read_available(&mut stderr, &mut stderr_bytes, maximum_output)?;
            return Ok(BoundedCommandOutput {
                status,
                stdout: stdout_bytes,
                _stderr: stderr_bytes,
            });
        }
        if Instant::now() >= deadline {
            stop_child(&mut child, Instant::now() + CLEANUP_TIMEOUT)?;
            return Err("process deadline exceeded".into());
        }
        thread::sleep(Duration::from_millis(5));
    }
}

fn encode_response(
    result: Value,
    isolation: Option<IsolationReceipt<'_>>,
) -> Result<Vec<u8>, String> {
    let response =
        serde_json::json!({"protocol_version": PROTOCOL, "result": result, "isolation": isolation});
    let bytes = serde_json::to_vec(&response).map_err(|_| "response encoding failed")?;
    if bytes.len() > MAX_RESPONSE_BYTES {
        return Err("response is unbounded".into());
    }
    Ok(bytes)
}

fn verify_grant(
    config: &ServiceConfig,
    request: &ValidatedRequest,
    reference: &GrantReference,
) -> Result<PathBuf, String> {
    if !valid_grant_id(&reference.grant_id) || !valid_digest(&reference.binding_digest) {
        return Err("grant reference invalid".into());
    }
    let grant_root = config
        .material_root
        .join("workspaces")
        .join(&reference.grant_id);
    if grant_root
        .components()
        .any(|item| matches!(item, Component::ParentDir))
    {
        return Err("grant path invalid".into());
    }
    let canonical_root = fs::canonicalize(&grant_root).map_err(|_| "grant missing")?;
    if canonical_root != grant_root
        || canonical_root.parent() != Some(&config.material_root.join("workspaces"))
    {
        return Err("grant root differs".into());
    }
    let grant_metadata = fs::symlink_metadata(&grant_root).map_err(|_| "grant missing")?;
    if !grant_metadata.file_type().is_dir()
        || grant_metadata.file_type().is_symlink()
        || grant_metadata.mode() & 0o777 != 0o700
        || grant_metadata.uid() != config.sandbox_uid
        || grant_metadata.gid() != config.sandbox_gid
    {
        return Err("grant root identity differs".into());
    }
    let raw = read_grant_manifest(
        &grant_root.join(".external-checker-grant.json"),
        config.sandbox_uid,
        config.sandbox_gid,
    )?;
    if raw.contains(&0) {
        return Err("grant manifest invalid".into());
    }
    let manifest: GrantManifest =
        serde_json::from_slice(&raw).map_err(|_| "grant manifest invalid")?;
    let value: Value = serde_json::from_slice(&raw).map_err(|_| "grant manifest invalid")?;
    let mut body = value.as_object().cloned().ok_or("grant manifest invalid")?;
    body.remove("binding_digest");
    let binding = canonical_hash(&Value::Object(body)).map_err(|_| "grant binding invalid")?;
    if manifest.protocol_version != GRANT_PROTOCOL
        || manifest.grant_id != reference.grant_id
        || manifest.request_digest != request.request_digest
        || manifest.binding_digest != binding
        || manifest.binding_digest != reference.binding_digest
        || !grant_matches_request(&manifest, request)
    {
        return Err("grant binding differs".into());
    }
    let workspace = grant_root.join("workspace");
    let observed = inspect_workspace(&workspace, config.sandbox_uid, config.sandbox_gid)?;
    if observed.files != manifest.files || observed.directories != manifest.directories {
        return Err("grant material differs".into());
    }
    Ok(workspace)
}

fn grant_matches_request(manifest: &GrantManifest, request: &ValidatedRequest) -> bool {
    if request.phase != "pre_submit" {
        return false;
    }
    let Some(identity) = request.value.get("identity").and_then(Value::as_object) else {
        return false;
    };
    let Some(materials) = request.value.get("materials").and_then(Value::as_array) else {
        return false;
    };
    let Some(archive) = materials.iter().find_map(|item| {
        let object = item.as_object()?;
        (object.get("role")?.as_str()? == "submission_archive").then_some(object)
    }) else {
        return false;
    };
    let semantic_manifest_sha256 = semantic_manifest_hash(manifest).ok();
    identity
        .get("prepared_generation_id")
        .and_then(Value::as_str)
        == Some(&manifest.prepared_generation_id)
        && identity.get("attempt_id").and_then(Value::as_str) == Some(&manifest.attempt_id)
        && identity
            .get("attempt_request_digest")
            .and_then(Value::as_str)
            == Some(&manifest.attempt_request_digest)
        && archive.get("sha256").and_then(Value::as_str) == Some(&manifest.archive_sha256)
        && archive.get("byte_count").and_then(Value::as_u64) == Some(manifest.archive_byte_count)
        && semantic_manifest_sha256.as_deref() == Some(&manifest.semantic_manifest_sha256)
}

fn semantic_manifest_hash(manifest: &GrantManifest) -> Result<String, String> {
    let mut entries = Vec::with_capacity(manifest.directories.len() + manifest.files.len());
    for path in &manifest.directories {
        entries.push(serde_json::json!({
            "normalized_path": path,
            "entry_type": "directory",
        }));
    }
    for file in &manifest.files {
        entries.push(serde_json::json!({
            "normalized_path": file.normalized_path,
            "entry_type": "file",
            "sha256": file.sha256,
            "byte_count": file.byte_count,
            "executable": file.executable,
        }));
    }
    entries.sort_by(|left, right| {
        left["normalized_path"]
            .as_str()
            .cmp(&right["normalized_path"].as_str())
    });
    canonical_hash(&serde_json::json!({
        "schema_version": "workstream.submission_bundle_manifest.v1",
        "entries": entries,
    }))
    .map_err(|_| "semantic manifest invalid".into())
}

fn read_grant_manifest(
    path: &Path,
    expected_uid: u32,
    expected_gid: u32,
) -> Result<Vec<u8>, String> {
    const MAXIMUM: u64 = 2 * 1024 * 1024;
    let before = fs::symlink_metadata(path).map_err(|_| "grant manifest missing")?;
    if !before.file_type().is_file()
        || before.file_type().is_symlink()
        || before.mode() & 0o777 != 0o400
        || before.uid() != expected_uid
        || before.gid() != expected_gid
        || before.len() > MAXIMUM
    {
        return Err("grant manifest identity differs".into());
    }
    let file = File::open(path).map_err(|_| "grant manifest unavailable")?;
    let opened = file.metadata().map_err(|_| "grant manifest unavailable")?;
    if (
        opened.dev(),
        opened.ino(),
        opened.mode(),
        opened.uid(),
        opened.gid(),
    ) != (
        before.dev(),
        before.ino(),
        before.mode(),
        before.uid(),
        before.gid(),
    ) {
        return Err("grant manifest changed".into());
    }
    let mut raw = Vec::new();
    file.take(MAXIMUM + 1)
        .read_to_end(&mut raw)
        .map_err(|_| "grant manifest unavailable")?;
    if raw.len() as u64 > MAXIMUM {
        return Err("grant manifest unbounded".into());
    }
    Ok(raw)
}

fn inspect_workspace(
    root: &Path,
    expected_uid: u32,
    expected_gid: u32,
) -> Result<WorkspaceInventory, String> {
    let canonical = fs::canonicalize(root).map_err(|_| "workspace missing")?;
    if canonical != root {
        return Err("workspace path differs".into());
    }
    let metadata = fs::symlink_metadata(root).map_err(|_| "workspace missing")?;
    if !metadata.file_type().is_dir()
        || metadata.file_type().is_symlink()
        || metadata.mode() & 0o777 != 0o500
        || metadata.uid() != expected_uid
        || metadata.gid() != expected_gid
    {
        return Err("workspace mode invalid".into());
    }
    let mut files = Vec::new();
    let mut directories = Vec::new();
    inspect_directory(
        root,
        Path::new(""),
        &mut files,
        &mut directories,
        expected_uid,
        expected_gid,
    )?;
    files.sort_by(|left, right| left.normalized_path.cmp(&right.normalized_path));
    directories.sort();
    Ok(WorkspaceInventory { directories, files })
}

fn inspect_directory(
    root: &Path,
    relative: &Path,
    files: &mut Vec<GrantFile>,
    directories: &mut Vec<String>,
    expected_uid: u32,
    expected_gid: u32,
) -> Result<(), String> {
    let directory = root.join(relative);
    for entry in fs::read_dir(&directory).map_err(|_| "workspace read failed")? {
        let entry = entry.map_err(|_| "workspace read failed")?;
        let name = entry.file_name();
        let next = relative.join(&name);
        let path = entry.path();
        let metadata = fs::symlink_metadata(&path).map_err(|_| "workspace entry missing")?;
        if metadata.uid() != expected_uid || metadata.gid() != expected_gid {
            return Err("workspace owner differs".into());
        }
        if metadata.file_type().is_symlink() {
            return Err("workspace symlink rejected".into());
        }
        if metadata.file_type().is_dir() {
            if metadata.mode() & 0o777 != 0o500 {
                return Err("workspace directory mode invalid".into());
            }
            directories.push(
                next.to_str()
                    .ok_or("workspace path invalid")?
                    .replace('\\', "/"),
            );
            inspect_directory(root, &next, files, directories, expected_uid, expected_gid)?;
        } else if metadata.file_type().is_file() {
            let mode = metadata.mode() & 0o777;
            if !matches!(mode, 0o400 | 0o500) {
                return Err("workspace file mode invalid".into());
            }
            let mut file = File::open(&path).map_err(|_| "workspace file unavailable")?;
            let mut digest = Sha256::new();
            let count =
                std::io::copy(&mut file, &mut digest).map_err(|_| "workspace file read failed")?;
            files.push(GrantFile {
                normalized_path: next
                    .to_str()
                    .ok_or("workspace path invalid")?
                    .replace('\\', "/"),
                byte_count: count,
                sha256: format!("sha256:{:x}", digest.finalize()),
                executable: mode == 0o500,
            });
        } else {
            return Err("workspace special file rejected".into());
        }
    }
    Ok(())
}

fn inspect_image(
    config: &ServiceConfig,
    cache: &CacheEntry,
    deadline: Instant,
) -> Result<(), String> {
    let reference = format!("{}@{}", cache.repository, cache.platform_manifest_digest);
    let output = run_bounded_command(
        &config.docker_binary,
        &["image", "inspect", "--format", "{{json .}}", &reference],
        deadline,
        2 * 1024 * 1024,
    )
    .map_err(|_| "image inspect unavailable")?;
    if !output.status.success() {
        return Err("image missing".into());
    }
    let value: Value =
        serde_json::from_slice(&output.stdout).map_err(|_| "image inspect invalid")?;
    let repo = value
        .get("RepoDigests")
        .and_then(Value::as_array)
        .ok_or("image digests missing")?;
    if value.get("Id").and_then(Value::as_str) != Some(&cache.config_image_id)
        || value.get("Os").and_then(Value::as_str) != Some(&cache.operating_system)
        || value.get("Architecture").and_then(Value::as_str) != Some(&cache.architecture)
        || !repo.iter().any(|item| item.as_str() == Some(&reference))
    {
        return Err("image identity differs".into());
    }
    Ok(())
}

fn execute_container(
    config: &ServiceConfig,
    cache: &CacheEntry,
    request: &ValidatedRequest,
    workspace: &Path,
    client: &UnixStream,
    deadline: Instant,
) -> Result<Value, (&'static str, bool)> {
    // Revalidate immediately before handing the path to Docker.
    inspect_workspace(workspace, config.sandbox_uid, config.sandbox_gid)
        .map_err(|_| ("material_unavailable", false))?;
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|_| ("implementation_unavailable", false))?
        .as_nanos();
    let name = format!("ws-checker-{nonce:x}");
    let image = format!("{}@{}", cache.repository, cache.platform_manifest_digest);
    let sandbox_user = format!("{}:{}", config.sandbox_uid, config.sandbox_gid);
    let cpus = format!("{:.3}", request.cpu_millis as f64 / 1000.0);
    let memory = request.memory_bytes.to_string();
    let pids = ((request.memory_bytes / (16 * 1024 * 1024)).clamp(16, 256)).to_string();
    let mount = format!(
        "type=bind,src={},dst=/work/input,readonly",
        workspace.display()
    );
    let create_arguments = [
        "create",
        "--name",
        &name,
        "--label",
        "workstream.external-checker=true",
        "--runtime",
        &config.runtime,
        "--network",
        "none",
        "--read-only",
        "--user",
        &sandbox_user,
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        &pids,
        "--memory",
        &memory,
        "--cpus",
        &cpus,
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,nodev,size=16777216",
        "--mount",
        &mount,
        "-i",
        &image,
    ];
    let created = match run_bounded_command(
        &config.docker_binary,
        &create_arguments,
        deadline,
        64 * 1024,
    ) {
        Ok(output) => output,
        Err(error) => {
            if !remove_container(config, &name) {
                return Err(("implementation_unavailable", false));
            }
            return Err((
                if error == "process deadline exceeded" {
                    "deadline_exceeded"
                } else {
                    "implementation_unavailable"
                },
                false,
            ));
        }
    };
    if !created.status.success() {
        if !remove_container(config, &name) {
            return Err(("implementation_unavailable", false));
        }
        return Err(("implementation_unavailable", false));
    }
    let result = run_started_container(config, &name, request, client, deadline);
    if !remove_container(config, &name) {
        return Err(("implementation_unavailable", true));
    }
    result.map_err(|code| (code, true))
}

fn remove_container(config: &ServiceConfig, name: &str) -> bool {
    let cleanup_deadline = Instant::now() + CLEANUP_TIMEOUT;
    if run_bounded_command(
        &config.docker_binary,
        &["rm", "-f", name],
        cleanup_deadline,
        64 * 1024,
    )
    .is_err()
    {
        return false;
    }
    matches!(
        run_bounded_command(
            &config.docker_binary,
            &["container", "inspect", name],
            cleanup_deadline,
            64 * 1024,
        ),
        Ok(output) if !output.status.success()
    )
}

fn run_started_container(
    config: &ServiceConfig,
    name: &str,
    request: &ValidatedRequest,
    client: &UnixStream,
    deadline: Instant,
) -> Result<Value, &'static str> {
    let payload = serde_json::to_vec(&request.value).map_err(|_| "invalid_output")?;
    let files = RuntimeFiles {
        output: config.material_root.join(format!(".{name}.stdout")),
        error: config.material_root.join(format!(".{name}.stderr")),
    };
    let output = OpenOptions::new()
        .create_new(true)
        .write(true)
        .mode(0o600)
        .open(&files.output)
        .map_err(|_| "implementation_unavailable")?;
    let error = OpenOptions::new()
        .create_new(true)
        .write(true)
        .mode(0o600)
        .open(&files.error)
        .map_err(|_| "implementation_unavailable")?;
    let mut child = Command::new(&config.docker_binary)
        .args(["start", "-a", "-i", name])
        .stdin(Stdio::piped())
        .stdout(output)
        .stderr(error)
        .spawn()
        .map_err(|_| "implementation_unavailable")?;
    let mut stdin = match child.stdin.take() {
        Some(stdin) => Some(stdin),
        None => {
            terminate_container(config, name, &mut child);
            return Err("implementation_unavailable");
        }
    };
    if set_nonblocking(stdin.as_ref().unwrap()).is_err() {
        terminate_container(config, name, &mut child);
        return Err("implementation_unavailable");
    }
    let mut written = 0;
    let status = loop {
        if Instant::now() >= deadline {
            terminate_container(config, name, &mut child);
            return Err("deadline_exceeded");
        }
        if !client_is_connected(client) {
            terminate_container(config, name, &mut child);
            return Err("implementation_unavailable");
        }
        if written < payload.len() {
            match stdin.as_mut().unwrap().write(&payload[written..]) {
                Ok(0) => {
                    terminate_container(config, name, &mut child);
                    return Err("implementation_unavailable");
                }
                Ok(count) => written += count,
                Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {}
                Err(_) => {
                    terminate_container(config, name, &mut child);
                    return Err("implementation_unavailable");
                }
            }
        }
        if written == payload.len() {
            stdin.take();
        }
        let status = match child.try_wait() {
            Ok(status) => status,
            Err(_) => {
                terminate_container(config, name, &mut child);
                return Err("implementation_unavailable");
            }
        };
        if let Some(status) = status {
            break status;
        }
        let sizes = fs::metadata(&files.output)
            .and_then(|output| fs::metadata(&files.error).map(|error| (output.len(), error.len())));
        let (output_size, error_size) = match sizes {
            Ok(sizes) => sizes,
            Err(_) => {
                terminate_container(config, name, &mut child);
                return Err("implementation_unavailable");
            }
        };
        if output_size > request.maximum_output_bytes as u64 || error_size > MAX_RESULT_BYTES as u64
        {
            terminate_container(config, name, &mut child);
            return Err("invalid_output");
        }
        thread::sleep(Duration::from_millis(10));
    };
    stdin.take();
    if written != payload.len() {
        return Err("invalid_output");
    }
    let bytes = read_bounded_file(&files.output, request.maximum_output_bytes)
        .map_err(|_| "invalid_output")?;
    read_bounded_file(&files.error, MAX_RESULT_BYTES).map_err(|_| "invalid_output")?;
    if !status.success() {
        return if container_was_oom_killed(config, name)? {
            Err("capacity_exceeded")
        } else {
            Err("invalid_output")
        };
    }
    if bytes.is_empty() || bytes.len() > request.maximum_output_bytes {
        return Err("invalid_output");
    }
    let result: Value = serde_json::from_slice(&bytes).map_err(|_| "invalid_output")?;
    validate_result(&result, request).map_err(|_| "invalid_output")?;
    Ok(result)
}

struct RuntimeFiles {
    output: PathBuf,
    error: PathBuf,
}

impl Drop for RuntimeFiles {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.output);
        let _ = fs::remove_file(&self.error);
    }
}

fn terminate_container(config: &ServiceConfig, name: &str, child: &mut std::process::Child) {
    let cleanup_deadline = Instant::now() + CLEANUP_TIMEOUT;
    let _ = run_bounded_command(
        &config.docker_binary,
        &["kill", name],
        cleanup_deadline,
        64 * 1024,
    );
    if reap_child(child, Instant::now() + Duration::from_secs(1)).is_err() {
        let _ = stop_child(child, cleanup_deadline);
    }
}

fn container_was_oom_killed(config: &ServiceConfig, name: &str) -> Result<bool, &'static str> {
    let output = run_bounded_command(
        &config.docker_binary,
        &["inspect", "--format", "{{json .State.OOMKilled}}", name],
        Instant::now() + DOCKER_CONTROL_TIMEOUT,
        16 * 1024,
    )
    .map_err(|_| "implementation_unavailable")?;
    if !output.status.success() {
        return Err("implementation_unavailable");
    }
    serde_json::from_slice(&output.stdout).map_err(|_| "implementation_unavailable")
}

fn read_bounded_file(path: &Path, maximum: usize) -> Result<Vec<u8>, String> {
    let file = File::open(path).map_err(|_| "process output unavailable")?;
    let mut bytes = Vec::new();
    file.take(maximum as u64 + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| "process output unavailable")?;
    if bytes.len() > maximum {
        return Err("process output unbounded".into());
    }
    Ok(bytes)
}

fn client_is_connected(stream: &UnixStream) -> bool {
    let mut byte = 0_u8;
    // SAFETY: recv peeks one byte into valid local storage without mutating the stream.
    let result = unsafe {
        libc::recv(
            stream.as_raw_fd(),
            (&mut byte as *mut u8).cast(),
            1,
            libc::MSG_PEEK | libc::MSG_DONTWAIT,
        )
    };
    if result >= 0 {
        false
    } else {
        let error = std::io::Error::last_os_error().raw_os_error();
        error == Some(libc::EAGAIN) || error == Some(libc::EWOULDBLOCK)
    }
}

fn read_frame(stream: &mut UnixStream, maximum: usize) -> Result<Vec<u8>, String> {
    let mut header = [0_u8; 4];
    stream
        .read_exact(&mut header)
        .map_err(|_| "request frame missing")?;
    let size = u32::from_be_bytes(header) as usize;
    if size == 0 || size > maximum {
        return Err("request frame unbounded".into());
    }
    let mut bytes = vec![0; size];
    stream
        .read_exact(&mut bytes)
        .map_err(|_| "request frame incomplete")?;
    Ok(bytes)
}

fn transfer_until(
    stream: &mut UnixStream,
    bytes: &mut [u8],
    deadline: Instant,
    mut operation: impl FnMut(&mut UnixStream, &mut [u8]) -> std::io::Result<usize>,
    incomplete: &'static str,
) -> Result<(), String> {
    let mut offset = 0;
    while offset < bytes.len() {
        if Instant::now() >= deadline {
            return Err(incomplete.into());
        }
        match operation(stream, &mut bytes[offset..]) {
            Ok(0) => return Err(incomplete.into()),
            Ok(count) => offset += count,
            Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                thread::sleep(Duration::from_millis(2));
            }
            Err(_) => return Err(incomplete.into()),
        }
    }
    Ok(())
}

fn read_frame_until(
    stream: &mut UnixStream,
    maximum: usize,
    deadline: Instant,
) -> Result<Vec<u8>, String> {
    let mut header = [0_u8; 4];
    transfer_until(
        stream,
        &mut header,
        deadline,
        |value, bytes| value.read(bytes),
        "request frame missing",
    )?;
    let size = u32::from_be_bytes(header) as usize;
    if size == 0 || size > maximum {
        return Err("request frame unbounded".into());
    }
    let mut bytes = vec![0; size];
    transfer_until(
        stream,
        &mut bytes,
        deadline,
        |value, bytes| value.read(bytes),
        "request frame incomplete",
    )?;
    Ok(bytes)
}

fn write_frame(stream: &mut UnixStream, bytes: &[u8]) -> Result<(), String> {
    if bytes.is_empty() || bytes.len() > MAX_RESPONSE_BYTES {
        return Err("response frame invalid".into());
    }
    stream
        .write_all(&(bytes.len() as u32).to_be_bytes())
        .map_err(|_| "response header failed")?;
    stream
        .write_all(bytes)
        .map_err(|_| "response body failed")?;
    Ok(())
}

fn write_frame_until(
    stream: &mut UnixStream,
    bytes: &[u8],
    deadline: Instant,
) -> Result<(), String> {
    if bytes.is_empty() || bytes.len() > MAX_RESPONSE_BYTES {
        return Err("response frame invalid".into());
    }
    let mut header = (bytes.len() as u32).to_be_bytes();
    transfer_until(
        stream,
        &mut header,
        deadline,
        |value, bytes| value.write(bytes),
        "response header failed",
    )?;
    let mut body = bytes.to_vec();
    transfer_until(
        stream,
        &mut body,
        deadline,
        |value, bytes| value.write(bytes),
        "response body failed",
    )
}

fn valid_grant_id(value: &str) -> bool {
    value.len() == 40
        && value.starts_with("extract_")
        && value[8..]
            .bytes()
            .all(|item| item.is_ascii_hexdigit() && !item.is_ascii_uppercase())
}

fn valid_digest(value: &str) -> bool {
    value.len() == 71
        && value.starts_with("sha256:")
        && value[7..]
            .bytes()
            .all(|item| item.is_ascii_hexdigit() && !item.is_ascii_uppercase())
}

fn valid_repository(value: &str) -> bool {
    if value.is_empty()
        || value.len() > 255
        || value.contains('@')
        || value.bytes().any(|item| {
            !(item.is_ascii_lowercase()
                || item.is_ascii_digit()
                || matches!(item, b'.' | b'_' | b'-' | b':' | b'/'))
        })
    {
        return false;
    }
    let components: Vec<_> = value.split('/').collect();
    if components.iter().any(|component| {
        component.is_empty()
            || !component.as_bytes()[0].is_ascii_alphanumeric()
            || !component.as_bytes()[component.len() - 1].is_ascii_alphanumeric()
    }) {
        return false;
    }
    let registry = components[0];
    let port_is_valid = registry.split_once(':').is_none_or(|(host, port)| {
        !host.contains(':') && !port.is_empty() && port.bytes().all(|item| item.is_ascii_digit())
    });
    port_is_valid
        && components
            .iter()
            .skip(1)
            .all(|component| !component.contains(':'))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::symlink;
    use std::os::unix::net::UnixStream;
    use std::time::Instant;

    fn test_config() -> (PathBuf, ServiceConfig) {
        let root = std::env::temp_dir().join(format!(
            "ws-pilot04-service-{}",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let material_root = root.join("material");
        let socket_root = root.join("socket");
        fs::create_dir_all(&material_root).unwrap();
        fs::create_dir_all(&socket_root).unwrap();
        fs::set_permissions(&material_root, fs::Permissions::from_mode(0o700)).unwrap();
        fs::set_permissions(&socket_root, fs::Permissions::from_mode(0o700)).unwrap();
        let docker = root.join("docker");
        fs::write(&docker, b"#!/bin/sh\nprintf '{\"runc\":{}}'\n").unwrap();
        fs::set_permissions(&docker, fs::Permissions::from_mode(0o700)).unwrap();
        let owner = fs::metadata(&material_root).unwrap();
        let sandbox_uid = owner.uid();
        let sandbox_gid = owner.gid();
        let config = ServiceConfig {
            socket_path: socket_root.join("checker.sock"),
            material_root,
            docker_binary: docker,
            runtime: "runc".into(),
            isolation_mode: "docker-dev".into(),
            operating_system: "linux".into(),
            architecture: "amd64".into(),
            sandbox_uid,
            sandbox_gid,
            cache: vec![CacheEntry {
                repository: "registry.example/workstream/checker".into(),
                platform_manifest_digest: format!("sha256:{}", "1".repeat(64)),
                platform_manifest_media_type: "application/vnd.oci.image.manifest.v1+json".into(),
                platform_manifest_byte_count: 1_367,
                operating_system: "linux".into(),
                architecture: "amd64".into(),
                config_image_id: format!("sha256:{}", "2".repeat(64)),
            }],
        };
        (root, config)
    }

    #[test]
    fn grant_ids_and_cache_repositories_are_closed() {
        assert!(valid_grant_id("extract_0123456789abcdef0123456789abcdef"));
        assert!(!valid_grant_id(
            "../extract_0123456789abcdef0123456789abcdef"
        ));
        assert!(valid_repository("registry.example/workstream/checker"));
        assert!(valid_repository("localhost:35104/workstream/checker"));
        assert!(!valid_repository("repo@sha256:bad"));
        assert!(!valid_repository("--network/host"));
        assert!(!valid_repository(
            "registry.example/workstream/checker:latest"
        ));
    }

    #[test]
    fn health_rechecks_runtime_and_ambiguous_manifest_cache_is_rejected() {
        let (root, mut config) = test_config();
        validate_config(&config).unwrap();
        let (mut client, mut server) = UnixStream::pair().unwrap();
        let request = serde_json::to_vec(
            &serde_json::json!({"protocol_version": PROTOCOL, "operation": "health"}),
        )
        .unwrap();
        write_frame(&mut client, &request).unwrap();
        let response = handle(&config, &mut server).unwrap();
        let value: Value = serde_json::from_slice(&response).unwrap();
        assert_eq!(value["status"], "ready");
        assert_eq!(value["isolation_mode"], "docker-dev");

        let mut duplicate = config.cache[0].clone();
        duplicate.repository = "registry.example/other/checker".into();
        config.cache.push(duplicate);
        assert_eq!(
            validate_config(&config).unwrap_err(),
            "cache identity invalid"
        );
        config.cache.pop();
        config.isolation_mode = "gvisor".into();
        config.runtime = "runsc".into();
        assert_eq!(
            validate_config(&config).unwrap_err(),
            "configured runtime unavailable"
        );
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn workspace_inventory_includes_empty_directories() {
        let (root, config) = test_config();
        let workspace = config.material_root.join("workspace");
        fs::create_dir(&workspace).unwrap();
        fs::create_dir(workspace.join("empty")).unwrap();
        fs::set_permissions(workspace.join("empty"), fs::Permissions::from_mode(0o500)).unwrap();
        fs::set_permissions(&workspace, fs::Permissions::from_mode(0o500)).unwrap();
        let metadata = fs::metadata(&workspace).unwrap();
        let inventory = inspect_workspace(&workspace, metadata.uid(), metadata.gid()).unwrap();
        assert_eq!(inventory.directories, vec!["empty"]);
        assert!(inventory.files.is_empty());
        let target = config.material_root.join("manifest.json");
        fs::write(&target, b"{}").unwrap();
        fs::set_permissions(&target, fs::Permissions::from_mode(0o400)).unwrap();
        let link = config.material_root.join("manifest-link.json");
        symlink(&target, &link).unwrap();
        assert_eq!(
            read_grant_manifest(&link, metadata.uid(), metadata.gid()).unwrap_err(),
            "grant manifest identity differs"
        );
        fs::set_permissions(&workspace, fs::Permissions::from_mode(0o700)).unwrap();
        fs::set_permissions(workspace.join("empty"), fs::Permissions::from_mode(0o700)).unwrap();
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn missing_platform_manifest_returns_closed_infrastructure_result() {
        let (root, mut config) = test_config();
        config.cache[0].platform_manifest_digest = format!("sha256:{}", "5".repeat(64));
        let request: Value =
            serde_json::from_slice(include_bytes!("../../fixtures/request.json")).unwrap();
        let envelope = serde_json::json!({
            "protocol_version": PROTOCOL,
            "operation": "execute",
            "request": request,
            "grant": {
                "grant_id": "extract_0123456789abcdef0123456789abcdef",
                "binding_digest": format!("sha256:{}", "6".repeat(64)),
            },
        });
        let (mut client, mut server) = UnixStream::pair().unwrap();
        write_frame(&mut client, &serde_json::to_vec(&envelope).unwrap()).unwrap();
        let response: Value =
            serde_json::from_slice(&handle(&config, &mut server).unwrap()).unwrap();
        assert_eq!(
            response["result"]["infrastructure_failure_code"],
            "implementation_unavailable"
        );
        assert!(response["isolation"].is_null());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn partial_frames_are_bounded_and_do_not_block_the_next_connection() {
        let (root, config) = test_config();
        let (mut stalled_client, stalled_server) = UnixStream::pair().unwrap();
        let writer = thread::spawn(move || {
            stalled_client.write_all(&20_u32.to_be_bytes()).unwrap();
            for _ in 0..20 {
                if stalled_client.write_all(b" ").is_err() {
                    break;
                }
                thread::sleep(Duration::from_millis(30));
            }
        });
        let started = Instant::now();
        serve_connection(&config, stalled_server, Duration::from_millis(100));
        assert!(started.elapsed() < Duration::from_millis(300));

        let (mut client, server) = UnixStream::pair().unwrap();
        let request = serde_json::to_vec(
            &serde_json::json!({"protocol_version": PROTOCOL, "operation": "health"}),
        )
        .unwrap();
        write_frame(&mut client, &request).unwrap();
        serve_connection(&config, server, Duration::from_secs(1));
        let response = read_frame(&mut client, MAX_RESPONSE_BYTES).unwrap();
        assert_eq!(
            serde_json::from_slice::<Value>(&response).unwrap()["status"],
            "ready"
        );
        writer.join().unwrap();
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn response_frame_write_uses_one_absolute_budget() {
        let (mut writer, reader) = UnixStream::pair().unwrap();
        let send_buffer: libc::c_int = 1_024;
        // SAFETY: setsockopt receives a valid Unix socket and a pointer to a
        // live integer whose size is supplied exactly.
        let configured = unsafe {
            libc::setsockopt(
                writer.as_raw_fd(),
                libc::SOL_SOCKET,
                libc::SO_SNDBUF,
                (&send_buffer as *const libc::c_int).cast(),
                std::mem::size_of_val(&send_buffer) as libc::socklen_t,
            )
        };
        assert_eq!(configured, 0);
        writer.set_nonblocking(true).unwrap();
        let started = Instant::now();
        assert_eq!(
            write_frame_until(
                &mut writer,
                &vec![b'x'; MAX_RESPONSE_BYTES],
                Instant::now() + Duration::from_millis(50),
            ),
            Err("response body failed".into())
        );
        assert!(started.elapsed() < Duration::from_millis(300));
        drop(reader);
    }

    #[test]
    fn process_input_and_client_disconnect_are_bounded_by_cleanup() {
        let (root, config) = test_config();
        fs::write(
            &config.docker_binary,
            b"#!/bin/sh\ncase \"$1\" in start) sleep 5;; kill) exit 0;; *) exit 0;; esac\n",
        )
        .unwrap();
        fs::set_permissions(&config.docker_binary, fs::Permissions::from_mode(0o700)).unwrap();
        let mut request = parse_request(include_bytes!("../../fixtures/request.json")).unwrap();
        request.deadline_ms = 100;
        request.value["input"] = Value::String("x".repeat(300_000));
        let (_peer, client) = UnixStream::pair().unwrap();
        let started = Instant::now();
        assert_eq!(
            run_started_container(
                &config,
                "bounded-stdin",
                &request,
                &client,
                Instant::now() + Duration::from_millis(100)
            ),
            Err("deadline_exceeded")
        );
        assert!(started.elapsed() < Duration::from_secs(2));

        request.deadline_ms = 30_000;
        let (peer, disconnected) = UnixStream::pair().unwrap();
        drop(peer);
        let started = Instant::now();
        assert_eq!(
            run_started_container(
                &config,
                "disconnected",
                &request,
                &disconnected,
                Instant::now() + Duration::from_secs(30)
            ),
            Err("implementation_unavailable")
        );
        assert!(started.elapsed() < Duration::from_secs(2));
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn uncertain_container_creation_is_removed_before_returning() {
        let (root, config) = test_config();
        fs::write(
            &config.docker_binary,
            b"#!/bin/sh\nroot=$(dirname \"$0\")\ncase \"$1\" in\n  create) : > \"$root/container\"; exit 17;;\n  rm) rm -f \"$root/container\"; exit 0;;\n  container) test -e \"$root/container\";;\nesac\n",
        )
        .unwrap();
        fs::set_permissions(&config.docker_binary, fs::Permissions::from_mode(0o700)).unwrap();
        let workspace = config.material_root.join("workspace");
        fs::create_dir(&workspace).unwrap();
        fs::set_permissions(&workspace, fs::Permissions::from_mode(0o500)).unwrap();
        let request = parse_request(include_bytes!("../../fixtures/request.json")).unwrap();
        let (_peer, client) = UnixStream::pair().unwrap();

        assert_eq!(
            execute_container(
                &config,
                &config.cache[0],
                &request,
                &workspace,
                &client,
                Instant::now() + Duration::from_secs(2),
            ),
            Err(("implementation_unavailable", false))
        );
        assert!(!root.join("container").exists());

        fs::set_permissions(&workspace, fs::Permissions::from_mode(0o700)).unwrap();
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn grant_lineage_matches_the_normalized_pre_submit_request() {
        let mut request = parse_request(include_bytes!("../../fixtures/request.json")).unwrap();
        let mut manifest = GrantManifest {
            protocol_version: GRANT_PROTOCOL.into(),
            grant_id: "extract_0123456789abcdef0123456789abcdef".into(),
            request_digest: request.request_digest.clone(),
            prepared_generation_id: request.value["identity"]["prepared_generation_id"]
                .as_str()
                .unwrap()
                .into(),
            attempt_id: request.value["identity"]["attempt_id"]
                .as_str()
                .unwrap()
                .into(),
            attempt_request_digest: request.value["identity"]["attempt_request_digest"]
                .as_str()
                .unwrap()
                .into(),
            archive_sha256: request.value["materials"][0]["sha256"]
                .as_str()
                .unwrap()
                .into(),
            archive_byte_count: request.value["materials"][0]["byte_count"]
                .as_u64()
                .unwrap(),
            semantic_manifest_sha256: String::new(),
            directories: Vec::new(),
            files: Vec::new(),
            binding_digest: format!("sha256:{}", "9".repeat(64)),
        };
        manifest.semantic_manifest_sha256 = semantic_manifest_hash(&manifest).unwrap();
        assert!(grant_matches_request(&manifest, &request));
        for field in 0..6 {
            let original = (
                manifest.prepared_generation_id.clone(),
                manifest.attempt_id.clone(),
                manifest.attempt_request_digest.clone(),
                manifest.archive_sha256.clone(),
                manifest.archive_byte_count,
                manifest.semantic_manifest_sha256.clone(),
            );
            match field {
                0 => {
                    manifest.prepared_generation_id = "00000000-0000-4000-8000-000000000000".into()
                }
                1 => manifest.attempt_id = "00000000-0000-4000-8000-000000000000".into(),
                2 => manifest.attempt_request_digest = format!("sha256:{}", "8".repeat(64)),
                3 => manifest.archive_sha256 = format!("sha256:{}", "8".repeat(64)),
                4 => manifest.archive_byte_count += 1,
                _ => manifest.semantic_manifest_sha256 = format!("sha256:{}", "8".repeat(64)),
            }
            assert!(!grant_matches_request(&manifest, &request));
            (
                manifest.prepared_generation_id,
                manifest.attempt_id,
                manifest.attempt_request_digest,
                manifest.archive_sha256,
                manifest.archive_byte_count,
                manifest.semantic_manifest_sha256,
            ) = original;
        }
        request.phase = "post_submit".into();
        assert!(!grant_matches_request(&manifest, &request));
    }
}
