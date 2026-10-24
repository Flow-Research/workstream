//! Strict wire validation shared by the checker service and external images.

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;
use std::fmt::Write;

pub const REQUEST_SCHEMA_VERSION: &str = "external_checker_request.v1";
pub const RESULT_SCHEMA_VERSION: &str = "external_checker_result.v1";
pub const MAX_REQUEST_BYTES: usize = 2 * 1024 * 1024;
pub const MAX_RESULT_BYTES: usize = 65_536;
const EVALUATION_CONTEXT_VERSION: &str = "v1";
const EVALUATION_CONTEXT_SCHEMA_VERSION: &str = "workstream.post_submit_evaluation_context.v1";
const EVALUATION_CONTEXT_VERSION_KEY: &str = "workstream_evaluation_context_version";
const EVALUATION_CONTEXT_ROLES_KEY: &str = "workstream_evaluation_context_roles";
const PREDECESSOR_ARCHIVE_ROLE: &str = "predecessor_submission_archive";
const PREDECESSOR_FINDINGS_ROLE: &str = "predecessor_findings";
const CURRENT_ARCHIVE_ROLE: &str = "submission_archive";
const MAX_REVISION_FEEDBACK_BYTES: usize = 524_288;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ContractError(&'static str);

impl std::fmt::Display for ContractError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(self.0)
    }
}

impl std::error::Error for ContractError {}

#[derive(Debug, Clone)]
pub struct ValidatedRequest {
    pub value: Value,
    pub request_digest: String,
    pub registry_entry_id: String,
    pub registry_entry_digest: String,
    pub image_digest: String,
    pub configuration_digest: String,
    pub phase: String,
    pub post_material_roles: Vec<String>,
    pub evaluation_context_sha256: Option<String>,
    pub cpu_millis: u64,
    pub memory_bytes: u64,
    pub deadline_ms: u64,
    pub maximum_output_bytes: usize,
}

