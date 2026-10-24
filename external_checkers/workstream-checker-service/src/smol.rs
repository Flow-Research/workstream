//! Private Smol engine. Product callers retain the existing checker contract.
use super::*;
use std::os::unix::process::CommandExt;
use std::sync::{
    atomic::{AtomicBool, AtomicUsize, Ordering},
    Arc,
};
use workstream_checker_guest::{
    GuestJob, GuestPurpose, MaterialFile, CAPACITY_EXIT_CODE, MAX_JOB_BYTES,
};

const CONTROL_OUTPUT: usize = 256 * 1024;
const HOST_OVERHEAD: u64 = 512 * 1024 * 1024;
const GUEST_OVERHEAD_MIB: u64 = 128;
const VERSION: &str = "1.31.4";

mod intake;
pub(super) use intake::{serve as serve_intake, IntakeConfig};

#[derive(Clone, Copy)]
struct Resources {
    cpu_millis: u64,
    memory_bytes: u64,
    storage_gib: u64,
}
impl From<&ValidatedRequest> for Resources {
    fn from(value: &ValidatedRequest) -> Self {
        Self {
            cpu_millis: value.cpu_millis,
            memory_bytes: value.memory_bytes,
            storage_gib: 1,
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct SmolConfig {
    pub binary: PathBuf,
    pub binary_sha256: String,
    pub home: PathBuf,
    pub guest_binary: PathBuf,
    pub guest_sha256: String,
    pub cgroup_root: PathBuf,
    pub maximum_parallel: usize,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct SmolImage {
    pub archive: PathBuf,
    pub archive_sha256: String,
    pub image_config: PathBuf,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Lease {
    name: String,
    owner: String,
    epoch: String,
    expires_ms: u64,
    lifetime_ms: u64,
    root: PathBuf,
    runtime: SmolConfig,
}
struct Machine {
    lease: Lease,
    guardian: Child,
    keeper: Option<std::process::ChildStdin>,
    consumed: bool,
}

#[derive(Debug)]
pub(super) struct Admission {
    memory: AtomicUsize,
    slots: AtomicUsize,
    maximum_slots: usize,
    epoch: String,
    limit: usize,
}
pub(super) struct Reservation {
    admission: Arc<Admission>,
    bytes: usize,
}
impl Drop for Reservation {
    fn drop(&mut self) {
        self.admission
            .memory
            .fetch_sub(self.bytes, Ordering::SeqCst);
        self.admission.slots.fetch_sub(1, Ordering::SeqCst);
    }
}
pub(super) fn reserve(
    config: &ServiceConfig,
    request: &ValidatedRequest,
) -> Result<Reservation, String> {
    reserve_resources(config, request.into())
}
fn reserve_resources(config: &ServiceConfig, resources: Resources) -> Result<Reservation, String> {
    let admission = config
        .smol_admission
        .as_ref()
        .ok_or("admission unavailable")?
        .clone();
    let bytes = usize::try_from(resources.memory_bytes.saturating_add(HOST_OVERHEAD))
        .map_err(|_| "capacity unavailable")?;
    admission
        .slots
        .fetch_update(Ordering::SeqCst, Ordering::SeqCst, |used| {
            used.checked_add(1)
                .filter(|next| *next <= admission.maximum_slots)
        })
        .map_err(|_| "capacity unavailable")?;
    if admission
        .memory
        .fetch_update(Ordering::SeqCst, Ordering::SeqCst, |used| {
            used.checked_add(bytes)
                .filter(|next| *next <= admission.limit)
        })
        .is_err()
    {
        admission.slots.fetch_sub(1, Ordering::SeqCst);
        return Err("capacity unavailable".into());
    }
    Ok(Reservation { admission, bytes })
}
fn memory_capacity(s: &SmolConfig) -> Result<usize, String> {
    let limit: usize = fs::read_to_string(s.cgroup_root.join("memory.max"))
        .map_err(|_| "node memory bound missing")?
        .trim()
        .parse()
        .map_err(|_| "node memory must be bounded")?;
    if limit <= HOST_OVERHEAD as usize {
        return Err("node memory insufficient".into());
    }
    Ok(limit - 128 * 1024 * 1024)
}

fn random_token() -> Result<String, String> {
    let mut bytes = [0u8; 32];
    File::open("/dev/urandom")
        .and_then(|mut f| f.read_exact(&mut bytes))
        .map_err(|_| "randomness unavailable")?;
    Ok(bytes.iter().map(|v| format!("{v:02x}")).collect())
}

fn now_ms() -> Result<u64, String> {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .map_err(|_| "clock unavailable".into())
}
fn private_directory(path: &Path) -> Result<(), String> {
    let metadata = fs::symlink_metadata(path).map_err(|_| "private directory missing")?;
    if !private_socket_parent(&metadata)
        || fs::canonicalize(path).map_err(|_| "directory unavailable")? != path
    {
        return Err("directory custody invalid".into());
    }
    Ok(())
}
fn hash_file(path: &Path, expected: &str) -> Result<(), String> {
    if !valid_digest(expected) || !path.is_absolute() {
        return Err("cache identity invalid".into());
    }
    let mut file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(path)
        .map_err(|_| "cache unavailable")?;
    let metadata = file.metadata().map_err(|_| "cache unavailable")?;
    // Smol retains a hard link to imported local archives in its private cache.
    // Verify the inode's bytes and write permissions, not a single-link count.
    if !metadata.is_file() || metadata.mode() & 0o022 != 0 {
        return Err("cache custody invalid".into());
    }
    let mut digest = Sha256::new();
    let mut bytes = [0u8; 65536];
    loop {
        let n = file.read(&mut bytes).map_err(|_| "cache read failed")?;
        if n == 0 {
            break;
        }
        digest.update(&bytes[..n]);
    }
    if format!("sha256:{:x}", digest.finalize()) != expected {
        return Err("cache digest differs".into());
    }
    Ok(())
}
fn settings(config: &ServiceConfig) -> Result<&SmolConfig, String> {
    config
        .smol
        .as_ref()
        .ok_or_else(|| "Smol configuration missing".into())
}
pub(super) fn validate(config: &ServiceConfig) -> Result<(), String> {
    let s = settings(config)?;
    if config.operating_system != "linux"
        || config.architecture != "amd64"
        || s.maximum_parallel == 0
        || s.maximum_parallel > 64
        || !s.cgroup_root.is_absolute()
    {
        return Err("Smol configuration invalid".into());
    }
    private_directory(&s.home)?;
    let membership =
        fs::read_to_string("/proc/self/cgroup").map_err(|_| "cgroup membership unavailable")?;
    let relative = membership
        .lines()
        .find_map(|line| line.strip_prefix("0::/"))
        .ok_or("cgroup v2 required")?;
    let current = Path::new("/sys/fs/cgroup").join(relative);
    let metadata = fs::metadata(&s.cgroup_root).map_err(|_| "delegated cgroup unavailable")?;
    if current.parent() != Some(s.cgroup_root.as_path())
        || metadata.uid() != unsafe { libc::geteuid() }
    {
        return Err("service must run in its delegated controller subgroup".into());
    }
    fs::write(
        s.cgroup_root.join("cgroup.subtree_control"),
        "+cpu +memory +pids",
    )
    .map_err(|_| "cgroup delegation unavailable")?;
    hash_file(&s.binary, &s.binary_sha256)?;
    hash_file(&s.guest_binary, &s.guest_sha256)?;
    for image in &config.cache {
        inspect_image(image)?;
        let source = image.smol.as_ref().ok_or("Smol image missing")?;
        hash_file(&source.archive, &source.archive_sha256)?;
    }
    Ok(())
}
pub(super) fn inspect_image(image: &CacheEntry) -> Result<(), String> {
    let source = image.smol.as_ref().ok_or("Smol image missing")?;
    hash_file(&source.image_config, &image.config_image_id)?;
    let value: Value =
        serde_json::from_slice(&read_bounded_file(&source.image_config, MAX_REQUEST_BYTES)?)
            .map_err(|_| "image configuration invalid")?;
    if value["os"].as_str() != Some(&image.operating_system)
        || value["architecture"].as_str() != Some(&image.architecture)
    {
        return Err("image platform differs".into());
    }
    image_command(&value)?;
    Ok(())
}
fn image_command(value: &Value) -> Result<Vec<String>, String> {
    let mut command = Vec::new();
    for field in ["Entrypoint", "Cmd"] {
        if value["config"][field].is_null() {
            continue;
        }
        for argument in value["config"][field]
            .as_array()
            .ok_or("image command invalid")?
        {
            command.push(argument.as_str().ok_or("image command invalid")?.to_owned());
        }
    }
    if command.is_empty() || command.len() > 256 {
        return Err("image command missing".into());
    }
    Ok(command)
}
pub(super) fn ready(config: &ServiceConfig) -> Result<(), String> {
    let s = settings(config)?;
    memory_capacity(s)?;
    let kvm = OpenOptions::new()
        .read(true)
        .write(true)
        .open("/dev/kvm")
        .map_err(|_| "KVM unavailable")?;
    // KVM rejects a nonzero argument even for GET_API_VERSION. Supplying no
    // variadic argument left an indeterminate register in optimized builds.
    if unsafe { libc::ioctl(kvm.as_raw_fd(), 0xae00, 0 as libc::c_ulong) } != 12 {
        return Err("KVM API unavailable".into());
    }
    let controllers = fs::read_to_string(s.cgroup_root.join("cgroup.subtree_control"))
        .map_err(|_| "cgroup delegation unavailable")?;
    if !["cpu", "memory", "pids"]
        .iter()
        .all(|c| controllers.split_whitespace().any(|v| v == *c))
    {
        return Err("cgroup controllers unavailable".into());
    }
    let output = control(
        s,
        &["--version"],
        None,
        Instant::now() + DOCKER_CONTROL_TIMEOUT,
        None,
    )?;
    if !output.status.success()
        || !String::from_utf8_lossy(&output.stdout)
            .split_whitespace()
            .any(|v| v == VERSION)
    {
        return Err("Smol version differs".into());
    }
    Ok(())
}
fn command(s: &SmolConfig, args: &[&str], cgroup: Option<&Path>) -> Result<Command, String> {
    let mut command = Command::new(&s.binary);
    command
        .args(args)
        .env_clear()
        .env("HOME", &s.home)
        .env("PATH", "/usr/local/bin:/usr/bin:/bin")
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .process_group(0);
    let group_file = cgroup
        .map(|path| {
            OpenOptions::new()
                .write(true)
                .open(path.join("cgroup.procs"))
        })
        .transpose()
        .map_err(|_| "cgroup unavailable")?;
    // Only async-signal-safe syscalls in the child before exec. Writing zero
    // joins the calling process and therefore all subsequently forked VMMs.
    unsafe {
        command.pre_exec(move || {
            if libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL, 0, 0, 0) != 0 {
                return Err(std::io::Error::last_os_error());
            }
            if let Some(file) = &group_file {
                if libc::write(file.as_raw_fd(), b"0".as_ptr().cast(), 1) != 1 {
                    return Err(std::io::Error::last_os_error());
                }
            }
            Ok(())
        });
    }
    Ok(command)
}
fn collect(
    child: Child,
    deadline: Instant,
    maximum: usize,
    client: Option<&UnixStream>,
) -> Result<BoundedCommandOutput, String> {
    collect_bounded_command(child, deadline, maximum, client, None).map_err(|error| {
        match error.as_str() {
            "process deadline exceeded" => "deadline_exceeded".into(),
            "process output unbounded" => "invalid_output".into(),
            _ => "implementation_unavailable".into(),
        }
    })
}
fn control(
    s: &SmolConfig,
    args: &[&str],
    cgroup: Option<&Path>,
    deadline: Instant,
    client: Option<&UnixStream>,
) -> Result<BoundedCommandOutput, String> {
    if Instant::now() >= deadline {
        return Err("deadline_exceeded".into());
    }
    let child = command(s, args, cgroup)?
        .spawn()
        .map_err(|_| "runtime launch unavailable")?;
    collect(child, deadline, CONTROL_OUTPUT, client)
}
fn checked(
    s: &SmolConfig,
    args: &[&str],
    group: Option<&Path>,
    deadline: Instant,
    client: Option<&UnixStream>,
) -> Result<(), String> {
    let output = control(s, args, group, deadline, client)?;
    if output.status.success() {
        Ok(())
    } else {
        eprintln!(
            "Smol control operation failed: {}",
            String::from_utf8_lossy(&output._stderr)
        );
        Err("runtime command failed".into())
    }
}
impl Lease {
    fn cgroup(&self) -> PathBuf {
        self.runtime.cgroup_root.join(&self.name)
    }
    fn path(&self) -> PathBuf {
        self.root.join(format!("{}.json", self.name))
    }
    fn disk_path(&self) -> PathBuf {
        // Smol 1.31.4 agent::vm_data_dir uses the first eight SHA-256 bytes.
        // Only inspect this exact lease's path; never sweep its cache root.
        let digest = format!("{:x}", Sha256::digest(self.name.as_bytes()));
        self.runtime
            .home
            .join(".cache/smolvm/vms")
            .join(&digest[..16])
    }
    fn valid(&self) -> bool {
        valid_full_container_id(&self.owner)
            && valid_full_container_id(&self.epoch)
            && self.name.starts_with("ws-")
            && self.name.len() == 35
            && self.name[3..]
                .bytes()
                .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
    }
    fn inventory(&self, deadline: Instant) -> Result<bool, String> {
        let output = control(
            &self.runtime,
            &["machine", "ls", "--json"],
            None,
            deadline,
            None,
        )?;
        if !output.status.success() {
            return Err("runtime inventory unavailable".into());
        }
        let value: Value =
            serde_json::from_slice(&output.stdout).map_err(|_| "runtime inventory invalid")?;
        let rows = value
            .as_array()
            .or_else(|| value.get("machines").and_then(Value::as_array))
            .ok_or("runtime inventory invalid")?;
        let matches: Vec<_> = rows
            .iter()
            .filter(|v| v["name"].as_str() == Some(&self.name))
            .collect();
        if matches.len() > 1 {
            return Err("runtime inventory ambiguous".into());
        }
        if let Some(row) = matches.first() {
            if row["labels"]["workstream.external-checker-owner"].as_str() != Some(&self.owner) {
                return Err("runtime owner differs".into());
            }
            return Ok(true);
        }
        Ok(false)
    }
    fn cleanup(&self) -> Result<(), String> {
        if !self.valid() {
            return Err("lease ownership invalid".into());
        }
        let deadline = Instant::now() + CLEANUP_TIMEOUT;
        let group = self.cgroup();
        if group.exists() {
            fs::write(group.join("cgroup.kill"), "1").map_err(|_| "cgroup cleanup unavailable")?;
            loop {
                let events = fs::read_to_string(group.join("cgroup.events"))
                    .map_err(|_| "cgroup state unavailable")?;
                if events.lines().any(|line| line == "populated 0") {
                    break;
                }
                if Instant::now() >= deadline {
                    return Err("cgroup cleanup unsettled".into());
                }
                thread::sleep(Duration::from_millis(5));
            }
        }
        if self.inventory(deadline)? {
            checked(
                &self.runtime,
                &["machine", "delete", "--name", &self.name, "--force"],
                None,
                deadline,
                None,
            )?;
        }
        if self.inventory(deadline)? {
            return Err("VM cleanup unsettled".into());
        }
        match fs::symlink_metadata(self.disk_path()) {
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            _ => return Err("VM disk cleanup unsettled".into()),
        }
        if group.exists() {
            fs::remove_dir(&group).map_err(|_| "cgroup removal unsettled")?;
        }
        fs::remove_file(self.path()).map_err(|_| "lease removal failed")?;
        File::open(&self.root)
            .and_then(|f| f.sync_all())
            .map_err(|_| "lease persistence failed")?;
        Ok(())
    }
}
impl Machine {
    fn create(
        config: &ServiceConfig,
        resources: Resources,
        deadline: Instant,
    ) -> Result<Self, String> {
        let s = settings(config)?.clone();
        let root = config
            .socket_path
            .parent()
            .ok_or("socket parent missing")?
            .join("smol-leases");
        let mut random = [0u8; 16];
        File::open("/dev/urandom")
            .and_then(|mut f| f.read_exact(&mut random))
            .map_err(|_| "randomness unavailable")?;
        let nonce: String = random.iter().map(|b| format!("{b:02x}")).collect();
        let owner = container_owner(config)?.to_owned();
        let lease = Lease {
            name: format!("ws-{nonce}"),
            owner,
            epoch: config
                .smol_admission
                .as_ref()
                .ok_or("admission unavailable")?
                .epoch
                .clone(),
            expires_ms: now_ms()?.saturating_add(
                deadline
                    .saturating_duration_since(Instant::now())
                    .as_millis() as u64,
            ),
            lifetime_ms: deadline
                .saturating_duration_since(Instant::now())
                .as_millis() as u64,
            root,
            runtime: s,
        };
        let bytes = serde_json::to_vec(&lease).map_err(|_| "lease encoding failed")?;
        let mut file = OpenOptions::new()
            .create_new(true)
            .write(true)
            .mode(0o600)
            .open(lease.path())
            .map_err(|_| "lease create failed")?;
        file.write_all(&bytes)
            .and_then(|_| file.sync_all())
            .map_err(|_| "lease persistence failed")?;
        File::open(&lease.root)
            .and_then(|f| f.sync_all())
            .map_err(|_| "lease persistence failed")?;
        // Persist ownership before any runtime resource is created. The guardian
        // is a distinct exec with its own lifetime and only this lease's custody.
        let mut guardian =
            Command::new(std::env::current_exe().map_err(|_| "service executable unavailable")?)
                .arg("--smol-guardian")
                .arg(lease.path())
                .env_clear()
                .stdin(Stdio::piped())
                .stdout(Stdio::piped())
                .stderr(Stdio::null())
                .spawn()
                .map_err(|_| "guardian unavailable")?;
        let keeper = guardian.stdin.take();
        let mut handshake = guardian
            .stdout
            .take()
            .ok_or("guardian handshake unavailable")?;
        set_nonblocking(&handshake)?;
        let mut bytes = Vec::new();
        let handshake_deadline = deadline.min(Instant::now() + SOCKET_IO_TIMEOUT);
        loop {
            read_available(&mut handshake, &mut bytes, 1)?;
            if bytes == [1] {
                break;
            }
            if Instant::now() >= handshake_deadline {
                drop(keeper);
                return Err("guardian handshake timed out".into());
            }
            thread::sleep(Duration::from_millis(5));
        }
        let mut machine = Self {
            lease,
            guardian,
            keeper,
            consumed: false,
        };
        if machine.configure_cgroup(resources).is_err() {
            let _ = machine.close();
            return Err("cgroup reservation unavailable".into());
        }
        Ok(machine)
    }
    fn configure_cgroup(&self, resources: Resources) -> Result<(), String> {
        let group = self.lease.cgroup();
        fs::create_dir(&group).map_err(|_| "cgroup allocation failed")?;
        for (file, value) in [
            ("cpu.max", format!("{} 100000", resources.cpu_millis * 100)),
            (
                "memory.max",
                resources
                    .memory_bytes
                    .saturating_add(HOST_OVERHEAD)
                    .to_string(),
            ),
            ("memory.swap.max", "0".into()),
            ("memory.oom.group", "1".into()),
            ("pids.max", "512".into()),
        ] {
            fs::write(group.join(file), value).map_err(|_| "cgroup enforcement failed")?;
        }
        Ok(())
    }
    fn prepare(
        &self,
        cache: &CacheEntry,
        resources: Resources,
        client: &UnixStream,
        deadline: Instant,
    ) -> Result<(), String> {
        let lease = &self.lease;
        let s = &lease.runtime;
        let group = lease.cgroup();
        let image = cache.smol.as_ref().ok_or("Smol image missing")?;
        let archive = image.archive.to_str().ok_or("image path invalid")?;
        let label = format!("workstream.external-checker-owner={}", lease.owner);
        checked(
            s,
            &[
                "machine",
                "create",
                "--name",
                &lease.name,
                "--image",
                archive,
                "--label",
                &label,
                "--cpus",
                &resources.cpu_millis.div_ceil(1000).to_string(),
                "--mem",
                &(resources.memory_bytes.div_ceil(1024 * 1024) + GUEST_OVERHEAD_MIB).to_string(),
                "--storage",
                &resources.storage_gib.to_string(),
            ],
            Some(&group),
            deadline,
            Some(client),
        )?;
        checked(
            s,
            &["machine", "start", "--name", &lease.name, "--no-workload"],
            Some(&group),
            deadline,
            Some(client),
        )?;
        checked(
            s,
            &[
                "machine",
                "cp",
                "--mode",
                "0555",
                s.guest_binary.to_str().ok_or("guest path invalid")?,
                &format!("{}:/.workstream-guest", lease.name),
            ],
            Some(&group),
            deadline,
            Some(client),
        )
    }
    fn run(
        &mut self,
        cache: &CacheEntry,
        config: &ServiceConfig,
        request: &ValidatedRequest,
        workspace: &Path,
        client: &UnixStream,
        deadline: Instant,
    ) -> Result<ExecutedChecker, String> {
        if self.consumed {
            return Err("execution already consumed".into());
        }
        self.consumed = true;
        let inventory = inspect_workspace(workspace, config.sandbox_uid, config.sandbox_gid)?;
        let source = cache.smol.as_ref().ok_or("Smol image missing")?;
        let value: Value =
            serde_json::from_slice(&read_bounded_file(&source.image_config, MAX_REQUEST_BYTES)?)
                .map_err(|_| "image configuration invalid")?;
        let environment = match value["config"]["Env"].as_array() {
            Some(items) => items
                .iter()
                .map(|v| {
                    v.as_str()
                        .map(str::to_owned)
                        .ok_or("image environment invalid")
                })
                .collect::<Result<Vec<_>, _>>()?,
            None if value["config"]["Env"].is_null() => Vec::new(),
            _ => return Err("image environment invalid".into()),
        };
        let job = GuestJob {
            purpose: GuestPurpose::Project,
            request: request.value.clone(),
            command: image_command(&value)?,
            environment,
            working_directory: value["config"]["WorkingDir"]
                .as_str()
                .unwrap_or("/")
                .to_owned(),
            uid: config.sandbox_uid,
            gid: config.sandbox_gid,
            directories: inventory.directories,
            files: inventory
                .files
                .into_iter()
                .map(|f| MaterialFile {
                    normalized_path: f.normalized_path,
                    byte_count: f.byte_count,
                    sha256: f.sha256,
                    executable: f.executable,
                })
                .collect(),
        };
        let bytes = serde_json::to_vec(&job).map_err(|_| "guest job invalid")?;
        if bytes.len() > MAX_JOB_BYTES {
            return Err("guest job too large".into());
        }
        let mut cmd = command(
            &self.lease.runtime,
            &[
                "machine",
                "exec",
                "--name",
                &self.lease.name,
                "--user",
                "0:0",
                "--interactive",
                "--stream",
                "--",
                "/.workstream-guest",
            ],
            Some(&self.lease.cgroup()),
        )?;
        cmd.stdin(Stdio::piped());
        let mut child = cmd.spawn().map_err(|_| "guest launch failed")?;
        let mut stdin = child.stdin.take().ok_or("guest input unavailable")?;
        let workspace = workspace.to_owned();
        let writer = thread::spawn(move || -> Result<(), String> {
            stdin
                .write_all(&(bytes.len() as u32).to_be_bytes())
                .and_then(|_| stdin.write_all(&bytes))
                .map_err(|_| "guest input failed")?;
            for file in &job.files {
                let mut input = OpenOptions::new()
                    .read(true)
                    .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
                    .open(workspace.join(&file.normalized_path))
                    .map_err(|_| "material unavailable")?;
                let n = std::io::copy(
                    &mut Read::by_ref(&mut input).take(file.byte_count),
                    &mut stdin,
                )
                .map_err(|_| "material transfer failed")?;
                if n != file.byte_count {
                    return Err("material transfer truncated".into());
                }
            }
            Ok(())
        });
        let result = collect(child, deadline, request.maximum_output_bytes, Some(client));
        let written = writer.join().map_err(|_| "material transfer failed")?;
        let output = result?;
        written?;
        if output.status.code() == Some(CAPACITY_EXIT_CODE) {
            return Err("capacity_exceeded".into());
        }
        if !output.status.success() {
            return Err("implementation_unavailable".into());
        }
        let value = serde_json::from_slice(&output.stdout).map_err(|_| "invalid_output")?;
        Ok(ExecutedChecker { value })
    }
    fn close(&mut self) -> Result<(), String> {
        // EOF transfers cleanup exclusively to the guardian. Wait for its durable
        // absence confirmation before returning capacity or a result.
        drop(self.keeper.take());
        let status = reap_child(
            &mut self.guardian,
            Instant::now() + CLEANUP_TIMEOUT + SOCKET_IO_TIMEOUT,
        )?;
        if status.success() && !self.lease.path().exists() && !self.lease.cgroup().exists() {
            Ok(())
        } else {
            Err(UNSETTLED_RESOURCE_ERROR.into())
        }
    }
}
impl Drop for Machine {
    fn drop(&mut self) {
        drop(self.keeper.take());
    }
}
pub(super) fn execute(
    config: &ServiceConfig,
    cache: &CacheEntry,
    request: &ValidatedRequest,
    workspace: &Path,
    client: &UnixStream,
    budget: &mut RequestExecutionBudget,
) -> Result<ExecutedChecker, ExecutionFailure> {
    for attempt in 0..3 {
        let mut machine = Machine::create(config, request.into(), budget.deadline)
            .map_err(|_| ExecutionFailure::unsettled(false))?;
        let prepared = machine.prepare(cache, request.into(), client, budget.deadline);
        let launched = prepared.is_ok();
        let result = prepared
            .and_then(|_| machine.run(cache, config, request, workspace, client, budget.deadline));
        if machine.close().is_err() {
            return Err(ExecutionFailure::unsettled(launched));
        }
        if !launched
            && attempt < 2
            && Instant::now() < budget.deadline
            && client_is_connected(client)
        {
            continue;
        }
        return result.map_err(|code| {
            ExecutionFailure::ordinary(
                match code.as_str() {
                    "deadline_exceeded" => "deadline_exceeded",
                    "invalid_output" => "invalid_output",
                    "capacity_exceeded" => "capacity_exceeded",
                    _ => "implementation_unavailable",
                },
                launched,
            )
        });
    }
    unreachable!("bounded preparation attempts always return")
}

pub(super) fn guardian() -> Result<(), String> {
    let path = std::env::args_os().nth(2).ok_or("guardian lease missing")?;
    let bytes = read_bounded_file(Path::new(&path), MAX_ENVELOPE_BYTES)?;
    let lease: Lease = serde_json::from_slice(&bytes).map_err(|_| "guardian lease invalid")?;
    if !lease.valid() || lease.path() != Path::new(&path) {
        return Err("guardian custody invalid".into());
    }
    private_directory(&lease.root)?;
    // Lock custody for this guardian. Startup recovery waits for the old guardian
    // to finish; it cannot delete a live VM behind a surviving controller.
    let file = File::open(&path).map_err(|_| "guardian lease unavailable")?;
    if unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
        return Err("guardian already active".into());
    }
    let input = std::io::stdin();
    set_nonblocking(&input)?;
    std::io::stdout()
        .write_all(&[1])
        .and_then(|_| std::io::stdout().flush())
        .map_err(|_| "guardian handshake failed")?;
    let expires = Instant::now()
        + Duration::from_millis(
            lease
                .expires_ms
                .saturating_sub(now_ms()?)
                .min(lease.lifetime_ms),
        );
    let mut reader = input.lock();
    let mut byte = [0u8; 1];
    loop {
        match reader.read(&mut byte) {
            Ok(_) => break,
            Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {}
            Err(_) => break,
        }
        if Instant::now() >= expires {
            break;
        }
        thread::sleep(Duration::from_millis(20));
    }
    lease.cleanup()
}
pub(super) fn recover(config: &ServiceConfig) -> Result<(), String> {
    let root = config
        .socket_path
        .parent()
        .ok_or("socket parent missing")?
        .join("smol-leases");
    use std::os::unix::fs::DirBuilderExt;
    match fs::DirBuilder::new().mode(0o700).create(&root) {
        Ok(()) => {}
        Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => {}
        Err(_) => return Err("lease directory unavailable".into()),
    }
    private_directory(&root)?;
    for entry in fs::read_dir(&root).map_err(|_| "lease inventory unavailable")? {
        let entry = entry.map_err(|_| "lease inventory unavailable")?;
        let lease: Lease =
            serde_json::from_slice(&read_bounded_file(&entry.path(), MAX_ENVELOPE_BYTES)?)
                .map_err(|_| "lease inventory invalid")?;
        if lease.owner != container_owner(config)?
            || lease.root != root
            || lease.runtime.home != settings(config)?.home
            || lease.runtime.cgroup_root != settings(config)?.cgroup_root
            || !lease.valid()
            || entry.path() != lease.path()
        {
            return Err("lease ownership differs".into());
        }
        let file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW)
            .open(entry.path())
            .map_err(|_| "lease unavailable")?;
        let deadline = Instant::now() + CLEANUP_TIMEOUT + SOCKET_IO_TIMEOUT;
        loop {
            if unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } == 0 {
                break;
            }
            if Instant::now() >= deadline {
                return Err("prior guardian unsettled".into());
            }
            thread::sleep(Duration::from_millis(20));
        }
        if lease.path().exists() {
            lease.cleanup()?;
        }
    }
    Ok(())
}
pub(super) fn serve<I>(config: &ServiceConfig, connections: I) -> Result<(), String>
where
    I: IntoIterator<Item = std::io::Result<UnixStream>>,
{
    let maximum = settings(config)?.maximum_parallel;
    let mut config = config.clone();
    config.smol_admission = Some(Arc::new(Admission {
        memory: AtomicUsize::new(0),
        slots: AtomicUsize::new(0),
        maximum_slots: maximum,
        epoch: random_token()?,
        limit: memory_capacity(settings(&config)?)?,
    }));
    let config = Arc::new(config);
    let active = Arc::new(AtomicUsize::new(0));
    let failed = Arc::new(AtomicBool::new(false));
    let mut workers = Vec::new();
    for connection in connections {
        let Ok(stream) = connection else { continue };
        if failed.load(Ordering::SeqCst) {
            break;
        }
        workers.retain(|handle: &thread::JoinHandle<()>| !handle.is_finished());
        if active.load(Ordering::SeqCst) >= maximum + 8 {
            drop(stream);
            continue;
        }
        active.fetch_add(1, Ordering::SeqCst);
        let config = config.clone();
        let active = active.clone();
        let failed = failed.clone();
        workers.push(thread::spawn(move || {
            if serve_connection(&config, stream, SOCKET_IO_TIMEOUT).is_err() {
                failed.store(true, Ordering::SeqCst);
                // Terminate the controller so every independent guardian sees EOF.
                // systemd restarts only through exact-owner startup reconciliation.
                std::process::exit(1);
            }
            active.fetch_sub(1, Ordering::SeqCst);
        }));
    }
    for worker in workers {
        let _ = worker.join();
    }
    if failed.load(Ordering::SeqCst) {
        Err(UNSETTLED_RESOURCE_ERROR.into())
    } else {
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn concurrent_capacity_is_reserved_until_its_owner_releases_it() {
        let (_, mut config) = super::super::tests::test_config();
        let request = parse_request(include_bytes!("../../fixtures/request.json")).unwrap();
        let capacity = request.memory_bytes as usize + HOST_OVERHEAD as usize;
        config.smol_admission = Some(Arc::new(Admission {
            memory: AtomicUsize::new(0),
            slots: AtomicUsize::new(0),
            maximum_slots: 1,
            epoch: "e".repeat(64),
            limit: capacity,
        }));
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
}
