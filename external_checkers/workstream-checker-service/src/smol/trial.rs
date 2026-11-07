//! Production host adapter for fresh, invocation-bound Smol trial siblings.

use super::io::IoGuard;
use super::trial_io::{self, ExportTarget};
use super::{checked, command, Machine, Resources, SmolImage};
use crate::trial_engine::{
    SandboxBackendIdentity, SandboxBaselineUsage, SandboxBuildRequest, SandboxStepRequest,
};
use crate::trial_relay::TrialProfile;
use crate::trial_smol::{
    PreparedCandidateFacts, SmolTrialChildResult, SmolTrialConfiguration, SmolTrialOwner,
    SmolTrialRuntime, SmolTrialRuntimeFailure,
};
use crate::{CacheEntry, ServiceConfig, TrialRuntimeConfiguration};
use sha2::{Digest, Sha256};
use std::collections::HashSet;
use std::fs::{self, OpenOptions};
use std::io::Read;
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::path::{Path, PathBuf};
use std::process::Stdio;
use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc, Mutex,
};
use std::time::Instant;
use workstream_checker_guest::{
    GuestJob, GuestPurpose, TrialChildLimits, TrialChildResult, TrialExportOutcome,
    TrialFilesystemLimit, TrialRequest, TrialVisibleRole, TRIAL_LIMITS_ARGUMENT,
    TRIAL_LIMITS_MAXIMUM_BYTES,
};

const GIB: u64 = 1024 * 1024 * 1024;

#[derive(Clone)]
struct Candidate {
    owner: SmolTrialOwner,
    archive: PathBuf,
    archive_sha256: String,
    archive_byte_count: u64,
    config_image_id: String,
    platform: String,
    expanded_byte_count: u64,
    expanded_entry_count: u64,
    environment: Vec<String>,
}

#[derive(Default)]
struct State {
    owner: Option<SmolTrialOwner>,
    candidate: Option<Candidate>,
}

pub(crate) struct Runtime {
    config: ServiceConfig,
    runtime: TrialRuntimeConfiguration,
    profile: TrialProfile,
    client: std::os::unix::net::UnixStream,
    builder: CacheEntry,
    builder_environment: Vec<String>,
    baseline: SandboxBaselineUsage,
    reservation: Arc<super::Reservation>,
    invocation_cancelled: Arc<AtomicBool>,
    deadline: Instant,
    state: Mutex<State>,
    active: AtomicBool,
}

impl Runtime {
    pub(crate) fn new(
        config: ServiceConfig,
        runtime: TrialRuntimeConfiguration,
        profile: TrialProfile,
        client: std::os::unix::net::UnixStream,
        reservation: Arc<super::Reservation>,
        deadline: Instant,
        invocation_cancelled: Arc<AtomicBool>,
    ) -> Result<Self, String> {
        if invocation_cancelled.load(Ordering::Acquire) || Instant::now() >= deadline {
            return Err("trial initialization unavailable".into());
        }
        let cancelled = [invocation_cancelled.as_ref()];
        let guard = IoGuard {
            deadline,
            client: Some(&client),
            cancelled: &cancelled,
        };
        let configured = config
            .trial_runtime
            .as_ref()
            .ok_or("trial runtime unavailable")?;
        let actual_runtime_digest = crate::trial_runtime_configuration_digest(&config, &runtime)?;
        if configured.relay_root != runtime.relay_root
            || configured.scratch_root != runtime.scratch_root
            || configured.child_home_root != runtime.child_home_root
            || configured.outer_runtime_config_digest != runtime.outer_runtime_config_digest
            || configured.offline_cache_root != runtime.offline_cache_root
            || configured.deployment_owner != runtime.deployment_owner
            || configured.builder_image_id != runtime.builder_image_id
            || configured.trusted_launcher_path != runtime.trusted_launcher_path
            || configured.trusted_launcher_digest != runtime.trusted_launcher_digest
            || configured.filesystem_tool_path != runtime.filesystem_tool_path
            || configured.filesystem_tool_digest != runtime.filesystem_tool_digest
            || configured.maximum_candidate_archive_bytes != runtime.maximum_candidate_archive_bytes
            || runtime.outer_runtime_config_digest != profile.outer_runtime_config_digest
            || runtime.outer_runtime_config_digest != profile.child_runtime_config_digest
            || actual_runtime_digest != runtime.outer_runtime_config_digest
            || runtime.trusted_launcher_digest != profile.trusted_launcher_digest
            || runtime.filesystem_tool_digest != profile.filesystem_tool_digest
            || runtime.maximum_candidate_archive_bytes == 0
            || config.sandbox_uid != unsafe { libc::geteuid() }
            || config.sandbox_gid != unsafe { libc::getegid() }
        {
            return Err("trial runtime identity differs".into());
        }
        super::private_directory(&runtime.relay_root)?;
        super::private_directory(&runtime.scratch_root)?;
        super::private_directory(&runtime.child_home_root)?;
        let matches: Vec<_> = config
            .cache
            .iter()
            .filter(|entry| {
                entry.platform_manifest_digest == profile.builder_image_digest
                    && entry.config_image_id == runtime.builder_image_id
                    && entry.operating_system == "linux"
                    && entry.architecture == "amd64"
                    && entry.smol.is_some()
            })
            .cloned()
            .collect();
        let [builder] = matches.as_slice() else {
            return Err("trial builder cache identity differs".into());
        };
        let (baseline, builder_environment) =
            measure_baseline(&config, &runtime, &profile, builder, &guard, &cancelled)
                .map_err(|failure| format!("trial baseline invalid: {failure:?}"))?;
        Ok(Self {
            config,
            runtime,
            profile,
            client,
            builder: builder.clone(),
            builder_environment,
            baseline,
            reservation,
            invocation_cancelled,
            deadline,
            state: Mutex::new(State::default()),
            active: AtomicBool::new(false),
        })
    }

