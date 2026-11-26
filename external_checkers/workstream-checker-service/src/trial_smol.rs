//! Smol microVM backend for the generic trial engine.

use crate::smol::Reservation;
use crate::trial_engine::{
    image_archive::{validate_single_image_archive, ImageArchiveFailure, ValidatedImageArchive},
    SandboxBackendIdentity, SandboxBaselineUsage, SandboxBuildRequest, SandboxBuildResult,
    SandboxFailure, SandboxStepRequest, SandboxStepResult, TrialSandboxBackend,
};
use crate::trial_relay::{
    TrialBuildObservation, TrialExportOutcome, TrialOperationOutcome, TrialRelayFailure,
    TrialStepObservation,
};
use sha2::{Digest, Sha256};
use std::fs;
use std::sync::{atomic::AtomicBool, Arc};
use std::time::Instant;

const SMOL_CHILD_TRANSPORT: &str = "workstream.smol_guest_io.v1";

#[derive(Clone, Debug, Hash, PartialEq, Eq)]
pub(crate) struct SmolTrialOwner {
    pub(crate) deployment_owner: String,
    pub(crate) request_digest: String,
    pub(crate) attempt_id: String,
    pub(crate) trial_owner_id: String,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum SmolTrialTermination {
    Exited,
    Signalled,
    DeadlineExceeded,
    CpuExceeded,
    MemoryExceeded,
    PidExceeded,
    DiskExceeded,
    OutputExceeded,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct SmolTrialChildResult {
    pub(crate) termination: SmolTrialTermination,
    pub(crate) exit_code: Option<i32>,
    pub(crate) signal: Option<i32>,
    pub(crate) stdout: String,
    pub(crate) stderr: String,
    pub(crate) stdout_sha256: String,
    pub(crate) stderr_sha256: String,
    pub(crate) stdout_bytes: u64,
    pub(crate) stderr_bytes: u64,
    pub(crate) export_outcome: TrialExportOutcome,
    pub(crate) elapsed_ms: u64,
    pub(crate) cpu_time_ms: u64,
    pub(crate) peak_memory_bytes: u64,
    pub(crate) peak_pids: u64,
    pub(crate) written_bytes: u64,
    pub(crate) written_entries: u64,
    pub(crate) measurement_method: String,
    pub(crate) workspace_before_sha256: Option<String>,
    pub(crate) workspace_after_sha256: Option<String>,
    /// True only after the guest reaped descendants and the host guardian
    /// confirmed the sibling VM, cgroup, and disks absent. The invocation-owned
    /// prepared candidate lease intentionally remains until `cleanup_owner`.
    pub(crate) cleanup_confirmed: bool,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct PreparedCandidateFacts {
    pub(crate) config_image_id: String,
    pub(crate) platform: String,
    pub(crate) archive_sha256: String,
    pub(crate) archive_byte_count: u64,
    pub(crate) expanded_byte_count: u64,
    pub(crate) expanded_entry_count: u64,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum SmolTrialRuntimeFailure {
    InvalidObservation,
    CapacityExceeded,
    DeadlineExceeded,
    Cancelled,
    Unavailable,
    CleanupUnsettled,
}

/// Invocation-bound Smol control. Implementations retain the one atomic outer
/// plus child reservation and acquire its sequential child credit internally.
pub(crate) trait SmolTrialRuntime: Send + Sync + 'static {
    fn baseline_usage(
        &self,
        config: &SmolTrialConfiguration,
    ) -> Result<SandboxBaselineUsage, SmolTrialRuntimeFailure>;

    fn run_build(
        &self,
        config: &SmolTrialConfiguration,
        owner: &SmolTrialOwner,
        request: &SandboxBuildRequest,
        deadline: Instant,
        invocation_cancelled: &AtomicBool,
        relay_cancelled: &AtomicBool,
    ) -> Result<SmolTrialChildResult, SmolTrialRuntimeFailure>;

    fn prepare_candidate(
        &self,
        config: &SmolTrialConfiguration,
        owner: &SmolTrialOwner,
        archive: &std::path::Path,
        validated: &ValidatedImageArchive,
        archive_sha256: &str,
        archive_byte_count: u64,
        deadline: Instant,
    ) -> Result<PreparedCandidateFacts, SmolTrialRuntimeFailure>;

    fn run_step(
        &self,
        config: &SmolTrialConfiguration,
        owner: &SmolTrialOwner,
        request: &SandboxStepRequest,
        deadline: Instant,
        invocation_cancelled: &AtomicBool,
        relay_cancelled: &AtomicBool,
    ) -> Result<SmolTrialChildResult, SmolTrialRuntimeFailure>;

    fn cleanup_owner(
        &self,
        config: &SmolTrialConfiguration,
        owner: &SmolTrialOwner,
        deadline: Instant,
    ) -> Result<(), SmolTrialRuntimeFailure>;
}

pub(crate) struct SmolTrialConfiguration {
    pub(crate) identity: SandboxBackendIdentity,
    pub(crate) deployment_owner: String,
    pub(crate) request_digest: String,
    pub(crate) attempt_id: String,
    pub(crate) maximum_candidate_archive_bytes: u64,
    pub(crate) candidate_uid: u32,
    pub(crate) candidate_gid: u32,
    pub(crate) reservation: Arc<Reservation>,
}

pub(crate) struct SmolTrialBackend {
    config: SmolTrialConfiguration,
    runtime: Arc<dyn SmolTrialRuntime>,
}

impl SmolTrialBackend {
    pub(crate) fn new(
        config: SmolTrialConfiguration,
        runtime: Arc<dyn SmolTrialRuntime>,
    ) -> Result<Self, SandboxFailure> {
        if config.identity.child_runtime != "smolvm"
            || config.identity.child_transport != SMOL_CHILD_TRANSPORT
            || config.identity.platform != "linux/amd64"
            || !valid_digest(&config.identity.engine_identity_digest)
            || !valid_digest(&config.identity.guest_binary_digest)
            || !valid_digest(&config.identity.child_runtime_config_digest)
            || !valid_digest(&config.identity.platform_identity_digest)
            || !valid_digest(&config.identity.builder_image_digest)
            || !valid_digest(&config.identity.trusted_launcher_digest)
            || !valid_digest(&config.identity.filesystem_tool_digest)
            || !valid_digest(&config.identity.offline_cache_digest)
            || config
                .identity
                .approved_base_digests
                .iter()
                .any(|value| !valid_digest(value))
            || !valid_owner_component(&config.deployment_owner)
            || !valid_digest(&config.request_digest)
            || !valid_owner_component(&config.attempt_id)
            || config.maximum_candidate_archive_bytes == 0
            || config.candidate_uid == 0
            || config.candidate_gid == 0
        {
            return Err(infrastructure(TrialRelayFailure::InvalidRequest));
        }
        Ok(Self { config, runtime })
    }

    fn owner(&self, owner_id: &str) -> Result<SmolTrialOwner, SandboxFailure> {
        if !valid_owner_component(owner_id) {
            return Err(infrastructure(TrialRelayFailure::InvalidRequest));
        }
        Ok(SmolTrialOwner {
            deployment_owner: self.config.deployment_owner.clone(),
            request_digest: self.config.request_digest.clone(),
            attempt_id: self.config.attempt_id.clone(),
            trial_owner_id: owner_id.to_owned(),
        })
    }
}

impl TrialSandboxBackend for SmolTrialBackend {
    fn identity(&self) -> SandboxBackendIdentity {
        self.config.identity.clone()
    }

    fn baseline_usage(&self) -> Result<SandboxBaselineUsage, SandboxFailure> {
        self.runtime
            .baseline_usage(&self.config)
            .map_err(runtime_failure)
    }

    fn build(
        &self,
        request: &SandboxBuildRequest,
        deadline: Instant,
        invocation_cancelled: &AtomicBool,
        relay_cancelled: &AtomicBool,
    ) -> Result<SandboxBuildResult, SandboxFailure> {
        let owner = self.owner(&request.owner_id)?;
        let result = self
            .runtime
            .run_build(
                &self.config,
                &owner,
                request,
                deadline,
                invocation_cancelled,
                relay_cancelled,
            )
            .map_err(runtime_failure)?;
        validate_child_result(
            &result,
            request.timeout_ms,
            request.remaining_cpu_time_ms,
            request.resources.memory_bytes,
            request.resources.pids,
            request.mutable_disk_bytes,
            request.mutable_entries,
            request.maximum_output_bytes,
            &request.enforcement_overruns,
            false,
        )?;
        let mut observation = build_observation(&result)?;
        let mut retained_image_bytes = 0;
        let mut retained_image_entries = 0;
        if observation.outcome == TrialOperationOutcome::Succeeded {
            if result.export_outcome != TrialExportOutcome::Exported {
                return Err(infrastructure(TrialRelayFailure::ImplementationUnavailable));
            }
            let metadata = fs::symlink_metadata(&request.output_archive)
                .map_err(|_| infrastructure(TrialRelayFailure::ImplementationUnavailable))?;
            if !metadata.file_type().is_file()
                || metadata.file_type().is_symlink()
                || metadata.len() == 0
                || metadata.len() > self.config.maximum_candidate_archive_bytes
            {
                return Err(infrastructure(TrialRelayFailure::ImplementationUnavailable));
            }
            let expanded_bytes = request
                .mutable_disk_bytes
                .checked_sub(result.written_bytes)
                .ok_or_else(|| infrastructure(TrialRelayFailure::CapacityExceeded))?;
            let expanded_entries = request
                .mutable_entries
                .checked_sub(result.written_entries)
                .ok_or_else(|| infrastructure(TrialRelayFailure::CapacityExceeded))?;
            let validated = match validate_single_image_archive(
                &request.output_archive,
                &request.destination,
                &request.platform,
                self.config.maximum_candidate_archive_bytes,
                expanded_bytes,
                expanded_entries,
                deadline,
                &[invocation_cancelled, relay_cancelled],
            ) {
                Ok(validated) => validated,
                Err(ImageArchiveFailure::Invalid) => {
                    observation.outcome = TrialOperationOutcome::ExportInvalid;
                    observation.export_outcome = TrialExportOutcome::Invalid;
                    return Ok(SandboxBuildResult {
                        observation,
                        retained_image_bytes: 0,
                        retained_image_entries: 0,
                    });
                }
                Err(ImageArchiveFailure::CapacityExceeded) => {
                    observation.outcome = TrialOperationOutcome::DiskExceeded;
                    observation.export_outcome = TrialExportOutcome::CapacityExceeded;
                    return Ok(SandboxBuildResult {
                        observation,
                        retained_image_bytes: 0,
                        retained_image_entries: 0,
                    });
                }
                Err(error) => return Err(archive_failure(error)),
            };
            let archive_sha256 = validated.archive_sha256.clone();
            if validated.archive_byte_count != metadata.len() {
                return Err(infrastructure(TrialRelayFailure::ImplementationUnavailable));
            }
            let prepared = self
                .runtime
                .prepare_candidate(
                    &self.config,
                    &owner,
                    &request.output_archive,
                    &validated,
                    &archive_sha256,
                    metadata.len(),
                    deadline,
                )
                .map_err(runtime_failure)?;
            if prepared.config_image_id != validated.config_image_id
                || prepared.platform != validated.platform
                || prepared.archive_sha256 != archive_sha256
                || prepared.archive_byte_count != metadata.len()
                || prepared.expanded_byte_count != validated.expanded_bytes
                || prepared.expanded_entry_count != validated.expanded_entries
            {
                return Err(infrastructure(TrialRelayFailure::ImplementationUnavailable));
            }
            observation.candidate_image_digest = Some(prepared.config_image_id);
            observation.candidate_archive_digest = Some(archive_sha256);
            retained_image_bytes = prepared.expanded_byte_count;
            retained_image_entries = prepared.expanded_entry_count;
        }
        Ok(SandboxBuildResult {
            observation,
            retained_image_bytes,
            retained_image_entries,
        })
    }

    fn run_step(
        &self,
        request: &SandboxStepRequest,
        operation_order: u32,
        deadline: Instant,
        invocation_cancelled: &AtomicBool,
        relay_cancelled: &AtomicBool,
    ) -> Result<SandboxStepResult, SandboxFailure> {
        let owner = self.owner(&request.owner_id)?;
        let result = self
            .runtime
            .run_step(
                &self.config,
                &owner,
                request,
                deadline,
                invocation_cancelled,
                relay_cancelled,
            )
            .map_err(runtime_failure)?;
        validate_child_result(
            &result,
            request.timeout_ms,
            request.remaining_cpu_time_ms,
            request.resources.memory_bytes,
            request.resources.pids,
            request.mutable_disk_bytes,
            request.mutable_entries,
            request.maximum_output_bytes,
            &request.enforcement_overruns,
            true,
        )?;
        let workspace_before_sha256 = result
            .workspace_before_sha256
            .clone()
            .filter(|value| valid_digest(value))
            .ok_or_else(|| infrastructure(TrialRelayFailure::ImplementationUnavailable))?;
        let workspace_after_sha256 = result
            .workspace_after_sha256
            .clone()
            .filter(|value| valid_digest(value))
            .ok_or_else(|| infrastructure(TrialRelayFailure::ImplementationUnavailable))?;
        Ok(SandboxStepResult {
            observation: TrialStepObservation {
                slot_id: request.slot_id.clone(),
                operation_order,
                workspace_identity: request
                    .workspace_root
                    .file_name()
                    .and_then(|value| value.to_str())
                    .filter(|value| valid_owner_component(value))
                    .ok_or_else(|| infrastructure(TrialRelayFailure::InvalidRequest))?
                    .to_owned(),
                visible_role_inventory_digests: request.visible_role_inventory_digests.clone(),
                outcome: operation_outcome(&result)?,
                exit_code: result.exit_code,
                signal: result.signal,
                stdout: result.stdout.clone(),
                stdout_sha256: result.stdout_sha256.clone(),
                stderr: result.stderr.clone(),
                stderr_sha256: result.stderr_sha256.clone(),
                workspace_before_sha256,
                workspace_after_sha256,
                export_outcome: result.export_outcome,
                elapsed_ms: result.elapsed_ms,
                cpu_time_ms: result.cpu_time_ms,
                peak_memory_bytes: result.peak_memory_bytes,
                peak_pids: result.peak_pids,
                written_bytes: result.written_bytes,
                written_entries: result.written_entries,
                measurement_method: result.measurement_method.clone(),
            },
        })
    }

    fn cleanup(&self, owner_id: &str, deadline: Instant) -> Result<(), SandboxFailure> {
        let owner = self.owner(owner_id)?;
        self.runtime
            .cleanup_owner(&self.config, &owner, deadline)
            .map_err(runtime_failure)
    }
}

#[allow(clippy::too_many_arguments)]
fn validate_child_result(
    result: &SmolTrialChildResult,
    timeout_ms: u64,
    cpu_time_ms: u64,
    memory_bytes: u64,
    pids: u64,
    disk_bytes: u64,
    entries: u64,
    maximum_output_bytes: usize,
    overruns: &crate::trial_engine::SandboxEnforcementOverruns,
    step: bool,
) -> Result<(), SandboxFailure> {
    if !result.cleanup_confirmed {
        return Err(SandboxFailure {
            code: TrialRelayFailure::CleanupUnsettled,
            cleanup_unsettled: true,
        });
    }
    if result.measurement_method.is_empty()
        || result.measurement_method.len() > 256
        || !valid_digest(&result.stdout_sha256)
        || !valid_digest(&result.stderr_sha256)
        || result.stdout.len() as u64 != result.stdout_bytes
        || result.stderr.len() as u64 != result.stderr_bytes
        || format!("sha256:{:x}", Sha256::digest(result.stdout.as_bytes())) != result.stdout_sha256
        || format!("sha256:{:x}", Sha256::digest(result.stderr.as_bytes())) != result.stderr_sha256
        || result
            .stdout_bytes
            .checked_add(result.stderr_bytes)
            .is_none_or(|value| value > maximum_output_bytes as u64)
        || result.elapsed_ms > timeout_ms.saturating_add(overruns.wall_time_ms)
        || result.cpu_time_ms > cpu_time_ms.saturating_add(overruns.cpu_time_ms)
        || result.peak_memory_bytes > memory_bytes.saturating_add(overruns.memory_bytes)
        || result.peak_pids > pids.saturating_add(overruns.pids)
        || result.written_bytes > disk_bytes.saturating_add(overruns.disk_bytes)
        || result.written_entries > entries.saturating_add(overruns.entries)
        || (step
            && (result.workspace_before_sha256.is_none()
                || result.workspace_after_sha256.is_none()))
        || (!step
            && (result.workspace_before_sha256.is_some()
                || result.workspace_after_sha256.is_some()))
    {
        return Err(infrastructure(TrialRelayFailure::ImplementationUnavailable));
    }
    let crossed = match result.termination {
        SmolTrialTermination::DeadlineExceeded => result.elapsed_ms >= timeout_ms,
        SmolTrialTermination::CpuExceeded => result.cpu_time_ms >= cpu_time_ms,
        SmolTrialTermination::MemoryExceeded => result.peak_memory_bytes >= memory_bytes,
        SmolTrialTermination::PidExceeded => result.peak_pids >= pids,
        SmolTrialTermination::DiskExceeded => {
            result.written_bytes >= disk_bytes || result.written_entries >= entries
        }
        SmolTrialTermination::OutputExceeded => true,
        SmolTrialTermination::Exited | SmolTrialTermination::Signalled => true,
    };
    if !crossed {
        return Err(infrastructure(TrialRelayFailure::ImplementationUnavailable));
    }
    let forced = matches!(
        result.termination,
        SmolTrialTermination::DeadlineExceeded
            | SmolTrialTermination::CpuExceeded
            | SmolTrialTermination::MemoryExceeded
            | SmolTrialTermination::PidExceeded
            | SmolTrialTermination::DiskExceeded
            | SmolTrialTermination::OutputExceeded
    );
    let operation = operation_outcome(result)?;
    if (result.export_outcome == TrialExportOutcome::NotStarted
        && (step || operation == TrialOperationOutcome::Succeeded))
        || (result.export_outcome == TrialExportOutcome::Unavailable && !forced)
        || (matches!(
            result.export_outcome,
            TrialExportOutcome::CapacityExceeded | TrialExportOutcome::Invalid
        ) && forced)
    {
        return Err(infrastructure(TrialRelayFailure::ImplementationUnavailable));
    }
    Ok(())
}

fn operation_outcome(
    result: &SmolTrialChildResult,
) -> Result<TrialOperationOutcome, SandboxFailure> {
    let base = match result.termination {
        SmolTrialTermination::Exited => match (result.exit_code, result.signal) {
            (Some(0), None) => TrialOperationOutcome::Succeeded,
            (Some(_), None) => TrialOperationOutcome::ExitNonzero,
            _ => return Err(infrastructure(TrialRelayFailure::ImplementationUnavailable)),
        },
        SmolTrialTermination::Signalled => match (result.exit_code, result.signal) {
            (None, Some(_)) => TrialOperationOutcome::Signalled,
            _ => return Err(infrastructure(TrialRelayFailure::ImplementationUnavailable)),
        },
        SmolTrialTermination::DeadlineExceeded => TrialOperationOutcome::DeadlineExceeded,
        SmolTrialTermination::CpuExceeded => TrialOperationOutcome::CpuExceeded,
        SmolTrialTermination::MemoryExceeded => TrialOperationOutcome::MemoryExceeded,
        SmolTrialTermination::PidExceeded => TrialOperationOutcome::PidExceeded,
        SmolTrialTermination::DiskExceeded => TrialOperationOutcome::DiskExceeded,
        SmolTrialTermination::OutputExceeded => TrialOperationOutcome::OutputExceeded,
    };
    match result.export_outcome {
        TrialExportOutcome::CapacityExceeded => Ok(TrialOperationOutcome::DiskExceeded),
        TrialExportOutcome::Invalid => Ok(TrialOperationOutcome::ExportInvalid),
        TrialExportOutcome::Exported
        | TrialExportOutcome::Unavailable
        | TrialExportOutcome::NotStarted => Ok(base),
    }
}

fn build_observation(
    result: &SmolTrialChildResult,
) -> Result<TrialBuildObservation, SandboxFailure> {
    Ok(TrialBuildObservation {
        outcome: operation_outcome(result)?,
        exit_code: result.exit_code,
        signal: result.signal,
        stdout: result.stdout.clone(),
        stdout_sha256: result.stdout_sha256.clone(),
        stderr: result.stderr.clone(),
        stderr_sha256: result.stderr_sha256.clone(),
        candidate_image_digest: None,
        candidate_archive_digest: None,
        export_outcome: result.export_outcome,
        elapsed_ms: result.elapsed_ms,
        cpu_time_ms: result.cpu_time_ms,
        peak_memory_bytes: result.peak_memory_bytes,
        peak_pids: result.peak_pids,
        written_bytes: result.written_bytes,
        written_entries: result.written_entries,
        measurement_method: result.measurement_method.clone(),
    })
}

fn archive_failure(value: ImageArchiveFailure) -> SandboxFailure {
    match value {
        ImageArchiveFailure::Invalid => {
            infrastructure(TrialRelayFailure::ImplementationUnavailable)
        }
        ImageArchiveFailure::CapacityExceeded => {
            infrastructure(TrialRelayFailure::CapacityExceeded)
        }
        ImageArchiveFailure::DeadlineExceeded => {
            infrastructure(TrialRelayFailure::DeadlineExceeded)
        }
        ImageArchiveFailure::Cancelled => infrastructure(TrialRelayFailure::Cancelled),
    }
}

fn runtime_failure(value: SmolTrialRuntimeFailure) -> SandboxFailure {
    match value {
        SmolTrialRuntimeFailure::CapacityExceeded => {
            infrastructure(TrialRelayFailure::CapacityExceeded)
        }
        SmolTrialRuntimeFailure::DeadlineExceeded => {
            infrastructure(TrialRelayFailure::DeadlineExceeded)
        }
        SmolTrialRuntimeFailure::Cancelled => infrastructure(TrialRelayFailure::Cancelled),
        SmolTrialRuntimeFailure::CleanupUnsettled => SandboxFailure {
            code: TrialRelayFailure::CleanupUnsettled,
            cleanup_unsettled: true,
        },
        SmolTrialRuntimeFailure::InvalidObservation | SmolTrialRuntimeFailure::Unavailable => {
            infrastructure(TrialRelayFailure::ImplementationUnavailable)
        }
    }
}

fn valid_digest(value: &str) -> bool {
    value.len() == 71
        && value.starts_with("sha256:")
        && value[7..]
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn valid_owner_component(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'.'))
}

fn infrastructure(code: TrialRelayFailure) -> SandboxFailure {
    SandboxFailure {
        code,
        cleanup_unsettled: false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::smol::{Admission, Capacity, Phase};
    use crate::trial_engine::SandboxEnforcementOverruns;

    struct NoopRuntime;

    impl SmolTrialRuntime for NoopRuntime {
        fn baseline_usage(
            &self,
            _config: &SmolTrialConfiguration,
        ) -> Result<SandboxBaselineUsage, SmolTrialRuntimeFailure> {
            Ok(SandboxBaselineUsage {
                bytes: 1,
                entries: 1,
            })
        }

        fn run_build(
            &self,
            _: &SmolTrialConfiguration,
            _: &SmolTrialOwner,
            _: &SandboxBuildRequest,
            _: Instant,
            _: &AtomicBool,
            _: &AtomicBool,
        ) -> Result<SmolTrialChildResult, SmolTrialRuntimeFailure> {
            unreachable!()
        }

        fn prepare_candidate(
            &self,
            _: &SmolTrialConfiguration,
            _: &SmolTrialOwner,
            _: &std::path::Path,
            _: &ValidatedImageArchive,
            _: &str,
            _: u64,
            _: Instant,
        ) -> Result<PreparedCandidateFacts, SmolTrialRuntimeFailure> {
            unreachable!()
        }

        fn run_step(
            &self,
            _: &SmolTrialConfiguration,
            _: &SmolTrialOwner,
            _: &SandboxStepRequest,
            _: Instant,
            _: &AtomicBool,
            _: &AtomicBool,
        ) -> Result<SmolTrialChildResult, SmolTrialRuntimeFailure> {
            unreachable!()
        }

        fn cleanup_owner(
            &self,
            _: &SmolTrialConfiguration,
            _: &SmolTrialOwner,
            _: Instant,
        ) -> Result<(), SmolTrialRuntimeFailure> {
            unreachable!()
        }
    }

    fn digest(byte: char) -> String {
        format!("sha256:{}", byte.to_string().repeat(64))
    }

    fn configuration() -> SmolTrialConfiguration {
        let admission = Arc::new(
            Admission::new(
                Capacity {
                    slots: 2,
                    memory_bytes: 2 * 1024 * 1024,
                    storage_bytes: 2 * 1024 * 1024,
                },
                None,
                "epoch".into(),
            )
            .unwrap(),
        );
        let reservation = admission
            .reserve(
                Phase::Background,
                Capacity {
                    slots: 1,
                    memory_bytes: 1024,
                    storage_bytes: 1024,
                },
                Some(Capacity {
                    slots: 1,
                    memory_bytes: 1024,
                    storage_bytes: 1024,
                }),
            )
            .unwrap();
        SmolTrialConfiguration {
            identity: SandboxBackendIdentity {
                engine_identity_digest: digest('1'),
                guest_binary_digest: digest('2'),
                child_runtime: "smolvm".into(),
                child_runtime_config_digest: digest('3'),
                child_transport: SMOL_CHILD_TRANSPORT.into(),
                platform: "linux/amd64".into(),
                platform_identity_digest: digest('4'),
                builder_image_digest: digest('5'),
                trusted_launcher_digest: digest('6'),
                filesystem_tool_digest: digest('8'),
                offline_cache_digest: digest('7'),
                approved_base_digests: vec![digest('8')],
            },
            deployment_owner: "deployment".into(),
            request_digest: digest('9'),
            attempt_id: "attempt".into(),
            maximum_candidate_archive_bytes: 1024 * 1024,
            candidate_uid: 65532,
            candidate_gid: 65532,
            reservation,
        }
    }

    fn result() -> SmolTrialChildResult {
        SmolTrialChildResult {
            termination: SmolTrialTermination::Exited,
            exit_code: Some(0),
            signal: None,
            stdout: String::new(),
            stderr: String::new(),
            stdout_sha256: format!("sha256:{:x}", Sha256::digest([])),
            stderr_sha256: format!("sha256:{:x}", Sha256::digest([])),
            stdout_bytes: 0,
            stderr_bytes: 0,
            export_outcome: TrialExportOutcome::Exported,
            elapsed_ms: 10,
            cpu_time_ms: 5,
            peak_memory_bytes: 100,
            peak_pids: 1,
            written_bytes: 100,
            written_entries: 2,
            measurement_method: "smol_guest_cgroup_v2_and_bounded_ext4".into(),
            workspace_before_sha256: None,
            workspace_after_sha256: None,
            cleanup_confirmed: true,
        }
    }

    fn overruns() -> SandboxEnforcementOverruns {
        SandboxEnforcementOverruns {
            wall_time_ms: 1,
            cpu_time_ms: 1,
            memory_bytes: 1,
            pids: 1,
            disk_bytes: 1,
            entries: 1,
        }
    }

    #[test]
    fn configuration_requires_exact_smol_identity_and_invocation_reservation() {
        assert!(SmolTrialBackend::new(configuration(), Arc::new(NoopRuntime)).is_ok());
        let mut wrong_transport = configuration();
        wrong_transport.identity.child_transport = "none".into();
        assert!(SmolTrialBackend::new(wrong_transport, Arc::new(NoopRuntime)).is_err());
        let mut wrong_guest = configuration();
        wrong_guest.identity.guest_binary_digest = digest('A');
        assert!(SmolTrialBackend::new(wrong_guest, Arc::new(NoopRuntime)).is_err());
        let mut wrong_filesystem_tool = configuration();
        wrong_filesystem_tool.identity.filesystem_tool_digest = "sha256:short".into();
        assert!(SmolTrialBackend::new(wrong_filesystem_tool, Arc::new(NoopRuntime)).is_err());
        let mut root_child = configuration();
        root_child.candidate_uid = 0;
        assert!(SmolTrialBackend::new(root_child, Arc::new(NoopRuntime)).is_err());
    }

    #[test]
    fn child_cleanup_and_export_provenance_fail_closed() {
        let mut value = result();
        validate_child_result(
            &value,
            100,
            100,
            1000,
            4,
            1000,
            10,
            1024,
            &overruns(),
            false,
        )
        .unwrap();

        value.cleanup_confirmed = false;
        let failure = validate_child_result(
            &value,
            100,
            100,
            1000,
            4,
            1000,
            10,
            1024,
            &overruns(),
            false,
        )
        .unwrap_err();
        assert_eq!(failure.code, TrialRelayFailure::CleanupUnsettled);
        assert!(failure.cleanup_unsettled);

        let mut unavailable = result();
        unavailable.export_outcome = TrialExportOutcome::Unavailable;
        assert!(validate_child_result(
            &unavailable,
            100,
            100,
            1000,
            4,
            1000,
            10,
            1024,
            &overruns(),
            false,
        )
        .is_err());
        unavailable.termination = SmolTrialTermination::DeadlineExceeded;
        unavailable.exit_code = None;
        unavailable.elapsed_ms = 100;
        validate_child_result(
            &unavailable,
            100,
            100,
            1000,
            4,
            1000,
            10,
            1024,
            &overruns(),
            false,
        )
        .unwrap();
    }

    #[test]
    fn real_output_is_preserved_and_forged_text_cannot_enter_observations() {
        let mut value = result();
        value.stdout = "candidate build completed\n".into();
        value.stderr = "bounded build diagnostic\n".into();
        value.stdout_bytes = value.stdout.len() as u64;
        value.stderr_bytes = value.stderr.len() as u64;
        value.stdout_sha256 = format!("sha256:{:x}", Sha256::digest(value.stdout.as_bytes()));
        value.stderr_sha256 = format!("sha256:{:x}", Sha256::digest(value.stderr.as_bytes()));
        validate_child_result(
            &value,
            100,
            100,
            1000,
            4,
            1000,
            10,
            1024,
            &overruns(),
            false,
        )
        .unwrap();
        let observation = build_observation(&value).unwrap();
        assert_eq!(observation.stdout, value.stdout);
        assert_eq!(observation.stderr, value.stderr);
        assert_eq!(observation.stdout_sha256, value.stdout_sha256);
        assert_eq!(observation.stderr_sha256, value.stderr_sha256);
        value.stdout.clear();
        assert!(validate_child_result(
            &value,
            100,
            100,
            1000,
            4,
            1000,
            10,
            1024,
            &overruns(),
            false
        )
        .is_err());
    }

    #[test]
    fn exact_child_exit_signal_and_measurement_limits_are_required() {
        let mut invalid = result();
        invalid.signal = Some(9);
        assert!(operation_outcome(&invalid).is_err());

        let mut over = result();
        over.peak_memory_bytes = 1002;
        assert!(validate_child_result(
            &over,
            100,
            100,
            1000,
            4,
            1000,
            10,
            1024,
            &overruns(),
            false,
        )
        .is_err());
    }
}
