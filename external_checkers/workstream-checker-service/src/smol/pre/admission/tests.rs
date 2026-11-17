use super::*;
use serde_json::json;
use workstream_checker_guest::pre_bootstrap::PrePartition;

pub(crate) fn fixture() -> (PathBuf, ServiceConfig, Value) {
    let (root, mut config, _, _) = super::super::tests::fixture();
    let mut header: Value =
        serde_json::from_str::<Value>(include_str!("../../../../../fixtures/pre_startup.json"))
            .unwrap()["request"]
            .clone();
    header["lease_expires_at"] = json!("2099-01-01T00:00:00Z");
    header["reservation"]["pre_deadline_at"] = json!("2099-01-01T00:00:00+00:00");
    header["request_digest"] = json!(hash(&header["reservation"]).unwrap());
    config.runtime = "smolvm".into();
    config.isolation_mode = "smol-microvm".into();
    config.sandbox_uid = 23456;
    config.sandbox_gid = 23456;
    let image = root.join("image.json");
    let bytes = serde_json::to_vec(
        &json!({"os":"linux","architecture":"amd64","config":{"Cmd":["/checker"]}}),
    )
    .unwrap();
    fs::write(&image, &bytes).unwrap();
    fs::set_permissions(&image, fs::Permissions::from_mode(0o644)).unwrap();
    config.cache[0].platform_manifest_digest = header["reservation"]["policy"]["entries"][0]
        ["registry"]["image_digest"]
        .as_str()
        .unwrap()
        .into();
    config.cache[0].config_image_id = format!("sha256:{:x}", Sha256::digest(bytes));
    config.cache[0].smol = Some(SmolImage {
        archive: root.join("image.tar"),
        archive_sha256: format!("sha256:{}", "d".repeat(64)),
        image_config: image,
    });
    let profile = header["reservation"]["runtime_profile"].clone();
    config.pre = Some(Config {
        profile_sha256: hash(&profile).unwrap(),
        profile,
        root_bundle: root.join("root.bundle"),
        root: RootDescriptor {
            schema_version: "workstream.trusted_root.v1".into(),
            platform_manifest_digest: format!("sha256:{}", "e".repeat(64)),
            config_image_id: format!("sha256:{}", "f".repeat(64)),
            default_behavior_sha256: header["reservation"]["policy"]["workstream_default"]
                ["behavior_sha256"]
                .as_str()
                .unwrap()
                .into(),
            expanded_bytes: 1024,
            entries: 3,
            bundle_sha256: format!("sha256:{}", "a".repeat(64)),
            bundle_byte_count: 1024,
        },
        root_limits: RootLimits {
            maximum_bundle_bytes: 2048,
            maximum_root_bytes: 2048,
            maximum_entries: 10,
        },
        smol_binary_sha256: config.smol.as_ref().unwrap().binary_sha256.clone(),
        guest_sha256: config.smol.as_ref().unwrap().guest_sha256.clone(),
        limits: PreBootstrapLimits {
            control: PrePartition {
                cpu_millis: 100,
                memory_bytes: 64 * 1024 * 1024,
                processes: 3,
            },
            worker: PrePartition {
                cpu_millis: 400,
                memory_bytes: 512 * 1024 * 1024,
                processes: 8,
            },
            project: PrePartition {
                cpu_millis: 1500,
                memory_bytes: 256 * 1024 * 1024,
                processes: 8,
            },
            worker_uid: 12345,
            worker_gid: 12345,
            worker_scratch_bytes: 4 * 1024 * 1024,
            project_scratch_bytes: 4 * 1024 * 1024,
            maximum_source_bytes: 1024 * 1024,
            maximum_control_bytes: 2 * 1024 * 1024,
            maximum_output_bytes: 1024 * 1024,
            maximum_log_bytes: 1024 * 1024,
            timeout_ms: 1000,
            cleanup_timeout_ms: 2000,
            overlay_bytes: 1024 * 1024,
            filesystem_overhead_bytes: 1024 * 1024,
        },
    });
    fs::write(root.join("root.bundle"), vec![0_u8; 1024]).unwrap();
    fs::set_permissions(root.join("root.bundle"), fs::Permissions::from_mode(0o644)).unwrap();
    (root, config, header)
}

