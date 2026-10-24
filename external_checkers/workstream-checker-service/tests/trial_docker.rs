use sha2::Digest;
use std::collections::VecDeque;
use std::fs::{self, File};
use std::os::unix::fs::{MetadataExt, PermissionsExt};
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicBool, AtomicI32, AtomicU8};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Mutex;
use std::time::{Duration, Instant};

#[cfg(not(feature = "trial-docker-qualification"))]
#[allow(dead_code)]
#[path = "../src/trial_docker.rs"]
mod trial_docker;
#[cfg(not(feature = "trial-docker-qualification"))]
#[allow(dead_code)]
#[path = "../src/trial_engine.rs"]
mod trial_engine;
#[cfg(not(feature = "trial-docker-qualification"))]
#[allow(dead_code)]
#[path = "../src/trial_relay.rs"]
mod trial_relay;

#[cfg(feature = "trial-docker-qualification")]
use crate::trial_docker::*;
#[cfg(feature = "trial-docker-qualification")]
use crate::trial_engine::*;
#[cfg(feature = "trial-docker-qualification")]
use crate::trial_relay::*;
#[cfg(not(feature = "trial-docker-qualification"))]
use trial_docker::*;
#[cfg(not(feature = "trial-docker-qualification"))]
use trial_engine::*;
#[cfg(not(feature = "trial-docker-qualification"))]
use trial_relay::*;

static TEST_ROOT_SEQUENCE: AtomicU64 = AtomicU64::new(0);

#[derive(Default)]
struct FakeControl {
    creates: Mutex<Vec<OwnedContainerCreate>>,
    limits: Mutex<Vec<ContainerExecutionLimits>>,
    launcher_child_exit: AtomicI32,
    builder_export_failure: AtomicU8,
    step_export_failure: AtomicU8,
    observations: Mutex<VecDeque<ObservedContainerExit>>,
    cleaned: Mutex<Vec<RuntimeOwner>>,
}

impl RuntimeControl for FakeControl {
    fn require_image(
        &self,
        config_image_id: &str,
        identity: &SandboxBackendIdentity,
        runtime_key: &str,
        _deadline: Instant,
    ) -> Result<(), RuntimeControlFailure> {
        assert_eq!(config_image_id, digest('4'));
        assert_eq!(identity.platform_identity_digest, digest('3'));
        assert_eq!(runtime_key, "runsc");
        Ok(())
    }

    fn require_offline_cache(
        &self,
        root: &Path,
        inventory_digest: &str,
    ) -> Result<(), RuntimeControlFailure> {
        assert!(root.is_absolute());
        assert_eq!(inventory_digest, digest('5'));
        Ok(())
    }

    fn create_owned_container(
        &self,
        request: OwnedContainerCreate,
        _deadline: Instant,
        _invocation_cancelled: &AtomicBool,
        _relay_cancelled: &AtomicBool,
    ) -> Result<(), RuntimeControlFailure> {
        self.creates.lock().unwrap().push(request);
        Ok(())
    }

    fn run_owned_container(
        &self,
        _owner: &RuntimeOwner,
        _name: &str,
        writable_roots: &[PathBuf],
        limits: &ContainerExecutionLimits,
        _invocation_cancelled: &AtomicBool,
        _relay_cancelled: &AtomicBool,
    ) -> Result<ObservedContainerExit, RuntimeControlFailure> {
        self.limits.lock().unwrap().push(limits.clone());
        let observation = self
            .observations
            .lock()
            .unwrap()
            .pop_front()
            .ok_or(RuntimeControlFailure::InvalidObservation)?;
        if observation.workspace_before_sha256.is_none() {
            let output = writable_roots
                .first()
                .ok_or(RuntimeControlFailure::InvalidObservation)?;
            let child_exit = self.launcher_child_exit.load(Ordering::Relaxed);
            let export_failure = self.builder_export_failure.load(Ordering::Relaxed);
            if child_exit == 0 && export_failure == 0 {
                fs::write(output.join("candidate.tar"), vec![0_u8; 128])
                    .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
            }
            let failure = match export_failure {
                0 => "null",
                1 => "\"capacity_exceeded\"",
                2 => "\"invalid\"",
                _ => return Err(RuntimeControlFailure::InvalidObservation),
            };
            fs::write(
                output.join("status.json"),
                format!("{{\"candidate_exported\":{},\"child\":{{\"exit_code\":{child_exit},\"signal\":null}},\"export_failure\":{failure},\"schema\":\"workstream.trial_launcher_status.v1\",\"workspace_exported\":false}}", child_exit == 0 && export_failure == 0),
            )
            .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
        } else {
            let export = writable_roots
                .first()
                .ok_or(RuntimeControlFailure::InvalidObservation)?;
            let export_failure = self.step_export_failure.load(Ordering::Relaxed);
            if export_failure == 0 {
                fs::create_dir(export.join("workspace.next"))
                    .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
            }
            let child_exit = self.launcher_child_exit.load(Ordering::Relaxed);
            let failure = match export_failure {
                0 => "null",
                1 => "\"capacity_exceeded\"",
                2 => "\"invalid\"",
                _ => return Err(RuntimeControlFailure::InvalidObservation),
            };
            fs::write(
                export.join("status.json"),
                format!("{{\"candidate_exported\":false,\"child\":{{\"exit_code\":{child_exit},\"signal\":null}},\"export_failure\":{failure},\"schema\":\"workstream.trial_launcher_status.v1\",\"workspace_exported\":{}}}", export_failure == 0),
            )
            .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
        }
        Ok(observation)
    }

    fn load_single_owned_image(
        &self,
        _owner: &RuntimeOwner,
        _archive: &Path,
        expected_tag: &str,
        _maximum_bytes: u64,
        maximum_expanded_bytes: u64,
        maximum_expanded_entries: u64,
        _deadline: Instant,
    ) -> Result<LoadedOwnedImage, RuntimeControlFailure> {
        assert!(expected_tag.starts_with("workstream-trial:"));
        assert!(maximum_expanded_bytes >= 1024);
        assert!(maximum_expanded_entries >= 2);
        Ok(LoadedOwnedImage {
            config_image_id: digest('a'),
            archive_sha256: digest('b'),
            archive_byte_count: 128,
            expanded_byte_count: 1024,
            expanded_entry_count: 2,
        })
    }

    fn cleanup_owner(
        &self,
        owner: &RuntimeOwner,
        _deadline: Instant,
    ) -> Result<(), RuntimeControlFailure> {
        self.cleaned.lock().unwrap().push(owner.clone());
        Ok(())
    }
}

