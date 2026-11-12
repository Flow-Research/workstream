use super::*;
use std::os::unix::process::CommandExt;
use std::sync::{
    atomic::{AtomicBool, AtomicUsize, Ordering},
    Arc,
};
use workstream_checker_guest::{
    GuestCapabilities, GuestJob, GuestPurpose, MaterialFile, CAPACITY_EXIT_CODE, MAX_JOB_BYTES,
};

const CONTROL_OUTPUT: usize = 256 * 1024;
const HOST_OVERHEAD: u64 = 512 * 1024 * 1024;
const GUEST_OVERHEAD_MIB: u64 = 128;
const VERSION: &str = "1.31.4";

// Pinned Smol creates HOME/.cache/smolvm/vms/<16hex>/control.sock.
// Linux sockaddr_un reserves one of its 108 bytes for the trailing NUL.
pub(super) fn validate_home_socket_path(home: &Path) -> Result<(), String> {
    use std::os::unix::ffi::OsStrExt;
    if home.as_os_str().as_bytes().len() > 107 - 48 {
        return Err("Smol HOME exceeds Unix socket path limit".into());
    }
    Ok(())
}

pub(super) fn validate_child_home_root(root: &Path) -> Result<(), String> {
    validate_home_socket_path(&root.join(format!("ws-{}.home", "0".repeat(32))))
}

mod admission;
pub(crate) use admission::{Admission, Capacity, Reservation};
mod intake;
pub(crate) mod trial;
mod trial_io;
pub(super) use intake::{serve as serve_intake, IntakeConfig};
mod io;
mod pre;
pub(super) use io::{ProjectCallbacks, ProjectMaterials};
pub(super) use pre::admission::Config as PreConfig;

#[derive(Clone, Copy)]
struct Resources {
    cpu_millis: u64,
    memory_bytes: u64,
    storage_gib: u64,
    pids: u64,
}
impl From<&ValidatedRequest> for Resources {
    fn from(value: &ValidatedRequest) -> Self {
        Self {
            cpu_millis: value.cpu_millis,
            memory_bytes: value.memory_bytes,
            storage_gib: 1,
            pids: (value.memory_bytes / (16 * 1024 * 1024)).clamp(16, 256),
        }
    }
}

