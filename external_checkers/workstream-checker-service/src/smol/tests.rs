use super::*;

#[test]
fn small_guest_process_limits_leave_room_for_native_vmm_threads() {
    let request = parse_request(include_bytes!("../../../fixtures/request.json")).unwrap();
    let mut resources = Resources::from(&request);
    resources.memory_bytes = 512 * 1024 * 1024;
    resources.pids = 32;
    assert_eq!(resources.host_pids(), 128);
    assert_eq!(resources.pids, 32);
    resources.pids = 3;
    assert_eq!(resources.host_pids(), 128);
    assert_eq!(resources.pids, 3);
    resources.pids = 256;
    assert_eq!(resources.host_pids(), 256);
}

#[test]
fn smol_socket_paths_reserve_the_full_runtime_suffix_in_bytes() {
    let home = format!("/{}", "a".repeat(58));
    assert!(validate_home_socket_path(Path::new(&home)).is_ok());
    assert!(validate_home_socket_path(Path::new(&(home + "b"))).is_err());
    let child = format!("/{}", "a".repeat(17));
    assert!(validate_child_home_root(Path::new(&child)).is_ok());
    assert!(validate_child_home_root(Path::new(&(child + "b"))).is_err());
    // Character counts would admit this 60-byte path and fail at VM launch.
    let multibyte = format!("/a{}", "é".repeat(29));
    assert!(validate_home_socket_path(Path::new(&multibyte)).is_err());
}

#[test]
fn trial_peak_reservation_admits_maximum_memory_and_overrun_atomically() {
    let maximum_memory = 32 * 1024 * 1024;
    let overrun = 1024 * 1024;
    let disk = 64 * 1024 * 1024;
    let outer = resource_capacity(
        Resources {
            cpu_millis: 1000,
            memory_bytes: maximum_memory,
            storage_gib: 1,
            pids: 16,
        },
        None,
    )
    .unwrap();
    let peak = trial_peak_capacity(maximum_memory, overrun, disk).unwrap();
    let maximum = Capacity {
        slots: outer.slots + peak.slots,
        memory_bytes: outer.memory_bytes + peak.memory_bytes,
        storage_bytes: outer.storage_bytes + peak.storage_bytes,
    };
    let node = Arc::new(Admission::new(maximum, "e".repeat(64)).unwrap());
    let invocation = node.reserve(outer, Some(peak)).unwrap();
    let child = invocation
        .child(trial_capacity(maximum_memory + overrun, disk).unwrap())
        .unwrap();
    assert!(node.reserve(outer, None).is_err());
    drop(child);
    drop(invocation);
    let mut insufficient = maximum;
    insufficient.memory_bytes -= 1;
    let node = Arc::new(Admission::new(insufficient, "f".repeat(64)).unwrap());
    assert!(node.reserve(outer, Some(peak)).is_err());
    assert!(node.reserve(outer, None).is_ok());
    assert!(trial_peak_capacity(u64::MAX, 1, disk).is_err());
}