fn digest(character: char) -> String {
    format!("sha256:{}", character.to_string().repeat(64))
}

fn identity() -> SandboxBackendIdentity {
    SandboxBackendIdentity {
        engine_identity_digest: digest('1'),
        child_runtime: "runsc".into(),
        child_runtime_config_digest: digest('2'),
        child_host_uds: "none".into(),
        platform: "linux/amd64".into(),
        platform_identity_digest: digest('3'),
        builder_image_digest: digest('4'),
        trusted_launcher_digest: digest('6'),
        offline_cache_digest: digest('5'),
        approved_base_digests: vec![digest('6')],
    }
}

fn resources() -> TrialResources {
    TrialResources {
        cpu_quota_millis: 500,
        cpu_time_ms: 2000,
        memory_bytes: 64 * 1024 * 1024,
        disk_bytes: 32 * 1024 * 1024,
        maximum_entries: 100,
        pids: 16,
    }
}

fn overruns() -> SandboxEnforcementOverruns {
    SandboxEnforcementOverruns {
        wall_time_ms: 100,
        cpu_time_ms: 200,
        memory_bytes: 1024,
        pids: 1,
        disk_bytes: 4096,
        entries: 2,
    }
}

fn observed(workspace: bool) -> ObservedContainerExit {
    ObservedContainerExit {
        termination: RuntimeTermination::Exited,
        exit_code: Some(0),
        signal: None,
        stdout: "ok\n".into(),
        stderr: String::new(),
        elapsed_ms: 20,
        cpu_time_ms: 10,
        peak_memory_bytes: 1024,
        peak_pids: 1,
        written_bytes: 128,
        written_entries: 1,
        measurement_method: "cgroup_v2_and_owned_tree".into(),
        workspace_before_sha256: workspace.then(|| digest('7')),
        workspace_after_sha256: workspace.then(|| digest('8')),
    }
}

struct Root(PathBuf);

impl Root {
    fn new() -> Self {
        let root = std::env::temp_dir().join(format!(
            "workstream-trial-docker-test-{}-{}",
            std::process::id(),
            TEST_ROOT_SEQUENCE.fetch_add(1, Ordering::Relaxed),
        ));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir(&root).unwrap();
        fs::set_permissions(&root, fs::Permissions::from_mode(0o700)).unwrap();
        Self(root)
    }

    fn child(&self, name: &str) -> PathBuf {
        let path = self.0.join(name);
        fs::create_dir(&path).unwrap();
        path
    }
}

