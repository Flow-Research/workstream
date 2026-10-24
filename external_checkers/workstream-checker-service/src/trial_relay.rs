//! Invocation-local, profile-bounded isolated trial relay for checker agents.

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::HashSet;
use std::fs::{self, DirBuilder};
use std::io::{Read, Write};
use std::os::unix::ffi::OsStrExt;
use std::os::unix::fs::{DirBuilderExt, FileTypeExt, MetadataExt, PermissionsExt};
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::{Component, Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;
use std::thread::{self, JoinHandle};
use std::time::{Duration, Instant};
use workstream_checker_sdk::{canonical_hash, canonical_json};

pub(crate) const CONTAINER_EXECUTION_SOCKET: &str = "/work/execution.sock";
const TRIAL_PROTOCOL: &str = "workstream.checker_trial.v1";
const TRIAL_PLAN_SCHEMA: &str = "workstream.checker_trial_plan.v1";
const TRIAL_RECEIPT_SCHEMA: &str = "workstream.checker_trial_receipt.v1";
const INVOCATION_DIRECTORY_PREFIX: &str = ".trial-";
const ABSOLUTE_MAXIMUM_FRAME_BYTES: usize = 4 * 1024 * 1024;
const ABSOLUTE_MAXIMUM_RECEIPT_BYTES: usize = 1024 * 1024;
static INVOCATION_SEQUENCE: AtomicU64 = AtomicU64::new(0);

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(crate) struct TrialRequestIdentity {
    pub(crate) request_digest: String,
    pub(crate) material_binding_digest: String,
    pub(crate) input_digest: String,
    pub(crate) materials_digest: String,
    pub(crate) project_id: String,
    pub(crate) task_id: String,
    pub(crate) assignment_id: String,
    pub(crate) submission_id: String,
    pub(crate) submission_version: u64,
    pub(crate) requirement_id: String,
    pub(crate) registry_entry_id: String,
    pub(crate) registry_entry_digest: String,
    pub(crate) checker_image_digest: String,
    pub(crate) configuration_sha256: String,
    pub(crate) evaluation_request_id: String,
    pub(crate) evaluation_generation: u64,
    pub(crate) checker_run_id: String,
    pub(crate) attempt_id: String,
    pub(crate) result_id: String,
    pub(crate) worker_lease_id: String,
    pub(crate) worker_lease_generation: u64,
    pub(crate) worker_lease_expires_at: String,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(crate) struct TrialProfile {
    pub(crate) profile_id: String,
    pub(crate) profile_version: u32,
    pub(crate) profile_digest: String,
    pub(crate) projection_id: String,
    pub(crate) projection_version: u32,
    pub(crate) projection_digest: String,
    pub(crate) trial_kind: String,
    pub(crate) registry_entry_id: String,
    pub(crate) registry_entry_digest: String,
    pub(crate) checker_image_digest: String,
    pub(crate) configuration_sha256: String,
    pub(crate) engine_identity_digest: String,
    pub(crate) outer_runtime_config_digest: String,
    pub(crate) child_runtime: String,
    pub(crate) child_runtime_config_digest: String,
    pub(crate) child_host_uds: String,
    pub(crate) platform: String,
    pub(crate) platform_identity_digest: String,
    pub(crate) builder_image_digest: String,
    pub(crate) trusted_launcher_digest: String,
    pub(crate) offline_cache_digest: String,
    pub(crate) approved_base_digests: Vec<String>,
    pub(crate) source_material_roles: Vec<String>,
    pub(crate) material_projections: Vec<TrialMaterialProjectionProfile>,
    pub(crate) build_context_roles: Vec<String>,
    pub(crate) allowed_material_roles: Vec<String>,
    pub(crate) slot_templates: Vec<TrialSlotProfile>,
    pub(crate) maximum_frame_bytes: usize,
    pub(crate) maximum_response_bytes: usize,
    pub(crate) maximum_steps: usize,
    pub(crate) maximum_total_timeout_ms: u64,
    pub(crate) maximum_build_timeout_ms: u64,
    pub(crate) maximum_step_timeout_ms: u64,
    pub(crate) maximum_step_output_bytes: usize,
    pub(crate) maximum_observation_bytes: usize,
    pub(crate) maximum_receipt_bytes: usize,
    pub(crate) maximum_cpu_quota_millis: u64,
    pub(crate) maximum_cpu_time_ms: u64,
    pub(crate) maximum_wall_time_overrun_ms: u64,
    pub(crate) maximum_cpu_time_overrun_ms: u64,
    pub(crate) maximum_memory_bytes: u64,
    pub(crate) maximum_memory_overrun_bytes: u64,
    pub(crate) maximum_disk_bytes: u64,
    pub(crate) maximum_disk_overrun_bytes: u64,
    pub(crate) maximum_entries: u64,
    pub(crate) maximum_entries_overrun: u64,
    pub(crate) maximum_pids: u64,
    pub(crate) maximum_pids_overrun: u64,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(crate) struct TrialSlotProfile {
    pub(crate) slot_kind: String,
    pub(crate) minimum_occurrences: usize,
    pub(crate) maximum_occurrences: usize,
    pub(crate) seed_roles: Vec<String>,
    pub(crate) visible_roles: Vec<String>,
    pub(crate) fresh_workspace: bool,
    pub(crate) retain_state_after: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(crate) struct TrialMaterialProjectionProfile {
    pub(crate) role: String,
    pub(crate) source_role: String,
    pub(crate) projection_kind: String,
    pub(crate) source_relative: String,
    pub(crate) destination_relative: String,
    pub(crate) exclusions: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(crate) struct TrialPlan {
    pub(crate) schema_version: String,
    pub(crate) environment: TrialEnvironment,
    pub(crate) resources: TrialResources,
    pub(crate) build_timeout_ms: u64,
    pub(crate) steps: Vec<TrialStep>,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(crate) struct TrialEnvironment {
    pub(crate) dockerfile: String,
    pub(crate) context: String,
    pub(crate) platform: String,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(crate) struct TrialResources {
    pub(crate) cpu_quota_millis: u64,
    pub(crate) cpu_time_ms: u64,
    pub(crate) memory_bytes: u64,
    pub(crate) disk_bytes: u64,
    pub(crate) maximum_entries: u64,
    pub(crate) pids: u64,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(crate) struct TrialStep {
    pub(crate) slot_id: String,
    pub(crate) slot_kind: String,
    pub(crate) operation: String,
    pub(crate) state_source: String,
    pub(crate) visible_roles: Vec<String>,
    pub(crate) command: Vec<String>,
    pub(crate) working_directory: String,
    pub(crate) timeout_ms: u64,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(crate) struct TrialExecution {
    pub(crate) platform_identity_digest: String,
    pub(crate) builder_image_digest: String,
    pub(crate) trusted_launcher_digest: String,
    pub(crate) offline_cache_digest: String,
    pub(crate) base_image_digests: Vec<String>,
    pub(crate) material_inventory_digests: Vec<RoleInventoryDigest>,
    pub(crate) build: TrialBuildObservation,
    pub(crate) steps: Vec<TrialStepObservation>,
    pub(crate) cleanup_confirmed: bool,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(crate) struct RoleInventoryDigest {
    pub(crate) role: String,
    pub(crate) digest: String,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(crate) struct TrialBuildObservation {
    pub(crate) outcome: TrialOperationOutcome,
    pub(crate) exit_code: Option<i32>,
    pub(crate) signal: Option<i32>,
    pub(crate) stdout: String,
    pub(crate) stdout_sha256: String,
    pub(crate) stderr: String,
    pub(crate) stderr_sha256: String,
    pub(crate) candidate_image_digest: Option<String>,
    pub(crate) candidate_archive_digest: Option<String>,
    pub(crate) export_outcome: TrialExportOutcome,
    pub(crate) elapsed_ms: u64,
    pub(crate) cpu_time_ms: u64,
    pub(crate) peak_memory_bytes: u64,
    pub(crate) peak_pids: u64,
    pub(crate) written_bytes: u64,
    pub(crate) written_entries: u64,
    pub(crate) measurement_method: String,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(crate) struct TrialStepObservation {
    pub(crate) slot_id: String,
    pub(crate) operation_order: u32,
    pub(crate) workspace_identity: String,
    pub(crate) visible_role_inventory_digests: Vec<RoleInventoryDigest>,
    pub(crate) outcome: TrialOperationOutcome,
    pub(crate) exit_code: Option<i32>,
    pub(crate) signal: Option<i32>,
    pub(crate) stdout: String,
    pub(crate) stdout_sha256: String,
    pub(crate) stderr: String,
    pub(crate) stderr_sha256: String,
    pub(crate) workspace_before_sha256: String,
    pub(crate) workspace_after_sha256: String,
    pub(crate) export_outcome: TrialExportOutcome,
    pub(crate) elapsed_ms: u64,
    pub(crate) cpu_time_ms: u64,
    pub(crate) peak_memory_bytes: u64,
    pub(crate) peak_pids: u64,
    pub(crate) written_bytes: u64,
    pub(crate) written_entries: u64,
    pub(crate) measurement_method: String,
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub(crate) enum TrialOperationOutcome {
    Succeeded,
    ExitNonzero,
    Signalled,
    DeadlineExceeded,
    CpuExceeded,
    MemoryExceeded,
    PidExceeded,
    DiskExceeded,
    OutputExceeded,
    ExportInvalid,
    DependencySkipped,
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub(crate) enum TrialExportOutcome {
    Exported,
    Invalid,
    CapacityExceeded,
    Unavailable,
    NotStarted,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum TrialRelayFailure {
    InvalidRequest,
    MaterialUnavailable,
    ImplementationUnavailable,
    CapacityExceeded,
    DeadlineExceeded,
    Cancelled,
    CleanupUnsettled,
}

impl TrialRelayFailure {
    fn wire_code(self) -> &'static str {
        match self {
            Self::InvalidRequest => "invalid_request",
            Self::MaterialUnavailable => "material_unavailable",
            Self::ImplementationUnavailable => "implementation_unavailable",
            Self::CapacityExceeded => "capacity_exceeded",
            Self::DeadlineExceeded => "deadline_exceeded",
            Self::Cancelled => "cancelled",
            Self::CleanupUnsettled => "cleanup_unsettled",
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct TrialEngineFailure {
    pub(crate) code: TrialRelayFailure,
    pub(crate) cleanup_unsettled: bool,
}

pub(crate) trait TrialEngine: Send + Sync + 'static {
    fn execute(
        &self,
        context: &TrialEngineContext,
        plan: &TrialPlan,
        deadline: Instant,
        invocation_cancelled: &AtomicBool,
        relay_cancelled: &AtomicBool,
    ) -> Result<TrialExecution, TrialEngineFailure>;
}

#[derive(Clone, Debug)]
pub(crate) struct TrialEngineContext {
    pub(crate) identity: TrialRequestIdentity,
    pub(crate) profile: TrialProfile,
    pub(crate) verified_material_root: PathBuf,
    pub(crate) trial_scratch_root: PathBuf,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct TrialReceiptPublication {
    pub(crate) schema_version: String,
    pub(crate) request_identity_digest: String,
    pub(crate) originating_identity: TrialRequestIdentity,
    pub(crate) material_binding_digest: String,
    pub(crate) profile_id: String,
    pub(crate) profile_version: u32,
    pub(crate) profile_digest: String,
    pub(crate) trial_kind: String,
    pub(crate) engine_identity_digest: String,
    pub(crate) plan_digest: String,
    pub(crate) observation_digest: String,
    pub(crate) observation_byte_count: usize,
    pub(crate) slot_ids: Vec<String>,
    pub(crate) plan_started: bool,
    pub(crate) plan_completed: bool,
    pub(crate) cleanup_confirmed: bool,
    pub(crate) plan: TrialPlan,
    pub(crate) execution: TrialExecution,
}

#[derive(Debug)]
pub(crate) struct CanonicalTrialReceipt {
    pub(crate) receipt_digest: String,
    pub(crate) byte_count: usize,
    pub(crate) canonical_bytes: Vec<u8>,
    pub(crate) facts: TrialReceiptPublication,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct TrialReceiptCustodyAck {
    pub(crate) binding_id: String,
    pub(crate) content_id: String,
    pub(crate) put_attempt_id: String,
    pub(crate) verification_receipt_id: String,
    pub(crate) content_sha256: String,
    pub(crate) byte_count: usize,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct PublishedTrialReceipt {
    pub(crate) receipt_handle: String,
    pub(crate) custody: TrialReceiptCustodyAck,
}

#[derive(Clone, Debug, Serialize, PartialEq, Eq)]
pub(crate) struct TrialEvidenceSubject {
    pub(crate) project_id: String,
    pub(crate) task_id: String,
    pub(crate) assignment_id: String,
    pub(crate) submission_id: String,
    pub(crate) submission_version: u64,
    pub(crate) requirement_id: String,
    pub(crate) registry_entry_id: String,
    pub(crate) registry_entry_digest: String,
    pub(crate) configuration_sha256: String,
    pub(crate) trial_kind: String,
    pub(crate) slot_index: u32,
    pub(crate) plan_sha256: String,
    pub(crate) input_digest: String,
    pub(crate) materials_digest: String,
}

#[derive(Debug)]
pub(crate) enum TrialReceiptReservation {
    Fresh {
        trial_evidence_id: String,
    },
    Retained {
        trial_evidence_id: String,
        receipt: CanonicalTrialReceipt,
        published: PublishedTrialReceipt,
    },
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct TrialReceiptPublishFailure {
    pub(crate) code: TrialRelayFailure,
}

pub(crate) trait TrialReceiptPublisher: Send + Sync + 'static {
    fn reserve_completed(
        &self,
        subject: TrialEvidenceSubject,
    ) -> Result<TrialReceiptReservation, TrialReceiptPublishFailure>;

    fn publish_completed(
        &self,
        trial_evidence_id: &str,
        receipt: CanonicalTrialReceipt,
    ) -> Result<PublishedTrialReceipt, TrialReceiptPublishFailure>;
}

#[derive(Debug, PartialEq, Eq)]
pub(crate) struct TrialRelayFinish {
    pub(crate) failure: Option<TrialRelayFailure>,
    pub(crate) cleanup_unsettled: bool,
    pub(crate) plan_started: bool,
    pub(crate) plan_completed: bool,
    pub(crate) receipt_handle: Option<String>,
    pub(crate) receipt_digest: Option<String>,
}

#[derive(Debug)]
pub(crate) struct TrialRelayStartFailure {
    pub(crate) code: TrialRelayFailure,
    pub(crate) cleanup_unsettled: bool,
}

#[derive(Debug)]
struct RelayPaths {
    directory: PathBuf,
    socket: PathBuf,
    directory_device: u64,
    directory_inode: u64,
    socket_device: u64,
    socket_inode: u64,
    sandbox_uid: u32,
    sandbox_gid: u32,
}

#[derive(Debug)]
struct WorkerOutcome {
    failure: Option<TrialRelayFailure>,
    cleanup_unsettled: bool,
    plan_started: bool,
    plan_completed: bool,
    receipt_handle: Option<String>,
    receipt_digest: Option<String>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ImageTrialRequest {
    protocol_version: String,
    operation: String,
    plan: TrialPlan,
}

#[derive(Serialize)]
#[serde(deny_unknown_fields)]
struct CompletedImageTrialResponse<'a> {
    protocol_version: &'static str,
    outcome: &'static str,
    receipt_handle: &'a str,
    receipt_digest: &'a str,
    observations: &'a TrialObservationProjection,
    failure_code: Option<&'static str>,
}

#[derive(Serialize)]
struct TrialObservationProjection {
    schema_version: &'static str,
    terminal_state: &'static str,
    profile_digest: String,
    engine_identity_digest: String,
    plan_digest: String,
    observation_digest: String,
    build: TrialBuildProjection,
    steps: Vec<TrialStepProjection>,
}

#[derive(Serialize)]
struct TrialBuildProjection {
    terminal_state: &'static str,
    outcome: TrialOperationOutcome,
    export_outcome: TrialExportOutcome,
    exit_code: Option<i32>,
    signal: Option<i32>,
    stdout_sha256: String,
    stdout_byte_count: usize,
    stderr_sha256: String,
    stderr_byte_count: usize,
    candidate_image_digest: Option<String>,
    candidate_archive_digest: Option<String>,
    measurements_available: bool,
    elapsed_ms: u64,
    cpu_time_ms: u64,
    peak_memory_bytes: u64,
    peak_pids: u64,
    written_bytes: u64,
    written_entries: u64,
    measurement_method: String,
}

#[derive(Serialize)]
struct TrialStepProjection {
    terminal_state: &'static str,
    slot_id: String,
    operation_order: u32,
    outcome: TrialOperationOutcome,
    export_outcome: TrialExportOutcome,
    exit_code: Option<i32>,
    signal: Option<i32>,
    stdout_sha256: String,
    stdout_byte_count: usize,
    stderr_sha256: String,
    stderr_byte_count: usize,
    workspace_before_sha256: String,
    workspace_after_sha256: String,
    measurements_available: bool,
    elapsed_ms: u64,
    cpu_time_ms: u64,
    peak_memory_bytes: u64,
    peak_pids: u64,
    written_bytes: u64,
    written_entries: u64,
    measurement_method: String,
}

#[derive(Serialize)]
#[serde(deny_unknown_fields)]
struct UnavailableImageTrialResponse {
    protocol_version: &'static str,
    outcome: &'static str,
    receipt_handle: Option<&'static str>,
    receipt_digest: Option<&'static str>,
    failure_code: &'static str,
}

pub(crate) struct TrialRelay {
    paths: RelayPaths,
    local_cancelled: Arc<AtomicBool>,
    invocation_cancelled: Arc<AtomicBool>,
    worker: Option<JoinHandle<WorkerOutcome>>,
}

impl TrialRelay {
    #[allow(clippy::too_many_arguments)]
    pub(crate) fn start(
        relay_root: &Path,
        verified_material_root: &Path,
        trial_scratch_root: &Path,
        identity: &TrialRequestIdentity,
        profile: &TrialProfile,
        publisher: Arc<dyn TrialReceiptPublisher>,
        engine: Arc<dyn TrialEngine>,
        sandbox_uid: u32,
        sandbox_gid: u32,
        deadline: Instant,
        invocation_cancelled: Arc<AtomicBool>,
    ) -> Result<Self, TrialRelayStartFailure> {
        validate_start(
            relay_root,
            verified_material_root,
            trial_scratch_root,
            identity,
            profile,
            sandbox_uid,
            sandbox_gid,
        )?;
        let profile_deadline = Instant::now()
            .checked_add(Duration::from_millis(profile.maximum_total_timeout_ms))
            .ok_or(TrialRelayStartFailure {
                code: TrialRelayFailure::InvalidRequest,
                cleanup_unsettled: false,
            })?;
        let deadline = deadline.min(profile_deadline);
        let directory = create_invocation_directory(relay_root)?;
        let socket = directory.join("execution.sock");
        let listener = UnixListener::bind(&socket).map_err(|_| {
            let cleanup_unsettled = fs::remove_dir(&directory).is_err();
            TrialRelayStartFailure {
                code: TrialRelayFailure::ImplementationUnavailable,
                cleanup_unsettled,
            }
        })?;
        if listener.set_nonblocking(true).is_err()
            || fs::set_permissions(&socket, fs::Permissions::from_mode(0o600)).is_err()
        {
            drop(listener);
            return Err(remove_created_paths(&directory, &socket));
        }
        let directory_metadata = fs::symlink_metadata(&directory)
            .map_err(|_| remove_created_paths(&directory, &socket))?;
        let socket_metadata =
            fs::symlink_metadata(&socket).map_err(|_| remove_created_paths(&directory, &socket))?;
        if !private_directory(&directory_metadata, sandbox_uid, sandbox_gid)
            || socket_metadata.file_type().is_symlink()
            || !socket_metadata.file_type().is_socket()
            || socket_metadata.mode() & 0o777 != 0o600
            || socket_metadata.uid() != sandbox_uid
            || socket_metadata.gid() != sandbox_gid
        {
            drop(listener);
            return Err(remove_created_paths(&directory, &socket));
        }
        let paths = RelayPaths {
            directory,
            socket,
            directory_device: directory_metadata.dev(),
            directory_inode: directory_metadata.ino(),
            socket_device: socket_metadata.dev(),
            socket_inode: socket_metadata.ino(),
            sandbox_uid,
            sandbox_gid,
        };
        let context = TrialEngineContext {
            identity: identity.clone(),
            profile: profile.clone(),
            verified_material_root: verified_material_root.to_owned(),
            trial_scratch_root: trial_scratch_root.to_owned(),
        };
        let local_cancelled = Arc::new(AtomicBool::new(false));
        let worker_local_cancelled = Arc::clone(&local_cancelled);
        let worker_invocation_cancelled = Arc::clone(&invocation_cancelled);
        let worker = thread::Builder::new()
            .name("checker-trial-relay".into())
            .spawn(move || {
                relay_once(
                    listener,
                    &context,
                    publisher,
                    engine,
                    deadline,
                    &worker_local_cancelled,
                    &worker_invocation_cancelled,
                )
            })
            .map_err(|_| TrialRelayStartFailure {
                code: TrialRelayFailure::ImplementationUnavailable,
                cleanup_unsettled: !cleanup_paths(&paths),
            })?;
        Ok(Self {
            paths,
            local_cancelled,
            invocation_cancelled,
            worker: Some(worker),
        })
    }

    pub(crate) fn mount_spec(&self) -> String {
        format!(
            "type=bind,src={},dst={CONTAINER_EXECUTION_SOCKET},readonly",
            self.paths.socket.display()
        )
    }

    #[cfg(test)]
    pub(crate) fn socket_path(&self) -> &Path {
        &self.paths.socket
    }

    pub(crate) fn finish(mut self) -> TrialRelayFinish {
        let invocation_was_cancelled = self.invocation_cancelled.load(Ordering::Acquire);
        self.local_cancelled.store(true, Ordering::Release);
        let outcome = self
            .worker
            .take()
            .and_then(|worker| worker.join().ok())
            .unwrap_or(WorkerOutcome {
                failure: Some(TrialRelayFailure::ImplementationUnavailable),
                cleanup_unsettled: false,
                plan_started: false,
                plan_completed: false,
                receipt_handle: None,
                receipt_digest: None,
            });
        let cleanup_unsettled = outcome.cleanup_unsettled || !cleanup_paths(&self.paths);
        let unused = !invocation_was_cancelled
            && !outcome.plan_started
            && outcome.failure == Some(TrialRelayFailure::Cancelled);
        let failure = outcome
            .failure
            .filter(|_| !unused)
            .or(cleanup_unsettled.then_some(TrialRelayFailure::CleanupUnsettled));
        let receipt_usable = failure.is_none() && outcome.plan_completed;
        TrialRelayFinish {
            failure,
            cleanup_unsettled,
            plan_started: outcome.plan_started,
            plan_completed: outcome.plan_completed,
            receipt_handle: outcome.receipt_handle.filter(|_| receipt_usable),
            receipt_digest: outcome.receipt_digest.filter(|_| receipt_usable),
        }
    }
}

impl Drop for TrialRelay {
    fn drop(&mut self) {
        self.local_cancelled.store(true, Ordering::Release);
        if let Some(worker) = self.worker.take() {
            let _ = worker.join();
        }
        let _ = cleanup_paths(&self.paths);
    }
}

#[allow(clippy::too_many_arguments)]
fn validate_start(
    relay_root: &Path,
    verified_material_root: &Path,
    trial_scratch_root: &Path,
    identity: &TrialRequestIdentity,
    profile: &TrialProfile,
    sandbox_uid: u32,
    sandbox_gid: u32,
) -> Result<(), TrialRelayStartFailure> {
    let invalid = || TrialRelayStartFailure {
        code: TrialRelayFailure::InvalidRequest,
        cleanup_unsettled: false,
    };
    validate_private_root(relay_root, sandbox_uid, sandbox_gid).map_err(|_| invalid())?;
    validate_private_root(verified_material_root, sandbox_uid, sandbox_gid).map_err(|_| {
        TrialRelayStartFailure {
            code: TrialRelayFailure::MaterialUnavailable,
            cleanup_unsettled: false,
        }
    })?;
    validate_private_root(trial_scratch_root, sandbox_uid, sandbox_gid).map_err(|_| {
        TrialRelayStartFailure {
            code: TrialRelayFailure::MaterialUnavailable,
            cleanup_unsettled: false,
        }
    })?;
    if verified_material_root == trial_scratch_root
        || !valid_profile(profile)
        || identity.registry_entry_id != profile.registry_entry_id
        || identity.registry_entry_digest != profile.registry_entry_digest
        || identity.checker_image_digest != profile.checker_image_digest
        || identity.configuration_sha256 != profile.configuration_sha256
        || !valid_identity(identity)
    {
        return Err(invalid());
    }
    let socket_path = relay_root
        .join(format!("{INVOCATION_DIRECTORY_PREFIX}{}", "0".repeat(16)))
        .join("execution.sock");
    if relay_root.as_os_str().as_bytes().contains(&b',')
        || socket_path.as_os_str().as_bytes().len() >= 108
    {
        return Err(invalid());
    }
    Ok(())
}

pub(crate) fn valid_profile(profile: &TrialProfile) -> bool {
    let source_roles: HashSet<_> = profile.source_material_roles.iter().collect();
    let allowed_roles: HashSet<_> = profile.allowed_material_roles.iter().collect();
    let projection_roles: HashSet<_> = profile
        .material_projections
        .iter()
        .map(|item| &item.role)
        .collect();
    let build_roles: HashSet<_> = profile.build_context_roles.iter().collect();
    let base_digests: HashSet<_> = profile.approved_base_digests.iter().collect();
    let slot_kinds: HashSet<_> = profile
        .slot_templates
        .iter()
        .map(|slot| &slot.slot_kind)
        .collect();
    valid_uuid(&profile.profile_id)
        && profile.profile_version > 0
        && valid_sha256(&profile.profile_digest)
        && valid_uuid(&profile.projection_id)
        && profile.projection_version > 0
        && valid_sha256(&profile.projection_digest)
        && valid_identifier(&profile.trial_kind)
        && valid_uuid(&profile.registry_entry_id)
        && valid_sha256(&profile.registry_entry_digest)
        && valid_sha256(&profile.checker_image_digest)
        && valid_sha256(&profile.configuration_sha256)
        && valid_sha256(&profile.engine_identity_digest)
        && valid_sha256(&profile.outer_runtime_config_digest)
        && profile.child_runtime == "runsc"
        && valid_sha256(&profile.child_runtime_config_digest)
        && profile.child_host_uds == "none"
        && valid_sha256(&profile.platform_identity_digest)
        && valid_sha256(&profile.builder_image_digest)
        && valid_sha256(&profile.trusted_launcher_digest)
        && valid_sha256(&profile.offline_cache_digest)
        && !profile.approved_base_digests.is_empty()
        && base_digests.len() == profile.approved_base_digests.len()
        && profile
            .approved_base_digests
            .iter()
            .all(|value| valid_sha256(value))
        && !source_roles.is_empty()
        && source_roles.len() == profile.source_material_roles.len()
        && profile
            .source_material_roles
            .iter()
            .all(|value| valid_identifier(value))
        && !allowed_roles.is_empty()
        && allowed_roles.len() == profile.allowed_material_roles.len()
        && projection_roles == allowed_roles
        && profile
            .material_projections
            .iter()
            .all(|item| valid_material_projection(item, &source_roles))
        && ["build_context", "state_seed", "state_overlay"]
            .iter()
            .all(|kind| {
                !projection_destinations_overlap(
                    profile
                        .material_projections
                        .iter()
                        .filter(|item| item.projection_kind == *kind)
                        .map(|item| item.destination_relative.as_str()),
                )
            })
        && profile
            .allowed_material_roles
            .iter()
            .all(|value| valid_identifier(value))
        && !profile.build_context_roles.is_empty()
        && build_roles.len() == profile.build_context_roles.len()
        && profile.build_context_roles.iter().all(|value| {
            allowed_roles.contains(value)
                && profile
                    .material_projections
                    .iter()
                    .any(|item| item.role == *value && item.projection_kind == "build_context")
        })
        && !profile.slot_templates.is_empty()
        && slot_kinds.len() == profile.slot_templates.len()
        && profile.slot_templates.iter().all(|slot| {
            let visible_roles: HashSet<_> = slot.visible_roles.iter().collect();
            let seed_roles: HashSet<_> = slot.seed_roles.iter().collect();
            valid_identifier(&slot.slot_kind)
                && slot.minimum_occurrences <= slot.maximum_occurrences
                && slot.maximum_occurrences > 0
                && seed_roles.len() == slot.seed_roles.len()
                && visible_roles.len() == slot.visible_roles.len()
                && slot.seed_roles.iter().all(|value| {
                    allowed_roles.contains(value)
                        && profile
                            .material_projections
                            .iter()
                            .any(|item| item.role == *value && item.projection_kind == "state_seed")
                })
                && slot.visible_roles.iter().all(|value| {
                    allowed_roles.contains(value)
                        && profile.material_projections.iter().any(|item| {
                            item.role == *value && item.projection_kind == "state_overlay"
                        })
                })
                && !slot.retain_state_after.is_empty()
                && slot.retain_state_after.len()
                    == slot.retain_state_after.iter().collect::<HashSet<_>>().len()
                && slot.retain_state_after.iter().all(|value| {
                    matches!(value.as_str(), "succeeded" | "exit_nonzero" | "signalled")
                })
                && !projection_destinations_overlap(
                    slot.seed_roles
                        .iter()
                        .chain(&slot.visible_roles)
                        .filter_map(|role| {
                            profile
                                .material_projections
                                .iter()
                                .find(|item| item.role == **role)
                                .map(|item| item.destination_relative.as_str())
                        }),
                )
        })
        && (1..=ABSOLUTE_MAXIMUM_FRAME_BYTES).contains(&profile.maximum_frame_bytes)
        && (1..=ABSOLUTE_MAXIMUM_FRAME_BYTES).contains(&profile.maximum_response_bytes)
        && profile
            .slot_templates
            .iter()
            .try_fold(0_usize, |total, slot| {
                total.checked_add(slot.maximum_occurrences)
            })
            .is_some_and(|total| total <= profile.maximum_steps)
        && profile.maximum_build_timeout_ms > 0
        && profile.maximum_total_timeout_ms > 0
        && profile.maximum_build_timeout_ms <= profile.maximum_total_timeout_ms
        && profile.maximum_step_timeout_ms > 0
        && profile.maximum_step_timeout_ms <= profile.maximum_total_timeout_ms
        && profile.maximum_step_output_bytes > 0
        && profile.maximum_step_output_bytes <= ABSOLUTE_MAXIMUM_FRAME_BYTES
        && profile.maximum_observation_bytes > 0
        && profile.maximum_observation_bytes <= ABSOLUTE_MAXIMUM_FRAME_BYTES
        && profile.maximum_receipt_bytes > 0
        && profile.maximum_receipt_bytes <= ABSOLUTE_MAXIMUM_RECEIPT_BYTES
        && profile.maximum_cpu_quota_millis > 0
        && profile.maximum_cpu_time_ms > 0
        && profile.maximum_wall_time_overrun_ms > 0
        && profile.maximum_cpu_time_overrun_ms > 0
        && profile.maximum_memory_bytes > 0
        && profile.maximum_memory_overrun_bytes > 0
        && profile.maximum_disk_bytes > 0
        && profile.maximum_disk_overrun_bytes > 0
        && profile.maximum_entries > 0
        && profile.maximum_entries_overrun > 0
        // Every submitted operation runs beneath the trusted PID 1 launcher,
        // and the whole-container ceiling includes both processes.
        && profile.maximum_pids >= 2
        && profile.maximum_pids_overrun > 0
        && !profile.platform.is_empty()
}

fn valid_material_projection(
    projection: &TrialMaterialProjectionProfile,
    source_roles: &HashSet<&String>,
) -> bool {
    valid_identifier(&projection.role)
        && source_roles.contains(&projection.source_role)
        && matches!(
            projection.projection_kind.as_str(),
            "build_context" | "state_seed" | "state_overlay"
        )
        && safe_relative_path(&projection.source_relative, true)
        && safe_relative_path(&projection.destination_relative, true)
        && !(projection.projection_kind == "state_overlay"
            && (projection.destination_relative == "."
                || projection.destination_relative.contains('/')))
        && projection
            .exclusions
            .iter()
            .all(|value| safe_relative_path(value, false))
        && projection
            .exclusions
            .windows(2)
            .all(|items| items[0] < items[1])
        && !projection_destinations_overlap(projection.exclusions.iter().map(String::as_str))
}

fn projection_destinations_overlap<'a>(values: impl Iterator<Item = &'a str>) -> bool {
    let values = values.collect::<Vec<_>>();
    values.iter().enumerate().any(|(index, left)| {
        values[index + 1..].iter().any(|right| {
            left == right
                || *left == "."
                || *right == "."
                || left
                    .strip_prefix(*right)
                    .is_some_and(|suffix| suffix.starts_with('/'))
                || right
                    .strip_prefix(*left)
                    .is_some_and(|suffix| suffix.starts_with('/'))
        })
    })
}

fn valid_identity(identity: &TrialRequestIdentity) -> bool {
    valid_sha256(&identity.request_digest)
        && valid_sha256(&identity.material_binding_digest)
        && valid_sha256(&identity.input_digest)
        && valid_sha256(&identity.materials_digest)
        && [
            &identity.project_id,
            &identity.task_id,
            &identity.assignment_id,
            &identity.submission_id,
            &identity.registry_entry_id,
            &identity.evaluation_request_id,
            &identity.checker_run_id,
            &identity.attempt_id,
            &identity.result_id,
            &identity.worker_lease_id,
        ]
        .into_iter()
        .all(|value| valid_uuid(value))
        && identity.submission_version > 0
        && identity.evaluation_generation > 0
        && identity.worker_lease_generation > 0
        && valid_identifier(&identity.requirement_id)
        && valid_sha256(&identity.registry_entry_digest)
        && valid_sha256(&identity.checker_image_digest)
        && valid_sha256(&identity.configuration_sha256)
        && !identity.worker_lease_expires_at.is_empty()
        && identity.worker_lease_expires_at.len() <= 64
        && !identity
            .worker_lease_expires_at
            .chars()
            .any(char::is_control)
}

fn validate_plan(plan: &TrialPlan, profile: &TrialProfile) -> Result<(), TrialRelayFailure> {
    let planned_timeout_ms = plan
        .steps
        .iter()
        .try_fold(plan.build_timeout_ms, |total, step| {
            total.checked_add(step.timeout_ms)
        })
        .ok_or(TrialRelayFailure::InvalidRequest)?;
    if plan.schema_version != TRIAL_PLAN_SCHEMA
        || !safe_relative_path(&plan.environment.dockerfile, false)
        || !safe_relative_path(&plan.environment.context, true)
        || plan.environment.platform != profile.platform
        || plan.build_timeout_ms == 0
        || plan.build_timeout_ms > profile.maximum_build_timeout_ms
        || planned_timeout_ms > profile.maximum_total_timeout_ms
        || plan.steps.is_empty()
        || plan.steps.len() > profile.maximum_steps
        || plan.resources.cpu_quota_millis == 0
        || plan.resources.cpu_quota_millis > profile.maximum_cpu_quota_millis
        || plan.resources.cpu_time_ms == 0
        || plan.resources.cpu_time_ms > profile.maximum_cpu_time_ms
        || plan.resources.memory_bytes == 0
        || plan.resources.memory_bytes > profile.maximum_memory_bytes
        || plan.resources.disk_bytes == 0
        || plan.resources.disk_bytes > profile.maximum_disk_bytes
        || plan.resources.maximum_entries == 0
        || plan.resources.maximum_entries > profile.maximum_entries
        || plan.resources.pids < 2
        || plan.resources.pids > profile.maximum_pids
    {
        return Err(TrialRelayFailure::InvalidRequest);
    }
    let mut completed_ids = HashSet::new();
    let mut counts = vec![0_usize; profile.slot_templates.len()];
    let mut previous_template = 0_usize;
    for step in &plan.steps {
        let Some((template_index, expected)) = profile
            .slot_templates
            .iter()
            .enumerate()
            .find(|(_, template)| template.slot_kind == step.slot_kind)
        else {
            return Err(TrialRelayFailure::InvalidRequest);
        };
        let expected_roles: HashSet<_> = expected.visible_roles.iter().collect();
        let actual_roles: HashSet<_> = step.visible_roles.iter().collect();
        if !valid_identifier(&step.slot_id)
            || completed_ids.contains(&step.slot_id)
            || !valid_identifier(&step.slot_kind)
            || template_index < previous_template
            || counts[template_index] >= expected.maximum_occurrences
            || step.operation != "run"
            || expected_roles != actual_roles
            || expected.visible_roles.len() != step.visible_roles.len()
            || step.command.is_empty()
            || step.command.len() > 64
            || step.command.iter().any(|value| {
                value.is_empty() || value.len() > 4096 || value.as_bytes().contains(&0)
            })
            || !safe_relative_path(&step.working_directory, true)
            || step.timeout_ms == 0
            || step.timeout_ms > profile.maximum_step_timeout_ms
            || (expected.fresh_workspace && step.state_source != "fresh")
            || (!expected.fresh_workspace
                && step.state_source != "fresh"
                && !completed_ids.contains(&step.state_source))
        {
            return Err(TrialRelayFailure::InvalidRequest);
        }
        completed_ids.insert(step.slot_id.clone());
        counts[template_index] += 1;
        previous_template = template_index;
    }
    if profile
        .slot_templates
        .iter()
        .zip(counts)
        .any(|(template, count)| {
            count < template.minimum_occurrences || count > template.maximum_occurrences
        })
    {
        return Err(TrialRelayFailure::InvalidRequest);
    }
    Ok(())
}

fn relay_once(
    listener: UnixListener,
    context: &TrialEngineContext,
    publisher: Arc<dyn TrialReceiptPublisher>,
    engine: Arc<dyn TrialEngine>,
    deadline: Instant,
    relay_cancelled: &AtomicBool,
    invocation_cancelled: &AtomicBool,
) -> WorkerOutcome {
    let mut stream = match accept_until(&listener, deadline, relay_cancelled, invocation_cancelled)
    {
        Ok(stream) => stream,
        Err(code) => return failed_outcome(code, false, false),
    };
    let frame = match read_frame_until(
        &mut stream,
        context.profile.maximum_frame_bytes,
        deadline,
        relay_cancelled,
        invocation_cancelled,
    ) {
        Ok(frame) => frame,
        Err(code) => {
            let _ = write_unavailable(
                &mut stream,
                code,
                context.profile.maximum_response_bytes,
                deadline,
            );
            return failed_outcome(code, false, false);
        }
    };
    let request: ImageTrialRequest = match serde_json::from_slice(&frame) {
        Ok(request) => request,
        Err(_) => {
            let code = TrialRelayFailure::InvalidRequest;
            let _ = write_unavailable(
                &mut stream,
                code,
                context.profile.maximum_response_bytes,
                deadline,
            );
            return failed_outcome(code, false, false);
        }
    };
    if request.protocol_version != TRIAL_PROTOCOL
        || request.operation != "execute_plan"
        || validate_plan(&request.plan, &context.profile).is_err()
    {
        let code = TrialRelayFailure::InvalidRequest;
        let _ = write_unavailable(
            &mut stream,
            code,
            context.profile.maximum_response_bytes,
            deadline,
        );
        return failed_outcome(code, false, false);
    }
    let subject = match trial_evidence_subject(context, &request.plan) {
        Ok(subject) => subject,
        Err(code) => {
            let _ = write_unavailable(
                &mut stream,
                code,
                context.profile.maximum_response_bytes,
                deadline,
            );
            return failed_outcome(code, false, false);
        }
    };
    let trial_evidence_id = match publisher.reserve_completed(subject) {
        Ok(TrialReceiptReservation::Fresh { trial_evidence_id })
            if valid_uuid(&trial_evidence_id) =>
        {
            trial_evidence_id
        }
        Ok(TrialReceiptReservation::Retained {
            trial_evidence_id,
            receipt,
            published,
        }) if valid_uuid(&trial_evidence_id)
            && validate_retained_receipt(&receipt, context, &request.plan).is_ok()
            && valid_receipt_handle(&published.receipt_handle)
            && valid_custody_ack(
                &published.custody,
                &receipt.receipt_digest,
                receipt.byte_count,
            ) =>
        {
            let observations = observation_projection(&receipt.facts);
            let response = CompletedImageTrialResponse {
                protocol_version: TRIAL_PROTOCOL,
                outcome: "completed",
                receipt_handle: &published.receipt_handle,
                receipt_digest: &receipt.receipt_digest,
                observations: &observations,
                failure_code: None,
            };
            if write_json_frame(
                &mut stream,
                &response,
                context.profile.maximum_response_bytes,
                deadline,
            )
            .is_err()
            {
                return failed_outcome(TrialRelayFailure::ImplementationUnavailable, false, false);
            }
            return WorkerOutcome {
                failure: None,
                cleanup_unsettled: false,
                plan_started: false,
                plan_completed: true,
                receipt_handle: Some(published.receipt_handle),
                receipt_digest: Some(receipt.receipt_digest),
            };
        }
        Ok(_) => {
            let code = TrialRelayFailure::ImplementationUnavailable;
            let _ = write_unavailable(
                &mut stream,
                code,
                context.profile.maximum_response_bytes,
                deadline,
            );
            return failed_outcome(code, false, false);
        }
        Err(failure) => {
            eprintln!("trial unavailable: stage=reserve code={:?}", failure.code);
            let _ = write_unavailable(
                &mut stream,
                failure.code,
                context.profile.maximum_response_bytes,
                deadline,
            );
            return failed_outcome(failure.code, false, false);
        }
    };
    let execution = match engine.execute(
        context,
        &request.plan,
        deadline,
        invocation_cancelled,
        relay_cancelled,
    ) {
        Ok(execution) => execution,
        Err(failure) => {
            let code = if failure.cleanup_unsettled {
                TrialRelayFailure::CleanupUnsettled
            } else {
                failure.code
            };
            eprintln!("trial unavailable: stage=execute code={code:?}");
            let _ = write_unavailable(
                &mut stream,
                code,
                context.profile.maximum_response_bytes,
                deadline,
            );
            return failed_outcome(code, true, failure.cleanup_unsettled);
        }
    };
    if let Err(code) = validate_execution(&execution, &request.plan, &context.profile) {
        eprintln!("trial unavailable: stage=validate_execution code={code:?}");
        let _ = write_unavailable(
            &mut stream,
            code,
            context.profile.maximum_response_bytes,
            deadline,
        );
        return failed_outcome(code, true, code == TrialRelayFailure::CleanupUnsettled);
    }
    let receipt = match canonical_receipt(context, request.plan, execution) {
        Ok(receipt) => receipt,
        Err(code) => {
            eprintln!("trial unavailable: stage=receipt code={code:?}");
            let _ = write_unavailable(
                &mut stream,
                code,
                context.profile.maximum_response_bytes,
                deadline,
            );
            return failed_outcome(code, true, false);
        }
    };
    let receipt_digest = receipt.receipt_digest.clone();
    let receipt_byte_count = receipt.byte_count;
    let observations = observation_projection(&receipt.facts);
    let published = match publisher.publish_completed(&trial_evidence_id, receipt) {
        Ok(published)
            if valid_receipt_handle(&published.receipt_handle)
                && valid_custody_ack(&published.custody, &receipt_digest, receipt_byte_count) =>
        {
            published
        }
        Ok(_) => {
            let code = TrialRelayFailure::ImplementationUnavailable;
            let _ = write_unavailable(
                &mut stream,
                code,
                context.profile.maximum_response_bytes,
                deadline,
            );
            return failed_outcome(code, true, false);
        }
        Err(failure) => {
            eprintln!("trial unavailable: stage=publish code={:?}", failure.code);
            let _ = write_unavailable(
                &mut stream,
                failure.code,
                context.profile.maximum_response_bytes,
                deadline,
            );
            return failed_outcome(
                failure.code,
                true,
                failure.code == TrialRelayFailure::CleanupUnsettled,
            );
        }
    };
    let response = CompletedImageTrialResponse {
        protocol_version: TRIAL_PROTOCOL,
        outcome: "completed",
        receipt_handle: &published.receipt_handle,
        receipt_digest: &receipt_digest,
        observations: &observations,
        failure_code: None,
    };
    if write_json_frame(
        &mut stream,
        &response,
        context.profile.maximum_response_bytes,
        deadline,
    )
    .is_err()
    {
        return failed_outcome(TrialRelayFailure::ImplementationUnavailable, true, false);
    }
    WorkerOutcome {
        failure: None,
        cleanup_unsettled: false,
        plan_started: true,
        plan_completed: true,
        receipt_handle: Some(published.receipt_handle),
        receipt_digest: Some(receipt_digest),
    }
}

fn observation_projection(receipt: &TrialReceiptPublication) -> TrialObservationProjection {
    let build = &receipt.execution.build;
    TrialObservationProjection {
        schema_version: "workstream.checker_trial_observations.v1",
        terminal_state: "completed_work",
        profile_digest: receipt.profile_digest.clone(),
        engine_identity_digest: receipt.engine_identity_digest.clone(),
        plan_digest: receipt.plan_digest.clone(),
        observation_digest: receipt.observation_digest.clone(),
        build: TrialBuildProjection {
            terminal_state: "completed_work",
            outcome: build.outcome,
            export_outcome: build.export_outcome,
            exit_code: build.exit_code,
            signal: build.signal,
            stdout_sha256: build.stdout_sha256.clone(),
            stdout_byte_count: build.stdout.len(),
            stderr_sha256: build.stderr_sha256.clone(),
            stderr_byte_count: build.stderr.len(),
            candidate_image_digest: build.candidate_image_digest.clone(),
            candidate_archive_digest: build.candidate_archive_digest.clone(),
            measurements_available: true,
            elapsed_ms: build.elapsed_ms,
            cpu_time_ms: build.cpu_time_ms,
            peak_memory_bytes: build.peak_memory_bytes,
            peak_pids: build.peak_pids,
            written_bytes: build.written_bytes,
            written_entries: build.written_entries,
            measurement_method: build.measurement_method.clone(),
        },
        steps: receipt
            .execution
            .steps
            .iter()
            .map(|step| TrialStepProjection {
                terminal_state: "completed_work",
                slot_id: step.slot_id.clone(),
                operation_order: step.operation_order,
                outcome: step.outcome,
                export_outcome: step.export_outcome,
                exit_code: step.exit_code,
                signal: step.signal,
                stdout_sha256: step.stdout_sha256.clone(),
                stdout_byte_count: step.stdout.len(),
                stderr_sha256: step.stderr_sha256.clone(),
                stderr_byte_count: step.stderr.len(),
                workspace_before_sha256: step.workspace_before_sha256.clone(),
                workspace_after_sha256: step.workspace_after_sha256.clone(),
                measurements_available: true,
                elapsed_ms: step.elapsed_ms,
                cpu_time_ms: step.cpu_time_ms,
                peak_memory_bytes: step.peak_memory_bytes,
                peak_pids: step.peak_pids,
                written_bytes: step.written_bytes,
                written_entries: step.written_entries,
                measurement_method: step.measurement_method.clone(),
            })
            .collect(),
    }
}

fn canonical_receipt(
    context: &TrialEngineContext,
    plan: TrialPlan,
    execution: TrialExecution,
) -> Result<CanonicalTrialReceipt, TrialRelayFailure> {
    let plan_value =
        serde_json::to_value(&plan).map_err(|_| TrialRelayFailure::ImplementationUnavailable)?;
    let execution_value = serde_json::to_value(&execution)
        .map_err(|_| TrialRelayFailure::ImplementationUnavailable)?;
    let observation_bytes = canonical_json(&execution_value)
        .map_err(|_| TrialRelayFailure::ImplementationUnavailable)?
        .len();
    if observation_bytes > context.profile.maximum_observation_bytes {
        return Err(TrialRelayFailure::CapacityExceeded);
    }
    let facts = TrialReceiptPublication {
        schema_version: TRIAL_RECEIPT_SCHEMA.into(),
        request_identity_digest: context.identity.request_digest.clone(),
        originating_identity: context.identity.clone(),
        material_binding_digest: context.identity.material_binding_digest.clone(),
        profile_id: context.profile.profile_id.clone(),
        profile_version: context.profile.profile_version,
        profile_digest: context.profile.profile_digest.clone(),
        trial_kind: context.profile.trial_kind.clone(),
        engine_identity_digest: context.profile.engine_identity_digest.clone(),
        plan_digest: canonical_hash(&plan_value)
            .map_err(|_| TrialRelayFailure::ImplementationUnavailable)?,
        observation_digest: canonical_hash(&execution_value)
            .map_err(|_| TrialRelayFailure::ImplementationUnavailable)?,
        observation_byte_count: observation_bytes,
        slot_ids: plan.steps.iter().map(|step| step.slot_id.clone()).collect(),
        plan_started: true,
        plan_completed: true,
        cleanup_confirmed: true,
        plan,
        execution,
    };
    let value =
        serde_json::to_value(&facts).map_err(|_| TrialRelayFailure::ImplementationUnavailable)?;
    let canonical = canonical_json(&value)
        .map_err(|_| TrialRelayFailure::ImplementationUnavailable)?
        .into_bytes();
    if canonical.is_empty() || canonical.len() > context.profile.maximum_receipt_bytes {
        return Err(TrialRelayFailure::CapacityExceeded);
    }
    let receipt_digest =
        canonical_hash(&value).map_err(|_| TrialRelayFailure::ImplementationUnavailable)?;
    Ok(CanonicalTrialReceipt {
        receipt_digest,
        byte_count: canonical.len(),
        canonical_bytes: canonical,
        facts,
    })
}

fn trial_evidence_subject(
    context: &TrialEngineContext,
    plan: &TrialPlan,
) -> Result<TrialEvidenceSubject, TrialRelayFailure> {
    let plan_value =
        serde_json::to_value(plan).map_err(|_| TrialRelayFailure::ImplementationUnavailable)?;
    Ok(TrialEvidenceSubject {
        project_id: context.identity.project_id.clone(),
        task_id: context.identity.task_id.clone(),
        assignment_id: context.identity.assignment_id.clone(),
        submission_id: context.identity.submission_id.clone(),
        submission_version: context.identity.submission_version,
        requirement_id: context.identity.requirement_id.clone(),
        registry_entry_id: context.identity.registry_entry_id.clone(),
        registry_entry_digest: context.identity.registry_entry_digest.clone(),
        configuration_sha256: context.identity.configuration_sha256.clone(),
        trial_kind: context.profile.trial_kind.clone(),
        slot_index: 0,
        plan_sha256: canonical_hash(&plan_value)
            .map_err(|_| TrialRelayFailure::ImplementationUnavailable)?,
        input_digest: context.identity.input_digest.clone(),
        materials_digest: context.identity.materials_digest.clone(),
    })
}

fn validate_retained_receipt(
    receipt: &CanonicalTrialReceipt,
    context: &TrialEngineContext,
    plan: &TrialPlan,
) -> Result<(), TrialRelayFailure> {
    let value = serde_json::to_value(&receipt.facts)
        .map_err(|_| TrialRelayFailure::ImplementationUnavailable)?;
    let canonical = canonical_json(&value)
        .map_err(|_| TrialRelayFailure::ImplementationUnavailable)?
        .into_bytes();
    let expected_digest =
        canonical_hash(&value).map_err(|_| TrialRelayFailure::ImplementationUnavailable)?;
    let expected_plan = trial_evidence_subject(context, plan)?.plan_sha256;
    if canonical != receipt.canonical_bytes
        || receipt.byte_count != canonical.len()
        || receipt.byte_count == 0
        || receipt.byte_count > context.profile.maximum_receipt_bytes
        || receipt.receipt_digest != expected_digest
        || receipt.facts.schema_version != TRIAL_RECEIPT_SCHEMA
        || !same_stable_trial_identity(&receipt.facts.originating_identity, &context.identity)
        || receipt.facts.profile_id != context.profile.profile_id
        || receipt.facts.profile_version != context.profile.profile_version
        || receipt.facts.profile_digest != context.profile.profile_digest
        || receipt.facts.trial_kind != context.profile.trial_kind
        || receipt.facts.engine_identity_digest != context.profile.engine_identity_digest
        || receipt.facts.plan_digest != expected_plan
        || receipt.facts.plan != *plan
        || receipt.facts.slot_ids
            != plan
                .steps
                .iter()
                .map(|step| step.slot_id.clone())
                .collect::<Vec<_>>()
        || !receipt.facts.plan_started
        || !receipt.facts.plan_completed
        || !receipt.facts.cleanup_confirmed
    {
        return Err(TrialRelayFailure::ImplementationUnavailable);
    }
    validate_execution(&receipt.facts.execution, plan, &context.profile)
}

fn same_stable_trial_identity(
    original: &TrialRequestIdentity,
    current: &TrialRequestIdentity,
) -> bool {
    original.project_id == current.project_id
        && original.task_id == current.task_id
        && original.assignment_id == current.assignment_id
        && original.submission_id == current.submission_id
        && original.submission_version == current.submission_version
        && original.requirement_id == current.requirement_id
        && original.registry_entry_id == current.registry_entry_id
        && original.registry_entry_digest == current.registry_entry_digest
        && original.checker_image_digest == current.checker_image_digest
        && original.configuration_sha256 == current.configuration_sha256
        && original.input_digest == current.input_digest
        && original.materials_digest == current.materials_digest
}

fn validate_execution(
    execution: &TrialExecution,
    plan: &TrialPlan,
    profile: &TrialProfile,
) -> Result<(), TrialRelayFailure> {
    if !execution.cleanup_confirmed {
        return Err(TrialRelayFailure::CleanupUnsettled);
    }
    if execution.platform_identity_digest != profile.platform_identity_digest
        || execution.builder_image_digest != profile.builder_image_digest
        || execution.trusted_launcher_digest != profile.trusted_launcher_digest
        || execution.offline_cache_digest != profile.offline_cache_digest
        || execution.base_image_digests != profile.approved_base_digests
        || execution.steps.len() != plan.steps.len()
        || !valid_build_observation(&execution.build, plan, profile)
        || !valid_role_inventory(
            &execution.material_inventory_digests,
            &profile.allowed_material_roles,
        )
    {
        return Err(TrialRelayFailure::ImplementationUnavailable);
    }
    let build_succeeded = execution.build.outcome == TrialOperationOutcome::Succeeded;
    let aggregate_cpu_time_ms = execution
        .steps
        .iter()
        .try_fold(execution.build.cpu_time_ms, |total, item| {
            total.checked_add(item.cpu_time_ms)
        });
    let cpu_exceeded = execution.build.outcome == TrialOperationOutcome::CpuExceeded
        || execution
            .steps
            .iter()
            .any(|item| item.outcome == TrialOperationOutcome::CpuExceeded);
    if aggregate_cpu_time_ms.is_none_or(|value| {
        !measured_limit(
            value,
            plan.resources.cpu_time_ms,
            profile.maximum_cpu_time_overrun_ms,
            cpu_exceeded,
        )
    }) {
        return Err(TrialRelayFailure::ImplementationUnavailable);
    }
    let mut retained_slots = HashSet::new();
    let mut consumed_cpu_time_ms = execution.build.cpu_time_ms;
    let mut invocation_capacity_exhausted =
        execution.build.outcome == TrialOperationOutcome::DiskExceeded;
    for (index, (observation, step)) in execution.steps.iter().zip(&plan.steps).enumerate() {
        let slot_profile = profile
            .slot_templates
            .iter()
            .find(|template| template.slot_kind == step.slot_kind)
            .ok_or(TrialRelayFailure::ImplementationUnavailable)?;
        let dependency_succeeded =
            step.state_source == "fresh" || retained_slots.contains(step.state_source.as_str());
        let cpu_exhausted = consumed_cpu_time_ms >= plan.resources.cpu_time_ms;
        let remaining_cpu_time_ms = plan
            .resources
            .cpu_time_ms
            .saturating_sub(consumed_cpu_time_ms);
        let must_skip = !build_succeeded
            || !dependency_succeeded
            || cpu_exhausted
            || invocation_capacity_exhausted;
        if observation.slot_id != step.slot_id
            || observation.operation_order != (index + 1) as u32
            || !valid_identifier(&observation.workspace_identity)
            || !valid_identifier(&observation.measurement_method)
            || !valid_sha256(&observation.stdout_sha256)
            || !valid_sha256(&observation.stderr_sha256)
            || !valid_sha256(&observation.workspace_before_sha256)
            || !valid_sha256(&observation.workspace_after_sha256)
            || sha256_text(&observation.stdout) != observation.stdout_sha256
            || sha256_text(&observation.stderr) != observation.stderr_sha256
            || observation
                .stdout
                .len()
                .saturating_add(observation.stderr.len())
                > profile.maximum_step_output_bytes
            || !valid_measured_resources(
                observation.outcome,
                observation.elapsed_ms,
                step.timeout_ms,
                observation.cpu_time_ms,
                remaining_cpu_time_ms,
                observation.peak_memory_bytes,
                plan.resources.memory_bytes,
                observation.peak_pids,
                plan.resources.pids,
                observation.written_bytes,
                plan.resources.disk_bytes,
                observation.written_entries,
                plan.resources.maximum_entries,
                profile,
            )
            || !valid_role_inventory(
                &observation.visible_role_inventory_digests,
                &step.visible_roles,
            )
            || !valid_operation_outcome(
                observation.outcome,
                observation.export_outcome,
                observation.exit_code,
                observation.signal,
                &observation.stdout,
                &observation.stderr,
                must_skip,
            )
            || (must_skip
                && (observation.elapsed_ms != 0
                    || observation.cpu_time_ms != 0
                    || observation.peak_memory_bytes != 0
                    || observation.peak_pids != 0
                    || observation.written_bytes != 0
                    || observation.written_entries != 0))
        {
            return Err(TrialRelayFailure::ImplementationUnavailable);
        }
        consumed_cpu_time_ms = consumed_cpu_time_ms
            .checked_add(observation.cpu_time_ms)
            .ok_or(TrialRelayFailure::ImplementationUnavailable)?;
        invocation_capacity_exhausted |= observation.outcome == TrialOperationOutcome::DiskExceeded;
        if observation.export_outcome == TrialExportOutcome::Exported
            && slot_profile
                .retain_state_after
                .iter()
                .any(|value| value == trial_outcome_name(observation.outcome))
        {
            retained_slots.insert(observation.slot_id.as_str());
        }
    }
    Ok(())
}

fn trial_outcome_name(outcome: TrialOperationOutcome) -> &'static str {
    match outcome {
        TrialOperationOutcome::Succeeded => "succeeded",
        TrialOperationOutcome::ExitNonzero => "exit_nonzero",
        TrialOperationOutcome::Signalled => "signalled",
        TrialOperationOutcome::DeadlineExceeded => "deadline_exceeded",
        TrialOperationOutcome::CpuExceeded => "cpu_exceeded",
        TrialOperationOutcome::MemoryExceeded => "memory_exceeded",
        TrialOperationOutcome::PidExceeded => "pid_exceeded",
        TrialOperationOutcome::DiskExceeded => "disk_exceeded",
        TrialOperationOutcome::OutputExceeded => "output_exceeded",
        TrialOperationOutcome::ExportInvalid => "export_invalid",
        TrialOperationOutcome::DependencySkipped => "dependency_skipped",
    }
}

fn valid_build_observation(
    observation: &TrialBuildObservation,
    plan: &TrialPlan,
    profile: &TrialProfile,
) -> bool {
    valid_identifier(&observation.measurement_method)
        && valid_sha256(&observation.stdout_sha256)
        && valid_sha256(&observation.stderr_sha256)
        && sha256_text(&observation.stdout) == observation.stdout_sha256
        && sha256_text(&observation.stderr) == observation.stderr_sha256
        && observation
            .stdout
            .len()
            .saturating_add(observation.stderr.len())
            <= profile.maximum_step_output_bytes
        && observation
            .candidate_image_digest
            .as_deref()
            .is_none_or(valid_sha256)
        && observation
            .candidate_archive_digest
            .as_deref()
            .is_none_or(valid_sha256)
        && valid_measured_resources(
            observation.outcome,
            observation.elapsed_ms,
            plan.build_timeout_ms,
            observation.cpu_time_ms,
            plan.resources.cpu_time_ms,
            observation.peak_memory_bytes,
            plan.resources.memory_bytes,
            observation.peak_pids,
            plan.resources.pids,
            observation.written_bytes,
            plan.resources.disk_bytes,
            observation.written_entries,
            plan.resources.maximum_entries,
            profile,
        )
        && (observation.candidate_image_digest.is_none()
            == observation.candidate_archive_digest.is_none())
        && valid_build_outcome(observation)
        && profile
            .approved_base_digests
            .iter()
            .all(|digest| valid_sha256(digest))
}

fn valid_build_outcome(observation: &TrialBuildObservation) -> bool {
    let has_candidate = observation.candidate_image_digest.is_some();
    match (observation.outcome, observation.export_outcome) {
        (TrialOperationOutcome::Succeeded, TrialExportOutcome::Exported) => {
            has_candidate && observation.exit_code == Some(0) && observation.signal.is_none()
        }
        (TrialOperationOutcome::ExitNonzero, TrialExportOutcome::NotStarted) => {
            !has_candidate
                && observation
                    .exit_code
                    .is_some_and(|value| (1..=255).contains(&value))
                && observation.signal.is_none()
        }
        (TrialOperationOutcome::Signalled, TrialExportOutcome::NotStarted) => {
            !has_candidate
                && observation.exit_code.is_none()
                && observation
                    .signal
                    .is_some_and(|value| (1..=64).contains(&value))
        }
        (
            TrialOperationOutcome::DeadlineExceeded
            | TrialOperationOutcome::CpuExceeded
            | TrialOperationOutcome::MemoryExceeded
            | TrialOperationOutcome::PidExceeded
            | TrialOperationOutcome::DiskExceeded
            | TrialOperationOutcome::OutputExceeded,
            TrialExportOutcome::Unavailable,
        ) => !has_candidate && observation.exit_code.is_none() && observation.signal.is_none(),
        (TrialOperationOutcome::DiskExceeded, TrialExportOutcome::CapacityExceeded) => {
            !has_candidate && valid_actual_child(observation.exit_code, observation.signal)
        }
        (TrialOperationOutcome::ExportInvalid, TrialExportOutcome::Invalid) => {
            !has_candidate && valid_actual_child(observation.exit_code, observation.signal)
        }
        _ => false,
    }
}

#[allow(clippy::too_many_arguments)]
fn valid_measured_resources(
    outcome: TrialOperationOutcome,
    elapsed_ms: u64,
    timeout_ms: u64,
    cpu_time_ms: u64,
    cpu_time_limit_ms: u64,
    peak_memory_bytes: u64,
    memory_limit_bytes: u64,
    peak_pids: u64,
    pids_limit: u64,
    written_bytes: u64,
    disk_limit_bytes: u64,
    written_entries: u64,
    entries_limit: u64,
    profile: &TrialProfile,
) -> bool {
    measured_limit(
        elapsed_ms,
        timeout_ms,
        profile.maximum_wall_time_overrun_ms,
        outcome == TrialOperationOutcome::DeadlineExceeded,
    ) && upper_with_overrun(
        cpu_time_ms,
        cpu_time_limit_ms,
        profile.maximum_cpu_time_overrun_ms,
        outcome == TrialOperationOutcome::CpuExceeded,
    ) && measured_limit(
        peak_memory_bytes,
        memory_limit_bytes,
        profile.maximum_memory_overrun_bytes,
        outcome == TrialOperationOutcome::MemoryExceeded,
    ) && measured_limit(
        peak_pids,
        pids_limit,
        profile.maximum_pids_overrun,
        outcome == TrialOperationOutcome::PidExceeded,
    ) && valid_disk_measurement(
        written_bytes,
        disk_limit_bytes,
        profile.maximum_disk_overrun_bytes,
        written_entries,
        entries_limit,
        profile.maximum_entries_overrun,
        outcome == TrialOperationOutcome::DiskExceeded,
    )
}

fn valid_disk_measurement(
    bytes: u64,
    byte_limit: u64,
    byte_overrun: u64,
    entries: u64,
    entry_limit: u64,
    entry_overrun: u64,
    exceeded: bool,
) -> bool {
    if exceeded {
        byte_limit
            .checked_add(byte_overrun)
            .is_some_and(|upper| bytes <= upper)
            && entry_limit
                .checked_add(entry_overrun)
                .is_some_and(|upper| entries <= upper)
    } else {
        bytes <= byte_limit && entries <= entry_limit
    }
}

fn measured_limit(observed: u64, limit: u64, overrun: u64, exceeded: bool) -> bool {
    if exceeded {
        observed > limit
            && limit
                .checked_add(overrun)
                .is_some_and(|upper| observed <= upper)
    } else {
        observed <= limit
    }
}

fn upper_with_overrun(observed: u64, limit: u64, overrun: u64, exceeded: bool) -> bool {
    if exceeded {
        limit
            .checked_add(overrun)
            .is_some_and(|upper| observed <= upper)
    } else {
        observed <= limit
    }
}

fn valid_operation_outcome(
    outcome: TrialOperationOutcome,
    export_outcome: TrialExportOutcome,
    exit_code: Option<i32>,
    signal: Option<i32>,
    stdout: &str,
    stderr: &str,
    must_skip: bool,
) -> bool {
    if must_skip {
        return outcome == TrialOperationOutcome::DependencySkipped
            && export_outcome == TrialExportOutcome::NotStarted
            && exit_code.is_none()
            && signal.is_none()
            && stdout.is_empty()
            && stderr.is_empty();
    }
    match (outcome, export_outcome) {
        (TrialOperationOutcome::Succeeded, TrialExportOutcome::Exported) => {
            exit_code == Some(0) && signal.is_none()
        }
        (TrialOperationOutcome::ExitNonzero, TrialExportOutcome::Exported) => {
            exit_code.is_some_and(|value| (1..=255).contains(&value)) && signal.is_none()
        }
        (TrialOperationOutcome::Signalled, TrialExportOutcome::Exported) => {
            exit_code.is_none() && signal.is_some_and(|value| (1..=64).contains(&value))
        }
        (
            TrialOperationOutcome::DeadlineExceeded
            | TrialOperationOutcome::CpuExceeded
            | TrialOperationOutcome::MemoryExceeded
            | TrialOperationOutcome::PidExceeded
            | TrialOperationOutcome::DiskExceeded
            | TrialOperationOutcome::OutputExceeded,
            TrialExportOutcome::Unavailable,
        ) => exit_code.is_none() && signal.is_none(),
        (TrialOperationOutcome::DiskExceeded, TrialExportOutcome::CapacityExceeded)
        | (TrialOperationOutcome::ExportInvalid, TrialExportOutcome::Invalid) => {
            valid_actual_child(exit_code, signal)
        }
        _ => false,
    }
}

fn valid_actual_child(exit_code: Option<i32>, signal: Option<i32>) -> bool {
    matches!(
        (exit_code, signal),
        (Some(0..=255), None) | (None, Some(1..=64))
    )
}

fn valid_role_inventory(values: &[RoleInventoryDigest], expected: &[String]) -> bool {
    let mut roles = HashSet::new();
    values.len() == expected.len()
        && values.iter().all(|value| {
            valid_identifier(&value.role)
                && valid_sha256(&value.digest)
                && roles.insert(value.role.as_str())
        })
        && roles == expected.iter().map(String::as_str).collect()
}

fn failed_outcome(
    code: TrialRelayFailure,
    plan_started: bool,
    cleanup_unsettled: bool,
) -> WorkerOutcome {
    WorkerOutcome {
        failure: Some(code),
        cleanup_unsettled,
        plan_started,
        plan_completed: false,
        receipt_handle: None,
        receipt_digest: None,
    }
}

fn accept_until(
    listener: &UnixListener,
    deadline: Instant,
    relay_cancelled: &AtomicBool,
    invocation_cancelled: &AtomicBool,
) -> Result<UnixStream, TrialRelayFailure> {
    loop {
        check_available(deadline, relay_cancelled, invocation_cancelled)?;
        match listener.accept() {
            Ok((stream, _)) => {
                stream
                    .set_nonblocking(true)
                    .map_err(|_| TrialRelayFailure::ImplementationUnavailable)?;
                return Ok(stream);
            }
            Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                thread::park_timeout(Duration::from_millis(2));
            }
            Err(_) => return Err(TrialRelayFailure::ImplementationUnavailable),
        }
    }
}

fn read_frame_until(
    stream: &mut UnixStream,
    maximum: usize,
    deadline: Instant,
    relay_cancelled: &AtomicBool,
    invocation_cancelled: &AtomicBool,
) -> Result<Vec<u8>, TrialRelayFailure> {
    let mut length = [0_u8; 4];
    read_exact_until(
        stream,
        &mut length,
        deadline,
        relay_cancelled,
        invocation_cancelled,
    )?;
    let length = u32::from_be_bytes(length) as usize;
    if length == 0 || length > maximum {
        return Err(TrialRelayFailure::InvalidRequest);
    }
    let mut bytes = vec![0_u8; length];
    read_exact_until(
        stream,
        &mut bytes,
        deadline,
        relay_cancelled,
        invocation_cancelled,
    )?;
    Ok(bytes)
}

fn read_exact_until(
    stream: &mut UnixStream,
    mut bytes: &mut [u8],
    deadline: Instant,
    relay_cancelled: &AtomicBool,
    invocation_cancelled: &AtomicBool,
) -> Result<(), TrialRelayFailure> {
    while !bytes.is_empty() {
        check_available(deadline, relay_cancelled, invocation_cancelled)?;
        match stream.read(bytes) {
            Ok(0) => return Err(TrialRelayFailure::InvalidRequest),
            Ok(count) => bytes = &mut bytes[count..],
            Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                thread::park_timeout(Duration::from_millis(2));
            }
            Err(_) => return Err(TrialRelayFailure::ImplementationUnavailable),
        }
    }
    Ok(())
}

fn write_unavailable(
    stream: &mut UnixStream,
    code: TrialRelayFailure,
    maximum: usize,
    deadline: Instant,
) -> Result<(), TrialRelayFailure> {
    write_json_frame(
        stream,
        &UnavailableImageTrialResponse {
            protocol_version: TRIAL_PROTOCOL,
            outcome: "unavailable",
            receipt_handle: None,
            receipt_digest: None,
            failure_code: code.wire_code(),
        },
        maximum,
        deadline,
    )
}

fn write_json_frame<T: Serialize>(
    stream: &mut UnixStream,
    value: &T,
    maximum: usize,
    deadline: Instant,
) -> Result<(), TrialRelayFailure> {
    let bytes =
        serde_json::to_vec(value).map_err(|_| TrialRelayFailure::ImplementationUnavailable)?;
    if bytes.is_empty() || bytes.len() > maximum || bytes.len() > u32::MAX as usize {
        return Err(TrialRelayFailure::CapacityExceeded);
    }
    write_all_until(stream, &(bytes.len() as u32).to_be_bytes(), deadline)?;
    write_all_until(stream, &bytes, deadline)
}

fn write_all_until(
    stream: &mut UnixStream,
    mut bytes: &[u8],
    deadline: Instant,
) -> Result<(), TrialRelayFailure> {
    while !bytes.is_empty() {
        if Instant::now() >= deadline {
            return Err(TrialRelayFailure::DeadlineExceeded);
        }
        match stream.write(bytes) {
            Ok(0) => return Err(TrialRelayFailure::ImplementationUnavailable),
            Ok(count) => bytes = &bytes[count..],
            Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                thread::park_timeout(Duration::from_millis(2));
            }
            Err(_) => return Err(TrialRelayFailure::ImplementationUnavailable),
        }
    }
    Ok(())
}

fn check_available(
    deadline: Instant,
    relay_cancelled: &AtomicBool,
    invocation_cancelled: &AtomicBool,
) -> Result<(), TrialRelayFailure> {
    if relay_cancelled.load(Ordering::Acquire) || invocation_cancelled.load(Ordering::Acquire) {
        Err(TrialRelayFailure::Cancelled)
    } else if Instant::now() >= deadline {
        Err(TrialRelayFailure::DeadlineExceeded)
    } else {
        Ok(())
    }
}

fn create_invocation_directory(root: &Path) -> Result<PathBuf, TrialRelayStartFailure> {
    for _ in 0..32 {
        let sequence = INVOCATION_SEQUENCE.fetch_add(1, Ordering::Relaxed);
        let path = root.join(format!(
            "{INVOCATION_DIRECTORY_PREFIX}{:08x}{:08x}",
            std::process::id(),
            sequence
        ));
        let mut builder = DirBuilder::new();
        builder.mode(0o700);
        match builder.create(&path) {
            Ok(()) => return Ok(path),
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(_) => {
                return Err(TrialRelayStartFailure {
                    code: TrialRelayFailure::ImplementationUnavailable,
                    cleanup_unsettled: false,
                });
            }
        }
    }
    Err(TrialRelayStartFailure {
        code: TrialRelayFailure::CapacityExceeded,
        cleanup_unsettled: false,
    })
}

fn remove_created_paths(directory: &Path, socket: &Path) -> TrialRelayStartFailure {
    let socket_removed = match fs::symlink_metadata(socket) {
        Ok(metadata) if metadata.file_type().is_socket() => fs::remove_file(socket).is_ok(),
        Ok(_) => false,
        Err(error) => error.kind() == std::io::ErrorKind::NotFound,
    };
    let directory_removed = fs::remove_dir(directory).is_ok();
    TrialRelayStartFailure {
        code: TrialRelayFailure::ImplementationUnavailable,
        cleanup_unsettled: !(socket_removed && directory_removed),
    }
}

fn cleanup_paths(paths: &RelayPaths) -> bool {
    let socket_ok = match fs::symlink_metadata(&paths.socket) {
        Ok(metadata)
            if metadata.file_type().is_socket()
                && metadata.dev() == paths.socket_device
                && metadata.ino() == paths.socket_inode
                && metadata.uid() == paths.sandbox_uid
                && metadata.gid() == paths.sandbox_gid =>
        {
            fs::remove_file(&paths.socket).is_ok()
        }
        _ => false,
    };
    let directory_ok = match fs::symlink_metadata(&paths.directory) {
        Ok(metadata)
            if private_directory(&metadata, paths.sandbox_uid, paths.sandbox_gid)
                && metadata.dev() == paths.directory_device
                && metadata.ino() == paths.directory_inode =>
        {
            fs::remove_dir(&paths.directory).is_ok()
        }
        _ => false,
    };
    socket_ok && directory_ok
}

fn validate_private_root(path: &Path, uid: u32, gid: u32) -> Result<(), ()> {
    let metadata = fs::symlink_metadata(path).map_err(|_| ())?;
    if !private_directory(&metadata, uid, gid)
        || path.as_os_str().as_bytes().contains(&0)
        || path.as_os_str().as_bytes().contains(&b'\n')
        || path.as_os_str().as_bytes().contains(&b'\r')
    {
        return Err(());
    }
    Ok(())
}

fn private_directory(metadata: &fs::Metadata, uid: u32, gid: u32) -> bool {
    metadata.file_type().is_dir()
        && metadata.mode() & 0o077 == 0
        && metadata.uid() == uid
        && metadata.gid() == gid
}

fn safe_relative_path(value: &str, allow_dot: bool) -> bool {
    if value.is_empty()
        || value.len() > 1000
        || value.as_bytes().contains(&0)
        || value.contains('\\')
        || (!allow_dot && value == ".")
    {
        return false;
    }
    let path = Path::new(value);
    !path.is_absolute()
        && path.components().all(|component| match component {
            Component::Normal(part) => !part.is_empty(),
            Component::CurDir => allow_dot && value == ".",
            _ => false,
        })
}

fn valid_identifier(value: &str) -> bool {
    let mut characters = value.chars();
    value.len() <= 100
        && characters
            .next()
            .is_some_and(|first| first.is_ascii_lowercase())
        && characters.all(|item| {
            item.is_ascii_lowercase() || item.is_ascii_digit() || matches!(item, '_' | '.' | '-')
        })
}

pub(crate) fn valid_uuid(value: &str) -> bool {
    value.len() == 36
        && value.bytes().enumerate().all(|(index, item)| {
            if matches!(index, 8 | 13 | 18 | 23) {
                item == b'-'
            } else {
                lower_hex(item)
            }
        })
}

pub(crate) fn valid_sha256(value: &str) -> bool {
    value.len() == 71 && value.starts_with("sha256:") && value[7..].bytes().all(lower_hex)
}

fn valid_receipt_handle(value: &str) -> bool {
    value.len() == 46 && value.starts_with("trial_receipt_") && value[14..].bytes().all(lower_hex)
}

fn valid_custody_ack(
    value: &TrialReceiptCustodyAck,
    receipt_digest: &str,
    byte_count: usize,
) -> bool {
    [
        &value.binding_id,
        &value.content_id,
        &value.put_attempt_id,
        &value.verification_receipt_id,
    ]
    .into_iter()
    .all(|item| valid_uuid(item))
        && value.content_sha256 == receipt_digest
        && value.byte_count == byte_count
}

fn lower_hex(value: u8) -> bool {
    value.is_ascii_digit() || (b'a'..=b'f').contains(&value)
}

fn sha256_text(value: &str) -> String {
    format!("sha256:{:x}", Sha256::digest(value.as_bytes()))
}