    fn begin(&self, owner: &SmolTrialOwner) -> Result<Active<'_>, SmolTrialRuntimeFailure> {
        if owner.deployment_owner != self.runtime.deployment_owner
            || self
                .active
                .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
                .is_err()
        {
            return Err(SmolTrialRuntimeFailure::Unavailable);
        }
        let accepted = self
            .state
            .lock()
            .map_err(|_| SmolTrialRuntimeFailure::CleanupUnsettled)
            .and_then(|mut state| match &state.owner {
                Some(expected) if expected != owner => Err(SmolTrialRuntimeFailure::Unavailable),
                Some(_) => Ok(()),
                None => {
                    state.owner = Some(owner.clone());
                    Ok(())
                }
            });
        if let Err(error) = accepted {
            self.active.store(false, Ordering::SeqCst);
            return Err(error);
        }
        Ok(Active {
            active: &self.active,
        })
    }

    fn identity(&self) -> SandboxBackendIdentity {
        SandboxBackendIdentity {
            engine_identity_digest: self.profile.engine_identity_digest.clone(),
            guest_binary_digest: self.profile.guest_binary_digest.clone(),
            filesystem_tool_digest: self.profile.filesystem_tool_digest.clone(),
            child_runtime: self.profile.child_runtime.clone(),
            child_runtime_config_digest: self.profile.child_runtime_config_digest.clone(),
            child_transport: self.profile.child_transport.clone(),
            platform: self.profile.platform.clone(),
            platform_identity_digest: self.profile.platform_identity_digest.clone(),
            builder_image_digest: self.profile.builder_image_digest.clone(),
            trusted_launcher_digest: self.profile.trusted_launcher_digest.clone(),
            offline_cache_digest: self.profile.offline_cache_digest.clone(),
            approved_base_digests: self.profile.approved_base_digests.clone(),
        }
    }

    fn accepts_configuration(&self, config: &SmolTrialConfiguration) -> bool {
        config.identity == self.identity()
            && config.deployment_owner == self.runtime.deployment_owner
            && config.maximum_candidate_archive_bytes
                == self.runtime.maximum_candidate_archive_bytes
            && config.candidate_uid == self.config.sandbox_uid
            && config.candidate_gid == self.config.sandbox_gid
            && Arc::ptr_eq(&config.reservation, &self.reservation)
    }

    fn accepts_cancellation(&self, cancellation: &AtomicBool) -> bool {
        std::ptr::eq(cancellation, Arc::as_ptr(&self.invocation_cancelled))
    }
}

fn offline_cache_failure(
    failure: crate::trial_engine::offline_cache::OfflineCacheFailure,
) -> SmolTrialRuntimeFailure {
    match failure {
        crate::trial_engine::offline_cache::OfflineCacheFailure::Invalid => {
            SmolTrialRuntimeFailure::InvalidObservation
        }
        crate::trial_engine::offline_cache::OfflineCacheFailure::Capacity => {
            SmolTrialRuntimeFailure::CapacityExceeded
        }
        crate::trial_engine::offline_cache::OfflineCacheFailure::Deadline => {
            SmolTrialRuntimeFailure::DeadlineExceeded
        }
        crate::trial_engine::offline_cache::OfflineCacheFailure::Cancelled => {
            SmolTrialRuntimeFailure::Cancelled
        }
    }
}

struct Active<'a> {
    active: &'a AtomicBool,
}

impl Drop for Active<'_> {
    fn drop(&mut self) {
        self.active.store(false, Ordering::SeqCst);
    }
}

fn hash_file_bounded(path: &Path, expected: &str, guard: &IoGuard<'_>) -> Result<u64, String> {
    if !path.is_absolute()
        || expected.len() != 71
        || !expected.starts_with("sha256:")
        || expected[7..]
            .bytes()
            .any(|byte| !byte.is_ascii_hexdigit() || byte.is_ascii_uppercase())
    {
        return Err("trial asset identity invalid".into());
    }
    let mut file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(path)
        .map_err(|_| "trial asset unavailable")?;
    let metadata = file.metadata().map_err(|_| "trial asset unavailable")?;
    if !metadata.file_type().is_file() || metadata.mode() & 0o022 != 0 {
        return Err("trial asset custody invalid".into());
    }
    let mut digest = Sha256::new();
    let mut observed = 0_u64;
    let mut buffer = [0_u8; 65_536];
    loop {
        guard.check()?;
        let count = file
            .read(&mut buffer)
            .map_err(|_| "trial asset read failed")?;
        if count == 0 {
            break;
        }
        observed = observed
            .checked_add(count as u64)
            .ok_or("trial asset size overflow")?;
        digest.update(&buffer[..count]);
    }
    if observed != metadata.len() || format!("sha256:{:x}", digest.finalize()) != expected {
        return Err("trial asset digest differs".into());
    }
    Ok(observed)
}

fn image_archive_failure(
    failure: crate::trial_engine::image_archive::ImageArchiveFailure,
) -> SmolTrialRuntimeFailure {
    match failure {
        crate::trial_engine::image_archive::ImageArchiveFailure::Invalid => {
            SmolTrialRuntimeFailure::InvalidObservation
        }
        crate::trial_engine::image_archive::ImageArchiveFailure::CapacityExceeded => {
            SmolTrialRuntimeFailure::CapacityExceeded
        }
        crate::trial_engine::image_archive::ImageArchiveFailure::DeadlineExceeded => {
            SmolTrialRuntimeFailure::DeadlineExceeded
        }
        crate::trial_engine::image_archive::ImageArchiveFailure::Cancelled => {
            SmolTrialRuntimeFailure::Cancelled
        }
    }
}

