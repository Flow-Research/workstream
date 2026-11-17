//! Feature-selected portable integration proof, explicitly run by checker CI.
use super::*;
use std::os::fd::OwnedFd;
use std::process::{Child, Stdio};

struct ChildGuard(Child);
impl Drop for ChildGuard {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}
struct Directory(PathBuf);
impl Drop for Directory {
    fn drop(&mut self) {
        // The real projector seals directories 0500. Restore only fixture
        // directory permissions so the test owns cleanup even after failure.
        fn writable(path: &Path) {
            fs::set_permissions(path, fs::Permissions::from_mode(0o700)).unwrap();
            for entry in fs::read_dir(path).unwrap() {
                let entry = entry.unwrap();
                if entry.file_type().unwrap().is_dir() {
                    writable(&entry.path());
                }
            }
        }
        writable(&self.0);
        fs::remove_dir_all(&self.0).unwrap();
    }
}
fn wait(child: &mut ChildGuard, deadline: Instant) -> std::process::ExitStatus {
    loop {
        if let Some(status) = child.0.try_wait().unwrap() {
            return status;
        }
        assert!(
            Instant::now() < deadline,
            "Python proof process exceeded deadline"
        );
        thread::sleep(Duration::from_millis(5));
    }
}

#[test]
fn live_python_worker_dialogue() {
    let python = std::env::var_os("WORKSTREAM_PRE_WORKER_PYTHON")
        .expect("pre-dialogue-proof requires the frozen backend Python interpreter");
    let script = Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/pre_dialogue.py");
    for case in ["passing", "secret", "unsafe"] {
        let path = std::env::temp_dir().join(format!("ws-live-pre-{}-{case}", std::process::id()));
        fs::create_dir(&path).unwrap();
        let directory = Directory(path);
        fs::set_permissions(&directory.0, fs::Permissions::from_mode(0o700)).unwrap();
        let mut limits = super::tests::limits();
        limits.timeout_ms = 30_000;
        limits.cleanup_timeout_ms = 45_000;
        let now = Instant::now();
        let envelope = Envelope {
            limits,
            deadline: now + Duration::from_secs(30),
            cleanup: now + Duration::from_secs(45),
        };
        let (parent, child) = socket_pair().unwrap();
        let (stderr, child_stderr) = socket_pair().unwrap();
        let mut process = ChildGuard(
            Command::new(&python)
                .arg(&script)
                .args(["worker", case])
                .arg(&directory.0)
                .env(
                    "WORKSTREAM_PRE_PROOF_LIMITS",
                    serde_json::to_string(&limits).unwrap(),
                )
                .stdin(Stdio::from(OwnedFd::from(child.try_clone().unwrap())))
                .stdout(Stdio::from(OwnedFd::from(child)))
                .stderr(Stdio::from(OwnedFd::from(child_stderr)))
                .spawn()
                .unwrap(),
        );
        parent.set_nonblocking(true).unwrap();
        stderr.set_nonblocking(true).unwrap();
        // ChildGuard owns this portable process; native cgroup cleanup is not
        // simulated. Production Worker framing and terminal sequencing are used.
        let mut worker = Worker {
            active: false,
            pid: None,
            control: parent,
            stderr,
            log_bytes: 0,
            cleanup: envelope.cleanup,
        };
        let prefix = worker
            .read_frame(&envelope)
            .unwrap_or_else(|error| panic!("live worker startup {case}: {error}"));
        let job: PreBootstrapJob = serde_json::from_slice(&prefix).unwrap();
        assert_eq!(job.limits, limits);
        let bound = binding(&job).unwrap();
        let mut project_calls = 0;
        let received = terminal(&mut worker, &envelope, &bound, |frame| {
            project_calls += 1;
            assert_eq!(
                case, "passing",
                "default blocker launched the project phase"
            );
            let (request, manifest) = super::super::project_request(&bound, frame)?;
            assert_eq!(manifest.entries.len(), 2);
            assert_eq!(manifest.entries[0].path(), "nested");
            assert_eq!(manifest.entries[1].path(), "nested/work.txt");
            assert_eq!(
                request.value["input"]["manifest"][0],
                json!({"normalized_path":"nested",
                "entry_type":"directory","byte_count":0,"sha256":null,"executable":null})
            );
            assert_eq!(request.value["input"]["manifest"][1]["byte_count"], 14);
            assert_eq!(
                request.value["input"]["manifest"][1]["sha256"],
                format!("sha256:{:x}", Sha256::digest(b"finished work\n"))
            );
            let result = workstream_checker_sdk::completed_result(&request, vec![])?;
            Ok(
                json!({"request_digest":bound.request_digest,"lease_id":bound.lease_id,
                "lease_generation":bound.lease_generation,"result":result}),
            )
        });
        let received = received.unwrap_or_else(|error| {
            panic!("live case {case} failed after {project_calls} project calls: {error}")
        });
        assert_eq!(project_calls, usize::from(case == "passing"));
        assert!(wait(&mut process, envelope.cleanup).success());
        worker
            .check_logs(limits.maximum_log_bytes, envelope.cleanup)
            .unwrap();
        assert_eq!(
            worker.log_bytes, 0,
            "Python worker emitted unexpected diagnostics"
        );
        let mut trailing = [0];
        assert_eq!(worker.control.read(&mut trailing).unwrap(), 0);
        // A fresh Python decoder validates the exact received completion, not
        // a re-created Rust expectation or the helper's simulated reply.
        let completion = directory.0.join("received-completion.json");
        fs::write(&completion, &received).unwrap();
        let mut validator = ChildGuard(
            Command::new(&python)
                .arg(&script)
                .args(["validate", case])
                .arg(&directory.0)
                .stdin(Stdio::from(File::open(&completion).unwrap()))
                .stdout(Stdio::piped())
                .stderr(Stdio::inherit())
                .spawn()
                .unwrap(),
        );
        assert!(
            wait(&mut validator, envelope.cleanup).success(),
            "typed completion rejected for {case}"
        );
        let mut report = String::new();
        validator
            .0
            .stdout
            .take()
            .unwrap()
            .read_to_string(&mut report)
            .unwrap();
        let report: Value = serde_json::from_str(&report).unwrap();
        assert_eq!(report["eligible"], case == "passing");
        assert!(report["result_digest"]
            .as_str()
            .unwrap()
            .starts_with("sha256:"));
    }
}