#[derive(Debug)]
struct PostEvaluationContext {
    sha256: String,
    kind: String,
    predecessor_submission_id: Option<String>,
    predecessor_submission_version: Option<u64>,
    predecessor_content_sha256: Option<String>,
    predecessor_byte_count: Option<u64>,
    predecessor_semantic_manifest_sha256: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Finding {
    pub check_id: String,
    pub code: String,
    pub level: String,
    pub message: String,
    pub path: Option<String>,
    pub line: Option<u64>,
}

/// Mirrors Python `safe_finding_path`: a relative archive path with no control,
/// formatting, traversal or absolute forms. Python revalidates every result.
pub fn is_safe_finding_path(path: &str) -> bool {
    let formatting = |item: char| {
        matches!(item as u32,
            0x0080..=0x009F | 0x2028 | 0x2029 | 0x00AD | 0x0600..=0x0605 | 0x061C | 0x06DD | 0x070F | 0x0890..=0x0891 | 0x08E2
            | 0x180E | 0x200B..=0x200F | 0x202A..=0x202E | 0x2060..=0x2064 | 0x2066..=0x206F
            | 0xFEFF | 0xFFF9..=0xFFFB | 0x110BD | 0x110CD | 0x13430..=0x1343F
            | 0x1BCA0..=0x1BCA3 | 0x1D173..=0x1D17A | 0xE0001 | 0xE0020..=0xE007F)
    };
    let parts: Vec<&str> = path.split('/').collect();
    !path.is_empty()
        && path.chars().count() <= 1000
        && !path.contains('\\')
        && !path.starts_with('/')
        && !path
            .chars()
            .any(|item| (item as u32) < 32 || item as u32 == 127 || formatting(item))
        && !parts.iter().any(|part| {
            matches!(*part, "" | "." | "..") || part.ends_with(' ') || part.ends_with('.')
        })
        && !parts[0].contains(':')
}

/// Mirrors the Python `Identifier`: lowercase start, then `[a-z0-9_.-]`, at most 100.
fn is_identifier(value: &str) -> bool {
    let mut characters = value.chars();
    value.len() <= 100
        && characters
            .next()
            .is_some_and(|first| first.is_ascii_lowercase())
        && characters.all(|item| {
            item.is_ascii_lowercase() || item.is_ascii_digit() || matches!(item, '_' | '.' | '-')
        })
}

pub fn canonical_json(value: &Value) -> Result<String, ContractError> {
    let mut output = String::new();
    write_canonical(value, &mut output)?;
    Ok(output)
}

pub fn canonical_hash(value: &Value) -> Result<String, ContractError> {
    let encoded = canonical_json(value)?;
    let digest = Sha256::digest(encoded.as_bytes());
    Ok(format!("sha256:{digest:x}"))
}

pub fn parse_request(bytes: &[u8]) -> Result<ValidatedRequest, ContractError> {
    if bytes.is_empty() || bytes.len() > MAX_REQUEST_BYTES || bytes.contains(&0) {
        return Err(ContractError("request bytes are invalid"));
    }
    let value: Value =
        serde_json::from_slice(bytes).map_err(|_| ContractError("request JSON is invalid"))?;
    let object = exact_object(
        &value,
        &[
            "schema_version",
            "registry",
            "identity",
            "configuration",
            "configuration_sha256",
            "input",
            "input_sha256",
            "materials",
            "request_digest",
        ],
    )?;
    if string(object, "schema_version")? != REQUEST_SCHEMA_VERSION {
        return Err(ContractError("request schema is invalid"));
    }
    let request_digest = digest(object, "request_digest")?.to_owned();
    let mut body = object.clone();
    body.remove("request_digest");
    if canonical_hash(&Value::Object(body))? != request_digest {
        return Err(ContractError("request digest differs"));
    }
    if canonical_hash(
        object
            .get("configuration")
            .ok_or(ContractError("configuration missing"))?,
    )? != digest(object, "configuration_sha256")?
        || canonical_hash(object.get("input").ok_or(ContractError("input missing"))?)?
            != digest(object, "input_sha256")?
    {
        return Err(ContractError("request content digest differs"));
    }
    let registry = object
        .get("registry")
        .and_then(Value::as_object)
        .ok_or(ContractError("registry is invalid"))?;
    let identity = object
        .get("identity")
        .and_then(Value::as_object)
        .ok_or(ContractError("identity is invalid"))?;
    let phase = string(identity, "phase")?.to_owned();
    if string(registry, "phase")? != phase
        || !matches!(phase.as_str(), "pre_submit" | "post_submit")
    {
        return Err(ContractError("request phase differs"));
    }
    validate_registry(registry, &phase)?;
    validate_identity(identity, &phase)?;
    let configuration = object
        .get("configuration")
        .and_then(Value::as_object)
        .ok_or(ContractError("configuration is invalid"))?;
    let input = object
        .get("input")
        .and_then(Value::as_object)
        .ok_or(ContractError("input is invalid"))?;
    let context_roles = evaluation_context_roles(configuration, &phase, registry)?;
    let evaluation_context =
        validate_post_evaluation_context(input, identity, context_roles.as_ref())?;
    let materials = object
        .get("materials")
        .and_then(Value::as_array)
        .ok_or(ContractError("request materials are invalid"))?;
    if materials.is_empty() || materials.len() > 32 {
        return Err(ContractError("request materials are unbounded"));
    }
    let mut roles = BTreeSet::new();
    for material in materials {
        let material = material
            .as_object()
            .ok_or(ContractError("request material is invalid"))?;
        if string(material, "phase")? != phase
            || !roles.insert(string(material, "role")?)
            || !string(material, "media_type")?.contains('/')
        {
            return Err(ContractError("request material is invalid"));
        }
        if phase == "pre_submit" {
            exact_map(
                material,
                &[
                    "phase",
                    "role",
                    "prepared_generation_id",
                    "attempt_id",
                    "attempt_request_digest",
                    "archive_sha256",
                    "archive_byte_count",
                    "semantic_manifest_sha256",
                    "media_type",
                ],
            )?;
            if unsigned(material, "archive_byte_count")? > i64::MAX as u64 {
                return Err(ContractError("request material is invalid"));
            }
            digest(material, "attempt_request_digest")?;
            digest(material, "archive_sha256")?;
            digest(material, "semantic_manifest_sha256")?;
            if string(material, "prepared_generation_id")?
                != string(identity, "prepared_generation_id")?
                || string(material, "attempt_id")? != string(identity, "attempt_id")?
                || digest(material, "attempt_request_digest")?
                    != digest(identity, "attempt_request_digest")?
            {
                return Err(ContractError("request material identity differs"));
            }
        } else {
            exact_map(
                material,
                &[
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
                ],
            )?;
            if unsigned(material, "byte_count")? > i64::MAX as u64
                || unsigned(material, "submission_version")? == 0
                || unsigned(material, "verification_generation")? == 0
            {
                return Err(ContractError("request material is invalid"));
            }
            digest(material, "content_sha256")?;
            digest(material, "namespace_fingerprint")?;
            digest(material, "semantic_manifest_sha256")?;
            let role = string(material, "role")?;
            match role {
                CURRENT_ARCHIVE_ROLE => {
                    if string(material, "submission_id")? != string(identity, "submission_id")?
                        || unsigned(material, "submission_version")?
                            != unsigned(identity, "submission_version")?
                    {
                        return Err(ContractError("request material identity differs"));
                    }
                }
                PREDECESSOR_ARCHIVE_ROLE => {
                    let context = evaluation_context.as_ref().ok_or(ContractError(
                        "request predecessor material is unauthorized",
                    ))?;
                    if !context_roles
                        .as_ref()
                        .is_some_and(|selected| selected.contains(PREDECESSOR_ARCHIVE_ROLE))
                        || context.kind != "checker_remediation"
                        || Some(string(material, "submission_id")?)
                            != context.predecessor_submission_id.as_deref()
                        || Some(unsigned(material, "submission_version")?)
                            != context.predecessor_submission_version
                        || Some(digest(material, "content_sha256")?)
                            != context.predecessor_content_sha256.as_deref()
                        || Some(unsigned(material, "byte_count")?) != context.predecessor_byte_count
                        || Some(digest(material, "semantic_manifest_sha256")?)
                            != context.predecessor_semantic_manifest_sha256.as_deref()
                    {
                        return Err(ContractError("request predecessor material differs"));
                    }
                }
                _ => return Err(ContractError("request material role is invalid")),
            }
        }
    }
    if phase == "post_submit" {
        if !roles.contains(CURRENT_ARCHIVE_ROLE) {
            return Err(ContractError("request current material is missing"));
        }
        let predecessor_required = context_roles
            .as_ref()
            .is_some_and(|selected| selected.contains(PREDECESSOR_ARCHIVE_ROLE))
            && evaluation_context
                .as_ref()
                .is_some_and(|context| context.kind == "checker_remediation");
        if roles.contains(PREDECESSOR_ARCHIVE_ROLE) != predecessor_required {
            return Err(ContractError(
                "request predecessor material selection differs",
            ));
        }
    }
    let resources = registry
        .get("resources")
        .and_then(Value::as_object)
        .ok_or(ContractError("resources are invalid"))?;
    let limits = (
        unsigned(resources, "cpu_millis")?,
        unsigned(resources, "memory_bytes")?,
        unsigned(resources, "deadline_ms")?,
        unsigned(resources, "maximum_output_bytes")?,
    );
    if !(100..=64_000).contains(&limits.0)
        || !(16 * 1024 * 1024..=64 * 1024_u64.pow(3)).contains(&limits.1)
        || !(100..=3_600_000).contains(&limits.2)
        || !(256..=MAX_RESULT_BYTES as u64).contains(&limits.3)
    {
        return Err(ContractError("resource limits are invalid"));
    }
    let registry_entry_id = string(registry, "registry_entry_id")?.to_owned();
    let registry_entry_digest = digest(registry, "entry_digest")?.to_owned();
    let image_digest = digest(registry, "image_digest")?.to_owned();
    let configuration_digest = digest(object, "configuration_sha256")?.to_owned();
    let post_submit = phase == "post_submit";
    let post_material_roles = if post_submit {
        materials
            .iter()
            .map(|material| {
                material
                    .get("role")
                    .and_then(Value::as_str)
                    .map(str::to_owned)
                    .ok_or(ContractError("request material role is invalid"))
            })
            .collect::<Result<Vec<_>, _>>()?
    } else {
        Vec::new()
    };
    Ok(ValidatedRequest {
        value,
        request_digest,
        registry_entry_id,
        registry_entry_digest,
        image_digest,
        configuration_digest,
        phase,
        post_material_roles,
        evaluation_context_sha256: evaluation_context.map(|context| context.sha256),
        cpu_millis: limits.0,
        memory_bytes: limits.1,
        deadline_ms: limits.2,
        maximum_output_bytes: limits.3 as usize,
    })
}

pub fn completed_result(
    request: &ValidatedRequest,
    findings: Vec<Finding>,
) -> Result<Value, ContractError> {
    let failed = findings.iter().any(|finding| finding.level == "error");
    let findings =
        serde_json::to_value(findings).map_err(|_| ContractError("findings encoding failed"))?;
    let mut body = Map::new();
    body.insert(
        "schema_version".into(),
        Value::String(RESULT_SCHEMA_VERSION.into()),
    );
    body.insert(
        "request_digest".into(),
        Value::String(request.request_digest.clone()),
    );
    body.insert(
        "registry_entry_id".into(),
        Value::String(request.registry_entry_id.clone()),
    );
    body.insert(
        "registry_entry_digest".into(),
        Value::String(request.registry_entry_digest.clone()),
    );
    body.insert("phase".into(), Value::String(request.phase.clone()));
    body.insert("outcome".into(), Value::String("completed".into()));
    body.insert(
        "verdict".into(),
        Value::String(if failed { "failed" } else { "passed" }.into()),
    );
    body.insert("findings".into(), findings);
    body.insert("infrastructure_failure_code".into(), Value::Null);
    let digest = canonical_hash(&Value::Object(body.clone()))?;
    body.insert("result_digest".into(), Value::String(digest));
    let value = Value::Object(body);
    validate_result(&value, request)?;
    Ok(value)
}

fn validate_registry(registry: &Map<String, Value>, phase: &str) -> Result<(), ContractError> {
    exact_map(
        registry,
        &[
            "capability_id",
            "capability_version",
            "phase",
            "image_digest",
            "configuration_schema",
            "input_schema",
            "output_schema",
            "resources",
            "registry_entry_id",
            "entry_digest",
            "registration_operation_id",
            "registered_by_actor_profile_id",
            "authorization_decision_event_id",
            "created_at",
        ],
    )?;
    digest(registry, "image_digest")?;
    let entry_digest = digest(registry, "entry_digest")?;
    for (name, expected_id) in [
        ("configuration_schema", None),
        (
            "input_schema",
            Some(if phase == "pre_submit" {
                "external_checker_pre_submit_input"
            } else {
                "external_checker_post_submit_input"
            }),
        ),
        ("output_schema", Some("external_checker_result")),
    ] {
        let schema = exact_object(
            registry.get(name).ok_or(ContractError("schema missing"))?,
            &["schema_id", "schema_version", "document", "schema_sha256"],
        )?;
        if expected_id.is_some_and(|expected| string(schema, "schema_id").ok() != Some(expected))
            || canonical_hash(
                schema
                    .get("document")
                    .ok_or(ContractError("schema missing"))?,
            )? != digest(schema, "schema_sha256")?
            || canonical_json(
                schema
                    .get("document")
                    .ok_or(ContractError("schema missing"))?,
            )?
            .len()
                > 65_536
        {
            return Err(ContractError("registry schema is invalid"));
        }
    }
    let resources = exact_object(
        registry
            .get("resources")
            .ok_or(ContractError("resources missing"))?,
        &[
            "cpu_millis",
            "memory_bytes",
            "deadline_ms",
            "maximum_output_bytes",
        ],
    )?;
    for name in [
        "cpu_millis",
        "memory_bytes",
        "deadline_ms",
        "maximum_output_bytes",
    ] {
        unsigned(resources, name)?;
    }
    let mut spec = registry.clone();
    for field in [
        "registry_entry_id",
        "entry_digest",
        "registration_operation_id",
        "registered_by_actor_profile_id",
        "authorization_decision_event_id",
        "created_at",
    ] {
        spec.remove(field);
    }
    if canonical_hash(&Value::Object(spec))? != entry_digest {
        return Err(ContractError("registry entry digest differs"));
    }
    Ok(())
}

fn validate_identity(identity: &Map<String, Value>, phase: &str) -> Result<(), ContractError> {
    let fields = if phase == "pre_submit" {
        vec![
            "phase",
            "project_id",
            "task_id",
            "assignment_id",
            "prepared_generation_id",
            "attempt_id",
            "attempt_request_digest",
            "effective_plan_sha256",
        ]
    } else {
        vec![
            "phase",
            "project_id",
            "task_id",
            "assignment_id",
            "submission_id",
            "submission_version",
            "evaluation_request_id",
            "evaluation_request_digest",
            "evaluation_generation",
            "attempt_id",
            "result_id",
            "lease_id",
            "lease_generation",
            "lease_expires_at",
        ]
    };
    exact_map(identity, &fields)?;
    for (name, value) in identity {
        if name.ends_with("_digest") || name.ends_with("_sha256") {
            digest(identity, name)?;
        } else if name.ends_with("_version") || name.ends_with("_generation") {
            if unsigned(identity, name)? == 0 {
                return Err(ContractError("identity integer is invalid"));
            }
        } else if value.as_str().is_none() {
            return Err(ContractError("identity string is invalid"));
        }
    }
    Ok(())
}

fn evaluation_context_roles(
    configuration: &Map<String, Value>,
    phase: &str,
    registry: &Map<String, Value>,
) -> Result<Option<BTreeSet<String>>, ContractError> {
    let version = configuration.get(EVALUATION_CONTEXT_VERSION_KEY);
    let roles = configuration.get(EVALUATION_CONTEXT_ROLES_KEY);
    if configuration.keys().any(|key| {
        key.starts_with("workstream_evaluation_context_")
            && !matches!(
                key.as_str(),
                EVALUATION_CONTEXT_VERSION_KEY | EVALUATION_CONTEXT_ROLES_KEY
            )
    }) {
        return Err(ContractError("evaluation context configuration is invalid"));
    }
    if version.is_none() && roles.is_none() {
        return Ok(None);
    }
    if phase != "post_submit" || version.and_then(Value::as_str) != Some(EVALUATION_CONTEXT_VERSION)
    {
        return Err(ContractError("evaluation context configuration is invalid"));
    }
    let declared = registry
        .get("configuration_schema")
        .and_then(Value::as_object)
        .and_then(|schema| schema.get("document"))
        .and_then(Value::as_object)
        .and_then(|document| document.get("properties"))
        .and_then(Value::as_object)
        .is_some_and(|properties| {
            properties.contains_key(EVALUATION_CONTEXT_VERSION_KEY)
                && properties.contains_key(EVALUATION_CONTEXT_ROLES_KEY)
        });
    if !declared {
        return Err(ContractError(
            "evaluation context configuration is undeclared",
        ));
    }
    let values = roles
        .and_then(Value::as_array)
        .ok_or(ContractError("evaluation context roles are invalid"))?;
    let mut selected = BTreeSet::new();
    let mut previous: Option<&str> = None;
    for value in values {
        let role = value
            .as_str()
            .ok_or(ContractError("evaluation context roles are invalid"))?;
        if !matches!(role, PREDECESSOR_ARCHIVE_ROLE | PREDECESSOR_FINDINGS_ROLE)
            || previous.is_some_and(|item| item >= role)
            || !selected.insert(role.to_owned())
        {
            return Err(ContractError("evaluation context roles are invalid"));
        }
        previous = Some(role);
    }
    Ok(Some(selected))
}

fn validate_post_evaluation_context(
    input: &Map<String, Value>,
    identity: &Map<String, Value>,
    selected_roles: Option<&BTreeSet<String>>,
) -> Result<Option<PostEvaluationContext>, ContractError> {
    let context = input.get("evaluation_context");
    let Some(selected_roles) = selected_roles else {
        if context.is_some() {
            return Err(ContractError("evaluation context is unauthorized"));
        }
        return Ok(None);
    };
    let value = context.ok_or(ContractError("evaluation context is missing"))?;
    let context = exact_object(
        value,
        &[
            "schema_version",
            "kind",
            "source",
            "predecessor",
            "feedback",
        ],
    )?;
    if string(context, "schema_version")? != EVALUATION_CONTEXT_SCHEMA_VERSION {
        return Err(ContractError("evaluation context schema is invalid"));
    }
    let kind = string(context, "kind")?;
    let source_value = context
        .get("source")
        .ok_or(ContractError("source is missing"))?;
    let predecessor_value = context
        .get("predecessor")
        .ok_or(ContractError("predecessor is missing"))?;
    let feedback_value = context
        .get("feedback")
        .ok_or(ContractError("feedback is missing"))?;
    if kind == "initial" {
        if !source_value.is_null() || !predecessor_value.is_null() || !feedback_value.is_null() {
            return Err(ContractError("initial evaluation context is invalid"));
        }
        return Ok(Some(PostEvaluationContext {
            sha256: canonical_hash(value)?,
            kind: kind.into(),
            predecessor_submission_id: None,
            predecessor_submission_version: None,
            predecessor_content_sha256: None,
            predecessor_byte_count: None,
            predecessor_semantic_manifest_sha256: None,
        }));
    }
    if kind != "checker_remediation" {
        return Err(ContractError("evaluation context kind is invalid"));
    }
    let source = exact_object(
        source_value,
        &[
            "preparation_id",
            "preparation_sha256",
            "routing_manifest_id",
            "revision_round",
            "evaluation",
        ],
    )?;
    string(source, "preparation_id")?;
    digest(source, "preparation_sha256")?;
    string(source, "routing_manifest_id")?;
    unsigned(source, "revision_round")?;
    let evaluation = exact_object(
        source
            .get("evaluation")
            .ok_or(ContractError("source evaluation is missing"))?,
        &[
            "project_id",
            "task_id",
            "submission_id",
            "submission_version",
            "checker_run_id",
            "evaluation_request_id",
            "evaluation_request_digest",
            "evaluation_generation",
            "result_id",
            "result_digest",
            "completion_event_id",
            "routing_recommendation",
        ],
    )?;
    let predecessor = exact_object(
        predecessor_value,
        &[
            "submission_id",
            "submission_version",
            "content_sha256",
            "byte_count",
            "semantic_manifest_sha256",
        ],
    )?;
    let predecessor_id = string(predecessor, "submission_id")?;
    let predecessor_version = unsigned(predecessor, "submission_version")?;
    if predecessor_version == 0
        || unsigned(predecessor, "byte_count")? > i64::MAX as u64
        || string(evaluation, "project_id")? != string(identity, "project_id")?
        || string(evaluation, "task_id")? != string(identity, "task_id")?
        || string(evaluation, "submission_id")? != predecessor_id
        || unsigned(evaluation, "submission_version")? != predecessor_version
        || predecessor_id == string(identity, "submission_id")?
        || predecessor_version.checked_add(1) != Some(unsigned(identity, "submission_version")?)
        || unsigned(evaluation, "evaluation_generation")? == 0
        || string(evaluation, "routing_recommendation")? != "needs_revision"
    {
        return Err(ContractError("evaluation context source differs"));
    }
    for field in [
        "checker_run_id",
        "evaluation_request_id",
        "result_id",
        "completion_event_id",
    ] {
        if string(evaluation, field)?.is_empty() {
            return Err(ContractError("evaluation context source is invalid"));
        }
    }
    digest(evaluation, "evaluation_request_digest")?;
    digest(evaluation, "result_digest")?;
    let predecessor_content_sha256 = digest(predecessor, "content_sha256")?;
    let predecessor_semantic_manifest_sha256 = digest(predecessor, "semantic_manifest_sha256")?;
    let feedback_required = selected_roles.contains(PREDECESSOR_FINDINGS_ROLE);
    if feedback_required {
        let feedback = feedback_value
            .as_object()
            .ok_or(ContractError("revision feedback is missing"))?;
        validate_revision_feedback(feedback, identity, evaluation)?;
    } else if !feedback_value.is_null() {
        return Err(ContractError("revision feedback is unauthorized"));
    }
    Ok(Some(PostEvaluationContext {
        sha256: canonical_hash(value)?,
        kind: kind.into(),
        predecessor_submission_id: Some(predecessor_id.into()),
        predecessor_submission_version: Some(predecessor_version),
        predecessor_content_sha256: Some(predecessor_content_sha256.into()),
        predecessor_byte_count: Some(unsigned(predecessor, "byte_count")?),
        predecessor_semantic_manifest_sha256: Some(predecessor_semantic_manifest_sha256.into()),
    }))
}

fn validate_revision_feedback(
    feedback: &Map<String, Value>,
    identity: &Map<String, Value>,
    evaluation: &Map<String, Value>,
) -> Result<(), ContractError> {
    exact_map(feedback, &["source", "policy_sha256", "members"])?;
    digest(feedback, "policy_sha256")?;
    if canonical_json(&Value::Object(feedback.clone()))?.len() > MAX_REVISION_FEEDBACK_BYTES {
        return Err(ContractError("revision feedback is unbounded"));
    }
    let source = exact_object(
        feedback
            .get("source")
            .ok_or(ContractError("revision feedback source is missing"))?,
        &[
            "project_id",
            "task_id",
            "assignment_id",
            "submission_id",
            "submission_version",
            "completion_event_id",
            "result",
        ],
    )?;
    let result = exact_object(
        source
            .get("result")
            .ok_or(ContractError("revision feedback result is missing"))?,
        &[
            "schema_version",
            "request_id",
            "request_digest",
            "attempt_id",
            "evaluation_generation",
            "result_id",
            "result_digest",
        ],
    )?;
    if string(source, "project_id")? != string(identity, "project_id")?
        || string(source, "task_id")? != string(identity, "task_id")?
        || string(source, "assignment_id")? != string(identity, "assignment_id")?
        || string(source, "submission_id")? != string(evaluation, "submission_id")?
        || unsigned(source, "submission_version")? != unsigned(evaluation, "submission_version")?
        || string(source, "completion_event_id")? != string(evaluation, "completion_event_id")?
        || string(result, "schema_version")? != "post_submit_current_result_reference"
        || string(result, "request_id")? != string(evaluation, "evaluation_request_id")?
        || digest(result, "request_digest")? != digest(evaluation, "evaluation_request_digest")?
        || string(result, "attempt_id")? != string(evaluation, "checker_run_id")?
        || unsigned(result, "evaluation_generation")?
            != unsigned(evaluation, "evaluation_generation")?
        || string(result, "result_id")? != string(evaluation, "result_id")?
        || digest(result, "result_digest")? != digest(evaluation, "result_digest")?
    {
        return Err(ContractError("revision feedback source differs"));
    }
    let members = feedback
        .get("members")
        .and_then(Value::as_array)
        .ok_or(ContractError("revision feedback members are invalid"))?;
    let mut requirements = BTreeSet::new();
    for (order, member) in members.iter().enumerate() {
        let member = exact_object(
            member,
            &[
                "order",
                "requirement_id",
                "registry_entry_id",
                "registry_entry_digest",
                "configuration_sha256",
                "request_digest",
                "result_digest",
                "verdict",
                "findings",
            ],
        )?;
        let requirement = string(member, "requirement_id")?;
        if unsigned(member, "order")? != order as u64
            || requirement.is_empty()
            || requirement.chars().count() > 100
            || !requirements.insert(requirement)
        {
            return Err(ContractError("revision feedback member order is invalid"));
        }
        string(member, "registry_entry_id")?;
        for field in [
            "registry_entry_digest",
            "configuration_sha256",
            "request_digest",
            "result_digest",
        ] {
            digest(member, field)?;
        }
        let verdict = string(member, "verdict")?;
        if !matches!(verdict, "passed" | "failed") {
            return Err(ContractError("revision feedback verdict is invalid"));
        }
        let findings = member
            .get("findings")
            .and_then(Value::as_array)
            .ok_or(ContractError("revision feedback findings are invalid"))?;
        if findings.len() > 256 {
            return Err(ContractError("revision feedback findings are unbounded"));
        }
        let has_error = findings.iter().try_fold(false, |found, finding| {
            Ok(found || validate_finding(finding)?)
        })?;
        if (verdict == "failed") != has_error {
            return Err(ContractError("revision feedback verdict differs"));
        }
    }
    Ok(())
}

fn validate_finding(value: &Value) -> Result<bool, ContractError> {
    let keys = exact_object(
        value,
        &["check_id", "code", "level", "message", "path", "line"],
    )?;
    let finding: Finding =
        serde_json::from_value(value.clone()).map_err(|_| ContractError("finding is invalid"))?;
    if !keys.contains_key("path")
        || !keys.contains_key("line")
        || !is_identifier(&finding.check_id)
        || !is_identifier(&finding.code)
        || finding.message.is_empty()
        || finding.message.chars().count() > 4096
        || !matches!(
            finding.level.as_str(),
            "info" | "warning" | "error" | "coverage_incomplete"
        )
        || finding
            .path
            .as_ref()
            .is_some_and(|path| !is_safe_finding_path(path))
        || finding
            .line
            .is_some_and(|line| finding.path.is_none() || !(1..=10_000_000).contains(&line))
    {
        return Err(ContractError("finding is invalid"));
    }
    Ok(finding.level == "error")
}

pub fn validate_result(value: &Value, request: &ValidatedRequest) -> Result<(), ContractError> {
    let object = exact_object(
        value,
        &[
            "schema_version",
            "request_digest",
            "registry_entry_id",
            "registry_entry_digest",
            "phase",
            "outcome",
            "verdict",
            "findings",
            "infrastructure_failure_code",
            "result_digest",
        ],
    )?;
    if string(object, "schema_version")? != RESULT_SCHEMA_VERSION
        || digest(object, "request_digest")? != request.request_digest
        || string(object, "registry_entry_id")? != request.registry_entry_id
        || digest(object, "registry_entry_digest")? != request.registry_entry_digest
        || string(object, "phase")? != request.phase
    {
        return Err(ContractError("result request identity differs"));
    }
    let result_digest = digest(object, "result_digest")?;
    let mut body = object.clone();
    body.remove("result_digest");
    if canonical_hash(&Value::Object(body))? != result_digest {
        return Err(ContractError("result digest differs"));
    }
    let outcome = string(object, "outcome")?;
    let findings = object
        .get("findings")
        .and_then(Value::as_array)
        .ok_or(ContractError("result findings are invalid"))?;
    if findings.len() > 256 {
        return Err(ContractError("result findings are unbounded"));
    }
    let verdict = object
        .get("verdict")
        .ok_or(ContractError("result verdict missing"))?;
    let failure = object
        .get("infrastructure_failure_code")
        .ok_or(ContractError("result failure missing"))?;
    if outcome == "infrastructure_failed" {
        let code = failure
            .as_str()
            .ok_or(ContractError("infrastructure result is invalid"))?;
        if !verdict.is_null()
            || !findings.is_empty()
            || !matches!(
                code,
                "capacity_exceeded"
                    | "deadline_exceeded"
                    | "material_unavailable"
                    | "implementation_unavailable"
                    | "invalid_output"
            )
        {
            return Err(ContractError("infrastructure result is invalid"));
        }
    } else if outcome == "completed" {
        let passed = verdict
            .as_str()
            .ok_or(ContractError("completed result is invalid"))?;
        if !failure.is_null() || !matches!(passed, "passed" | "failed") {
            return Err(ContractError("completed result is invalid"));
        }
        let has_error = findings
            .iter()
            .try_fold(false, |found, item| Ok(found || validate_finding(item)?))?;
        if (passed == "failed") != has_error {
            return Err(ContractError("result verdict differs"));
        }
    } else {
        return Err(ContractError("result outcome is invalid"));
    }
    let encoded = canonical_json(value)?.into_bytes();
    if encoded.len() > MAX_RESULT_BYTES || encoded.len() > request.maximum_output_bytes {
        return Err(ContractError("result exceeds output bound"));
    }
    Ok(())
}

pub fn infrastructure_result(
    request: &ValidatedRequest,
    code: &str,
) -> Result<Value, ContractError> {
    let mut body = Map::new();
    body.insert(
        "schema_version".into(),
        Value::String(RESULT_SCHEMA_VERSION.into()),
    );
    body.insert(
        "request_digest".into(),
        Value::String(request.request_digest.clone()),
    );
    body.insert(
        "registry_entry_id".into(),
        Value::String(request.registry_entry_id.clone()),
    );
    body.insert(
        "registry_entry_digest".into(),
        Value::String(request.registry_entry_digest.clone()),
    );
    body.insert("phase".into(), Value::String(request.phase.clone()));
    body.insert(
        "outcome".into(),
        Value::String("infrastructure_failed".into()),
    );
    body.insert("verdict".into(), Value::Null);
    body.insert("findings".into(), Value::Array(Vec::new()));
    body.insert(
        "infrastructure_failure_code".into(),
        Value::String(code.into()),
    );
    let digest = canonical_hash(&Value::Object(body.clone()))?;
    body.insert("result_digest".into(), Value::String(digest));
    let value = Value::Object(body);
    validate_result(&value, request)?;
    Ok(value)
}

fn write_canonical(value: &Value, output: &mut String) -> Result<(), ContractError> {
    match value {
        Value::Null => output.push_str("null"),
        Value::Bool(value) => output.push_str(if *value { "true" } else { "false" }),
        Value::Number(value) => output.push_str(&canonical_number(&value.to_string())?),
        Value::String(value) => {
            if value.contains('\0') {
                return Err(ContractError("NUL is not canonical JSON"));
            }
            output.push_str(
                &serde_json::to_string(value).map_err(|_| ContractError("string is invalid"))?,
            );
        }
        Value::Array(values) => {
            output.push('[');
            for (index, item) in values.iter().enumerate() {
                if index > 0 {
                    output.push(',');
                }
                write_canonical(item, output)?;
            }
            output.push(']');
        }
        Value::Object(values) => {
            output.push('{');
            let mut keys: Vec<_> = values.keys().collect();
            keys.sort();
            for (index, key) in keys.into_iter().enumerate() {
                if key.contains('\0') {
                    return Err(ContractError("NUL is not canonical JSON"));
                }
                if index > 0 {
                    output.push(',');
                }
                output.push_str(
                    &serde_json::to_string(key).map_err(|_| ContractError("key is invalid"))?,
                );
                output.push(':');
                write_canonical(&values[key], output)?;
            }
            output.push('}');
        }
    }
    Ok(())
}

fn canonical_number(source: &str) -> Result<String, ContractError> {
    let is_float = source.contains(['.', 'e', 'E']);
    if !is_float {
        return Ok(if source == "-0" { "0" } else { source }.into());
    }
    let value: f64 = source
        .parse()
        .map_err(|_| ContractError("number is invalid"))?;
    if !value.is_finite() {
        return Err(ContractError("number is invalid"));
    }
    if value == 0.0 {
        return Ok("0.0".into());
    }
    let normalized = shortest_python_float(value)?;
    let Some(position) = normalized.find(['e', 'E']) else {
        if value.fract() == 0.0 && value.abs() < 1e16 {
            return Ok(format!("{normalized}.0"));
        }
        return Ok(normalized);
    };
    let (mantissa, exponent) = normalized.split_at(position);
    let exponent: i32 = exponent[1..]
        .parse()
        .map_err(|_| ContractError("number is invalid"))?;
    let negative = mantissa.starts_with('-');
    let unsigned = mantissa.trim_start_matches('-');
    let decimal = unsigned.find('.').unwrap_or(unsigned.len());
    let digits: String = unsigned.chars().filter(|item| *item != '.').collect();
    let new_decimal = decimal as i32 + exponent;
    let mut result = String::new();
    if negative {
        result.push('-');
    }
    if new_decimal <= 0 {
        result.push_str("0.");
        for _ in 0..-new_decimal {
            result.push('0');
        }
        result.push_str(&digits);
    } else if new_decimal as usize >= digits.len() {
        result.push_str(&digits);
        for _ in digits.len()..new_decimal as usize {
            result.push('0');
        }
    } else {
        let split = new_decimal as usize;
        write!(result, "{}.{}", &digits[..split], &digits[split..]).unwrap();
    }
    if value.fract() == 0.0 && value.abs() < 1e16 && !result.contains('.') {
        result.push_str(".0");
    }
    Ok(result)
}

fn shortest_python_float(value: f64) -> Result<String, ContractError> {
    // Python's float repr and Rust's Display can select different decimal
    // members of the same shortest round-trip interval. The Python contract
    // selects the correctly rounded decimal at the first significant-digit
    // precision that round-trips to the original IEEE-754 value.
    for precision in 1..=17 {
        let candidate = format!("{:.*e}", precision - 1, value);
        let round_trip: f64 = candidate
            .parse()
            .map_err(|_| ContractError("number is invalid"))?;
        if round_trip.to_bits() == value.to_bits() {
            return Ok(candidate);
        }
    }
    Err(ContractError("number is invalid"))
}

fn exact_object<'a>(
    value: &'a Value,
    fields: &[&str],
) -> Result<&'a Map<String, Value>, ContractError> {
    let object = value
        .as_object()
        .ok_or(ContractError("object is invalid"))?;
    let expected: BTreeSet<_> = fields.iter().copied().collect();
    let actual: BTreeSet<_> = object.keys().map(String::as_str).collect();
    if actual != expected {
        return Err(ContractError("object fields are invalid"));
    }
    Ok(object)
}

