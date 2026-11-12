use super::*;

fn invocation() -> Invocation {
    Invocation {
        operation: Operation::ExecutePre,
        run_id: "01a1d010-14fa-7444-a807-ade92ac62129".into(),
        source_operation_id: "01a1d010-14fa-7444-a807-ade92ac62130".into(),
        request_digest: format!("sha256:{}", "a".repeat(64)),
        source_sha256: format!("sha256:{}", "b".repeat(64)),
        profile_sha256: format!("sha256:{}", "c".repeat(64)),
        image_digest: format!("sha256:{}", "d".repeat(64)),
        config_image_id: format!("sha256:{}", "e".repeat(64)),
        lease_id: "01a1d010-14fa-7444-a807-ade92ac62131".into(),
        lease_generation: 1,
    }
}

pub(super) fn fixture() -> (PathBuf, ServiceConfig, Lease, Journal) {
    let (root, mut config) = super::super::super::tests::test_config();
    let leases = root.join("leases");
    fs::create_dir(&leases).unwrap();
    fs::set_permissions(&leases, fs::Permissions::from_mode(0o700)).unwrap();
    let runtime = SmolConfig {
        binary: root.join("unused-runtime"),
        binary_sha256: format!("sha256:{}", "a".repeat(64)),
        home: root.join("home"),
        guest_binary: root.join("guest"),
        guest_sha256: format!("sha256:{}", "b".repeat(64)),
        cgroup_root: root.join("groups"),
        maximum_parallel: 1,
        maximum_storage_bytes: 4 * 1024 * 1024 * 1024,
    };
    config.smol = Some(runtime.clone());
    config.smol_admission = Some(Arc::new(
        Admission::new(
            Capacity {
                slots: 1,
                memory_bytes: u64::MAX,
                storage_bytes: u64::MAX,
            },
            "e".repeat(64),
        )
        .unwrap(),
    ));
    let lease = Lease {
        name: format!("ws-{}", "0".repeat(32)),
        owner: container_owner(&config).unwrap().to_owned(),
        epoch: "e".repeat(64),
        expires_ms: 1,
        lifetime_ms: 1,
        root: leases,
        runtime,
        private_home_root: None,
        pre: Some(invocation()),
    };
    let bytes = serde_json::to_vec(&lease).unwrap();
    let mut file = OpenOptions::new()
        .create_new(true)
        .write(true)
        .mode(0o600)
        .open(lease.path())
        .unwrap();
    file.write_all(&bytes).unwrap();
    file.sync_all().unwrap();
    let journal = Journal::capture(&file, &bytes).unwrap();
    (root, config, lease, journal)
}

#[test]
fn pending_cleanup_requires_exact_pre_journal_and_quarantines_admission() {
    let (root, config, lease, journal) = fixture();
    let mut machine = Machine {
        lease,
        journal,
        guardian: Command::new("/bin/true").spawn().unwrap(),
        keeper: None,
        consumed: false,
    };
    machine.guardian.wait().unwrap();
    let digest = machine.pending_pre_cleanup(&config).unwrap();
    assert_eq!(
        digest,
        format!(
            "sha256:{:x}",
            Sha256::digest(fs::read(machine.lease.path()).unwrap())
        )
    );
    assert!(config
        .smol_admission
        .as_ref()
        .unwrap()
        .reserve(
            Capacity {
                slots: 1,
                memory_bytes: 1,
                storage_bytes: 1,
            },
            None
        )
        .is_err());
    // A dead guardian does not erase the durable startup reaper obligation.
    fs::remove_file(machine.lease.path()).unwrap();
    assert!(machine.pending_pre_cleanup(&config).is_err());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn lost_journal_still_quarantines_the_node() {
    let (root, config, lease, journal) = fixture();
    let mut machine = Machine {
        lease,
        journal,
        guardian: Command::new("/bin/true").spawn().unwrap(),
        keeper: None,
        consumed: false,
    };
    machine.guardian.wait().unwrap();
    fs::remove_file(machine.lease.path()).unwrap();
    assert!(machine.pending_pre_cleanup(&config).is_err());
    assert!(config
        .smol_admission
        .as_ref()
        .unwrap()
        .reserve(
            Capacity {
                slots: 1,
                memory_bytes: 1,
                storage_bytes: 1,
            },
            None
        )
        .is_err());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn changed_or_rebound_cleanup_journal_is_never_a_receipt() {
    for attack in [
        "fence", "source", "replace", "symlink", "hardlink", "mode", "parent",
    ] {
        let (root, _config, mut lease, journal) = fixture();
        let original = fs::read(lease.path()).unwrap();
        match attack {
            "fence" => {
                lease.pre.as_mut().unwrap().lease_generation += 1;
                fs::write(lease.path(), serde_json::to_vec(&lease).unwrap()).unwrap();
            }
            "source" => {
                lease.pre.as_mut().unwrap().source_sha256 = format!("sha256:{}", "f".repeat(64));
                fs::write(lease.path(), serde_json::to_vec(&lease).unwrap()).unwrap();
            }
            "replace" | "symlink" => {
                let retained = root.join("retained");
                fs::rename(lease.path(), &retained).unwrap();
                if attack == "symlink" {
                    std::os::unix::fs::symlink(retained, lease.path()).unwrap();
                } else {
                    fs::write(lease.path(), original).unwrap();
                    fs::set_permissions(lease.path(), fs::Permissions::from_mode(0o600)).unwrap();
                }
            }
            "hardlink" => fs::hard_link(lease.path(), root.join("alias")).unwrap(),
            "mode" => fs::set_permissions(lease.path(), fs::Permissions::from_mode(0o644)).unwrap(),
            "parent" => {
                fs::set_permissions(&lease.root, fs::Permissions::from_mode(0o755)).unwrap()
            }
            _ => unreachable!(),
        }
        assert!(journal.retained(&lease).is_err(), "accepted {attack}");
        fs::remove_dir_all(root).unwrap();
    }
}

#[test]
fn pre_creation_persists_binding_before_guardian_or_runtime() {
    let (root, config, _lease, _journal) = fixture();
    let leases = config.socket_path.parent().unwrap().join("smol-leases");
    fs::create_dir(&leases).unwrap();
    fs::set_permissions(&leases, fs::Permissions::from_mode(0o700)).unwrap();
    let resources = Resources {
        cpu_millis: 1000,
        memory_bytes: 1024,
        storage_gib: 1,
        pids: 4,
    };
    let mut invalid = invocation();
    invalid.lease_generation = 0;
    assert!(Machine::create_pre(
        &config,
        resources,
        Instant::now() + Duration::from_millis(100),
        invalid
    )
    .is_err());
    assert_eq!(fs::read_dir(&leases).unwrap().count(), 0);
    // This test executable cannot run the production guardian entrypoint. Its
    // failed handshake must leave exactly one already bound durable obligation.
    assert!(Machine::create_pre(
        &config,
        resources,
        Instant::now() + Duration::from_millis(100),
        invocation()
    )
    .is_err());
    let paths: Vec<_> = fs::read_dir(&leases)
        .unwrap()
        .map(|entry| entry.unwrap().path())
        .collect();
    assert_eq!(paths.len(), 1);
    let saved: Lease = serde_json::from_slice(&fs::read(&paths[0]).unwrap()).unwrap();
    assert!(saved.valid());
    assert_eq!(
        serde_json::to_value(saved.pre.unwrap()).unwrap(),
        serde_json::to_value(invocation()).unwrap()
    );
    fs::remove_dir_all(root).unwrap();
}
