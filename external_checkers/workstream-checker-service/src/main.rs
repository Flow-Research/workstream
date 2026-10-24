//! Trusted long-lived Unix-socket boundary for digest-pinned checker containers.

mod model_relay;
mod proxy_transport;
mod smol;
mod trial_docker;
mod trial_engine;
mod trial_evidence_proxy;
mod trial_profiles;
mod trial_relay;

use model_relay::{
    deserialize_required_model_grant, valid_model_grant, validate_proxy_socket,
    validate_relay_root, InvocationReceiptRegistry, InvocationRelay, ModelGrant,
    ModelReceiptResolver, RequiredModelGrant,
};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::os::fd::AsRawFd;
use std::os::unix::fs::FileTypeExt;
use std::os::unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt};
use std::os::unix::net::{UnixListener, UnixStream};
use std::os::unix::process::CommandExt;
use std::path::{Component, Path, PathBuf};
use std::process::{Child, Command, ExitStatus, Stdio};
use std::sync::Arc;
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};
use trial_docker::DockerRuntimeControl;
use trial_docker::{DockerTrialBackend, DockerTrialConfiguration};
use trial_engine::{GenericTrialEngine, SandboxBackendIdentity};
use trial_evidence_proxy::{
    DurableTrialReceiptPublisher, InvocationReceiptRegistrar, TrialEvidenceProxyClient,
};
use trial_profiles::TrialProfileCatalog;
use trial_relay::{TrialEngine, TrialProfile, TrialRelay, TrialRequestIdentity};
use workstream_checker_sdk::{
    canonical_hash, infrastructure_result, parse_request, validate_result, ValidatedRequest,
    MAX_REQUEST_BYTES,
};