impl Drop for Root {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn backend(root: &Root) -> DockerTrialBackend<FakeControl> {
    let cache = root.child("cache");
    let launcher = root.0.join("launcher");
    fs::write(&launcher, b"trusted launcher").unwrap();
    fs::set_permissions(&launcher, fs::Permissions::from_mode(0o555)).unwrap();
    let launcher_digest = format!("sha256:{:x}", sha2::Sha256::digest(b"trusted launcher"));
    let mut identity = identity();
    identity.trusted_launcher_digest = launcher_digest.clone();
    DockerTrialBackend::new(
        DockerTrialConfiguration {
            identity,
            deployment_owner: "deployment_a".into(),
            request_digest: digest('9'),
            attempt_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00001".into(),
            runtime_key: "runsc".into(),
            builder_image_id: digest('4'),
            trusted_launcher_path: launcher,
            trusted_launcher_digest: launcher_digest,
            offline_cache_root: cache,
            maximum_candidate_archive_bytes: 64 * 1024 * 1024,
            candidate_uid: 65532,
            candidate_gid: 65532,
            export_uid: 65532,
            export_gid: 65532,
        },
        FakeControl {
            observations: Mutex::new(VecDeque::from([observed(false), observed(true)])),
            ..FakeControl::default()
        },
    )
    .unwrap()
}

#[test]
fn backend_emits_offline_bounded_builder_and_socketless_candidate_specs() {
    let root = Root::new();
    let context = root.child("context");
    let output = root.child("output");
    let workspace = root.child("workspace");
    let export = root.child("export");
    let source = root.child("source");
    let backend = backend(&root);
    let deadline = Instant::now() + Duration::from_secs(2);
    let cancelled = AtomicBool::new(false);
    let build = backend
        .build(
            &SandboxBuildRequest {
                owner_id: format!("trial_{}", "a".repeat(32)),
                context_root: context,
                context_relative: "environment".into(),
                dockerfile_relative: "environment/Containerfile".into(),
                output_archive: output.join("candidate.tar"),
                destination: "workstream-trial:test".into(),
                platform: "linux/amd64".into(),
                resources: resources(),
                remaining_cpu_time_ms: 2_000,
                mutable_disk_bytes: 4096,
                mutable_entries: 10,
                launcher_root_bytes: 64 * 1024,
                launcher_root_entries: 64,
                launcher_candidate_bytes: 16 * 1024,
                launcher_temporary_bytes: 4096,
                launcher_temporary_entries: 2,
                launcher_shared_memory_bytes: 4096,
                launcher_shared_memory_entries: 2,
                timeout_ms: 1000,
                maximum_output_bytes: 4096,
                enforcement_overruns: overruns(),
            },
            deadline,
            &cancelled,
            &cancelled,
        )
        .unwrap();
    assert_eq!(build.observation.candidate_image_digest, Some(digest('a')));
    assert_eq!(
        build.observation.export_outcome,
        TrialExportOutcome::Exported
    );
    backend
        .control
        .launcher_child_exit
        .store(17, Ordering::Relaxed);
    let step = backend
        .run_step(
            &SandboxStepRequest {
                owner_id: format!("trial_{}", "a".repeat(32)),
                slot_id: "slot_a".into(),
                candidate_image_digest: digest('a'),
                workspace_root: workspace,
                export_root: export,
                visible_roles: vec![ProjectedRoleMount {
                    role: "source".into(),
                    path: source,
                    destination_relative: "source".into(),
                }],
                visible_role_inventory_digests: vec![RoleInventoryDigest {
                    role: "source".into(),
                    digest: digest('c'),
                }],
                command: vec!["/candidate/check".into(), "case-a".into()],
                working_directory: ".".into(),
                resources: resources(),
                remaining_cpu_time_ms: 2_000,
                mutable_disk_bytes: 4096,
                mutable_entries: 10,
                launcher_root_bytes: 64 * 1024,
                launcher_root_entries: 32,
                launcher_workspace_bytes: 4096,
                launcher_workspace_entries: 10,
                launcher_temporary_bytes: 4096,
                launcher_temporary_entries: 2,
                launcher_shared_memory_bytes: 4096,
                launcher_shared_memory_entries: 2,
                timeout_ms: 500,
                maximum_output_bytes: 4096,
                enforcement_overruns: overruns(),
            },
            1,
            deadline,
            &cancelled,
            &cancelled,
        )
        .unwrap();
    assert_eq!(step.observation.outcome, TrialOperationOutcome::ExitNonzero);
    assert_eq!(step.observation.exit_code, Some(17));
    assert_eq!(
        step.observation.export_outcome,
        TrialExportOutcome::Exported
    );
    let creates = backend.control.creates.lock().unwrap();
    assert_eq!(creates.len(), 2);
    let builder = &creates[0].arguments;
    assert!(builder.iter().any(|item| item == "--no-healthcheck"));
    assert!(builder
        .windows(2)
        .any(|item| item == ["--entrypoint", "/workstream-bootstrap/launcher"]));
    assert!(builder.iter().any(|item| item == "--ignore-path=/out"));
    assert!(builder.iter().any(|item| item == "--candidate-bytes"));
    assert!(builder
        .windows(2)
        .any(|item| item == ["--export-uid", "65532"]));
    assert!(builder
        .windows(2)
        .any(|item| item == ["--export-gid", "65532"]));
    assert!(builder.windows(2).any(|item| item == ["--network", "none"]));
    assert!(builder
        .windows(2)
        .any(|item| item == ["--runtime", "runsc"]));
    assert_eq!(
        builder.iter().filter(|item| *item == "--cap-add").count(),
        9
    );
    assert!(!builder.iter().any(|item| item == "--privileged"));
    assert!(!builder.iter().any(|item| item == "--mount"));
    assert!(builder
        .iter()
        .any(|item| item == "--dockerfile=/workspace/environment/Containerfile"));
    assert!(builder
        .iter()
        .any(|item| item == "--context=dir:///workspace/environment"));
    assert!(!builder
        .iter()
        .any(|item| { item == "--dockerfile=/workspace/environment/environment/Containerfile" }));
    assert_eq!(creates[0].mounts.len(), 4);
    assert_eq!(creates[0].mounts[0].class, OwnedMountClass::TrustedLauncher);
    assert_eq!(creates[0].mounts[1].class, OwnedMountClass::LauncherContext);
    assert_eq!(creates[0].mounts[2].class, OwnedMountClass::LauncherCache);
    assert_eq!(creates[0].mounts[3].class, OwnedMountClass::LauncherExport);
    assert!(creates[0].mounts[..3].iter().all(|mount| mount.readonly));
    assert!(!creates[0].mounts[3].readonly);
    let candidate = &creates[1].arguments;
    assert!(candidate.iter().any(|item| item == "--no-healthcheck"));
    assert!(candidate.iter().any(|item| item == "--read-only"));
    assert!(candidate.iter().any(|item| item == "step"));
    assert!(candidate.iter().any(|item| item == "--root-inodes"));
    assert!(candidate
        .windows(2)
        .any(|item| item == ["--export-uid", "65532"]));
    assert!(candidate
        .windows(2)
        .any(|item| item == ["--export-gid", "65532"]));
    assert!(candidate
        .windows(2)
        .any(|item| item == ["--visible", "source=source"]));
    assert!(candidate.windows(2).any(|item| item == ["--user", "0:0"]));
    assert!(!candidate.iter().any(|item| item.contains("docker.sock")));
    assert!(!candidate.iter().any(|item| item.contains("execution.sock")));
    assert!(!candidate.iter().any(|item| item.contains("model.sock")));
    assert_eq!(
        candidate.iter().filter(|item| *item == "--cap-add").count(),
        9
    );
    assert!(!candidate.iter().any(|item| item == "--mount"));
    assert_eq!(creates[1].mounts[0].class, OwnedMountClass::TrustedLauncher);
    assert_eq!(
        creates[1].mounts[1].class,
        OwnedMountClass::LauncherWorkspace
    );
    assert_eq!(creates[1].mounts[2].class, OwnedMountClass::LauncherExport);
    assert_eq!(creates[1].mounts[3].class, OwnedMountClass::LauncherRole);
    assert_eq!(
        creates[1].mounts[3].destination,
        "/workstream-bootstrap/input/roles/source"
    );
    assert!(creates[1].mounts[0].readonly && creates[1].mounts[1].readonly);
    assert!(!creates[1].mounts[2].readonly);
    assert!(creates[1].mounts[3].readonly);
    drop(creates);
    let limits = backend.control.limits.lock().unwrap();
    assert_eq!(limits[1].wall_time_overrun_ms, 100);
    assert_eq!(limits[1].cpu_time_overrun_ms, 200);
    drop(limits);
    let launcher = backend.control.creates.lock().unwrap()[0].mounts[0]
        .source
        .clone();
    fs::set_permissions(&launcher, fs::Permissions::from_mode(0o755)).unwrap();
    fs::write(&launcher, b"drifted launcher").unwrap();
    fs::set_permissions(&launcher, fs::Permissions::from_mode(0o555)).unwrap();
    let drift_output = root.child("drift-output");
    let failure = backend
        .build(
            &SandboxBuildRequest {
                owner_id: format!("trial_{}", "b".repeat(32)),
                context_root: root.child("drift-context"),
                context_relative: ".".into(),
                dockerfile_relative: "Dockerfile".into(),
                output_archive: drift_output.join("candidate.tar"),
                destination: format!("workstream-trial:{}", "b".repeat(32)),
                platform: "linux/amd64".into(),
                resources: resources(),
                remaining_cpu_time_ms: 2_000,
                mutable_disk_bytes: 1024 * 1024,
                mutable_entries: 100,
                launcher_root_bytes: 512 * 1024,
                launcher_root_entries: 64,
                launcher_candidate_bytes: 128 * 1024,
                launcher_temporary_bytes: 4096,
                launcher_temporary_entries: 4,
                launcher_shared_memory_bytes: 4096,
                launcher_shared_memory_entries: 4,
                timeout_ms: 1000,
                maximum_output_bytes: 4096,
                enforcement_overruns: overruns(),
            },
            deadline,
            &cancelled,
            &cancelled,
        )
        .unwrap_err();
    assert_eq!(failure.code, TrialRelayFailure::ImplementationUnavailable);
    assert_eq!(backend.control.creates.lock().unwrap().len(), 2);
    backend
        .cleanup(&format!("trial_{}", "a".repeat(32)), deadline)
        .unwrap();
    assert_eq!(backend.control.cleaned.lock().unwrap().len(), 1);
}

#[test]
fn trusted_builder_status_keeps_child_125_as_a_work_outcome() {
    let root = Root::new();
    let context = root.child("context");
    let output = root.child("output");
    let backend = backend(&root);
    backend
        .control
        .launcher_child_exit
        .store(125, Ordering::Relaxed);
    let result = backend
        .build(
            &SandboxBuildRequest {
                owner_id: format!("trial_{}", "c".repeat(32)),
                context_root: context,
                context_relative: ".".into(),
                dockerfile_relative: "Dockerfile".into(),
                output_archive: output.join("candidate.tar"),
                destination: format!("workstream-trial:{}", "c".repeat(32)),
                platform: "linux/amd64".into(),
                resources: resources(),
                remaining_cpu_time_ms: 2_000,
                mutable_disk_bytes: 1024 * 1024,
                mutable_entries: 100,
                launcher_root_bytes: 512 * 1024,
                launcher_root_entries: 64,
                launcher_candidate_bytes: 128 * 1024,
                launcher_temporary_bytes: 4096,
                launcher_temporary_entries: 4,
                launcher_shared_memory_bytes: 4096,
                launcher_shared_memory_entries: 4,
                timeout_ms: 1000,
                maximum_output_bytes: 4096,
                enforcement_overruns: overruns(),
            },
            Instant::now() + Duration::from_secs(2),
            &AtomicBool::new(false),
            &AtomicBool::new(false),
        )
        .unwrap();
    assert_eq!(
        result.observation.outcome,
        TrialOperationOutcome::ExitNonzero
    );
    assert_eq!(result.observation.exit_code, Some(125));
    assert_eq!(
        result.observation.export_outcome,
        TrialExportOutcome::NotStarted
    );
    assert!(result.observation.candidate_image_digest.is_none());
    assert!(fs::read_dir(output).unwrap().next().is_none());
}

#[test]
fn launcher_exit_125_is_infrastructure_even_when_a_fake_status_exists() {
    let root = Root::new();
    let output = root.child("launcher-infrastructure-output");
    let backend = backend(&root);
    let mut launcher_failure = observed(false);
    launcher_failure.exit_code = Some(125);
    let mut observations = backend.control.observations.lock().unwrap();
    observations.clear();
    observations.push_back(launcher_failure);
    drop(observations);
    let failure = backend
        .build(
            &SandboxBuildRequest {
                owner_id: format!("trial_{}", "d".repeat(32)),
                context_root: root.child("launcher-infrastructure-context"),
                context_relative: ".".into(),
                dockerfile_relative: "Dockerfile".into(),
                output_archive: output.join("candidate.tar"),
                destination: format!("workstream-trial:{}", "d".repeat(32)),
                platform: "linux/amd64".into(),
                resources: resources(),
                remaining_cpu_time_ms: 2_000,
                mutable_disk_bytes: 1024 * 1024,
                mutable_entries: 100,
                launcher_root_bytes: 512 * 1024,
                launcher_root_entries: 64,
                launcher_candidate_bytes: 128 * 1024,
                launcher_temporary_bytes: 4096,
                launcher_temporary_entries: 4,
                launcher_shared_memory_bytes: 4096,
                launcher_shared_memory_entries: 4,
                timeout_ms: 1000,
                maximum_output_bytes: 4096,
                enforcement_overruns: overruns(),
            },
            Instant::now() + Duration::from_secs(2),
            &AtomicBool::new(false),
            &AtomicBool::new(false),
        )
        .unwrap_err();
    assert_eq!(failure.code, TrialRelayFailure::ImplementationUnavailable);
}

#[test]
fn trusted_builder_export_failures_are_closed_facts_with_actual_child_status() {
    let cancelled = AtomicBool::new(false);
    for (index, failure, expected_outcome, expected_export) in [
        (
            0,
            1,
            TrialOperationOutcome::DiskExceeded,
            TrialExportOutcome::CapacityExceeded,
        ),
        (
            1,
            2,
            TrialOperationOutcome::ExportInvalid,
            TrialExportOutcome::Invalid,
        ),
    ] {
        let root = Root::new();
        let backend = backend(&root);
        backend
            .control
            .builder_export_failure
            .store(failure, Ordering::Relaxed);
        let output = root.child(&format!("closed-export-{index}"));
        let result = backend
            .build(
                &SandboxBuildRequest {
                    owner_id: format!("trial_{index:032x}"),
                    context_root: root.child(&format!("closed-context-{index}")),
                    context_relative: ".".into(),
                    dockerfile_relative: "Dockerfile".into(),
                    output_archive: output.join("candidate.tar"),
                    destination: format!("workstream-trial:{index:032x}"),
                    platform: "linux/amd64".into(),
                    resources: resources(),
                    remaining_cpu_time_ms: 2_000,
                    mutable_disk_bytes: 1024 * 1024,
                    mutable_entries: 100,
                    launcher_root_bytes: 512 * 1024,
                    launcher_root_entries: 64,
                    launcher_candidate_bytes: 128 * 1024,
                    launcher_temporary_bytes: 4096,
                    launcher_temporary_entries: 4,
                    launcher_shared_memory_bytes: 4096,
                    launcher_shared_memory_entries: 4,
                    timeout_ms: 1000,
                    maximum_output_bytes: 4096,
                    enforcement_overruns: overruns(),
                },
                Instant::now() + Duration::from_secs(2),
                &cancelled,
                &cancelled,
            )
            .unwrap();
        assert_eq!(result.observation.outcome, expected_outcome);
        assert_eq!(result.observation.export_outcome, expected_export);
        assert_eq!(result.observation.exit_code, Some(0));
        assert_eq!(result.observation.signal, None);
        assert_eq!(result.observation.written_bytes, 128);
        assert!(result.observation.candidate_image_digest.is_none());
        assert!(fs::read_dir(output).unwrap().next().is_none());
    }
}

#[test]
fn backend_projects_forced_causes_without_synthetic_exit_or_signal() {
    let root = Root::new();
    let context = root.child("context-forced");
    let output = root.child("output-forced");
    let backend = backend(&root);
    let mut observations = backend.control.observations.lock().unwrap();
    observations.clear();
    for termination in [
        RuntimeTermination::DeadlineExceeded,
        RuntimeTermination::CpuExceeded,
        RuntimeTermination::MemoryExceeded,
        RuntimeTermination::DiskExceeded,
    ] {
        let mut value = observed(false);
        value.termination = termination;
        value.exit_code = None;
        value.signal = None;
        observations.push_back(value);
    }
    let mut invalid = observed(false);
    invalid.termination = RuntimeTermination::DeadlineExceeded;
    invalid.exit_code = Some(137);
    observations.push_back(invalid);
    drop(observations);

    let deadline = Instant::now() + Duration::from_secs(2);
    let cancelled = AtomicBool::new(false);
    for (index, expected) in [
        TrialOperationOutcome::DeadlineExceeded,
        TrialOperationOutcome::CpuExceeded,
        TrialOperationOutcome::MemoryExceeded,
        TrialOperationOutcome::DiskExceeded,
    ]
    .into_iter()
    .enumerate()
    {
        let result = backend
            .build(
                &SandboxBuildRequest {
                    owner_id: format!("trial_{index:032x}"),
                    context_root: context.clone(),
                    context_relative: ".".into(),
                    dockerfile_relative: "Dockerfile".into(),
                    output_archive: output.join(format!("candidate-{index}.tar")),
                    destination: format!("workstream-trial:{index:032x}"),
                    platform: "linux/amd64".into(),
                    resources: resources(),
                    remaining_cpu_time_ms: 2_000,
                    mutable_disk_bytes: 4096,
                    mutable_entries: 10,
                    launcher_root_bytes: 64 * 1024,
                    launcher_root_entries: 64,
                    launcher_candidate_bytes: 16 * 1024,
                    launcher_temporary_bytes: 4096,
                    launcher_temporary_entries: 2,
                    launcher_shared_memory_bytes: 4096,
                    launcher_shared_memory_entries: 2,
                    timeout_ms: 1000,
                    maximum_output_bytes: 4096,
                    enforcement_overruns: overruns(),
                },
                deadline,
                &cancelled,
                &cancelled,
            )
            .unwrap();
        assert_eq!(result.observation.outcome, expected);
        assert_eq!(result.observation.exit_code, None);
        assert_eq!(result.observation.signal, None);
        assert_eq!(
            result.observation.export_outcome,
            TrialExportOutcome::Unavailable
        );
    }

    let invalid = backend.build(
        &SandboxBuildRequest {
            owner_id: format!("trial_{}", "f".repeat(32)),
            context_root: context,
            context_relative: ".".into(),
            dockerfile_relative: "Dockerfile".into(),
            output_archive: output.join("invalid.tar"),
            destination: format!("workstream-trial:{}", "f".repeat(32)),
            platform: "linux/amd64".into(),
            resources: resources(),
            remaining_cpu_time_ms: 2_000,
            mutable_disk_bytes: 4096,
            mutable_entries: 10,
            launcher_root_bytes: 64 * 1024,
            launcher_root_entries: 64,
            launcher_candidate_bytes: 16 * 1024,
            launcher_temporary_bytes: 4096,
            launcher_temporary_entries: 2,
            launcher_shared_memory_bytes: 4096,
            launcher_shared_memory_entries: 2,
            timeout_ms: 1000,
            maximum_output_bytes: 4096,
            enforcement_overruns: overruns(),
        },
        deadline,
        &cancelled,
        &cancelled,
    );
    assert_eq!(
        invalid.unwrap_err().code,
        TrialRelayFailure::ImplementationUnavailable
    );
}

#[test]
fn backend_rejects_runtime_profile_that_would_expose_host_uds() {
    let root = Root::new();
    let mut host_uds_identity = identity();
    host_uds_identity.child_host_uds = "open".into();
    let launcher = root.0.join("launcher");
    fs::write(&launcher, b"trusted launcher").unwrap();
    fs::set_permissions(&launcher, fs::Permissions::from_mode(0o555)).unwrap();
    let launcher_digest = format!("sha256:{:x}", sha2::Sha256::digest(b"trusted launcher"));
    host_uds_identity.trusted_launcher_digest = launcher_digest.clone();
    let result = DockerTrialBackend::new(
        DockerTrialConfiguration {
            identity: host_uds_identity,
            deployment_owner: "deployment_a".into(),
            request_digest: digest('9'),
            attempt_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00001".into(),
            runtime_key: "runsc".into(),
            builder_image_id: digest('4'),
            trusted_launcher_path: launcher,
            trusted_launcher_digest: launcher_digest,
            offline_cache_root: root.child("cache"),
            maximum_candidate_archive_bytes: 1024,
            candidate_uid: 65532,
            candidate_gid: 65532,
            export_uid: 65532,
            export_gid: 65532,
        },
        FakeControl::default(),
    );
    assert_eq!(
        result.err().unwrap().code,
        TrialRelayFailure::InvalidRequest
    );

    for (name, candidate_uid, candidate_gid) in [("uid", 65531, 65532), ("gid", 65532, 65531)] {
        let launcher = root.0.join(format!("launcher-identity-{name}"));
        let launcher_bytes = format!("trusted launcher identity {name}");
        fs::write(&launcher, launcher_bytes.as_bytes()).unwrap();
        fs::set_permissions(&launcher, fs::Permissions::from_mode(0o555)).unwrap();
        let launcher_digest = format!(
            "sha256:{:x}",
            sha2::Sha256::digest(launcher_bytes.as_bytes())
        );
        let mut identity = identity();
        identity.trusted_launcher_digest = launcher_digest.clone();
        let mismatch = DockerTrialBackend::new(
            DockerTrialConfiguration {
                identity,
                deployment_owner: "deployment_a".into(),
                request_digest: digest('9'),
                attempt_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00001".into(),
                runtime_key: "runsc".into(),
                builder_image_id: digest('4'),
                trusted_launcher_path: launcher,
                trusted_launcher_digest: launcher_digest,
                offline_cache_root: root.child(&format!("cache-identity-{name}")),
                maximum_candidate_archive_bytes: 1024,
                candidate_uid,
                candidate_gid,
                export_uid: 65532,
                export_gid: 65532,
            },
            FakeControl::default(),
        );
        assert_eq!(
            mismatch.err().unwrap().code,
            TrialRelayFailure::InvalidRequest
        );
    }
}

pub fn concrete_runtime_builds_and_runs_offline_under_runsc() {
    let state = PathBuf::from(
        std::env::var("WORKSTREAM_TRIAL_QUALIFICATION_ROOT")
            .expect("qualification root must be explicit"),
    );
    let platform_identity = std::env::var("WORKSTREAM_TRIAL_PLATFORM_IDENTITY_SHA256")
        .expect("platform identity must be explicit");
    let trusted_launcher_path = PathBuf::from(
        std::env::var("WORKSTREAM_TRIAL_LAUNCHER_PATH")
            .expect("trusted launcher path must be explicit"),
    );
    let trusted_launcher_digest = std::env::var("WORKSTREAM_TRIAL_LAUNCHER_SHA256")
        .expect("trusted launcher digest must be explicit");
    let run = state.join("trial-scratch/engine-qualification");
    let _ = fs::remove_dir_all(&run);
    fs::create_dir(&run).unwrap();
    fs::set_permissions(&run, fs::Permissions::from_mode(0o700)).unwrap();
    let runtime = run.join("runtime");
    let context = run.join("context");
    let output = run.join("output");
    let workspace = run.join("workspace");
    let deadline_workspace = run.join("deadline-workspace");
    let step_export = run.join("step-export");
    let deadline_export = run.join("deadline-export");
    let source = run.join("source");
    for path in [
        &runtime,
        &context,
        &output,
        &workspace,
        &deadline_workspace,
        &step_export,
        &deadline_export,
        &source,
    ] {
        fs::create_dir(path).unwrap();
        fs::set_permissions(path, fs::Permissions::from_mode(0o700)).unwrap();
    }
    fs::write(
        context.join("Dockerfile"),
        b"FROM alpine@sha256:c64c687cbea9300178b30c95835354e34c4e4febc4badfe27102879de0483b5e\nCOPY payload.txt /opt/qualification/payload.txt\nRUN test \"$(sed -n 's/^CapEff:[[:space:]]*//p' /proc/self/status)\" = 000000000000000b && test \"$(sed -n 's/^CapBnd:[[:space:]]*//p' /proc/self/status)\" = 000000000000000b && printf 'builder-capabilities=000000000000000b\\n' > /opt/qualification/builder-capabilities.txt\nUSER 65532:65532\nENTRYPOINT [\"/bin/sh\"]\n",
    )
    .unwrap();
    fs::write(
        context.join("payload.txt"),
        b"generic offline qualification\n",
    )
    .unwrap();
    fs::write(source.join("visible.txt"), b"visible role\n").unwrap();

    let identity = SandboxBackendIdentity {
        engine_identity_digest:
            "sha256:88a87d5d6d06160d4c144f51f95ec6dd6fe0fc6b02697eb877876683c5b57a91".into(),
        child_runtime: "runsc".into(),
        child_runtime_config_digest:
            "sha256:46429fe1ec5b135d7214c1090c28c75a3175169307ae2981c502015152c3d330".into(),
        child_host_uds: "none".into(),
        platform: "linux/amd64".into(),
        platform_identity_digest: platform_identity,
        builder_image_digest:
            "sha256:b8c743a43e82f0cef9956ea09eae79c2d56b51d359b65a736c171624a9fc95e3".into(),
        trusted_launcher_digest: trusted_launcher_digest.clone(),
        offline_cache_digest:
            "sha256:0d7c48edceae685051d2f60497b0df7f55a0f3f8dd6d29c5e82b9c0cd75a40e1".into(),
        approved_base_digests: vec![
            "sha256:c64c687cbea9300178b30c95835354e34c4e4febc4badfe27102879de0483b5e".into(),
        ],
    };
    let control = DockerRuntimeControl::new(
        PathBuf::from("/usr/local/bin/docker"),
        runtime,
        PathBuf::from("/etc/docker/pilot-daemon.json"),
    )
    .unwrap();
    let backend = DockerTrialBackend::new(
        DockerTrialConfiguration {
            identity: identity.clone(),
            deployment_owner: "qualification".into(),
            request_digest: digest('9'),
            attempt_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00026".into(),
            runtime_key: "runsc".into(),
            builder_image_id:
                "sha256:b8c743a43e82f0cef9956ea09eae79c2d56b51d359b65a736c171624a9fc95e3".into(),
            trusted_launcher_path,
            trusted_launcher_digest,
            offline_cache_root: state.join("cache/content"),
            maximum_candidate_archive_bytes: 64 * 1024 * 1024,
            candidate_uid: 65532,
            candidate_gid: 65532,
            export_uid: 65532,
            export_gid: 65532,
        },
        control,
    )
    .unwrap();
    let owner_id = format!("trial_{}", "a".repeat(32));
    let cancelled = AtomicBool::new(false);
    let deadline = Instant::now() + Duration::from_secs(90);
    let trial_resources = TrialResources {
        cpu_quota_millis: 1000,
        cpu_time_ms: 60_000,
        memory_bytes: 1024 * 1024 * 1024,
        disk_bytes: 64 * 1024 * 1024,
        maximum_entries: 10_000,
        pids: 128,
    };
    let execution = (|| {
        let build = backend.build(
            &SandboxBuildRequest {
                owner_id: owner_id.clone(),
                context_root: context,
                context_relative: ".".into(),
                dockerfile_relative: "Dockerfile".into(),
                output_archive: output.join("candidate.tar"),
                destination: "workstream-trial:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa".into(),
                platform: "linux/amd64".into(),
                resources: trial_resources.clone(),
                remaining_cpu_time_ms: 60_000,
                mutable_disk_bytes: 64 * 1024 * 1024,
                mutable_entries: 10_000,
                launcher_root_bytes: 32 * 1024 * 1024,
                launcher_root_entries: 5000,
                launcher_candidate_bytes: 16 * 1024 * 1024,
                launcher_temporary_bytes: 8 * 1024 * 1024,
                launcher_temporary_entries: 256,
                launcher_shared_memory_bytes: 4096,
                launcher_shared_memory_entries: 2,
                timeout_ms: 60_000,
                maximum_output_bytes: 1024 * 1024,
                enforcement_overruns: SandboxEnforcementOverruns {
                    wall_time_ms: 5_000,
                    cpu_time_ms: 5_000,
                    memory_bytes: 16 * 1024 * 1024,
                    pids: 4,
                    disk_bytes: 8 * 1024 * 1024,
                    entries: 100,
                },
            },
            deadline,
            &cancelled,
            &cancelled,
        );
        eprintln!("qualification build result: {build:?}");
        let build = build?;
        let candidate_metadata = fs::metadata(output.join("candidate.tar")).unwrap();
        assert_eq!(candidate_metadata.uid(), unsafe { libc::geteuid() });
        assert_eq!(candidate_metadata.gid(), unsafe { libc::getegid() });
        assert!(File::open(output.join("candidate.tar")).is_ok());
        assert!(!output.join("status.json").exists());
        let candidate = build
            .observation
            .candidate_image_digest
            .clone()
            .ok_or(SandboxFailure {
                code: TrialRelayFailure::ImplementationUnavailable,
                cleanup_unsettled: false,
            })?;
        assert_archive_excludes(
            &output.join("candidate.tar"),
            &state.join("protected-role/canary.txt"),
            &run.join("archive-inspection"),
        );
        let step = backend.run_step(
            &SandboxStepRequest {
                owner_id: owner_id.clone(),
                slot_id: "generic_offline_probe".into(),
                candidate_image_digest: candidate,
                workspace_root: workspace,
                export_root: step_export,
                visible_roles: vec![ProjectedRoleMount {
                    role: "source".into(),
                    path: source,
                    destination_relative: "source".into(),
                }],
                visible_role_inventory_digests: vec![RoleInventoryDigest {
                    role: "source".into(),
                    digest: digest('c'),
                }],
                command: vec![
                    "/bin/sh".into(),
                    "-ceu".into(),
                    "test -e /proc/gvisor/kernel_is_gvisor; test \"$(id -u)\" = 65532; test \"$(sed -n 's/^CapEff:[[:space:]]*//p' /proc/self/status)\" = 0000000000000000; test \"$(cat /opt/qualification/builder-capabilities.txt)\" = builder-capabilities=000000000000000b; test ! -e /var/run/docker.sock; test ! -e /work/execution.sock; test ! -e /work/model.sock; test ! -e /workspace/protected; test -f /workspace/source/visible.txt; if touch /workspace/source/sibling 2>/dev/null; then exit 72; fi; if mv /workspace/source /workspace/renamed 2>/dev/null; then exit 73; fi; if wget -T 1 -qO- http://1.1.1.1 >/dev/null 2>&1; then exit 71; fi; sleep 1; printf 'qualification=pass\\n'".into(),
                ],
                working_directory: ".".into(),
                resources: trial_resources,
                remaining_cpu_time_ms: 60_000,
                mutable_disk_bytes: 64 * 1024 * 1024,
                mutable_entries: 10_000,
                launcher_root_bytes: 1024 * 1024,
                launcher_root_entries: 512,
                launcher_workspace_bytes: 24 * 1024 * 1024,
                launcher_workspace_entries: 4000,
                launcher_temporary_bytes: 8 * 1024 * 1024,
                launcher_temporary_entries: 256,
                launcher_shared_memory_bytes: 4096,
                launcher_shared_memory_entries: 2,
                timeout_ms: 10_000,
                maximum_output_bytes: 64 * 1024,
                enforcement_overruns: SandboxEnforcementOverruns {
                    wall_time_ms: 2_000,
                    cpu_time_ms: 1_000,
                    memory_bytes: 16 * 1024 * 1024,
                    pids: 4,
                    disk_bytes: 1024 * 1024,
                    entries: 16,
                },
            },
            1,
            deadline,
            &cancelled,
            &cancelled,
        );
        eprintln!("qualification step result: {step:?}");
        let step = step?;
        assert!(!run.join("step-export").exists());
        let workspace_metadata = fs::metadata(run.join("workspace")).unwrap();
        assert_eq!(workspace_metadata.uid(), unsafe { libc::geteuid() });
        assert_eq!(workspace_metadata.gid(), unsafe { libc::getegid() });
        assert!(!run.join("workspace/source").exists());
        let deadline_step = backend.run_step(
            &SandboxStepRequest {
                owner_id: owner_id.clone(),
                slot_id: "generic_deadline_probe".into(),
                candidate_image_digest: build.observation.candidate_image_digest.clone().unwrap(),
                workspace_root: deadline_workspace,
                export_root: deadline_export,
                visible_roles: vec![ProjectedRoleMount {
                    role: "source".into(),
                    path: run.join("source"),
                    destination_relative: "source".into(),
                }],
                visible_role_inventory_digests: vec![RoleInventoryDigest {
                    role: "source".into(),
                    digest: digest('c'),
                }],
                command: vec!["/bin/sh".into(), "-ceu".into(), "sleep 30".into()],
                working_directory: ".".into(),
                resources: TrialResources {
                    cpu_quota_millis: 1000,
                    cpu_time_ms: 60_000,
                    memory_bytes: 1024 * 1024 * 1024,
                    disk_bytes: 64 * 1024 * 1024,
                    maximum_entries: 10_000,
                    pids: 128,
                },
                remaining_cpu_time_ms: 60_000,
                mutable_disk_bytes: 64 * 1024 * 1024,
                mutable_entries: 10_000,
                launcher_root_bytes: 1024 * 1024,
                launcher_root_entries: 512,
                launcher_workspace_bytes: 24 * 1024 * 1024,
                launcher_workspace_entries: 4000,
                launcher_temporary_bytes: 8 * 1024 * 1024,
                launcher_temporary_entries: 256,
                launcher_shared_memory_bytes: 4096,
                launcher_shared_memory_entries: 2,
                timeout_ms: 4_000,
                maximum_output_bytes: 64 * 1024,
                enforcement_overruns: SandboxEnforcementOverruns {
                    wall_time_ms: 5_000,
                    cpu_time_ms: 1_000,
                    memory_bytes: 16 * 1024 * 1024,
                    pids: 4,
                    disk_bytes: 1024 * 1024,
                    entries: 16,
                },
            },
            2,
            deadline,
            &cancelled,
            &cancelled,
        );
        eprintln!("qualification deadline result: {deadline_step:?}");
        let deadline_step = deadline_step?;
        assert!(!run.join("deadline-export").exists());
        Ok::<_, SandboxFailure>((build, step, deadline_step))
    })();
    let cleanup = backend.cleanup(&owner_id, Instant::now() + Duration::from_secs(20));
    let (build, step, deadline_step) = execution.unwrap();
    cleanup.unwrap();
    let recovery_owner = RuntimeOwner {
        deployment_owner: "qualification".into(),
        request_digest: digest('8'),
        attempt_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00027".into(),
        trial_owner_id: format!("trial_{}", "b".repeat(32)),
    };
    backend
        .control
        .create_owned_container(
            OwnedContainerCreate {
                owner: recovery_owner,
                name: "ws-trial-restart-recovery".into(),
                arguments: vec![
                    "--runtime".into(),
                    "runsc".into(),
                    "--network".into(),
                    "none".into(),
                    "--cap-drop".into(),
                    "ALL".into(),
                    "--security-opt".into(),
                    "no-new-privileges".into(),
                    "--pids-limit".into(),
                    "16".into(),
                    "--memory".into(),
                    (64 * 1024 * 1024).to_string(),
                    "--cpus".into(),
                    "0.5".into(),
                    "sha256:b8c743a43e82f0cef9956ea09eae79c2d56b51d359b65a736c171624a9fc95e3"
                        .into(),
                    "--version".into(),
                ],
                mounts: vec![OwnedBindMount {
                    source: run.join("context"),
                    destination: "/workstream-bootstrap/input/context".into(),
                    readonly: true,
                    class: OwnedMountClass::LauncherContext,
                }],
            },
            Instant::now() + Duration::from_secs(10),
            &cancelled,
            &cancelled,
        )
        .unwrap();
    drop(backend);
    let recovered = DockerRuntimeControl::new(
        PathBuf::from("/usr/local/bin/docker"),
        run.join("runtime"),
        PathBuf::from("/etc/docker/pilot-daemon.json"),
    )
    .unwrap();
    recovered
        .recover_deployment("qualification", Instant::now() + Duration::from_secs(20))
        .unwrap();
    let invalid_configuration = run.join("invalid-daemon.json");
    let mut invalid_configuration_bytes = fs::read("/etc/docker/pilot-daemon.json").unwrap();
    invalid_configuration_bytes.push(b'\n');
    fs::write(&invalid_configuration, invalid_configuration_bytes).unwrap();
    let invalid_control = DockerRuntimeControl::new(
        PathBuf::from("/usr/local/bin/docker"),
        run.join("runtime"),
        invalid_configuration,
    )
    .unwrap();
    assert_eq!(
        invalid_control.require_image(
            "sha256:b8c743a43e82f0cef9956ea09eae79c2d56b51d359b65a736c171624a9fc95e3",
            &identity,
            "runsc",
            Instant::now() + Duration::from_secs(10),
        ),
        Err(RuntimeControlFailure::ImageUnavailable)
    );
    let cache_root = run.join("cache-negative/content");
    fs::create_dir_all(&cache_root).unwrap();
    fs::write(cache_root.join("base"), b"sealed").unwrap();
    let base_digest = sha2::Sha256::digest(b"sealed");
    let manifest = format!("{base_digest:x}  ./base\n");
    fs::write(run.join("cache-negative/cache.sha256"), manifest.as_bytes()).unwrap();
    let manifest_digest = format!("sha256:{:x}", sha2::Sha256::digest(manifest.as_bytes()));
    recovered
        .require_offline_cache(&cache_root, &manifest_digest)
        .unwrap();
    fs::write(cache_root.join("base"), b"mutated").unwrap();
    assert_eq!(
        recovered.require_offline_cache(&cache_root, &manifest_digest),
        Err(RuntimeControlFailure::CacheUnavailable)
    );
    assert_eq!(build.observation.outcome, TrialOperationOutcome::Succeeded);
    assert_eq!(step.observation.outcome, TrialOperationOutcome::Succeeded);
    assert_eq!(step.observation.stdout, "qualification=pass\n");
    assert_eq!(
        deadline_step.observation.outcome,
        TrialOperationOutcome::DeadlineExceeded
    );
    let evidence = serde_json::json!({
        "schema_version": "workstream.trial_docker_qualification.v1",
        "builder_image": build.observation.candidate_image_digest,
        "builder_archive": build.observation.candidate_archive_digest,
        "build_elapsed_ms": build.observation.elapsed_ms,
        "build_cpu_time_ms": build.observation.cpu_time_ms,
        "build_peak_memory_bytes": build.observation.peak_memory_bytes,
        "build_peak_pids": build.observation.peak_pids,
        "step_elapsed_ms": step.observation.elapsed_ms,
        "step_cpu_time_ms": step.observation.cpu_time_ms,
        "step_peak_memory_bytes": step.observation.peak_memory_bytes,
        "step_peak_pids": step.observation.peak_pids,
        "step_stdout_sha256": step.observation.stdout_sha256,
        "deadline_elapsed_ms": deadline_step.observation.elapsed_ms,
        "deadline_cpu_time_ms": deadline_step.observation.cpu_time_ms,
        "deadline_outcome": "deadline_exceeded",
        "measurement_method": step.observation.measurement_method,
        "protected_layer_canary_absent": true,
        "cleanup_confirmed": true,
        "restart_recovery_confirmed": true,
        "runtime_configuration_substitution_rejected": true,
        "offline_cache_mutation_rejected": true,
    });
    fs::create_dir_all(state.join("results")).unwrap();
    fs::write(
        state.join("results/trial-docker-qualification.json"),
        serde_json::to_vec_pretty(&evidence).unwrap(),
    )
    .unwrap();
}

fn assert_archive_excludes(archive: &Path, canary_path: &Path, inspection: &Path) {
    let canary = fs::read(canary_path).unwrap();
    fs::create_dir(inspection).unwrap();
    let status = Command::new("/bin/tar")
        .args(["-xf"])
        .arg(archive)
        .args(["-C"])
        .arg(inspection)
        .status()
        .unwrap();
    assert!(status.success());
    let mut layers = fs::read_dir(inspection)
        .unwrap()
        .map(|entry| entry.unwrap().path())
        .filter(|path| path.extension().is_some_and(|value| value == "gz"))
        .collect::<Vec<_>>();
    layers.sort();
    assert!(!layers.is_empty());
    for (index, layer) in layers.iter().enumerate() {
        let root = inspection.join(format!("layer-{index}"));
        fs::create_dir(&root).unwrap();
        let status = Command::new("/bin/tar")
            .args(["-xzf"])
            .arg(layer)
            .args(["-C"])
            .arg(&root)
            .status()
            .unwrap();
        assert!(status.success());
        assert_tree_excludes(&root, &canary);
    }
}

fn assert_tree_excludes(root: &Path, needle: &[u8]) {
    for entry in fs::read_dir(root).unwrap() {
        let path = entry.unwrap().path();
        let metadata = fs::symlink_metadata(&path).unwrap();
        if metadata.file_type().is_dir() {
            assert_tree_excludes(&path, needle);
        } else if metadata.file_type().is_file() {
            let bytes = fs::read(path).unwrap();
            assert!(!bytes.windows(needle.len()).any(|window| window == needle));
        }
    }
}