#[test]
fn pre_admission_binds_actual_run_and_charges_rounded_storage_and_overlay() {
    let (root, config, header) = fixture();
    let prepared = prepare(&config, &serde_json::to_vec(&header).unwrap()).unwrap();
    assert_eq!(
        prepared.invocation.run_id,
        header["reservation"]["attempt_id"]
    );
    assert_eq!(
        prepared.invocation.source_operation_id,
        header["reservation"]["source"]["location"]["operation_id"]
    );
    assert_eq!(prepared.resources.storage_gib, 1);
    assert_eq!(prepared.overlay_gib, 1);
    assert_eq!(
        resource_capacity(prepared.resources, Some(prepared.overlay_gib))
            .unwrap()
            .storage_bytes,
        2 * 1024 * 1024 * 1024
    );
    assert_eq!(
        prepared.cache.config_image_id,
        prepared.invocation.config_image_id
    );
    assert!(prepared.job.selected.request.is_null());
    assert!(prepared.deadline > Instant::now());
    assert_eq!(prepared.root_bundle.metadata().unwrap().len(), 1024);
    // No runtime binary or image archive exists, and admission creates no lease.
    assert!(!config
        .socket_path
        .parent()
        .unwrap()
        .join("smol-leases")
        .exists());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn pre_admission_refuses_rebound_pins_fences_and_bounds_before_allocation() {
    for attack in [
        "request",
        "source",
        "profile",
        "image",
        "binary",
        "guest",
        "root",
        "default",
        "count",
        "fence",
        "expired",
        "unknown",
        "partition",
        "overflow",
        "disk",
        "uid",
        "duplicate_image",
        "missing_root",
        "root_size",
        "root_symlink",
        "root_mode",
    ] {
        let (root, mut config, mut header) = fixture();
        prepare(&config, &serde_json::to_vec(&header).unwrap())
            .expect("valid control before mutation");
        match attack {
            "request" => header["request_digest"] = json!(format!("sha256:{}", "0".repeat(64))),
            "source" => header["reservation"]["source"]["raw_byte_count"] = json!(2),
            "profile" => header["reservation"]["runtime_profile"]["memory_bytes"] = json!(3),
            "image" => {
                header["reservation"]["policy"]["entries"][0]["registry"]["image_digest"] =
                    json!(format!("sha256:{}", "0".repeat(64)))
            }
            "binary" => {
                config.pre.as_mut().unwrap().smol_binary_sha256 =
                    format!("sha256:{}", "0".repeat(64))
            }
            "guest" => {
                config.pre.as_mut().unwrap().guest_sha256 = format!("sha256:{}", "0".repeat(64))
            }
            "root" => {
                config.pre.as_mut().unwrap().root.bundle_sha256 =
                    format!("sha256:{}", "0".repeat(64))
            }
            "default" => {
                config.pre.as_mut().unwrap().root.default_behavior_sha256 =
                    format!("sha256:{}", "0".repeat(64))
            }
            "count" => {
                let entry = header["reservation"]["policy"]["entries"][0].clone();
                header["reservation"]["policy"]["entries"]
                    .as_array_mut()
                    .unwrap()
                    .push(entry);
            }
            "fence" => header["lease_generation"] = json!(0),
            "expired" => header["lease_expires_at"] = json!("2000-01-01T00:00:00Z"),
            "unknown" => header["extra"] = json!(true),
            "partition" => config.pre.as_mut().unwrap().limits.control.memory_bytes = u64::MAX,
            "overflow" => config.pre.as_mut().unwrap().limits.worker_scratch_bytes = u64::MAX,
            "disk" => {
                config.pre.as_mut().unwrap().limits.worker_scratch_bytes = 4 * 1024 * 1024 * 1024
            }
            "uid" => config.sandbox_uid = config.pre.as_ref().unwrap().limits.worker_uid,
            "duplicate_image" => config.cache.push(config.cache[0].clone()),
            "missing_root" => fs::remove_file(root.join("root.bundle")).unwrap(),
            "root_size" => fs::write(root.join("root.bundle"), b"truncated").unwrap(),
            "root_symlink" => {
                fs::rename(root.join("root.bundle"), root.join("root.original")).unwrap();
                std::os::unix::fs::symlink(root.join("root.original"), root.join("root.bundle"))
                    .unwrap();
            }
            "root_mode" => {
                fs::set_permissions(root.join("root.bundle"), fs::Permissions::from_mode(0o666))
                    .unwrap()
            }
            _ => unreachable!(),
        }
        for selected in header["reservation"]["policy"]["entries"]
            .as_array_mut()
            .unwrap()
        {
            let mut spec = selected["registry"].as_object().unwrap().clone();
            for key in [
                "registry_entry_id",
                "entry_digest",
                "registration_operation_id",
                "registered_by_actor_profile_id",
                "authorization_decision_event_id",
                "created_at",
            ] {
                spec.remove(key);
            }
            selected["registry"]["entry_digest"] = json!(hash(&Value::Object(spec)).unwrap());
        }
        let mut policy = header["reservation"]["policy"].as_object().unwrap().clone();
        policy.remove("policy_sha256");
        header["reservation"]["policy"]["policy_sha256"] =
            json!(hash(&Value::Object(policy)).unwrap());
        if attack != "request" {
            header["request_digest"] = json!(hash(&header["reservation"]).unwrap());
        }
        assert!(
            prepare(&config, &serde_json::to_vec(&header).unwrap()).is_err(),
            "accepted {attack}"
        );
        assert!(!config
            .socket_path
            .parent()
            .unwrap()
            .join("smol-leases")
            .exists());
        fs::remove_dir_all(root).unwrap();
    }
}

#[test]
fn source_cap_rejects_self_consistent_bytes_above_the_configured_maximum() {
    let (root, config, mut header) = fixture();
    let maximum = config.pre.as_ref().unwrap().limits.maximum_source_bytes;
    for (count, accepted) in [(maximum, true), (maximum + 1, false)] {
        header["reservation"]["source"]["raw_byte_count"] = json!(count);
        let mut source = header["reservation"]["source"].as_object().unwrap().clone();
        source.insert(
            "schema_version".into(),
            json!("workstream.sealed_submission_source.v1"),
        );
        header["reservation"]["source_sha256"] = json!(hash(&Value::Object(source)).unwrap());
        header["request_digest"] = json!(hash(&header["reservation"]).unwrap());
        let result = prepare(&config, &serde_json::to_vec(&header).unwrap());
        if accepted {
            let prepared = result.expect("the exact configured source maximum is admitted");
            assert_eq!(
                prepared.job.startup["request"]["reservation"]["source"]["raw_byte_count"],
                count
            );
        } else {
            assert!(matches!(result, Err(ref error) if error == "PRE configured identity differs"));
        }
        assert!(!config
            .socket_path
            .parent()
            .unwrap()
            .join("smol-leases")
            .exists());
    }
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn utc_deadlines_refuse_normalization_and_floor_submillisecond_expiry() {
    assert_eq!(utc_millis("2024-02-29T00:00:00Z").unwrap(), 1709164800000);
    assert_eq!(
        utc_millis("2024-02-29T00:00:00.123999+00:00").unwrap(),
        1709164800123
    );
    for invalid in [
        "2023-02-29T00:00:00Z",
        "2024-13-01T00:00:00Z",
        "2024-01-01T24:00:00Z",
        "2024-01-01T00:00:60Z",
        "2024-01-01T00:00:00.1234567Z",
        "2024-01-01T00:00:00+01:00",
        "2024-01-01T00:00:00.Z",
        "2024-01-01T00:00:00",
    ] {
        assert!(utc_millis(invalid).is_err(), "accepted {invalid}");
    }
}