const PROTOCOL: &str = "external_checker_service.v1";
const PRE_GRANT_PROTOCOL: &str = "workstream.external_checker_material_grant.v1";
const POST_GRANT_PROTOCOL: &str = "workstream.external_checker_material_grant.v2";
const CURRENT_ARCHIVE_ROLE: &str = "submission_archive";
const PREDECESSOR_ARCHIVE_ROLE: &str = "predecessor_submission_archive";
const MAX_ENVELOPE_BYTES: usize = MAX_REQUEST_BYTES + 16_384;
const MAX_RESPONSE_BYTES: usize = 65_536 + 16_384;
const SOCKET_IO_TIMEOUT: Duration = Duration::from_secs(2);
const DOCKER_CONTROL_TIMEOUT: Duration = Duration::from_secs(10);
const CLEANUP_TIMEOUT: Duration = Duration::from_secs(10);
const CLEANUP_MAXIMUM_OUTPUT_BYTES: usize = 256 * 1024;
const RUNTIME_FILE_PREFIX: &str = ".workstream-checker-runtime-";
const CONTAINER_OWNER_FILE: &str = ".workstream-checker-owner";
const UNSETTLED_RESOURCE_ERROR: &str = "owned runtime resource cleanup unsettled";

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
struct ServiceConfig {
    #[serde(skip)]
    container_owner: Option<String>,
    #[serde(skip)]
    smol_admission: Option<std::sync::Arc<smol::Admission>>,
    socket_path: PathBuf,
    model_proxy_socket: Option<PathBuf>,
    model_relay_root: Option<PathBuf>,
    #[serde(default)]
    trial_authority_manifest_path: Option<PathBuf>,
    #[serde(default)]
    trial_authority_manifest_digest: Option<String>,
    #[serde(skip)]
    trial_profiles: Option<TrialProfileCatalog>,
    #[serde(default)]
    trial_runtime: Option<TrialRuntimeConfiguration>,
    #[serde(skip)]
    trial_control: Option<Arc<DockerRuntimeControl>>,
    material_root: PathBuf,
    #[serde(default)]
    docker_binary: PathBuf,
    #[serde(default)]
    smol: Option<smol::SmolConfig>,
    runtime: String,
    isolation_mode: String,
    operating_system: String,
    architecture: String,
    sandbox_uid: u32,
    sandbox_gid: u32,
    cache: Vec<CacheEntry>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct TrialRuntimeConfiguration {
    relay_root: PathBuf,
    scratch_root: PathBuf,
    runtime_root: PathBuf,
    runtime_configuration: PathBuf,
    outer_runtime_config_digest: String,
    offline_cache_root: PathBuf,
    deployment_owner: String,
    runtime_key: String,
    builder_image_id: String,
    trusted_launcher_path: PathBuf,
    trusted_launcher_digest: String,
    maximum_candidate_archive_bytes: u64,
}

impl InvocationReceiptRegistrar for InvocationReceiptRegistry {
    fn register(
        &self,
        request_digest: &str,
        canonical_receipt_utf8: String,
        receipt_sha256: String,
        _custody: &trial_relay::TrialReceiptCustodyAck,
    ) -> Result<String, ()> {
        InvocationReceiptRegistry::register(
            self,
            request_digest,
            &canonical_receipt_utf8,
            &receipt_sha256,
        )
        .map_err(|_| ())
    }
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
    #[serde(default)]
    smol: Option<smol::SmolImage>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ExecuteEnvelope {
    protocol_version: String,
    operation: String,
    request: Value,
    grant: GrantReference,
    #[serde(deserialize_with = "deserialize_required_model_grant")]
    model_grant: RequiredModelGrant,
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

#[derive(Debug, Clone, Deserialize, Serialize)]
struct GrantManifest {
    protocol_version: String,
    grant_id: String,
    request_digest: String,
    #[serde(flatten)]
    identity: GrantIdentity,
    directories: Vec<String>,
    files: Vec<GrantFile>,
    binding_digest: String,
}

struct VerifiedGrant {
    binding_digest: String,
    input: PathBuf,
    input_inventory: WorkspaceInventory,
    predecessor: Option<PathBuf>,
    predecessor_inventory: Option<WorkspaceInventory>,
}

#[derive(Debug, PartialEq)]
struct ExecutedChecker {
    value: Value,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(tag = "phase", deny_unknown_fields)]
enum GrantIdentity {
    #[serde(rename = "pre_submit")]
    PreSubmit {
        prepared_generation_id: String,
        attempt_id: String,
        attempt_request_digest: String,
        archive_sha256: String,
        archive_byte_count: u64,
        semantic_manifest_sha256: String,
    },
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct PostGrantManifest {
    protocol_version: String,
    grant_id: String,
    request_digest: String,
    phase: String,
    identity: Value,
    evaluation_context_sha256: Option<String>,
    materials: Vec<PostGrantMaterial>,
    visible_roles: Vec<String>,
    binding_digest: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct PostGrantMaterial {
    material: Value,
    directories: Vec<String>,
    files: Vec<GrantFile>,
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
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

struct EmergencyCleanupBudget {
    deadline: Option<Instant>,
    remaining_output: usize,
}

struct OutputMeter {
    remaining: usize,
}

struct RequestExecutionBudget {
    deadline: Instant,
    output: OutputMeter,
    cleanup: EmergencyCleanupBudget,
}

#[derive(Debug, PartialEq, Eq)]
struct ExecutionFailure {
    code: &'static str,
    launched: bool,
    cleanup_unsettled: bool,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum RemovalOutcome {
    Confirmed,
    Recovered,
    Unsettled,
}

impl OutputMeter {
    fn new(maximum: usize) -> Self {
        Self { remaining: maximum }
    }

    fn bytes(&mut self, count: usize) -> Result<(), &'static str> {
        self.remaining = self.remaining.checked_sub(count).ok_or("invalid_output")?;
        Ok(())
    }

    fn charge(&mut self, output: &BoundedCommandOutput) -> Result<(), &'static str> {
        self.bytes(output.stdout.len().saturating_add(output._stderr.len()))
    }
}

impl EmergencyCleanupBudget {
    fn new() -> Self {
        Self {
            deadline: None,
            remaining_output: CLEANUP_MAXIMUM_OUTPUT_BYTES,
        }
    }

    fn deadline(&mut self) -> Instant {
        *self
            .deadline
            .get_or_insert_with(|| Instant::now() + CLEANUP_TIMEOUT)
    }

    fn charge(&mut self, output: &BoundedCommandOutput) -> Result<(), String> {
        let count = output.stdout.len().saturating_add(output._stderr.len());
        self.remaining_output = self
            .remaining_output
            .checked_sub(count)
            .ok_or_else(|| "cleanup output unbounded".to_owned())?;
        Ok(())
    }
}

impl RequestExecutionBudget {
    fn new(deadline: Instant, maximum_output: usize) -> Self {
        Self {
            deadline,
            output: OutputMeter::new(maximum_output),
            cleanup: EmergencyCleanupBudget::new(),
        }
    }
}

#[derive(Debug)]
struct OwnedSocketListener {
    listener: Option<UnixListener>,
    parent: File,
    path: PathBuf,
    device: u64,
    inode: u64,
}

impl OwnedSocketListener {
    fn bind(path: &Path) -> Result<Self, String> {
        let parent_path = path.parent().ok_or("socket parent missing")?;
        let parent = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(parent_path)
            .map_err(|_| "socket parent unavailable")?;
        let parent_metadata = parent.metadata().map_err(|_| "socket parent unavailable")?;
        if !private_socket_parent(&parent_metadata)
            || fs::canonicalize(format!("/proc/self/fd/{}", parent.as_raw_fd()))
                .map_err(|_| "socket parent unavailable")?
                != parent_path
        {
            return Err("socket parent is not private".into());
        }
        // SAFETY: `parent` is a live descriptor. `flock` changes only its advisory lock state.
        if unsafe { libc::flock(parent.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
            return Err("socket custody unavailable".into());
        }
        prepare_socket_path(path, &parent)?;
        let listener = UnixListener::bind(path).map_err(|_| "socket bind failed")?;
        let mut owned = Self {
            listener: Some(listener),
            parent,
            path: path.to_owned(),
            device: 0,
            inode: 0,
        };
        let initial = fs::symlink_metadata(path).map_err(|_| "socket identity missing")?;
        if !process_owned_socket(&initial) {
            return Err("socket identity invalid".into());
        }
        owned.device = initial.dev();
        owned.inode = initial.ino();
        fs::set_permissions(path, fs::Permissions::from_mode(0o600))
            .map_err(|_| "socket permission failed")?;
        let metadata = fs::symlink_metadata(path).map_err(|_| "socket identity missing")?;
        if !owned_socket_identity(&metadata) {
            return Err("socket identity invalid".into());
        }
        if (metadata.dev(), metadata.ino()) != (owned.device, owned.inode) {
            return Err("socket identity changed".into());
        }
        Ok(owned)
    }

    fn incoming(&self) -> std::os::unix::net::Incoming<'_> {
        self.listener
            .as_ref()
            .expect("owned listener exists until drop")
            .incoming()
    }
}

impl Drop for OwnedSocketListener {
    fn drop(&mut self) {
        drop(self.listener.take());
        let Ok(metadata) = fs::symlink_metadata(&self.path) else {
            return;
        };
        if process_owned_socket(&metadata)
            && (metadata.dev(), metadata.ino()) == (self.device, self.inode)
        {
            let _ = unlink_socket_at(&self.parent, &self.path);
            let _ = self.parent.sync_all();
        }
    }
}

fn owned_socket_identity(metadata: &fs::Metadata) -> bool {
    process_owned_socket(metadata) && metadata.mode() & 0o777 == 0o600
}

fn process_owned_socket(metadata: &fs::Metadata) -> bool {
    // SAFETY: effective process IDs are read-only process attributes.
    let (effective_uid, effective_gid) = unsafe { (libc::geteuid(), libc::getegid()) };
    metadata.file_type().is_socket()
        && metadata.uid() == effective_uid
        && metadata.gid() == effective_gid
}

fn private_socket_parent(metadata: &fs::Metadata) -> bool {
    // SAFETY: effective process IDs are read-only process attributes.
    let (effective_uid, effective_gid) = unsafe { (libc::geteuid(), libc::getegid()) };
    metadata.file_type().is_dir()
        && metadata.mode() & 0o777 == 0o700
        && metadata.uid() == effective_uid
        && metadata.gid() == effective_gid
}

fn unlink_socket_at(parent: &File, path: &Path) -> Result<(), String> {
    use std::os::unix::ffi::OsStrExt;

    let name = path.file_name().ok_or("socket name missing")?;
    let name = std::ffi::CString::new(name.as_bytes()).map_err(|_| "socket name invalid")?;
    // SAFETY: `parent` is a pinned directory descriptor and `name` is NUL terminated.
    if unsafe { libc::unlinkat(parent.as_raw_fd(), name.as_ptr(), 0) } != 0 {
        return Err("socket cleanup failed".into());
    }
    Ok(())
}

fn prepare_socket_path(path: &Path, parent: &File) -> Result<(), String> {
    let before = match fs::symlink_metadata(path) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(()),
        Err(_) => return Err("socket identity unavailable".into()),
    };
    if !owned_socket_identity(&before) {
        return Err("socket path is not an owned socket".into());
    }
    match UnixStream::connect(path) {
        Ok(_) => return Err("socket listener already active".into()),
        Err(error) if error.kind() == std::io::ErrorKind::ConnectionRefused => {}
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(()),
        Err(_) => return Err("socket listener state is ambiguous".into()),
    }
    let after = fs::symlink_metadata(path).map_err(|_| "socket identity changed")?;
    if !owned_socket_identity(&after) || (before.dev(), before.ino()) != (after.dev(), after.ino())
    {
        return Err("socket identity changed".into());
    }
    unlink_socket_at(parent, path).map_err(|_| "stale socket cleanup failed")?;
    parent
        .sync_all()
        .map_err(|_| "stale socket cleanup failed".into())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("external checker service unavailable: {error}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), String> {
    if std::env::args().nth(1).as_deref() == Some("--smol-guardian") {
        return smol::guardian();
    }
    let path = std::env::args_os()
        .nth(1)
        .ok_or("configuration path missing")?;
    let bytes = fs::read(path).map_err(|_| "configuration unavailable")?;
    let mut config: ServiceConfig =
        serde_json::from_slice(&bytes).map_err(|_| "configuration invalid")?;
    load_trial_profiles(&mut config)?;
    let listener = prepare_listener(&mut config)?;
    if config.runtime == "smolvm" {
        smol::serve(&config, listener.incoming())
    } else {
        serve_connections(&config, listener.incoming(), SOCKET_IO_TIMEOUT)
    }
}

fn load_trial_runtime(config: &mut ServiceConfig) -> Result<(), String> {
    match (&config.trial_profiles, &config.trial_runtime) {
        (None, None) => Ok(()),
        (Some(_), Some(runtime)) => {
            if runtime.maximum_candidate_archive_bytes == 0
                || !valid_digest(&runtime.outer_runtime_config_digest)
                || !valid_digest(&runtime.trusted_launcher_digest)
                || !runtime.trusted_launcher_path.is_absolute()
                || config.runtime != "runsc"
                || config.isolation_mode != "gvisor"
                || config.model_proxy_socket.is_none()
            {
                return Err("trial runtime configuration invalid".into());
            }
            let control = DockerRuntimeControl::new(
                config.docker_binary.clone(),
                runtime.runtime_root.clone(),
                runtime.runtime_configuration.clone(),
            )
            .map_err(|_| "trial runtime configuration invalid")?;
            control
                .recover_deployment(&runtime.deployment_owner, Instant::now() + CLEANUP_TIMEOUT)
                .map_err(|_| UNSETTLED_RESOURCE_ERROR.to_owned())?;
            config.trial_control = Some(Arc::new(control));
            Ok(())
        }
        _ => Err("trial authority/runtime configuration incomplete".into()),
    }
}

fn trial_engine(
    config: &ServiceConfig,
    request: &ValidatedRequest,
    profile: &TrialProfile,
) -> Result<Arc<dyn TrialEngine>, String> {
    // SAFETY: effective process IDs are read-only process attributes and name
    // the service account that owns all engine-created export directories.
    let (export_uid, export_gid) = unsafe { (libc::geteuid(), libc::getegid()) };
    let runtime = config
        .trial_runtime
        .as_ref()
        .ok_or("trial runtime unavailable")?;
    let control = config
        .trial_control
        .as_ref()
        .ok_or("trial runtime unavailable")?
        .clone();
    if runtime.outer_runtime_config_digest != profile.outer_runtime_config_digest {
        return Err("trial outer runtime identity invalid".into());
    }
    let identity = request
        .value
        .get("identity")
        .and_then(Value::as_object)
        .ok_or("trial request identity invalid")?;
    let attempt_id = identity
        .get("attempt_id")
        .and_then(Value::as_str)
        .ok_or("trial request identity invalid")?;
    let backend = DockerTrialBackend::new(
        DockerTrialConfiguration {
            identity: SandboxBackendIdentity {
                engine_identity_digest: profile.engine_identity_digest.clone(),
                child_runtime: profile.child_runtime.clone(),
                child_runtime_config_digest: profile.child_runtime_config_digest.clone(),
                child_host_uds: profile.child_host_uds.clone(),
                platform: profile.platform.clone(),
                platform_identity_digest: profile.platform_identity_digest.clone(),
                builder_image_digest: profile.builder_image_digest.clone(),
                trusted_launcher_digest: profile.trusted_launcher_digest.clone(),
                offline_cache_digest: profile.offline_cache_digest.clone(),
                approved_base_digests: profile.approved_base_digests.clone(),
            },
            deployment_owner: runtime.deployment_owner.clone(),
            request_digest: request.request_digest.clone(),
            attempt_id: attempt_id.to_owned(),
            runtime_key: runtime.runtime_key.clone(),
            builder_image_id: runtime.builder_image_id.clone(),
            trusted_launcher_path: runtime.trusted_launcher_path.clone(),
            trusted_launcher_digest: runtime.trusted_launcher_digest.clone(),
            offline_cache_root: runtime.offline_cache_root.clone(),
            maximum_candidate_archive_bytes: runtime.maximum_candidate_archive_bytes,
            candidate_uid: config.sandbox_uid,
            candidate_gid: config.sandbox_gid,
            export_uid,
            export_gid,
        },
        control,
    )
    .map_err(|_| "trial runtime unavailable")?;
    Ok(Arc::new(GenericTrialEngine::new(backend)))
}

fn trial_request_identity(
    request: &ValidatedRequest,
    material_binding_digest: &str,
) -> Result<TrialRequestIdentity, String> {
    let identity = request
        .value
        .get("identity")
        .and_then(Value::as_object)
        .ok_or("trial request identity invalid")?;
    let string = |name: &str| {
        identity
            .get(name)
            .and_then(Value::as_str)
            .map(str::to_owned)
            .ok_or("trial request identity invalid")
    };
    let number = |name: &str| {
        identity
            .get(name)
            .and_then(Value::as_u64)
            .ok_or("trial request identity invalid")
    };
    let requirement_id = request
        .value
        .pointer("/input/requirement_id")
        .and_then(Value::as_str)
        .ok_or("trial requirement invalid")?;
    let input_digest = request
        .value
        .get("input_sha256")
        .and_then(Value::as_str)
        .ok_or("trial input digest invalid")?;
    let materials = request
        .value
        .get("materials")
        .ok_or("trial materials invalid")?;
    Ok(TrialRequestIdentity {
        request_digest: request.request_digest.clone(),
        material_binding_digest: material_binding_digest.to_owned(),
        input_digest: input_digest.to_owned(),
        materials_digest: canonical_hash(materials).map_err(|_| "trial materials invalid")?,
        project_id: string("project_id")?,
        task_id: string("task_id")?,
        assignment_id: string("assignment_id")?,
        submission_id: string("submission_id")?,
        submission_version: number("submission_version")?,
        requirement_id: requirement_id.to_owned(),
        registry_entry_id: request.registry_entry_id.clone(),
        registry_entry_digest: request.registry_entry_digest.clone(),
        checker_image_digest: request.image_digest.clone(),
        configuration_sha256: request.configuration_digest.clone(),
        evaluation_request_id: string("evaluation_request_id")?,
        evaluation_generation: number("evaluation_generation")?,
        checker_run_id: string("attempt_id")?,
        attempt_id: string("attempt_id")?,
        result_id: string("result_id")?,
        worker_lease_id: string("lease_id")?,
        worker_lease_generation: number("lease_generation")?,
        worker_lease_expires_at: string("lease_expires_at")?,
    })
}

fn load_trial_profiles(config: &mut ServiceConfig) -> Result<(), String> {
    match (
        config.trial_authority_manifest_path.as_deref(),
        config.trial_authority_manifest_digest.as_deref(),
    ) {
        (None, None) => Ok(()),
        (Some(path), Some(digest)) => {
            let bytes = read_trial_authority_manifest(path)?;
            config.trial_profiles = Some(
                TrialProfileCatalog::from_bytes(&bytes, digest)
                    .map_err(|error| error.to_owned())?,
            );
            Ok(())
        }
        _ => Err("trial authority manifest configuration incomplete".into()),
    }
}

fn read_trial_authority_manifest(path: &Path) -> Result<Vec<u8>, String> {
    read_trial_authority_manifest_after_open(path, || {})
}

fn read_trial_authority_manifest_after_open(
    path: &Path,
    after_open: impl FnOnce(),
) -> Result<Vec<u8>, String> {
    const MAXIMUM_BYTES: u64 = 4 * 1024 * 1024;
    if !path.is_absolute()
        || fs::canonicalize(path).map_err(|_| "trial authority manifest unavailable")? != path
    {
        return Err("trial authority manifest path invalid".into());
    }
    let mut file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK)
        .open(path)
        .map_err(|_| "trial authority manifest unavailable")?;
    let before = file
        .metadata()
        .map_err(|_| "trial authority manifest unavailable")?;
    if !before.file_type().is_file()
        || before.file_type().is_symlink()
        || before.nlink() != 1
        || before.len() == 0
        || before.len() > MAXIMUM_BYTES
    {
        return Err("trial authority manifest path invalid".into());
    }
    after_open();
    let mut bytes = Vec::with_capacity(before.len() as usize);
    Read::by_ref(&mut file)
        .take(MAXIMUM_BYTES + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| "trial authority manifest unavailable")?;
    let after = file
        .metadata()
        .map_err(|_| "trial authority manifest unavailable")?;
    let current = fs::symlink_metadata(path).map_err(|_| "trial authority manifest unavailable")?;
    if bytes.len() as u64 != before.len()
        || bytes.len() as u64 > MAXIMUM_BYTES
        || (after.dev(), after.ino(), after.len()) != (before.dev(), before.ino(), before.len())
        || (current.dev(), current.ino(), current.len())
            != (before.dev(), before.ino(), before.len())
    {
        return Err("trial authority manifest changed".into());
    }
    Ok(bytes)
}

fn serve_connections<I>(
    config: &ServiceConfig,
    connections: I,
    timeout: Duration,
) -> Result<(), String>
where
    I: IntoIterator<Item = std::io::Result<UnixStream>>,
{
    for connection in connections {
        match connection {
            Ok(stream) => serve_connection(config, stream, timeout)?,
            Err(_) => continue,
        }
    }
    Ok(())
}

fn prepare_listener(config: &mut ServiceConfig) -> Result<OwnedSocketListener, String> {
    // Socket-parent custody must precede validation that invokes Docker and every
    // startup cleanup. A losing concurrent process cannot inspect or remove the
    // live owner's resources.
    let listener = OwnedSocketListener::bind(&config.socket_path)?;
    config.container_owner = Some(load_container_owner(&listener.parent)?);
    validate_config(config)?;
    cleanup_stale_runtime_files(config)?;
    if config.runtime == "smolvm" {
        smol::recover(config)?;
    } else {
        cleanup_stale_checker_containers(config)?;
    }
    // Trial recovery uses the same settled socket-parent custody. Smol nodes
    // cannot admit trial configuration through this Docker/runsc capability.
    load_trial_runtime(config)?;
    Ok(listener)
}

fn load_container_owner(parent: &File) -> Result<String, String> {
    let path = PathBuf::from(format!(
        "/proc/self/fd/{}/{}",
        parent.as_raw_fd(),
        CONTAINER_OWNER_FILE
    ));
    let flags = libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK;
    match OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .custom_flags(flags)
        .open(&path)
    {
        Ok(mut file) => {
            let mut random = [0_u8; 32];
            File::open("/dev/urandom")
                .and_then(|mut source| source.read_exact(&mut random))
                .map_err(|_| "container owner randomness unavailable")?;
            let mut owner = String::with_capacity(64);
            for byte in random {
                use std::fmt::Write;
                write!(&mut owner, "{byte:02x}").expect("writing to String cannot fail");
            }
            file.write_all(owner.as_bytes())
                .and_then(|_| file.sync_all())
                .map_err(|_| "container owner persistence failed")?;
            parent
                .sync_all()
                .map_err(|_| "container owner persistence failed")?;
        }
        Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {}
        Err(_) => return Err("container owner unavailable".into()),
    }
    let file = OpenOptions::new()
        .read(true)
        .custom_flags(flags)
        .open(path)
        .map_err(|_| "container owner unavailable")?;
    let metadata = file.metadata().map_err(|_| "container owner unavailable")?;
    // SAFETY: effective process IDs are read-only process attributes.
    let (uid, gid) = unsafe { (libc::geteuid(), libc::getegid()) };
    if !metadata.is_file()
        || metadata.nlink() != 1
        || metadata.uid() != uid
        || metadata.gid() != gid
        || metadata.mode() & 0o7777 != 0o600
        || metadata.len() != 64
    {
        return Err("container owner identity invalid".into());
    }
    let mut owner = String::new();
    file.take(65)
        .read_to_string(&mut owner)
        .map_err(|_| "container owner invalid")?;
    if !valid_full_container_id(&owner) {
        return Err("container owner invalid".into());
    }
    Ok(owner)
}

fn container_owner(config: &ServiceConfig) -> Result<&str, String> {
    config
        .container_owner
        .as_deref()
        .filter(|owner| valid_full_container_id(owner))
        .ok_or_else(|| "container owner custody missing".into())
}

fn serve_connection(
    config: &ServiceConfig,
    mut stream: UnixStream,
    timeout: Duration,
) -> Result<(), String> {
    if stream.set_nonblocking(true).is_err() {
        return Ok(());
    }
    let response = read_frame_until(&mut stream, MAX_ENVELOPE_BYTES, Instant::now() + timeout)
        .and_then(|bytes| handle_frame(config, &stream, &bytes));
    if let Err(error) = &response {
        eprintln!("checker request rejected: {error}");
    }
    if let Some(bytes) = connection_response(response)? {
        let _ = write_frame_until(&mut stream, &bytes, Instant::now() + timeout);
    }
    Ok(())
}

fn connection_response(response: Result<Vec<u8>, String>) -> Result<Option<Vec<u8>>, String> {
    match response {
        Ok(bytes) => Ok(Some(bytes)),
        Err(error) if error == UNSETTLED_RESOURCE_ERROR => Err(error),
        Err(_) => Ok(None),
    }
}

fn validate_config(config: &ServiceConfig) -> Result<(), String> {
    if !config.socket_path.is_absolute()
        || !config.material_root.is_absolute()
        || !matches!(
            (config.runtime.as_str(), config.isolation_mode.as_str()),
            ("runsc", "gvisor") | ("runc", "docker-dev") | ("smolvm", "smol-microvm")
        )
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
    // SAFETY: effective process IDs are read-only process attributes.
    let (effective_uid, effective_gid) = unsafe { (libc::geteuid(), libc::getegid()) };
    if !socket_parent_metadata.file_type().is_dir()
        || socket_parent_metadata.file_type().is_symlink()
        || socket_parent_metadata.mode() & 0o777 != 0o700
        || socket_parent_metadata.uid() != effective_uid
        || socket_parent_metadata.gid() != effective_gid
        || fs::canonicalize(socket_parent).map_err(|_| "socket parent invalid")? != socket_parent
    {
        return Err("socket parent is not private".into());
    }
    match (&config.model_proxy_socket, &config.model_relay_root) {
        (Some(model_proxy_socket), Some(model_relay_root)) if config.runtime != "smolvm" => {
            validate_proxy_socket(model_proxy_socket)?;
            validate_relay_root(model_relay_root)?;
            if (config.sandbox_uid, config.sandbox_gid) != (effective_uid, effective_gid) {
                return Err("model relay identity differs".into());
            }
        }
        (None, None) => {}
        _ => return Err("model relay configuration incomplete".into()),
    }
    if config.runtime == "smolvm" {
        if !config.docker_binary.as_os_str().is_empty() {
            return Err("unused Docker configuration".into());
        }
        smol::validate(config)?;
    } else {
        if config.smol.is_some() || !config.docker_binary.is_absolute() {
            return Err("engine configuration invalid".into());
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

#[cfg(test)]
fn handle(config: &ServiceConfig, stream: &mut UnixStream) -> Result<Vec<u8>, String> {
    let bytes = read_frame(stream, MAX_ENVELOPE_BYTES)?;
    handle_frame(config, stream, &bytes)
}

fn handle_frame(
    config: &ServiceConfig,
    stream: &UnixStream,
    bytes: &[u8],
) -> Result<Vec<u8>, String> {
    let value: Value = serde_json::from_slice(bytes).map_err(|_| "request envelope invalid")?;
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
    if let Some(model_grant) = envelope.model_grant.0.as_ref() {
        if !valid_model_grant(model_grant, &request.request_digest, &request.phase) {
            return Err("model grant invalid".into());
        }
        if config.runtime == "smolvm" {
            return encode_response(
                infrastructure_result(&request, "implementation_unavailable")
                    .map_err(|_| "result construction failed")?,
                None,
            );
        }
        if config.model_proxy_socket.is_none() || config.model_relay_root.is_none() {
            return Err("model grant invalid".into());
        }
    }
    let _reservation = if config.runtime == "smolvm" {
        match smol::reserve(config, &request) {
            Ok(reservation) => Some(reservation),
            Err(_) => {
                return encode_response(
                    infrastructure_result(&request, "implementation_unavailable")
                        .map_err(|_| "result construction failed")?,
                    None,
                )
            }
        }
    } else {
        None
    };
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
    let mut budget = RequestExecutionBudget::new(
        Instant::now() + Duration::from_millis(request.deadline_ms),
        request.maximum_output_bytes,
    );
    let (result, isolation) = match verify_grant(config, &request, &envelope.grant) {
        Ok(grant) => match inspect_image(config, cache, stream, &mut budget) {
            Ok(()) => match execute_container(
                config,
                cache,
                &request,
                &grant,
                envelope.model_grant.0.as_ref(),
                stream,
                &mut budget,
            ) {
                Ok(output) if validate_result(&output.value, &request).is_ok() => {
                    (output.value, Some(isolation))
                }
                Ok(_) => (
                    infrastructure_result(&request, "invalid_output")
                        .map_err(|_| "result construction failed")?,
                    Some(isolation),
                ),
                Err(failure) if failure.cleanup_unsettled => {
                    return Err(UNSETTLED_RESOURCE_ERROR.into());
                }
                Err(failure) => (
                    infrastructure_result(&request, failure.code)
                        .map_err(|_| "result construction failed")?,
                    failure.launched.then_some(isolation),
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
    if config.runtime == "smolvm" {
        return smol::ready(config);
    }
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
    run_bounded_command_inner(binary, arguments, deadline, maximum_output, None, None)
}

fn run_bounded_command_cancellable(
    binary: &Path,
    arguments: &[&str],
    deadline: Instant,
    maximum_output: usize,
    client: &UnixStream,
    cleanup: &mut EmergencyCleanupBudget,
) -> Result<BoundedCommandOutput, String> {
    run_bounded_command_inner(
        binary,
        arguments,
        deadline,
        maximum_output,
        Some(client),
        Some(cleanup),
    )
}

fn run_bounded_command_inner(
    binary: &Path,
    arguments: &[&str],
    deadline: Instant,
    maximum_output: usize,
    client: Option<&UnixStream>,
    cleanup: Option<&mut EmergencyCleanupBudget>,
) -> Result<BoundedCommandOutput, String> {
    if Instant::now() >= deadline {
        return Err("process deadline exceeded".into());
    }
    let child = Command::new(binary)
        .args(arguments)
        .process_group(0)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|_| "process launch failed")?;
    collect_bounded_command(child, deadline, maximum_output, client, cleanup)
}

fn stop_command_group(child: &mut Child, deadline: Instant) -> Result<ExitStatus, String> {
    // Every control command has its own fresh process group; never kill by name.
    unsafe {
        libc::kill(-(child.id() as i32), libc::SIGKILL);
    }
    stop_child(child, deadline)
}

fn collect_bounded_command(
    mut child: Child,
    deadline: Instant,
    maximum_output: usize,
    client: Option<&UnixStream>,
    mut cleanup: Option<&mut EmergencyCleanupBudget>,
) -> Result<BoundedCommandOutput, String> {
    let mut stdout = match child.stdout.take() {
        Some(stdout) => stdout,
        None => {
            let _ = stop_command_group(&mut child, command_cleanup_deadline(&mut cleanup));
            return Err("process stdout unavailable".into());
        }
    };
    let mut stderr = match child.stderr.take() {
        Some(stderr) => stderr,
        None => {
            let _ = stop_command_group(&mut child, command_cleanup_deadline(&mut cleanup));
            return Err("process stderr unavailable".into());
        }
    };
    if set_nonblocking(&stdout).is_err() || set_nonblocking(&stderr).is_err() {
        let _ = stop_command_group(&mut child, command_cleanup_deadline(&mut cleanup));
        return Err("process descriptor unavailable".into());
    }
    let mut stdout_bytes = Vec::new();
    let mut stderr_bytes = Vec::new();
    loop {
        if client.is_some_and(|stream| !client_is_connected(stream)) {
            let _ = stop_command_group(&mut child, command_cleanup_deadline(&mut cleanup));
            return Err("client disconnected".into());
        }
        let stdout_read = read_available(&mut stdout, &mut stdout_bytes, maximum_output);
        let stderr_read = read_available(&mut stderr, &mut stderr_bytes, maximum_output);
        if stdout_read.is_err()
            || stderr_read.is_err()
            || stdout_bytes.len().saturating_add(stderr_bytes.len()) > maximum_output
        {
            let _ = stop_command_group(&mut child, command_cleanup_deadline(&mut cleanup));
            return Err("process output unbounded".into());
        }
        let status = match child.try_wait() {
            Ok(status) => status,
            Err(_) => {
                let _ = stop_command_group(&mut child, command_cleanup_deadline(&mut cleanup));
                return Err("process wait failed".into());
            }
        };
        if let Some(status) = status.filter(|_| stdout_read == Ok(true) && stderr_read == Ok(true))
        {
            read_available(&mut stdout, &mut stdout_bytes, maximum_output)?;
            read_available(&mut stderr, &mut stderr_bytes, maximum_output)?;
            if stdout_bytes.len().saturating_add(stderr_bytes.len()) > maximum_output {
                return Err("process output unbounded".into());
            }
            return Ok(BoundedCommandOutput {
                status,
                stdout: stdout_bytes,
                _stderr: stderr_bytes,
            });
        }
        if Instant::now() >= deadline {
            stop_command_group(&mut child, command_cleanup_deadline(&mut cleanup))?;
            return Err("process deadline exceeded".into());
        }
        thread::sleep(Duration::from_millis(5));
    }
}

fn command_cleanup_deadline(cleanup: &mut Option<&mut EmergencyCleanupBudget>) -> Instant {
    cleanup
        .as_deref_mut()
        .map(EmergencyCleanupBudget::deadline)
        .unwrap_or_else(|| Instant::now() + CLEANUP_TIMEOUT)
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
) -> Result<VerifiedGrant, String> {
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
    let value: Value = serde_json::from_slice(&raw).map_err(|_| "grant manifest invalid")?;
    let mut body = value.as_object().cloned().ok_or("grant manifest invalid")?;
    body.remove("binding_digest");
    let binding = canonical_hash(&Value::Object(body)).map_err(|_| "grant binding invalid")?;
    if value.get("binding_digest").and_then(Value::as_str) != Some(binding.as_str())
        || binding != reference.binding_digest
    {
        return Err("grant binding differs".into());
    }
    match value.get("protocol_version").and_then(Value::as_str) {
        Some(PRE_GRANT_PROTOCOL) => {
            let manifest: GrantManifest =
                serde_json::from_value(value).map_err(|_| "grant manifest invalid")?;
            if manifest.grant_id != reference.grant_id
                || manifest.request_digest != request.request_digest
                || manifest.binding_digest != reference.binding_digest
                || !grant_matches_request(&manifest, request)
            {
                return Err("grant binding differs".into());
            }
            let input = grant_root.join("workspace");
            let observed = inspect_workspace(&input, config.sandbox_uid, config.sandbox_gid)?;
            if observed.files != manifest.files || observed.directories != manifest.directories {
                return Err("grant material differs".into());
            }
            Ok(VerifiedGrant {
                binding_digest: reference.binding_digest.clone(),
                input,
                input_inventory: observed,
                predecessor: None,
                predecessor_inventory: None,
            })
        }
        Some(POST_GRANT_PROTOCOL) => {
            let manifest: PostGrantManifest =
                serde_json::from_value(value).map_err(|_| "grant manifest invalid")?;
            verify_post_grant(config, request, reference, &grant_root, &manifest)
        }
        _ => Err("grant protocol invalid".into()),
    }
}

fn grant_matches_request(manifest: &GrantManifest, request: &ValidatedRequest) -> bool {
    let Some(identity) = request.value.get("identity").and_then(Value::as_object) else {
        return false;
    };
    let Some(materials) = request.value.get("materials").and_then(Value::as_array) else {
        return false;
    };
    let Some(archive) = materials.iter().find_map(|item| {
        let object = item.as_object()?;
        (object.get("phase")?.as_str()? == request.phase
            && object.get("role")?.as_str()? == "submission_archive")
            .then_some(object)
    }) else {
        return false;
    };
    let semantic_manifest_sha256 = semantic_manifest_hash(manifest).ok();
    match &manifest.identity {
        GrantIdentity::PreSubmit {
            prepared_generation_id,
            attempt_id,
            attempt_request_digest,
            archive_sha256,
            archive_byte_count,
            semantic_manifest_sha256: expected_manifest,
        } => {
            request.phase == "pre_submit"
                && identity
                    .get("prepared_generation_id")
                    .and_then(Value::as_str)
                    == Some(prepared_generation_id)
                && identity.get("attempt_id").and_then(Value::as_str) == Some(attempt_id)
                && identity
                    .get("attempt_request_digest")
                    .and_then(Value::as_str)
                    == Some(attempt_request_digest)
                && archive
                    .get("prepared_generation_id")
                    .and_then(Value::as_str)
                    == Some(prepared_generation_id)
                && archive.get("attempt_id").and_then(Value::as_str) == Some(attempt_id)
                && archive
                    .get("attempt_request_digest")
                    .and_then(Value::as_str)
                    == Some(attempt_request_digest)
                && archive.get("archive_sha256").and_then(Value::as_str) == Some(archive_sha256)
                && archive.get("archive_byte_count").and_then(Value::as_u64)
                    == Some(*archive_byte_count)
                && archive
                    .get("semantic_manifest_sha256")
                    .and_then(Value::as_str)
                    == Some(expected_manifest)
                && semantic_manifest_sha256.as_deref() == Some(expected_manifest)
        }
    }
}

fn verify_post_grant(
    config: &ServiceConfig,
    request: &ValidatedRequest,
    reference: &GrantReference,
    grant_root: &Path,
    manifest: &PostGrantManifest,
) -> Result<VerifiedGrant, String> {
    if request.phase != "post_submit"
        || manifest.protocol_version != POST_GRANT_PROTOCOL
        || manifest.grant_id != reference.grant_id
        || manifest.request_digest != request.request_digest
        || manifest.binding_digest != reference.binding_digest
        || manifest.phase != "post_submit"
        || manifest.identity != request.value["identity"]
        || manifest.evaluation_context_sha256 != request.evaluation_context_sha256
        || manifest.visible_roles != request.post_material_roles
    {
        return Err("POST grant binding differs".into());
    }
    let requested = request
        .value
        .get("materials")
        .and_then(Value::as_array)
        .ok_or("request materials missing")?;
    if requested.len() != manifest.visible_roles.len() || manifest.materials.is_empty() {
        return Err("POST grant material selection differs".into());
    }
    let mut available = std::collections::BTreeMap::new();
    let mut available_roles = Vec::with_capacity(manifest.materials.len());
    for item in &manifest.materials {
        let role = validate_post_grant_material(item)?;
        available_roles.push(role);
        if available.insert(role.to_owned(), item).is_some() {
            return Err("POST grant material role duplicated".into());
        }
    }
    if !matches!(
        available_roles.as_slice(),
        [CURRENT_ARCHIVE_ROLE] | [CURRENT_ARCHIVE_ROLE, PREDECESSOR_ARCHIVE_ROLE]
    ) || !available.contains_key(CURRENT_ARCHIVE_ROLE)
        || available.len() > 2
        || !manifest
            .visible_roles
            .iter()
            .all(|role| available.contains_key(role))
    {
        return Err("POST grant material roles invalid".into());
    }
    if let Some(prior) = available.get(PREDECESSOR_ARCHIVE_ROLE) {
        let actual = prior
            .material
            .as_object()
            .ok_or("POST grant predecessor material invalid")?;
        let current = available[CURRENT_ARCHIVE_ROLE]
            .material
            .as_object()
            .ok_or("POST grant current material invalid")?;
        if actual.get("submission_id") == current.get("submission_id")
            || actual
                .get("submission_version")
                .and_then(Value::as_u64)
                .and_then(|version| version.checked_add(1))
                != current.get("submission_version").and_then(Value::as_u64)
        {
            return Err("POST grant predecessor lineage differs".into());
        }
        if manifest
            .visible_roles
            .iter()
            .any(|role| role == PREDECESSOR_ARCHIVE_ROLE)
        {
            let expected = request
                .value
                .pointer("/input/evaluation_context/predecessor")
                .and_then(Value::as_object)
                .ok_or("POST grant predecessor context missing")?;
            if [
                "submission_id",
                "submission_version",
                "content_sha256",
                "byte_count",
                "semantic_manifest_sha256",
            ]
            .iter()
            .any(|field| actual.get(*field) != expected.get(*field))
            {
                return Err("POST grant predecessor context differs".into());
            }
        }
    }
    for material in requested {
        let role = material
            .get("role")
            .and_then(Value::as_str)
            .ok_or("request material role missing")?;
        if available.get(role).map(|item| &item.material) != Some(material) {
            return Err("POST grant visible material differs".into());
        }
    }
    let materials_root = grant_root.join("materials");
    verify_materials_root(
        &materials_root,
        available.keys().map(String::as_str),
        config.sandbox_uid,
        config.sandbox_gid,
    )?;
    let mut inventories = std::collections::BTreeMap::new();
    for (role, item) in &available {
        let root = materials_root.join(role);
        let observed = inspect_workspace(&root, config.sandbox_uid, config.sandbox_gid)?;
        if observed.files != item.files || observed.directories != item.directories {
            return Err("POST grant material inventory differs".into());
        }
        inventories.insert(role.to_owned(), observed);
    }
    let input = materials_root.join(CURRENT_ARCHIVE_ROLE);
    let input_inventory = inventories
        .remove(CURRENT_ARCHIVE_ROLE)
        .ok_or("POST grant current inventory missing")?;
    let predecessor = manifest
        .visible_roles
        .iter()
        .any(|role| role == PREDECESSOR_ARCHIVE_ROLE)
        .then(|| materials_root.join(PREDECESSOR_ARCHIVE_ROLE));
    let predecessor_inventory = predecessor
        .as_ref()
        .and_then(|_| inventories.remove(PREDECESSOR_ARCHIVE_ROLE));
    if predecessor.is_some() != predecessor_inventory.is_some() {
        return Err("POST grant predecessor inventory missing".into());
    }
    Ok(VerifiedGrant {
        binding_digest: reference.binding_digest.clone(),
        input,
        input_inventory,
        predecessor,
        predecessor_inventory,
    })
}

fn validate_post_grant_material(item: &PostGrantMaterial) -> Result<&str, String> {
    let material = item
        .material
        .as_object()
        .ok_or("POST grant material invalid")?;
    let expected: std::collections::BTreeSet<_> = [
        "phase",
        "role",
        "submission_id",
        "submission_version",
        "binding_id",
        "content_id",
        "replica_id",
        "content_sha256",
        "byte_count",
        "media_type",
        "evidence_id",
        "verification_receipt_id",
        "verification_job_id",
        "verification_generation",
        "namespace_fingerprint",
        "semantic_manifest_sha256",
    ]
    .into_iter()
    .collect();
    if material
        .keys()
        .map(String::as_str)
        .collect::<std::collections::BTreeSet<_>>()
        != expected
        || material.get("phase").and_then(Value::as_str) != Some("post_submit")
    {
        return Err("POST grant material invalid".into());
    }
    let role = material
        .get("role")
        .and_then(Value::as_str)
        .ok_or("POST grant material role invalid")?;
    if !matches!(role, CURRENT_ARCHIVE_ROLE | PREDECESSOR_ARCHIVE_ROLE)
        || material.get("submission_version").and_then(Value::as_u64) == Some(0)
        || material
            .get("verification_generation")
            .and_then(Value::as_u64)
            == Some(0)
        || !material
            .get("byte_count")
            .and_then(Value::as_u64)
            .is_some_and(|value| value <= i64::MAX as u64)
        || !material
            .get("media_type")
            .and_then(Value::as_str)
            .is_some_and(|value| value.contains('/'))
    {
        return Err("POST grant material invalid".into());
    }
    for field in [
        "submission_id",
        "binding_id",
        "content_id",
        "replica_id",
        "evidence_id",
        "verification_receipt_id",
        "verification_job_id",
    ] {
        if !material
            .get(field)
            .and_then(Value::as_str)
            .is_some_and(|value| !value.is_empty())
        {
            return Err("POST grant material identity invalid".into());
        }
    }
    for field in [
        "content_sha256",
        "namespace_fingerprint",
        "semantic_manifest_sha256",
    ] {
        if !material
            .get(field)
            .and_then(Value::as_str)
            .is_some_and(valid_digest)
        {
            return Err("POST grant material digest invalid".into());
        }
    }
    if semantic_manifest_hash_parts(&item.directories, &item.files)
        .ok()
        .as_deref()
        != material
            .get("semantic_manifest_sha256")
            .and_then(Value::as_str)
    {
        return Err("POST grant semantic manifest differs".into());
    }
    Ok(role)
}

fn verify_materials_root<'a>(
    root: &Path,
    expected_roles: impl Iterator<Item = &'a str>,
    expected_uid: u32,
    expected_gid: u32,
) -> Result<(), String> {
    if fs::canonicalize(root).map_err(|_| "POST grant materials missing")? != root {
        return Err("POST grant materials path differs".into());
    }
    let metadata = fs::symlink_metadata(root).map_err(|_| "POST grant materials missing")?;
    if !metadata.file_type().is_dir()
        || metadata.file_type().is_symlink()
        || metadata.mode() & 0o077 != 0
        || metadata.uid() != expected_uid
        || metadata.gid() != expected_gid
    {
        return Err("POST grant materials identity differs".into());
    }
    let expected: std::collections::BTreeSet<_> = expected_roles.collect();
    let actual: std::collections::BTreeSet<_> = fs::read_dir(root)
        .map_err(|_| "POST grant materials unreadable")?
        .map(|entry| {
            entry
                .map_err(|_| "POST grant materials unreadable".to_owned())?
                .file_name()
                .into_string()
                .map_err(|_| "POST grant material role invalid".to_owned())
        })
        .collect::<Result<Vec<_>, _>>()?
        .into_iter()
        .collect();
    if actual
        .iter()
        .map(String::as_str)
        .collect::<std::collections::BTreeSet<_>>()
        != expected
    {
        return Err("POST grant material roots differ".into());
    }
    Ok(())
}

fn semantic_manifest_hash(manifest: &GrantManifest) -> Result<String, String> {
    semantic_manifest_hash_parts(&manifest.directories, &manifest.files)
}

fn semantic_manifest_hash_parts(
    directories: &[String],
    files: &[GrantFile],
) -> Result<String, String> {
    let mut entries = Vec::with_capacity(directories.len() + files.len());
    for path in directories {
        entries.push(serde_json::json!({
            "normalized_path": path,
            "entry_type": "directory",
        }));
    }
    for file in files {
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
    client: &UnixStream,
    budget: &mut RequestExecutionBudget,
) -> Result<(), String> {
    if config.runtime == "smolvm" {
        return smol::inspect_image(cache);
    }
    let reference = format!("{}@{}", cache.repository, cache.platform_manifest_digest);
    let output = run_bounded_command_cancellable(
        &config.docker_binary,
        &["image", "inspect", "--format", "{{json .}}", &reference],
        budget.deadline,
        budget.output.remaining,
        client,
        &mut budget.cleanup,
    )
    .map_err(|_| "image inspect unavailable")?;
    budget.output.charge(&output)?;
    validate_inspected_image(cache, &output)
}

fn validate_inspected_image(
    cache: &CacheEntry,
    output: &BoundedCommandOutput,
) -> Result<(), String> {
    let reference = format!("{}@{}", cache.repository, cache.platform_manifest_digest);
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
    grant: &VerifiedGrant,
    model_grant: Option<&ModelGrant>,
    client: &UnixStream,
    budget: &mut RequestExecutionBudget,
) -> Result<ExecutedChecker, ExecutionFailure> {
    container_owner(config)
        .map_err(|_| ExecutionFailure::ordinary("implementation_unavailable", false))?;
    let selected_trial = match config.trial_profiles.as_ref() {
        Some(catalog) => catalog
            .resolve(request)
            .map_err(|_| ExecutionFailure::ordinary("implementation_unavailable", false))?,
        None => {
            let has_trial_selector = request
                .value
                .get("configuration")
                .and_then(Value::as_object)
                .is_some_and(|configuration| {
                    configuration.keys().any(|key| key.starts_with("trial_"))
                });
            if has_trial_selector {
                return Err(ExecutionFailure::ordinary(
                    "implementation_unavailable",
                    false,
                ));
            }
            None
        }
    };
    let receipt_registry = Arc::new(InvocationReceiptRegistry::default());
    let invocation_cancelled = Arc::new(std::sync::atomic::AtomicBool::new(false));
    let mut trial_relay =
        match selected_trial {
            Some(profile) => {
                let runtime = config.trial_runtime.as_ref().ok_or_else(|| {
                    ExecutionFailure::ordinary("implementation_unavailable", false)
                })?;
                let proxy_path = config.model_proxy_socket.as_ref().ok_or_else(|| {
                    ExecutionFailure::ordinary("implementation_unavailable", false)
                })?;
                let identity = trial_request_identity(request, &grant.binding_digest)
                    .map_err(|_| ExecutionFailure::ordinary("implementation_unavailable", false))?;
                let engine = trial_engine(config, request, profile)
                    .map_err(|_| ExecutionFailure::ordinary("implementation_unavailable", false))?;
                let publisher = DurableTrialReceiptPublisher::new(
                    TrialEvidenceProxyClient::new(proxy_path.clone(), request.value.clone()),
                    Arc::clone(&receipt_registry),
                    request.request_digest.clone(),
                    profile.maximum_receipt_bytes,
                    budget.deadline,
                    Arc::clone(&invocation_cancelled),
                )
                .map_err(|_| ExecutionFailure::ordinary("implementation_unavailable", false))?;
                let material_root = grant
                    .input
                    .parent()
                    .ok_or_else(|| ExecutionFailure::ordinary("material_unavailable", false))?;
                Some(
                    TrialRelay::start(
                        &runtime.relay_root,
                        material_root,
                        &runtime.scratch_root,
                        &identity,
                        profile,
                        Arc::new(publisher),
                        engine,
                        config.sandbox_uid,
                        config.sandbox_gid,
                        budget.deadline,
                        Arc::clone(&invocation_cancelled),
                    )
                    .map_err(|failure| {
                        if failure.cleanup_unsettled {
                            ExecutionFailure::unsettled(false)
                        } else {
                            ExecutionFailure::ordinary("implementation_unavailable", false)
                        }
                    })?,
                )
            }
            None => None,
        };
    let model_relay = match model_grant {
        Some(grant) => {
            let Some(proxy_path) = config.model_proxy_socket.as_deref() else {
                return Err(ExecutionFailure::ordinary(
                    "implementation_unavailable",
                    false,
                ));
            };
            let Some(relay_root) = config.model_relay_root.as_deref() else {
                return Err(ExecutionFailure::ordinary(
                    "implementation_unavailable",
                    false,
                ));
            };
            match InvocationRelay::start_with_resolver(
                relay_root,
                proxy_path,
                grant,
                &request.request_digest,
                Arc::clone(&receipt_registry) as Arc<dyn ModelReceiptResolver>,
                config.sandbox_uid,
                config.sandbox_gid,
                budget.deadline,
            ) {
                Ok(relay) => Some(relay),
                Err(failure) => {
                    let trial_cleanup_unsettled = trial_relay
                        .take()
                        .is_some_and(|relay| relay.finish().cleanup_unsettled);
                    return Err(if failure.cleanup_unsettled || trial_cleanup_unsettled {
                        ExecutionFailure::unsettled(false)
                    } else {
                        ExecutionFailure::ordinary("implementation_unavailable", false)
                    });
                }
            }
        }
        None => None,
    };
    let model_mount = model_relay.as_ref().map(InvocationRelay::mount_spec);
    let trial_mount = trial_relay.as_ref().map(TrialRelay::mount_spec);
    let result = execute_container_inner(
        config,
        cache,
        request,
        grant,
        model_mount.as_deref(),
        trial_mount.as_deref(),
        client,
        budget,
    );
    let launched = match &result {
        Ok(_) => true,
        Err(failure) => failure.launched,
    };
    let model_finish = model_relay.map(InvocationRelay::finish);
    let trial_finish = trial_relay.map(TrialRelay::finish);
    if model_finish
        .as_ref()
        .is_some_and(|finish| finish.cleanup_unsettled)
        || trial_finish
            .as_ref()
            .is_some_and(|finish| finish.cleanup_unsettled)
    {
        return Err(ExecutionFailure::unsettled(launched));
    }
    if model_finish.as_ref().is_some_and(|finish| finish.failed)
        || trial_finish
            .as_ref()
            .is_some_and(|finish| finish.failure.is_some())
    {
        return Err(ExecutionFailure::ordinary(
            "implementation_unavailable",
            launched,
        ));
    }
    result
}

fn execute_container_inner(
    config: &ServiceConfig,
    cache: &CacheEntry,
    request: &ValidatedRequest,
    grant: &VerifiedGrant,
    model_mount: Option<&str>,
    trial_mount: Option<&str>,
    client: &UnixStream,
    budget: &mut RequestExecutionBudget,
) -> Result<ExecutedChecker, ExecutionFailure> {
    let owner = container_owner(config)
        .map_err(|_| ExecutionFailure::ordinary("implementation_unavailable", false))?;
    // Revalidate immediately before handing the path to Docker.
    let observed_input = inspect_workspace(&grant.input, config.sandbox_uid, config.sandbox_gid)
        .map_err(|_| ExecutionFailure::ordinary("material_unavailable", false))?;
    if observed_input != grant.input_inventory {
        return Err(ExecutionFailure::ordinary("material_unavailable", false));
    }
    if config.runtime == "smolvm" {
        if grant.predecessor.is_some() || model_mount.is_some() || trial_mount.is_some() {
            return Err(ExecutionFailure::ordinary(
                "implementation_unavailable",
                false,
            ));
        }
        return smol::execute(config, cache, request, &grant.input, client, budget);
    }
    if let (Some(predecessor), Some(expected)) = (&grant.predecessor, &grant.predecessor_inventory)
    {
        let observed = inspect_workspace(predecessor, config.sandbox_uid, config.sandbox_gid)
            .map_err(|_| ExecutionFailure::ordinary("material_unavailable", false))?;
        if observed != *expected {
            return Err(ExecutionFailure::ordinary("material_unavailable", false));
        }
    } else if grant.predecessor.is_some() || grant.predecessor_inventory.is_some() {
        return Err(ExecutionFailure::ordinary("material_unavailable", false));
    }
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|_| ExecutionFailure::ordinary("implementation_unavailable", false))?
        .as_nanos();
    let name = format!("ws-checker-{owner}-{nonce:x}");
    let owner_label = format!("workstream.external-checker-owner={owner}");
    let attempt_label = format!("workstream.external-checker-attempt={nonce:x}");
    let image = format!("{}@{}", cache.repository, cache.platform_manifest_digest);
    let sandbox_user = format!("{}:{}", config.sandbox_uid, config.sandbox_gid);
    let cpus = format!("{:.3}", request.cpu_millis as f64 / 1000.0);
    let memory = request.memory_bytes.to_string();
    let pids = ((request.memory_bytes / (16 * 1024 * 1024)).clamp(16, 256)).to_string();
    let input_mount = format!(
        "type=bind,src={},dst=/work/input,readonly",
        grant.input.display()
    );
    let predecessor_mount = grant.predecessor.as_ref().map(|path| {
        format!(
            "type=bind,src={},dst=/work/context/predecessor,readonly",
            path.display()
        )
    });
    let create_arguments = container_create_arguments(
        &name,
        &attempt_label,
        &owner_label,
        &config.runtime,
        &sandbox_user,
        &pids,
        &memory,
        &cpus,
        &input_mount,
        predecessor_mount.as_deref(),
        model_mount,
        trial_mount,
        &image,
    );
    let create_argument_refs: Vec<_> = create_arguments.iter().map(String::as_str).collect();
    let created = match run_bounded_command_cancellable(
        &config.docker_binary,
        &create_argument_refs,
        budget.deadline,
        budget.output.remaining,
        client,
        &mut budget.cleanup,
    ) {
        Ok(output) => output,
        Err(error) => {
            if !remove_container_cleanup(config, &name, &mut budget.cleanup) {
                return Err(ExecutionFailure::unsettled(false));
            }
            return Err(ExecutionFailure::ordinary(
                if error == "process deadline exceeded" {
                    "deadline_exceeded"
                } else {
                    "implementation_unavailable"
                },
                false,
            ));
        }
    };
    if budget.output.charge(&created).is_err() {
        return if remove_container_cleanup(config, &name, &mut budget.cleanup) {
            Err(ExecutionFailure::ordinary("invalid_output", false))
        } else {
            Err(ExecutionFailure::unsettled(false))
        };
    }
    if !created.status.success() {
        if !remove_container_cleanup(config, &name, &mut budget.cleanup) {
            return Err(ExecutionFailure::unsettled(false));
        }
        return Err(ExecutionFailure::ordinary(
            "implementation_unavailable",
            false,
        ));
    }
    let result = run_started_container(
        config,
        &name,
        request,
        client,
        budget.deadline,
        &mut budget.output,
        &mut budget.cleanup,
    );
    match remove_container_work(
        config,
        &name,
        client,
        budget.deadline,
        &mut budget.output,
        &mut budget.cleanup,
    ) {
        RemovalOutcome::Confirmed => {}
        RemovalOutcome::Recovered => {
            return Err(ExecutionFailure::ordinary(
                "implementation_unavailable",
                true,
            ));
        }
        RemovalOutcome::Unsettled => return Err(ExecutionFailure::unsettled(true)),
    }
    result.map_err(|code| ExecutionFailure::ordinary(code, true))
}

#[allow(clippy::too_many_arguments)]
fn container_create_arguments(
    name: &str,
    attempt_label: &str,
    owner_label: &str,
    runtime: &str,
    sandbox_user: &str,
    pids: &str,
    memory: &str,
    cpus: &str,
    material_mount: &str,
    predecessor_mount: Option<&str>,
    model_mount: Option<&str>,
    trial_mount: Option<&str>,
    image: &str,
) -> Vec<String> {
    let mut arguments = vec![
        "create".to_string(),
        "--name".into(),
        name.into(),
        "--label".into(),
        "workstream.external-checker=true".into(),
        "--label".into(),
        attempt_label.into(),
        "--label".into(),
        owner_label.into(),
        "--runtime".into(),
        runtime.into(),
        "--network".into(),
        "none".into(),
        "--read-only".into(),
        "--user".into(),
        sandbox_user.into(),
        "--cap-drop".into(),
        "ALL".into(),
        "--security-opt".into(),
        "no-new-privileges".into(),
        "--pids-limit".into(),
        pids.into(),
        "--memory".into(),
        memory.into(),
        "--cpus".into(),
        cpus.into(),
        "--tmpfs".into(),
        "/tmp:rw,noexec,nosuid,nodev,size=16777216".into(),
        "--mount".into(),
        material_mount.into(),
    ];
    if let Some(predecessor_mount) = predecessor_mount {
        arguments.push("--mount".into());
        arguments.push(predecessor_mount.into());
    }
    if let Some(model_mount) = model_mount {
        arguments.push("--mount".into());
        arguments.push(model_mount.into());
    }
    if let Some(trial_mount) = trial_mount {
        arguments.push("--mount".into());
        arguments.push(trial_mount.into());
    }
    arguments.extend(["-i".into(), image.into()]);
    arguments
}

fn remove_container_work(
    config: &ServiceConfig,
    name: &str,
    client: &UnixStream,
    deadline: Instant,
    output_meter: &mut OutputMeter,
    cleanup: &mut EmergencyCleanupBudget,
) -> RemovalOutcome {
    let removed = run_bounded_command_cancellable(
        &config.docker_binary,
        &["rm", "-f", name],
        deadline,
        output_meter.remaining,
        client,
        cleanup,
    );
    let Ok(removed) = removed else {
        return removal_recovery(config, name, cleanup);
    };
    if output_meter.charge(&removed).is_err() {
        return removal_recovery(config, name, cleanup);
    }
    let filter = format!("name=^/{name}$");
    let inventory = run_bounded_command_cancellable(
        &config.docker_binary,
        &[
            "container",
            "ls",
            "--all",
            "--quiet",
            "--no-trunc",
            "--filter",
            &filter,
        ],
        deadline,
        output_meter.remaining,
        client,
        cleanup,
    );
    let Ok(inventory) = inventory else {
        return removal_recovery(config, name, cleanup);
    };
    if output_meter.charge(&inventory).is_err() || !successful_empty_inventory(&inventory) {
        return removal_recovery(config, name, cleanup);
    }
    RemovalOutcome::Confirmed
}

fn removal_recovery(
    config: &ServiceConfig,
    name: &str,
    cleanup: &mut EmergencyCleanupBudget,
) -> RemovalOutcome {
    if remove_container_cleanup(config, name, cleanup) {
        RemovalOutcome::Recovered
    } else {
        RemovalOutcome::Unsettled
    }
}

fn remove_container_cleanup(
    config: &ServiceConfig,
    name: &str,
    cleanup: &mut EmergencyCleanupBudget,
) -> bool {
    let deadline = cleanup.deadline();
    let removed = run_bounded_command(
        &config.docker_binary,
        &["rm", "-f", name],
        deadline,
        cleanup.remaining_output,
    );
    let Ok(removed) = removed else {
        return false;
    };
    if cleanup.charge(&removed).is_err() {
        return false;
    }
    let filter = format!("name=^/{name}$");
    let inventory = run_bounded_command(
        &config.docker_binary,
        &[
            "container",
            "ls",
            "--all",
            "--quiet",
            "--no-trunc",
            "--filter",
            &filter,
        ],
        deadline,
        cleanup.remaining_output,
    );
    matches!(inventory, Ok(output) if cleanup.charge(&output).is_ok() && successful_empty_inventory(&output))
}

fn successful_empty_inventory(output: &BoundedCommandOutput) -> bool {
    output.status.success() && output.stdout.iter().all(u8::is_ascii_whitespace)
}

fn cleanup_stale_checker_containers(config: &ServiceConfig) -> Result<(), String> {
    let owner = container_owner(config)?;
    let owner_filter = format!("label=workstream.external-checker-owner={owner}");
    let deadline = Instant::now() + CLEANUP_TIMEOUT;
    let listed = run_bounded_command(
        &config.docker_binary,
        &[
            "container",
            "ls",
            "--all",
            "--quiet",
            "--no-trunc",
            "--filter",
            "label=workstream.external-checker=true",
            "--filter",
            &owner_filter,
        ],
        deadline,
        1024 * 1024,
    )
    .map_err(|_| "external checker container recovery unavailable")?;
    if !listed.status.success() {
        return Err("external checker container recovery unavailable".into());
    }
    let ids = String::from_utf8(listed.stdout)
        .map_err(|_| "external checker container recovery invalid")?;
    for id in ids.lines().filter(|line| !line.is_empty()) {
        if !valid_full_container_id(id) {
            return Err("external checker container recovery invalid".into());
        }
        let inspected = run_bounded_command(
            &config.docker_binary,
            &["container", "inspect", id],
            deadline,
            1024 * 1024,
        )
        .map_err(|_| "external checker container recovery unavailable")?;
        if !inspected.status.success() || !owned_checker_container(&inspected.stdout, id, owner) {
            return Err("external checker container recovery identity differs".into());
        }
        if !remove_container_until(config, id, deadline) {
            return Err("external checker container recovery failed".into());
        }
    }
    Ok(())
}

fn valid_full_container_id(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
}

fn owned_checker_container(bytes: &[u8], id: &str, owner: &str) -> bool {
    let Ok(value) = serde_json::from_slice::<Value>(bytes) else {
        return false;
    };
    let Some(containers) = value.as_array().filter(|items| items.len() == 1) else {
        return false;
    };
    let container = &containers[0];
    let prefix = format!("/ws-checker-{owner}-");
    let Some(attempt) = container
        .get("Name")
        .and_then(Value::as_str)
        .and_then(|name| name.strip_prefix(&prefix))
        .filter(|attempt| {
            !attempt.is_empty()
                && attempt.len() <= 32
                && attempt
                    .bytes()
                    .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
        })
    else {
        return false;
    };
    container.get("Id").and_then(Value::as_str) == Some(id)
        && container
            .pointer("/Config/Labels/workstream.external-checker-owner")
            .and_then(Value::as_str)
            == Some(owner)
        && container
            .pointer("/Config/Labels/workstream.external-checker")
            .and_then(Value::as_str)
            == Some("true")
        && container
            .pointer("/Config/Labels/workstream.external-checker-attempt")
            .and_then(Value::as_str)
            == Some(attempt)
}

fn remove_container_until(config: &ServiceConfig, id: &str, deadline: Instant) -> bool {
    if Instant::now() >= deadline {
        return false;
    }
    if run_bounded_command(
        &config.docker_binary,
        &["rm", "-f", id],
        deadline,
        64 * 1024,
    )
    .is_err()
    {
        return false;
    }
    let filter = format!("id={id}");
    matches!(
        run_bounded_command(
            &config.docker_binary,
            &[
                "container",
                "ls",
                "--all",
                "--quiet",
                "--no-trunc",
                "--filter",
                &filter,
            ],
            deadline,
            64 * 1024,
        ),
        Ok(output) if successful_empty_inventory(&output)
    )
}

impl ExecutionFailure {
    fn ordinary(code: &'static str, launched: bool) -> Self {
        Self {
            code,
            launched,
            cleanup_unsettled: false,
        }
    }

    fn unsettled(launched: bool) -> Self {
        Self {
            code: "implementation_unavailable",
            launched,
            cleanup_unsettled: true,
        }
    }
}

fn run_started_container(
    config: &ServiceConfig,
    name: &str,
    request: &ValidatedRequest,
    client: &UnixStream,
    deadline: Instant,
    output_meter: &mut OutputMeter,
    cleanup_budget: &mut EmergencyCleanupBudget,
) -> Result<ExecutedChecker, &'static str> {
    let payload = serde_json::to_vec(&request.value).map_err(|_| "invalid_output")?;
    let files = RuntimeFiles::new(config, name)?;
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
            terminate_container(config, name, &mut child, cleanup_budget);
            return Err("implementation_unavailable");
        }
    };
    if set_nonblocking(stdin.as_ref().unwrap()).is_err() {
        terminate_container(config, name, &mut child, cleanup_budget);
        return Err("implementation_unavailable");
    }
    let mut written = 0;
    let status = loop {
        if Instant::now() >= deadline {
            terminate_container(config, name, &mut child, cleanup_budget);
            return Err("deadline_exceeded");
        }
        if !client_is_connected(client) {
            terminate_container(config, name, &mut child, cleanup_budget);
            return Err("implementation_unavailable");
        }
        if written < payload.len() {
            match stdin.as_mut().unwrap().write(&payload[written..]) {
                Ok(0) => {
                    terminate_container(config, name, &mut child, cleanup_budget);
                    return Err("implementation_unavailable");
                }
                Ok(count) => written += count,
                Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {}
                Err(_) => {
                    terminate_container(config, name, &mut child, cleanup_budget);
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
                terminate_container(config, name, &mut child, cleanup_budget);
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
                terminate_container(config, name, &mut child, cleanup_budget);
                return Err("implementation_unavailable");
            }
        };
        if output_size.saturating_add(error_size) > output_meter.remaining as u64 {
            terminate_container(config, name, &mut child, cleanup_budget);
            return Err("invalid_output");
        }
        thread::sleep(Duration::from_millis(10));
    };
    stdin.take();
    if written != payload.len() {
        return Err("invalid_output");
    }
    let bytes =
        read_bounded_file(&files.output, output_meter.remaining).map_err(|_| "invalid_output")?;
    let error_bytes =
        read_bounded_file(&files.error, output_meter.remaining).map_err(|_| "invalid_output")?;
    output_meter
        .bytes(bytes.len().saturating_add(error_bytes.len()))
        .map_err(|_| "invalid_output")?;
    if !status.success() {
        return if container_was_oom_killed(
            config,
            name,
            client,
            deadline,
            output_meter,
            cleanup_budget,
        )? {
            Err("capacity_exceeded")
        } else {
            Err("invalid_output")
        };
    }
    if bytes.is_empty() {
        return Err("invalid_output");
    }
    let result: Value = serde_json::from_slice(&bytes).map_err(|_| "invalid_output")?;
    Ok(ExecutedChecker { value: result })
}

struct RuntimeFiles {
    output: PathBuf,
    error: PathBuf,
}

impl RuntimeFiles {
    fn new(config: &ServiceConfig, name: &str) -> Result<Self, &'static str> {
        let parent = config
            .socket_path
            .parent()
            .ok_or("implementation_unavailable")?;
        Ok(Self {
            output: parent.join(format!("{RUNTIME_FILE_PREFIX}{name}.stdout")),
            error: parent.join(format!("{RUNTIME_FILE_PREFIX}{name}.stderr")),
        })
    }
}

impl Drop for RuntimeFiles {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.output);
        let _ = fs::remove_file(&self.error);
    }
}

fn cleanup_stale_runtime_files(config: &ServiceConfig) -> Result<(), String> {
    let parent = config.socket_path.parent().ok_or("socket parent missing")?;
    for entry in fs::read_dir(parent).map_err(|_| "runtime directory unavailable")? {
        let entry = entry.map_err(|_| "runtime directory unavailable")?;
        let name = entry.file_name();
        let name = name.to_str().ok_or("runtime file name invalid")?;
        if !name.starts_with(RUNTIME_FILE_PREFIX)
            || !(name.ends_with(".stdout") || name.ends_with(".stderr"))
        {
            continue;
        }
        let kind = entry
            .file_type()
            .map_err(|_| "runtime file identity unavailable")?;
        if !kind.is_file() || kind.is_symlink() {
            return Err("runtime file identity invalid".into());
        }
        fs::remove_file(entry.path()).map_err(|_| "runtime file cleanup failed")?;
    }
    Ok(())
}

fn terminate_container(
    config: &ServiceConfig,
    name: &str,
    child: &mut std::process::Child,
    cleanup: &mut EmergencyCleanupBudget,
) {
    let cleanup_deadline = cleanup.deadline();
    if let Ok(output) = run_bounded_command(
        &config.docker_binary,
        &["kill", name],
        cleanup_deadline,
        cleanup.remaining_output,
    ) {
        let _ = cleanup.charge(&output);
    }
    if reap_child(child, Instant::now() + Duration::from_secs(1)).is_err() {
        let _ = stop_child(child, cleanup_deadline);
    }
}

fn container_was_oom_killed(
    config: &ServiceConfig,
    name: &str,
    client: &UnixStream,
    deadline: Instant,
    output_meter: &mut OutputMeter,
    cleanup: &mut EmergencyCleanupBudget,
) -> Result<bool, &'static str> {
    let output = run_bounded_command_cancellable(
        &config.docker_binary,
        &["inspect", "--format", "{{json .State.OOMKilled}}", name],
        deadline,
        output_meter.remaining,
        client,
        cleanup,
    )
    .map_err(|_| "implementation_unavailable")?;
    output_meter.charge(&output).map_err(|_| "invalid_output")?;
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

#[cfg(test)]
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

#[cfg(test)]
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

    pub(super) fn test_config() -> (PathBuf, ServiceConfig) {
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
        fs::write(
            &docker,
            b"#!/bin/sh\ncase \"$1 $2\" in\n  \"container ls\") exit 0;;\n  \"info --format\") printf '{\"runc\":{}}'; exit 0;;\nesac\nexit 2\n",
        )
        .unwrap();
        fs::set_permissions(&docker, fs::Permissions::from_mode(0o700)).unwrap();
        let owner = fs::metadata(&material_root).unwrap();
        let sandbox_uid = owner.uid();
        let sandbox_gid = owner.gid();
        let config = ServiceConfig {
            smol: None,
            smol_admission: None,
            container_owner: Some(
                load_container_owner(&File::open(&socket_root).unwrap()).unwrap(),
            ),
            socket_path: socket_root.join("checker.sock"),
            model_proxy_socket: None,
            model_relay_root: None,
            trial_authority_manifest_path: None,
            trial_authority_manifest_digest: None,
            trial_profiles: None,
            trial_runtime: None,
            trial_control: None,
            material_root,
            docker_binary: docker,
            runtime: "runc".into(),
            isolation_mode: "docker-dev".into(),
            operating_system: "linux".into(),
            architecture: "amd64".into(),
            sandbox_uid,
            sandbox_gid,
            cache: vec![CacheEntry {
                smol: None,
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
    fn trial_manifest_reader_rejects_growth_and_path_replacement() {
        let (root, _) = test_config();
        let path = root.join("trial-authority.json");
        fs::write(&path, b"{}").unwrap();
        assert_eq!(
            read_trial_authority_manifest_after_open(&path, || {
                let mut file = OpenOptions::new().append(true).open(&path).unwrap();
                file.write_all(b"x").unwrap();
            })
            .unwrap_err(),
            "trial authority manifest changed"
        );

        fs::write(&path, b"{}").unwrap();
        let replacement = root.join("replacement.json");
        fs::write(&replacement, b"{}").unwrap();
        assert_eq!(
            read_trial_authority_manifest_after_open(&path, || {
                fs::rename(&replacement, &path).unwrap();
            })
            .unwrap_err(),
            "trial authority manifest changed"
        );
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn trial_manifest_reader_rejects_fifo_without_blocking() {
        const CHILD_PATH: &str = "WORKSTREAM_TRIAL_MANIFEST_FIFO_CHILD";
        if let Some(path) = std::env::var_os(CHILD_PATH) {
            assert_eq!(
                read_trial_authority_manifest(Path::new(&path)).unwrap_err(),
                "trial authority manifest path invalid"
            );
            return;
        }

        use std::ffi::CString;
        use std::os::unix::ffi::OsStrExt;

        let (root, _) = test_config();
        let path = root.join("trial-authority.fifo");
        let path_bytes = CString::new(path.as_os_str().as_bytes()).unwrap();
        // SAFETY: the path is a NUL-free CString beneath this test's private root.
        assert_eq!(unsafe { libc::mkfifo(path_bytes.as_ptr(), 0o600) }, 0);
        let mut child = Command::new(std::env::current_exe().unwrap())
            .args([
                "--exact",
                "tests::trial_manifest_reader_rejects_fifo_without_blocking",
                "--nocapture",
            ])
            .env(CHILD_PATH, &path)
            .spawn()
            .unwrap();
        let deadline = Instant::now() + Duration::from_secs(2);
        let status = loop {
            if let Some(status) = child.try_wait().unwrap() {
                break status;
            }
            if Instant::now() >= deadline {
                child.kill().unwrap();
                let _ = child.wait();
                panic!("FIFO manifest read blocked");
            }
            thread::sleep(Duration::from_millis(10));
        };
        assert!(status.success());
        fs::remove_dir_all(root).unwrap();
    }

    fn pre_submit_envelope_with_grant(config: &ServiceConfig) -> Value {
        let grant_id = "extract_0123456789abcdef0123456789abcdef";
        let mut request: Value =
            serde_json::from_slice(include_bytes!("../../fixtures/request.json")).unwrap();
        let mut manifest = GrantManifest {
            protocol_version: PRE_GRANT_PROTOCOL.into(),
            grant_id: grant_id.into(),
            request_digest: String::new(),
            identity: GrantIdentity::PreSubmit {
                prepared_generation_id: request["identity"]["prepared_generation_id"]
                    .as_str()
                    .unwrap()
                    .into(),
                attempt_id: request["identity"]["attempt_id"].as_str().unwrap().into(),
                attempt_request_digest: request["identity"]["attempt_request_digest"]
                    .as_str()
                    .unwrap()
                    .into(),
                archive_sha256: request["materials"][0]["archive_sha256"]
                    .as_str()
                    .unwrap()
                    .into(),
                archive_byte_count: request["materials"][0]["archive_byte_count"]
                    .as_u64()
                    .unwrap(),
                semantic_manifest_sha256: String::new(),
            },
            directories: Vec::new(),
            files: Vec::new(),
            binding_digest: format!("sha256:{}", "0".repeat(64)),
        };
        let semantic = semantic_manifest_hash(&manifest).unwrap();
        let GrantIdentity::PreSubmit {
            semantic_manifest_sha256,
            ..
        } = &mut manifest.identity;
        *semantic_manifest_sha256 = semantic.clone();
        request["materials"][0]["semantic_manifest_sha256"] = Value::String(semantic);
        let mut request_body = request.as_object().unwrap().clone();
        request_body.remove("request_digest");
        let request_digest = canonical_hash(&Value::Object(request_body)).unwrap();
        request["request_digest"] = Value::String(request_digest.clone());
        manifest.request_digest = request_digest;

        let mut manifest_value = serde_json::to_value(&manifest).unwrap();
        manifest_value
            .as_object_mut()
            .unwrap()
            .remove("binding_digest");
        manifest.binding_digest = canonical_hash(&manifest_value).unwrap();

        let grants = config.material_root.join("workspaces");
        let grant_root = grants.join(grant_id);
        let workspace = grant_root.join("workspace");
        fs::create_dir(&grants).unwrap();
        fs::create_dir(&grant_root).unwrap();
        fs::create_dir(&workspace).unwrap();
        fs::set_permissions(&grant_root, fs::Permissions::from_mode(0o700)).unwrap();
        fs::set_permissions(&workspace, fs::Permissions::from_mode(0o500)).unwrap();
        let manifest_path = grant_root.join(".external-checker-grant.json");
        fs::write(&manifest_path, serde_json::to_vec(&manifest).unwrap()).unwrap();
        fs::set_permissions(&manifest_path, fs::Permissions::from_mode(0o400)).unwrap();

        serde_json::json!({
            "protocol_version": PROTOCOL,
            "operation": "execute",
            "request": request,
            "grant": {
                "grant_id": grant_id,
                "binding_digest": manifest.binding_digest,
            },
            "model_grant": null,
        })
    }

    #[test]
    fn runtime_files_use_socket_custody_and_stale_cleanup_never_touches_art() {
        let (root, config) = test_config();
        let material_marker = config.material_root.join("preserved-art-custody");
        fs::write(&material_marker, b"retained").unwrap();
        let socket_root = config.socket_path.parent().unwrap();

        let files = RuntimeFiles::new(&config, "owned").unwrap();
        assert_eq!(files.output.parent(), Some(socket_root));
        assert_eq!(files.error.parent(), Some(socket_root));
        assert_ne!(files.output.parent(), Some(config.material_root.as_path()));
        fs::write(&files.output, b"stdout").unwrap();
        fs::write(&files.error, b"stderr").unwrap();
        let output = files.output.clone();
        let error = files.error.clone();
        std::mem::forget(files);

        cleanup_stale_runtime_files(&config).unwrap();
        assert!(!output.exists());
        assert!(!error.exists());
        assert_eq!(fs::read(&material_marker).unwrap(), b"retained");

        let unrelated = socket_root.join("operator-owned");
        fs::write(&unrelated, b"preserved").unwrap();
        cleanup_stale_runtime_files(&config).unwrap();
        assert_eq!(fs::read(&unrelated).unwrap(), b"preserved");
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn socket_startup_recovers_only_a_stale_owned_socket() {
        let (root, config) = test_config();
        let stale = UnixListener::bind(&config.socket_path).unwrap();
        fs::set_permissions(&config.socket_path, fs::Permissions::from_mode(0o600)).unwrap();
        drop(stale);
        assert!(config.socket_path.exists());

        let owned = OwnedSocketListener::bind(&config.socket_path).unwrap();
        assert!(config.socket_path.exists());
        drop(owned);
        assert!(!config.socket_path.exists());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn socket_startup_preserves_live_and_foreign_paths() {
        let (root, config) = test_config();
        let live = UnixListener::bind(&config.socket_path).unwrap();
        fs::set_permissions(&config.socket_path, fs::Permissions::from_mode(0o600)).unwrap();
        assert_eq!(
            OwnedSocketListener::bind(&config.socket_path).unwrap_err(),
            "socket listener already active"
        );
        assert!(config.socket_path.exists());
        drop(live);
        fs::remove_file(&config.socket_path).unwrap();

        fs::write(&config.socket_path, b"foreign").unwrap();
        assert_eq!(
            OwnedSocketListener::bind(&config.socket_path).unwrap_err(),
            "socket path is not an owned socket"
        );
        assert_eq!(fs::read(&config.socket_path).unwrap(), b"foreign");
        fs::remove_file(&config.socket_path).unwrap();
        let target = config.socket_path.with_extension("target");
        fs::write(&target, b"foreign").unwrap();
        symlink(&target, &config.socket_path).unwrap();
        assert_eq!(
            OwnedSocketListener::bind(&config.socket_path).unwrap_err(),
            "socket path is not an owned socket"
        );
        assert!(fs::symlink_metadata(&config.socket_path)
            .unwrap()
            .file_type()
            .is_symlink());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn socket_parent_lock_serializes_startup_and_guard_preserves_substitution() {
        let (root, config) = test_config();
        let first = OwnedSocketListener::bind(&config.socket_path).unwrap();
        assert_eq!(
            OwnedSocketListener::bind(&config.socket_path).unwrap_err(),
            "socket custody unavailable"
        );
        fs::remove_file(&config.socket_path).unwrap();
        fs::write(&config.socket_path, b"replacement").unwrap();
        drop(first);
        assert_eq!(fs::read(&config.socket_path).unwrap(), b"replacement");
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn losing_full_startup_cannot_run_cleanup_under_the_live_owner() {
        let (root, mut config) = test_config();
        let first = prepare_listener(&mut config).unwrap();
        let socket_root = config.socket_path.parent().unwrap();
        let stale_runtime = socket_root.join(format!("{RUNTIME_FILE_PREFIX}loser.stdout"));
        fs::write(&stale_runtime, b"winner-owned").unwrap();
        let docker_marker = root.join("docker-called-by-loser");
        fs::write(
            &config.docker_binary,
            format!(
                "#!/bin/sh\ntouch {}\nprintf '{{\"runc\":{{}}}}'\n",
                docker_marker.display()
            ),
        )
        .unwrap();

        assert_eq!(
            prepare_listener(&mut config).unwrap_err(),
            "socket custody unavailable"
        );
        assert_eq!(fs::read(&stale_runtime).unwrap(), b"winner-owned");
        assert!(!docker_marker.exists());

        fs::remove_file(stale_runtime).unwrap();
        drop(first);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn losing_startup_cannot_recover_live_trial_resources() {
        let (root, mut config) = test_config();
        let proxy_root = root.join("proxy");
        let relay_root = root.join("relay");
        let runtime_root = root.join("trial-runtime");
        let trial_relay_root = root.join("trial-relay");
        let scratch_root = root.join("trial-scratch");
        let cache_root = root.join("offline-cache");
        for directory in [
            &proxy_root,
            &relay_root,
            &runtime_root,
            &trial_relay_root,
            &scratch_root,
            &cache_root,
        ] {
            fs::create_dir(directory).unwrap();
            fs::set_permissions(directory, fs::Permissions::from_mode(0o700)).unwrap();
        }
        let proxy_path = proxy_root.join("proxy.sock");
        let _proxy = UnixListener::bind(&proxy_path).unwrap();
        fs::set_permissions(&proxy_path, fs::Permissions::from_mode(0o600)).unwrap();
        let runtime_configuration = root.join("runsc-trial.toml");
        fs::write(&runtime_configuration, b"rootless = false\n").unwrap();
        fs::write(
            &config.docker_binary,
            b"#!/bin/sh\ncase \"$1 $2\" in\n  \"container ls\") exit 0;;\n  \"info --format\") printf '{\"runsc\":{}}'; exit 0;;\nesac\nexit 2\n",
        )
        .unwrap();
        config.runtime = "runsc".into();
        config.isolation_mode = "gvisor".into();
        config.model_proxy_socket = Some(proxy_path);
        config.model_relay_root = Some(relay_root);
        config.trial_profiles = Some(TrialProfileCatalog::empty_for_test());
        config.trial_runtime = Some(TrialRuntimeConfiguration {
            relay_root: trial_relay_root,
            scratch_root,
            runtime_root: runtime_root.clone(),
            runtime_configuration,
            outer_runtime_config_digest: format!("sha256:{}", "1".repeat(64)),
            offline_cache_root: cache_root,
            deployment_owner: "deployment_a".into(),
            runtime_key: "runsc-trial".into(),
            builder_image_id: format!("sha256:{}", "2".repeat(64)),
            trusted_launcher_path: config.docker_binary.clone(),
            trusted_launcher_digest: format!("sha256:{}", "3".repeat(64)),
            maximum_candidate_archive_bytes: 1024,
        });

        let first = prepare_listener(&mut config).unwrap();
        let first_control = config.trial_control.as_ref().unwrap().clone();
        let journal =
            trial_docker::persist_runtime_journal_for_test(&runtime_root, "deployment_a").unwrap();
        let journal_before = fs::read(&journal).unwrap();
        let live_resource = root.join("live-trial-resource");
        let docker_called = root.join("docker-called-by-loser");
        fs::write(&live_resource, b"live").unwrap();
        fs::write(
            &config.docker_binary,
            format!(
                "#!/bin/sh\ntouch '{}'\nrm -f '{}'\nexit 2\n",
                docker_called.display(),
                live_resource.display(),
            ),
        )
        .unwrap();

        assert_eq!(
            prepare_listener(&mut config).unwrap_err(),
            "socket custody unavailable"
        );
        assert!(Arc::ptr_eq(
            config.trial_control.as_ref().unwrap(),
            &first_control
        ));
        assert!(!docker_called.exists());
        assert_eq!(fs::read(&journal).unwrap(), journal_before);
        assert_eq!(fs::read(&live_resource).unwrap(), b"live");

        drop(first);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn owner_custody_is_stable_private_and_bounded() {
        let (root, config) = test_config();
        let (other_root, other) = test_config();
        let parent = File::open(config.socket_path.parent().unwrap()).unwrap();
        let path = config
            .socket_path
            .parent()
            .unwrap()
            .join(CONTAINER_OWNER_FILE);
        let original = container_owner(&config).unwrap();
        assert_eq!(load_container_owner(&parent).unwrap(), original);
        assert_ne!(original, container_owner(&other).unwrap());
        let listener = OwnedSocketListener::bind(&config.socket_path).unwrap();
        drop(listener);
        assert_eq!(load_container_owner(&parent).unwrap(), original);
        for bytes in [
            vec![],
            vec![b'a'; 63],
            vec![b'a'; 65],
            vec![b'A'; 64],
            vec![b'g'; 64],
        ] {
            fs::write(&path, bytes).unwrap();
            assert!(load_container_owner(&parent).is_err());
        }
        fs::write(&path, original).unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o644)).unwrap();
        assert!(load_container_owner(&parent).is_err());
        fs::set_permissions(&path, fs::Permissions::from_mode(0o600)).unwrap();
        let alias = root.join("alias");
        fs::hard_link(&path, &alias).unwrap();
        assert!(load_container_owner(&parent).is_err());
        fs::remove_file(&path).unwrap();
        symlink(&alias, &path).unwrap();
        assert!(load_container_owner(&parent).is_err());
        fs::remove_file(&path).unwrap();
        fs::create_dir(&path).unwrap();
        assert!(load_container_owner(&parent).is_err());
        fs::remove_dir(&path).unwrap();
        // Lost custody is never reconstructed from generic containers.
        assert_ne!(load_container_owner(&parent).unwrap(), original);
        fs::remove_dir_all(root).unwrap();
        fs::remove_dir_all(other_root).unwrap();
    }

    #[test]
    fn unsafe_owner_custody_stops_startup_before_docker() {
        use std::os::unix::fs::symlink;
        let (root, mut config) = test_config();
        let owner_path = config
            .socket_path
            .parent()
            .unwrap()
            .join(CONTAINER_OWNER_FILE);
        let marker = root.join("docker-called");
        fs::write(
            &config.docker_binary,
            format!("#!/bin/sh\ntouch '{}'\nexit 1\n", marker.display()),
        )
        .unwrap();
        fs::write(&owner_path, b"partial").unwrap();
        assert!(prepare_listener(&mut config).is_err());
        assert!(
            !marker.exists(),
            "unsafe owner allowed Docker startup calls"
        );
        fs::remove_file(&owner_path).unwrap();
        symlink(root.join("substituted-owner"), &owner_path).unwrap();
        assert!(prepare_listener(&mut config).is_err());
        assert!(
            !marker.exists(),
            "substituted owner allowed Docker startup calls"
        );
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn container_identity_requires_all_ownership_facts() {
        let id = "a".repeat(64);
        let owner = "b".repeat(64);
        let valid = serde_json::json!([{
            "Id": id, "Name": format!("/ws-checker-{owner}-c1"),
            "Config": {"Labels": {
                "workstream.external-checker": "true",
                "workstream.external-checker-owner": owner,
                "workstream.external-checker-attempt": "c1"
            }}
        }]);
        assert!(owned_checker_container(
            &serde_json::to_vec(&valid).unwrap(),
            &id,
            &owner
        ));
        for path in [
            "/0/Id",
            "/0/Name",
            "/0/Config/Labels/workstream.external-checker",
            "/0/Config/Labels/workstream.external-checker-owner",
            "/0/Config/Labels/workstream.external-checker-attempt",
        ] {
            for replacement in [Value::Null, Value::String("different".into())] {
                let mut bad = valid.clone();
                *bad.pointer_mut(path).unwrap() = replacement;
                assert!(
                    !owned_checker_container(&serde_json::to_vec(&bad).unwrap(), &id, &owner),
                    "{path}"
                );
            }
        }
        let (root, mut config) = test_config();
        config.container_owner = None;
        assert_eq!(
            cleanup_stale_checker_containers(&config).unwrap_err(),
            "container owner custody missing"
        );
        config.container_owner = Some(String::new());
        assert!(cleanup_stale_checker_containers(&config).is_err());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn startup_recovery_is_instance_scoped() {
        let (root, mut a) = test_config();
        let (b_root, mut b) = test_config();
        let live = prepare_listener(&mut a).unwrap();
        let a_owner = container_owner(&a).unwrap();
        let b_owner = container_owner(&b).unwrap().to_owned();
        let a_id = "a".repeat(64);
        let b_id = "b".repeat(64);
        let unowned = "c".repeat(64);
        for id in [&a_id, &b_id, &unowned] {
            fs::write(b_root.join(id), b"container").unwrap();
        }
        let script = format!(
            r#"#!/bin/sh
root='{root}'
case "$1 $2" in
 "info --format") printf '{{"runc":{{}}}}';;
 "container ls")
   for argument in "$@"; do
     case "$argument" in
       id=*) id="${{argument#id=}}"; test -e "$root/$id" && printf '%s\n' "$id"; exit 0;;
     esac
   done
   case "$*" in
    *'label=workstream.external-checker-owner={b_owner}'*) touch "$root/owner-filter"; test -e "$root/{b_id}" && printf '{b_id}\n';;
    *) printf '{a_id}\n{b_id}\n{unowned}\n';;
   esac; exit 0;;
 "container inspect")
   case "$3" in
    '{a_id}') owner='{a_owner}';;
    '{b_id}') owner='{b_owner}';;
    *) owner='';;
   esac
   name='/ws-checker-a1'
   test -e "$root/owner-filter" && name="/ws-checker-$owner-a1"
   printf '[{{"Id":"%s","Name":"%s","Config":{{"Labels":{{"workstream.external-checker":"true","workstream.external-checker-owner":"%s","workstream.external-checker-attempt":"a1"}}}}}}]' "$3" "$name" "$owner";;
 "rm -f") rm "$root/$3";;
 *) exit 2;;
esac
"#,
            root = b_root.display()
        );
        fs::write(&b.docker_binary, script).unwrap();
        let b_listener = prepare_listener(&mut b).unwrap();
        assert!(
            b_root.join(&a_id).exists(),
            "foreign active container was removed"
        );
        assert!(
            b_root.join(&unowned).exists(),
            "unowned container was removed"
        );
        assert!(
            !b_root.join(&b_id).exists(),
            "own stale container was not recovered"
        );
        drop(b_listener);
        let restarted = prepare_listener(&mut b).unwrap();
        assert_eq!(container_owner(&b).unwrap(), b_owner);
        drop(restarted);
        drop(live);
        fs::remove_dir_all(root).unwrap();
        fs::remove_dir_all(b_root).unwrap();
    }

    #[test]
    fn startup_recovery_requires_exact_container_identity_and_absence() {
        let (root, config) = test_config();
        let container = root.join("generic-container");
        let preserved = root.join("preserved");
        fs::write(&container, b"owned").unwrap();
        fs::write(&preserved, b"foreign").unwrap();
        let container_id = "a".repeat(64);
        fs::write(
            &config.docker_binary,
            format!(
                r#"#!/bin/sh
case "$1 $2" in
  "container ls") test -e "{container}" && printf '{container_id}\n'; exit 0;;
  "container inspect")
    printf '%s\n' '[{{"Id":"{container_id}","Name":"/ws-checker-{owner}-a1","Config":{{"Labels":{{"workstream.external-checker":"true","workstream.external-checker-owner":"{owner}","workstream.external-checker-attempt":"a1"}}}}}}]'
    exit 0;;
  "rm -f") rm -f "{container}"; exit 0;;
esac
exit 2
"#,
                container = container.display(),
                owner = container_owner(&config).unwrap(),
            ),
        )
        .unwrap();
        fs::set_permissions(&config.docker_binary, fs::Permissions::from_mode(0o700)).unwrap();