fn measure_baseline(
    config: &ServiceConfig,
    runtime: &TrialRuntimeConfiguration,
    profile: &TrialProfile,
    builder: &CacheEntry,
    guard: &IoGuard<'_>,
    cancellations: &[&AtomicBool],
) -> Result<(SandboxBaselineUsage, Vec<String>), SmolTrialRuntimeFailure> {
    let image = builder
        .smol
        .as_ref()
        .ok_or(SmolTrialRuntimeFailure::InvalidObservation)?;
    if cancellations.is_empty() {
        return Err(SmolTrialRuntimeFailure::InvalidObservation);
    }
    let map_asset_failure = |_| classify_cancellations(guard.deadline, cancellations);
    let launcher_bytes = hash_file_bounded(
        &runtime.trusted_launcher_path,
        &runtime.trusted_launcher_digest,
        guard,
    )
    .map_err(map_asset_failure)?;
    let filesystem_tool_bytes = hash_file_bounded(
        &runtime.filesystem_tool_path,
        &runtime.filesystem_tool_digest,
        guard,
    )
    .map_err(map_asset_failure)?;
    let builder_archive_bytes = hash_file_bounded(&image.archive, &image.archive_sha256, guard)
        .map_err(map_asset_failure)?;
    let builder_config_bytes =
        hash_file_bounded(&image.image_config, &builder.config_image_id, guard)
            .map_err(map_asset_failure)?;
    let smol = super::settings(config).map_err(|_| SmolTrialRuntimeFailure::InvalidObservation)?;
    let guest_bytes = hash_file_bounded(&smol.guest_binary, &smol.guest_sha256, guard)
        .map_err(map_asset_failure)?;
    let cache_usage = crate::trial_engine::offline_cache::verify_offline_cache(
        &runtime.offline_cache_root,
        &profile.offline_cache_digest,
        guard.deadline,
        cancellations,
    )
    .map_err(offline_cache_failure)?;
    let builder_facts = crate::trial_engine::image_archive::validate_pinned_builder_archive(
        &image.archive,
        &builder.platform_manifest_digest,
        &builder.config_image_id,
        &profile.platform,
        profile.maximum_disk_bytes,
        profile.maximum_disk_bytes,
        profile.maximum_entries,
        guard.deadline,
        cancellations,
    )
    .map_err(image_archive_failure)?;
    let baseline = SandboxBaselineUsage {
        bytes: [
            cache_usage
                .bytes
                .checked_mul(2)
                .ok_or(SmolTrialRuntimeFailure::CapacityExceeded)?,
            cache_usage
                .entries
                .checked_mul(4096)
                .ok_or(SmolTrialRuntimeFailure::CapacityExceeded)?,
            builder_archive_bytes,
            builder_config_bytes,
            builder_facts.expanded_bytes,
            launcher_bytes
                .checked_mul(2)
                .ok_or(SmolTrialRuntimeFailure::CapacityExceeded)?,
            filesystem_tool_bytes
                .checked_mul(2)
                .ok_or(SmolTrialRuntimeFailure::CapacityExceeded)?,
            guest_bytes
                .checked_mul(2)
                .ok_or(SmolTrialRuntimeFailure::CapacityExceeded)?,
        ]
        .into_iter()
        .try_fold(0_u64, |sum, value| sum.checked_add(value))
        .ok_or(SmolTrialRuntimeFailure::CapacityExceeded)?,
        entries: cache_usage
            .entries
            .checked_mul(2)
            .and_then(|value| value.checked_add(builder_facts.expanded_entries))
            .and_then(|value| value.checked_add(8))
            .ok_or(SmolTrialRuntimeFailure::CapacityExceeded)?,
    };
    if baseline.bytes == 0
        || baseline.entries == 0
        || baseline.bytes > profile.maximum_disk_bytes
        || baseline.entries > profile.maximum_entries
    {
        return Err(SmolTrialRuntimeFailure::CapacityExceeded);
    }
    Ok((baseline, builder_facts.environment))
}

fn limits(
    request: &SandboxBuildRequest,
) -> Result<(TrialChildLimits, Resources), SmolTrialRuntimeFailure> {
    let memory = request
        .resources
        .memory_bytes
        .checked_add(request.enforcement_overruns.memory_bytes)
        .ok_or(SmolTrialRuntimeFailure::CapacityExceeded)?;
    let pids = request
        .resources
        .pids
        .checked_add(request.enforcement_overruns.pids)
        .ok_or(SmolTrialRuntimeFailure::CapacityExceeded)?;
    let disk = request
        .mutable_disk_bytes
        .checked_add(request.enforcement_overruns.disk_bytes)
        .ok_or(SmolTrialRuntimeFailure::CapacityExceeded)?;
    Ok((
        TrialChildLimits {
            cpu_quota_millis: request.resources.cpu_quota_millis,
            cpu_time_ms: request.remaining_cpu_time_ms,
            finalization_cpu_time_ms: request
                .remaining_cpu_time_ms
                .checked_add(request.enforcement_overruns.cpu_time_ms)
                .ok_or(SmolTrialRuntimeFailure::CapacityExceeded)?,
            memory_bytes: memory,
            pids,
            timeout_ms: request.timeout_ms,
            finalization_timeout_ms: request
                .timeout_ms
                .checked_add(request.enforcement_overruns.wall_time_ms)
                .ok_or(SmolTrialRuntimeFailure::CapacityExceeded)?,
            output_bytes: request.maximum_output_bytes as u64,
        },
        Resources {
            cpu_millis: request.resources.cpu_quota_millis,
            memory_bytes: memory,
            storage_gib: disk.div_ceil(GIB).max(1),
            pids,
        },
    ))
}

fn step_limits(
    request: &SandboxStepRequest,
) -> Result<(TrialChildLimits, Resources), SmolTrialRuntimeFailure> {
    let memory = request
        .resources
        .memory_bytes
        .checked_add(request.enforcement_overruns.memory_bytes)
        .ok_or(SmolTrialRuntimeFailure::CapacityExceeded)?;
    let pids = request
        .resources
        .pids
        .checked_add(request.enforcement_overruns.pids)
        .ok_or(SmolTrialRuntimeFailure::CapacityExceeded)?;
    let disk = request
        .mutable_disk_bytes
        .checked_add(request.enforcement_overruns.disk_bytes)
        .ok_or(SmolTrialRuntimeFailure::CapacityExceeded)?;
    Ok((
        TrialChildLimits {
            cpu_quota_millis: request.resources.cpu_quota_millis,
            cpu_time_ms: request.remaining_cpu_time_ms,
            finalization_cpu_time_ms: request
                .remaining_cpu_time_ms
                .checked_add(request.enforcement_overruns.cpu_time_ms)
                .ok_or(SmolTrialRuntimeFailure::CapacityExceeded)?,
            memory_bytes: memory,
            pids,
            timeout_ms: request.timeout_ms,
            finalization_timeout_ms: request
                .timeout_ms
                .checked_add(request.enforcement_overruns.wall_time_ms)
                .ok_or(SmolTrialRuntimeFailure::CapacityExceeded)?,
            output_bytes: request.maximum_output_bytes as u64,
        },
        Resources {
            cpu_millis: request.resources.cpu_quota_millis,
            memory_bytes: memory,
            storage_gib: disk.div_ceil(GIB).max(1),
            pids,
        },
    ))
}