impl Resources {
    fn host_pids(self) -> u64 {
        // The VMM needs host threads independently of the guest workload's
        // process ceiling. The pinned runtime reaches 57 during cold startup.
        self.pids.max(128)
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
    pub maximum_storage_bytes: u64,
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
    #[serde(default)]
    private_home_root: Option<PathBuf>,
    #[serde(default)]
    pre: Option<pre::Invocation>,
}
struct Machine {
    lease: Lease,
    journal: pre::Journal,
    guardian: Child,
    keeper: Option<std::process::ChildStdin>,
    consumed: bool,
}

pub(super) fn reserve(
    config: &ServiceConfig,
    request: &ValidatedRequest,
) -> Result<Arc<Reservation>, String> {
    reserve_resources(config, request.into())
}
fn resource_capacity(resources: Resources, overlay_gib: Option<u64>) -> Result<Capacity, String> {
    Ok(Capacity {
        slots: 1,
        memory_bytes: resources
            .memory_bytes
            .checked_add(HOST_OVERHEAD)
            .ok_or("capacity overflow")?,
        storage_bytes: resources
            .storage_gib
            .checked_add(overlay_gib.unwrap_or(0))
            .and_then(|gib| gib.checked_mul(1024 * 1024 * 1024))
            .ok_or("capacity overflow")?,
    })
}
fn reserve_resources(
    config: &ServiceConfig,
    resources: Resources,
) -> Result<Arc<Reservation>, String> {
    reserve_capacity(config, resource_capacity(resources, None)?, None)
}
pub(super) fn reserve_invocation(
    config: &ServiceConfig,
    request: &ValidatedRequest,
    child: Capacity,
) -> Result<Arc<Reservation>, String> {
    reserve_capacity(
        config,
        resource_capacity(request.into(), None)?,
        Some(child),
    )
}
pub(crate) fn trial_capacity(memory_bytes: u64, disk_bytes: u64) -> Result<Capacity, String> {
    const GIB: u64 = 1024 * 1024 * 1024;
    if memory_bytes == 0 || disk_bytes == 0 {
        return Err("invalid child capacity".into());
    }
    let storage_gib = disk_bytes.checked_add(GIB - 1).ok_or("capacity overflow")? / GIB;
    let mut capacity = resource_capacity(
        Resources {
            cpu_millis: 1,
            memory_bytes,
            storage_gib,
            pids: 2,
        },
        None,
    )?;
    capacity.storage_bytes = capacity
        .storage_bytes
        .checked_add(disk_bytes)
        .ok_or("capacity overflow")?;
    Ok(capacity)
}
pub(crate) fn trial_peak_capacity(
    memory_bytes: u64,
    memory_overrun_bytes: u64,
    disk_bytes: u64,
) -> Result<Capacity, String> {
    trial_capacity(
        memory_bytes
            .checked_add(memory_overrun_bytes)
            .ok_or("capacity overflow")?,
        disk_bytes,
    )
}

pub(crate) fn quarantine(config: &ServiceConfig) {
    if let Some(admission) = &config.smol_admission {
        admission.quarantine();
    }
}
fn reserve_capacity(
    config: &ServiceConfig,
    outer: Capacity,
    child: Option<Capacity>,
) -> Result<Arc<Reservation>, String> {
    let admission = config
        .smol_admission
        .as_ref()
        .ok_or("admission unavailable")?;
    let reservation = admission.reserve(outer, child)?;
    // Reserve atomically first, then recheck physical space. A failure drops the
    // complete reservation; no VM or provider operation has begun.
    let required = admission.reserved_storage_bytes()?;
    if available_storage(settings(config)?)? < required {
        return Err("node storage unavailable".into());
    }
    Ok(reservation)
}
fn available_storage(s: &SmolConfig) -> Result<u64, String> {
    let directory = File::open(&s.home).map_err(|_| "Smol storage unavailable")?;
    let mut values = std::mem::MaybeUninit::<libc::statvfs>::uninit();
    // The descriptor remains open and statvfs writes the complete structure.
    if unsafe { libc::fstatvfs(directory.as_raw_fd(), values.as_mut_ptr()) } != 0 {
        return Err("Smol storage capacity unavailable".into());
    }
    let values = unsafe { values.assume_init() };
    (values.f_bavail as u64)
        .checked_mul(values.f_frsize as u64)
        .ok_or("Smol storage capacity overflow".into())
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
    validate_home_socket_path(&s.home)?;
    if config.operating_system != "linux"
        || config.architecture != "amd64"
        || s.maximum_parallel == 0
        || s.maximum_parallel > 64
        || s.maximum_storage_bytes < 1024 * 1024 * 1024
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
    image_configuration(image).map(|_| ())
}
fn image_configuration(image: &CacheEntry) -> Result<Value, String> {
    let source = image.smol.as_ref().ok_or("Smol image missing")?;
    if !source.image_config.is_absolute() || !valid_digest(&image.config_image_id) {
        return Err("image configuration identity invalid".into());
    }
    let mut file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK)
        .open(&source.image_config)
        .map_err(|_| "image configuration unavailable")?;
    let metadata = file
        .metadata()
        .map_err(|_| "image configuration unavailable")?;
    if !metadata.is_file()
        || metadata.mode() & 0o022 != 0
        || metadata.len() > MAX_REQUEST_BYTES as u64
    {
        return Err("image configuration custody invalid".into());
    }
    let mut bytes = Vec::new();
    Read::by_ref(&mut file)
        .take(MAX_REQUEST_BYTES as u64 + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| "image configuration unavailable")?;
    if bytes.len() > MAX_REQUEST_BYTES
        || format!("sha256:{:x}", Sha256::digest(&bytes)) != image.config_image_id
    {
        return Err("image configuration identity differs".into());
    }
    let value: Value = serde_json::from_slice(&bytes).map_err(|_| "image configuration invalid")?;
    if value["os"].as_str() != Some(&image.operating_system)
        || value["architecture"].as_str() != Some(&image.architecture)
    {
        return Err("image platform differs".into());
    }
    image_command(&value)?;
    Ok(value)
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
    if let Some(admission) = &config.smol_admission {
        admission.reserved_storage_bytes()?;
    }
    let s = settings(config)?;
    memory_capacity(s)?;
    if s.maximum_storage_bytes < 1024 * 1024 * 1024 {
        return Err("node storage must be bounded".into());
    }
    available_storage(s)?;
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
        .env("SMOLVM_IMAGE_SEEDS", "0")
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
    fn private_home_path(&self) -> PathBuf {
        self.private_home_root
            .as_ref()
            .unwrap_or(&self.root)
            .join(format!("{}.home", self.name))
    }
    fn disk_path(&self) -> PathBuf {
        // Inspect only this exact Smol 1.31.4 lease disk; never sweep its cache root.
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
            && self.private_home_root.as_ref().is_none_or(|root| {
                root.is_absolute()
                    && root != &self.root
                    && self.runtime.home == self.private_home_path()
            })
            && self
                .pre
                .as_ref()
                .is_none_or(|invocation| self.private_home_root.is_none() && invocation.valid())
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
    fn verify_network_disabled(&self, deadline: Instant) -> Result<(), String> {
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
            .filter(|row| row["name"].as_str() == Some(&self.name))
            .collect();
        if matches.len() != 1
            || matches[0]["labels"]["workstream.external-checker-owner"].as_str()
                != Some(&self.owner)
            || matches[0]["network"].as_bool() != Some(false)
        {
            return Err("runtime network isolation differs".into());
        }
        Ok(())
    }
    fn cleanup(&self) -> Result<(), String> {
        if !self.valid() {
            return Err("lease ownership invalid".into());
        }
        let deadline = Instant::now() + CLEANUP_TIMEOUT;
        let group = self.cgroup();
        let private_home_exists = if let Some(home_root) = &self.private_home_root {
            private_directory(home_root).map_err(|_| "private Smol root custody unsettled")?;
            let home = self.private_home_path();
            match fs::symlink_metadata(&home) {
                Ok(_) => {
                    private_directory(&home).map_err(|_| "private Smol home custody unsettled")?;
                    true
                }
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => false,
                Err(_) => return Err("private Smol home custody unsettled".into()),
            }
        } else {
            true
        };
        if self.private_home_root.is_some() && !private_home_exists && group.exists() {
            return Err("private Smol home cleanup order unsettled".into());
        }
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
        if private_home_exists && self.inventory(deadline)? {
            checked(
                &self.runtime,
                &["machine", "delete", "--name", &self.name, "--force"],
                None,
                deadline,
                None,
            )?;
        }
        if private_home_exists && self.inventory(deadline)? {
            return Err("VM cleanup unsettled".into());
        }
        if private_home_exists {
            match fs::symlink_metadata(self.disk_path()) {
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
                _ => return Err("VM disk cleanup unsettled".into()),
            }
        }
        if group.exists() {
            fs::remove_dir(&group).map_err(|_| "cgroup removal unsettled")?;
        }
        if self.private_home_root.is_some() {
            let home = self.private_home_path();
            if private_home_exists {
                fs::remove_dir_all(&home).map_err(|_| "private Smol home cleanup unsettled")?;
                if home.exists() {
                    return Err("private Smol home cleanup unsettled".into());
                }
            }
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
    ) -> Result<Self, ExecutionFailure> {
        Self::create_inner(config, resources, deadline, None, None)
    }

    pub(super) fn create_child(
        config: &ServiceConfig,
        resources: Resources,
        deadline: Instant,
        child_home_root: &Path,
    ) -> Result<Self, ExecutionFailure> {
        if config
            .trial_runtime
            .as_ref()
            .map(|runtime| runtime.child_home_root.as_path())
            != Some(child_home_root)
            || private_directory(child_home_root).is_err()
        {
            return Err(ExecutionFailure::ordinary(
                "implementation_unavailable",
                false,
            ));
        }
        Self::create_inner(
            config,
            resources,
            deadline,
            Some(child_home_root.to_owned()),
            None,
        )
    }

    fn create_inner(
        config: &ServiceConfig,
        resources: Resources,
        deadline: Instant,
        private_home_root: Option<PathBuf>,
        pre: Option<pre::Invocation>,
    ) -> Result<Self, ExecutionFailure> {
        if pre.as_ref().is_some_and(|invocation| !invocation.valid())
            || (pre.is_some() && private_home_root.is_some())
        {
            return Err(ExecutionFailure::ordinary(
                "implementation_unavailable",
                false,
            ));
        }
        let mut s = settings(config)
            .map_err(|_| ExecutionFailure::ordinary("implementation_unavailable", false))?
            .clone();
        let root = config
            .socket_path
            .parent()
            .ok_or("socket parent missing")
            .map_err(|_| ExecutionFailure::ordinary("implementation_unavailable", false))?
            .join("smol-leases");
        let mut random = [0u8; 16];
        File::open("/dev/urandom")
            .and_then(|mut f| f.read_exact(&mut random))
            .map_err(|_| ExecutionFailure::ordinary("implementation_unavailable", false))?;
        let nonce: String = random.iter().map(|b| format!("{b:02x}")).collect();
        let owner = container_owner(config)
            .map_err(|_| ExecutionFailure::ordinary("implementation_unavailable", false))?
            .to_owned();
        let name = format!("ws-{nonce}");
        if let Some(home_root) = &private_home_root {
            use std::os::unix::fs::DirBuilderExt;
            let home = home_root.join(format!("{name}.home"));
            fs::DirBuilder::new()
                .mode(0o700)
                .create(&home)
                .map_err(|_| ExecutionFailure::ordinary("implementation_unavailable", false))?;
            if private_directory(&home).is_err() {
                return Err(if fs::remove_dir(&home).is_ok() {
                    ExecutionFailure::ordinary("implementation_unavailable", false)
                } else {
                    ExecutionFailure::unsettled(false)
                });
            }
            s.home = home;
        }
        let lease = Lease {
            name,
            owner,
            epoch: config
                .smol_admission
                .as_ref()
                .ok_or_else(|| ExecutionFailure::ordinary("implementation_unavailable", false))?
                .epoch
                .clone(),
            expires_ms: now_ms()
                .map_err(|_| ExecutionFailure::ordinary("implementation_unavailable", false))?
                .saturating_add(
                    deadline
                        .saturating_duration_since(Instant::now())
                        .as_millis() as u64,
                ),
            lifetime_ms: deadline
                .saturating_duration_since(Instant::now())
                .as_millis() as u64,
            root,
            runtime: s,
            private_home_root,
            pre,
        };
        let bytes = match serde_json::to_vec(&lease) {
            Ok(bytes) => bytes,
            Err(_) => {
                let home_clean = lease.private_home_root.is_none()
                    || fs::remove_dir(&lease.runtime.home).is_ok();
                return Err(if home_clean {
                    ExecutionFailure::ordinary("implementation_unavailable", false)
                } else {
                    ExecutionFailure::unsettled(false)
                });
            }
        };
        let mut file = match OpenOptions::new()
            .create_new(true)
            .write(true)
            .mode(0o600)
            .open(lease.path())
        {
            Ok(file) => file,
            Err(error) => {
                let home_clean = lease.private_home_root.is_none()
                    || fs::remove_dir(&lease.runtime.home).is_ok();
                if error.kind() == std::io::ErrorKind::AlreadyExists {
                    return Err(ExecutionFailure::unsettled(false));
                } else if home_clean {
                    return Err(ExecutionFailure::ordinary(
                        "implementation_unavailable",
                        false,
                    ));
                } else {
                    return Err(ExecutionFailure::unsettled(false));
                }
            }
        };
        file.write_all(&bytes)
            .and_then(|_| file.sync_all())
            .map_err(|_| ExecutionFailure::unsettled(false))?;
        File::open(&lease.root)
            .and_then(|f| f.sync_all())
            .map_err(|_| ExecutionFailure::unsettled(false))?;
        let journal =
            pre::Journal::capture(&file, &bytes).map_err(|_| ExecutionFailure::unsettled(false))?;
        // Persist ownership before any runtime resource is created. The guardian
        // is a distinct exec with its own lifetime and only this lease's custody.
        let mut guardian =
            Command::new(std::env::current_exe().map_err(|_| ExecutionFailure::unsettled(false))?)
                .arg("--smol-guardian")
                .arg(lease.path())
                .env_clear()
                .stdin(Stdio::piped())
                .stdout(Stdio::piped())
                .stderr(Stdio::null())
                .spawn()
                .map_err(|_| ExecutionFailure::unsettled(false))?;
        let keeper = guardian.stdin.take();
        let mut handshake = guardian
            .stdout
            .take()
            .ok_or_else(|| ExecutionFailure::unsettled(false))?;
        set_nonblocking(&handshake).map_err(|_| ExecutionFailure::unsettled(false))?;
        let mut bytes = Vec::new();
        let handshake_deadline = deadline.min(Instant::now() + SOCKET_IO_TIMEOUT);
        loop {
            read_available(&mut handshake, &mut bytes, 1)
                .map_err(|_| ExecutionFailure::unsettled(false))?;
            if bytes == [1] {
                break;
            }
            if Instant::now() >= handshake_deadline {
                drop(keeper);
                return Err(ExecutionFailure::unsettled(false));
            }
            thread::sleep(Duration::from_millis(5));
        }
        let mut machine = Self {
            lease,
            journal,
            guardian,
            keeper,
            consumed: false,
        };
        if machine.configure_cgroup(resources).is_err() {
            return Err(if machine.close().is_ok() {
                ExecutionFailure::ordinary("implementation_unavailable", false)
            } else {
                ExecutionFailure::unsettled(false)
            });
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
            ("pids.max", resources.host_pids().to_string()),
        ] {
            fs::write(group.join(file), value).map_err(|_| "cgroup enforcement failed")?;
        }
        Ok(())
    }
    fn prepare(
        &self,
        cache: &CacheEntry,
        resources: Resources,
        overlay_gib: Option<u64>,
        client: &UnixStream,
        deadline: Instant,
    ) -> Result<(), String> {
        let lease = &self.lease;
        let s = &lease.runtime;
        let group = lease.cgroup();
        let image = cache.smol.as_ref().ok_or("Smol image missing")?;
        let archive = image.archive.to_str().ok_or("image path invalid")?;
        let label = format!("workstream.external-checker-owner={}", lease.owner);
        let cpus = resources.cpu_millis.div_ceil(1000).to_string();
        let memory =
            (resources.memory_bytes.div_ceil(1024 * 1024) + GUEST_OVERHEAD_MIB).to_string();
        let storage = resources.storage_gib.to_string();
        let overlay = overlay_gib.map(|value| value.to_string());
        let mut args = vec![
            "machine",
            "create",
            "--name",
            &lease.name,
            "--image",
            archive,
            "--label",
            &label,
            "--cpus",
            &cpus,
            "--mem",
            &memory,
            "--storage",
            &storage,
        ];
        if let Some(value) = overlay.as_deref() {
            args.extend(["--overlay", value]);
        }
        checked(s, &args, Some(&group), deadline, Some(client))?;
        // Closed argv omits network enablers; verify exact-owner state before start.
        lease.verify_network_disabled(deadline)?;
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
        materials: ProjectMaterials<'_>,
        callbacks: &ProjectCallbacks,
        client: &UnixStream,
        deadline: Instant,
        cancelled: &AtomicBool,
    ) -> Result<ExecutedChecker, String> {
        if self.consumed {
            return Err("execution already consumed".into());
        }
        self.consumed = true;
        let mut sources =
            vec![
                io::material_source("current", materials.current.0, materials.current.1, config)
                    .map_err(|_| "material_unavailable")?,
            ];
        if let Some((root, inventory)) = materials.predecessor {
            sources.push(
                io::material_source("predecessor", root, inventory, config)
                    .map_err(|_| "material_unavailable")?,
            );
        }
        let value = image_configuration(cache)?;
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
            purpose: GuestPurpose::Project {
                capabilities: GuestCapabilities {
                    model: callbacks.model.is_some(),
                    execution: callbacks.execution.is_some(),
                },
                materials: sources
                    .iter()
                    .map(|source| source.manifest.clone())
                    .collect(),
            },
            request: request.value.clone(),
            command: image_command(&value)?,
            environment,
            working_directory: value["config"]["WorkingDir"]
                .as_str()
                .unwrap_or("/")
                .to_owned(),
            uid: config.sandbox_uid,
            gid: config.sandbox_gid,
            directories: Vec::new(),
            files: Vec::new(),
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
        let child = cmd.spawn().map_err(|_| "guest launch failed")?;
        let output = io::run_project(
            child,
            &job,
            &sources,
            callbacks,
            deadline,
            request.maximum_output_bytes,
            client,
            cancelled,
        )?;
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
        // EOF transfers cleanup to the guardian; wait for durable absence.
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
    materials: ProjectMaterials<'_>,
    callbacks: &ProjectCallbacks,
    client: &UnixStream,
    budget: &mut RequestExecutionBudget,
    cancelled: &AtomicBool,
) -> Result<ExecutedChecker, ExecutionFailure> {
    io::validate_endpoints(callbacks)
        .map_err(|_| ExecutionFailure::ordinary("implementation_unavailable", false))?;
    for attempt in 0..3 {
        let mut machine = Machine::create(config, request.into(), budget.deadline)?;
        let prepared = machine.prepare(cache, request.into(), None, client, budget.deadline);
        let launched = prepared.is_ok();
        let result = prepared.and_then(|_| {
            machine.run(
                cache,
                config,
                request,
                ProjectMaterials {
                    current: materials.current,
                    predecessor: materials.predecessor,
                },
                callbacks,
                client,
                budget.deadline,
                cancelled,
            )
        });
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
                    "material_unavailable" => "material_unavailable",
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
    let mut leases = Vec::new();
    let inspection_deadline = Instant::now() + CLEANUP_TIMEOUT;
    for entry in fs::read_dir(&root).map_err(|_| "lease inventory unavailable")? {
        if leases.len() >= 1_000_000 || Instant::now() >= inspection_deadline {
            return Err("lease inventory bound exceeded".into());
        }
        let entry = entry.map_err(|_| "lease inventory unavailable")?;
        let mut file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK)
            .open(entry.path())
            .map_err(|_| "lease unavailable")?;
        let metadata = file.metadata().map_err(|_| "lease unavailable")?;
        if !metadata.is_file()
            || metadata.nlink() != 1
            || metadata.uid() != unsafe { libc::geteuid() }
            || metadata.gid() != unsafe { libc::getegid() }
            || metadata.mode() & 0o7777 != 0o600
            || metadata.len() > MAX_ENVELOPE_BYTES as u64
        {
            return Err("lease custody differs".into());
        }
        let mut bytes = Vec::new();
        Read::by_ref(&mut file)
            .take(MAX_ENVELOPE_BYTES as u64 + 1)
            .read_to_end(&mut bytes)
            .map_err(|_| "lease unavailable")?;
        if bytes.len() > MAX_ENVELOPE_BYTES {
            return Err("lease inventory unbounded".into());
        }
        let lease: Lease = serde_json::from_slice(&bytes).map_err(|_| "lease inventory invalid")?;
        let runtime_home_matches = match &lease.private_home_root {
            Some(root) => {
                config
                    .trial_runtime
                    .as_ref()
                    .map(|runtime| runtime.child_home_root.as_path())
                    == Some(root.as_path())
                    && lease.runtime.home == lease.private_home_path()
            }
            None => lease.runtime.home == settings(config)?.home,
        };
        if lease.owner != container_owner(config)?
            || lease.root != root
            || !runtime_home_matches
            || lease.runtime.cgroup_root != settings(config)?.cgroup_root
            || !lease.valid()
            || entry.path() != lease.path()
        {
            return Err("lease ownership differs".into());
        }
        leases.push((lease, file, metadata));
    }
    // A foreign or malformed lease must refuse startup before deleting an
    // earlier valid lease's VM. Cleanup is restricted to this complete inventory.
    for (lease, file, metadata) in leases {
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
            let current =
                fs::symlink_metadata(lease.path()).map_err(|_| "lease identity unavailable")?;
            if (current.dev(), current.ino(), current.mode())
                != (metadata.dev(), metadata.ino(), metadata.mode())
            {
                return Err("lease identity changed".into());
            }
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
    config.smol_admission = Some(Arc::new(Admission::new(
        Capacity {
            slots: maximum,
            memory_bytes: memory_capacity(settings(&config)?)? as u64,
            storage_bytes: settings(&config)?.maximum_storage_bytes,
        },
        random_token()?,
    )?));
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
mod tests;