        cleanup_stale_checker_containers(&config).unwrap();
        assert!(!container.exists());
        assert_eq!(fs::read(&preserved).unwrap(), b"foreign");

        let mismatched = serde_json::to_vec(&serde_json::json!([{
            "Name": "/ws-checker-a1",
            "Config": {"Labels": {
                "workstream.external-checker": "true",
                "workstream.external-checker-attempt": "b2"
            }}
        }]))
        .unwrap();
        assert!(!owned_checker_container(
            &mismatched,
            &container_id,
            container_owner(&config).unwrap()
        ));

        fs::write(&container, b"ambiguous").unwrap();
        fs::write(
            &config.docker_binary,
            b"#!/bin/sh\ncase \"$1 $2\" in\n  \"rm -f\"|\"container ls\") exit 125;;\nesac\nexit 2\n",
        )
        .unwrap();
        assert!(!remove_container_until(
            &config,
            &container_id,
            Instant::now() + Duration::from_secs(2),
        ));
        assert!(container.exists());
        fs::remove_dir_all(root).unwrap();
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
            "model_grant": null,
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
    fn service_configuration_rejects_removed_project_profiles() {
        let mut configuration = serde_json::json!({
            "socket_path": "/tmp/checker.sock",
            "material_root": "/tmp/material",
            "docker_binary": "/usr/bin/docker",
            "runtime": "runsc",
            "isolation_mode": "gvisor",
            "operating_system": "linux",
            "architecture": "amd64",
            "sandbox_uid": 65532,
            "sandbox_gid": 65532,
            "cache": [],
        });
        assert!(serde_json::from_value::<ServiceConfig>(configuration.clone()).is_ok());
        configuration["terminal_benchmark"] = Value::Null;
        assert!(serde_json::from_value::<ServiceConfig>(configuration).is_err());
    }