fn stage_tools(
    machine: &Machine,
    runtime: &TrialRuntimeConfiguration,
    client: &std::os::unix::net::UnixStream,
    guard: &IoGuard<'_>,
) -> Result<(), String> {
    for (source, digest, destination) in [
        (
            &runtime.trusted_launcher_path,
            &runtime.trusted_launcher_digest,
            format!("{}:/.workstream-trial-launcher", machine.lease.name),
        ),
        (
            &runtime.filesystem_tool_path,
            &runtime.filesystem_tool_digest,
            format!("{}:/.workstream-mkfs.ext4", machine.lease.name),
        ),
    ] {
        hash_file_bounded(source, digest, guard)?;
        checked(
            &machine.lease.runtime,
            &[
                "machine",
                "cp",
                "--mode",
                "0555",
                source.to_str().ok_or("trial tool path invalid")?,
                &destination,
            ],
            Some(&machine.lease.cgroup()),
            guard.deadline,
            Some(client),
        )?;
    }
    Ok(())
}

fn revalidate_machine_inputs(
    config: &ServiceConfig,
    cache: &CacheEntry,
    guard: &IoGuard<'_>,
) -> Result<(), String> {
    let image = cache.smol.as_ref().ok_or("trial image unavailable")?;
    hash_file_bounded(&image.archive, &image.archive_sha256, guard)?;
    let smol = super::settings(config)?;
    hash_file_bounded(&smol.guest_binary, &smol.guest_sha256, guard)?;
    Ok(())
}

fn spawn_guest(machine: &Machine, limits: TrialChildLimits) -> Result<std::process::Child, String> {
    let bootstrap = serde_json::to_string(&limits).map_err(|_| "trial bootstrap limits invalid")?;
    if bootstrap.len() > TRIAL_LIMITS_MAXIMUM_BYTES {
        return Err("trial bootstrap limits unbounded".into());
    }
    let mut command = command(
        &machine.lease.runtime,
        &[
            "machine",
            "exec",
            "--name",
            &machine.lease.name,
            "--user",
            "0:0",
            "--interactive",
            "--stream",
            "--",
            "/.workstream-guest",
            TRIAL_LIMITS_ARGUMENT,
            &bootstrap,
        ],
        Some(&machine.lease.cgroup()),
    )?;
    command
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null());
    command
        .spawn()
        .map_err(|_| "trial guest launch failed".into())
}

fn classify_io(
    deadline: Instant,
    invocation_cancelled: &AtomicBool,
    relay_cancelled: &AtomicBool,
) -> SmolTrialRuntimeFailure {
    if invocation_cancelled.load(Ordering::Acquire) || relay_cancelled.load(Ordering::Acquire) {
        SmolTrialRuntimeFailure::Cancelled
    } else if Instant::now() >= deadline {
        SmolTrialRuntimeFailure::DeadlineExceeded
    } else {
        SmolTrialRuntimeFailure::InvalidObservation
    }
}

fn classify_cancellations(
    deadline: Instant,
    cancellations: &[&AtomicBool],
) -> SmolTrialRuntimeFailure {
    if cancellations
        .iter()
        .any(|value| value.load(Ordering::Acquire))
    {
        SmolTrialRuntimeFailure::Cancelled
    } else if Instant::now() >= deadline {
        SmolTrialRuntimeFailure::DeadlineExceeded
    } else {
        SmolTrialRuntimeFailure::InvalidObservation
    }
}

fn machine_failure(error: crate::ExecutionFailure) -> SmolTrialRuntimeFailure {
    if error.cleanup_unsettled {
        SmolTrialRuntimeFailure::CleanupUnsettled
    } else if error.code == "capacity_exceeded" {
        SmolTrialRuntimeFailure::CapacityExceeded
    } else if error.code == "deadline_exceeded" {
        SmolTrialRuntimeFailure::DeadlineExceeded
    } else {
        SmolTrialRuntimeFailure::Unavailable
    }
}

fn close_machine(
    machine: &mut Machine,
    result: Result<TrialChildResult, SmolTrialRuntimeFailure>,
) -> Result<TrialChildResult, SmolTrialRuntimeFailure> {
    if machine.close().is_err() {
        return Err(SmolTrialRuntimeFailure::CleanupUnsettled);
    }
    result
}

fn candidate_cache(candidate: &Candidate) -> CacheEntry {
    CacheEntry {
        repository: "workstream/dynamic-trial".into(),
        platform_manifest_digest: candidate.config_image_id.clone(),
        platform_manifest_media_type: "application/vnd.oci.image.manifest.v1+json".into(),
        platform_manifest_byte_count: 1,
        operating_system: "linux".into(),
        architecture: "amd64".into(),
        config_image_id: candidate.config_image_id.clone(),
        smol: Some(SmolImage {
            archive: candidate.archive.clone(),
            archive_sha256: candidate.archive_sha256.clone(),
            image_config: candidate.archive.clone(),
        }),
    }
}

fn replace_workspace(request: &SandboxStepRequest) -> Result<(), SmolTrialRuntimeFailure> {
    let next = request.export_root.join("workspace.next");
    let parent = request
        .workspace_root
        .parent()
        .ok_or(SmolTrialRuntimeFailure::InvalidObservation)?;
    let backup = parent.join(format!(".{}.previous", request.slot_id));
    if backup.exists() {
        return Err(SmolTrialRuntimeFailure::CleanupUnsettled);
    }
    fs::rename(&request.workspace_root, &backup)
        .map_err(|_| SmolTrialRuntimeFailure::CleanupUnsettled)?;
    if fs::rename(&next, &request.workspace_root).is_err() {
        let _ = fs::rename(&backup, &request.workspace_root);
        return Err(SmolTrialRuntimeFailure::CleanupUnsettled);
    }
    fs::remove_dir_all(&backup).map_err(|_| SmolTrialRuntimeFailure::CleanupUnsettled)?;
    fs::remove_dir(&request.export_root).map_err(|_| SmolTrialRuntimeFailure::CleanupUnsettled)
}

fn remove_empty_export(root: &Path) -> Result<(), SmolTrialRuntimeFailure> {
    fs::remove_dir(root).map_err(|_| SmolTrialRuntimeFailure::CleanupUnsettled)
}

