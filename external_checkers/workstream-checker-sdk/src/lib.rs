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
    pub phase: String,
    pub cpu_millis: u64,
    pub memory_bytes: u64,
    pub deadline_ms: u64,
    pub maximum_output_bytes: usize,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Finding {
    pub code: String,
    pub level: String,
    pub message: String,
    pub path: Option<String>,
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
    if materials.len() > 32 {
        return Err(ContractError("request materials are unbounded"));
    }
    let mut roles = BTreeSet::new();
    for material in materials {
        let material = exact_object(
            material,
            &[
                "role",
                "content_id",
                "replica_id",
                "sha256",
                "byte_count",
                "media_type",
            ],
        )?;
        if !roles.insert(string(material, "role")?)
            || unsigned(material, "byte_count")? > i64::MAX as u64
            || !string(material, "media_type")?.contains('/')
        {
            return Err(ContractError("request material is invalid"));
        }
        digest(material, "sha256")?;
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
    Ok(ValidatedRequest {
        value,
        request_digest,
        registry_entry_id,
        registry_entry_digest,
        image_digest,
        phase,
        cpu_millis: limits.0,
        memory_bytes: limits.1,
        deadline_ms: limits.2,
        maximum_output_bytes: limits.3 as usize,
    })
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
            let finding: Finding = serde_json::from_value(item.clone())
                .map_err(|_| ContractError("finding is invalid"))?;
            if finding.code.is_empty()
                || finding.code.len() > 100
                || finding.message.is_empty()
                || finding.message.len() > 4096
                || !matches!(finding.level.as_str(), "info" | "warning" | "error")
                || finding
                    .path
                    .as_ref()
                    .is_some_and(|path| path.is_empty() || path.len() > 1000)
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
    if source == "-0.0" || source == "-0e0" || source == "-0E0" {
        return Ok("0.0".into());
    }
    let Some(position) = source.find(['e', 'E']) else {
        return Ok(source.into());
    };
    let (mantissa, exponent) = source.split_at(position);
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
        if unsigned.contains('.') {
            result.push_str(".0");
        }
    } else {
        let split = new_decimal as usize;
        write!(result, "{}.{}", &digits[..split], &digits[split..]).unwrap();
    }
    Ok(result)
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
            "sha256:81adbc8a7cc0e13b4221ac06ecdd2f95850d6215c3a336d932ad14f8988a70b7"
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
    }
}
