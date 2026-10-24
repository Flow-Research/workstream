//! Trusted trial-evidence reservation and ART-custody callback client.

use crate::proxy_transport::{connect_private, read_frame, write_frame};
use crate::trial_relay::{
    valid_sha256, valid_uuid, CanonicalTrialReceipt, PublishedTrialReceipt, TrialEvidenceSubject,
    TrialReceiptCustodyAck, TrialReceiptPublication, TrialReceiptPublishFailure,
    TrialReceiptPublisher, TrialReceiptReservation, TrialRelayFailure,
};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::atomic::AtomicBool;
use std::sync::{Arc, Mutex};
use std::time::Instant;
use workstream_checker_sdk::canonical_hash;

const PROTOCOL: &str = "workstream.trial_evidence_proxy.v1";
const MAXIMUM_FRAME_BYTES: usize = 4 * 1024 * 1024;
const MAXIMUM_RECEIPT_BYTES: usize = 1024 * 1024;

#[derive(Clone, Debug)]
pub(crate) struct TrialEvidenceProxyClient {
    socket: PathBuf,
    external_request: Value,
    reservations: Arc<Mutex<HashMap<String, ReservedOwner>>>,
}

pub(crate) trait InvocationReceiptRegistrar: Send + Sync + 'static {
    fn register(
        &self,
        request_digest: &str,
        canonical_receipt_utf8: String,
        receipt_sha256: String,
        custody: &TrialReceiptCustodyAck,
    ) -> Result<String, ()>;
}

pub(crate) struct DurableTrialReceiptPublisher<R: InvocationReceiptRegistrar> {
    proxy: TrialEvidenceProxyClient,
    registrar: Arc<R>,
    request_digest: String,
    maximum_receipt_bytes: usize,
    deadline: Instant,
    cancelled: Arc<AtomicBool>,
}

#[derive(Clone, Debug)]
struct ReservedOwner {
    subject: TrialEvidenceSubject,
    maximum_bytes: usize,
}

#[derive(Debug)]
pub(crate) enum ReservedTrialEvidence {
    Fresh {
        trial_evidence_id: String,
    },
    Retained {
        trial_evidence_id: String,
        receipt: CanonicalTrialReceipt,
        custody: TrialReceiptCustodyAck,
    },
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum TrialEvidenceProxyFailure {
    Unavailable,
    Deadline,
    InvalidResponse,
}

#[derive(Serialize)]
struct ReserveRequest<'a> {
    protocol_version: &'static str,
    operation: &'static str,
    external_request: &'a Value,
    subject: &'a TrialEvidenceSubject,
}