impl SmolTrialRuntime for Runtime {
    fn baseline_usage(
        &self,
        config: &SmolTrialConfiguration,
    ) -> Result<SandboxBaselineUsage, SmolTrialRuntimeFailure> {
        if !self.accepts_configuration(config) {
            return Err(SmolTrialRuntimeFailure::InvalidObservation);
        }
        let cancelled = [self.invocation_cancelled.as_ref()];
        let guard = IoGuard {
            deadline: self.deadline,
            client: Some(&self.client),
            cancelled: &cancelled,
        };
        let (observed, environment) = measure_baseline(
            &self.config,
            &self.runtime,
            &self.profile,
            &self.builder,
            &guard,
            &cancelled,
        )?;
        if observed != self.baseline || environment != self.builder_environment {
            return Err(SmolTrialRuntimeFailure::InvalidObservation);
        }
        Ok(observed)
    }

    fn run_build(
        &self,
        config: &SmolTrialConfiguration,
        owner: &SmolTrialOwner,
        request: &SandboxBuildRequest,
        deadline: Instant,
        invocation_cancelled: &AtomicBool,
        relay_cancelled: &AtomicBool,
    ) -> Result<SmolTrialChildResult, SmolTrialRuntimeFailure> {
        let _active = self.begin(owner)?;
        if !self.accepts_configuration(config) || !self.accepts_cancellation(invocation_cancelled) {
            return Err(SmolTrialRuntimeFailure::InvalidObservation);
        }
        let cancelled = [invocation_cancelled, relay_cancelled];
        let guard = IoGuard {
            deadline,
            client: Some(&self.client),
            cancelled: &cancelled,
        };
        crate::trial_engine::offline_cache::verify_offline_cache(
            &self.runtime.offline_cache_root,
            &self.profile.offline_cache_digest,
            deadline,
            &[invocation_cancelled, relay_cancelled],
        )
        .map_err(offline_cache_failure)?;
        let (child_limits, mut resources) = limits(request)?;
        resources.storage_gib = self.profile.maximum_disk_bytes.div_ceil(GIB);
        let capacity =
            super::trial_capacity(resources.memory_bytes, self.profile.maximum_disk_bytes)
                .map_err(|_| SmolTrialRuntimeFailure::CapacityExceeded)?;
        let child_reservation = config
            .reservation
            .child(capacity)
            .map_err(|_| SmolTrialRuntimeFailure::CapacityExceeded)?;
        let (context, _, _) = trial_io::scan_material(
            "context",
            &request.context_root,
            request.mutable_disk_bytes,
            request.mutable_entries,
            &guard,
        )?;
        let (cache, _, _) = trial_io::scan_material(
            "cache",
            &self.runtime.offline_cache_root,
            self.profile.maximum_disk_bytes,
            self.profile.maximum_entries,
            &guard,
        )?;
        let materials = vec![context, cache];
        let operation = trial_io::operation_id(owner, "build");
        let trial_request = TrialRequest::Build {
            schema_version: workstream_checker_guest::TRIAL_REQUEST_PROTOCOL.into(),
            operation_id: operation.clone(),
            context_relative: request.context_relative.clone(),
            dockerfile_relative: request.dockerfile_relative.clone(),
            platform: request.platform.clone(),
            destination: request.destination.clone(),
            limits: child_limits,
            root: TrialFilesystemLimit {
                bytes: request.launcher_root_bytes,
                entries: request.launcher_root_entries,
            },
            tmp: TrialFilesystemLimit {
                bytes: request.launcher_temporary_bytes,
                entries: request.launcher_temporary_entries,
            },
            shm: TrialFilesystemLimit {
                bytes: request.launcher_shared_memory_bytes,
                entries: request.launcher_shared_memory_entries,
            },
            candidate_archive_max_bytes: request
                .launcher_candidate_bytes
                .min(config.maximum_candidate_archive_bytes),
            output_max_bytes: request.maximum_output_bytes as u64,
        };
        let job = GuestJob {
            purpose: GuestPurpose::TrialBuild {
                materials: materials
                    .iter()
                    .map(|source| source.manifest.clone())
                    .collect(),
            },
            request: serde_json::to_value(trial_request)
                .map_err(|_| SmolTrialRuntimeFailure::InvalidObservation)?,
            command: vec![
                "/kaniko/executor".into(),
                format!("--dockerfile=/workspace/{}", request.dockerfile_relative),
                format!("--context=dir:///workspace/{}", request.context_relative),
                "--cache=true".into(),
                "--cache-dir=/cache".into(),
                "--cache-run-layers=false".into(),
                "--cache-copy-layers=false".into(),
                "--no-push".into(),
                "--no-push-cache".into(),
                "--tar-path=/out/candidate.tar".into(),
                "--ignore-path=/out".into(),
                format!("--destination={}", request.destination),
                "--force".into(),
                "--log-format=text".into(),
            ],
            environment: self.builder_environment.clone(),
            working_directory: "/".into(),
            uid: config.candidate_uid,
            gid: config.candidate_gid,
            directories: Vec::new(),
            files: Vec::new(),
        };
        revalidate_machine_inputs(&self.config, &self.builder, &guard)
            .map_err(|_| classify_io(deadline, invocation_cancelled, relay_cancelled))?;
        let mut machine = match Machine::create_child(
            &self.config,
            resources,
            deadline,
            &self.runtime.child_home_root,
        ) {
            Ok(machine) => machine,
            Err(error) => {
                let unsettled = error.cleanup_unsettled;
                let failure = machine_failure(error);
                if unsettled {
                    child_reservation.quarantine();
                }
                return Err(failure);
            }
        };
        let prepared = machine
            .prepare(&self.builder, resources, None, &self.client, deadline)
            .and_then(|_| stage_tools(&machine, &self.runtime, &self.client, &guard));
        let result = match prepared {
            Ok(()) => {
                let child = spawn_guest(&machine, child_limits)
                    .map_err(|_| SmolTrialRuntimeFailure::Unavailable);
                child.and_then(|child| {
                    trial_io::exchange(
                        child,
                        &job,
                        &materials,
                        &operation,
                        ExportTarget::Candidate {
                            path: &request.output_archive,
                            maximum_bytes: config.maximum_candidate_archive_bytes,
                        },
                        &guard,
                    )
                    .map_err(|_| classify_io(deadline, invocation_cancelled, relay_cancelled))
                })
            }
            Err(_) => Err(classify_io(deadline, invocation_cancelled, relay_cancelled)),
        };
        match close_machine(&mut machine, result) {
            Ok(result) => Ok(trial_io::child_result(result, None, None)),
            Err(error) => {
                if error == SmolTrialRuntimeFailure::CleanupUnsettled {
                    child_reservation.quarantine();
                }
                Err(error)
            }
        }
    }