fn exact_map(object: &Map<String, Value>, fields: &[&str]) -> Result<(), ContractError> {
    let expected: BTreeSet<_> = fields.iter().copied().collect();
    let actual: BTreeSet<_> = object.keys().map(String::as_str).collect();
    if actual != expected {
        return Err(ContractError("object fields are invalid"));
    }
    Ok(())
}

fn string<'a>(object: &'a Map<String, Value>, key: &str) -> Result<&'a str, ContractError> {
    object
        .get(key)
        .and_then(Value::as_str)
        .ok_or(ContractError("string field is invalid"))
}

fn digest<'a>(object: &'a Map<String, Value>, key: &str) -> Result<&'a str, ContractError> {
    let value = string(object, key)?;
    if value.len() != 71
        || !value.starts_with("sha256:")
        || !value[7..]
            .bytes()
            .all(|item| item.is_ascii_hexdigit() && !item.is_ascii_uppercase())
    {
        return Err(ContractError("digest is invalid"));
    }
    Ok(value)
}

fn unsigned(object: &Map<String, Value>, key: &str) -> Result<u64, ContractError> {
    object
        .get(key)
        .and_then(Value::as_u64)
        .ok_or(ContractError("integer field is invalid"))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn resign_request(mut request: Value) -> Value {
        request["configuration_sha256"] =
            Value::String(canonical_hash(&request["configuration"]).unwrap());
        request["input_sha256"] = Value::String(canonical_hash(&request["input"]).unwrap());
        let registry = request["registry"].as_object_mut().unwrap();
        for name in ["configuration_schema", "input_schema"] {
            let document = registry[name]["document"].clone();
            registry[name]["schema_sha256"] = Value::String(canonical_hash(&document).unwrap());
        }
        let mut spec = registry.clone();
        for field in [
            "registry_entry_id",
            "entry_digest",
            "registration_operation_id",
            "registered_by_actor_profile_id",
            "authorization_decision_event_id",
            "created_at",
        ] {
            spec.remove(field);
        }
        registry.insert(
            "entry_digest".into(),
            Value::String(canonical_hash(&Value::Object(spec)).unwrap()),
        );
        let mut body = request.as_object().unwrap().clone();
        body.remove("request_digest");
        request["request_digest"] = Value::String(canonical_hash(&Value::Object(body)).unwrap());
        request
    }

    fn post_context_request(kind: &str, selected_roles: &[&str]) -> Value {
        let digest = |byte: char| format!("sha256:{}", byte.to_string().repeat(64));
        let id = |byte: char| format!("{0}{0}{0}{0}{0}{0}{0}{0}-0000-4000-8000-000000000000", byte);
        let mut request: Value =
            serde_json::from_slice(include_bytes!("../../fixtures/request.json")).unwrap();
        request["registry"]["phase"] = Value::String("post_submit".into());
        request["registry"]["input_schema"]["schema_id"] =
            Value::String("external_checker_post_submit_input".into());
        request["registry"]["configuration_schema"]["document"]["properties"]
            [EVALUATION_CONTEXT_VERSION_KEY] =
            serde_json::json!({"type": "string", "const": EVALUATION_CONTEXT_VERSION});
        request["registry"]["configuration_schema"]["document"]["properties"]
            [EVALUATION_CONTEXT_ROLES_KEY] = serde_json::json!({
            "type": "array",
            "items": {"type": "string", "enum": [
                PREDECESSOR_FINDINGS_ROLE, PREDECESSOR_ARCHIVE_ROLE
            ]},
            "uniqueItems": true
        });
        request["identity"] = serde_json::json!({
            "phase": "post_submit", "project_id": id('1'), "task_id": id('2'),
            "assignment_id": id('3'), "submission_id": id('4'), "submission_version": 2,
            "evaluation_request_id": id('5'), "evaluation_request_digest": digest('5'),
            "evaluation_generation": 3, "attempt_id": id('6'), "result_id": id('7'),
            "lease_id": id('8'), "lease_generation": 4,
            "lease_expires_at": "2026-10-11T12:00:00+00:00"
        });
        request["configuration"] = serde_json::json!({
            EVALUATION_CONTEXT_VERSION_KEY: EVALUATION_CONTEXT_VERSION,
            EVALUATION_CONTEXT_ROLES_KEY: selected_roles,
        });
        let prior_id = id('0');
        let evaluation = serde_json::json!({
            "project_id": id('1'), "task_id": id('2'), "submission_id": prior_id,
            "submission_version": 1, "checker_run_id": id('9'),
            "evaluation_request_id": id('a'), "evaluation_request_digest": digest('a'),
            "evaluation_generation": 1, "result_id": id('b'), "result_digest": digest('b'),
            "completion_event_id": id('c'), "routing_recommendation": "needs_revision"
        });
        let result_reference = serde_json::json!({
            "schema_version": "post_submit_current_result_reference",
            "request_id": evaluation["evaluation_request_id"],
            "request_digest": evaluation["evaluation_request_digest"],
            "attempt_id": evaluation["checker_run_id"],
            "evaluation_generation": 1, "result_id": evaluation["result_id"],
            "result_digest": evaluation["result_digest"],
        });
        let feedback = serde_json::json!({
            "source": {
                "project_id": id('1'), "task_id": id('2'), "assignment_id": id('3'),
                "submission_id": prior_id, "submission_version": 1,
                "completion_event_id": evaluation["completion_event_id"],
                "result": result_reference,
            },
            "policy_sha256": digest('c'),
            "members": [],
        });
        let context = if kind == "initial" {
            serde_json::json!({
                "schema_version": EVALUATION_CONTEXT_SCHEMA_VERSION, "kind": "initial",
                "source": null, "predecessor": null, "feedback": null,
            })
        } else {
            serde_json::json!({
                "schema_version": EVALUATION_CONTEXT_SCHEMA_VERSION,
                "kind": "checker_remediation",
                "source": {
                    "preparation_id": id('d'), "preparation_sha256": digest('d'),
                    "routing_manifest_id": id('e'), "revision_round": 1,
                    "evaluation": evaluation,
                },
                "predecessor": {
                    "submission_id": prior_id, "submission_version": 1,
                    "content_sha256": digest('e'), "byte_count": 0,
                    "semantic_manifest_sha256": digest('f'),
                },
                "feedback": if selected_roles.contains(&PREDECESSOR_FINDINGS_ROLE) {
                    feedback
                } else {
                    Value::Null
                },
            })
        };
        request["input"] = serde_json::json!({
            "task_version": "v1", "evaluation_context": context,
        });
        let current = serde_json::json!({
            "phase": "post_submit", "role": CURRENT_ARCHIVE_ROLE,
            "submission_id": id('4'), "submission_version": 2,
            "binding_id": id('1'), "content_id": id('2'), "replica_id": id('3'),
            "content_sha256": digest('1'), "byte_count": 0, "media_type": "application/zip",
            "evidence_id": id('4'), "verification_receipt_id": id('5'),
            "verification_job_id": id('6'), "verification_generation": 1,
            "namespace_fingerprint": digest('2'), "semantic_manifest_sha256": digest('3'),
        });
        let prior = serde_json::json!({
            "phase": "post_submit", "role": PREDECESSOR_ARCHIVE_ROLE,
            "submission_id": id('0'), "submission_version": 1,
            "binding_id": id('7'), "content_id": id('8'), "replica_id": id('9'),
            "content_sha256": digest('e'), "byte_count": 0, "media_type": "application/zip",
            "evidence_id": id('a'), "verification_receipt_id": id('b'),
            "verification_job_id": id('c'), "verification_generation": 1,
            "namespace_fingerprint": digest('4'), "semantic_manifest_sha256": digest('f'),
        });
        request["materials"] =
            if kind != "initial" && selected_roles.contains(&PREDECESSOR_ARCHIVE_ROLE) {
                serde_json::json!([current, prior])
            } else {
                serde_json::json!([current])
            };
        resign_request(request)
    }

    #[test]
    fn canonical_numeric_encoding_matches_python_contract() {
        let value: Value = serde_json::from_str(r#"{"minimum":1e-6}"#).unwrap();
        assert_eq!(canonical_json(&value).unwrap(), r#"{"minimum":0.000001}"#);
        assert_eq!(
            canonical_hash(&value).unwrap(),
            "sha256:e084f70f19f83edfde8a2b57061cd7734340a5be2e7d127e3b73c090556478a7"
        );
    }

    #[test]
    fn shared_numeric_fixtures_preserve_python_precision() {
        let cases: Value =
            serde_json::from_slice(include_bytes!("../../fixtures/canonical_numbers.json"))
                .unwrap();
        for case in cases.as_array().unwrap() {
            let source = case["json"].as_str().unwrap();
            let value: Value = serde_json::from_str(source).unwrap();
            assert_eq!(canonical_json(&value).unwrap(), case["canonical"]);
        }
    }

    #[test]
    fn canonical_json_rejects_nul() {
        assert!(canonical_json(&serde_json::json!({"safe": "bad\0value"})).is_err());
        assert!(canonical_json(&serde_json::json!({"bad\0key": "value"})).is_err());
    }

    #[test]
    fn shared_python_fixtures_preserve_request_and_result_identity() {
        let request = parse_request(include_bytes!("../../fixtures/request.json"))
            .expect("Python request fixture must satisfy the Rust contract");
        assert_eq!(
            request.request_digest,
            "sha256:a06707b14348ffe5ef22a55de8d4ec4845c9029da7180d5731fb2c120b5591f3"
        );
        let result: Value = serde_json::from_slice(include_bytes!("../../fixtures/result.json"))
            .expect("result fixture is JSON");
        validate_result(&result, &request).expect("Python result fixture must bind the request");

        let mut changed: Value =
            serde_json::from_slice(include_bytes!("../../fixtures/request.json")).unwrap();
        changed["configuration"]["threshold"] = serde_json::json!(0.000002);
        assert!(parse_request(&serde_json::to_vec(&changed).unwrap()).is_err());

        let mut nested_extra: Value =
            serde_json::from_slice(include_bytes!("../../fixtures/request.json")).unwrap();
        nested_extra["identity"]["unchecked"] = Value::Bool(true);
        let mut body = nested_extra.as_object().unwrap().clone();
        body.remove("request_digest");
        nested_extra["request_digest"] =
            Value::String(canonical_hash(&Value::Object(body)).unwrap());
        assert!(parse_request(&serde_json::to_vec(&nested_extra).unwrap()).is_err());

        let mut unicode_result = result.clone();
        unicode_result["verdict"] = Value::String("failed".into());
        unicode_result["findings"] = serde_json::json!([{
            "check_id": "unicode",
            "code": "unicode",
            "level": "error",
            "message": "汉".repeat(2_000),
            "path": "路".repeat(500),
            "line": 7,
        }]);
        let mut body = unicode_result.as_object().unwrap().clone();
        body.remove("result_digest");
        unicode_result["result_digest"] =
            Value::String(canonical_hash(&Value::Object(body)).unwrap());
        validate_result(&unicode_result, &request)
            .expect("character ceilings must match Python rather than UTF-8 bytes");

        let resign = |mut value: Value| {
            let mut body = value.as_object().unwrap().clone();
            body.remove("result_digest");
            value["result_digest"] = Value::String(canonical_hash(&Value::Object(body)).unwrap());
            value
        };
        let mut coverage = result.clone();
        coverage["findings"] = serde_json::json!([{
            "check_id": "coverage.files",
            "code": "coverage.unreadable",
            "level": "coverage_incomplete",
            "message": "one file could not be evaluated",
            "path": "src/main.rs",
            "line": null,
        }]);
        validate_result(&resign(coverage.clone()), &request)
            .expect("coverage gaps alone keep a passed verdict");
        let mut orphan_line = coverage.clone();
        orphan_line["findings"][0]["path"] = Value::Null;
        orphan_line["findings"][0]["line"] = serde_json::json!(3);
        assert!(validate_result(&resign(orphan_line), &request).is_err());
        let mut missing_check = coverage.clone();
        missing_check["findings"][0]
            .as_object_mut()
            .unwrap()
            .remove("check_id");
        assert!(validate_result(&resign(missing_check), &request).is_err());
        for unsafe_path in [
            "../x",
            "/etc/passwd",
            "a//b",
            "bidi\u{202e}exe",
            "c:/x",
            "dir/ ",
        ] {
            let mut traversal = coverage.clone();
            traversal["findings"][0]["path"] = Value::String(unsafe_path.into());
            assert!(
                validate_result(&resign(traversal), &request).is_err(),
                "{unsafe_path}"
            );
        }
        let mut missing_line = coverage.clone();
        missing_line["findings"][0]
            .as_object_mut()
            .unwrap()
            .remove("line");
        assert!(validate_result(&resign(missing_line), &request).is_err());
        let mut uppercase_check = coverage;
        uppercase_check["findings"][0]["check_id"] = Value::String("Coverage".into());
        assert!(validate_result(&resign(uppercase_check), &request).is_err());
    }

    #[test]
    fn post_context_closes_roles_source_feedback_and_predecessor_material() {
        let request = post_context_request(
            "checker_remediation",
            &[PREDECESSOR_FINDINGS_ROLE, PREDECESSOR_ARCHIVE_ROLE],
        );
        let checked = parse_request(&serde_json::to_vec(&request).unwrap()).unwrap();
        assert_eq!(
            checked.post_material_roles,
            [CURRENT_ARCHIVE_ROLE, PREDECESSOR_ARCHIVE_ROLE]
        );
        assert_eq!(
            checked.evaluation_context_sha256.as_deref(),
            Some(
                canonical_hash(&request["input"]["evaluation_context"])
                    .unwrap()
                    .as_str()
            )
        );

        let mut missing_prior = request.clone();
        missing_prior["materials"].as_array_mut().unwrap().pop();
        assert!(
            parse_request(&serde_json::to_vec(&resign_request(missing_prior)).unwrap()).is_err()
        );

        let mut substituted_result = request.clone();
        substituted_result["input"]["evaluation_context"]["feedback"]["source"]["result"]
            ["result_digest"] = Value::String(format!("sha256:{}", "0".repeat(64)));
        assert!(
            parse_request(&serde_json::to_vec(&resign_request(substituted_result)).unwrap())
                .is_err()
        );
        let mut undeclared = request.clone();
        undeclared["registry"]["configuration_schema"]["document"]["properties"]
            .as_object_mut()
            .unwrap()
            .remove(EVALUATION_CONTEXT_ROLES_KEY);
        assert!(parse_request(&serde_json::to_vec(&resign_request(undeclared)).unwrap()).is_err());

        let initial = post_context_request(
            "initial",
            &[PREDECESSOR_FINDINGS_ROLE, PREDECESSOR_ARCHIVE_ROLE],
        );
        let initial = parse_request(&serde_json::to_vec(&initial).unwrap()).unwrap();
        assert_eq!(initial.post_material_roles, [CURRENT_ARCHIVE_ROLE]);

        let mut unknown = request;
        unknown["configuration"]["workstream_evaluation_context_unknown"] = Value::Bool(true);
        assert!(parse_request(&serde_json::to_vec(&resign_request(unknown)).unwrap()).is_err());
    }
}
