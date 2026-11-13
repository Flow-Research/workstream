use super::*;
use serde_json::json;

const GUEST: &str = r#"
import hashlib,json,struct,sys,time,os
mode=sys.argv[1]
if mode=='log_stall':
    while True: os.write(2,b'x'*65536)
if mode=='stall':
    time.sleep(30)
    sys.exit(1)
def read(n):
    b=b''
    while len(b)<n:
        chunk=sys.stdin.buffer.read(n-len(b))
        if not chunk: raise EOFError('truncated')
        b+=chunk
    return b
job=json.loads(read(struct.unpack('>I',read(4))[0]))
if '--pre-limits' in sys.argv: assert json.loads(sys.argv[-1])==job['limits']
root=read(job['root']['bundle_byte_count'])
source=read(job['startup']['request']['reservation']['source']['raw_byte_count'])
assert read(4)==b'\0'*4
assert sys.stdin.buffer.read(1)==b''
if mode=='permitted_logs':
    sys.stderr.buffer.write(b'x'*job['limits']['maximum_log_bytes']);sys.stderr.buffer.flush()
if mode=='logs':
    sys.stderr.buffer.write(b'x'*(job['limits']['maximum_log_bytes']+1));sys.stderr.buffer.flush()
payload=json.dumps({'root':hashlib.sha256(root).hexdigest(),'source':hashlib.sha256(source).hexdigest(),'bytes':len(source),'pid':os.getpid(),'limits':job['limits']}).encode()
if mode=='zero':payload=b''
if mode=='output':payload=b'x'*(job['limits']['maximum_control_bytes']+1)
sys.stdout.buffer.write(struct.pack('>I',len(payload))+payload)
if mode=='trailing':sys.stdout.buffer.write(b'x')
sys.stdout.buffer.flush()
if mode=='failure':sys.exit(9)
"#;

fn child(mode: &str) -> Child {
    Command::new("/usr/bin/python3")
        .args(["-I", "-c", GUEST, mode])
        .env_clear()
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .process_group(0)
        .spawn()
        .unwrap()
}

fn run_case(attack: &str) -> Result<Value, String> {
    let (root, mut config, mut header) = admission::tests::fixture();
    let source = vec![b'z'; 128 * 1024 + 3];
    header["reservation"]["source"]["raw_byte_count"] = json!(source.len());
    header["reservation"]["source"]["raw_sha256"] =
        json!(format!("sha256:{:x}", Sha256::digest(&source)));
    let mut body = header["reservation"]["source"].as_object().unwrap().clone();
    body.insert(
        "schema_version".into(),
        json!("workstream.sealed_submission_source.v1"),
    );
    header["reservation"]["source_sha256"] = json!(canonical_hash(&Value::Object(body)).unwrap());
    let root_digest = format!("sha256:{:x}", Sha256::digest(vec![0_u8; 1024]));
    let pre = config.pre.as_mut().unwrap();
    if attack == "log_stall" || attack == "permitted_logs" {
        let maximum = if attack == "log_stall" {
            u32::MAX as usize
        } else {
            4 * 1024 * 1024
        };
        pre.limits.maximum_log_bytes = maximum;
        pre.profile["maximum_log_bytes"] = json!(maximum);
    }
    pre.root.bundle_sha256 = root_digest.clone();
    pre.profile["platform_root_sha256"] = json!(root_digest);
    pre.profile_sha256 = canonical_hash(&pre.profile).unwrap();
    header["reservation"]["runtime_profile"] = pre.profile.clone();
    header["request_digest"] = json!(canonical_hash(&header["reservation"]).unwrap());
    if attack == "launch" {
        let program = format!("#!/usr/bin/python3\n{GUEST}");
        let path = root.join("runtime");
        fs::write(&path, &program).unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o700)).unwrap();
        let digest = format!("sha256:{:x}", Sha256::digest(program.as_bytes()));
        config.smol.as_mut().unwrap().binary = path;
        config.smol.as_mut().unwrap().binary_sha256 = digest.clone();
        config.pre.as_mut().unwrap().smol_binary_sha256 = digest;
    }
    let mut prepared = admission::prepare(&config, &serde_json::to_vec(&header).unwrap()).unwrap();
    if attack == "root_truncated" {
        fs::write(root.join("root.bundle"), b"short").unwrap();
    }
    if attack == "root" {
        fs::write(root.join("root.bundle"), vec![1_u8; 1024]).unwrap();
    }
    let (mut client, mut producer) = UnixStream::pair().unwrap();
    client.set_nonblocking(true).unwrap();
    let attack = attack.to_owned();
    let producer_attack = attack.clone();
    let producer_thread = thread::spawn(move || {
        if producer_attack == "disconnect" {
            return;
        }
        let _ = (|| -> std::io::Result<()> {
            if producer_attack == "partial" {
                producer.write_all(&[0, 0])?;
            } else if producer_attack == "chunk" {
                producer.write_all(&65537_u32.to_be_bytes())?;
            } else {
                let mut payload = source;
                if producer_attack == "hash" {
                    payload[0] = b'q';
                }
                if producer_attack == "excess" {
                    payload.push(0);
                }
                if producer_attack == "count" {
                    payload.pop();
                }
                for chunk in payload.chunks(65536) {
                    producer.write_all(&(chunk.len() as u32).to_be_bytes())?;
                    producer.write_all(chunk)?;
                }
                producer.write_all(&[0; 4])?;
                if producer_attack == "source_trailing" {
                    producer.write_all(b"x")?;
                }
            }
            let _ = producer.read(&mut [0]);
            Ok(())
        })();
    });
    let result = if attack == "launch" {
        // A regular file stands in for cgroup.procs; this proves host argv and
        // byte transport only, never cgroup enforcement or native VM creation.
        let path = root
            .join("leases")
            .join(format!("ws-{}.json", "0".repeat(32)));
        let mut lease: Lease = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
        lease.runtime = config.smol.as_ref().unwrap().clone();
        lease.pre = Some(prepared.invocation.clone());
        fs::create_dir_all(lease.cgroup()).unwrap();
        fs::write(lease.cgroup().join("cgroup.procs"), b"").unwrap();
        let bytes = serde_json::to_vec(&lease).unwrap();
        fs::write(&path, &bytes).unwrap();
        let file = File::open(&path).unwrap();
        let journal = Journal::capture(&file, &bytes).unwrap();
        let mut machine = Machine {
            lease,
            journal,
            guardian: Command::new("/bin/true").spawn().unwrap(),
            keeper: None,
            consumed: false,
        };
        machine.guardian.wait().unwrap();
        prepared.deadline = Instant::now() + Duration::from_millis(500);
        let result = machine.run_pre(&mut prepared, &mut client);
        assert!(machine.run_pre(&mut prepared, &mut client).is_err());
        result
    } else {
        let child = child(&attack);
        let pid = child.id();
        let deadline = Instant::now() + Duration::from_secs(2);
        let result = exchange(
            child,
            &mut client,
            &mut prepared.root_bundle,
            &prepared.job,
            deadline,
        );
        assert_eq!(
            unsafe { libc::kill(pid as i32, 0) },
            -1,
            "child was not reaped"
        );
        result
    }
    .and_then(|bytes| serde_json::from_slice(&bytes).map_err(|_| "test output invalid".into()));
    drop(client);
    producer_thread.join().unwrap();
    fs::remove_dir_all(root).unwrap();
    result
}