    fn prepare_candidate(
        &self,
        config: &SmolTrialConfiguration,
        owner: &SmolTrialOwner,
        archive: &Path,
        validated: &crate::trial_engine::image_archive::ValidatedImageArchive,
        archive_sha256: &str,
        archive_byte_count: u64,
        deadline: Instant,
    ) -> Result<PreparedCandidateFacts, SmolTrialRuntimeFailure> {
        if !self.accepts_configuration(config) {
            return Err(SmolTrialRuntimeFailure::InvalidObservation);
        }
        let _active = self.begin(owner)?;
        if self.invocation_cancelled.load(Ordering::Acquire) {
            return Err(SmolTrialRuntimeFailure::Cancelled);
        }
        if Instant::now() >= deadline {
            return Err(SmolTrialRuntimeFailure::DeadlineExceeded);
        }
        let metadata = fs::symlink_metadata(archive)
            .map_err(|_| SmolTrialRuntimeFailure::InvalidObservation)?;
        if !metadata.file_type().is_file()
            || metadata.file_type().is_symlink()
            || metadata.len() != archive_byte_count
            || archive_byte_count == 0
            || archive_byte_count > self.runtime.maximum_candidate_archive_bytes
            || validated.archive_byte_count != archive_byte_count
            || validated.archive_sha256 != archive_sha256
        {
            return Err(SmolTrialRuntimeFailure::InvalidObservation);
        }
        let candidate = Candidate {
            owner: owner.clone(),
            archive: archive.to_owned(),
            archive_sha256: archive_sha256.to_owned(),
            archive_byte_count,
            config_image_id: validated.config_image_id.clone(),
            platform: validated.platform.clone(),
            expanded_byte_count: validated.expanded_bytes,
            expanded_entry_count: validated.expanded_entries,
            environment: validated.environment.clone(),
        };
        let mut state = self
            .state
            .lock()
            .map_err(|_| SmolTrialRuntimeFailure::CleanupUnsettled)?;
        if state.candidate.is_some() {
            return Err(SmolTrialRuntimeFailure::InvalidObservation);
        }
        state.candidate = Some(candidate.clone());
        Ok(PreparedCandidateFacts {
            config_image_id: candidate.config_image_id,
            platform: candidate.platform,
            archive_sha256: candidate.archive_sha256,
            archive_byte_count: candidate.archive_byte_count,
            expanded_byte_count: candidate.expanded_byte_count,
            expanded_entry_count: candidate.expanded_entry_count,
        })
    }

    fn run_step(
        &self,
        config: &SmolTrialConfiguration,
        owner: &SmolTrialOwner,
        request: &SandboxStepRequest,
        deadline: Instant,
        invocation_cancelled: &AtomicBool,
        relay_cancelled: &AtomicBool,
    ) -> Result<SmolTrialChildResult, SmolTrialRuntimeFailure> {
        let _active = self.begin(owner)?;
        if !self.accepts_configuration(config) || !self.accepts_cancellation(invocation_cancelled) {
            return Err(SmolTrialRuntimeFailure::InvalidObservation);
        }
        let candidate = self
            .state
            .lock()
            .map_err(|_| SmolTrialRuntimeFailure::CleanupUnsettled)?
            .candidate
            .clone()
            .filter(|candidate| {
                candidate.owner == *owner
                    && candidate.config_image_id == request.candidate_image_digest
            })
            .ok_or(SmolTrialRuntimeFailure::InvalidObservation)?;
        let cancelled = [invocation_cancelled, relay_cancelled];
        let guard = IoGuard {
            deadline,
            client: Some(&self.client),
            cancelled: &cancelled,
        };
        hash_file_bounded(&candidate.archive, &candidate.archive_sha256, &guard)
            .map_err(|_| classify_io(deadline, invocation_cancelled, relay_cancelled))?;
        let (child_limits, mut resources) = step_limits(request)?;
        resources.storage_gib = self.profile.maximum_disk_bytes.div_ceil(GIB);
        let capacity =
            super::trial_capacity(resources.memory_bytes, self.profile.maximum_disk_bytes)
                .map_err(|_| SmolTrialRuntimeFailure::CapacityExceeded)?;
        let child_reservation = config
            .reservation
            .child(capacity)
            .map_err(|_| SmolTrialRuntimeFailure::CapacityExceeded)?;
        let (workspace, _, _) = trial_io::scan_material(
            "workspace",
            &request.workspace_root,
            request.mutable_disk_bytes,
            request.mutable_entries,
            &guard,
        )?;
        let before = trial_io::material_digest(&workspace.manifest)?;
        let mut materials = vec![workspace];
        let mut visible = Vec::with_capacity(request.visible_roles.len());
        let mut seen_roles = HashSet::new();
        for role in &request.visible_roles {
            if !seen_roles.insert(role.role.as_str()) {
                return Err(SmolTrialRuntimeFailure::InvalidObservation);
            }
            let (source, _, _) = trial_io::scan_material(
                &role.role,
                &role.path,
                request.mutable_disk_bytes,
                request.mutable_entries,
                &guard,
            )?;
            materials.push(source);
            visible.push(TrialVisibleRole {
                role: role.role.clone(),
                destination: role.destination_relative.clone(),
            });
        }
        let operation = trial_io::operation_id(owner, &request.slot_id);
        let trial_request = TrialRequest::Step {
            schema_version: workstream_checker_guest::TRIAL_REQUEST_PROTOCOL.into(),
            operation_id: operation.clone(),
            visible_roles: visible,
            limits: child_limits,
            root: TrialFilesystemLimit {
                bytes: request.launcher_root_bytes,
                entries: request.launcher_root_entries,
            },
            workspace: TrialFilesystemLimit {
                bytes: request.launcher_workspace_bytes,
                entries: request.launcher_workspace_entries,
            },
            tmp: TrialFilesystemLimit {
                bytes: request.launcher_temporary_bytes,
                entries: request.launcher_temporary_entries,
            },
            shm: TrialFilesystemLimit {
                bytes: request.launcher_shared_memory_bytes,
                entries: request.launcher_shared_memory_entries,
            },
            output_max_bytes: request.maximum_output_bytes as u64,
        };
        let job = GuestJob {
            purpose: GuestPurpose::TrialStep {
                materials: materials
                    .iter()
                    .map(|source| source.manifest.clone())
                    .collect(),
            },
            request: serde_json::to_value(trial_request)
                .map_err(|_| SmolTrialRuntimeFailure::InvalidObservation)?,
            command: request.command.clone(),
            environment: candidate.environment.clone(),
            working_directory: request.working_directory.clone(),
            uid: config.candidate_uid,
            gid: config.candidate_gid,
            directories: Vec::new(),
            files: Vec::new(),
        };
        let cache = candidate_cache(&candidate);
        revalidate_machine_inputs(&self.config, &cache, &guard)
            .map_err(|_| classify_io(deadline, invocation_cancelled, relay_cancelled))?;
        let mut machine = match Machine::create_child(
            &self.config,
            resources,
            deadline,
            &self.runtime.child_home_root,
        ) {
            Ok(machine) => machine,
            Err(error) => {
                let unsettled = error.cleanup_unsettled;
                let failure = machine_failure(error);
                if unsettled {
                    child_reservation.quarantine();
                }
                return Err(failure);
            }
        };
        let prepared = machine
            .prepare(&cache, resources, None, &self.client, deadline)
            .and_then(|_| stage_tools(&machine, &self.runtime, &self.client, &guard));
        let result = match prepared {
            Ok(()) => {
                let child = spawn_guest(&machine, child_limits)
                    .map_err(|_| SmolTrialRuntimeFailure::Unavailable);
                child.and_then(|child| {
                    trial_io::exchange(
                        child,
                        &job,
                        &materials,
                        &operation,
                        ExportTarget::Workspace {
                            root: &request.export_root,
                            maximum_bytes: request.launcher_workspace_bytes,
                            maximum_entries: request.launcher_workspace_entries,
                        },
                        &guard,
                    )
                    .map_err(|_| classify_io(deadline, invocation_cancelled, relay_cancelled))
                })
            }
            Err(_) => Err(classify_io(deadline, invocation_cancelled, relay_cancelled)),
        };
        let result = match close_machine(&mut machine, result) {
            Ok(result) => result,
            Err(error) => {
                if error == SmolTrialRuntimeFailure::CleanupUnsettled {
                    child_reservation.quarantine();
                }
                return Err(error);
            }
        };
        let after = if result.export_outcome == TrialExportOutcome::Exported {
            trial_io::workspace_digest(&result)?
        } else {
            before.clone()
        };
        if result.export_outcome == TrialExportOutcome::Exported {
            replace_workspace(request)?;
        } else {
            remove_empty_export(&request.export_root)?;
        }
        Ok(trial_io::child_result(result, Some(before), Some(after)))
    }

