//! Digest-bound Docker/runsc backend for the generic trial engine.

use crate::trial_engine::{
    SandboxBackendIdentity, SandboxBuildRequest, SandboxBuildResult, SandboxEnforcementOverruns,
    SandboxFailure, SandboxStepRequest, SandboxStepResult, TrialSandboxBackend,
};
use crate::trial_relay::{
    TrialBuildObservation, TrialExportOutcome, TrialOperationOutcome, TrialRelayFailure,
    TrialStepObservation,
};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::{HashMap, HashSet};
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Seek, SeekFrom};
use std::os::unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::atomic::AtomicBool;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};
use workstream_checker_sdk::canonical_hash;

#[path = "trial_docker/image_archive.rs"]
mod image_archive;

static RUNTIME_FILE_SEQUENCE: AtomicU64 = AtomicU64::new(0);

#[derive(Clone, Debug, Deserialize, Hash, PartialEq, Eq, Serialize)]
pub(crate) struct RuntimeOwner {
    pub(crate) deployment_owner: String,
    pub(crate) request_digest: String,
    pub(crate) attempt_id: String,
    pub(crate) trial_owner_id: String,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct OwnedContainerCreate {
    pub(crate) owner: RuntimeOwner,
    pub(crate) name: String,
    /// Docker `create` arguments after ownership labels and before the image.
    pub(crate) arguments: Vec<String>,
    pub(crate) mounts: Vec<OwnedBindMount>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum OwnedMountClass {
    TrustedLauncher,
    LauncherContext,
    LauncherCache,
    LauncherExport,
    LauncherWorkspace,
    LauncherRole,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct OwnedBindMount {
    pub(crate) source: PathBuf,
    pub(crate) destination: String,
    pub(crate) readonly: bool,
    pub(crate) class: OwnedMountClass,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct ContainerExecutionLimits {
    pub(crate) deadline: Instant,
    pub(crate) operation_timeout_ms: u64,
    pub(crate) cpu_time_ms: u64,
    pub(crate) wall_time_overrun_ms: u64,
    pub(crate) cpu_time_overrun_ms: u64,
    pub(crate) memory_bytes: u64,
    pub(crate) memory_overrun_bytes: u64,
    pub(crate) pids: u64,
    pub(crate) pids_overrun: u64,
    pub(crate) disk_bytes: u64,
    pub(crate) disk_overrun_bytes: u64,
    pub(crate) entries: u64,
    pub(crate) entries_overrun: u64,
    pub(crate) output_bytes: usize,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum RuntimeTermination {
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
pub(crate) struct ObservedContainerExit {
    pub(crate) termination: RuntimeTermination,
    pub(crate) exit_code: Option<i32>,
    pub(crate) signal: Option<i32>,
    pub(crate) stdout: String,
    pub(crate) stderr: String,
    pub(crate) elapsed_ms: u64,
    pub(crate) cpu_time_ms: u64,
    pub(crate) peak_memory_bytes: u64,
    pub(crate) peak_pids: u64,
    pub(crate) written_bytes: u64,
    pub(crate) written_entries: u64,
    pub(crate) measurement_method: String,
    pub(crate) workspace_before_sha256: Option<String>,
    pub(crate) workspace_after_sha256: Option<String>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct LoadedOwnedImage {
    pub(crate) config_image_id: String,
    pub(crate) archive_sha256: String,
    pub(crate) archive_byte_count: u64,
    pub(crate) expanded_byte_count: u64,
    pub(crate) expanded_entry_count: u64,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum RuntimeControlFailure {
    InvalidConfiguration,
    ImageUnavailable,
    CacheUnavailable,
    LaunchUnavailable,
    DeadlineExceeded,
    Cancelled,
    CapacityExceeded,
    InvalidObservation,
    CleanupUnsettled,
}

/// Module-neutral owner/cancellation/measurement surface extracted from main by #492.
pub(crate) trait RuntimeControl: Send + Sync + 'static {
    fn require_image(
        &self,
        config_image_id: &str,
        identity: &SandboxBackendIdentity,
        runtime_key: &str,
        deadline: Instant,
    ) -> Result<(), RuntimeControlFailure>;

    fn require_offline_cache(
        &self,
        root: &std::path::Path,
        inventory_digest: &str,
    ) -> Result<(), RuntimeControlFailure>;

    fn create_owned_container(
        &self,
        request: OwnedContainerCreate,
        deadline: Instant,
        invocation_cancelled: &AtomicBool,
        relay_cancelled: &AtomicBool,
    ) -> Result<(), RuntimeControlFailure>;

    fn run_owned_container(
        &self,
        owner: &RuntimeOwner,
        name: &str,
        writable_roots: &[PathBuf],
        limits: &ContainerExecutionLimits,
        invocation_cancelled: &AtomicBool,
        relay_cancelled: &AtomicBool,
    ) -> Result<ObservedContainerExit, RuntimeControlFailure>;

    /// Validate exactly one expected tag/image in the archive before and after load.
    fn load_single_owned_image(
        &self,
        owner: &RuntimeOwner,
        archive: &std::path::Path,
        expected_tag: &str,
        maximum_bytes: u64,
        maximum_expanded_bytes: u64,
        maximum_expanded_entries: u64,
        deadline: Instant,
    ) -> Result<LoadedOwnedImage, RuntimeControlFailure>;

    /// Kill/remove only exact owner-labelled containers/images and confirm absence.
    fn cleanup_owner(
        &self,
        owner: &RuntimeOwner,
        deadline: Instant,
    ) -> Result<(), RuntimeControlFailure>;
}

impl<C: RuntimeControl> RuntimeControl for Arc<C> {
    fn require_image(
        &self,
        config_image_id: &str,
        identity: &SandboxBackendIdentity,
        runtime_key: &str,
        deadline: Instant,
    ) -> Result<(), RuntimeControlFailure> {
        (**self).require_image(config_image_id, identity, runtime_key, deadline)
    }

    fn require_offline_cache(
        &self,
        root: &std::path::Path,
        inventory_digest: &str,
    ) -> Result<(), RuntimeControlFailure> {
        (**self).require_offline_cache(root, inventory_digest)
    }

    fn create_owned_container(
        &self,
        request: OwnedContainerCreate,
        deadline: Instant,
        invocation_cancelled: &AtomicBool,
        relay_cancelled: &AtomicBool,
    ) -> Result<(), RuntimeControlFailure> {
        (**self).create_owned_container(request, deadline, invocation_cancelled, relay_cancelled)
    }

    fn run_owned_container(
        &self,
        owner: &RuntimeOwner,
        name: &str,
        writable_roots: &[PathBuf],
        limits: &ContainerExecutionLimits,
        invocation_cancelled: &AtomicBool,
        relay_cancelled: &AtomicBool,
    ) -> Result<ObservedContainerExit, RuntimeControlFailure> {
        (**self).run_owned_container(
            owner,
            name,
            writable_roots,
            limits,
            invocation_cancelled,
            relay_cancelled,
        )
    }

    fn load_single_owned_image(
        &self,
        owner: &RuntimeOwner,
        archive: &std::path::Path,
        expected_tag: &str,
        maximum_bytes: u64,
        maximum_expanded_bytes: u64,
        maximum_expanded_entries: u64,
        deadline: Instant,
    ) -> Result<LoadedOwnedImage, RuntimeControlFailure> {
        (**self).load_single_owned_image(
            owner,
            archive,
            expected_tag,
            maximum_bytes,
            maximum_expanded_bytes,
            maximum_expanded_entries,
            deadline,
        )
    }

    fn cleanup_owner(
        &self,
        owner: &RuntimeOwner,
        deadline: Instant,
    ) -> Result<(), RuntimeControlFailure> {
        (**self).cleanup_owner(owner, deadline)
    }
}

#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
struct OwnedRuntimeResources {
    containers: Vec<String>,
    images: Vec<(String, String)>,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct RuntimeJournal {
    schema_version: String,
    owner: RuntimeOwner,
    resources: OwnedRuntimeResources,
}

/// Concrete Docker CLI + cgroup-v2 control used on a dedicated runsc node.
#[derive(Debug)]
pub(crate) struct DockerRuntimeControl {
    docker_binary: PathBuf,
    runtime_root: PathBuf,
    runtime_configuration: PathBuf,
    owned: Mutex<HashMap<RuntimeOwner, OwnedRuntimeResources>>,
}

impl DockerRuntimeControl {
    pub(crate) fn new(
        docker_binary: PathBuf,
        runtime_root: PathBuf,
        runtime_configuration: PathBuf,
    ) -> Result<Self, RuntimeControlFailure> {
        let binary = fs::canonicalize(&docker_binary)
            .map_err(|_| RuntimeControlFailure::InvalidConfiguration)?;
        let binary_metadata = fs::symlink_metadata(&binary)
            .map_err(|_| RuntimeControlFailure::InvalidConfiguration)?;
        let root = fs::canonicalize(&runtime_root)
            .map_err(|_| RuntimeControlFailure::InvalidConfiguration)?;
        let root_metadata =
            fs::symlink_metadata(&root).map_err(|_| RuntimeControlFailure::InvalidConfiguration)?;
        let runtime_configuration = fs::canonicalize(&runtime_configuration)
            .map_err(|_| RuntimeControlFailure::InvalidConfiguration)?;
        let configuration_metadata = fs::symlink_metadata(&runtime_configuration)
            .map_err(|_| RuntimeControlFailure::InvalidConfiguration)?;
        if !binary_metadata.file_type().is_file()
            || binary_metadata.permissions().mode() & 0o111 == 0
            || !root_metadata.file_type().is_dir()
            || root_metadata.file_type().is_symlink()
            || root_metadata.permissions().mode() & 0o077 != 0
            || !configuration_metadata.file_type().is_file()
            || configuration_metadata.file_type().is_symlink()
        {
            return Err(RuntimeControlFailure::InvalidConfiguration);
        }
        let owned = load_runtime_journals(&root)?;
        Ok(Self {
            docker_binary: binary,
            runtime_root: root,
            runtime_configuration,
            owned: Mutex::new(owned),
        })
    }

    pub(crate) fn recover_deployment(
        &self,
        deployment_owner: &str,
        deadline: Instant,
    ) -> Result<(), RuntimeControlFailure> {
        if !valid_label_value(deployment_owner, 128) {
            return Err(RuntimeControlFailure::InvalidConfiguration);
        }
        let owners = self
            .owned
            .lock()
            .map_err(|_| RuntimeControlFailure::CleanupUnsettled)?
            .keys()
            .filter(|owner| owner.deployment_owner == deployment_owner)
            .cloned()
            .collect::<Vec<_>>();
        for owner in owners {
            self.cleanup_owner(&owner, deadline)?;
        }
        Ok(())
    }

    fn persist_owner(
        &self,
        owner: &RuntimeOwner,
        resources: &OwnedRuntimeResources,
    ) -> Result<(), RuntimeControlFailure> {
        persist_runtime_journal(&self.runtime_root, owner, resources)
    }

    fn command(
        &self,
        arguments: &[String],
        deadline: Instant,
        maximum_output: usize,
    ) -> Result<CommandResult, RuntimeControlFailure> {
        let nonce = format!(
            "{:016x}",
            RUNTIME_FILE_SEQUENCE.fetch_add(1, Ordering::Relaxed)
        );
        let stdout_path = self.runtime_root.join(format!(".runtime-{nonce}.stdout"));
        let stderr_path = self.runtime_root.join(format!(".runtime-{nonce}.stderr"));
        let stdout = create_output(&stdout_path)?;
        let stderr = create_output(&stderr_path)?;
        let mut child = Command::new(&self.docker_binary)
            .args(arguments)
            .stdin(Stdio::null())
            .stdout(stdout)
            .stderr(stderr)
            .spawn()
            .map_err(|_| RuntimeControlFailure::LaunchUnavailable)?;
        let status = loop {
            if Instant::now() >= deadline {
                let _ = child.kill();
                let _ = child.wait();
                remove_outputs(&stdout_path, &stderr_path);
                return Err(RuntimeControlFailure::DeadlineExceeded);
            }
            match child.try_wait() {
                Ok(Some(status)) => break status,
                Ok(None) => {
                    if output_size(&stdout_path, &stderr_path)? > maximum_output as u64 {
                        let _ = child.kill();
                        let _ = child.wait();
                        remove_outputs(&stdout_path, &stderr_path);
                        return Err(RuntimeControlFailure::CapacityExceeded);
                    }
                }
                Err(_) => {
                    remove_outputs(&stdout_path, &stderr_path);
                    return Err(RuntimeControlFailure::LaunchUnavailable);
                }
            }
            thread::sleep(Duration::from_millis(5));
        };
        let stdout = read_bounded(&stdout_path, maximum_output)?;
        let stderr = read_bounded(&stderr_path, maximum_output.saturating_sub(stdout.len()))?;
        remove_outputs(&stdout_path, &stderr_path);
        Ok(CommandResult {
            success: status.success(),
            stdout,
            stderr,
        })
    }

    fn kill_container(&self, name: &str, deadline: Instant) {
        let _ = self.command(&["kill".into(), name.into()], deadline, 64 * 1024);
    }

    fn container_pid(&self, name: &str, deadline: Instant) -> Option<u32> {
        let output = self
            .command(
                &[
                    "inspect".into(),
                    "--format".into(),
                    "{{.State.Pid}}".into(),
                    name.into(),
                ],
                deadline,
                1024,
            )
            .ok()?;
        if !output.success {
            return None;
        }
        std::str::from_utf8(&output.stdout)
            .ok()?
            .trim()
            .parse()
            .ok()
    }

    fn container_state(
        &self,
        name: &str,
        deadline: Instant,
    ) -> Result<ContainerState, RuntimeControlFailure> {
        let output = self.command(
            &[
                "inspect".into(),
                "--format".into(),
                "{{json .State}}".into(),
                name.into(),
            ],
            deadline,
            64 * 1024,
        )?;
        if !output.success {
            return Err(RuntimeControlFailure::InvalidObservation);
        }
        let value: serde_json::Value = serde_json::from_slice(&output.stdout)
            .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
        Ok(ContainerState {
            exit_code: value
                .get("ExitCode")
                .and_then(serde_json::Value::as_i64)
                .and_then(|item| i32::try_from(item).ok()),
            oom_killed: value
                .get("OOMKilled")
                .and_then(serde_json::Value::as_bool)
                .unwrap_or(false),
        })
    }
}

struct CommandResult {
    success: bool,
    stdout: Vec<u8>,
    #[allow(dead_code)]
    stderr: Vec<u8>,
}

struct ContainerState {
    exit_code: Option<i32>,
    oom_killed: bool,
}

#[derive(Default)]
struct Measurements {
    cgroup_samples: u64,
    cpu_time_ms: u64,
    peak_memory_bytes: u64,
    peak_pids: u64,
    written_bytes: u64,
    written_entries: u64,
}

impl RuntimeControl for DockerRuntimeControl {
    fn require_image(
        &self,
        config_image_id: &str,
        identity: &SandboxBackendIdentity,
        runtime_key: &str,
        deadline: Instant,
    ) -> Result<(), RuntimeControlFailure> {
        if !valid_sha256(config_image_id)
            || !valid_relative_label(runtime_key)
            || !valid_sha256(&identity.engine_identity_digest)
            || !valid_sha256(&identity.child_runtime_config_digest)
            || !valid_sha256(&identity.platform_identity_digest)
            || identity.child_runtime != "runsc"
            || identity.child_host_uds != "none"
        {
            return Err(RuntimeControlFailure::InvalidConfiguration);
        }
        let configuration = read_bounded(&self.runtime_configuration, 1024 * 1024)?;
        if sha256_bytes(&configuration) != identity.child_runtime_config_digest {
            return Err(RuntimeControlFailure::ImageUnavailable);
        }
        let configuration: serde_json::Value = serde_json::from_slice(&configuration)
            .map_err(|_| RuntimeControlFailure::InvalidConfiguration)?;
        let runtime = configuration
            .pointer(&format!("/runtimes/{runtime_key}"))
            .and_then(serde_json::Value::as_object)
            .ok_or(RuntimeControlFailure::ImageUnavailable)?;
        let runtime_path = runtime
            .get("path")
            .and_then(serde_json::Value::as_str)
            .map(std::path::Path::new)
            .ok_or(RuntimeControlFailure::ImageUnavailable)?;
        let runtime_arguments = runtime
            .get("runtimeArgs")
            .and_then(serde_json::Value::as_array)
            .ok_or(RuntimeControlFailure::ImageUnavailable)?;
        if !runtime_path.is_absolute()
            || runtime_arguments.iter().any(|value| {
                value.as_str().is_some_and(|argument| {
                    argument.starts_with("--host-uds=") && argument != "--host-uds=none"
                })
            })
            || !runtime_arguments
                .iter()
                .any(|value| value.as_str() == Some("--host-uds=none"))
        {
            return Err(RuntimeControlFailure::ImageUnavailable);
        }
        let runtime_path =
            fs::canonicalize(runtime_path).map_err(|_| RuntimeControlFailure::ImageUnavailable)?;
        if hash_bounded_file(&runtime_path, 1024 * 1024 * 1024)? != identity.engine_identity_digest
        {
            return Err(RuntimeControlFailure::ImageUnavailable);
        }
        let platform = self.command(
            &["info".into(), "--format".into(), "{{json .}}".into()],
            deadline,
            1024 * 1024,
        )?;
        if !platform.success {
            return Err(RuntimeControlFailure::ImageUnavailable);
        }
        let platform: serde_json::Value = serde_json::from_slice(&platform.stdout)
            .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
        if platform
            .get("Runtimes")
            .and_then(serde_json::Value::as_object)
            .is_none_or(|runtimes| !runtimes.contains_key(runtime_key))
        {
            return Err(RuntimeControlFailure::ImageUnavailable);
        }
        let platform = serde_json::json!({
            "architecture": platform.get("Architecture"),
            "cgroup_driver": platform.get("CgroupDriver"),
            "cgroup_version": platform.get("CgroupVersion"),
            "driver": platform.get("Driver"),
            "kernel_version": platform.get("KernelVersion"),
            "operating_system": platform.get("OperatingSystem"),
            "os_type": platform.get("OSType"),
            "runtime": {
                "path": platform.pointer(&format!("/Runtimes/{runtime_key}/path")),
                "runtime_args": platform.pointer(&format!("/Runtimes/{runtime_key}/runtimeArgs")),
            },
        });
        if canonical_hash(&platform).map_err(|_| RuntimeControlFailure::InvalidObservation)?
            != identity.platform_identity_digest
        {
            return Err(RuntimeControlFailure::ImageUnavailable);
        }
        let output = self.command(
            &[
                "image".into(),
                "inspect".into(),
                "--format".into(),
                "{{json .}}".into(),
                config_image_id.into(),
            ],
            deadline,
            1024 * 1024,
        )?;
        if !output.success {
            return Err(RuntimeControlFailure::ImageUnavailable);
        }
        let value: serde_json::Value = serde_json::from_slice(&output.stdout)
            .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
        if value.get("Id").and_then(serde_json::Value::as_str) != Some(config_image_id) {
            return Err(RuntimeControlFailure::ImageUnavailable);
        }
        Ok(())
    }

    fn require_offline_cache(
        &self,
        root: &std::path::Path,
        inventory_digest: &str,
    ) -> Result<(), RuntimeControlFailure> {
        let canonical = canonical_directory(root)?;
        if canonical != root || !valid_sha256(inventory_digest) {
            return Err(RuntimeControlFailure::CacheUnavailable);
        }
        let manifest_path = canonical
            .parent()
            .ok_or(RuntimeControlFailure::CacheUnavailable)?
            .join("cache.sha256");
        let manifest = read_bounded(&manifest_path, 1024 * 1024)
            .map_err(|_| RuntimeControlFailure::CacheUnavailable)?;
        if sha256_bytes(&manifest) != inventory_digest {
            return Err(RuntimeControlFailure::CacheUnavailable);
        }
        validate_sha256_manifest(&canonical, &manifest)?;
        Ok(())
    }

    fn create_owned_container(
        &self,
        request: OwnedContainerCreate,
        deadline: Instant,
        invocation_cancelled: &AtomicBool,
        relay_cancelled: &AtomicBool,
    ) -> Result<(), RuntimeControlFailure> {
        require_available(deadline, invocation_cancelled, relay_cancelled)?;
        validate_owner(&request.owner)?;
        validate_container_name(&request.name)?;
        validate_docker_arguments(&request.arguments)?;
        if request.mounts.is_empty() || request.mounts.len() > 32 {
            return Err(RuntimeControlFailure::InvalidConfiguration);
        }
        let mut arguments = vec![
            "container".into(),
            "create".into(),
            "--name".into(),
            request.name.clone(),
        ];
        for (key, value) in owner_labels(&request.owner) {
            arguments.extend(["--label".into(), format!("{key}={value}")]);
        }
        for mount in &request.mounts {
            validate_owned_mount(mount)?;
            let mut specification = format!(
                "type=bind,src={},dst={}",
                mount.source.display(),
                mount.destination
            );
            if mount.readonly {
                specification.push_str(",readonly");
            }
            arguments.extend(["--mount".into(), specification]);
        }
        arguments.extend(request.arguments.iter().cloned());
        {
            let mut owned = self
                .owned
                .lock()
                .map_err(|_| RuntimeControlFailure::CleanupUnsettled)?;
            let resources = owned.entry(request.owner.clone()).or_default();
            if resources
                .containers
                .iter()
                .any(|item| item == &request.name)
            {
                return Err(RuntimeControlFailure::InvalidObservation);
            }
            resources.containers.push(request.name.clone());
            if self.persist_owner(&request.owner, resources).is_err() {
                resources.containers.pop();
                return Err(RuntimeControlFailure::CleanupUnsettled);
            }
        }
        let output = self.command(&arguments, deadline, 1024 * 1024)?;
        if !output.success {
            return Err(RuntimeControlFailure::LaunchUnavailable);
        }
        let identifier = std::str::from_utf8(&output.stdout)
            .map_err(|_| RuntimeControlFailure::InvalidObservation)?
            .trim();
        if !valid_full_container_id(identifier) {
            return Err(RuntimeControlFailure::InvalidObservation);
        }
        if !owned_container_matches(self, &request.name, &request.owner, deadline)? {
            return Err(RuntimeControlFailure::InvalidObservation);
        }
        Ok(())
    }

    fn run_owned_container(
        &self,
        owner: &RuntimeOwner,
        name: &str,
        writable_roots: &[PathBuf],
        limits: &ContainerExecutionLimits,
        invocation_cancelled: &AtomicBool,
        relay_cancelled: &AtomicBool,
    ) -> Result<ObservedContainerExit, RuntimeControlFailure> {
        validate_owner(owner)?;
        validate_container_name(name)?;
        if !owned_container_matches(self, name, owner, limits.deadline)? {
            return Err(RuntimeControlFailure::InvalidObservation);
        }
        let roots = writable_roots
            .iter()
            .map(|root| {
                let canonical = canonical_directory(root)?;
                if &canonical != root {
                    return Err(RuntimeControlFailure::InvalidConfiguration);
                }
                Ok(canonical)
            })
            .collect::<Result<Vec<_>, _>>()?;
        let workspace_before_sha256 = combined_tree_digest(&roots, limits)?;
        let nonce = format!(
            "{:016x}",
            RUNTIME_FILE_SEQUENCE.fetch_add(1, Ordering::Relaxed)
        );
        let stdout_path = self.runtime_root.join(format!(".container-{nonce}.stdout"));
        let stderr_path = self.runtime_root.join(format!(".container-{nonce}.stderr"));
        let stdout = create_output(&stdout_path)?;
        let stderr = create_output(&stderr_path)?;
        let mut child = Command::new(&self.docker_binary)
            .args(["container", "start", "--attach", name])
            .stdin(Stdio::null())
            .stdout(stdout)
            .stderr(stderr)
            .spawn()
            .map_err(|_| RuntimeControlFailure::LaunchUnavailable)?;
        let started = Instant::now();
        let operation_deadline = started
            .checked_add(Duration::from_millis(limits.operation_timeout_ms))
            .unwrap_or(limits.deadline);
        let mut measurements = Measurements::default();
        let mut forced = None;
        loop {
            if invocation_cancelled.load(Ordering::SeqCst) || relay_cancelled.load(Ordering::SeqCst)
            {
                stop_runtime_child(self, &mut child, name, limits.deadline);
                remove_outputs(&stdout_path, &stderr_path);
                return Err(RuntimeControlFailure::Cancelled);
            }
            if Instant::now() >= limits.deadline && limits.deadline < operation_deadline {
                stop_runtime_child(self, &mut child, name, limits.deadline);
                remove_outputs(&stdout_path, &stderr_path);
                return Err(RuntimeControlFailure::DeadlineExceeded);
            }
            if forced.is_none() && Instant::now() >= operation_deadline {
                forced = Some(RuntimeTermination::DeadlineExceeded);
            }
            if forced.is_none()
                && output_size(&stdout_path, &stderr_path)? > limits.output_bytes as u64
            {
                forced = Some(RuntimeTermination::OutputExceeded);
            }
            let usage = combined_tree_usage(&roots)?;
            measurements.written_bytes = measurements.written_bytes.max(usage.0);
            measurements.written_entries = measurements.written_entries.max(usage.1);
            if forced.is_none() && usage.0 > limits.disk_bytes {
                forced = Some(RuntimeTermination::DiskExceeded);
            }
            if forced.is_none() && usage.1 > limits.entries {
                forced = Some(RuntimeTermination::DiskExceeded);
            }
            if let Some(pid) = self.container_pid(name, limits.deadline) {
                if let Ok(sample) = sample_cgroup(pid) {
                    measurements.cgroup_samples = measurements.cgroup_samples.saturating_add(1);
                    measurements.cpu_time_ms = measurements.cpu_time_ms.max(sample.cpu_time_ms);
                    measurements.peak_memory_bytes =
                        measurements.peak_memory_bytes.max(sample.peak_memory_bytes);
                    measurements.peak_pids = measurements.peak_pids.max(sample.peak_pids);
                }
            }
            if forced.is_none() && measurements.cpu_time_ms > limits.cpu_time_ms {
                forced = Some(RuntimeTermination::CpuExceeded);
            }
            if forced.is_none() && measurements.peak_memory_bytes > limits.memory_bytes {
                forced = Some(RuntimeTermination::MemoryExceeded);
            }
            if forced.is_none() && measurements.peak_pids > limits.pids {
                forced = Some(RuntimeTermination::PidExceeded);
            }
            if forced.is_some() {
                self.kill_container(name, limits.deadline);
            }
            match child.try_wait() {
                Ok(Some(_)) => break,
                Ok(None) => thread::sleep(Duration::from_millis(10)),
                Err(_) => {
                    stop_runtime_child(self, &mut child, name, limits.deadline);
                    remove_outputs(&stdout_path, &stderr_path);
                    return Err(RuntimeControlFailure::LaunchUnavailable);
                }
            }
        }
        let state = self.container_state(name, limits.deadline)?;
        let elapsed_ms = elapsed_ms(started);
        let stdout = read_prefix(&stdout_path, limits.output_bytes)?;
        let stderr = read_prefix(
            &stderr_path,
            limits.output_bytes.saturating_sub(stdout.len()),
        )?;
        remove_outputs(&stdout_path, &stderr_path);
        let stdout =
            String::from_utf8(stdout).map_err(|_| RuntimeControlFailure::InvalidObservation)?;
        let stderr =
            String::from_utf8(stderr).map_err(|_| RuntimeControlFailure::InvalidObservation)?;
        let usage = combined_tree_usage(&roots)?;
        measurements.written_bytes = measurements.written_bytes.max(usage.0);
        measurements.written_entries = measurements.written_entries.max(usage.1);
        let workspace_after_sha256 = combined_tree_digest(&roots, limits)?;
        if measurements.cgroup_samples == 0 {
            return Err(RuntimeControlFailure::InvalidObservation);
        }
        let termination = forced.unwrap_or(if state.oom_killed {
            RuntimeTermination::MemoryExceeded
        } else {
            // Docker exposes an exit status here, not the signal provenance.
            // Statuses >= 128 may also be emitted directly by an application.
            RuntimeTermination::Exited
        });
        validate_measurement_overruns(&measurements, elapsed_ms, termination, limits)?;
        let exit_code = if termination == RuntimeTermination::Exited {
            state.exit_code
        } else {
            None
        };
        Ok(ObservedContainerExit {
            termination,
            exit_code,
            signal: None,
            stdout,
            stderr,
            elapsed_ms,
            cpu_time_ms: measurements.cpu_time_ms,
            peak_memory_bytes: measurements.peak_memory_bytes,
            peak_pids: measurements.peak_pids,
            written_bytes: measurements.written_bytes,
            written_entries: measurements.written_entries,
            measurement_method: "cgroup_v2_sampled_cpu_usage_memory_peak_pids_peak_and_owned_tree"
                .into(),
            workspace_before_sha256: Some(workspace_before_sha256),
            workspace_after_sha256: Some(workspace_after_sha256),
        })
    }

    fn load_single_owned_image(
        &self,
        owner: &RuntimeOwner,
        archive: &std::path::Path,
        expected_tag: &str,
        maximum_bytes: u64,
        maximum_expanded_bytes: u64,
        maximum_expanded_entries: u64,
        deadline: Instant,
    ) -> Result<LoadedOwnedImage, RuntimeControlFailure> {
        validate_owner(owner)?;
        validate_image_tag(expected_tag)?;
        let canonical =
            fs::canonicalize(archive).map_err(|_| RuntimeControlFailure::InvalidObservation)?;
        if canonical != archive {
            return Err(RuntimeControlFailure::InvalidObservation);
        }
        let metadata = fs::symlink_metadata(&canonical)
            .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
        if !metadata.file_type().is_file() || metadata.len() == 0 || metadata.len() > maximum_bytes
        {
            return Err(RuntimeControlFailure::InvalidObservation);
        }
        let expanded = validate_single_image_archive(
            &canonical,
            expected_tag,
            maximum_bytes,
            maximum_expanded_bytes,
            maximum_expanded_entries,
            deadline,
        )?;
        if image_exists(self, expected_tag, deadline)? {
            return Err(RuntimeControlFailure::InvalidObservation);
        }
        {
            let mut owned = self
                .owned
                .lock()
                .map_err(|_| RuntimeControlFailure::CleanupUnsettled)?;
            let resources = owned.entry(owner.clone()).or_default();
            if resources.images.iter().any(|item| item.0 == expected_tag) {
                return Err(RuntimeControlFailure::InvalidObservation);
            }
            resources.images.push((expected_tag.into(), String::new()));
            if self.persist_owner(owner, resources).is_err() {
                resources.images.pop();
                return Err(RuntimeControlFailure::CleanupUnsettled);
            }
        }
        let output = self.command(
            &[
                "image".into(),
                "load".into(),
                "--input".into(),
                canonical.display().to_string(),
            ],
            deadline,
            1024 * 1024,
        )?;
        if !output.success {
            return Err(RuntimeControlFailure::LaunchUnavailable);
        }
        let inspected = self.command(
            &[
                "image".into(),
                "inspect".into(),
                "--format".into(),
                "{{.Id}}".into(),
                expected_tag.into(),
            ],
            deadline,
            4096,
        )?;
        let config_image_id = std::str::from_utf8(&inspected.stdout)
            .map_err(|_| RuntimeControlFailure::InvalidObservation)?
            .trim()
            .to_owned();
        if !inspected.success || !valid_sha256(&config_image_id) {
            return Err(RuntimeControlFailure::InvalidObservation);
        }
        let archive_sha256 = hash_bounded_file(&canonical, maximum_bytes)?;
        let mut owned = self
            .owned
            .lock()
            .map_err(|_| RuntimeControlFailure::CleanupUnsettled)?;
        let resources = owned
            .get_mut(owner)
            .ok_or(RuntimeControlFailure::CleanupUnsettled)?;
        let image = resources
            .images
            .iter_mut()
            .find(|item| item.0 == expected_tag)
            .ok_or(RuntimeControlFailure::CleanupUnsettled)?;
        image.1.clone_from(&config_image_id);
        self.persist_owner(owner, resources)?;
        Ok(LoadedOwnedImage {
            config_image_id,
            archive_sha256,
            archive_byte_count: metadata.len(),
            expanded_byte_count: expanded.bytes,
            expanded_entry_count: expanded.entries,
        })
    }

    fn cleanup_owner(
        &self,
        owner: &RuntimeOwner,
        deadline: Instant,
    ) -> Result<(), RuntimeControlFailure> {
        validate_owner(owner)?;
        let resources = self
            .owned
            .lock()
            .map_err(|_| RuntimeControlFailure::CleanupUnsettled)?
            .get(owner)
            .cloned()
            .unwrap_or_default();
        for name in resources.containers.iter().rev() {
            if container_exists(self, name, deadline)? {
                if !owned_container_matches(self, name, owner, deadline)? {
                    return Err(RuntimeControlFailure::CleanupUnsettled);
                }
                let removed = self.command(
                    &[
                        "container".into(),
                        "rm".into(),
                        "--force".into(),
                        "--volumes".into(),
                        name.clone(),
                    ],
                    deadline,
                    64 * 1024,
                )?;
                if !removed.success || container_exists(self, name, deadline)? {
                    return Err(RuntimeControlFailure::CleanupUnsettled);
                }
            }
        }
        for (tag, identifier) in resources.images.iter().rev() {
            if image_exists(self, tag, deadline)? {
                let inspected = self.command(
                    &[
                        "image".into(),
                        "inspect".into(),
                        "--format".into(),
                        "{{.Id}}".into(),
                        tag.clone(),
                    ],
                    deadline,
                    4096,
                )?;
                if !identifier.is_empty()
                    && std::str::from_utf8(&inspected.stdout).ok().map(str::trim)
                        != Some(identifier)
                {
                    return Err(RuntimeControlFailure::CleanupUnsettled);
                }
                let removed = self.command(
                    &["image".into(), "rm".into(), tag.clone()],
                    deadline,
                    64 * 1024,
                )?;
                if !removed.success || image_exists(self, tag, deadline)? {
                    return Err(RuntimeControlFailure::CleanupUnsettled);
                }
            }
        }
        self.owned
            .lock()
            .map_err(|_| RuntimeControlFailure::CleanupUnsettled)?
            .remove(owner);
        remove_runtime_journal(&self.runtime_root, owner)?;
        Ok(())
    }
}

fn runtime_journal_path(
    root: &std::path::Path,
    owner: &RuntimeOwner,
) -> Result<PathBuf, RuntimeControlFailure> {
    let value =
        serde_json::to_value(owner).map_err(|_| RuntimeControlFailure::InvalidConfiguration)?;
    let digest = canonical_hash(&value).map_err(|_| RuntimeControlFailure::InvalidConfiguration)?;
    Ok(root.join(format!(".trial-owner-{}.json", &digest[7..])))
}

fn validate_runtime_resources(
    owner: &RuntimeOwner,
    resources: &OwnedRuntimeResources,
) -> Result<(), RuntimeControlFailure> {
    validate_owner(owner)?;
    if resources.containers.len() > 64 || resources.images.len() > 8 {
        return Err(RuntimeControlFailure::InvalidConfiguration);
    }
    let mut containers = HashSet::new();
    for name in &resources.containers {
        validate_container_name(name)?;
        if !containers.insert(name) {
            return Err(RuntimeControlFailure::InvalidConfiguration);
        }
    }
    let expected_tag = format!(
        "workstream-trial:{}",
        owner
            .trial_owner_id
            .strip_prefix("trial_")
            .ok_or(RuntimeControlFailure::InvalidConfiguration)?
    );
    let mut images = HashSet::new();
    for (tag, identifier) in &resources.images {
        validate_image_tag(tag)?;
        if tag != &expected_tag
            || (!identifier.is_empty() && !valid_sha256(identifier))
            || !images.insert(tag)
        {
            return Err(RuntimeControlFailure::InvalidConfiguration);
        }
    }
    Ok(())
}

fn load_runtime_journals(
    root: &std::path::Path,
) -> Result<HashMap<RuntimeOwner, OwnedRuntimeResources>, RuntimeControlFailure> {
    let root_metadata =
        fs::symlink_metadata(root).map_err(|_| RuntimeControlFailure::InvalidConfiguration)?;
    let mut entries = fs::read_dir(root)
        .map_err(|_| RuntimeControlFailure::InvalidConfiguration)?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|_| RuntimeControlFailure::InvalidConfiguration)?;
    entries.sort_by_key(std::fs::DirEntry::file_name);
    let mut loaded = HashMap::new();
    for entry in entries {
        let name = entry.file_name();
        let Some(name) = name.to_str() else {
            continue;
        };
        if !name.starts_with(".trial-owner-") || !name.ends_with(".json") {
            continue;
        }
        let path = entry.path();
        let metadata =
            fs::symlink_metadata(&path).map_err(|_| RuntimeControlFailure::CleanupUnsettled)?;
        if !metadata.file_type().is_file()
            || metadata.file_type().is_symlink()
            || metadata.permissions().mode() & 0o777 != 0o600
            || metadata.uid() != root_metadata.uid()
            || metadata.gid() != root_metadata.gid()
        {
            return Err(RuntimeControlFailure::CleanupUnsettled);
        }
        let bytes = read_bounded(&path, 1024 * 1024)
            .map_err(|_| RuntimeControlFailure::CleanupUnsettled)?;
        let journal: RuntimeJournal =
            serde_json::from_slice(&bytes).map_err(|_| RuntimeControlFailure::CleanupUnsettled)?;
        if serde_json::to_vec(&journal).map_err(|_| RuntimeControlFailure::CleanupUnsettled)?
            != bytes
        {
            return Err(RuntimeControlFailure::CleanupUnsettled);
        }
        if journal.schema_version != "workstream.trial_runtime_journal.v1"
            || runtime_journal_path(root, &journal.owner)? != path
        {
            return Err(RuntimeControlFailure::CleanupUnsettled);
        }
        validate_runtime_resources(&journal.owner, &journal.resources)
            .map_err(|_| RuntimeControlFailure::CleanupUnsettled)?;
        if loaded.insert(journal.owner, journal.resources).is_some() {
            return Err(RuntimeControlFailure::CleanupUnsettled);
        }
    }
    Ok(loaded)
}

fn persist_runtime_journal(
    root: &std::path::Path,
    owner: &RuntimeOwner,
    resources: &OwnedRuntimeResources,
) -> Result<(), RuntimeControlFailure> {
    validate_runtime_resources(owner, resources)?;
    let path = runtime_journal_path(root, owner)?;
    let nonce = RUNTIME_FILE_SEQUENCE.fetch_add(1, Ordering::Relaxed);
    let temporary = root.join(format!(".trial-owner-{nonce:016x}.tmp"));
    let bytes = serde_json::to_vec(&RuntimeJournal {
        schema_version: "workstream.trial_runtime_journal.v1".into(),
        owner: owner.clone(),
        resources: resources.clone(),
    })
    .map_err(|_| RuntimeControlFailure::CleanupUnsettled)?;
    let result = (|| {
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(&temporary)
            .map_err(|_| RuntimeControlFailure::CleanupUnsettled)?;
        std::io::Write::write_all(&mut file, &bytes)
            .map_err(|_| RuntimeControlFailure::CleanupUnsettled)?;
        file.sync_all()
            .map_err(|_| RuntimeControlFailure::CleanupUnsettled)?;
        fs::rename(&temporary, &path).map_err(|_| RuntimeControlFailure::CleanupUnsettled)?;
        File::open(root)
            .and_then(|directory| directory.sync_all())
            .map_err(|_| RuntimeControlFailure::CleanupUnsettled)
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temporary);
    }
    result
}

#[cfg(test)]
pub(crate) fn persist_runtime_journal_for_test(
    root: &std::path::Path,
    deployment_owner: &str,
) -> Result<PathBuf, RuntimeControlFailure> {
    let owner = RuntimeOwner {
        deployment_owner: deployment_owner.to_owned(),
        request_digest: format!("sha256:{}", "9".repeat(64)),
        attempt_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00001".into(),
        trial_owner_id: format!("trial_{}", "a".repeat(32)),
    };
    persist_runtime_journal(
        root,
        &owner,
        &OwnedRuntimeResources {
            containers: vec!["ws-trial-live-resource".into()],
            images: Vec::new(),
        },
    )?;
    runtime_journal_path(root, &owner)
}

fn remove_runtime_journal(
    root: &std::path::Path,
    owner: &RuntimeOwner,
) -> Result<(), RuntimeControlFailure> {
    let path = runtime_journal_path(root, owner)?;
    match fs::remove_file(path) {
        Ok(()) => File::open(root)
            .and_then(|directory| directory.sync_all())
            .map_err(|_| RuntimeControlFailure::CleanupUnsettled),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(_) => Err(RuntimeControlFailure::CleanupUnsettled),
    }
}

fn create_output(path: &std::path::Path) -> Result<File, RuntimeControlFailure> {
    OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(path)
        .map_err(|_| RuntimeControlFailure::LaunchUnavailable)
}

fn remove_outputs(stdout: &std::path::Path, stderr: &std::path::Path) {
    let _ = fs::remove_file(stdout);
    let _ = fs::remove_file(stderr);
}

fn output_size(
    stdout: &std::path::Path,
    stderr: &std::path::Path,
) -> Result<u64, RuntimeControlFailure> {
    let stdout = fs::metadata(stdout)
        .map_err(|_| RuntimeControlFailure::InvalidObservation)?
        .len();
    let stderr = fs::metadata(stderr)
        .map_err(|_| RuntimeControlFailure::InvalidObservation)?
        .len();
    stdout
        .checked_add(stderr)
        .ok_or(RuntimeControlFailure::CapacityExceeded)
}

fn read_bounded(path: &std::path::Path, maximum: usize) -> Result<Vec<u8>, RuntimeControlFailure> {
    let file = File::open(path).map_err(|_| RuntimeControlFailure::InvalidObservation)?;
    let mut bytes = Vec::new();
    file.take(maximum.saturating_add(1) as u64)
        .read_to_end(&mut bytes)
        .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
    if bytes.len() > maximum {
        return Err(RuntimeControlFailure::CapacityExceeded);
    }
    Ok(bytes)
}

fn read_prefix(path: &std::path::Path, maximum: usize) -> Result<Vec<u8>, RuntimeControlFailure> {
    let file = File::open(path).map_err(|_| RuntimeControlFailure::InvalidObservation)?;
    let mut bytes = Vec::new();
    file.take(maximum as u64)
        .read_to_end(&mut bytes)
        .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
    Ok(bytes)
}

fn canonical_directory(path: &std::path::Path) -> Result<PathBuf, RuntimeControlFailure> {
    let canonical =
        fs::canonicalize(path).map_err(|_| RuntimeControlFailure::InvalidConfiguration)?;
    let metadata = fs::symlink_metadata(&canonical)
        .map_err(|_| RuntimeControlFailure::InvalidConfiguration)?;
    if !metadata.file_type().is_dir() || metadata.file_type().is_symlink() {
        return Err(RuntimeControlFailure::InvalidConfiguration);
    }
    Ok(canonical)
}

fn validate_sha256_manifest(
    root: &std::path::Path,
    manifest: &[u8],
) -> Result<(), RuntimeControlFailure> {
    let text =
        std::str::from_utf8(manifest).map_err(|_| RuntimeControlFailure::CacheUnavailable)?;
    let mut expected = HashMap::new();
    for line in text.lines() {
        let (digest, relative) = line
            .split_once("  ")
            .ok_or(RuntimeControlFailure::CacheUnavailable)?;
        if digest.len() != 64
            || !digest
                .bytes()
                .all(|item| item.is_ascii_hexdigit() && !item.is_ascii_uppercase())
            || !relative.starts_with("./")
        {
            return Err(RuntimeControlFailure::CacheUnavailable);
        }
        let relative = std::path::Path::new(&relative[2..]);
        if relative.as_os_str().is_empty()
            || relative.is_absolute()
            || relative.components().any(|item| {
                !matches!(
                    item,
                    std::path::Component::Normal(_) | std::path::Component::CurDir
                )
            })
        {
            return Err(RuntimeControlFailure::CacheUnavailable);
        }
        if expected
            .insert(relative.to_owned(), digest.to_owned())
            .is_some()
        {
            return Err(RuntimeControlFailure::CacheUnavailable);
        }
    }
    if expected.is_empty() {
        return Err(RuntimeControlFailure::CacheUnavailable);
    }
    let mut actual = Vec::new();
    collect_regular_files(root, root, &mut actual, 100_000)?;
    if actual.len() != expected.len() {
        return Err(RuntimeControlFailure::CacheUnavailable);
    }
    for path in actual {
        let relative = path
            .strip_prefix(root)
            .map_err(|_| RuntimeControlFailure::CacheUnavailable)?;
        let expected_digest = expected
            .get(relative)
            .ok_or(RuntimeControlFailure::CacheUnavailable)?;
        if &hash_bounded_file(&path, u64::MAX)?[7..] != expected_digest {
            return Err(RuntimeControlFailure::CacheUnavailable);
        }
    }
    Ok(())
}

fn collect_regular_files(
    root: &std::path::Path,
    directory: &std::path::Path,
    files: &mut Vec<PathBuf>,
    maximum_entries: usize,
) -> Result<(), RuntimeControlFailure> {
    let mut entries = fs::read_dir(directory)
        .map_err(|_| RuntimeControlFailure::InvalidObservation)?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
    entries.sort_by_key(std::fs::DirEntry::file_name);
    for entry in entries {
        if files.len() >= maximum_entries {
            return Err(RuntimeControlFailure::CapacityExceeded);
        }
        let path = entry.path();
        if !path.starts_with(root) {
            return Err(RuntimeControlFailure::InvalidObservation);
        }
        let metadata =
            fs::symlink_metadata(&path).map_err(|_| RuntimeControlFailure::InvalidObservation)?;
        if metadata.file_type().is_symlink() {
            return Err(RuntimeControlFailure::InvalidObservation);
        }
        if metadata.file_type().is_dir() {
            collect_regular_files(root, &path, files, maximum_entries)?;
        } else if metadata.file_type().is_file() {
            files.push(path);
        } else {
            return Err(RuntimeControlFailure::InvalidObservation);
        }
    }
    Ok(())
}

fn require_available(
    deadline: Instant,
    invocation_cancelled: &AtomicBool,
    relay_cancelled: &AtomicBool,
) -> Result<(), RuntimeControlFailure> {
    if invocation_cancelled.load(Ordering::SeqCst) || relay_cancelled.load(Ordering::SeqCst) {
        return Err(RuntimeControlFailure::Cancelled);
    }
    if Instant::now() >= deadline {
        return Err(RuntimeControlFailure::DeadlineExceeded);
    }
    Ok(())
}

fn validate_owner(owner: &RuntimeOwner) -> Result<(), RuntimeControlFailure> {
    if !valid_label_value(&owner.deployment_owner, 128)
        || !valid_sha256(&owner.request_digest)
        || !valid_label_value(&owner.attempt_id, 128)
        || !owner.trial_owner_id.starts_with("trial_")
        || !valid_label_value(&owner.trial_owner_id, 64)
    {
        return Err(RuntimeControlFailure::InvalidConfiguration);
    }
    Ok(())
}

fn valid_label_value(value: &str, maximum: usize) -> bool {
    !value.is_empty()
        && value.len() <= maximum
        && value
            .bytes()
            .all(|item| item.is_ascii_alphanumeric() || matches!(item, b'_' | b'-' | b'.' | b':'))
}

fn owner_labels(owner: &RuntimeOwner) -> [(&'static str, &str); 5] {
    [
        ("workstream.trial", "true"),
        ("workstream.trial.deployment-owner", &owner.deployment_owner),
        ("workstream.trial.request-digest", &owner.request_digest),
        ("workstream.trial.attempt-id", &owner.attempt_id),
        ("workstream.trial.owner-id", &owner.trial_owner_id),
    ]
}

fn validate_container_name(value: &str) -> Result<(), RuntimeControlFailure> {
    if value.is_empty()
        || value.len() > 128
        || !value
            .bytes()
            .all(|item| item.is_ascii_alphanumeric() || matches!(item, b'_' | b'-' | b'.'))
    {
        return Err(RuntimeControlFailure::InvalidConfiguration);
    }
    Ok(())
}

fn validate_docker_arguments(arguments: &[String]) -> Result<(), RuntimeControlFailure> {
    if arguments.is_empty()
        || arguments.len() > 256
        || arguments.iter().any(|item| {
            item.is_empty()
                || item.len() > 4096
                || item
                    .bytes()
                    .any(|byte| byte == 0 || byte == b'\n' || byte == b'\r')
        })
    {
        return Err(RuntimeControlFailure::InvalidConfiguration);
    }
    Ok(())
}

fn validate_owned_mount(mount: &OwnedBindMount) -> Result<(), RuntimeControlFailure> {
    let canonical =
        fs::canonicalize(&mount.source).map_err(|_| RuntimeControlFailure::InvalidConfiguration)?;
    if canonical != mount.source
        || mount.source.to_str().is_none_or(|value| {
            !value.starts_with('/')
                || value.contains(',')
                || value.contains('\n')
                || value.contains('\r')
        })
        || mount.destination.contains(',')
        || mount.destination.contains('\n')
        || mount.destination.contains('\r')
    {
        return Err(RuntimeControlFailure::InvalidConfiguration);
    }
    let accepted = match mount.class {
        OwnedMountClass::TrustedLauncher => {
            mount.readonly && mount.destination == "/workstream-bootstrap/launcher"
        }
        OwnedMountClass::LauncherContext => {
            mount.readonly && mount.destination == "/workstream-bootstrap/input/context"
        }
        OwnedMountClass::LauncherCache => {
            mount.readonly && mount.destination == "/workstream-bootstrap/input/cache"
        }
        OwnedMountClass::LauncherExport => {
            !mount.readonly && mount.destination == "/workstream-bootstrap/export"
        }
        OwnedMountClass::LauncherWorkspace => {
            mount.readonly && mount.destination == "/workstream-bootstrap/input/workspace"
        }
        OwnedMountClass::LauncherRole => {
            mount.readonly
                && mount
                    .destination
                    .strip_prefix("/workstream-bootstrap/input/roles/")
                    .is_some_and(valid_container_relative_path)
        }
    };
    if !accepted {
        return Err(RuntimeControlFailure::InvalidConfiguration);
    }
    Ok(())
}

fn valid_container_relative_path(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 4096
        && !value.contains('\\')
        && value.split('/').all(|part| {
            !part.is_empty()
                && part != "."
                && part != ".."
                && !part.contains(':')
                && !part.bytes().any(|byte| byte.is_ascii_control())
        })
}

fn valid_relative_label(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 100
        && value
            .bytes()
            .all(|item| item.is_ascii_alphanumeric() || matches!(item, b'_' | b'-' | b'.'))
        && value != "."
        && value != ".."
}

fn valid_full_container_id(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|item| item.is_ascii_hexdigit() && !item.is_ascii_uppercase())
}

fn owned_container_matches(
    control: &DockerRuntimeControl,
    name: &str,
    owner: &RuntimeOwner,
    deadline: Instant,
) -> Result<bool, RuntimeControlFailure> {
    let output = control.command(
        &[
            "container".into(),
            "inspect".into(),
            "--format".into(),
            "{{json .}}".into(),
            name.into(),
        ],
        deadline,
        1024 * 1024,
    )?;
    if !output.success {
        return Ok(false);
    }
    let value: serde_json::Value = serde_json::from_slice(&output.stdout)
        .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
    if value.get("Name").and_then(serde_json::Value::as_str) != Some(&format!("/{name}")) {
        return Ok(false);
    }
    Ok(owner_labels(owner).iter().all(|(key, expected)| {
        value
            .pointer(&format!(
                "/Config/Labels/{}",
                key.replace('~', "~0").replace('/', "~1")
            ))
            .and_then(serde_json::Value::as_str)
            == Some(*expected)
    }))
}

fn container_exists(
    control: &DockerRuntimeControl,
    name: &str,
    deadline: Instant,
) -> Result<bool, RuntimeControlFailure> {
    let output = control.command(
        &["container".into(), "inspect".into(), name.into()],
        deadline,
        64 * 1024,
    )?;
    Ok(output.success)
}

fn image_exists(
    control: &DockerRuntimeControl,
    tag: &str,
    deadline: Instant,
) -> Result<bool, RuntimeControlFailure> {
    let output = control.command(
        &["image".into(), "inspect".into(), tag.into()],
        deadline,
        64 * 1024,
    )?;
    Ok(output.success)
}

fn stop_runtime_child(
    control: &DockerRuntimeControl,
    child: &mut Child,
    name: &str,
    deadline: Instant,
) {
    control.kill_container(name, deadline);
    let _ = child.kill();
    let _ = child.wait();
}

fn elapsed_ms(started: Instant) -> u64 {
    u64::try_from(started.elapsed().as_millis()).unwrap_or(u64::MAX)
}

fn sample_cgroup(pid: u32) -> Result<Measurements, RuntimeControlFailure> {
    let cgroup = fs::read_to_string(format!("/proc/{pid}/cgroup"))
        .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
    let relative = cgroup
        .lines()
        .find_map(|line| line.strip_prefix("0::"))
        .filter(|value| value.starts_with('/') && !value.contains(".."))
        .ok_or(RuntimeControlFailure::InvalidObservation)?;
    let root = std::path::Path::new("/sys/fs/cgroup").join(&relative[1..]);
    let cpu = fs::read_to_string(root.join("cpu.stat"))
        .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
    let usage_usec = cpu
        .lines()
        .find_map(|line| line.strip_prefix("usage_usec "))
        .and_then(|value| value.parse::<u64>().ok())
        .ok_or(RuntimeControlFailure::InvalidObservation)?;
    let memory_current = read_u64(root.join("memory.current"))?;
    let memory_peak = read_u64(root.join("memory.peak")).unwrap_or(memory_current);
    let pids = read_u64(root.join("pids.peak"))?;
    Ok(Measurements {
        cgroup_samples: 1,
        cpu_time_ms: usage_usec / 1000,
        peak_memory_bytes: memory_current.max(memory_peak),
        peak_pids: pids,
        ..Measurements::default()
    })
}

fn read_u64(path: PathBuf) -> Result<u64, RuntimeControlFailure> {
    fs::read_to_string(path)
        .map_err(|_| RuntimeControlFailure::InvalidObservation)?
        .trim()
        .parse()
        .map_err(|_| RuntimeControlFailure::InvalidObservation)
}

fn combined_tree_usage(roots: &[PathBuf]) -> Result<(u64, u64), RuntimeControlFailure> {
    let mut bytes = 0_u64;
    let mut entries = 0_u64;
    for root in roots {
        tree_usage(root, &mut bytes, &mut entries)?;
    }
    Ok((bytes, entries))
}

fn tree_usage(
    path: &std::path::Path,
    bytes: &mut u64,
    entries: &mut u64,
) -> Result<(), RuntimeControlFailure> {
    let metadata =
        fs::symlink_metadata(path).map_err(|_| RuntimeControlFailure::InvalidObservation)?;
    if metadata.file_type().is_symlink() {
        return Err(RuntimeControlFailure::InvalidObservation);
    }
    *entries = entries
        .checked_add(1)
        .ok_or(RuntimeControlFailure::CapacityExceeded)?;
    if metadata.file_type().is_file() {
        *bytes = bytes
            .checked_add(metadata.len())
            .ok_or(RuntimeControlFailure::CapacityExceeded)?;
    } else if metadata.file_type().is_dir() {
        let mut children = fs::read_dir(path)
            .map_err(|_| RuntimeControlFailure::InvalidObservation)?
            .collect::<Result<Vec<_>, _>>()
            .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
        children.sort_by_key(std::fs::DirEntry::file_name);
        for child in children {
            tree_usage(&child.path(), bytes, entries)?;
        }
    } else {
        return Err(RuntimeControlFailure::InvalidObservation);
    }
    Ok(())
}

fn combined_tree_digest(
    roots: &[PathBuf],
    limits: &ContainerExecutionLimits,
) -> Result<String, RuntimeControlFailure> {
    let mut digest = Sha256::new();
    let (bytes, entries) = combined_tree_usage(roots)?;
    if bytes > limits.disk_bytes.saturating_add(limits.disk_overrun_bytes)
        || entries > limits.entries.saturating_add(limits.entries_overrun)
    {
        return Err(RuntimeControlFailure::CapacityExceeded);
    }
    for root in roots {
        hash_tree(root, root, &mut digest)?;
    }
    Ok(format!("sha256:{:x}", digest.finalize()))
}

fn hash_tree(
    root: &std::path::Path,
    path: &std::path::Path,
    digest: &mut Sha256,
) -> Result<(), RuntimeControlFailure> {
    let metadata =
        fs::symlink_metadata(path).map_err(|_| RuntimeControlFailure::InvalidObservation)?;
    let relative = path
        .strip_prefix(root)
        .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
    let path_bytes = relative
        .to_str()
        .ok_or(RuntimeControlFailure::InvalidObservation)?
        .as_bytes();
    digest.update((path_bytes.len() as u64).to_be_bytes());
    digest.update(path_bytes);
    if metadata.file_type().is_dir() {
        digest.update(b"directory");
        let mut children = fs::read_dir(path)
            .map_err(|_| RuntimeControlFailure::InvalidObservation)?
            .collect::<Result<Vec<_>, _>>()
            .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
        children.sort_by_key(std::fs::DirEntry::file_name);
        for child in children {
            hash_tree(root, &child.path(), digest)?;
        }
    } else if metadata.file_type().is_file() {
        digest.update(b"file");
        digest.update(metadata.len().to_be_bytes());
        let mut file = File::open(path).map_err(|_| RuntimeControlFailure::InvalidObservation)?;
        std::io::copy(&mut file, digest).map_err(|_| RuntimeControlFailure::InvalidObservation)?;
    } else {
        return Err(RuntimeControlFailure::InvalidObservation);
    }
    Ok(())
}

fn validate_measurement_overruns(
    measurements: &Measurements,
    elapsed: u64,
    termination: RuntimeTermination,
    limits: &ContainerExecutionLimits,
) -> Result<(), RuntimeControlFailure> {
    let within =
        |observed: u64, bound: u64, overrun: u64| observed <= bound.saturating_add(overrun);
    if !within(
        elapsed,
        limits.operation_timeout_ms,
        limits.wall_time_overrun_ms,
    ) || !within(
        measurements.cpu_time_ms,
        limits.cpu_time_ms,
        limits.cpu_time_overrun_ms,
    ) || !within(
        measurements.peak_memory_bytes,
        limits.memory_bytes,
        limits.memory_overrun_bytes,
    ) || !within(measurements.peak_pids, limits.pids, limits.pids_overrun)
        || !within(
            measurements.written_bytes,
            limits.disk_bytes,
            limits.disk_overrun_bytes,
        )
        || !within(
            measurements.written_entries,
            limits.entries,
            limits.entries_overrun,
        )
    {
        return Err(RuntimeControlFailure::InvalidObservation);
    }
    let crossed = match termination {
        RuntimeTermination::DeadlineExceeded => elapsed >= limits.operation_timeout_ms,
        RuntimeTermination::CpuExceeded => measurements.cpu_time_ms >= limits.cpu_time_ms,
        RuntimeTermination::MemoryExceeded => measurements.peak_memory_bytes >= limits.memory_bytes,
        RuntimeTermination::PidExceeded => measurements.peak_pids >= limits.pids,
        RuntimeTermination::DiskExceeded => {
            measurements.written_bytes >= limits.disk_bytes
                || measurements.written_entries >= limits.entries
        }
        RuntimeTermination::OutputExceeded => true,
        RuntimeTermination::Exited | RuntimeTermination::Signalled => true,
    };
    if !crossed {
        return Err(RuntimeControlFailure::InvalidObservation);
    }
    Ok(())
}

fn validate_image_tag(value: &str) -> Result<(), RuntimeControlFailure> {
    let suffix = value
        .strip_prefix("workstream-trial:")
        .ok_or(RuntimeControlFailure::InvalidConfiguration)?;
    if !valid_relative_label(suffix) {
        return Err(RuntimeControlFailure::InvalidConfiguration);
    }
    Ok(())
}

fn validate_single_image_archive(
    archive: &std::path::Path,
    expected_tag: &str,
    maximum_bytes: u64,
    maximum_expanded_bytes: u64,
    maximum_expanded_entries: u64,
    deadline: Instant,
) -> Result<image_archive::ExpandedImage, RuntimeControlFailure> {
    let mut file = File::open(archive).map_err(|_| RuntimeControlFailure::InvalidObservation)?;
    let length = file
        .metadata()
        .map_err(|_| RuntimeControlFailure::InvalidObservation)?
        .len();
    if length == 0 || length > maximum_bytes {
        return Err(RuntimeControlFailure::InvalidObservation);
    }
    if length % 512 != 0 {
        return Err(RuntimeControlFailure::InvalidObservation);
    }
    let mut offset = 0_u64;
    let mut manifest = None;
    let mut entries = HashMap::new();
    while offset.saturating_add(512) <= length {
        file.seek(SeekFrom::Start(offset))
            .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
        let mut header = [0_u8; 512];
        file.read_exact(&mut header)
            .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
        if header.iter().all(|byte| *byte == 0) {
            if length.saturating_sub(offset) < 1024 {
                return Err(RuntimeControlFailure::InvalidObservation);
            }
            file.seek(SeekFrom::Start(offset))
                .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
            let mut trailing = vec![0_u8; (length - offset) as usize];
            file.read_exact(&mut trailing)
                .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
            if trailing.iter().any(|byte| *byte != 0) {
                return Err(RuntimeControlFailure::InvalidObservation);
            }
            offset = length;
            break;
        }
        validate_tar_checksum(&header)?;
        if !matches!(header[156], 0 | b'0') || header[157..257].iter().any(|byte| *byte != 0) {
            return Err(RuntimeControlFailure::InvalidObservation);
        }
        let name = tar_text(&header[0..100])?;
        let prefix = tar_text(&header[345..500])?;
        let path = if prefix.is_empty() {
            name
        } else {
            format!("{prefix}/{name}")
        };
        if !valid_archive_path(&path) {
            return Err(RuntimeControlFailure::InvalidObservation);
        }
        if entries.len() >= 4096 || entries.contains_key(&path) || path == "repositories" {
            return Err(RuntimeControlFailure::InvalidObservation);
        }
        let size = tar_octal(&header[124..136])?;
        let data = offset
            .checked_add(512)
            .ok_or(RuntimeControlFailure::InvalidObservation)?;
        let padded = size
            .checked_add(511)
            .map(|value| value / 512 * 512)
            .ok_or(RuntimeControlFailure::InvalidObservation)?;
        offset = data
            .checked_add(padded)
            .filter(|value| *value <= length)
            .ok_or(RuntimeControlFailure::InvalidObservation)?;
        entries.insert(path.clone(), (data, size));
        if path == "manifest.json" {
            if manifest.is_some() || size > 1024 * 1024 {
                return Err(RuntimeControlFailure::InvalidObservation);
            }
            file.seek(SeekFrom::Start(data))
                .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
            let mut bytes = vec![0_u8; size as usize];
            file.read_exact(&mut bytes)
                .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
            manifest = Some(bytes);
        }
    }
    if offset != length {
        return Err(RuntimeControlFailure::InvalidObservation);
    }
    let manifest = manifest.ok_or(RuntimeControlFailure::InvalidObservation)?;
    let manifests: Vec<ImageArchiveManifest> =
        serde_json::from_slice(&manifest).map_err(|_| RuntimeControlFailure::InvalidObservation)?;
    if manifests.len() != 1 {
        return Err(RuntimeControlFailure::InvalidObservation);
    }
    let manifest = manifests.first().unwrap();
    let config_digest = if valid_sha256(&manifest.config) {
        &manifest.config[7..]
    } else if manifest.config.len() == 69
        && manifest.config.ends_with(".json")
        && manifest.config[..64]
            .bytes()
            .all(|item| item.is_ascii_hexdigit() && !item.is_ascii_uppercase())
    {
        &manifest.config[..64]
    } else {
        return Err(RuntimeControlFailure::InvalidObservation);
    };
    if manifest.repo_tags.as_slice() != [expected_tag] || manifest.layers.is_empty() {
        return Err(RuntimeControlFailure::InvalidObservation);
    }
    let Some((config_offset, config_size)) = entries.get(&manifest.config).copied() else {
        return Err(RuntimeControlFailure::InvalidObservation);
    };
    if config_size == 0 || config_size > 16 * 1024 * 1024 {
        return Err(RuntimeControlFailure::InvalidObservation);
    }
    file.seek(SeekFrom::Start(config_offset))
        .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
    let mut config_bytes = vec![0_u8; config_size as usize];
    file.read_exact(&mut config_bytes)
        .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
    if format!("{:x}", Sha256::digest(&config_bytes)) != config_digest {
        return Err(RuntimeControlFailure::InvalidObservation);
    }
    let mut referenced = HashSet::from(["manifest.json".to_owned(), manifest.config.clone()]);
    for layer in &manifest.layers {
        if !valid_archive_path(layer)
            || layer == "manifest.json"
            || layer == &manifest.config
            || !entries.contains_key(layer)
        {
            return Err(RuntimeControlFailure::InvalidObservation);
        }
        // OCI/Docker layer sequences may legitimately reuse the same content
        // digest (for example, repeated empty metadata layers). The archive
        // still contains one canonical regular entry for that digest.
        referenced.insert(layer.clone());
    }
    if referenced.len() != entries.len() {
        return Err(RuntimeControlFailure::InvalidObservation);
    }
    image_archive::validate_layers(
        &mut file,
        &entries,
        &manifest.layers,
        &config_bytes,
        maximum_expanded_bytes,
        maximum_expanded_entries,
        deadline,
    )
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ImageArchiveManifest {
    #[serde(rename = "Config")]
    config: String,
    #[serde(rename = "RepoTags")]
    repo_tags: Vec<String>,
    #[serde(rename = "Layers")]
    layers: Vec<String>,
}

fn valid_archive_path(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 4096
        && !value.starts_with('/')
        && !value.ends_with('/')
        && !value.contains('\\')
        && value.bytes().all(|byte| {
            byte.is_ascii_alphanumeric() || matches!(byte, b'/' | b'.' | b'_' | b'-' | b':')
        })
        && value
            .split('/')
            .all(|part| !part.is_empty() && part != "." && part != "..")
}

fn validate_tar_checksum(header: &[u8; 512]) -> Result<(), RuntimeControlFailure> {
    let expected = tar_octal(&header[148..156])?;
    let actual: u64 = header
        .iter()
        .enumerate()
        .map(|(index, byte)| {
            if (148..156).contains(&index) {
                u64::from(b' ')
            } else {
                u64::from(*byte)
            }
        })
        .sum();
    if actual != expected {
        return Err(RuntimeControlFailure::InvalidObservation);
    }
    Ok(())
}

fn tar_text(bytes: &[u8]) -> Result<String, RuntimeControlFailure> {
    let end = bytes
        .iter()
        .position(|byte| *byte == 0)
        .unwrap_or(bytes.len());
    let value = std::str::from_utf8(&bytes[..end])
        .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
    Ok(value.to_owned())
}

fn tar_octal(bytes: &[u8]) -> Result<u64, RuntimeControlFailure> {
    let text = std::str::from_utf8(bytes)
        .map_err(|_| RuntimeControlFailure::InvalidObservation)?
        .trim_matches(|character| character == '\0' || character == ' ');
    u64::from_str_radix(text, 8).map_err(|_| RuntimeControlFailure::InvalidObservation)
}

fn hash_bounded_file(
    path: &std::path::Path,
    maximum_bytes: u64,
) -> Result<String, RuntimeControlFailure> {
    let mut file = File::open(path).map_err(|_| RuntimeControlFailure::InvalidObservation)?;
    let metadata = file
        .metadata()
        .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
    if metadata.len() > maximum_bytes {
        return Err(RuntimeControlFailure::CapacityExceeded);
    }
    let mut digest = Sha256::new();
    std::io::copy(&mut file, &mut digest).map_err(|_| RuntimeControlFailure::InvalidObservation)?;
    Ok(format!("sha256:{:x}", digest.finalize()))
}

fn sha256_bytes(value: &[u8]) -> String {
    format!("sha256:{:x}", Sha256::digest(value))
}

#[derive(Clone, Debug)]
pub(crate) struct DockerTrialConfiguration {
    pub(crate) identity: SandboxBackendIdentity,
    pub(crate) deployment_owner: String,
    pub(crate) request_digest: String,
    pub(crate) attempt_id: String,
    pub(crate) runtime_key: String,
    pub(crate) builder_image_id: String,
    pub(crate) trusted_launcher_path: PathBuf,
    pub(crate) trusted_launcher_digest: String,
    pub(crate) offline_cache_root: PathBuf,
    pub(crate) maximum_candidate_archive_bytes: u64,
    pub(crate) candidate_uid: u32,
    pub(crate) candidate_gid: u32,
    pub(crate) export_uid: u32,
    pub(crate) export_gid: u32,
}

pub(crate) struct DockerTrialBackend<C: RuntimeControl> {
    config: DockerTrialConfiguration,
    pub(crate) control: C,
}

impl<C: RuntimeControl> DockerTrialBackend<C> {
    pub(crate) fn new(
        config: DockerTrialConfiguration,
        control: C,
    ) -> Result<Self, SandboxFailure> {
        let trusted_launcher_path = fs::canonicalize(&config.trusted_launcher_path)
            .map_err(|_| infrastructure(TrialRelayFailure::InvalidRequest))?;
        let launcher_metadata = fs::symlink_metadata(&trusted_launcher_path)
            .map_err(|_| infrastructure(TrialRelayFailure::InvalidRequest))?;
        if config.identity.child_runtime != "runsc"
            || config.identity.child_host_uds != "none"
            || config.runtime_key.is_empty()
            || config.runtime_key.len() > 100
            || !config
                .runtime_key
                .bytes()
                .all(|item| item.is_ascii_alphanumeric() || matches!(item, b'_' | b'-' | b'.'))
            || !valid_sha256(&config.builder_image_id)
            || config.builder_image_id != config.identity.builder_image_digest
            || config.trusted_launcher_digest != config.identity.trusted_launcher_digest
            || !valid_sha256(&config.trusted_launcher_digest)
            || trusted_launcher_path != config.trusted_launcher_path
            || !launcher_metadata.file_type().is_file()
            || launcher_metadata.file_type().is_symlink()
            || launcher_metadata.permissions().mode() & 0o111 == 0
            || launcher_metadata.permissions().mode() & 0o022 != 0
            || hash_bounded_file(&trusted_launcher_path, 8 * 1024 * 1024)
                .ok()
                .as_deref()
                != Some(config.trusted_launcher_digest.as_str())
            || !config.offline_cache_root.is_absolute()
            || config.maximum_candidate_archive_bytes == 0
            || config.candidate_uid == 0
            || config.candidate_gid == 0
            || config.export_uid == 0
            || config.export_gid == 0
            || config.candidate_uid != config.export_uid
            || config.candidate_gid != config.export_gid
        {
            return Err(infrastructure(TrialRelayFailure::InvalidRequest));
        }
        Ok(Self { config, control })
    }

    fn owner(&self, trial_owner_id: &str) -> RuntimeOwner {
        RuntimeOwner {
            deployment_owner: self.config.deployment_owner.clone(),
            request_digest: self.config.request_digest.clone(),
            attempt_id: self.config.attempt_id.clone(),
            trial_owner_id: trial_owner_id.to_owned(),
        }
    }

    fn require_trusted_launcher(&self) -> Result<(), SandboxFailure> {
        let canonical = fs::canonicalize(&self.config.trusted_launcher_path)
            .map_err(|_| infrastructure(TrialRelayFailure::ImplementationUnavailable))?;
        let metadata = fs::symlink_metadata(&canonical)
            .map_err(|_| infrastructure(TrialRelayFailure::ImplementationUnavailable))?;
        if canonical != self.config.trusted_launcher_path
            || !metadata.file_type().is_file()
            || metadata.file_type().is_symlink()
            || metadata.permissions().mode() & 0o111 == 0
            || metadata.permissions().mode() & 0o022 != 0
            || hash_bounded_file(&canonical, 8 * 1024 * 1024)
                .ok()
                .as_deref()
                != Some(self.config.trusted_launcher_digest.as_str())
        {
            return Err(infrastructure(TrialRelayFailure::ImplementationUnavailable));
        }
        Ok(())
    }

    fn limits(
        &self,
        resources: &crate::trial_relay::TrialResources,
        cpu_time_ms: u64,
        disk_bytes: u64,
        entries: u64,
        timeout_ms: u64,
        output_bytes: usize,
        overruns: &SandboxEnforcementOverruns,
        deadline: Instant,
    ) -> ContainerExecutionLimits {
        ContainerExecutionLimits {
            deadline,
            operation_timeout_ms: timeout_ms,
            cpu_time_ms,
            wall_time_overrun_ms: overruns.wall_time_ms,
            cpu_time_overrun_ms: overruns.cpu_time_ms,
            memory_bytes: resources.memory_bytes,
            memory_overrun_bytes: overruns.memory_bytes,
            pids: resources.pids,
            pids_overrun: overruns.pids,
            disk_bytes,
            disk_overrun_bytes: overruns.disk_bytes,
            entries,
            entries_overrun: overruns.entries,
            output_bytes,
        }
    }

    fn common_create_arguments(
        &self,
        resources: &crate::trial_relay::TrialResources,
    ) -> Vec<String> {
        vec![
            "--runtime".into(),
            self.config.runtime_key.clone(),
            "--network".into(),
            "none".into(),
            "--no-healthcheck".into(),
            "--read-only".into(),
            "--cap-drop".into(),
            "ALL".into(),
            "--cap-add".into(),
            "CHOWN".into(),
            "--cap-add".into(),
            "DAC_OVERRIDE".into(),
            "--cap-add".into(),
            "FOWNER".into(),
            "--cap-add".into(),
            "KILL".into(),
            "--cap-add".into(),
            "SETGID".into(),
            "--cap-add".into(),
            "SETPCAP".into(),
            "--cap-add".into(),
            "SETUID".into(),
            "--cap-add".into(),
            "SYS_ADMIN".into(),
            "--cap-add".into(),
            "SYS_CHROOT".into(),
            "--security-opt".into(),
            "no-new-privileges".into(),
            "--user".into(),
            "0:0".into(),
            "--tmpfs".into(),
            "/workstream-bootstrap:rw,nosuid,nodev,size=65536".into(),
            "--entrypoint".into(),
            "/workstream-bootstrap/launcher".into(),
            "--pids-limit".into(),
            resources.pids.to_string(),
            "--memory".into(),
            resources.memory_bytes.to_string(),
            "--memory-swap".into(),
            resources.memory_bytes.to_string(),
            "--cpus".into(),
            format!("{:.3}", resources.cpu_quota_millis as f64 / 1000.0),
        ]
    }
}

impl<C: RuntimeControl> TrialSandboxBackend for DockerTrialBackend<C> {
    fn identity(&self) -> SandboxBackendIdentity {
        self.config.identity.clone()
    }

    fn build(
        &self,
        request: &SandboxBuildRequest,
        deadline: Instant,
        invocation_cancelled: &AtomicBool,
        relay_cancelled: &AtomicBool,
    ) -> Result<SandboxBuildResult, SandboxFailure> {
        self.control
            .require_image(
                &self.config.builder_image_id,
                &self.config.identity,
                &self.config.runtime_key,
                deadline,
            )
            .map_err(runtime_failure)?;
        self.control
            .require_offline_cache(
                &self.config.offline_cache_root,
                &self.config.identity.offline_cache_digest,
            )
            .map_err(runtime_failure)?;
        self.require_trusted_launcher()?;
        let owner = self.owner(&request.owner_id);
        let name = format!("ws-trial-{}-build", request.owner_id);
        let mut arguments = self.common_create_arguments(&request.resources);
        arguments.extend([
            self.config.builder_image_id.clone(),
            "builder".into(),
            "--root-bytes".into(),
            request.launcher_root_bytes.to_string(),
            "--root-inodes".into(),
            request.launcher_root_entries.to_string(),
            "--candidate-bytes".into(),
            request
                .launcher_candidate_bytes
                .min(self.config.maximum_candidate_archive_bytes)
                .to_string(),
            "--tmp-bytes".into(),
            request.launcher_temporary_bytes.to_string(),
            "--tmp-inodes".into(),
            request.launcher_temporary_entries.to_string(),
            "--shm-bytes".into(),
            request.launcher_shared_memory_bytes.to_string(),
            "--shm-inodes".into(),
            request.launcher_shared_memory_entries.to_string(),
            "--export-uid".into(),
            self.config.export_uid.to_string(),
            "--export-gid".into(),
            self.config.export_gid.to_string(),
            "--".into(),
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
        ]);
        self.control
            .create_owned_container(
                OwnedContainerCreate {
                    owner: owner.clone(),
                    name: name.clone(),
                    arguments,
                    mounts: vec![
                        owned_mount(
                            &self.config.trusted_launcher_path,
                            "/workstream-bootstrap/launcher",
                            true,
                            OwnedMountClass::TrustedLauncher,
                        )?,
                        owned_mount(
                            &request.context_root,
                            "/workstream-bootstrap/input/context",
                            true,
                            OwnedMountClass::LauncherContext,
                        )?,
                        owned_mount(
                            &self.config.offline_cache_root,
                            "/workstream-bootstrap/input/cache",
                            true,
                            OwnedMountClass::LauncherCache,
                        )?,
                        owned_mount(
                            request
                                .output_archive
                                .parent()
                                .ok_or_else(|| infrastructure(TrialRelayFailure::InvalidRequest))?,
                            "/workstream-bootstrap/export",
                            false,
                            OwnedMountClass::LauncherExport,
                        )?,
                    ],
                },
                deadline,
                invocation_cancelled,
                relay_cancelled,
            )
            .map_err(runtime_failure)?;
        let observed = self
            .control
            .run_owned_container(
                &owner,
                &name,
                &[request.output_archive.parent().unwrap().to_owned()],
                &self.limits(
                    &request.resources,
                    request.remaining_cpu_time_ms,
                    request.mutable_disk_bytes,
                    request.mutable_entries,
                    request.timeout_ms,
                    request.maximum_output_bytes,
                    &request.enforcement_overruns,
                    deadline,
                ),
                invocation_cancelled,
                relay_cancelled,
            )
            .map_err(runtime_failure)?;
        let mut observed = observed;
        let (export_outcome, outcome_override) = match observed.termination {
            RuntimeTermination::Exited if observed.exit_code == Some(0) => {
                let admitted = admit_builder_export(request)?;
                observed.termination = if admitted.child.exit_code.is_some() {
                    RuntimeTermination::Exited
                } else {
                    RuntimeTermination::Signalled
                };
                observed.exit_code = admitted.child.exit_code;
                observed.signal = admitted.child.signal;
                let outcome_override = match admitted.export_outcome {
                    TrialExportOutcome::CapacityExceeded => {
                        Some(TrialOperationOutcome::DiskExceeded)
                    }
                    TrialExportOutcome::Invalid => Some(TrialOperationOutcome::ExportInvalid),
                    _ => None,
                };
                (admitted.export_outcome, outcome_override)
            }
            RuntimeTermination::Exited | RuntimeTermination::Signalled => {
                return Err(runtime_failure(RuntimeControlFailure::InvalidObservation));
            }
            RuntimeTermination::DeadlineExceeded
            | RuntimeTermination::CpuExceeded
            | RuntimeTermination::MemoryExceeded
            | RuntimeTermination::PidExceeded
            | RuntimeTermination::DiskExceeded
            | RuntimeTermination::OutputExceeded => (TrialExportOutcome::Unavailable, None),
        };
        let mut observation = build_observation(observed, export_outcome, outcome_override)?;
        let mut retained_image_bytes = 0;
        let mut retained_image_entries = 0;
        if observation.outcome == TrialOperationOutcome::Succeeded {
            let archive_bytes = fs::metadata(&request.output_archive)
                .map_err(|_| runtime_failure(RuntimeControlFailure::InvalidObservation))?
                .len();
            if observation.written_bytes < archive_bytes || observation.written_entries == 0 {
                return Err(runtime_failure(RuntimeControlFailure::InvalidObservation));
            }
            let expanded_bytes = request
                .mutable_disk_bytes
                .checked_sub(observation.written_bytes)
                .ok_or_else(|| runtime_failure(RuntimeControlFailure::CapacityExceeded))?;
            let expanded_entries = request
                .mutable_entries
                .checked_sub(observation.written_entries)
                .ok_or_else(|| runtime_failure(RuntimeControlFailure::CapacityExceeded))?;
            let loaded = self
                .control
                .load_single_owned_image(
                    &owner,
                    &request.output_archive,
                    &request.destination,
                    self.config.maximum_candidate_archive_bytes,
                    expanded_bytes,
                    expanded_entries,
                    deadline,
                )
                .map_err(runtime_failure)?;
            observation.candidate_image_digest = Some(loaded.config_image_id);
            observation.candidate_archive_digest = Some(loaded.archive_sha256);
            observation.written_bytes = observation.written_bytes.max(loaded.archive_byte_count);
            retained_image_bytes = loaded.expanded_byte_count;
            retained_image_entries = loaded.expanded_entry_count;
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
        self.require_trusted_launcher()?;
        let owner = self.owner(&request.owner_id);
        let slot_digest = Sha256::digest(request.slot_id.as_bytes());
        let slot_digest = format!("{slot_digest:x}");
        let name = format!("ws-trial-{}-{}", request.owner_id, &slot_digest[..16]);
        let mut arguments = self.common_create_arguments(&request.resources);
        arguments.extend([
            request.candidate_image_digest.clone(),
            "step".into(),
            "--root-bytes".into(),
            request.launcher_root_bytes.to_string(),
            "--root-inodes".into(),
            request.launcher_root_entries.to_string(),
            "--workspace-bytes".into(),
            request.launcher_workspace_bytes.to_string(),
            "--workspace-inodes".into(),
            request.launcher_workspace_entries.to_string(),
            "--tmp-bytes".into(),
            request.launcher_temporary_bytes.to_string(),
            "--tmp-inodes".into(),
            request.launcher_temporary_entries.to_string(),
            "--shm-bytes".into(),
            request.launcher_shared_memory_bytes.to_string(),
            "--shm-inodes".into(),
            request.launcher_shared_memory_entries.to_string(),
            "--working-directory".into(),
            request.working_directory.clone(),
            "--uid".into(),
            self.config.candidate_uid.to_string(),
            "--gid".into(),
            self.config.candidate_gid.to_string(),
            "--export-uid".into(),
            self.config.export_uid.to_string(),
            "--export-gid".into(),
            self.config.export_gid.to_string(),
        ]);
        let mut mounts = vec![
            owned_mount(
                &self.config.trusted_launcher_path,
                "/workstream-bootstrap/launcher",
                true,
                OwnedMountClass::TrustedLauncher,
            )?,
            owned_mount(
                &request.workspace_root,
                "/workstream-bootstrap/input/workspace",
                true,
                OwnedMountClass::LauncherWorkspace,
            )?,
            owned_mount(
                &request.export_root,
                "/workstream-bootstrap/export",
                false,
                OwnedMountClass::LauncherExport,
            )?,
        ];
        for role in &request.visible_roles {
            arguments.extend([
                "--visible".into(),
                format!("{}={}", role.role, role.destination_relative),
            ]);
            mounts.push(owned_mount(
                &role.path,
                &format!("/workstream-bootstrap/input/roles/{}", role.role),
                true,
                OwnedMountClass::LauncherRole,
            )?);
        }
        arguments.push("--".into());
        arguments.extend(request.command.iter().cloned());
        let limits = self.limits(
            &request.resources,
            request.remaining_cpu_time_ms,
            request.mutable_disk_bytes,
            request.mutable_entries,
            request.timeout_ms,
            request.maximum_output_bytes,
            &request.enforcement_overruns,
            deadline,
        );
        let workspace_before_sha256 =
            combined_tree_digest(std::slice::from_ref(&request.workspace_root), &limits)
                .map_err(runtime_failure)?;
        self.control
            .create_owned_container(
                OwnedContainerCreate {
                    owner: owner.clone(),
                    name: name.clone(),
                    arguments,
                    mounts,
                },
                deadline,
                invocation_cancelled,
                relay_cancelled,
            )
            .map_err(runtime_failure)?;
        let observed = self
            .control
            .run_owned_container(
                &owner,
                &name,
                std::slice::from_ref(&request.export_root),
                &limits,
                invocation_cancelled,
                relay_cancelled,
            )
            .map_err(runtime_failure)?;
        let mut observed = observed;
        let (export_outcome, outcome_override) = match observed.termination {
            RuntimeTermination::Exited if observed.exit_code == Some(0) => {
                let admitted = admit_launcher_export(request)?;
                observed.termination = if admitted.child.exit_code.is_some() {
                    RuntimeTermination::Exited
                } else {
                    RuntimeTermination::Signalled
                };
                observed.exit_code = admitted.child.exit_code;
                observed.signal = admitted.child.signal;
                let outcome_override = match admitted.export_outcome {
                    TrialExportOutcome::CapacityExceeded => {
                        Some(TrialOperationOutcome::DiskExceeded)
                    }
                    TrialExportOutcome::Invalid => Some(TrialOperationOutcome::ExportInvalid),
                    _ => None,
                };
                (admitted.export_outcome, outcome_override)
            }
            RuntimeTermination::Exited | RuntimeTermination::Signalled => {
                return Err(runtime_failure(RuntimeControlFailure::InvalidObservation));
            }
            RuntimeTermination::DeadlineExceeded
            | RuntimeTermination::CpuExceeded
            | RuntimeTermination::MemoryExceeded
            | RuntimeTermination::PidExceeded
            | RuntimeTermination::DiskExceeded
            | RuntimeTermination::OutputExceeded => {
                remove_launcher_export(&request.export_root)?;
                (TrialExportOutcome::Unavailable, None)
            }
        };
        observed.workspace_before_sha256 = Some(workspace_before_sha256);
        observed.workspace_after_sha256 = Some(
            combined_tree_digest(std::slice::from_ref(&request.workspace_root), &limits)
                .map_err(runtime_failure)?,
        );
        Ok(SandboxStepResult {
            observation: step_observation(
                request,
                operation_order,
                observed,
                export_outcome,
                outcome_override,
            )?,
        })
    }

    fn cleanup(&self, owner_id: &str, deadline: Instant) -> Result<(), SandboxFailure> {
        self.control
            .cleanup_owner(&self.owner(owner_id), deadline)
            .map_err(runtime_failure)
    }
}

fn build_observation(
    value: ObservedContainerExit,
    export_outcome: TrialExportOutcome,
    outcome_override: Option<TrialOperationOutcome>,
) -> Result<TrialBuildObservation, SandboxFailure> {
    let outcome = outcome_override.unwrap_or(operation_outcome(&value)?);
    Ok(TrialBuildObservation {
        outcome,
        exit_code: value.exit_code,
        signal: value.signal,
        stdout_sha256: sha256_text(&value.stdout),
        stderr_sha256: sha256_text(&value.stderr),
        stdout: value.stdout,
        stderr: value.stderr,
        candidate_image_digest: None,
        candidate_archive_digest: None,
        export_outcome,
        elapsed_ms: value.elapsed_ms,
        cpu_time_ms: value.cpu_time_ms,
        peak_memory_bytes: value.peak_memory_bytes,
        peak_pids: value.peak_pids,
        written_bytes: value.written_bytes,
        written_entries: value.written_entries,
        measurement_method: value.measurement_method,
    })
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct LauncherStatus {
    schema: String,
    child: LauncherChildStatus,
    candidate_exported: bool,
    workspace_exported: bool,
    export_failure: Option<LauncherExportFailure>,
}

#[derive(Clone, Copy, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
enum LauncherExportFailure {
    CapacityExceeded,
    Invalid,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct LauncherChildStatus {
    exit_code: Option<i32>,
    signal: Option<i32>,
}

struct AdmittedLauncherExport {
    child: LauncherChildStatus,
    export_outcome: TrialExportOutcome,
}

fn read_launcher_status(root: &std::path::Path) -> Result<LauncherStatus, SandboxFailure> {
    let status_path = root.join("status.json");
    let status_metadata = fs::symlink_metadata(&status_path)
        .map_err(|_| runtime_failure(RuntimeControlFailure::InvalidObservation))?;
    if !status_metadata.file_type().is_file()
        || status_metadata.file_type().is_symlink()
        || status_metadata.len() > 4096
    {
        return Err(runtime_failure(RuntimeControlFailure::InvalidObservation));
    }
    let status: LauncherStatus =
        serde_json::from_slice(&read_bounded(&status_path, 4096).map_err(runtime_failure)?)
            .map_err(|_| runtime_failure(RuntimeControlFailure::InvalidObservation))?;
    let exact_outcome = match (status.child.exit_code, status.child.signal) {
        (Some(code), None) => (0..=255).contains(&code),
        (None, Some(signal)) => (1..=64).contains(&signal),
        _ => false,
    };
    if status.schema != "workstream.trial_launcher_status.v1" || !exact_outcome {
        return Err(runtime_failure(RuntimeControlFailure::InvalidObservation));
    }
    Ok(status)
}

fn admit_builder_export(
    request: &SandboxBuildRequest,
) -> Result<AdmittedLauncherExport, SandboxFailure> {
    let root = request
        .output_archive
        .parent()
        .ok_or_else(|| runtime_failure(RuntimeControlFailure::InvalidConfiguration))?;
    let status = read_launcher_status(root)?;
    let succeeded = status.child.exit_code == Some(0);
    let export_outcome = match status.export_failure {
        None if succeeded && status.candidate_exported => TrialExportOutcome::Exported,
        None if !succeeded && !status.candidate_exported => TrialExportOutcome::NotStarted,
        Some(LauncherExportFailure::CapacityExceeded)
            if succeeded && !status.candidate_exported =>
        {
            TrialExportOutcome::CapacityExceeded
        }
        Some(LauncherExportFailure::Invalid) if succeeded && !status.candidate_exported => {
            TrialExportOutcome::Invalid
        }
        _ => return Err(runtime_failure(RuntimeControlFailure::InvalidObservation)),
    };
    if status.workspace_exported {
        return Err(runtime_failure(RuntimeControlFailure::InvalidObservation));
    }
    let mut names = fs::read_dir(root)
        .map_err(|_| runtime_failure(RuntimeControlFailure::InvalidObservation))?
        .map(|entry| entry.map(|value| value.file_name()))
        .collect::<Result<Vec<_>, _>>()
        .map_err(|_| runtime_failure(RuntimeControlFailure::InvalidObservation))?;
    names.sort();
    let expected = if status.candidate_exported {
        vec![
            std::ffi::OsString::from("candidate.tar"),
            std::ffi::OsString::from("status.json"),
        ]
    } else {
        vec![std::ffi::OsString::from("status.json")]
    };
    if names != expected {
        return Err(runtime_failure(RuntimeControlFailure::InvalidObservation));
    }
    fs::remove_file(root.join("status.json"))
        .map_err(|_| runtime_failure(RuntimeControlFailure::CleanupUnsettled))?;
    Ok(AdmittedLauncherExport {
        child: status.child,
        export_outcome,
    })
}

fn admit_launcher_export(
    request: &SandboxStepRequest,
) -> Result<AdmittedLauncherExport, SandboxFailure> {
    let mut names = fs::read_dir(&request.export_root)
        .map_err(|_| runtime_failure(RuntimeControlFailure::InvalidObservation))?
        .map(|entry| entry.map(|value| value.file_name()))
        .collect::<Result<Vec<_>, _>>()
        .map_err(|_| runtime_failure(RuntimeControlFailure::InvalidObservation))?;
    names.sort();
    let status = read_launcher_status(&request.export_root)?;
    let export_outcome = match status.export_failure {
        None if status.workspace_exported => TrialExportOutcome::Exported,
        Some(LauncherExportFailure::CapacityExceeded) if !status.workspace_exported => {
            TrialExportOutcome::CapacityExceeded
        }
        Some(LauncherExportFailure::Invalid) if !status.workspace_exported => {
            TrialExportOutcome::Invalid
        }
        _ => return Err(runtime_failure(RuntimeControlFailure::InvalidObservation)),
    };
    let expected = if status.workspace_exported {
        vec![
            std::ffi::OsString::from("status.json"),
            std::ffi::OsString::from("workspace.next"),
        ]
    } else {
        vec![std::ffi::OsString::from("status.json")]
    };
    if names != expected || status.candidate_exported {
        return Err(runtime_failure(RuntimeControlFailure::InvalidObservation));
    }
    if export_outcome != TrialExportOutcome::Exported {
        fs::remove_file(request.export_root.join("status.json"))
            .map_err(|_| runtime_failure(RuntimeControlFailure::CleanupUnsettled))?;
        fs::remove_dir(&request.export_root)
            .map_err(|_| runtime_failure(RuntimeControlFailure::CleanupUnsettled))?;
        return Ok(AdmittedLauncherExport {
            child: status.child,
            export_outcome,
        });
    }
    let next = request.export_root.join("workspace.next");
    let (bytes, entries) =
        combined_tree_usage(std::slice::from_ref(&next)).map_err(runtime_failure)?;
    if bytes > request.launcher_workspace_bytes || entries > request.launcher_workspace_entries {
        return Err(runtime_failure(RuntimeControlFailure::CapacityExceeded));
    }
    let parent = request
        .workspace_root
        .parent()
        .ok_or_else(|| runtime_failure(RuntimeControlFailure::InvalidConfiguration))?;
    let backup = parent.join(format!(".{}.previous", request.slot_id));
    if backup.exists() {
        return Err(runtime_failure(RuntimeControlFailure::CleanupUnsettled));
    }
    fs::rename(&request.workspace_root, &backup)
        .map_err(|_| runtime_failure(RuntimeControlFailure::CleanupUnsettled))?;
    if fs::rename(&next, &request.workspace_root).is_err() {
        let _ = fs::rename(&backup, &request.workspace_root);
        return Err(runtime_failure(RuntimeControlFailure::CleanupUnsettled));
    }
    fs::remove_dir_all(&backup)
        .map_err(|_| runtime_failure(RuntimeControlFailure::CleanupUnsettled))?;
    fs::remove_file(request.export_root.join("status.json"))
        .map_err(|_| runtime_failure(RuntimeControlFailure::CleanupUnsettled))?;
    fs::remove_dir(&request.export_root)
        .map_err(|_| runtime_failure(RuntimeControlFailure::CleanupUnsettled))?;
    Ok(AdmittedLauncherExport {
        child: status.child,
        export_outcome,
    })
}

fn remove_launcher_export(root: &std::path::Path) -> Result<(), SandboxFailure> {
    let metadata = fs::symlink_metadata(root)
        .map_err(|_| runtime_failure(RuntimeControlFailure::CleanupUnsettled))?;
    if !metadata.file_type().is_dir() || metadata.file_type().is_symlink() {
        return Err(runtime_failure(RuntimeControlFailure::CleanupUnsettled));
    }
    fs::remove_dir_all(root).map_err(|_| runtime_failure(RuntimeControlFailure::CleanupUnsettled))
}

fn step_observation(
    request: &SandboxStepRequest,
    order: u32,
    value: ObservedContainerExit,
    export_outcome: TrialExportOutcome,
    outcome_override: Option<TrialOperationOutcome>,
) -> Result<TrialStepObservation, SandboxFailure> {
    let outcome = outcome_override.unwrap_or(operation_outcome(&value)?);
    Ok(TrialStepObservation {
        slot_id: request.slot_id.clone(),
        operation_order: order,
        workspace_identity: format!("workspace_{}", request.slot_id),
        visible_role_inventory_digests: request.visible_role_inventory_digests.clone(),
        outcome,
        exit_code: value.exit_code,
        signal: value.signal,
        stdout_sha256: sha256_text(&value.stdout),
        stderr_sha256: sha256_text(&value.stderr),
        stdout: value.stdout,
        stderr: value.stderr,
        workspace_before_sha256: value
            .workspace_before_sha256
            .ok_or_else(|| infrastructure(TrialRelayFailure::ImplementationUnavailable))?,
        workspace_after_sha256: value
            .workspace_after_sha256
            .ok_or_else(|| infrastructure(TrialRelayFailure::ImplementationUnavailable))?,
        export_outcome,
        elapsed_ms: value.elapsed_ms,
        cpu_time_ms: value.cpu_time_ms,
        peak_memory_bytes: value.peak_memory_bytes,
        peak_pids: value.peak_pids,
        written_bytes: value.written_bytes,
        written_entries: value.written_entries,
        measurement_method: value.measurement_method,
    })
}

fn operation_outcome(
    value: &ObservedContainerExit,
) -> Result<TrialOperationOutcome, SandboxFailure> {
    let valid_projection = match value.termination {
        RuntimeTermination::Exited => value.exit_code.is_some() && value.signal.is_none(),
        RuntimeTermination::Signalled => value.exit_code.is_none() && value.signal.is_some(),
        RuntimeTermination::DeadlineExceeded
        | RuntimeTermination::CpuExceeded
        | RuntimeTermination::MemoryExceeded
        | RuntimeTermination::PidExceeded
        | RuntimeTermination::DiskExceeded
        | RuntimeTermination::OutputExceeded => value.exit_code.is_none() && value.signal.is_none(),
    };
    if !valid_projection {
        return Err(infrastructure(TrialRelayFailure::ImplementationUnavailable));
    }
    let outcome = match value.termination {
        RuntimeTermination::Exited if value.exit_code == Some(0) && value.signal.is_none() => {
            TrialOperationOutcome::Succeeded
        }
        RuntimeTermination::Exited if value.exit_code.is_some_and(|code| code != 0) => {
            TrialOperationOutcome::ExitNonzero
        }
        RuntimeTermination::Signalled => TrialOperationOutcome::Signalled,
        RuntimeTermination::DeadlineExceeded => TrialOperationOutcome::DeadlineExceeded,
        RuntimeTermination::CpuExceeded => TrialOperationOutcome::CpuExceeded,
        RuntimeTermination::MemoryExceeded => TrialOperationOutcome::MemoryExceeded,
        RuntimeTermination::PidExceeded => TrialOperationOutcome::PidExceeded,
        RuntimeTermination::DiskExceeded => TrialOperationOutcome::DiskExceeded,
        RuntimeTermination::OutputExceeded => TrialOperationOutcome::OutputExceeded,
        _ => return Err(infrastructure(TrialRelayFailure::ImplementationUnavailable)),
    };
    Ok(outcome)
}

fn owned_mount(
    source: &std::path::Path,
    destination: &str,
    readonly: bool,
    class: OwnedMountClass,
) -> Result<OwnedBindMount, SandboxFailure> {
    let source_text = source
        .to_str()
        .filter(|value| value.starts_with('/') && !value.contains(',') && !value.contains('\n'))
        .ok_or_else(|| infrastructure(TrialRelayFailure::InvalidRequest))?;
    if source_text.contains('\r')
        || !destination.starts_with('/')
        || destination.contains(',')
        || destination.contains('\n')
        || destination.contains('\r')
    {
        return Err(infrastructure(TrialRelayFailure::InvalidRequest));
    }
    Ok(OwnedBindMount {
        source: source.to_owned(),
        destination: destination.to_owned(),
        readonly,
        class,
    })
}

fn runtime_failure(value: RuntimeControlFailure) -> SandboxFailure {
    eprintln!("trial runtime stage=control failure={value:?}");
    match value {
        RuntimeControlFailure::DeadlineExceeded => {
            infrastructure(TrialRelayFailure::DeadlineExceeded)
        }
        RuntimeControlFailure::Cancelled => infrastructure(TrialRelayFailure::Cancelled),
        RuntimeControlFailure::CapacityExceeded => {
            infrastructure(TrialRelayFailure::CapacityExceeded)
        }
        RuntimeControlFailure::CleanupUnsettled => SandboxFailure {
            code: TrialRelayFailure::CleanupUnsettled,
            cleanup_unsettled: true,
        },
        _ => infrastructure(TrialRelayFailure::ImplementationUnavailable),
    }
}

fn infrastructure(code: TrialRelayFailure) -> SandboxFailure {
    SandboxFailure {
        code,
        cleanup_unsettled: false,
    }
}

fn valid_sha256(value: &str) -> bool {
    value.len() == 71
        && value.starts_with("sha256:")
        && value[7..]
            .bytes()
            .all(|item| item.is_ascii_digit() || (b'a'..=b'f').contains(&item))
}

fn sha256_text(value: &str) -> String {
    format!("sha256:{:x}", Sha256::digest(value.as_bytes()))
}

#[cfg(test)]
mod runtime_journal_tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;

    fn owner() -> RuntimeOwner {
        RuntimeOwner {
            deployment_owner: "deployment_a".into(),
            request_digest: format!("sha256:{}", "9".repeat(64)),
            attempt_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00001".into(),
            trial_owner_id: format!("trial_{}", "a".repeat(32)),
        }
    }

    fn root() -> PathBuf {
        let root = std::env::temp_dir().join(format!(
            "workstream-runtime-journal-{}-{}",
            std::process::id(),
            RUNTIME_FILE_SEQUENCE.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&root).unwrap();
        fs::set_permissions(&root, fs::Permissions::from_mode(0o700)).unwrap();
        root
    }

    #[test]
    fn runtime_journal_round_trips_exact_owner_reservations() {
        let root = root();
        let owner = owner();
        let resources = OwnedRuntimeResources {
            containers: vec!["ws-trial-reserved".into()],
            images: vec![(
                format!("workstream-trial:{}", "a".repeat(32)),
                String::new(),
            )],
        };
        persist_runtime_journal(&root, &owner, &resources).unwrap();
        let loaded = load_runtime_journals(&root).unwrap();
        assert_eq!(loaded.get(&owner), Some(&resources));
        remove_runtime_journal(&root, &owner).unwrap();
        assert!(load_runtime_journals(&root).unwrap().is_empty());
        fs::remove_dir(root).unwrap();
    }

    #[test]
    fn runtime_journal_rejects_noncanonical_or_weakly_owned_bytes() {
        let root = root();
        let owner = owner();
        let resources = OwnedRuntimeResources {
            containers: vec!["ws-trial-reserved".into()],
            images: Vec::new(),
        };
        persist_runtime_journal(&root, &owner, &resources).unwrap();
        let path = runtime_journal_path(&root, &owner).unwrap();
        let mut bytes = fs::read(&path).unwrap();
        bytes.push(b'\n');
        fs::write(&path, bytes).unwrap();
        assert_eq!(
            load_runtime_journals(&root).unwrap_err(),
            RuntimeControlFailure::CleanupUnsettled
        );
        fs::set_permissions(&path, fs::Permissions::from_mode(0o644)).unwrap();
        assert_eq!(
            load_runtime_journals(&root).unwrap_err(),
            RuntimeControlFailure::CleanupUnsettled
        );
        fs::remove_file(path).unwrap();
        fs::remove_dir(root).unwrap();
    }

    fn tar_entry(path: &str, typeflag: u8, link: &str, bytes: &[u8]) -> Vec<u8> {
        let mut header = [0_u8; 512];
        assert!(path.len() < 100);
        header[..path.len()].copy_from_slice(path.as_bytes());
        header[100..108].copy_from_slice(b"0000600\0");
        header[108..116].copy_from_slice(b"0000000\0");
        header[116..124].copy_from_slice(b"0000000\0");
        let size = format!("{:011o}\0", bytes.len());
        header[124..136].copy_from_slice(size.as_bytes());
        header[136..148].copy_from_slice(b"00000000000\0");
        header[148..156].fill(b' ');
        header[156] = typeflag;
        assert!(link.len() < 100);
        header[157..157 + link.len()].copy_from_slice(link.as_bytes());
        header[257..263].copy_from_slice(b"ustar\0");
        header[263..265].copy_from_slice(b"00");
        let checksum = header.iter().map(|byte| u64::from(*byte)).sum::<u64>();
        let checksum = format!("{checksum:06o}\0 ");
        header[148..156].copy_from_slice(checksum.as_bytes());
        let mut result = header.to_vec();
        result.extend_from_slice(bytes);
        result.resize(result.len().next_multiple_of(512), 0);
        result
    }

    fn image_archive(
        manifest_path: &str,
        manifest_entries: usize,
        config_bytes: &[u8],
        config_name_override: Option<&str>,
        layer_path: &str,
        layer_type: u8,
        layer_link: &str,
    ) -> Vec<u8> {
        let mut layer = tar_entry("work/value", b'0', "", b"value");
        layer.extend([0_u8; 1024]);
        let mut config: serde_json::Value = serde_json::from_slice(config_bytes).unwrap();
        config["rootfs"] = serde_json::json!({"type": "layers", "diff_ids": [format!("sha256:{:x}", Sha256::digest(&layer))]});
        let config_bytes = serde_json::to_vec(&config).unwrap();
        let config_bytes = config_bytes.as_slice();
        let config_name = config_name_override
            .map(str::to_owned)
            .unwrap_or_else(|| format!("{:x}.json", Sha256::digest(config_bytes)));
        let item = serde_json::json!({
            "Config": config_name,
            "RepoTags": ["workstream-trial:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"],
            "Layers": [layer_path],
        });
        let manifest = serde_json::to_vec(&vec![item; manifest_entries]).unwrap();
        let mut archive = tar_entry(manifest_path, b'0', "", &manifest);
        archive.extend(tar_entry(&config_name, b'0', "", config_bytes));
        archive.extend(tar_entry(layer_path, layer_type, layer_link, &layer));
        archive.extend([0_u8; 1024]);
        archive
    }

    fn validate_archive_bytes(
        root: &std::path::Path,
        bytes: &[u8],
    ) -> Result<(), RuntimeControlFailure> {
        let path = root.join("candidate.tar");
        fs::write(&path, bytes).unwrap();
        validate_single_image_archive(
            &path,
            "workstream-trial:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            1024 * 1024,
            1024 * 1024,
            4096,
            Instant::now() + Duration::from_secs(10),
        )
        .map(|_| ())
    }

    #[test]
    fn image_archive_requires_one_canonical_regular_exactly_referenced_image() {
        let root = root();
        let valid = image_archive("manifest.json", 1, b"{}", None, "layer.tar.gz", b'0', "");
        validate_archive_bytes(&root, &valid).unwrap();

        for invalid in [
            image_archive("./manifest.json", 1, b"{}", None, "layer.tar.gz", b'0', ""),
            image_archive("manifest.json", 2, b"{}", None, "layer.tar.gz", b'0', ""),
            image_archive("manifest.json", 1, b"{}", None, "a//b", b'0', ""),
            image_archive(
                "manifest.json",
                1,
                b"{}",
                None,
                "layer.tar.gz",
                b'2',
                "target",
            ),
            image_archive("manifest.json", 1, b"{}", None, "layer.tar.gz", b'x', ""),
            image_archive(
                "manifest.json",
                1,
                b"{}",
                Some("0000000000000000000000000000000000000000000000000000000000000000.json"),
                "layer.tar.gz",
                b'0',
                "",
            ),
        ] {
            assert_eq!(
                validate_archive_bytes(&root, &invalid),
                Err(RuntimeControlFailure::InvalidObservation)
            );
        }

        let mut nonzero_trailing = valid;
        *nonzero_trailing.last_mut().unwrap() = 1;
        assert_eq!(
            validate_archive_bytes(&root, &nonzero_trailing),
            Err(RuntimeControlFailure::InvalidObservation)
        );
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn candidate_expansion_is_refused_before_any_docker_command() {
        let root = root();
        let binary = root.join("docker-probe");
        fs::write(
            &binary,
            b"#!/bin/sh\nprintf invoked > \"$0.invoked\"\nexit 1\n",
        )
        .unwrap();
        fs::set_permissions(&binary, fs::Permissions::from_mode(0o700)).unwrap();
        let configuration = root.join("daemon.json");
        fs::write(&configuration, b"{}").unwrap();
        let archive = root.join("candidate.tar");
        fs::write(
            &archive,
            image_archive("manifest.json", 1, b"{}", None, "layer.tar", b'0', ""),
        )
        .unwrap();
        let control = DockerRuntimeControl::new(binary, root.clone(), configuration).unwrap();
        assert_eq!(
            control.load_single_owned_image(
                &owner(),
                &archive,
                "workstream-trial:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                1024 * 1024,
                1,
                4096,
                Instant::now() + Duration::from_secs(10),
            ),
            Err(RuntimeControlFailure::CapacityExceeded)
        );
        assert!(!root.join("docker-probe.invoked").exists());
        assert!(control.owned.lock().unwrap().is_empty());
        fs::remove_dir_all(root).unwrap();
    }
}
