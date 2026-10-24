use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::fs;
use std::io::{Read, Write};
use std::os::unix::fs::{MetadataExt, PermissionsExt};
use std::os::unix::net::UnixStream;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

#[allow(dead_code)]
#[path = "../src/trial_relay.rs"]
mod trial_relay;
use trial_relay::*;

static TEST_SEQUENCE: AtomicUsize = AtomicUsize::new(0);

#[test]
fn profile_rejects_receipts_larger_than_durable_custody_limit() {
    let mut selected = profile();
    selected.maximum_receipt_bytes = 1024 * 1024 + 1;
    assert!(!valid_profile(&selected));
}

#[test]
fn profile_requires_room_for_trusted_pid_one_and_one_child() {
    let mut selected = profile();
    selected.maximum_pids = 1;
    assert!(!valid_profile(&selected));
}

struct TestRoot(PathBuf);

impl TestRoot {
    fn new() -> Self {
        let path = std::env::temp_dir().join(format!(
            "workstream-trial-relay-test-{}-{}",
            std::process::id(),
            TEST_SEQUENCE.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&path).unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o700)).unwrap();
        Self(path)
    }

    fn child(&self, name: &str) -> PathBuf {
        let path = self.0.join(name);
        fs::create_dir(&path).unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o700)).unwrap();
        path
    }
}

impl Drop for TestRoot {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

#[derive(Default)]
struct FakePublisher(Mutex<Vec<Value>>);

impl TrialReceiptPublisher for FakePublisher {
    fn reserve_completed(
        &self,
        subject: TrialEvidenceSubject,
    ) -> Result<TrialReceiptReservation, TrialReceiptPublishFailure> {
        assert_eq!(subject.slot_index, 0);
        Ok(TrialReceiptReservation::Fresh {
            trial_evidence_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00100".into(),
        })
    }

    fn publish_completed(
        &self,
        trial_evidence_id: &str,
        receipt: CanonicalTrialReceipt,
    ) -> Result<PublishedTrialReceipt, TrialReceiptPublishFailure> {
        assert_eq!(trial_evidence_id, "018f6f49-66b8-7d2a-bf4d-0e2eeaa00100");
        let parsed: Value = serde_json::from_slice(&receipt.canonical_bytes).unwrap();
        assert_eq!(parsed, serde_json::to_value(&receipt.facts).unwrap());
        assert_eq!(receipt.byte_count, receipt.canonical_bytes.len());
        assert_eq!(
            receipt.receipt_digest,
            text_digest(&String::from_utf8(receipt.canonical_bytes).unwrap())
        );
        self.0.lock().unwrap().push(parsed);
        Ok(PublishedTrialReceipt {
            receipt_handle: format!("trial_receipt_{}", "a".repeat(32)),
            custody: TrialReceiptCustodyAck {
                binding_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00101".into(),
                content_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00102".into(),
                put_attempt_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00103".into(),
                verification_receipt_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00104".into(),
                content_sha256: receipt.receipt_digest,
                byte_count: receipt.byte_count,
            },
        })
    }
}

struct FakeEngine {
    calls: AtomicUsize,
    cleanup_confirmed: bool,
}

struct RetainedPublisher(Mutex<Option<CanonicalTrialReceipt>>);

impl TrialReceiptPublisher for RetainedPublisher {
    fn reserve_completed(
        &self,
        _subject: TrialEvidenceSubject,
    ) -> Result<TrialReceiptReservation, TrialReceiptPublishFailure> {
        let receipt = self.0.lock().unwrap().take().unwrap();
        Ok(TrialReceiptReservation::Retained {
            trial_evidence_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00100".into(),
            published: PublishedTrialReceipt {
                receipt_handle: format!("trial_receipt_{}", "b".repeat(32)),
                custody: TrialReceiptCustodyAck {
                    binding_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00101".into(),
                    content_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00102".into(),
                    put_attempt_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00103".into(),
                    verification_receipt_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00104".into(),
                    content_sha256: receipt.receipt_digest.clone(),
                    byte_count: receipt.byte_count,
                },
            },
            receipt,
        })
    }