    #[test]
    fn smol_configuration_rejects_the_unprojected_host_model_relay() {
        let (root, mut config) = test_config();
        config.runtime = "smolvm".into();
        config.isolation_mode = "smol-microvm".into();
        config.docker_binary = PathBuf::new();
        config.model_proxy_socket = Some(root.join("private/model-proxy.sock"));
        config.model_relay_root = Some(root.join("private/model-relays"));

        assert_eq!(
            validate_config(&config),
            Err("model relay configuration incomplete".into())
        );
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn execute_wire_requires_an_exact_model_grant_member() {
        let (root, config) = test_config();
        let envelope = pre_submit_envelope_with_grant(&config);
        assert!(serde_json::from_value::<ExecuteEnvelope>(envelope.clone()).is_ok());

        let mut missing = envelope.clone();
        missing.as_object_mut().unwrap().remove("model_grant");
        assert!(serde_json::from_value::<ExecuteEnvelope>(missing).is_err());

        let mut extended = envelope;
        extended["model_grant"] = serde_json::json!({
            "grant_id": format!("model_{}", "1".repeat(32)),
            "binding_digest": extended["request"]["request_digest"],
            "extra": true,
        });
        assert!(serde_json::from_value::<ExecuteEnvelope>(extended).is_err());
        let workspace = config
            .material_root
            .join("workspaces/extract_0123456789abcdef0123456789abcdef/workspace");
        fs::set_permissions(workspace, fs::Permissions::from_mode(0o700)).unwrap();
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn model_grants_are_rejected_outside_the_bound_post_request() {
        let (root, mut config) = test_config();
        config.model_proxy_socket = Some(PathBuf::from("/unused/private/proxy.sock"));
        config.model_relay_root = Some(PathBuf::from("/unused/private/relay"));
        let mut envelope = pre_submit_envelope_with_grant(&config);
        envelope["model_grant"] = serde_json::json!({
            "grant_id": format!("model_{}", "1".repeat(32)),
            "binding_digest": envelope["request"]["request_digest"],
        });
        let (_client, server) = UnixStream::pair().unwrap();
        assert_eq!(
            handle_frame(&config, &server, &serde_json::to_vec(&envelope).unwrap()),
            Err("model grant invalid".into())
        );

        let workspace = config
            .material_root
            .join("workspaces/extract_0123456789abcdef0123456789abcdef/workspace");
        fs::set_permissions(workspace, fs::Permissions::from_mode(0o700)).unwrap();
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn container_arguments_mount_only_the_invocation_capability_sockets() {
        let material = "type=bind,src=/private/material,dst=/work/input,readonly";
        let invocation =
            "type=bind,src=/private/runtime/.model-123/model.sock,dst=/work/model.sock,readonly";
        let trial = "type=bind,src=/private/runtime/.trial-123/execution.sock,dst=/work/execution.sock,readonly";
        let arguments = container_create_arguments(
            "candidate",
            "workstream.external-checker-attempt=a",
            "workstream.external-checker-owner=b",
            "runc",
            "65532:65532",
            "16",
            "16777216",
            "1.000",
            material,
            None,
            Some(invocation),
            Some(trial),
            "registry.example/checker@sha256:123",
        );
        assert!(arguments
            .windows(2)
            .any(|pair| pair == ["--network", "none"]));
        let mounts: Vec<_> = arguments
            .windows(2)
            .filter(|pair| pair[0] == "--mount")
            .map(|pair| pair[1].as_str())
            .collect();
        assert_eq!(mounts, [material, invocation, trial]);
        assert!(!arguments.iter().any(|value| {
            value.contains("proxy.sock")
                || value.contains("model_0123456789abcdef0123456789abcdef")
                || value.contains("provider")
                || value.contains("api_key")
        }));

        let without_model = container_create_arguments(
            "candidate",
            "workstream.external-checker-attempt=a",
            "workstream.external-checker-owner=b",
            "runc",
            "65532:65532",
            "16",
            "16777216",
            "1.000",
            material,
            None,
            None,
            None,
            "registry.example/checker@sha256:123",
        );
        assert_eq!(
            without_model
                .windows(2)
                .filter(|pair| pair[0] == "--mount")
                .map(|pair| pair[1].as_str())
                .collect::<Vec<_>>(),
            [material]
        );
    }

    #[test]
    fn checker_output_cannot_request_another_execution() {
        let (root, config) = test_config();
        let envelope = pre_submit_envelope_with_grant(&config);
        let request = parse_request(&serde_json::to_vec(&envelope["request"]).unwrap()).unwrap();
        let cache = &config.cache[0];
        fs::write(
            root.join("image.json"),
            serde_json::to_vec(&serde_json::json!({
                "Id": cache.config_image_id,
                "Os": cache.operating_system,
                "Architecture": cache.architecture,
                "RepoDigests": [format!("{}@{}", cache.repository, cache.platform_manifest_digest)],
            }))
            .unwrap(),
        )
        .unwrap();
        fs::write(
            &config.docker_binary,
            b"#!/bin/sh\nroot=$(dirname \"$0\")\nprintf '%s\\n' \"$1\" >> \"$root/calls\"\ncase \"$1 $2\" in\n  \"image inspect\") cat \"$root/image.json\";;\n  \"create --name\") exit 0;;\n  \"start -a\") cat >/dev/null; cat \"$root/result.json\";;\n  \"rm -f\"|\"container ls\") exit 0;;\n  *) exit 2;;\nesac\n",
        )
        .unwrap();
        let valid = workstream_checker_sdk::completed_result(&request, Vec::new()).unwrap();
        for (output, expected) in [
            (
                serde_json::json!({"schema_version": "project_private_plan.v1", "operation": "build"}),
                infrastructure_result(&request, "invalid_output").unwrap(),
            ),
            (valid.clone(), valid),
        ] {
            fs::write(root.join("calls"), b"").unwrap();
            fs::write(
                root.join("result.json"),
                serde_json::to_vec(&output).unwrap(),
            )
            .unwrap();
            let (mut client, mut server) = UnixStream::pair().unwrap();
            write_frame(&mut client, &serde_json::to_vec(&envelope).unwrap()).unwrap();
            let response: Value =
                serde_json::from_slice(&handle(&config, &mut server).unwrap()).unwrap();
            assert_eq!(response["result"], expected);
            assert!(!response["isolation"].is_null());
            let calls = fs::read_to_string(root.join("calls")).unwrap();
            assert_eq!(
                calls.lines().collect::<Vec<_>>(),
                ["image", "create", "start", "rm", "container"]
            );
        }
        fs::set_permissions(
            config
                .material_root
                .join("workspaces")
                .join(envelope["grant"]["grant_id"].as_str().unwrap())
                .join("workspace"),
            fs::Permissions::from_mode(0o700),
        )
        .unwrap();
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
        serve_connection(&config, stalled_server, Duration::from_millis(100)).unwrap();
        assert!(started.elapsed() < Duration::from_millis(300));

        let (mut client, server) = UnixStream::pair().unwrap();
        let request = serde_json::to_vec(
            &serde_json::json!({"protocol_version": PROTOCOL, "operation": "health"}),
        )
        .unwrap();
        write_frame(&mut client, &request).unwrap();
        serve_connection(&config, server, Duration::from_secs(1)).unwrap();
        let response = read_frame(&mut client, MAX_RESPONSE_BYTES).unwrap();
        assert_eq!(
            serde_json::from_slice::<Value>(&response).unwrap()["status"],
            "ready"
        );
        writer.join().unwrap();
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn unresolved_cleanup_closes_the_listener_loop_without_admitting_the_next_connection() {
        let (root, config) = test_config();
        let retained = root.join("retained-container");
        let second_admitted = root.join("second-admitted");
        let cache = &config.cache[0];
        fs::write(
            &config.docker_binary,
            format!(
                r#"#!/bin/sh
case "$1 $2" in
  "image inspect")
    printf '%s\n' '{{"Id":"{image_id}","Os":"{os}","Architecture":"{architecture}","RepoDigests":["{repository}@{manifest}"]}}'
    exit 0;;
  "create --name") : > "{retained}"; exit 17;;
  "rm -f"|"container ls") exit 125;;
  "info --format") : > "{second_admitted}"; printf '{{"runc":{{}}}}'; exit 0;;
esac
exit 2
"#,
                image_id = cache.config_image_id,
                os = cache.operating_system,
                architecture = cache.architecture,
                repository = cache.repository,
                manifest = cache.platform_manifest_digest,
                retained = retained.display(),
                second_admitted = second_admitted.display(),
            ),
        )
        .unwrap();
        fs::set_permissions(&config.docker_binary, fs::Permissions::from_mode(0o700)).unwrap();
        let execute = serde_json::to_vec(&pre_submit_envelope_with_grant(&config)).unwrap();
        let health = serde_json::to_vec(
            &serde_json::json!({"protocol_version": PROTOCOL, "operation": "health"}),
        )
        .unwrap();

        let listener_path = root.join("queued-connections.sock");
        let listener = UnixListener::bind(&listener_path).unwrap();
        let mut execute_client = UnixStream::connect(&listener_path).unwrap();
        let (execute_server, _) = listener.accept().unwrap();
        let mut health_client = UnixStream::connect(&listener_path).unwrap();
        let (health_server, _) = listener.accept().unwrap();
        write_frame(&mut execute_client, &execute).unwrap();
        write_frame(&mut health_client, &health).unwrap();
        for client in [&execute_client, &health_client] {
            client
                .set_read_timeout(Some(Duration::from_millis(100)))
                .unwrap();
        }

        let outcome = serve_connections(
            &config,
            vec![Ok(execute_server), Ok(health_server)],
            Duration::from_secs(2),
        );
        let retained_exists = retained.exists();
        let second_was_admitted = second_admitted.exists();
        let execute_received_no_frame =
            read_frame(&mut execute_client, MAX_RESPONSE_BYTES).is_err();
        let health_received_no_frame = read_frame(&mut health_client, MAX_RESPONSE_BYTES).is_err();

        drop(listener);
        fs::remove_file(listener_path).unwrap();
        let workspace = config
            .material_root
            .join("workspaces/extract_0123456789abcdef0123456789abcdef/workspace");
        fs::set_permissions(workspace, fs::Permissions::from_mode(0o700)).unwrap();
        fs::remove_dir_all(root).unwrap();

        assert_eq!(outcome, Err(UNSETTLED_RESOURCE_ERROR.into()));
        assert!(retained_exists);
        assert!(!second_was_admitted);
        assert!(execute_received_no_frame);
        assert!(health_received_no_frame);
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
        let mut output = OutputMeter::new(request.maximum_output_bytes);
        let mut cleanup = EmergencyCleanupBudget::new();
        assert_eq!(
            run_started_container(
                &config,
                "bounded-stdin",
                &request,
                &client,
                Instant::now() + Duration::from_millis(100),
                &mut output,
                &mut cleanup,
            ),
            Err("deadline_exceeded")
        );
        assert!(started.elapsed() < Duration::from_secs(4));

        request.deadline_ms = 30_000;
        let (peer, disconnected) = UnixStream::pair().unwrap();
        drop(peer);
        let started = Instant::now();
        let mut output = OutputMeter::new(request.maximum_output_bytes);
        let mut cleanup = EmergencyCleanupBudget::new();
        assert_eq!(
            run_started_container(
                &config,
                "disconnected",
                &request,
                &disconnected,
                Instant::now() + Duration::from_secs(30),
                &mut output,
                &mut cleanup,
            ),
            Err("implementation_unavailable")
        );
        assert!(started.elapsed() < Duration::from_secs(4));
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn blocking_control_command_stops_on_disconnect_and_reuses_cleanup_budget() {
        let (root, config) = test_config();
        let cli_pid = root.join("cli-pid");
        let container = root.join("container");
        fs::write(&container, b"live").unwrap();
        fs::write(
            &config.docker_binary,
            format!(
                r#"#!/bin/sh
root=$(dirname "$0")
case "$1 $2" in
  "start --attach") printf '%s' "$$" > "{cli_pid}"; while :; do :; done;;
  "rm -f") rm -f "{container}"; printf 'removed'; exit 0;;
  "container ls") test -e "{container}" && printf '%064d\n' 0; exit 0;;
esac
exit 2
"#,
                cli_pid = cli_pid.display(),
                container = container.display(),
            ),
        )
        .unwrap();
        fs::set_permissions(&config.docker_binary, fs::Permissions::from_mode(0o700)).unwrap();