#[derive(Serialize)]
struct PublishRequest<'a> {
    protocol_version: &'static str,
    operation: &'static str,
    external_request: &'a Value,
    trial_evidence_id: &'a str,
    project_id: &'a str,
    content_sha256: &'a str,
    byte_count: usize,
    canonical_receipt_utf8: &'a str,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ReserveCompleted {
    protocol_version: String,
    operation: String,
    outcome: String,
    ticket: TrialEvidenceTicket,
    retained_receipt: Option<RetainedReceipt>,
    failure_code: Option<String>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PublishCompleted {
    protocol_version: String,
    operation: String,
    outcome: String,
    custody_ack: WireCustodyAck,
    failure_code: Option<String>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct UnavailableResponse {
    protocol_version: String,
    operation: String,
    outcome: String,
    failure_code: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct TrialEvidenceTicket {
    trial_evidence_id: String,
    subject: TrialEvidenceSubjectWire,
    origin: TrialEvidenceOrigin,
    slot: TrialEvidenceSlot,
    content_sha256: Option<String>,
    replayed: bool,
}

#[derive(Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct TrialEvidenceSubjectWire {
    project_id: String,
    task_id: String,
    assignment_id: String,
    submission_id: String,
    submission_version: u64,
    requirement_id: String,
    registry_entry_id: String,
    registry_entry_digest: String,
    configuration_sha256: String,
    trial_kind: String,
    slot_index: u32,
    plan_sha256: String,
    input_digest: String,
    materials_digest: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct TrialEvidenceOrigin {
    checker_run_id: String,
    worker_lease_id: String,
    worker_lease_generation: u64,
    worker_lease_expires_at: String,
    external_request_digest: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct TrialEvidenceSlot {
    key: String,
    media_type: String,
    maximum_bytes: usize,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct RetainedReceipt {
    canonical_receipt_utf8: String,
    content_sha256: String,
    byte_count: usize,
    custody_ack: WireCustodyAck,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
#[derive(Serialize)]
struct WireCustodyAck {
    trial_evidence_id: String,
    owner_digest: String,
    content_sha256: String,
    byte_count: usize,
    binding_id: String,
    content_id: String,
    put_attempt_id: String,
    verification_receipt_id: String,
    replayed: bool,
}

impl TrialEvidenceProxyClient {
    pub(crate) fn new(socket: PathBuf, external_request: Value) -> Self {
        Self {
            socket,
            external_request,
            reservations: Arc::new(Mutex::new(HashMap::new())),
        }
    }

    pub(crate) fn reserve(
        &self,
        subject: &TrialEvidenceSubject,
        maximum_receipt_bytes: usize,
        deadline: Instant,
        cancelled: &AtomicBool,
    ) -> Result<ReservedTrialEvidence, TrialEvidenceProxyFailure> {
        if maximum_receipt_bytes == 0 || maximum_receipt_bytes > MAXIMUM_RECEIPT_BYTES {
            return Err(TrialEvidenceProxyFailure::InvalidResponse);
        }
        let response = self.exchange(
            &ReserveRequest {
                protocol_version: PROTOCOL,
                operation: "reserve",
                external_request: &self.external_request,
                subject,
            },
            deadline,
            cancelled,
        )?;
        if response.get("outcome").and_then(Value::as_str) == Some("unavailable") {
            return parse_unavailable(response, "reserve");
        }
        require_exact_keys(
            &response,
            &[
                "protocol_version",
                "operation",
                "outcome",
                "ticket",
                "retained_receipt",
                "failure_code",
            ],
        )?;
        let completed: ReserveCompleted = serde_json::from_value(response)
            .map_err(|_| TrialEvidenceProxyFailure::InvalidResponse)?;
        if completed.protocol_version != PROTOCOL
            || completed.operation != "reserve"
            || completed.outcome != "completed"
            || completed.failure_code.is_some()
            || !valid_ticket(&completed.ticket, subject, maximum_receipt_bytes)
        {
            return Err(TrialEvidenceProxyFailure::InvalidResponse);
        }
        self.reservations
            .lock()
            .map_err(|_| TrialEvidenceProxyFailure::Unavailable)?
            .insert(
                completed.ticket.trial_evidence_id.clone(),
                ReservedOwner {
                    subject: subject.clone(),
                    maximum_bytes: maximum_receipt_bytes,
                },
            );
        match (completed.ticket.replayed, completed.retained_receipt) {
            (_, None) if completed.ticket.content_sha256.is_none() => {
                Ok(ReservedTrialEvidence::Fresh {
                    trial_evidence_id: completed.ticket.trial_evidence_id,
                })
            }
            (true, Some(retained)) => {
                let expected = completed
                    .ticket
                    .content_sha256
                    .as_deref()
                    .ok_or(TrialEvidenceProxyFailure::InvalidResponse)?;
                let (receipt, custody) = retained_receipt(
                    retained,
                    &completed.ticket.trial_evidence_id,
                    expected,
                    maximum_receipt_bytes,
                    &owner_digest(subject, maximum_receipt_bytes, expected)?,
                    &completed.ticket.origin,
                    true,
                )?;
                Ok(ReservedTrialEvidence::Retained {
                    trial_evidence_id: completed.ticket.trial_evidence_id,
                    receipt,
                    custody,
                })
            }
            _ => Err(TrialEvidenceProxyFailure::InvalidResponse),
        }
    }

    pub(crate) fn publish(
        &self,
        trial_evidence_id: &str,
        receipt: &CanonicalTrialReceipt,
        deadline: Instant,
        cancelled: &AtomicBool,
    ) -> Result<TrialReceiptCustodyAck, TrialEvidenceProxyFailure> {
        let canonical_receipt_utf8 = std::str::from_utf8(&receipt.canonical_bytes)
            .map_err(|_| TrialEvidenceProxyFailure::InvalidResponse)?;
        if !valid_uuid(trial_evidence_id)
            || receipt.byte_count == 0
            || receipt.byte_count > MAXIMUM_RECEIPT_BYTES
            || receipt.byte_count != receipt.canonical_bytes.len()
            || !valid_sha256(&receipt.receipt_digest)
        {
            return Err(TrialEvidenceProxyFailure::InvalidResponse);
        }
        let reserved = self
            .reservations
            .lock()
            .map_err(|_| TrialEvidenceProxyFailure::Unavailable)?
            .get(trial_evidence_id)
            .cloned()
            .ok_or(TrialEvidenceProxyFailure::InvalidResponse)?;
        if receipt.byte_count > reserved.maximum_bytes {
            return Err(TrialEvidenceProxyFailure::InvalidResponse);
        }
        let expected_owner_digest = owner_digest(
            &reserved.subject,
            reserved.maximum_bytes,
            &receipt.receipt_digest,
        )?;
        let response = self.exchange(
            &PublishRequest {
                protocol_version: PROTOCOL,
                operation: "publish",
                external_request: &self.external_request,
                trial_evidence_id,
                project_id: &reserved.subject.project_id,
                content_sha256: &receipt.receipt_digest,
                byte_count: receipt.byte_count,
                canonical_receipt_utf8,
            },
            deadline,
            cancelled,
        )?;
        if response.get("outcome").and_then(Value::as_str) == Some("unavailable") {
            return parse_unavailable(response, "publish");
        }
        require_exact_keys(
            &response,
            &[
                "protocol_version",
                "operation",
                "outcome",
                "custody_ack",
                "failure_code",
            ],
        )?;
        let completed: PublishCompleted = serde_json::from_value(response)
            .map_err(|_| TrialEvidenceProxyFailure::InvalidResponse)?;
        if completed.protocol_version != PROTOCOL
            || completed.operation != "publish"
            || completed.outcome != "completed"
            || completed.failure_code.is_some()
        {
            return Err(TrialEvidenceProxyFailure::InvalidResponse);
        }
        custody_ack(
            completed.custody_ack,
            trial_evidence_id,
            &receipt.receipt_digest,
            receipt.byte_count,
            &expected_owner_digest,
            false,
        )
    }

    fn exchange<T: Serialize>(
        &self,
        request: &T,
        deadline: Instant,
        cancelled: &AtomicBool,
    ) -> Result<Value, TrialEvidenceProxyFailure> {
        let body =
            serde_json::to_vec(request).map_err(|_| TrialEvidenceProxyFailure::InvalidResponse)?;
        let mut stream = connect_private(&self.socket, deadline, cancelled)
            .map_err(|_| TrialEvidenceProxyFailure::Unavailable)?;
        write_frame(&mut stream, &body, MAXIMUM_FRAME_BYTES, deadline, cancelled)
            .map_err(|_| TrialEvidenceProxyFailure::Unavailable)?;
        let response = read_frame(&mut stream, MAXIMUM_FRAME_BYTES, deadline, cancelled)
            .map_err(|_| TrialEvidenceProxyFailure::Unavailable)?;
        serde_json::from_slice(&response).map_err(|_| TrialEvidenceProxyFailure::InvalidResponse)
    }
}

impl<R: InvocationReceiptRegistrar> DurableTrialReceiptPublisher<R> {
    pub(crate) fn new(
        proxy: TrialEvidenceProxyClient,
        registrar: Arc<R>,
        request_digest: String,
        maximum_receipt_bytes: usize,
        deadline: Instant,
        cancelled: Arc<AtomicBool>,
    ) -> Result<Self, TrialReceiptPublishFailure> {
        if !valid_sha256(&request_digest)
            || maximum_receipt_bytes == 0
            || maximum_receipt_bytes > MAXIMUM_RECEIPT_BYTES
        {
            return Err(publish_failure(TrialEvidenceProxyFailure::InvalidResponse));
        }
        Ok(Self {
            proxy,
            registrar,
            request_digest,
            maximum_receipt_bytes,
            deadline,
            cancelled,
        })
    }

    fn register(
        &self,
        receipt: &CanonicalTrialReceipt,
        custody: &TrialReceiptCustodyAck,
    ) -> Result<String, TrialReceiptPublishFailure> {
        let canonical = String::from_utf8(receipt.canonical_bytes.clone())
            .map_err(|_| publish_failure(TrialEvidenceProxyFailure::InvalidResponse))?;
        self.registrar
            .register(
                &self.request_digest,
                canonical,
                receipt.receipt_digest.clone(),
                custody,
            )
            .map_err(|_| publish_failure(TrialEvidenceProxyFailure::Unavailable))
    }
}

impl<R: InvocationReceiptRegistrar> TrialReceiptPublisher for DurableTrialReceiptPublisher<R> {
    fn reserve_completed(
        &self,
        subject: TrialEvidenceSubject,
    ) -> Result<TrialReceiptReservation, TrialReceiptPublishFailure> {
        match self
            .proxy
            .reserve(
                &subject,
                self.maximum_receipt_bytes,
                self.deadline,
                &self.cancelled,
            )
            .map_err(publish_failure)?
        {
            ReservedTrialEvidence::Fresh { trial_evidence_id } => {
                Ok(TrialReceiptReservation::Fresh { trial_evidence_id })
            }
            ReservedTrialEvidence::Retained {
                trial_evidence_id,
                receipt,
                custody,
            } => {
                let receipt_handle = self.register(&receipt, &custody)?;
                Ok(TrialReceiptReservation::Retained {
                    trial_evidence_id,
                    receipt,
                    published: PublishedTrialReceipt {
                        receipt_handle,
                        custody,
                    },
                })
            }
        }
    }

    fn publish_completed(
        &self,
        trial_evidence_id: &str,
        receipt: CanonicalTrialReceipt,
    ) -> Result<PublishedTrialReceipt, TrialReceiptPublishFailure> {
        let custody = self
            .proxy
            .publish(trial_evidence_id, &receipt, self.deadline, &self.cancelled)
            .map_err(publish_failure)?;
        let receipt_handle = self.register(&receipt, &custody)?;
        Ok(PublishedTrialReceipt {
            receipt_handle,
            custody,
        })
    }
}

fn publish_failure(value: TrialEvidenceProxyFailure) -> TrialReceiptPublishFailure {
    TrialReceiptPublishFailure {
        code: match value {
            TrialEvidenceProxyFailure::Deadline => TrialRelayFailure::DeadlineExceeded,
            TrialEvidenceProxyFailure::Unavailable | TrialEvidenceProxyFailure::InvalidResponse => {
                TrialRelayFailure::ImplementationUnavailable
            }
        },
    }
}

fn valid_ticket(
    ticket: &TrialEvidenceTicket,
    subject: &TrialEvidenceSubject,
    maximum_receipt_bytes: usize,
) -> bool {
    valid_uuid(&ticket.trial_evidence_id)
        && ticket.subject == subject_wire(subject)
        && ticket.slot.key == "trial_receipt"
        && ticket.slot.media_type == "application/json"
        && ticket.slot.maximum_bytes == maximum_receipt_bytes
        && valid_origin(&ticket.origin)
        && ticket
            .content_sha256
            .as_ref()
            .is_none_or(|value| valid_sha256(value))
}

fn subject_wire(subject: &TrialEvidenceSubject) -> TrialEvidenceSubjectWire {
    TrialEvidenceSubjectWire {
        project_id: subject.project_id.clone(),
        task_id: subject.task_id.clone(),
        assignment_id: subject.assignment_id.clone(),
        submission_id: subject.submission_id.clone(),
        submission_version: subject.submission_version,
        requirement_id: subject.requirement_id.clone(),
        registry_entry_id: subject.registry_entry_id.clone(),
        registry_entry_digest: subject.registry_entry_digest.clone(),
        configuration_sha256: subject.configuration_sha256.clone(),
        trial_kind: subject.trial_kind.clone(),
        slot_index: subject.slot_index,
        plan_sha256: subject.plan_sha256.clone(),
        input_digest: subject.input_digest.clone(),
        materials_digest: subject.materials_digest.clone(),
    }
}

fn valid_origin(origin: &TrialEvidenceOrigin) -> bool {
    valid_uuid(&origin.checker_run_id)
        && valid_uuid(&origin.worker_lease_id)
        && origin.worker_lease_generation > 0
        && !origin.worker_lease_expires_at.is_empty()
        && origin.worker_lease_expires_at.len() <= 64
        && valid_sha256(&origin.external_request_digest)
}

fn retained_receipt(
    retained: RetainedReceipt,
    trial_evidence_id: &str,
    expected_digest: &str,
    maximum_receipt_bytes: usize,
    expected_owner_digest: &str,
    origin: &TrialEvidenceOrigin,
    expected_replayed: bool,
) -> Result<(CanonicalTrialReceipt, TrialReceiptCustodyAck), TrialEvidenceProxyFailure> {
    let bytes = retained.canonical_receipt_utf8.into_bytes();
    let digest = format!("sha256:{:x}", Sha256::digest(&bytes));
    if bytes.is_empty()
        || bytes.len() > maximum_receipt_bytes
        || retained.byte_count != bytes.len()
        || retained.content_sha256 != expected_digest
        || digest != expected_digest
    {
        return Err(TrialEvidenceProxyFailure::InvalidResponse);
    }
    let facts: TrialReceiptPublication =
        serde_json::from_slice(&bytes).map_err(|_| TrialEvidenceProxyFailure::InvalidResponse)?;
    if facts.originating_identity.checker_run_id != origin.checker_run_id
        || facts.originating_identity.worker_lease_id != origin.worker_lease_id
        || facts.originating_identity.worker_lease_generation != origin.worker_lease_generation
        || facts.originating_identity.worker_lease_expires_at != origin.worker_lease_expires_at
        || facts.originating_identity.request_digest != origin.external_request_digest
    {
        return Err(TrialEvidenceProxyFailure::InvalidResponse);
    }
    let custody = custody_ack(
        retained.custody_ack,
        trial_evidence_id,
        expected_digest,
        bytes.len(),
        expected_owner_digest,
        expected_replayed,
    )?;
    Ok((
        CanonicalTrialReceipt {
            receipt_digest: digest,
            byte_count: bytes.len(),
            canonical_bytes: bytes,
            facts,
        },
        custody,
    ))
}

fn custody_ack(
    ack: WireCustodyAck,
    trial_evidence_id: &str,
    digest: &str,
    byte_count: usize,
    expected_owner_digest: &str,
    expected_replayed: bool,
) -> Result<TrialReceiptCustodyAck, TrialEvidenceProxyFailure> {
    if ack.trial_evidence_id != trial_evidence_id
        || ack.owner_digest != expected_owner_digest
        || ack.content_sha256 != digest
        || ack.byte_count != byte_count
        || !valid_uuid(&ack.binding_id)
        || !valid_uuid(&ack.content_id)
        || !valid_uuid(&ack.put_attempt_id)
        || !valid_uuid(&ack.verification_receipt_id)
        || ack.replayed != expected_replayed
    {
        return Err(TrialEvidenceProxyFailure::InvalidResponse);
    }
    Ok(TrialReceiptCustodyAck {
        binding_id: ack.binding_id,
        content_id: ack.content_id,
        put_attempt_id: ack.put_attempt_id,
        verification_receipt_id: ack.verification_receipt_id,
        content_sha256: ack.content_sha256,
        byte_count: ack.byte_count,
    })
}

fn owner_digest(
    subject: &TrialEvidenceSubject,
    maximum_bytes: usize,
    content_sha256: &str,
) -> Result<String, TrialEvidenceProxyFailure> {
    canonical_hash(&serde_json::json!({
        "subject": subject,
        "slot": {
            "key": "trial_receipt",
            "media_type": "application/json",
            "maximum_bytes": maximum_bytes,
        },
        "content_sha256": content_sha256,
    }))
    .map_err(|_| TrialEvidenceProxyFailure::InvalidResponse)
}

fn parse_unavailable<T>(value: Value, operation: &str) -> Result<T, TrialEvidenceProxyFailure> {
    require_exact_keys(
        &value,
        &["protocol_version", "operation", "outcome", "failure_code"],
    )?;
    let response: UnavailableResponse =
        serde_json::from_value(value).map_err(|_| TrialEvidenceProxyFailure::InvalidResponse)?;
    if response.protocol_version != PROTOCOL
        || response.operation != operation
        || response.outcome != "unavailable"
        || !matches!(
            response.failure_code.as_str(),
            "trial_request_invalid"
                | "trial_request_too_large"
                | "trial_owner_unavailable"
                | "trial_subject_conflict"
                | "trial_evidence_unavailable"
                | "trial_evidence_custody_unavailable"
                | "trial_deadline"
        )
    {
        return Err(TrialEvidenceProxyFailure::InvalidResponse);
    }
    Err(if response.failure_code == "trial_deadline" {
        TrialEvidenceProxyFailure::Deadline
    } else {
        TrialEvidenceProxyFailure::Unavailable
    })
}

fn require_exact_keys(value: &Value, expected: &[&str]) -> Result<(), TrialEvidenceProxyFailure> {
    let object = value
        .as_object()
        .ok_or(TrialEvidenceProxyFailure::InvalidResponse)?;
    if object.len() != expected.len() || expected.iter().any(|key| !object.contains_key(*key)) {
        return Err(TrialEvidenceProxyFailure::InvalidResponse);
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::proxy_transport::{read_frame, write_frame};
    use std::fs;
    use std::os::unix::fs::PermissionsExt;
    use std::os::unix::net::UnixListener;
    use std::sync::atomic::AtomicU64;
    use std::thread;
    use std::time::Duration;

    static SEQUENCE: AtomicU64 = AtomicU64::new(0);

    struct TestRoot(PathBuf);

    impl TestRoot {
        fn new() -> Self {
            let path = std::env::temp_dir().join(format!(
                "trial-evidence-proxy-{}-{}",
                std::process::id(),
                SEQUENCE.fetch_add(1, std::sync::atomic::Ordering::Relaxed)
            ));
            fs::create_dir(&path).unwrap();
            fs::set_permissions(&path, fs::Permissions::from_mode(0o700)).unwrap();
            Self(path)
        }
    }

    impl Drop for TestRoot {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    fn digest(value: char) -> String {
        format!("sha256:{}", value.to_string().repeat(64))
    }

    fn subject() -> TrialEvidenceSubject {
        TrialEvidenceSubject {
            project_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00001".into(),
            task_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00002".into(),
            assignment_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00003".into(),
            submission_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00004".into(),
            submission_version: 2,
            requirement_id: "check_a".into(),
            registry_entry_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00005".into(),
            registry_entry_digest: digest('1'),
            configuration_sha256: digest('2'),
            trial_kind: "generic_build_run".into(),
            slot_index: 0,
            plan_sha256: digest('3'),
            input_digest: digest('4'),
            materials_digest: digest('5'),
        }
    }

    #[test]
    fn reserve_sends_full_request_and_accepts_only_exact_fresh_ticket() {
        let root = TestRoot::new();
        let socket = root.0.join("proxy.sock");
        let listener = UnixListener::bind(&socket).unwrap();
        fs::set_permissions(&socket, fs::Permissions::from_mode(0o600)).unwrap();
        let request = serde_json::json!({"request_digest": digest('a'), "configuration": {}});
        let expected_request = request.clone();
        let selected = subject();
        let expected_subject = serde_json::to_value(&selected).unwrap();
        let worker = thread::spawn(move || {
            for replayed in [false, true] {
                let (mut stream, _) = listener.accept().unwrap();
                let deadline = Instant::now() + Duration::from_secs(2);
                let cancelled = AtomicBool::new(false);
                let frame =
                    read_frame(&mut stream, MAXIMUM_FRAME_BYTES, deadline, &cancelled).unwrap();
                let value: Value = serde_json::from_slice(&frame).unwrap();
                assert_eq!(value["external_request"], expected_request);
                assert_eq!(value["subject"], expected_subject);
                let response = serde_json::json!({
                    "protocol_version": PROTOCOL,
                    "operation": "reserve",
                    "outcome": "completed",
                    "ticket": {
                        "trial_evidence_id": "018f6f49-66b8-7d2a-bf4d-0e2eeaa00006",
                        "subject": value["subject"],
                        "origin": {
                            "checker_run_id": "018f6f49-66b8-7d2a-bf4d-0e2eeaa00007",
                            "worker_lease_id": "018f6f49-66b8-7d2a-bf4d-0e2eeaa00008",
                            "worker_lease_generation": 1,
                            "worker_lease_expires_at": "2026-10-23T12:00:00Z",
                            "external_request_digest": digest('a'),
                        },
                        "slot": {"key":"trial_receipt","media_type":"application/json","maximum_bytes":1024},
                        "content_sha256": null,
                        "replayed": replayed,
                    },
                    "retained_receipt": null,
                    "failure_code": null,
                });
                write_frame(
                    &mut stream,
                    &serde_json::to_vec(&response).unwrap(),
                    MAXIMUM_FRAME_BYTES,
                    deadline,
                    &cancelled,
                )
                .unwrap();
            }
        });
        let client = TrialEvidenceProxyClient::new(socket, request);
        for _ in 0..2 {
            let reserved = client
                .reserve(
                    &selected,
                    1024,
                    Instant::now() + Duration::from_secs(2),
                    &AtomicBool::new(false),
                )
                .unwrap();
            assert!(matches!(reserved, ReservedTrialEvidence::Fresh { .. }));
        }
        worker.join().unwrap();
    }

    fn wire_ack(owner: String, replayed: bool) -> WireCustodyAck {
        WireCustodyAck {
            trial_evidence_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00006".into(),
            owner_digest: owner,
            content_sha256: digest('c'),
            byte_count: 17,
            binding_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00009".into(),
            content_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa0000a".into(),
            put_attempt_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa0000b".into(),
            verification_receipt_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa0000c".into(),
            replayed,
        }
    }

    #[test]
    fn custody_ack_rejects_owner_substitution_and_wrong_replay_state() {
        let expected = digest('d');
        assert_eq!(
            custody_ack(
                wire_ack(digest('e'), false),
                "018f6f49-66b8-7d2a-bf4d-0e2eeaa00006",
                &digest('c'),
                17,
                &expected,
                false,
            ),
            Err(TrialEvidenceProxyFailure::InvalidResponse),
        );
        assert_eq!(
            custody_ack(
                wire_ack(expected.clone(), true),
                "018f6f49-66b8-7d2a-bf4d-0e2eeaa00006",
                &digest('c'),
                17,
                &expected,
                false,
            ),
            Err(TrialEvidenceProxyFailure::InvalidResponse),
        );
        assert!(custody_ack(
            wire_ack(expected.clone(), true),
            "018f6f49-66b8-7d2a-bf4d-0e2eeaa00006",
            &digest('c'),
            17,
            &expected,
            true,
        )
        .is_ok());
    }

    #[test]
    fn publish_wire_includes_project_and_uses_custody_ack_field() {
        let external_request = serde_json::json!({"request_digest": digest('a')});
        let request = serde_json::to_value(PublishRequest {
            protocol_version: PROTOCOL,
            operation: "publish",
            external_request: &external_request,
            trial_evidence_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00006",
            project_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00001",
            content_sha256: &digest('c'),
            byte_count: 2,
            canonical_receipt_utf8: "{}",
        })
        .unwrap();
        assert_eq!(
            request
                .as_object()
                .unwrap()
                .keys()
                .cloned()
                .collect::<std::collections::BTreeSet<_>>(),
            [
                "byte_count",
                "canonical_receipt_utf8",
                "content_sha256",
                "external_request",
                "operation",
                "project_id",
                "protocol_version",
                "trial_evidence_id",
            ]
            .iter()
            .map(|key| key.to_string())
            .collect::<std::collections::BTreeSet<_>>()
        );
        let response = serde_json::json!({
            "protocol_version": PROTOCOL,
            "operation": "publish",
            "outcome": "completed",
            "custody_ack": wire_ack(digest('d'), false),
            "failure_code": null,
        });
        assert!(serde_json::from_value::<PublishCompleted>(response).is_ok());
    }
}