#[test]
fn streams_exact_root_and_multiple_source_chunks_without_a_host_spool() {
    let result = run_case("good").unwrap();
    assert_eq!(result["bytes"], 128 * 1024 + 3);
    assert_eq!(
        result["source"],
        format!("{:x}", Sha256::digest(vec![b'z'; 128 * 1024 + 3]))
    );
    assert_eq!(
        result["root"],
        format!("{:x}", Sha256::digest(vec![0_u8; 1024]))
    );
}

#[test]
fn host_launch_passes_identical_clamped_limits_to_argv_and_job() {
    let result = run_case("launch").unwrap();
    let run = result["limits"]["timeout_ms"].as_u64().unwrap();
    let cleanup = result["limits"]["cleanup_timeout_ms"].as_u64().unwrap();
    assert!(run > 0 && run <= 500);
    assert!(cleanup >= run && cleanup <= 500);
    assert_eq!(
        unsafe { libc::kill(result["pid"].as_u64().unwrap() as i32, 0) },
        -1
    );
}

#[test]
fn large_log_allowances_do_not_prevent_deadline_or_successful_completion() {
    assert_eq!(run_case("log_stall").unwrap_err(), "deadline_exceeded");
    assert!(run_case("permitted_logs").is_ok());
}

#[test]
fn invalid_streams_fail_and_reap_the_owned_process() {
    for attack in [
        "root",
        "root_truncated",
        "excess",
        "zero",
        "hash",
        "count",
        "chunk",
        "source_trailing",
        "partial",
        "disconnect",
        "stall",
        "logs",
        "output",
        "trailing",
        "failure",
    ] {
        assert!(run_case(attack).is_err(), "accepted {attack}");
    }
}

#[test]
fn streaming_connection_allows_queued_bytes_but_detects_disconnect() {
    let (client, mut peer) = UnixStream::pair().unwrap();
    peer.write_all(b"queued ZIP frame").unwrap();
    assert!(connected(&client));
    assert!(!client_is_connected(&client));
    let process = Command::new("/bin/true")
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .process_group(0)
        .spawn()
        .unwrap();
    assert!(collect_bounded_command_with_connection(
        process,
        Instant::now() + Duration::from_secs(1),
        100,
        Some(&client),
        None,
        connected
    )
    .unwrap()
    .status
    .success());
    drop(peer);
    assert!(!connected(&client));
}