    fn cleanup_owner(
        &self,
        config: &SmolTrialConfiguration,
        owner: &SmolTrialOwner,
        _deadline: Instant,
    ) -> Result<(), SmolTrialRuntimeFailure> {
        if !self.accepts_configuration(config) {
            return Err(SmolTrialRuntimeFailure::InvalidObservation);
        }
        if self.active.load(Ordering::SeqCst) {
            return Err(SmolTrialRuntimeFailure::CleanupUnsettled);
        }
        let mut state = self
            .state
            .lock()
            .map_err(|_| SmolTrialRuntimeFailure::CleanupUnsettled)?;
        match state.owner.as_ref() {
            None if state.candidate.is_none() => return Ok(()),
            Some(expected)
                if expected == owner
                    && state
                        .candidate
                        .as_ref()
                        .is_none_or(|candidate| candidate.owner == *owner) => {}
            _ => return Err(SmolTrialRuntimeFailure::Unavailable),
        }
        state.candidate = None;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::smol::{Admission, Capacity};
    use crate::trial_engine::{image_archive::ValidatedImageArchive, SandboxEnforcementOverruns};
    use crate::trial_relay::TrialResources;
    use std::os::unix::fs::PermissionsExt;
    use std::os::unix::net::UnixStream;
    use std::time::Duration;

    #[test]
    fn same_size_candidate_mutation_is_rejected_before_child_admission() {
        let (root, config) = crate::tests::test_config();
        struct RemoveRoot(PathBuf);
        impl Drop for RemoveRoot {
            fn drop(&mut self) {
                let _ = fs::remove_dir_all(&self.0);
            }
        }
        let _cleanup = RemoveRoot(root.clone());
        let digest = format!("sha256:{}", "a".repeat(64));
        let profile = TrialProfile {
            profile_id: "profile".into(),
            profile_version: 1,
            profile_digest: digest.clone(),
            projection_id: "projection".into(),
            projection_version: 1,
            projection_digest: digest.clone(),
            trial_kind: "generic_build_run".into(),
            registry_entry_id: "registry".into(),
            registry_entry_digest: digest.clone(),
            checker_image_digest: digest.clone(),
            configuration_sha256: digest.clone(),
            engine_identity_digest: digest.clone(),
            guest_binary_digest: digest.clone(),
            filesystem_tool_digest: digest.clone(),
            outer_runtime_config_digest: digest.clone(),
            child_runtime: "smolvm".into(),
            child_runtime_config_digest: digest.clone(),
            child_transport: "workstream.smol_guest_io.v1".into(),
            platform: "linux/amd64".into(),
            platform_identity_digest: digest.clone(),
            builder_image_digest: digest.clone(),
            trusted_launcher_digest: digest.clone(),
            offline_cache_digest: digest.clone(),
            approved_base_digests: vec![digest.clone()],
            source_material_roles: vec![],
            material_projections: vec![],
            build_context_roles: vec![],
            allowed_material_roles: vec![],
            slot_templates: vec![],
            maximum_frame_bytes: 4096,
            maximum_response_bytes: 4096,
            maximum_steps: 1,
            maximum_total_timeout_ms: 1000,
            maximum_build_timeout_ms: 1000,
            maximum_step_timeout_ms: 1000,
            maximum_step_output_bytes: 1024,
            maximum_observation_bytes: 4096,
            maximum_receipt_bytes: 4096,
            maximum_cpu_quota_millis: 1000,
            maximum_cpu_time_ms: 1000,
            maximum_wall_time_overrun_ms: 0,
            maximum_cpu_time_overrun_ms: 0,
            maximum_memory_bytes: 32 * 1024 * 1024,
            maximum_memory_overrun_bytes: 0,
            maximum_disk_bytes: 64 * 1024 * 1024,
            maximum_disk_overrun_bytes: 0,
            maximum_entries: 256,
            maximum_entries_overrun: 0,
            maximum_pids: 16,
            maximum_pids_overrun: 0,
        };
        // The positive control must stop at child admission, never a real VM.
        // Archive graph validation belongs to image_archive; this fixture starts
        // with that owner's typed facts at the adapter's preparation boundary.
        let credit = Capacity {
            slots: 1,
            memory_bytes: 1,
            storage_bytes: 1,
        };
        let admission = Arc::new(
            Admission::new(
                Capacity {
                    slots: 2,
                    memory_bytes: 2,
                    storage_bytes: 2,
                },
                "test".into(),
            )
            .unwrap(),
        );
        let reservation = admission.reserve(credit, Some(credit)).unwrap();
        let invocation_cancelled = Arc::new(AtomicBool::new(false));
        let (client, _connected_peer) = UnixStream::pair().unwrap();
        let deadline = Instant::now() + Duration::from_secs(5);
        let runtime = Runtime {
            builder: config.cache[0].clone(),
            runtime: TrialRuntimeConfiguration {
                relay_root: root.join("relay"),
                scratch_root: root.join("scratch"),
                child_home_root: root.join("children"),
                outer_runtime_config_digest: digest.clone(),
                offline_cache_root: root.join("cache"),
                deployment_owner: "deployment".into(),
                builder_image_id: digest.clone(),
                trusted_launcher_path: root.join("launcher"),
                trusted_launcher_digest: digest.clone(),
                filesystem_tool_path: root.join("mkfs"),
                filesystem_tool_digest: digest.clone(),
                maximum_candidate_archive_bytes: 1024,
            },
            config,
            profile,
            client,
            builder_environment: vec![],
            baseline: SandboxBaselineUsage {
                bytes: 1,
                entries: 1,
            },
            reservation: reservation.clone(),
            invocation_cancelled: invocation_cancelled.clone(),
            deadline,
            state: Mutex::new(State::default()),
            active: AtomicBool::new(false),
        };
        let configuration = SmolTrialConfiguration {
            identity: runtime.identity(),
            deployment_owner: "deployment".into(),
            request_digest: digest.clone(),
            attempt_id: "attempt".into(),
            maximum_candidate_archive_bytes: 1024,
            candidate_uid: runtime.config.sandbox_uid,
            candidate_gid: runtime.config.sandbox_gid,
            reservation: reservation.clone(),
        };
        let owner = SmolTrialOwner {
            deployment_owner: "deployment".into(),
            request_digest: digest.clone(),
            attempt_id: "attempt".into(),
            trial_owner_id: "trial".into(),
        };
        let archive = root.join("candidate.tar");
        let original = b"candidate layer A";
        let substituted = b"candidate layer B";
        assert_eq!(original.len(), substituted.len());
        fs::write(&archive, original).unwrap();
        fs::set_permissions(&archive, fs::Permissions::from_mode(0o600)).unwrap();
        let identity = fs::metadata(&archive).unwrap();
        let archive_sha256 = format!("sha256:{:x}", Sha256::digest(original));
        let validated = ValidatedImageArchive {
            archive_sha256: archive_sha256.clone(),
            archive_byte_count: original.len() as u64,
            expanded_bytes: 1,
            expanded_entries: 1,
            config_image_id: digest.clone(),
            platform: "linux/amd64".into(),
            environment: vec![],
        };
        runtime
            .prepare_candidate(
                &configuration,
                &owner,
                &archive,
                &validated,
                &archive_sha256,
                original.len() as u64,
                deadline,
            )
            .unwrap();
        let request = SandboxStepRequest {
            owner_id: "trial".into(),
            slot_id: "slot".into(),
            candidate_image_digest: digest,
            workspace_root: root.join("workspace"),
            export_root: root.join("export"),
            visible_roles: vec![],
            visible_role_inventory_digests: vec![],
            command: vec!["/bin/true".into()],
            working_directory: ".".into(),
            resources: TrialResources {
                cpu_quota_millis: 1000,
                cpu_time_ms: 1000,
                memory_bytes: 32 * 1024 * 1024,
                disk_bytes: 64 * 1024 * 1024,
                maximum_entries: 256,
                pids: 16,
            },
            remaining_cpu_time_ms: 1000,
            mutable_disk_bytes: 64 * 1024 * 1024,
            mutable_entries: 256,
            launcher_root_bytes: 4 * 1024 * 1024,
            launcher_root_entries: 32,
            launcher_workspace_bytes: 4 * 1024 * 1024,
            launcher_workspace_entries: 32,
            launcher_temporary_bytes: 4 * 1024 * 1024,
            launcher_temporary_entries: 32,
            launcher_shared_memory_bytes: 4 * 1024 * 1024,
            launcher_shared_memory_entries: 32,
            timeout_ms: 1000,
            maximum_output_bytes: 1024,
            enforcement_overruns: SandboxEnforcementOverruns {
                wall_time_ms: 0,
                cpu_time_ms: 0,
                memory_bytes: 0,
                pids: 0,
                disk_bytes: 0,
                entries: 0,
            },
        };
        let relay_cancelled = AtomicBool::new(false);
        for (bytes, expected) in [
            (original, SmolTrialRuntimeFailure::CapacityExceeded),
            (substituted, SmolTrialRuntimeFailure::InvalidObservation),
            (original, SmolTrialRuntimeFailure::CapacityExceeded),
        ] {
            fs::write(&archive, bytes).unwrap();
            let observed = fs::metadata(&archive).unwrap();
            assert_eq!(
                (
                    observed.dev(),
                    observed.ino(),
                    observed.len(),
                    observed.mode()
                ),
                (
                    identity.dev(),
                    identity.ino(),
                    identity.len(),
                    identity.mode()
                )
            );
            assert_eq!(
                runtime
                    .run_step(
                        &configuration,
                        &owner,
                        &request,
                        deadline,
                        &invocation_cancelled,
                        &relay_cancelled,
                    )
                    .unwrap_err(),
                expected
            );
            // Neither rejection consumes the invocation's sequential child credit.
            drop(reservation.child(credit).unwrap());
            assert!(!request.export_root.exists());
            assert!(!runtime.runtime.child_home_root.exists());
        }
        runtime
            .cleanup_owner(&configuration, &owner, deadline)
            .unwrap();
    }
}