        let (peer, client) = UnixStream::pair().unwrap();
        let pid_marker = cli_pid.clone();
        let disconnect = thread::spawn(move || {
            for _ in 0..200 {
                if pid_marker.exists() {
                    break;
                }
                thread::sleep(Duration::from_millis(5));
            }
            drop(peer);
        });
        let mut cleanup = EmergencyCleanupBudget::new();
        let started = Instant::now();
        let command_result = run_bounded_command_cancellable(
            &config.docker_binary,
            &["start", "--attach", "candidate"],
            Instant::now() + Duration::from_secs(30),
            1024,
            &client,
            &mut cleanup,
        );
        assert!(
            matches!(&command_result, Err(error) if error == "client disconnected"),
            "unexpected command error={:?}, status={:?}, pid_marker_exists={}, elapsed={:?}",
            command_result.as_ref().err(),
            command_result.as_ref().ok().map(|output| &output.status),
            cli_pid.exists(),
            started.elapsed()
        );
        disconnect.join().unwrap();
        assert!(started.elapsed() < Duration::from_secs(2));
        let pid: libc::pid_t = fs::read_to_string(&cli_pid).unwrap().parse().unwrap();
        // SAFETY: signal 0 only probes the recorded child PID after the bounded
        // command has reaped it.
        assert_eq!(unsafe { libc::kill(pid, 0) }, -1);