#[test]
fn foreign_lease_refuses_recovery_before_any_runtime_or_owned_cleanup() {
    let (root, mut config) = super::super::tests::test_config();
    let leases = config.socket_path.parent().unwrap().join("smol-leases");
    fs::create_dir(&leases).unwrap();
    fs::set_permissions(&leases, fs::Permissions::from_mode(0o700)).unwrap();
    let called = root.join("runtime-called");
    let binary = root.join("smol");
    fs::write(
        &binary,
        format!("#!/bin/sh\ntouch '{}'\nexit 1\n", called.display()),
    )
    .unwrap();
    fs::set_permissions(&binary, fs::Permissions::from_mode(0o700)).unwrap();
    let runtime = SmolConfig {
        binary,
        binary_sha256: format!("sha256:{}", "a".repeat(64)),
        home: root.join("home"),
        guest_binary: root.join("guest"),
        guest_sha256: format!("sha256:{}", "b".repeat(64)),
        cgroup_root: root.join("groups"),
        maximum_parallel: 2,
        maximum_storage_bytes: 4 * 1024 * 1024 * 1024,
    };
    config.smol = Some(runtime.clone());
    let mut lease = Lease {
        name: format!("ws-{}", "0".repeat(32)),
        owner: container_owner(&config).unwrap().to_owned(),
        epoch: "e".repeat(64),
        expires_ms: 1,
        lifetime_ms: 1,
        root: leases.clone(),
        runtime,
        private_home_root: None,
    };
    let owned = lease.path();
    fs::write(&owned, serde_json::to_vec(&lease).unwrap()).unwrap();
    fs::set_permissions(&owned, fs::Permissions::from_mode(0o600)).unwrap();
    lease.name = format!("ws-{}", "f".repeat(32));
    lease.owner = "d".repeat(64);
    let foreign = lease.path();
    fs::write(&foreign, serde_json::to_vec(&lease).unwrap()).unwrap();
    fs::set_permissions(&foreign, fs::Permissions::from_mode(0o600)).unwrap();
    assert_eq!(recover(&config).unwrap_err(), "lease ownership differs");
    assert!(owned.exists());
    assert!(foreign.exists());
    assert!(!called.exists());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn missing_lease_directory_does_not_poison_node_admission() {
    let (root, mut config) = super::super::tests::test_config();
    config.smol = Some(SmolConfig {
        binary: root.join("unused-runtime"),
        binary_sha256: format!("sha256:{}", "a".repeat(64)),
        home: root.join("home"),
        guest_binary: root.join("guest"),
        guest_sha256: format!("sha256:{}", "b".repeat(64)),
        cgroup_root: root.join("groups"),
        maximum_parallel: 2,
        maximum_storage_bytes: 4 * 1024 * 1024 * 1024,
    });
    config.smol_admission = Some(Arc::new(
        Admission::new(
            Capacity {
                slots: 2,
                memory_bytes: 1024 * 1024 * 1024,
                storage_bytes: 4 * 1024 * 1024 * 1024,
            },
            "e".repeat(64),
        )
        .unwrap(),
    ));
    let request = parse_request(include_bytes!("../../../fixtures/request.json")).unwrap();
    let (client, _peer) = UnixStream::pair().unwrap();
    let mut budget = RequestExecutionBudget::new(Instant::now() + Duration::from_secs(1), 32768);
    let inventory = WorkspaceInventory {
        directories: Vec::new(),
        files: Vec::new(),
    };
    let cancelled = AtomicBool::new(false);
    let result = execute(
        &config,
        &config.cache[0],
        &request,
        ProjectMaterials {
            current: (&root, &inventory),
            predecessor: None,
        },
        &ProjectCallbacks::default(),
        &client,
        &mut budget,
        &cancelled,
    );
    assert_eq!(
        result.unwrap_err(),
        ExecutionFailure::ordinary("implementation_unavailable", false)
    );
    assert!(!config
        .socket_path
        .parent()
        .unwrap()
        .join("smol-leases")
        .exists());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn concurrent_capacity_is_reserved_until_its_owner_releases_it() {
    let (root, mut config) = super::super::tests::test_config();
    let request = parse_request(include_bytes!("../../../fixtures/request.json")).unwrap();
    let capacity = request.memory_bytes + HOST_OVERHEAD;
    config.smol = Some(SmolConfig {
        binary: root.join("unused-runtime"),
        binary_sha256: format!("sha256:{}", "a".repeat(64)),
        home: root.clone(),
        guest_binary: root.join("guest"),
        guest_sha256: format!("sha256:{}", "b".repeat(64)),
        cgroup_root: root.join("groups"),
        maximum_parallel: 1,
        maximum_storage_bytes: 4 * 1024 * 1024 * 1024,
    });
    config.smol_admission = Some(Arc::new(
        Admission::new(
            Capacity {
                slots: 1,
                memory_bytes: capacity,
                storage_bytes: 4 * 1024 * 1024 * 1024,
            },
            "e".repeat(64),
        )
        .unwrap(),
    ));
    let held = reserve(&config, &request).unwrap();
    let concurrent = config.clone();
    let next = request.clone();
    assert!(thread::spawn(move || reserve(&concurrent, &next).is_err())
        .join()
        .unwrap());
    drop(held);
    assert!(reserve(&config, &request).is_ok());
    fs::remove_dir_all(config.socket_path.parent().unwrap().parent().unwrap()).unwrap();
}

#[test]
fn cached_image_config_must_match_its_pinned_digest_and_platform() {
    let (root, mut config) = super::super::tests::test_config();
    let path = root.join("image.json");
    let raw=br#"{"os":"linux","architecture":"amd64","config":{"Entrypoint":["/checker"],"Cmd":["--json"]}}"#;
    fs::write(&path, raw).unwrap();
    fs::set_permissions(&path, fs::Permissions::from_mode(0o400)).unwrap();
    let cache = &mut config.cache[0];
    cache.config_image_id = format!("sha256:{:x}", Sha256::digest(raw));
    cache.smol = Some(SmolImage {
        archive: root.join("unused.tar"),
        archive_sha256: format!("sha256:{}", "a".repeat(64)),
        image_config: path.clone(),
    });
    inspect_image(cache).unwrap();
    fs::hard_link(&path, root.join("runtime-cache-alias")).unwrap();
    inspect_image(cache).unwrap();
    cache.architecture = "arm64".into();
    assert!(inspect_image(cache).is_err());
    cache.architecture = "amd64".into();
    fs::set_permissions(&path, fs::Permissions::from_mode(0o600)).unwrap();
    fs::write(&path, b"{}").unwrap();
    assert!(inspect_image(cache).is_err());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn private_child_home_is_derived_from_the_exact_lease() {
    let (root, _config) = super::super::tests::test_config();
    let lease_root = root.join("smol-leases");
    let child_home_root = root.join("trial-child-homes");
    let name = format!("ws-{}", "a".repeat(32));
    let runtime = SmolConfig {
        binary: root.join("runtime"),
        binary_sha256: format!("sha256:{}", "a".repeat(64)),
        home: child_home_root.join(format!("{name}.home")),
        guest_binary: root.join("guest"),
        guest_sha256: format!("sha256:{}", "b".repeat(64)),
        cgroup_root: root.join("groups"),
        maximum_parallel: 2,
        maximum_storage_bytes: 4 * 1024 * 1024 * 1024,
    };
    let mut lease = Lease {
        name,
        owner: "b".repeat(64),
        epoch: "c".repeat(64),
        expires_ms: 1,
        lifetime_ms: 1,
        root: lease_root,
        runtime,
        private_home_root: Some(child_home_root),
    };
    assert!(lease.valid());
    lease.runtime.home = root.join("shared-or-foreign-home");
    assert!(!lease.valid());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn quarantined_admission_makes_runtime_health_unavailable() {
    let (root, mut config) = super::super::tests::test_config();
    let admission = Arc::new(
        Admission::new(
            Capacity {
                slots: 2,
                memory_bytes: 20,
                storage_bytes: 20,
            },
            "e".repeat(64),
        )
        .unwrap(),
    );
    let held = admission
        .reserve(
            Capacity {
                slots: 1,
                memory_bytes: 10,
                storage_bytes: 10,
            },
            Some(Capacity {
                slots: 1,
                memory_bytes: 10,
                storage_bytes: 10,
            }),
        )
        .unwrap();
    held.child(Capacity {
        slots: 1,
        memory_bytes: 10,
        storage_bytes: 10,
    })
    .unwrap()
    .quarantine();
    config.smol_admission = Some(admission);
    assert_eq!(ready(&config).unwrap_err(), "node admission quarantined");
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn intake_overlay_is_explicit_in_runtime_argv_and_project_creation_is_unchanged() {
    let (root, mut config) = super::super::tests::test_config();
    let log = root.join("argv");
    let binary = root.join("smol");
    fs::write(
        &binary,
        format!(
            "#!/bin/sh\nprintf '%s\\n' \"$@\" > '{}'\nexit 1\n",
            log.display()
        ),
    )
    .unwrap();
    fs::set_permissions(&binary, fs::Permissions::from_mode(0o700)).unwrap();
    let runtime = SmolConfig {
        binary,
        binary_sha256: format!("sha256:{}", "a".repeat(64)),
        home: root.join("home"),
        guest_binary: root.join("guest"),
        guest_sha256: format!("sha256:{}", "b".repeat(64)),
        cgroup_root: root.join("groups"),
        maximum_parallel: 1,
        maximum_storage_bytes: 4 * 1024 * 1024 * 1024,
    };
    config.cache[0].smol = Some(SmolImage {
        archive: root.join("intake.tar"),
        archive_sha256: format!("sha256:{}", "c".repeat(64)),
        image_config: root.join("intake.json"),
    });
    let lease = Lease {
        name: format!("ws-{}", "0".repeat(32)),
        owner: "d".repeat(64),
        epoch: "e".repeat(64),
        expires_ms: 1,
        lifetime_ms: 1,
        root: root.join("leases"),
        runtime,
        private_home_root: None,
    };
    fs::create_dir_all(lease.cgroup()).unwrap();
    // A private ordinary file substitutes the cgroup control, with no host effect.
    fs::write(lease.cgroup().join("cgroup.procs"), b"").unwrap();
    let mut machine = Machine {
        lease,
        guardian: Command::new("/bin/true").spawn().unwrap(),
        keeper: None,
        consumed: false,
    };
    let (client, _peer) = UnixStream::pair().unwrap();
    let request = parse_request(include_bytes!("../../../fixtures/request.json")).unwrap();
    let mut resources = Resources::from(&request);
    resources.storage_gib = 2;
    let mut base = None;
    for overlay in [None, Some(1)] {
        assert_eq!(
            machine
                .prepare(
                    &config.cache[0],
                    resources,
                    overlay,
                    &client,
                    Instant::now() + SOCKET_IO_TIMEOUT
                )
                .unwrap_err(),
            "runtime command failed"
        );
        let captured = fs::read_to_string(&log).unwrap();
        let mut args: Vec<_> = captured.lines().map(str::to_owned).collect();
        let storage = args.iter().position(|arg| arg == "--storage").unwrap();
        assert_eq!(args[storage + 1], "2");
        if overlay.is_some() {
            assert_eq!(args.split_off(args.len() - 2), ["--overlay", "1"]);
            assert_eq!(base.as_ref(), Some(&args));
        } else {
            assert!(!args.iter().any(|arg| arg == "--overlay"));
            base = Some(args);
        }
    }
    machine.guardian.wait().unwrap();
    drop(machine);
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn runtime_command_disables_image_seeds_despite_conflicting_ambient_environment() {
    const CHILD: &str = "WORKSTREAM_TEST_SMOL_SEED_POLICY_CHILD";
    if std::env::var_os(CHILD).is_none() {
        // Isolate the conflicting environment from other tests in this process.
        let output = Command::new(std::env::current_exe().unwrap())
            .args(["--exact", "smol::tests::runtime_command_disables_image_seeds_despite_conflicting_ambient_environment", "--nocapture"])
            .env(CHILD, "1")
            .env("SMOLVM_IMAGE_SEEDS", "1")
            .output()
            .unwrap();
        assert!(
            output.status.success(),
            "seed-policy child failed: {}{}",
            String::from_utf8_lossy(&output.stdout),
            String::from_utf8_lossy(&output.stderr)
        );
        return;
    }
    assert_eq!(std::env::var("SMOLVM_IMAGE_SEEDS").unwrap(), "1");
    let (root, _) = super::super::tests::test_config();
    let binary = root.join("runtime-probe");
    fs::write(
        &binary,
        b"#!/bin/sh\nprintf '%s\\n' \"$SMOLVM_IMAGE_SEEDS\" \"$HOME\" \"$PATH\" \"$@\"\n",
    )
    .unwrap();
    fs::set_permissions(&binary, fs::Permissions::from_mode(0o700)).unwrap();
    let runtime = SmolConfig {
        binary,
        binary_sha256: format!("sha256:{}", "a".repeat(64)),
        home: root.join("home"),
        guest_binary: root.join("guest"),
        guest_sha256: format!("sha256:{}", "b".repeat(64)),
        cgroup_root: root.join("groups"),
        maximum_parallel: 1,
        maximum_storage_bytes: 4 * 1024 * 1024 * 1024,
    };
    let output = command(
        &runtime,
        &["machine", "start", "--name", "owned-probe", "--no-workload"],
        None,
    )
    .unwrap()
    .output()
    .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8(output.stdout).unwrap();
    let observed: Vec<_> = stdout.lines().collect();
    assert_eq!(
        observed[0], "0",
        "owned runtime must disable seed creation and reuse"
    );
    assert_eq!(observed[1], runtime.home.to_str().unwrap());
    assert_eq!(observed[2], "/usr/local/bin:/usr/bin:/bin");
    assert_eq!(
        &observed[3..],
        ["machine", "start", "--name", "owned-probe", "--no-workload"]
    );
    fs::remove_dir_all(root).unwrap();
}
