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
pub const TERMINAL_BENCHMARK_PLAN_VERSION: &str = "terminal_benchmark_build_oracle.v1";

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
    pub cpu_millis: u64,
    pub memory_bytes: u64,
    pub deadline_ms: u64,
    pub maximum_output_bytes: usize,
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

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct TerminalBenchmarkPlan {
    pub schema_version: String,
    pub request_digest: String,
    pub registry_entry_id: String,
    pub registry_entry_digest: String,
    pub checker_image_digest: String,
    pub configuration_digest: String,
    pub external_task_id: String,
    pub plan_digest: String,
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
            if string(material, "submission_id")? != string(identity, "submission_id")?
                || unsigned(material, "submission_version")?
                    != unsigned(identity, "submission_version")?
            {
                return Err(ContractError("request material identity differs"));
            }
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
    Ok(ValidatedRequest {
        value,
        request_digest,
        registry_entry_id,
        registry_entry_digest,
        image_digest,
        configuration_digest,
        phase,
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

pub fn terminal_benchmark_plan(
    request: &ValidatedRequest,
    external_task_id: &str,
) -> Result<Value, ContractError> {
    if request.phase != "post_submit" || !is_identifier(external_task_id) {
        return Err(ContractError("terminal benchmark plan identity is invalid"));
    }
    let mut body = Map::new();
    body.insert(
        "schema_version".into(),
        Value::String(TERMINAL_BENCHMARK_PLAN_VERSION.into()),
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
    body.insert(
        "checker_image_digest".into(),
        Value::String(request.image_digest.clone()),
    );
    body.insert(
        "configuration_digest".into(),
        Value::String(request.configuration_digest.clone()),
    );
    body.insert(
        "external_task_id".into(),
        Value::String(external_task_id.into()),
    );
    let digest = canonical_hash(&Value::Object(body.clone()))?;
    body.insert("plan_digest".into(), Value::String(digest));
    let value = Value::Object(body);
    parse_terminal_benchmark_plan(&value, request)?;
    Ok(value)
}

pub fn parse_terminal_benchmark_plan(
    value: &Value,
    request: &ValidatedRequest,
) -> Result<TerminalBenchmarkPlan, ContractError> {
    let object = exact_object(
        value,
        &[
            "schema_version",
            "request_digest",
            "registry_entry_id",
            "registry_entry_digest",
            "checker_image_digest",
            "configuration_digest",
            "external_task_id",
            "plan_digest",
        ],
    )?;
    let plan: TerminalBenchmarkPlan = serde_json::from_value(value.clone())
        .map_err(|_| ContractError("terminal benchmark plan is invalid"))?;
    let mut body = object.clone();
    body.remove("plan_digest");
    if request.phase != "post_submit"
        || plan.schema_version != TERMINAL_BENCHMARK_PLAN_VERSION
        || plan.request_digest != request.request_digest
        || plan.registry_entry_id != request.registry_entry_id
        || plan.registry_entry_digest != request.registry_entry_digest
        || plan.checker_image_digest != request.image_digest
        || plan.configuration_digest != request.configuration_digest
        || !is_identifier(&plan.external_task_id)
        || !valid_digest_text(&plan.plan_digest)
        || canonical_hash(&Value::Object(body))? != plan.plan_digest
    {
        return Err(ContractError("terminal benchmark plan identity differs"));
    }
    Ok(plan)
}

fn valid_digest_text(value: &str) -> bool {
    value.len() == 71
        && value.starts_with("sha256:")
        && value[7..]
            .chars()
            .all(|item| item.is_ascii_hexdigit() && !item.is_ascii_uppercase())
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
        let has_error = findings.iter().try_fold(false, |found, item| {
            // Python always serializes both optional location keys before hashing.
            let keys = item
                .as_object()
                .ok_or(ContractError("finding is invalid"))?;
            if !keys.contains_key("path") || !keys.contains_key("line") {
                return Err(ContractError("finding is invalid"));
            }
            let finding: Finding = serde_json::from_value(item.clone())
                .map_err(|_| ContractError("finding is invalid"))?;
            if !is_identifier(&finding.check_id)
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
            Ok(found || finding.level == "error")
        })?;
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
    fn terminal_benchmark_plan_binds_only_request_facts_and_rejects_substitution() {
        let request = ValidatedRequest {
            value: serde_json::json!({}),
            request_digest: format!("sha256:{}", "0".repeat(64)),
            registry_entry_id: "019a0000-0000-7000-8000-000000000001".into(),
            registry_entry_digest: format!("sha256:{}", "1".repeat(64)),
            image_digest: format!("sha256:{}", "2".repeat(64)),
            configuration_digest: format!("sha256:{}", "3".repeat(64)),
            phase: "post_submit".into(),
            cpu_millis: 1000,
            memory_bytes: 256 * 1024 * 1024,
            deadline_ms: 30_000,
            maximum_output_bytes: 65_536,
        };
        let plan = terminal_benchmark_plan(&request, "terminal-ledger-reconcile").unwrap();
        let parsed = parse_terminal_benchmark_plan(&plan, &request).unwrap();
        assert_eq!(parsed.request_digest, request.request_digest);
        assert!(plan.get("grant_id").is_none());
        assert!(plan.get("grant_binding_digest").is_none());

        let mut substituted = request.clone();
        substituted.configuration_digest = format!("sha256:{}", "4".repeat(64));
        assert!(parse_terminal_benchmark_plan(&plan, &substituted).is_err());
        let mut extra = plan;
        extra["grant_id"] = Value::String("extract_0123456789abcdef0123456789abcdef".into());
        assert!(parse_terminal_benchmark_plan(&extra, &request).is_err());
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
}