    fn publish_completed(
        &self,
        _trial_evidence_id: &str,
        _receipt: CanonicalTrialReceipt,
    ) -> Result<PublishedTrialReceipt, TrialReceiptPublishFailure> {
        panic!("retained receipt must not be republished")
    }
}

impl TrialEngine for FakeEngine {
    fn execute(
        &self,
        _context: &TrialEngineContext,
        plan: &TrialPlan,
        _deadline: Instant,
        invocation_cancelled: &AtomicBool,
        relay_cancelled: &AtomicBool,
    ) -> Result<TrialExecution, TrialEngineFailure> {
        assert!(!invocation_cancelled.load(Ordering::Acquire));
        assert!(!relay_cancelled.load(Ordering::Acquire));
        self.calls.fetch_add(1, Ordering::Relaxed);
        let mut result = execution(self.cleanup_confirmed);
        let template = result.steps[0].clone();
        result.steps = plan
            .steps
            .iter()
            .enumerate()
            .map(|(index, step)| TrialStepObservation {
                slot_id: step.slot_id.clone(),
                operation_order: (index + 1) as u32,
                ..template.clone()
            })
            .collect();
        Ok(result)
    }
}

fn digest(character: char) -> String {
    format!("sha256:{}", character.to_string().repeat(64))
}

fn text_digest(value: &str) -> String {
    format!("sha256:{:x}", Sha256::digest(value.as_bytes()))
}

fn identity() -> TrialRequestIdentity {
    TrialRequestIdentity {
        request_digest: digest('1'),
        material_binding_digest: digest('2'),
        input_digest: digest('a'),
        materials_digest: digest('b'),
        project_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00001".into(),
        task_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00002".into(),
        assignment_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00003".into(),
        submission_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00004".into(),
        submission_version: 2,
        requirement_id: "check_a".into(),
        registry_entry_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00005".into(),
        registry_entry_digest: digest('3'),
        checker_image_digest: digest('4'),
        configuration_sha256: digest('5'),
        evaluation_request_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00006".into(),
        evaluation_generation: 3,
        checker_run_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00007".into(),
        attempt_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00008".into(),
        result_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00009".into(),
        worker_lease_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa0000a".into(),
        worker_lease_generation: 4,
        worker_lease_expires_at: "2026-10-23T12:00:00Z".into(),
    }
}

fn profile() -> TrialProfile {
    let identity = identity();
    TrialProfile {
        profile_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa0000b".into(),
        profile_version: 1,
        profile_digest: digest('6'),
        projection_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00010".into(),
        projection_version: 1,
        projection_digest: digest('7'),
        trial_kind: "generic_build_and_run".into(),
        registry_entry_id: identity.registry_entry_id,
        registry_entry_digest: identity.registry_entry_digest,
        checker_image_digest: identity.checker_image_digest,
        configuration_sha256: identity.configuration_sha256,
        engine_identity_digest: digest('7'),
        outer_runtime_config_digest: digest('6'),
        child_runtime: "runsc".into(),
        child_runtime_config_digest: digest('7'),
        child_host_uds: "none".into(),
        platform: "linux/amd64".into(),
        platform_identity_digest: digest('8'),
        builder_image_digest: digest('9'),
        trusted_launcher_digest: digest('c'),
        offline_cache_digest: digest('a'),
        approved_base_digests: vec![digest('b')],
        source_material_roles: vec!["submission_archive".into()],
        material_projections: vec![
            TrialMaterialProjectionProfile {
                role: "source".into(),
                source_role: "submission_archive".into(),
                projection_kind: "build_context".into(),
                source_relative: ".".into(),
                destination_relative: ".".into(),
                exclusions: Vec::new(),
            },
            TrialMaterialProjectionProfile {
                role: "checks".into(),
                source_role: "submission_archive".into(),
                projection_kind: "state_overlay".into(),
                source_relative: "checks".into(),
                destination_relative: "checks".into(),
                exclusions: Vec::new(),
            },
        ],
        build_context_roles: vec!["source".into()],
        allowed_material_roles: vec!["source".into(), "checks".into()],
        slot_templates: vec![TrialSlotProfile {
            slot_kind: "generic_run".into(),
            minimum_occurrences: 1,
            maximum_occurrences: 1,
            seed_roles: Vec::new(),
            visible_roles: vec!["checks".into()],
            fresh_workspace: true,
            retain_state_after: vec!["succeeded".into()],
        }],
        maximum_frame_bytes: 32 * 1024,
        maximum_response_bytes: 4 * 1024,
        maximum_steps: 2,
        maximum_total_timeout_ms: 5_000,
        maximum_build_timeout_ms: 2_000,
        maximum_step_timeout_ms: 1_000,
        maximum_step_output_bytes: 4_096,
        maximum_observation_bytes: 32 * 1024,
        maximum_receipt_bytes: 64 * 1024,
        maximum_cpu_quota_millis: 2_000,
        maximum_cpu_time_ms: 10_000,
        maximum_wall_time_overrun_ms: 100,
        maximum_cpu_time_overrun_ms: 250,
        maximum_memory_bytes: 128 * 1024 * 1024,
        maximum_memory_overrun_bytes: 1024 * 1024,
        maximum_disk_bytes: 64 * 1024 * 1024,
        maximum_disk_overrun_bytes: 1024 * 1024,
        maximum_entries: 1_000,
        maximum_entries_overrun: 16,
        maximum_pids: 32,
        maximum_pids_overrun: 2,
    }
}

fn plan() -> Value {
    json!({
        "schema_version": "workstream.checker_trial_plan.v1",
        "environment": {"dockerfile": "Containerfile", "context": ".", "platform": "linux/amd64"},
        "resources": {"cpu_quota_millis": 1000, "cpu_time_ms": 5000, "memory_bytes": 67_108_864, "disk_bytes": 33_554_432, "maximum_entries": 500, "pids": 16},
        "build_timeout_ms": 1500,
        "steps": [{
            "slot_id": "slot_a", "slot_kind": "generic_run", "operation": "run", "state_source": "fresh",
            "visible_roles": ["checks"],
            "command": ["/candidate/bin/check", "--case", "a"],
            "working_directory": ".", "timeout_ms": 800
        }]
    })
}

fn execution(cleanup_confirmed: bool) -> TrialExecution {
    let profile = profile();
    TrialExecution {
        platform_identity_digest: profile.platform_identity_digest,
        builder_image_digest: profile.builder_image_digest,
        trusted_launcher_digest: profile.trusted_launcher_digest,
        offline_cache_digest: profile.offline_cache_digest,
        base_image_digests: profile.approved_base_digests,
        material_inventory_digests: vec![
            RoleInventoryDigest {
                role: "source".into(),
                digest: digest('c'),
            },
            RoleInventoryDigest {
                role: "checks".into(),
                digest: digest('d'),
            },
        ],
        build: TrialBuildObservation {
            outcome: TrialOperationOutcome::Succeeded,
            exit_code: Some(0),
            signal: None,
            stdout: "built\n".into(),
            stdout_sha256: text_digest("built\n"),
            stderr: String::new(),
            stderr_sha256: text_digest(""),
            candidate_image_digest: Some(digest('e')),
            candidate_archive_digest: Some(digest('f')),
            export_outcome: TrialExportOutcome::Exported,
            elapsed_ms: 100,
            cpu_time_ms: 50,
            peak_memory_bytes: 1024,
            peak_pids: 2,
            written_bytes: 2048,
            written_entries: 4,
            measurement_method: "cgroup_v2".into(),
        },
        steps: vec![TrialStepObservation {
            slot_id: "slot_a".into(),
            operation_order: 1,
            workspace_identity: "workspace_a".into(),
            visible_role_inventory_digests: vec![RoleInventoryDigest {
                role: "checks".into(),
                digest: digest('d'),
            }],
            outcome: TrialOperationOutcome::Succeeded,
            exit_code: Some(0),
            signal: None,
            stdout: "ok\n".into(),
            stdout_sha256: text_digest("ok\n"),
            stderr: String::new(),
            stderr_sha256: text_digest(""),
            workspace_before_sha256: digest('1'),
            workspace_after_sha256: digest('2'),
            export_outcome: TrialExportOutcome::Exported,
            elapsed_ms: 20,
            cpu_time_ms: 10,
            peak_memory_bytes: 512,
            peak_pids: 1,
            written_bytes: 64,
            written_entries: 1,
            measurement_method: "cgroup_v2".into(),
        }],
        cleanup_confirmed,
    }
}

fn build_failure_execution() -> TrialExecution {
    let mut value = execution(true);
    value.build.outcome = TrialOperationOutcome::ExitNonzero;
    value.build.exit_code = Some(2);
    value.build.stdout.clear();
    value.build.stdout_sha256 = text_digest("");
    value.build.stderr = "compile error\n".into();
    value.build.stderr_sha256 = text_digest("compile error\n");
    value.build.candidate_image_digest = None;
    value.build.candidate_archive_digest = None;
    value.build.export_outcome = TrialExportOutcome::NotStarted;
    let step = &mut value.steps[0];
    step.outcome = TrialOperationOutcome::DependencySkipped;
    step.exit_code = None;
    step.signal = None;
    step.stdout.clear();
    step.stdout_sha256 = text_digest("");
    step.stderr.clear();
    step.stderr_sha256 = text_digest("");
    step.elapsed_ms = 0;
    step.cpu_time_ms = 0;
    step.peak_memory_bytes = 0;
    step.peak_pids = 0;
    step.written_bytes = 0;
    step.written_entries = 0;
    step.export_outcome = TrialExportOutcome::NotStarted;
    value
}

struct BuildFailureEngine;

impl TrialEngine for BuildFailureEngine {
    fn execute(
        &self,
        _context: &TrialEngineContext,
        _plan: &TrialPlan,
        _deadline: Instant,
        _invocation_cancelled: &AtomicBool,
        _relay_cancelled: &AtomicBool,
    ) -> Result<TrialExecution, TrialEngineFailure> {
        Ok(build_failure_execution())
    }
}

struct ObservedEngine(Mutex<Option<TrialExecution>>);

impl TrialEngine for ObservedEngine {
    fn execute(
        &self,
        _context: &TrialEngineContext,
        _plan: &TrialPlan,
        _deadline: Instant,
        _invocation_cancelled: &AtomicBool,
        _relay_cancelled: &AtomicBool,
    ) -> Result<TrialExecution, TrialEngineFailure> {
        Ok(self.0.lock().unwrap().take().unwrap())
    }
}

fn assert_observed_limit_is_published(observation: TrialExecution, expected: &str) {
    let root = TestRoot::new();
    let relay_root = root.child("relay");
    let material_root = root.child("material");
    let scratch_root = root.child("scratch");
    let metadata = fs::metadata(&root.0).unwrap();
    let publisher = Arc::new(FakePublisher::default());
    let relay = TrialRelay::start(
        &relay_root,
        &material_root,
        &scratch_root,
        &identity(),
        &profile(),
        publisher.clone(),
        Arc::new(ObservedEngine(Mutex::new(Some(observation)))),
        metadata.uid(),
        metadata.gid(),
        Instant::now() + Duration::from_secs(2),
        Arc::new(AtomicBool::new(false)),
    )
    .unwrap();
    let response = exchange(relay.socket_path(), &request(plan()));
    assert_eq!(response["outcome"], "completed");
    assert_eq!(
        publisher.0.lock().unwrap()[0]["execution"]["steps"][0]["outcome"],
        expected
    );
    assert_eq!(relay.finish().failure, None);
}

struct StartedRelay {
    _root: TestRoot,
    relay: TrialRelay,
    publisher: Arc<FakePublisher>,
    engine: Arc<FakeEngine>,
}

fn start(cleanup_confirmed: bool) -> StartedRelay {
    start_with_profile(cleanup_confirmed, profile())
}

fn start_with_profile(cleanup_confirmed: bool, profile: TrialProfile) -> StartedRelay {
    let root = TestRoot::new();
    let relay_root = root.child("relay");
    let material_root = root.child("material");
    let scratch_root = root.child("scratch");
    let metadata = fs::metadata(&root.0).unwrap();
    let publisher = Arc::new(FakePublisher::default());
    let engine = Arc::new(FakeEngine {
        calls: AtomicUsize::new(0),
        cleanup_confirmed,
    });
    let relay = TrialRelay::start(
        &relay_root,
        &material_root,
        &scratch_root,
        &identity(),
        &profile,
        publisher.clone(),
        engine.clone(),
        metadata.uid(),
        metadata.gid(),
        Instant::now() + Duration::from_secs(5),
        Arc::new(AtomicBool::new(false)),
    )
    .unwrap();
    StartedRelay {
        _root: root,
        relay,
        publisher,
        engine,
    }
}

fn exchange(path: &Path, value: &Value) -> Value {
    let mut stream = UnixStream::connect(path).unwrap();
    let bytes = serde_json::to_vec(value).unwrap();
    stream
        .write_all(&(bytes.len() as u32).to_be_bytes())
        .unwrap();
    stream.write_all(&bytes).unwrap();
    let mut length = [0_u8; 4];
    stream.read_exact(&mut length).unwrap();
    let mut response = vec![0_u8; u32::from_be_bytes(length) as usize];
    stream.read_exact(&mut response).unwrap();
    serde_json::from_slice(&response).unwrap()
}

fn request(plan: Value) -> Value {
    json!({"protocol_version": "workstream.checker_trial.v1", "operation": "execute_plan", "plan": plan})
}

fn assert_plan_rejected(mutator: impl FnOnce(&mut Value)) {
    let started = start(true);
    let mut bad_plan = plan();
    mutator(&mut bad_plan);
    let response = exchange(started.relay.socket_path(), &request(bad_plan));
    assert_eq!(response["outcome"], "unavailable");
    assert_eq!(response["failure_code"], "invalid_request");
    assert_eq!(started.engine.calls.load(Ordering::Relaxed), 0);
    assert!(started.publisher.0.lock().unwrap().is_empty());
    let finish = started.relay.finish();
    assert_eq!(finish.failure, Some(TrialRelayFailure::InvalidRequest));
}

#[test]
fn completed_plan_publishes_runner_facts_only_after_confirmed_cleanup() {
    let started = start(true);
    assert!(started
        .relay
        .mount_spec()
        .contains("dst=/work/execution.sock"));
    assert!(started.relay.mount_spec().ends_with(",readonly"));
    let response = exchange(started.relay.socket_path(), &request(plan()));
    assert_eq!(response["outcome"], "completed");
    assert!(response.get("plan").is_none());
    assert_eq!(
        response["observations"]["schema_version"],
        "workstream.checker_trial_observations.v1"
    );
    assert_eq!(response["observations"]["terminal_state"], "completed_work");
    assert_eq!(
        response["observations"]["build"]["export_outcome"],
        "exported"
    );
    assert_eq!(response["observations"]["steps"][0]["slot_id"], "slot_a");
    assert_eq!(response["observations"]["steps"][0]["outcome"], "succeeded");
    assert_eq!(
        response["observations"]["steps"][0]["export_outcome"],
        "exported"
    );
    assert_eq!(response["observations"]["steps"][0]["stdout_byte_count"], 3);
    assert_eq!(
        response["observations"]["steps"][0]["stdout_sha256"],
        text_digest("ok\n")
    );
    assert!(response["observations"]["steps"][0].get("stdout").is_none());
    let publications = started.publisher.0.lock().unwrap();
    assert_eq!(
        response["observations"]["observation_digest"],
        publications[0]["observation_digest"]
    );
    assert_eq!(started.engine.calls.load(Ordering::Relaxed), 1);
    assert_eq!(publications.len(), 1);
    assert_eq!(publications[0]["request_identity_digest"], digest('1'));
    assert_eq!(publications[0]["trial_kind"], "generic_build_and_run");
    assert_eq!(publications[0]["cleanup_confirmed"], true);
    assert!(publications[0].get("verdict").is_none());
    drop(publications);
    let finish = started.relay.finish();
    assert_eq!(finish.failure, None);
    assert!(finish.plan_started && finish.plan_completed && !finish.cleanup_unsettled);
}

#[test]
fn host_runtime_fields_and_profile_slot_substitution_are_rejected_before_engine() {
    assert_plan_rejected(|value| value["network_mode"] = json!("host"));
    assert_plan_rejected(|value| value["steps"][0]["slot_kind"] = json!("foreign_kind"));
    assert_plan_rejected(|value| value["steps"][0]["visible_roles"] = json!(["source"]));
    assert_plan_rejected(|value| value["steps"][0]["working_directory"] = json!("../host"));
    assert_plan_rejected(|value| value["resources"]["pids"] = json!(33));
    assert_plan_rejected(|value| value["resources"]["pids"] = json!(1));
    assert_plan_rejected(|value| value["environment"]["platform"] = json!("linux/arm64"));
    assert_plan_rejected(|value| {
        let trailing = value["steps"][0].clone();
        value["steps"].as_array_mut().unwrap().push(trailing);
    });
}

#[test]
fn two_pid_whole_container_boundary_reaches_the_engine() {
    let started = start(true);
    let mut bounded = plan();
    bounded["resources"]["pids"] = json!(2);
    let response = exchange(started.relay.socket_path(), &request(bounded));
    assert_eq!(response["outcome"], "completed");
    assert_eq!(started.engine.calls.load(Ordering::Relaxed), 1);
    assert_eq!(started.relay.finish().failure, None);
}

#[test]
fn state_source_must_reference_an_earlier_completed_slot() {
    let mut selected = profile();
    selected.slot_templates[0].fresh_workspace = false;
    let started = start_with_profile(true, selected);
    let mut self_referential = plan();
    self_referential["steps"][0]["state_source"] = json!("slot_a");
    let response = exchange(started.relay.socket_path(), &request(self_referential));
    assert_eq!(response["outcome"], "unavailable");
    assert_eq!(response["failure_code"], "invalid_request");
    assert_eq!(started.engine.calls.load(Ordering::Relaxed), 0);
    assert!(started.publisher.0.lock().unwrap().is_empty());
    assert_eq!(
        started.relay.finish().failure,
        Some(TrialRelayFailure::InvalidRequest)
    );
}

#[test]
fn profile_whole_run_timeout_rejects_aggregate_plan_before_engine() {
    let mut selected = profile();
    selected.maximum_total_timeout_ms = 2_000;
    let started = start_with_profile(true, selected);
    let response = exchange(started.relay.socket_path(), &request(plan()));
    assert_eq!(response["outcome"], "unavailable");
    assert_eq!(response["failure_code"], "invalid_request");
    assert_eq!(started.engine.calls.load(Ordering::Relaxed), 0);
    assert!(started.publisher.0.lock().unwrap().is_empty());
    assert_eq!(
        started.relay.finish().failure,
        Some(TrialRelayFailure::InvalidRequest)
    );
}

#[test]
fn ordered_slot_template_occurrences_are_finite_and_required() {
    let mut selected = profile();
    selected.maximum_steps = 3;
    selected.slot_templates = vec![
        TrialSlotProfile {
            slot_kind: "documented_command".into(),
            minimum_occurrences: 1,
            maximum_occurrences: 2,
            seed_roles: Vec::new(),
            visible_roles: vec!["checks".into()],
            fresh_workspace: true,
            retain_state_after: vec!["succeeded".into()],
        },
        TrialSlotProfile {
            slot_kind: "final_verification".into(),
            minimum_occurrences: 1,
            maximum_occurrences: 1,
            seed_roles: Vec::new(),
            visible_roles: vec!["checks".into()],
            fresh_workspace: true,
            retain_state_after: vec!["succeeded".into()],
        },
    ];
    let started = start_with_profile(true, selected.clone());
    let mut accepted = plan();
    accepted["steps"][0]["slot_kind"] = json!("documented_command");
    let mut final_step = accepted["steps"][0].clone();
    final_step["slot_id"] = json!("final_a");
    final_step["slot_kind"] = json!("final_verification");
    accepted["steps"].as_array_mut().unwrap().push(final_step);
    let response = exchange(started.relay.socket_path(), &request(accepted));
    assert_eq!(response["outcome"], "completed");
    assert_eq!(started.engine.calls.load(Ordering::Relaxed), 1);
    assert_eq!(started.relay.finish().failure, None);

    let started = start_with_profile(true, selected.clone());
    let mut missing = plan();
    missing["steps"][0]["slot_kind"] = json!("documented_command");
    let response = exchange(started.relay.socket_path(), &request(missing));
    assert_eq!(response["failure_code"], "invalid_request");
    assert_eq!(started.engine.calls.load(Ordering::Relaxed), 0);
    started.relay.finish();

    let started = start_with_profile(true, selected);
    let mut reversed = plan();
    reversed["steps"][0]["slot_kind"] = json!("final_verification");
    let mut trailing = reversed["steps"][0].clone();
    trailing["slot_id"] = json!("documented_a");
    trailing["slot_kind"] = json!("documented_command");
    reversed["steps"].as_array_mut().unwrap().push(trailing);
    let response = exchange(started.relay.socket_path(), &request(reversed));
    assert_eq!(response["failure_code"], "invalid_request");
    assert_eq!(started.engine.calls.load(Ordering::Relaxed), 0);
    started.relay.finish();
}

#[test]
fn cleanup_ambiguity_never_publishes_receipt_or_work_verdict() {
    let started = start(false);
    let response = exchange(started.relay.socket_path(), &request(plan()));
    assert_eq!(response["outcome"], "unavailable");
    assert_eq!(response["failure_code"], "cleanup_unsettled");
    assert!(response["receipt_handle"].is_null());
    assert!(started.publisher.0.lock().unwrap().is_empty());
    let finish = started.relay.finish();
    assert_eq!(finish.failure, Some(TrialRelayFailure::CleanupUnsettled));
    assert!(finish.cleanup_unsettled && finish.plan_started && !finish.plan_completed);
}

#[test]
fn mismatched_request_bound_profile_is_rejected_before_socket_creation() {
    let root = TestRoot::new();
    let relay_root = root.child("relay");
    let material_root = root.child("material");
    let scratch_root = root.child("scratch");
    let metadata = fs::metadata(&root.0).unwrap();
    let mut foreign = profile();
    foreign.configuration_sha256 = digest('0');
    let result = TrialRelay::start(
        &relay_root,
        &material_root,
        &scratch_root,
        &identity(),
        &foreign,
        Arc::new(FakePublisher::default()),
        Arc::new(FakeEngine {
            calls: AtomicUsize::new(0),
            cleanup_confirmed: true,
        }),
        metadata.uid(),
        metadata.gid(),
        Instant::now() + Duration::from_secs(1),
        Arc::new(AtomicBool::new(false)),
    );
    let failure = result.err().expect("mismatched profile must fail");
    assert_eq!(failure.code, TrialRelayFailure::InvalidRequest);
    assert!(!failure.cleanup_unsettled);
    assert!(fs::read_dir(relay_root).unwrap().next().is_none());
}

#[test]
fn invocation_cancellation_closes_waiting_relay_without_receipt() {
    let root = TestRoot::new();
    let relay_root = root.child("relay");
    let material_root = root.child("material");
    let scratch_root = root.child("scratch");
    let metadata = fs::metadata(&root.0).unwrap();
    let cancelled = Arc::new(AtomicBool::new(false));
    let publisher = Arc::new(FakePublisher::default());
    let engine = Arc::new(FakeEngine {
        calls: AtomicUsize::new(0),
        cleanup_confirmed: true,
    });
    let relay = TrialRelay::start(
        &relay_root,
        &material_root,
        &scratch_root,
        &identity(),
        &profile(),
        publisher.clone(),
        engine.clone(),
        metadata.uid(),
        metadata.gid(),
        Instant::now() + Duration::from_secs(2),
        cancelled.clone(),
    )
    .unwrap();
    cancelled.store(true, Ordering::Release);
    let finish = relay.finish();
    assert_eq!(finish.failure, Some(TrialRelayFailure::Cancelled));
    assert!(!finish.plan_started && !finish.plan_completed);
    assert_eq!(engine.calls.load(Ordering::Relaxed), 0);
    assert!(publisher.0.lock().unwrap().is_empty());
}

#[test]
fn selected_but_unused_trial_capability_finishes_cleanly() {
    let root = TestRoot::new();
    let relay_root = root.child("relay");
    let material_root = root.child("material");
    let scratch_root = root.child("scratch");
    let metadata = fs::metadata(&root.0).unwrap();
    let engine = Arc::new(FakeEngine {
        calls: AtomicUsize::new(0),
        cleanup_confirmed: true,
    });
    let relay = TrialRelay::start(
        &relay_root,
        &material_root,
        &scratch_root,
        &identity(),
        &profile(),
        Arc::new(FakePublisher::default()),
        engine.clone(),
        metadata.uid(),
        metadata.gid(),
        Instant::now() + Duration::from_secs(2),
        Arc::new(AtomicBool::new(false)),
    )
    .unwrap();
    let finish = relay.finish();
    assert_eq!(finish.failure, None);
    assert!(!finish.plan_started && !finish.plan_completed);
    assert_eq!(engine.calls.load(Ordering::Relaxed), 0);
}

#[test]
fn retained_receipt_skips_engine_and_accepts_new_worker_provenance() {
    let first = start(true);
    let first_response = exchange(first.relay.socket_path(), &request(plan()));
    assert_eq!(first_response["outcome"], "completed");
    let value = first.publisher.0.lock().unwrap()[0].clone();
    assert_eq!(first.relay.finish().failure, None);
    let canonical_bytes = serde_json::to_vec(&value).unwrap();
    let receipt = CanonicalTrialReceipt {
        receipt_digest: text_digest(&String::from_utf8(canonical_bytes.clone()).unwrap()),
        byte_count: canonical_bytes.len(),
        facts: serde_json::from_value(value).unwrap(),
        canonical_bytes,
    };

    let root = TestRoot::new();
    let metadata = fs::metadata(&root.0).unwrap();
    let mut retried = identity();
    retried.request_digest = digest('f');
    retried.evaluation_request_id = "018f6f49-66b8-7d2a-bf4d-0e2eeaa00200".into();
    retried.evaluation_generation += 1;
    retried.checker_run_id = "018f6f49-66b8-7d2a-bf4d-0e2eeaa00201".into();
    retried.attempt_id = "018f6f49-66b8-7d2a-bf4d-0e2eeaa00202".into();
    retried.result_id = "018f6f49-66b8-7d2a-bf4d-0e2eeaa00203".into();
    retried.worker_lease_id = "018f6f49-66b8-7d2a-bf4d-0e2eeaa00204".into();
    retried.worker_lease_generation += 1;
    let engine = Arc::new(FakeEngine {
        calls: AtomicUsize::new(0),
        cleanup_confirmed: true,
    });
    let relay = TrialRelay::start(
        &root.child("relay"),
        &root.child("material"),
        &root.child("scratch"),
        &retried,
        &profile(),
        Arc::new(RetainedPublisher(Mutex::new(Some(receipt)))),
        engine.clone(),
        metadata.uid(),
        metadata.gid(),
        Instant::now() + Duration::from_secs(2),
        Arc::new(AtomicBool::new(false)),
    )
    .unwrap();
    let response = exchange(relay.socket_path(), &request(plan()));
    assert_eq!(response["outcome"], "completed");
    assert_eq!(
        response["receipt_handle"],
        format!("trial_receipt_{}", "b".repeat(32))
    );
    assert_eq!(engine.calls.load(Ordering::Relaxed), 0);
    let finish = relay.finish();
    assert_eq!(finish.failure, None);
    assert!(!finish.plan_started && finish.plan_completed);
}

#[test]
fn observed_build_failure_publishes_work_evidence_and_skips_dependent_step() {
    let root = TestRoot::new();
    let relay_root = root.child("relay");
    let material_root = root.child("material");
    let scratch_root = root.child("scratch");
    let metadata = fs::metadata(&root.0).unwrap();
    let publisher = Arc::new(FakePublisher::default());
    let relay = TrialRelay::start(
        &relay_root,
        &material_root,
        &scratch_root,
        &identity(),
        &profile(),
        publisher.clone(),
        Arc::new(BuildFailureEngine),
        metadata.uid(),
        metadata.gid(),
        Instant::now() + Duration::from_secs(2),
        Arc::new(AtomicBool::new(false)),
    )
    .unwrap();
    let response = exchange(relay.socket_path(), &request(plan()));
    assert_eq!(response["outcome"], "completed");
    let publications = publisher.0.lock().unwrap();
    assert_eq!(
        publications[0]["execution"]["build"]["outcome"],
        "exit_nonzero"
    );
    assert_eq!(
        publications[0]["execution"]["steps"][0]["outcome"],
        "dependency_skipped"
    );
    drop(publications);
    assert_eq!(relay.finish().failure, None);
}

#[test]
fn observed_cpu_and_deadline_overruns_are_preserved_within_enforcement_caps() {
    let mut cpu = execution(true);
    cpu.steps[0].outcome = TrialOperationOutcome::CpuExceeded;
    cpu.steps[0].exit_code = None;
    cpu.steps[0].signal = None;
    cpu.steps[0].cpu_time_ms = 5_001;
    cpu.steps[0].export_outcome = TrialExportOutcome::Unavailable;
    assert_observed_limit_is_published(cpu, "cpu_exceeded");

    let mut deadline = execution(true);
    deadline.steps[0].outcome = TrialOperationOutcome::DeadlineExceeded;
    deadline.steps[0].exit_code = None;
    deadline.steps[0].signal = None;
    deadline.steps[0].elapsed_ms = 850;
    deadline.steps[0].export_outcome = TrialExportOutcome::Unavailable;
    assert_observed_limit_is_published(deadline, "deadline_exceeded");
}

#[test]
fn closed_export_failures_preserve_child_status_without_fabricating_usage() {
    let mut invalid = execution(true);
    invalid.steps[0].outcome = TrialOperationOutcome::ExportInvalid;
    invalid.steps[0].export_outcome = TrialExportOutcome::Invalid;
    invalid.steps[0].exit_code = Some(0);
    invalid.steps[0].signal = None;
    assert_observed_limit_is_published(invalid, "export_invalid");

    let mut capacity = execution(true);
    capacity.steps[0].outcome = TrialOperationOutcome::DiskExceeded;
    capacity.steps[0].export_outcome = TrialExportOutcome::CapacityExceeded;
    capacity.steps[0].exit_code = Some(0);
    capacity.steps[0].signal = None;
    capacity.steps[0].written_bytes = 64;
    capacity.steps[0].written_entries = 1;
    assert_observed_limit_is_published(capacity, "disk_exceeded");
}