        let cleanup_deadline = cleanup.deadline();
        assert!(remove_container_cleanup(&config, "candidate", &mut cleanup));
        assert_eq!(cleanup.deadline, Some(cleanup_deadline));
        assert!(cleanup.remaining_output < CLEANUP_MAXIMUM_OUTPUT_BYTES);
        assert!(!container.exists());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn initial_container_create_output_consumes_the_request_meter() {
        let (root, config) = test_config();
        fs::write(
            &config.docker_binary,
            b"#!/bin/sh\nroot=$(dirname \"$0\")\ncase \"$1\" in\n  create) printf 'abcd'; exit 17;;\n  rm) rm -f \"$root/container\"; exit 0;;\n  container) exit 0;;\nesac\n",
        )
        .unwrap();
        fs::set_permissions(&config.docker_binary, fs::Permissions::from_mode(0o700)).unwrap();
        let workspace = config.material_root.join("workspace-meter");
        fs::create_dir(&workspace).unwrap();
        fs::set_permissions(&workspace, fs::Permissions::from_mode(0o500)).unwrap();
        let request = parse_request(include_bytes!("../../fixtures/request.json")).unwrap();
        let grant = VerifiedGrant {
            binding_digest: request.request_digest.clone(),
            input: workspace.clone(),
            input_inventory: WorkspaceInventory {
                directories: Vec::new(),
                files: Vec::new(),
            },
            predecessor: None,
            predecessor_inventory: None,
        };
        let (_peer, client) = UnixStream::pair().unwrap();
        let mut budget = RequestExecutionBudget::new(Instant::now() + Duration::from_secs(2), 4);

        assert_eq!(
            execute_container(
                &config,
                &config.cache[0],
                &request,
                &grant,
                None,
                &client,
                &mut budget,
            ),
            Err(ExecutionFailure::ordinary(
                "implementation_unavailable",
                false
            ))
        );
        assert_eq!(budget.output.remaining, 0);

        fs::set_permissions(&workspace, fs::Permissions::from_mode(0o700)).unwrap();
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn uncertain_work_removal_retries_inside_the_shared_cleanup_budget() {
        let (root, config) = test_config();
        let container = root.join("container-work-cleanup");
        let first_removal = root.join("first-removal");
        fs::write(&container, b"live").unwrap();
        fs::write(
            &config.docker_binary,
            format!(
                r#"#!/bin/sh
case "$1 $2" in
  "rm -f")
    if test ! -e "{first_removal}"; then
      : > "{first_removal}"
      printf 'work'
    else
      rm -f "{container}"
      printf 'cleanup'
    fi
    exit 0;;
  "container ls") test -e "{container}" && printf '%064d\n' 0; exit 0;;
esac
exit 2
"#,
                first_removal = first_removal.display(),
                container = container.display(),
            ),
        )
        .unwrap();
        fs::set_permissions(&config.docker_binary, fs::Permissions::from_mode(0o700)).unwrap();
        let (_peer, client) = UnixStream::pair().unwrap();
        let mut output = OutputMeter::new(1024);
        let mut cleanup = EmergencyCleanupBudget::new();

