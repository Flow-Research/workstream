//! Trusted immutable trial authority resolved from flat locked-policy selectors.

use crate::trial_relay::{
    valid_profile, valid_sha256, valid_uuid, TrialMaterialProjectionProfile, TrialProfile,
    TrialSlotProfile,
};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashSet;
use workstream_checker_sdk::{canonical_hash, ValidatedRequest};

const MANIFEST_PROTOCOL: &str = "workstream.trial_authority_manifest.v1";
const MAXIMUM_MANIFEST_BYTES: usize = 4 * 1024 * 1024;

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct TrialAuthorityManifest {
    protocol_version: String,
    entries: Vec<TrialAuthorityEntry>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct TrialAuthorityEntry {
    registry_entry_id: String,
    registry_entry_digest: String,
    checker_image_digest: String,
    configuration_sha256: String,
    profile: RuntimeProfile,
    projection: ExecutionProjection,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct RuntimeProfile {
    schema_version: String,
    selector: ProfileSelector,
    runtime: String,
    isolation_mode: String,
    outer_host_uds: String,
    child_host_uds: String,
    outer_runtime_config_digest: String,
    child_runtime_config_digest: String,
    engine_identity_digest: String,
    platform: String,
    platform_identity_digest: String,
    builder_image_digest: String,
    trusted_launcher_digest: String,
    offline_cache_digest: String,
    approved_base_digests: Vec<String>,
    permitted_source_roles: Vec<String>,
    permitted_material_roles: Vec<String>,
    permitted_operations: Vec<String>,
    permitted_state_retention_outcomes: Vec<String>,
    trusted_launcher_capabilities: Vec<String>,
    builder_capabilities: Vec<String>,
    child_capabilities: Vec<String>,
    child_network: String,
    child_runs_as_non_root: bool,
    limits: RuntimeLimits,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct ProfileSelector {
    profile_id: String,
    profile_version: u32,
    profile_digest: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct RuntimeLimits {
    maximum_total_timeout_ms: u64,
    maximum_build_timeout_ms: u64,
    maximum_step_timeout_ms: u64,
    maximum_steps: usize,
    maximum_cpu_quota_millis: u64,
    maximum_cpu_time_ms: u64,
    maximum_wall_time_overrun_ms: u64,
    maximum_cpu_time_overrun_ms: u64,
    maximum_memory_bytes: u64,
    maximum_swap_bytes: u64,
    maximum_memory_overrun_bytes: u64,
    maximum_pids: u64,
    maximum_pids_overrun: u64,
    maximum_disk_bytes: u64,
    maximum_disk_overrun_bytes: u64,
    maximum_entries: u64,
    maximum_entries_overrun: u64,
    maximum_step_output_bytes: usize,
    maximum_observation_bytes: usize,
    maximum_receipt_bytes: usize,
    maximum_frame_bytes: usize,
    maximum_response_bytes: usize,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct ExecutionProjection {
    selector: ProjectionSelector,
    trial_kind: String,
    material_projections: Vec<TrialMaterialProjectionProfile>,
    allowed_material_roles: Vec<String>,
    build_context_roles: Vec<String>,
    slot_templates: Vec<TrialSlotProfile>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct ProjectionSelector {
    projection_id: String,
    projection_version: u32,
    projection_digest: String,
}

#[derive(Clone, Debug, PartialEq, Eq, Hash)]
struct Selector {
    profile_id: String,
    profile_version: u32,
    profile_digest: String,
    projection_id: String,
    projection_version: u32,
    projection_digest: String,
}

impl TrialAuthorityEntry {
    fn into_profile(self) -> Result<TrialProfile, &'static str> {
        let profile_digest = payload_digest(&self.profile, "profile_digest")?;
        let projection_digest = payload_digest(&self.projection, "projection_digest")?;
        let limits = self.profile.limits.clone();
        if self.profile.schema_version != "workstream.trial_execution_profile.v1"
            || self.profile.runtime != "runsc"
            || self.profile.isolation_mode != "gvisor"
            || self.profile.outer_host_uds != "open"
            || self.profile.child_host_uds != "none"
            || self.profile.child_network != "none"
            || !self.profile.child_runs_as_non_root
            || self.profile.trusted_launcher_capabilities
                != [
                    "CHOWN",
                    "DAC_OVERRIDE",
                    "FOWNER",
                    "KILL",
                    "SETGID",
                    "SETPCAP",
                    "SETUID",
                    "SYS_ADMIN",
                    "SYS_CHROOT",
                ]
            || self.profile.builder_capabilities != ["CHOWN", "DAC_OVERRIDE", "FOWNER"]
            || !self.profile.child_capabilities.is_empty()
            || self.profile.permitted_operations != ["run"]
            || profile_digest != self.profile.selector.profile_digest
            || projection_digest != self.projection.selector.projection_digest
            || limits.maximum_memory_bytes != limits.maximum_swap_bytes
            || limits.maximum_build_timeout_ms > limits.maximum_total_timeout_ms
            || limits.maximum_step_timeout_ms > limits.maximum_total_timeout_ms
            || limits.maximum_receipt_bytes > 1024 * 1024
            || self.profile.permitted_material_roles.is_empty()
            || self.profile.permitted_source_roles.is_empty()
            || self.profile.permitted_state_retention_outcomes.is_empty()
            || !self
                .projection
                .allowed_material_roles
                .iter()
                .all(|role| self.profile.permitted_material_roles.contains(role))
            || !self.projection.material_projections.iter().all(|material| {
                self.profile
                    .permitted_source_roles
                    .contains(&material.source_role)
            })
            || !self.projection.slot_templates.iter().all(|slot| {
                slot.retain_state_after.iter().all(|outcome| {
                    self.profile
                        .permitted_state_retention_outcomes
                        .contains(outcome)
                })
            })
            || !valid_uuid(&self.registry_entry_id)
            || !valid_sha256(&self.registry_entry_digest)
            || !valid_sha256(&self.checker_image_digest)
            || !valid_sha256(&self.configuration_sha256)
            || !valid_sha256(&self.profile.outer_runtime_config_digest)
        {
            return Err("trial authority manifest entry invalid");
        }
        Ok(TrialProfile {
            profile_id: self.profile.selector.profile_id,
            profile_version: self.profile.selector.profile_version,
            profile_digest: self.profile.selector.profile_digest,
            projection_id: self.projection.selector.projection_id,
            projection_version: self.projection.selector.projection_version,
            projection_digest: self.projection.selector.projection_digest,
            trial_kind: self.projection.trial_kind,
            registry_entry_id: self.registry_entry_id,
            registry_entry_digest: self.registry_entry_digest,
            checker_image_digest: self.checker_image_digest,
            configuration_sha256: self.configuration_sha256,
            engine_identity_digest: self.profile.engine_identity_digest,
            outer_runtime_config_digest: self.profile.outer_runtime_config_digest,
            child_runtime: self.profile.runtime,
            child_runtime_config_digest: self.profile.child_runtime_config_digest,
            child_host_uds: self.profile.child_host_uds,
            platform: self.profile.platform,
            platform_identity_digest: self.profile.platform_identity_digest,
            builder_image_digest: self.profile.builder_image_digest,
            trusted_launcher_digest: self.profile.trusted_launcher_digest,
            offline_cache_digest: self.profile.offline_cache_digest,
            approved_base_digests: self.profile.approved_base_digests,
            source_material_roles: self.profile.permitted_source_roles,
            material_projections: self.projection.material_projections,
            build_context_roles: self.projection.build_context_roles,
            allowed_material_roles: self.projection.allowed_material_roles,
            slot_templates: self.projection.slot_templates,
            maximum_frame_bytes: limits.maximum_frame_bytes,
            maximum_response_bytes: limits.maximum_response_bytes,
            maximum_steps: limits.maximum_steps,
            maximum_total_timeout_ms: limits.maximum_total_timeout_ms,
            maximum_build_timeout_ms: limits.maximum_build_timeout_ms,
            maximum_step_timeout_ms: limits.maximum_step_timeout_ms,
            maximum_step_output_bytes: limits.maximum_step_output_bytes,
            maximum_observation_bytes: limits.maximum_observation_bytes,
            maximum_receipt_bytes: limits.maximum_receipt_bytes,
            maximum_cpu_quota_millis: limits.maximum_cpu_quota_millis,
            maximum_cpu_time_ms: limits.maximum_cpu_time_ms,
            maximum_wall_time_overrun_ms: limits.maximum_wall_time_overrun_ms,
            maximum_cpu_time_overrun_ms: limits.maximum_cpu_time_overrun_ms,
            maximum_memory_bytes: limits.maximum_memory_bytes,
            maximum_memory_overrun_bytes: limits.maximum_memory_overrun_bytes,
            maximum_disk_bytes: limits.maximum_disk_bytes,
            maximum_disk_overrun_bytes: limits.maximum_disk_overrun_bytes,
            maximum_entries: limits.maximum_entries,
            maximum_entries_overrun: limits.maximum_entries_overrun,
            maximum_pids: limits.maximum_pids,
            maximum_pids_overrun: limits.maximum_pids_overrun,
        })
    }
}

fn payload_digest<T: Serialize>(value: &T, digest_key: &str) -> Result<String, &'static str> {
    let mut value = serde_json::to_value(value).map_err(|_| "trial authority manifest invalid")?;
    value
        .get_mut("selector")
        .and_then(Value::as_object_mut)
        .and_then(|selector| selector.remove(digest_key))
        .ok_or("trial authority manifest invalid")?;
    canonical_hash(&value).map_err(|_| "trial authority manifest invalid")
}

#[derive(Debug, Clone)]
pub(crate) struct TrialProfileCatalog {
    entries: Vec<TrialProfile>,
}

impl TrialProfileCatalog {
    #[cfg(test)]
    pub(crate) fn empty_for_test() -> Self {
        Self {
            entries: Vec::new(),
        }
    }

    pub(crate) fn from_bytes(bytes: &[u8], expected_digest: &str) -> Result<Self, &'static str> {
        if bytes.is_empty()
            || bytes.len() > MAXIMUM_MANIFEST_BYTES
            || !valid_sha256(expected_digest)
        {
            return Err("trial authority manifest invalid");
        }
        let value: Value =
            serde_json::from_slice(bytes).map_err(|_| "trial authority manifest invalid")?;
        if canonical_hash(&value).map_err(|_| "trial authority manifest invalid")?
            != expected_digest
        {
            return Err("trial authority manifest digest differs");
        }
        let manifest: TrialAuthorityManifest =
            serde_json::from_value(value).map_err(|_| "trial authority manifest invalid")?;
        if manifest.protocol_version != MANIFEST_PROTOCOL || manifest.entries.is_empty() {
            return Err("trial authority manifest invalid");
        }
        let mut entries = Vec::with_capacity(manifest.entries.len());
        let mut bindings = HashSet::new();
        for entry in manifest.entries {
            let profile = entry.into_profile()?;
            if !valid_profile(&profile)
                || !bindings.insert((
                    profile.registry_entry_id.clone(),
                    profile.registry_entry_digest.clone(),
                    profile.checker_image_digest.clone(),
                    profile.configuration_sha256.clone(),
                ))
            {
                return Err("trial authority manifest entry invalid");
            }
            entries.push(profile);
        }
        Ok(Self { entries })
    }

    pub(crate) fn resolve(
        &self,
        request: &ValidatedRequest,
    ) -> Result<Option<&TrialProfile>, &'static str> {
        let configuration = request
            .value
            .get("configuration")
            .and_then(Value::as_object)
            .ok_or("trial selectors invalid")?;
        let selected = selector_from_configuration(configuration)?;
        let Some(selected) = selected else {
            return Ok(None);
        };
        if request.phase != "post_submit" {
            return Err("trial selectors outside POST");
        }
        let matches = self
            .entries
            .iter()
            .filter(|profile| {
                selector_from_profile(profile) == selected
                    && profile.registry_entry_id == request.registry_entry_id
                    && profile.registry_entry_digest == request.registry_entry_digest
                    && profile.checker_image_digest == request.image_digest
                    && profile.configuration_sha256 == request.configuration_digest
            })
            .collect::<Vec<_>>();
        match matches.as_slice() {
            [profile] => Ok(Some(*profile)),
            _ => Err("trial authority unavailable"),
        }
    }
}

fn selector_from_profile(profile: &TrialProfile) -> Selector {
    Selector {
        profile_id: profile.profile_id.clone(),
        profile_version: profile.profile_version,
        profile_digest: profile.profile_digest.clone(),
        projection_id: profile.projection_id.clone(),
        projection_version: profile.projection_version,
        projection_digest: profile.projection_digest.clone(),
    }
}

fn selector_from_configuration(
    configuration: &serde_json::Map<String, Value>,
) -> Result<Option<Selector>, &'static str> {
    const KEYS: [&str; 6] = [
        "trial_profile_id",
        "trial_profile_version",
        "trial_profile_digest",
        "trial_projection_id",
        "trial_projection_version",
        "trial_projection_digest",
    ];
    let present = KEYS
        .iter()
        .filter(|key| configuration.contains_key(**key))
        .count();
    if configuration.contains_key("trial_execution") {
        return Err("nested trial authority forbidden");
    }
    if configuration
        .keys()
        .any(|key| key.starts_with("trial_") && !KEYS.contains(&key.as_str()))
    {
        return Err("trial selectors invalid");
    }
    if present == 0 {
        return Ok(None);
    }
    if present != KEYS.len() {
        return Err("trial selectors incomplete");
    }
    let string = |key| {
        configuration
            .get(key)
            .and_then(Value::as_str)
            .map(str::to_owned)
            .ok_or("trial selector invalid")
    };
    let version = |key| {
        configuration
            .get(key)
            .and_then(Value::as_u64)
            .and_then(|value| u32::try_from(value).ok())
            .filter(|value| *value > 0)
            .ok_or("trial selector invalid")
    };
    let selector = Selector {
        profile_id: string("trial_profile_id")?,
        profile_version: version("trial_profile_version")?,
        profile_digest: string("trial_profile_digest")?,
        projection_id: string("trial_projection_id")?,
        projection_version: version("trial_projection_version")?,
        projection_digest: string("trial_projection_digest")?,
    };
    if !valid_uuid(&selector.profile_id)
        || !valid_sha256(&selector.profile_digest)
        || !valid_uuid(&selector.projection_id)
        || !valid_sha256(&selector.projection_digest)
    {
        return Err("trial selector invalid");
    }
    Ok(Some(selector))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn digest(character: char) -> String {
        format!("sha256:{}", character.to_string().repeat(64))
    }

    fn authority_entry(configuration_sha256: &str) -> TrialAuthorityEntry {
        let mut profile = RuntimeProfile {
            schema_version: "workstream.trial_execution_profile.v1".into(),
            selector: ProfileSelector {
                profile_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00001".into(),
                profile_version: 1,
                profile_digest: digest('0'),
            },
            runtime: "runsc".into(),
            isolation_mode: "gvisor".into(),
            outer_host_uds: "open".into(),
            child_host_uds: "none".into(),
            outer_runtime_config_digest: digest('1'),
            child_runtime_config_digest: digest('2'),
            engine_identity_digest: digest('3'),
            platform: "linux/amd64".into(),
            platform_identity_digest: digest('4'),
            builder_image_digest: digest('5'),
            trusted_launcher_digest: digest('6'),
            offline_cache_digest: digest('6'),
            approved_base_digests: vec![digest('7')],
            permitted_source_roles: vec!["submission_archive".into()],
            permitted_material_roles: vec!["candidate_source".into()],
            permitted_operations: vec!["run".into()],
            permitted_state_retention_outcomes: vec!["succeeded".into()],
            trusted_launcher_capabilities: vec![
                "CHOWN".into(),
                "DAC_OVERRIDE".into(),
                "FOWNER".into(),
                "KILL".into(),
                "SETGID".into(),
                "SETPCAP".into(),
                "SETUID".into(),
                "SYS_ADMIN".into(),
                "SYS_CHROOT".into(),
            ],
            builder_capabilities: vec!["CHOWN".into(), "DAC_OVERRIDE".into(), "FOWNER".into()],
            child_capabilities: Vec::new(),
            child_network: "none".into(),
            child_runs_as_non_root: true,
            limits: RuntimeLimits {
                maximum_total_timeout_ms: 30_000,
                maximum_build_timeout_ms: 10_000,
                maximum_step_timeout_ms: 5_000,
                maximum_steps: 1,
                maximum_cpu_quota_millis: 1_000,
                maximum_cpu_time_ms: 20_000,
                maximum_wall_time_overrun_ms: 100,
                maximum_cpu_time_overrun_ms: 250,
                maximum_memory_bytes: 134_217_728,
                maximum_swap_bytes: 134_217_728,
                maximum_memory_overrun_bytes: 1_048_576,
                maximum_pids: 32,
                maximum_pids_overrun: 2,
                maximum_disk_bytes: 134_217_728,
                maximum_disk_overrun_bytes: 1_048_576,
                maximum_entries: 10_000,
                maximum_entries_overrun: 16,
                maximum_step_output_bytes: 65_536,
                maximum_observation_bytes: 262_144,
                maximum_receipt_bytes: 524_288,
                maximum_frame_bytes: 262_144,
                maximum_response_bytes: 16_384,
            },
        };
        profile.selector.profile_digest = payload_digest(&profile, "profile_digest").unwrap();
        let mut projection = ExecutionProjection {
            selector: ProjectionSelector {
                projection_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00002".into(),
                projection_version: 1,
                projection_digest: digest('0'),
            },
            trial_kind: "generic_build_run".into(),
            material_projections: vec![TrialMaterialProjectionProfile {
                role: "candidate_source".into(),
                source_role: "submission_archive".into(),
                projection_kind: "build_context".into(),
                source_relative: ".".into(),
                destination_relative: ".".into(),
                exclusions: Vec::new(),
            }],
            allowed_material_roles: vec!["candidate_source".into()],
            build_context_roles: vec!["candidate_source".into()],
            slot_templates: vec![TrialSlotProfile {
                slot_kind: "generic_run".into(),
                minimum_occurrences: 1,
                maximum_occurrences: 1,
                seed_roles: Vec::new(),
                visible_roles: Vec::new(),
                fresh_workspace: true,
                retain_state_after: vec!["succeeded".into()],
            }],
        };
        projection.selector.projection_digest =
            payload_digest(&projection, "projection_digest").unwrap();
        TrialAuthorityEntry {
            registry_entry_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00003".into(),
            registry_entry_digest: digest('a'),
            checker_image_digest: digest('b'),
            configuration_sha256: configuration_sha256.into(),
            profile,
            projection,
        }
    }

    fn catalog(entries: Vec<TrialAuthorityEntry>) -> Result<TrialProfileCatalog, &'static str> {
        let value = serde_json::json!({
            "protocol_version": MANIFEST_PROTOCOL,
            "entries": entries,
        });
        let digest = canonical_hash(&value).unwrap();
        TrialProfileCatalog::from_bytes(&serde_json::to_vec(&value).unwrap(), &digest)
    }

    fn request(entry: &TrialAuthorityEntry) -> ValidatedRequest {
        ValidatedRequest {
            value: serde_json::json!({
                "configuration": {
                    "trial_profile_id": entry.profile.selector.profile_id,
                    "trial_profile_version": entry.profile.selector.profile_version,
                    "trial_profile_digest": entry.profile.selector.profile_digest,
                    "trial_projection_id": entry.projection.selector.projection_id,
                    "trial_projection_version": entry.projection.selector.projection_version,
                    "trial_projection_digest": entry.projection.selector.projection_digest,
                }
            }),
            request_digest: digest('f'),
            registry_entry_id: entry.registry_entry_id.clone(),
            registry_entry_digest: entry.registry_entry_digest.clone(),
            image_digest: entry.checker_image_digest.clone(),
            configuration_digest: entry.configuration_sha256.clone(),
            phase: "post_submit".into(),
            post_material_roles: vec!["submission_archive".into()],
            evaluation_context_sha256: None,
            cpu_millis: 1_000,
            memory_bytes: 134_217_728,
            deadline_ms: 30_000,
            maximum_output_bytes: 65_536,
        }
    }

    #[test]
    fn shared_selectors_resolve_only_with_their_exact_binding_context() {
        let first = authority_entry(&digest('c'));
        let second = authority_entry(&digest('d'));
        let selected = catalog(vec![first.clone(), second.clone()]).unwrap();
        assert_eq!(
            selected
                .resolve(&request(&first))
                .unwrap()
                .unwrap()
                .configuration_sha256,
            digest('c')
        );
        assert_eq!(
            selected
                .resolve(&request(&second))
                .unwrap()
                .unwrap()
                .configuration_sha256,
            digest('d')
        );
        let mut foreign = request(&first);
        foreign.configuration_digest = digest('e');
        assert_eq!(
            selected.resolve(&foreign),
            Err("trial authority unavailable")
        );

        assert_eq!(
            catalog(vec![first.clone(), first]).err(),
            Some("trial authority manifest entry invalid")
        );
        let mut conflicting = second.clone();
        conflicting.configuration_sha256 = digest('c');
        conflicting.projection.selector.projection_id =
            "018f6f49-66b8-7d2a-bf4d-0e2eeaa00004".into();
        conflicting.projection.selector.projection_digest =
            payload_digest(&conflicting.projection, "projection_digest").unwrap();
        assert_eq!(
            catalog(vec![authority_entry(&digest('c')), conflicting]).err(),
            Some("trial authority manifest entry invalid")
        );
    }

    #[test]
    fn flat_selector_parser_rejects_partial_nested_and_wrong_types() {
        let mut value = serde_json::json!({});
        assert_eq!(
            selector_from_configuration(value.as_object().unwrap()),
            Ok(None)
        );
        value["trial_profile_id"] = Value::String("018f6f49-66b8-7d2a-bf4d-0e2eeaa00001".into());
        assert_eq!(
            selector_from_configuration(value.as_object().unwrap()),
            Err("trial selectors incomplete")
        );
        value = serde_json::json!({"trial_execution": {}});
        assert_eq!(
            selector_from_configuration(value.as_object().unwrap()),
            Err("nested trial authority forbidden")
        );
        value["trial_profile_id"] = Value::String("018f6f49-66b8-7d2a-bf4d-0e2eeaa00001".into());
        assert_eq!(
            selector_from_configuration(value.as_object().unwrap()),
            Err("nested trial authority forbidden")
        );
        value = serde_json::json!({"trial_future_authority": "forbidden"});
        assert_eq!(
            selector_from_configuration(value.as_object().unwrap()),
            Err("trial selectors invalid")
        );
    }

    #[test]
    fn launcher_and_builder_capability_sets_are_distinct_exact_authority() {
        let mut broad_builder = authority_entry(&digest('c'));
        broad_builder.profile.builder_capabilities =
            broad_builder.profile.trusted_launcher_capabilities.clone();
        broad_builder.profile.selector.profile_digest =
            payload_digest(&broad_builder.profile, "profile_digest").unwrap();
        assert_eq!(
            catalog(vec![broad_builder]).err(),
            Some("trial authority manifest entry invalid")
        );

        let mut narrow_launcher = authority_entry(&digest('c'));
        narrow_launcher.profile.trusted_launcher_capabilities =
            narrow_launcher.profile.builder_capabilities.clone();
        narrow_launcher.profile.selector.profile_digest =
            payload_digest(&narrow_launcher.profile, "profile_digest").unwrap();
        assert_eq!(
            catalog(vec![narrow_launcher]).err(),
            Some("trial authority manifest entry invalid")
        );
    }

    #[test]
    fn state_overlay_destination_rejects_nested_workspace_paths() {
        let mut nested = authority_entry(&digest('c'));
        nested
            .projection
            .material_projections
            .push(TrialMaterialProjectionProfile {
                role: "verification".into(),
                source_role: "submission_archive".into(),
                projection_kind: "state_overlay".into(),
                source_relative: "tests".into(),
                destination_relative: "nested/tests".into(),
                exclusions: Vec::new(),
            });
        nested
            .projection
            .allowed_material_roles
            .push("verification".into());
        nested.projection.slot_templates[0]
            .visible_roles
            .push("verification".into());
        nested.projection.selector.projection_digest =
            payload_digest(&nested.projection, "projection_digest").unwrap();
        assert_eq!(
            catalog(vec![nested]).err(),
            Some("trial authority manifest entry invalid")
        );
    }
}