        assert_eq!(
            remove_container_work(
                &config,
                "candidate",
                &client,
                Instant::now() + Duration::from_secs(2),
                &mut output,
                &mut cleanup,
            ),
            RemovalOutcome::Recovered
        );
        assert!(!container.exists());
        assert!(output.remaining < 1020);
        assert!(cleanup.deadline.is_some());
        assert!(cleanup.remaining_output < CLEANUP_MAXIMUM_OUTPUT_BYTES);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn ambiguous_container_removal_preserves_the_resource_for_work_and_cleanup() {
        let (root, config) = test_config();
        let container = root.join("container-ambiguous");
        fs::write(&container, b"live").unwrap();
        fs::write(
            &config.docker_binary,
            b"#!/bin/sh\ncase \"$1 $2\" in\n  \"rm -f\") exit 125;;\n  \"container ls\") exit 125;;\nesac\nexit 2\n",
        )
        .unwrap();
        fs::set_permissions(&config.docker_binary, fs::Permissions::from_mode(0o700)).unwrap();
        let (_peer, client) = UnixStream::pair().unwrap();
        let mut output = OutputMeter::new(1024);
        let mut cleanup = EmergencyCleanupBudget::new();

        assert_eq!(
            remove_container_work(
                &config,
                "candidate",
                &client,
                Instant::now() + Duration::from_secs(2),
                &mut output,
                &mut cleanup,
            ),
            RemovalOutcome::Unsettled
        );
        assert!(container.exists());
        assert!(!remove_container_cleanup(
            &config,
            "candidate",
            &mut cleanup,
        ));
        assert!(container.exists());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn unresolved_create_cleanup_is_a_fatal_execution_failure() {
        let (root, config) = test_config();
        let container = root.join("container");
        fs::write(
            &config.docker_binary,
            b"#!/bin/sh\nroot=$(dirname \"$0\")\ncase \"$1 $2\" in\n  \"create --name\") : > \"$root/container\"; exit 17;;\n  \"rm -f\"|\"container ls\") exit 125;;\nesac\nexit 2\n",
        )
        .unwrap();
        fs::set_permissions(&config.docker_binary, fs::Permissions::from_mode(0o700)).unwrap();
        let workspace = config.material_root.join("workspace-fatal-cleanup");
        fs::create_dir(&workspace).unwrap();
        fs::set_permissions(&workspace, fs::Permissions::from_mode(0o500)).unwrap();
        let request = parse_request(include_bytes!("../../fixtures/request.json")).unwrap();
        let grant = VerifiedGrant {
            binding_digest: request.request_digest.clone(),
            input: workspace.clone(),
            input_inventory: WorkspaceInventory {
                directories: Vec::new(),
                files: Vec::new(),
            },
            predecessor: None,
            predecessor_inventory: None,
        };
        let (_peer, client) = UnixStream::pair().unwrap();
        let mut budget = RequestExecutionBudget::new(
            Instant::now() + Duration::from_secs(2),
            request.maximum_output_bytes,
        );

        assert_eq!(
            execute_container(
                &config,
                &config.cache[0],
                &request,
                &grant,
                None,
                &client,
                &mut budget,
            ),
            Err(ExecutionFailure::unsettled(false))
        );
        assert!(container.exists());
        fs::set_permissions(&workspace, fs::Permissions::from_mode(0o700)).unwrap();
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn uncertain_container_creation_is_removed_before_returning() {
        let (root, config) = test_config();
        fs::write(
            &config.docker_binary,
            b"#!/bin/sh\nroot=$(dirname \"$0\")\ncase \"$1\" in\n  create) : > \"$root/container\"; exit 17;;\n  rm) rm -f \"$root/container\"; exit 0;;\n  container) test -e \"$root/container\" && printf '%064d\\n' 0; exit 0;;\nesac\n",
        )
        .unwrap();
        fs::set_permissions(&config.docker_binary, fs::Permissions::from_mode(0o700)).unwrap();
        let workspace = config.material_root.join("workspace");
        fs::create_dir(&workspace).unwrap();
        fs::set_permissions(&workspace, fs::Permissions::from_mode(0o500)).unwrap();
        let request = parse_request(include_bytes!("../../fixtures/request.json")).unwrap();
        let grant = VerifiedGrant {
            binding_digest: request.request_digest.clone(),
            input: workspace.clone(),
            input_inventory: WorkspaceInventory {
                directories: Vec::new(),
                files: Vec::new(),
            },
            predecessor: None,
            predecessor_inventory: None,
        };
        let (_peer, client) = UnixStream::pair().unwrap();
        let mut budget = RequestExecutionBudget::new(
            Instant::now() + Duration::from_secs(2),
            request.maximum_output_bytes,
        );

        assert_eq!(
            execute_container(
                &config,
                &config.cache[0],
                &request,
                &grant,
                None,
                &client,
                &mut budget,
            ),
            Err(ExecutionFailure::ordinary(
                "implementation_unavailable",
                false
            ))
        );
        assert!(!root.join("container").exists());

        fs::set_permissions(&workspace, fs::Permissions::from_mode(0o700)).unwrap();
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn grant_lineage_matches_the_normalized_pre_submit_request() {
        let mut request = parse_request(include_bytes!("../../fixtures/request.json")).unwrap();
        let mut manifest = GrantManifest {
            protocol_version: PRE_GRANT_PROTOCOL.into(),
            grant_id: "extract_0123456789abcdef0123456789abcdef".into(),
            request_digest: request.request_digest.clone(),
            identity: GrantIdentity::PreSubmit {
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
                archive_sha256: request.value["materials"][0]["archive_sha256"]
                    .as_str()
                    .unwrap()
                    .into(),
                archive_byte_count: request.value["materials"][0]["archive_byte_count"]
                    .as_u64()
                    .unwrap(),
                semantic_manifest_sha256: String::new(),
            },
            directories: Vec::new(),
            files: Vec::new(),
            binding_digest: format!("sha256:{}", "9".repeat(64)),
        };
        let semantic = semantic_manifest_hash(&manifest).unwrap();
        let GrantIdentity::PreSubmit {
            semantic_manifest_sha256,
            ..
        } = &mut manifest.identity;
        *semantic_manifest_sha256 = semantic;
        request.value["materials"][0]["semantic_manifest_sha256"] =
            Value::String(semantic_manifest_sha256.clone());
        assert!(grant_matches_request(&manifest, &request));
        for field in 0..6 {
            let original = manifest.identity.clone();
            let GrantIdentity::PreSubmit {
                prepared_generation_id,
                attempt_id,
                attempt_request_digest,
                archive_sha256,
                archive_byte_count,
                semantic_manifest_sha256,
            } = &mut manifest.identity;
            match field {
                0 => *prepared_generation_id = "00000000-0000-4000-8000-000000000000".into(),
                1 => *attempt_id = "00000000-0000-4000-8000-000000000000".into(),
                2 => *attempt_request_digest = format!("sha256:{}", "8".repeat(64)),
                3 => *archive_sha256 = format!("sha256:{}", "8".repeat(64)),
                4 => *archive_byte_count += 1,
                _ => *semantic_manifest_sha256 = format!("sha256:{}", "8".repeat(64)),
            }
            assert!(!grant_matches_request(&manifest, &request));
            manifest.identity = original;
        }
        request.phase = "post_submit".into();
        assert!(!grant_matches_request(&manifest, &request));
    }

    fn post_grant_fixture(
        include_prior: bool,
        prior_visible: bool,
        context_enabled: bool,
    ) -> (ValidatedRequest, PostGrantManifest) {
        let digest = |byte: char| format!("sha256:{}", byte.to_string().repeat(64));
        let id = |byte: char| format!("{0}{0}{0}{0}{0}{0}{0}{0}-0000-4000-8000-000000000000", byte);
        let identity = serde_json::json!({
            "phase": "post_submit", "project_id": id('1'), "task_id": id('2'),
            "assignment_id": id('3'), "submission_id": id('4'), "submission_version": 2,
            "evaluation_request_id": id('5'), "evaluation_request_digest": digest('5'),
            "evaluation_generation": 3, "attempt_id": id('6'), "result_id": id('7'),
            "lease_id": id('8'), "lease_generation": 4,
            "lease_expires_at": "2026-10-11T12:00:00+00:00"
        });
        let semantic = semantic_manifest_hash_parts(&[], &[]).unwrap();
        let material = |role: &str, submission_id: String, version: u64, marker: char| {
            serde_json::json!({
                "phase": "post_submit", "role": role,
                "submission_id": submission_id, "submission_version": version,
                "binding_id": id(marker), "content_id": id('a'), "replica_id": id('b'),
                "content_sha256": digest(marker), "byte_count": 0,
                "media_type": "application/zip", "evidence_id": id('c'),
                "verification_receipt_id": id('d'), "verification_job_id": id('e'),
                "verification_generation": 5, "namespace_fingerprint": digest('d'),
                "semantic_manifest_sha256": semantic
            })
        };
        let current = material(
            CURRENT_ARCHIVE_ROLE,
            identity["submission_id"].as_str().unwrap().into(),
            2,
            '9',
        );
        let prior = material(PREDECESSOR_ARCHIVE_ROLE, id('0'), 1, '8');
        let mut requested = vec![current.clone()];
        let mut visible_roles = vec![CURRENT_ARCHIVE_ROLE.to_owned()];
        if prior_visible {
            requested.push(prior.clone());
            visible_roles.push(PREDECESSOR_ARCHIVE_ROLE.to_owned());
        }
        let mut available = vec![PostGrantMaterial {
            material: current,
            directories: Vec::new(),
            files: Vec::new(),
        }];
        if include_prior {
            available.push(PostGrantMaterial {
                material: prior,
                directories: Vec::new(),
                files: Vec::new(),
            });
        }
        let context = context_enabled.then(|| {
            serde_json::json!({
                "schema_version": "workstream.post_submit_evaluation_context.v1",
                "kind": "checker_remediation",
                "source": {},
                "predecessor": {
                    "submission_id": id('0'), "submission_version": 1,
                    "content_sha256": digest('8'), "byte_count": 0,
                    "semantic_manifest_sha256": semantic,
                },
                "feedback": null,
            })
        });
        let context_sha256 = context.as_ref().map(|value| canonical_hash(value).unwrap());
        let request_digest = digest('7');
        let input = context
            .as_ref()
            .map(|value| serde_json::json!({"evaluation_context": value}))
            .unwrap_or_else(|| serde_json::json!({}));
        let request = ValidatedRequest {
            value: serde_json::json!({
                "identity": identity, "input": input, "materials": requested
            }),
            request_digest: request_digest.clone(),
            registry_entry_id: id('f'),
            registry_entry_digest: digest('1'),
            image_digest: digest('2'),
            configuration_digest: digest('3'),
            phase: "post_submit".into(),
            post_material_roles: visible_roles.clone(),
            evaluation_context_sha256: context_sha256.clone(),
            cpu_millis: 100,
            memory_bytes: 16 * 1024 * 1024,
            deadline_ms: 100,
            maximum_output_bytes: 256,
        };
        let mut manifest = PostGrantManifest {
            protocol_version: POST_GRANT_PROTOCOL.into(),
            grant_id: "extract_0123456789abcdef0123456789abcdef".into(),
            request_digest,
            phase: "post_submit".into(),
            identity: request.value["identity"].clone(),
            evaluation_context_sha256: context_sha256,
            materials: available,
            visible_roles,
            binding_digest: digest('0'),
        };
        let mut body = serde_json::to_value(&manifest).unwrap();
        body.as_object_mut().unwrap().remove("binding_digest");
        manifest.binding_digest = canonical_hash(&body).unwrap();
        (request, manifest)
    }

    fn publish_post_grant(config: &ServiceConfig, manifest: &PostGrantManifest) -> GrantReference {
        let grant_root = config
            .material_root
            .join("workspaces")
            .join(&manifest.grant_id);
        let materials = grant_root.join("materials");
        fs::create_dir_all(&materials).unwrap();
        for item in &manifest.materials {
            let role = item.material["role"].as_str().unwrap();
            let root = materials.join(role);
            if !root.exists() {
                fs::create_dir(&root).unwrap();
            }
            fs::set_permissions(&root, fs::Permissions::from_mode(0o500)).unwrap();
        }
        fs::set_permissions(&materials, fs::Permissions::from_mode(0o500)).unwrap();
        fs::set_permissions(&grant_root, fs::Permissions::from_mode(0o700)).unwrap();
        let path = grant_root.join(".external-checker-grant.json");
        fs::write(&path, serde_json::to_vec(manifest).unwrap()).unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o400)).unwrap();
        GrantReference {
            grant_id: manifest.grant_id.clone(),
            binding_digest: manifest.binding_digest.clone(),
        }
    }

    #[test]
    fn post_grant_v2_binds_context_roles_and_all_aggregate_inventories() {
        let (root, config) = test_config();
        let (request, manifest) = post_grant_fixture(true, false, false);
        assert!(request.value["input"].get("evaluation_context").is_none());
        assert_eq!(request.evaluation_context_sha256, None);
        assert_eq!(request.post_material_roles, [CURRENT_ARCHIVE_ROLE]);
        assert_eq!(manifest.materials.len(), 2);
        let reference = publish_post_grant(&config, &manifest);
        let verified = verify_grant(&config, &request, &reference).unwrap();
        assert!(verified.input.ends_with(CURRENT_ARCHIVE_ROLE));
        assert_eq!(
            verified.predecessor, None,
            "hidden prior must not be mounted"
        );
        let (unauthorized_request, unauthorized_manifest) = post_grant_fixture(true, true, false);
        let unauthorized_reference = GrantReference {
            grant_id: unauthorized_manifest.grant_id.clone(),
            binding_digest: unauthorized_manifest.binding_digest.clone(),
        };
        assert!(verify_post_grant(
            &config,
            &unauthorized_request,
            &unauthorized_reference,
            &config
                .material_root
                .join("workspaces")
                .join(&unauthorized_manifest.grant_id),
            &unauthorized_manifest,
        )
        .is_err());

        let manifest_path = config
            .material_root
            .join("workspaces")
            .join(&manifest.grant_id)
            .join(".external-checker-grant.json");
        fs::set_permissions(&manifest_path, fs::Permissions::from_mode(0o600)).unwrap();
        fs::remove_file(&manifest_path).unwrap();
        let (visible_request, visible_manifest) = post_grant_fixture(true, true, true);
        let visible_reference = publish_post_grant(&config, &visible_manifest);
        let visible = verify_grant(&config, &visible_request, &visible_reference).unwrap();
        assert!(visible.predecessor.is_some());

        let mut substituted = visible_manifest.clone();
        substituted.evaluation_context_sha256 = Some(format!("sha256:{}", "a".repeat(64)));
        assert!(verify_post_grant(
            &config,
            &visible_request,
            &visible_reference,
            &config
                .material_root
                .join("workspaces")
                .join(&substituted.grant_id),
            &substituted,
        )
        .is_err());
        let mut substituted_prior = visible_manifest.clone();
        substituted_prior.materials[1].material["content_sha256"] =
            Value::String(format!("sha256:{}", "a".repeat(64)));
        assert!(verify_post_grant(
            &config,
            &visible_request,
            &visible_reference,
            &config
                .material_root
                .join("workspaces")
                .join(&substituted_prior.grant_id),
            &substituted_prior,
        )
        .is_err());
        let mut extra = serde_json::to_value(&visible_manifest).unwrap();
        extra["unexpected"] = Value::Bool(true);
        assert!(serde_json::from_value::<PostGrantManifest>(extra).is_err());
        let mut legacy_shape = serde_json::to_value(&visible_manifest).unwrap();
        legacy_shape["protocol_version"] = Value::String(PRE_GRANT_PROTOCOL.into());
        assert!(serde_json::from_value::<GrantManifest>(legacy_shape).is_err());
        let mut unknown_role = visible_manifest.materials[1].clone();
        unknown_role.material["role"] = Value::String("foreign_archive".into());
        assert!(validate_post_grant_material(&unknown_role).is_err());
        let mut reordered = visible_manifest.clone();
        reordered.materials.reverse();
        assert!(verify_post_grant(
            &config,
            &visible_request,
            &visible_reference,
            &config
                .material_root
                .join("workspaces")
                .join(&reordered.grant_id),
            &reordered,
        )
        .is_err());
        let substituted_reference = GrantReference {
            grant_id: visible_reference.grant_id.clone(),
            binding_digest: format!("sha256:{}", "0".repeat(64)),
        };
        assert!(verify_grant(&config, &visible_request, &substituted_reference).is_err());
        let material_root = config
            .material_root
            .join("workspaces")
            .join(&visible_manifest.grant_id)
            .join("materials");
        let current_root = material_root.join(CURRENT_ARCHIVE_ROLE);
        fs::set_permissions(&current_root, fs::Permissions::from_mode(0o700)).unwrap();
        fs::write(current_root.join("drift"), b"changed").unwrap();
        fs::set_permissions(&current_root, fs::Permissions::from_mode(0o500)).unwrap();
        assert!(verify_grant(&config, &visible_request, &visible_reference).is_err());
        fs::set_permissions(&current_root, fs::Permissions::from_mode(0o700)).unwrap();
        fs::remove_file(current_root.join("drift")).unwrap();
        for role in [CURRENT_ARCHIVE_ROLE, PREDECESSOR_ARCHIVE_ROLE] {
            fs::set_permissions(material_root.join(role), fs::Permissions::from_mode(0o700))
                .unwrap();
        }
        fs::set_permissions(&material_root, fs::Permissions::from_mode(0o700)).unwrap();
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn container_mounts_only_server_verified_visible_roles() {
        let (root, mut config) = test_config();
        fs::write(
            &config.docker_binary,
            b"#!/bin/sh\nroot=$(dirname \"$0\")\ncase \"$1\" in\n  create) printf '%s\\n' \"$@\" > \"$root/args\"; exit 17;;\n  rm|container) exit 0;;\nesac\nexit 2\n",
        )
        .unwrap();
        fs::set_permissions(&config.docker_binary, fs::Permissions::from_mode(0o700)).unwrap();
        let current = config.material_root.join("visible-current");
        let prior = config.material_root.join("hidden-prior");
        fs::create_dir(&current).unwrap();
        fs::create_dir(&prior).unwrap();
        fs::set_permissions(&current, fs::Permissions::from_mode(0o500)).unwrap();
        fs::set_permissions(&prior, fs::Permissions::from_mode(0o500)).unwrap();
        let (request, _) = post_grant_fixture(true, false, false);
        let (_peer, client) = UnixStream::pair().unwrap();
        let mut budget = RequestExecutionBudget::new(
            Instant::now() + Duration::from_secs(2),
            request.maximum_output_bytes,
        );
        let hidden = VerifiedGrant {
            binding_digest: request.request_digest.clone(),
            input: current.clone(),
            input_inventory: WorkspaceInventory {
                directories: Vec::new(),
                files: Vec::new(),
            },
            predecessor: None,
            predecessor_inventory: None,
        };
        assert_eq!(
            execute_container(
                &config,
                &config.cache[0],
                &request,
                &hidden,
                None,
                &client,
                &mut budget,
            ),
            Err(ExecutionFailure::ordinary(
                "implementation_unavailable",
                false
            ))
        );
        let arguments = fs::read_to_string(root.join("args")).unwrap();
        assert!(arguments.contains("dst=/work/input,readonly"));
        assert!(!arguments.contains("/work/context/predecessor"));
        fs::set_permissions(&current, fs::Permissions::from_mode(0o700)).unwrap();
        fs::write(current.join("late-drift"), b"changed").unwrap();
        fs::set_permissions(&current, fs::Permissions::from_mode(0o500)).unwrap();
        let mut budget = RequestExecutionBudget::new(
            Instant::now() + Duration::from_secs(2),
            request.maximum_output_bytes,
        );
        assert_eq!(
            execute_container(
                &config,
                &config.cache[0],
                &request,
                &hidden,
                None,
                &client,
                &mut budget,
            ),
            Err(ExecutionFailure::ordinary("material_unavailable", false))
        );
        fs::set_permissions(&current, fs::Permissions::from_mode(0o700)).unwrap();
        fs::remove_file(current.join("late-drift")).unwrap();
        fs::set_permissions(&current, fs::Permissions::from_mode(0o500)).unwrap();

        let visible = VerifiedGrant {
            binding_digest: request.request_digest.clone(),
            input: current.clone(),
            input_inventory: WorkspaceInventory {
                directories: Vec::new(),
                files: Vec::new(),
            },
            predecessor: Some(prior.clone()),
            predecessor_inventory: Some(WorkspaceInventory {
                directories: Vec::new(),
                files: Vec::new(),
            }),
        };
        let mut budget = RequestExecutionBudget::new(
            Instant::now() + Duration::from_secs(2),
            request.maximum_output_bytes,
        );
        assert_eq!(
            execute_container(
                &config,
                &config.cache[0],
                &request,
                &visible,
                None,
                &client,
                &mut budget,
            ),
            Err(ExecutionFailure::ordinary(
                "implementation_unavailable",
                false
            ))
        );
        let arguments = fs::read_to_string(root.join("args")).unwrap();
        assert!(arguments.contains("dst=/work/input,readonly"));
        assert!(arguments.contains("dst=/work/context/predecessor,readonly"));
        // Smol has no predecessor projection yet: reject before VM admission.
        // Without this guard, missing Smol setup reaches Machine::create and
        // returns cleanup-unsettled, distinguishing a mere incidental failure.
        config.runtime = "smolvm".into();
        assert_eq!(
            execute_container_inner(
                &config,
                &config.cache[0],
                &request,
                &visible,
                None,
                None,
                &client,
                &mut budget,
            ),
            Err(ExecutionFailure::ordinary(
                "implementation_unavailable",
                false
            ))
        );
        fs::set_permissions(&current, fs::Permissions::from_mode(0o700)).unwrap();
        fs::set_permissions(&prior, fs::Permissions::from_mode(0o700)).unwrap();
        fs::remove_dir_all(root).unwrap();
    }
}
