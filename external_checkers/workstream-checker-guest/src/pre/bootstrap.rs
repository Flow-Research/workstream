//! One PRE guest: bounded input, pinned platform worker, then optional project.
use super::*;
use std::ffi::OsString;
use std::io::{Seek, SeekFrom};
use workstream_checker_guest::pre_bootstrap::{
    PreBootstrapJob, PreBootstrapLimits, PrePartition, PRE_LIMITS_MAXIMUM_BYTES,
};
use workstream_checker_guest::trusted_root::stage_root;

const CONTROL: &str = "/sys/fs/cgroup/workstream-pre-control";
const WORKER: &str = "/sys/fs/cgroup/workstream-pre-default";

fn parse_limits(mut arguments: impl Iterator<Item = OsString>) -> Result<PreBootstrapLimits> {
    let value = arguments.next().ok_or("PRE bootstrap limits missing")?;
    if value.len() > PRE_LIMITS_MAXIMUM_BYTES || arguments.next().is_some() {
        return Err("PRE bootstrap limits unbounded".into());
    }
    let limits: PreBootstrapLimits =
        serde_json::from_str(value.to_str().ok_or("PRE limits encoding invalid")?)?;
    limits.validate()?;
    Ok(limits)
}

fn configure_group(path: &str, partition: PrePartition) -> Result<()> {
    fs::create_dir(path)?;
    let group = Path::new(path);
    fs::write(
        group.join("cpu.max"),
        format!(
            "{} 100000",
            partition
                .cpu_millis
                .checked_mul(100)
                .ok_or("PRE CPU overflow")?
        ),
    )?;
    fs::write(group.join("memory.max"), partition.memory_bytes.to_string())?;
    disable_swap(group, Path::new("/proc/meminfo"))?;
    fs::write(group.join("memory.oom.group"), "1")?;
    fs::write(group.join("pids.max"), partition.processes.to_string())?;
    Ok(())
}

struct Envelope {
    limits: PreBootstrapLimits,
    deadline: Instant,
    cleanup: Instant,
}
impl Envelope {
    fn prepare(limits: PreBootstrapLimits) -> Result<Self> {
        limits.validate()?;
        let started = Instant::now();
        let result = Self {
            limits,
            deadline: started
                .checked_add(Duration::from_millis(limits.timeout_ms))
                .ok_or("PRE deadline overflow")?,
            cleanup: started
                .checked_add(Duration::from_millis(limits.cleanup_timeout_ms))
                .ok_or("PRE cleanup overflow")?,
        };
        fs::write(
            "/sys/fs/cgroup/cgroup.subtree_control",
            "+cpu +memory +pids",
        )?;
        configure_group(CONTROL, limits.control)?;
        configure_group(WORKER, limits.worker)?;
        // Before allocating the job or input-dependent buffers, charge this
        // supervisor to its own partition, never either workload's OOM group.
        fs::write(Path::new(CONTROL).join("cgroup.procs"), "0")?;
        result.check()?;
        Ok(result)
    }
    fn check(&self) -> Result<()> {
        if Instant::now() >= self.deadline {
            return Err("PRE deadline exceeded".into());
        }
        Ok(())
    }
    fn cleanup_check(&self) -> Result<()> {
        if Instant::now() >= self.cleanup {
            return Err("PRE cleanup deadline exceeded".into());
        }
        Ok(())
    }
    fn project_limits(&self) -> ProjectLimits {
        ProjectLimits {
            cpu_millis: self.limits.project.cpu_millis,
            memory_bytes: self.limits.project.memory_bytes,
            maximum_processes: self.limits.project.processes,
            scratch_bytes: self.limits.project_scratch_bytes,
            maximum_output_bytes: self.limits.maximum_output_bytes,
            maximum_log_bytes: self.limits.maximum_log_bytes,
            deadline: Some(self.deadline),
            cleanup_deadline: Some(self.cleanup),
        }
    }
}

fn text<'a>(value: &'a Value, field: &str) -> Result<&'a str> {
    value[field]
        .as_str()
        .ok_or_else(|| "PRE bootstrap text missing".into())
}
fn number(value: &Value, field: &str) -> Result<u64> {
    value[field]
        .as_u64()
        .ok_or_else(|| "PRE bootstrap number missing".into())
}
fn sum(values: impl IntoIterator<Item = u64>) -> Result<u64> {
    values.into_iter().try_fold(0u64, |total, value| {
        total
            .checked_add(value)
            .ok_or_else(|| "PRE resource overflow".into())
    })
}
fn binding(job: &PreBootstrapJob) -> Result<ProjectBinding<'_>> {
    let header = &job.startup["request"];
    let reservation = &header["reservation"];
    let source = &reservation["source"];
    let profile = &reservation["runtime_profile"];
    let mut source_body = source.as_object().ok_or("PRE source invalid")?.clone();
    source_body.insert(
        "schema_version".into(),
        json!("workstream.sealed_submission_source.v1"),
    );
    let entries = reservation["policy"]["entries"]
        .as_array()
        .ok_or("PRE policy missing")?;
    if entries.len() != 1 {
        return Err("PRE cardinality invalid".into());
    }
    let selected = &entries[0];
    let registry = &selected["registry"];
    if job.startup["operation"] != "execute_pre"
        || header["operation"] != "execute_pre"
        || header["protocol_version"] != "external_checker_service.v1"
        || canonical_hash(reservation)? != text(header, "request_digest")?
        || canonical_hash(&Value::Object(source_body))? != text(reservation, "source_sha256")?
        || profile["platform_root_sha256"] != job.root.bundle_sha256
        || reservation["policy"]["workstream_default"]["behavior_sha256"]
            != job.root.default_behavior_sha256
        || number(source, "raw_byte_count")? == 0
        || number(source, "raw_byte_count")? > job.limits.maximum_source_bytes
        || job.root.bundle_byte_count == 0
        || job.root.bundle_byte_count > job.root_limits.maximum_bundle_bytes
        || job.root.expanded_bytes > job.root_limits.maximum_root_bytes
        || job.root.entries == 0
        || job.root.entries > job.root_limits.maximum_entries
        || number(header, "lease_generation")? == 0
        || job.selected.uid == 0
        || job.selected.gid == 0
        || job.selected.uid == job.limits.worker_uid
        || job.selected.gid == job.limits.worker_gid
        || !job.selected.request.is_null()
        || !job.selected.files.is_empty()
        || !job.selected.directories.is_empty()
        || !matches!(&job.selected.purpose, GuestPurpose::Project { capabilities, materials }
            if !capabilities.model && !capabilities.execution && materials.is_empty())
        || job.selected.command.is_empty()
        || job.selected.command.len() > 256
        || job.selected.environment.len() > 1024
    {
        return Err("PRE bootstrap identity differs".into());
    }
    for (field, amounts) in [
        (
            "cpu_millis",
            [
                job.limits.control.cpu_millis,
                job.limits.worker.cpu_millis,
                job.limits.project.cpu_millis,
            ],
        ),
        (
            "memory_bytes",
            [
                job.limits.control.memory_bytes,
                job.limits.worker.memory_bytes,
                job.limits.project.memory_bytes,
            ],
        ),
        (
            "maximum_processes",
            [
                job.limits.control.processes,
                job.limits.worker.processes,
                job.limits.project.processes,
            ],
        ),
    ] {
        if sum(amounts)? > number(profile, field)? {
            return Err("PRE partitions exceed profile".into());
        }
    }
    let archive_limits = &profile["archive_limits"];
    if sum([
        job.root.bundle_byte_count,
        job.root.expanded_bytes,
        number(source, "raw_byte_count")?,
        number(archive_limits, "maximum_expanded_bytes")?,
        job.limits.worker_scratch_bytes,
        job.limits.project_scratch_bytes,
        job.limits.overlay_bytes,
        job.limits.filesystem_overhead_bytes,
    ])? > number(profile, "temporary_disk_bytes")?
        || job.limits.maximum_output_bytes as u64 > number(profile, "maximum_output_bytes")?
        || job.limits.maximum_log_bytes as u64 > number(profile, "maximum_log_bytes")?
        || job.limits.cleanup_timeout_ms > number(profile, "aggregate_deadline_ms")?
    {
        return Err("PRE envelope exceeds locked profile".into());
    }
    Ok(ProjectBinding {
        project_id: text(reservation, "project_id")?,
        task_id: text(reservation, "task_id")?,
        assignment_id: text(reservation, "assignment_id")?,
        attempt_id: text(reservation, "attempt_id")?,
        effective_plan_sha256: text(&reservation["admission_lineage"], "effective_plan_sha256")?,
        requirement_id: text(selected, "requirement_id")?,
        request_digest: text(header, "request_digest")?,
        lease_id: text(header, "lease_id")?,
        lease_generation: number(header, "lease_generation")?,
        operation_id: text(&source["location"], "operation_id")?,
        source_sha256: text(reservation, "source_sha256")?,
        archive_sha256: text(source, "raw_sha256")?,
        archive_byte_count: number(source, "raw_byte_count")?,
        image_digest: text(registry, "image_digest")?,
        configuration_digest: text(selected, "configuration_sha256")?,
        registry_entry_digest: text(registry, "entry_digest")?,
        maximum_control_bytes: job.limits.maximum_control_bytes,
        maximum_entries: usize::try_from(number(archive_limits, "maximum_entries")?)?,
        maximum_expanded_bytes: number(archive_limits, "maximum_expanded_bytes")?,
    })
}

fn spool(
    input: &mut File,
    target: &Path,
    count: u64,
    maximum: u64,
    envelope: &Envelope,
) -> Result<File> {
    if count == 0 || count > maximum {
        return Err("PRE spool bound invalid".into());
    }
    let mut file = OpenOptions::new()
        .read(true)
        .write(true)
        .create_new(true)
        .mode(0o600)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(target)?;
    let mut remaining = count;
    let mut buffer = [0; 65536];
    while remaining > 0 {
        envelope.check()?;
        let size = remaining.min(buffer.len() as u64) as usize;
        read_staged_bytes(input, &mut buffer[..size], &|| envelope.check())?;
        file.write_all(&buffer[..size])?;
        remaining -= size as u64;
    }
    envelope.check()?;
    file.seek(SeekFrom::Start(0))?;
    Ok(file)
}

fn transfer_root_owner(path: &Path, uid: u32, gid: u32, envelope: &Envelope) -> Result<()> {
    envelope.check()?;
    let metadata = fs::symlink_metadata(path)?;
    if metadata.is_dir() {
        for entry in fs::read_dir(path)? {
            transfer_root_owner(&entry?.path(), uid, gid, envelope)?;
        }
    }
    // Only the verified, supervisor-private tree exists here. lchown never
    // follows the platform root's pinned symlink targets into the host root.
    syscall_ok(unsafe {
        libc::lchown(
            c(path.to_str().ok_or("PRE root path invalid")?)?.as_ptr(),
            uid,
            gid,
        )
    })
}

struct Worker {
    active: bool,
    pid: Option<libc::pid_t>,
    control: UnixStream,
    stderr: UnixStream,
    log_bytes: usize,
    cleanup: Instant,
}
impl Worker {
    fn check_logs(&mut self, maximum: usize, deadline: Instant) -> Result<()> {
        let mut buffer = [0u8; 8192];
        loop {
            if Instant::now() >= deadline {
                return Err("PRE log deadline exceeded".into());
            }
            match self.stderr.read(&mut buffer) {
                Ok(0) => return Ok(()),
                Ok(count) => {
                    self.log_bytes = self
                        .log_bytes
                        .checked_add(count)
                        .ok_or("PRE log overflow")?;
                    if self.log_bytes > maximum {
                        return Err("PRE worker logs exceeded".into());
                    }
                }
                Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => return Ok(()),
                Err(error) if error.kind() == std::io::ErrorKind::Interrupted => continue,
                Err(error) => return Err(error.into()),
            }
        }
    }
    fn read_exact(&mut self, mut bytes: &mut [u8], envelope: &Envelope) -> Result<()> {
        while !bytes.is_empty() {
            envelope.check()?;
            self.check_logs(envelope.limits.maximum_log_bytes, envelope.deadline)?;
            let maximum = bytes.len().min(65536);
            match self.control.read(&mut bytes[..maximum]) {
                Ok(0) => return Err("PRE worker frame truncated".into()),
                Ok(count) => bytes = &mut bytes[count..],
                Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                    thread::sleep(Duration::from_millis(2))
                }
                Err(error) if error.kind() == std::io::ErrorKind::Interrupted => (),
                Err(error) => return Err(error.into()),
            }
        }
        envelope.check()
    }
    fn read_frame(&mut self, envelope: &Envelope) -> Result<Vec<u8>> {
        let mut length = [0; 4];
        self.read_exact(&mut length, envelope)?;
        let length = u32::from_be_bytes(length) as usize;
        if length == 0 || length > envelope.limits.maximum_control_bytes {
            return Err("PRE worker frame unbounded".into());
        }
        let mut bytes = vec![0; length];
        self.read_exact(&mut bytes, envelope)?;
        Ok(bytes)
    }
    fn reply(&mut self, result: &Value, envelope: &Envelope) -> Result<()> {
        let bytes = serde_json::to_vec(result)?;
        if bytes.is_empty() || bytes.len() > envelope.limits.maximum_control_bytes {
            return Err("PRE worker reply unbounded".into());
        }
        for mut remaining in [&(bytes.len() as u32).to_be_bytes()[..], &bytes[..]] {
            while !remaining.is_empty() {
                envelope.check()?;
                self.check_logs(envelope.limits.maximum_log_bytes, envelope.deadline)?;
                match self.control.write(&remaining[..remaining.len().min(65536)]) {
                    Ok(0) => return Err("PRE worker pipe closed".into()),
                    Ok(count) => remaining = &remaining[count..],
                    Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                        thread::sleep(Duration::from_millis(2))
                    }
                    Err(error) if error.kind() == std::io::ErrorKind::Interrupted => (),
                    Err(error) => return Err(error.into()),
                }
            }
        }
        envelope.check()
    }
    fn finish(&mut self, envelope: &Envelope) -> Result<()> {
        let child = self.pid.ok_or("PRE worker already reaped")?;
        let mut status = 0;
        loop {
            envelope.cleanup_check()?;
            self.check_logs(envelope.limits.maximum_log_bytes, envelope.cleanup)?;
            let waited = unsafe { libc::waitpid(child, &mut status, libc::WNOHANG) };
            if waited == child {
                self.pid = None;
                break;
            }
            if waited < 0
                && std::io::Error::last_os_error().kind() != std::io::ErrorKind::Interrupted
            {
                return Err(std::io::Error::last_os_error().into());
            }
            thread::sleep(Duration::from_millis(2));
        }
        fs::write(Path::new(WORKER).join("cgroup.kill"), "1")?;
        loop {
            envelope.cleanup_check()?;
            if fs::read_to_string(Path::new(WORKER).join("cgroup.events"))?
                .lines()
                .any(|line| line == "populated 0")
            {
                break;
            }
            thread::sleep(Duration::from_millis(2));
        }
        self.check_logs(envelope.limits.maximum_log_bytes, envelope.cleanup)?;
        let mut trailing = [0];
        if self.control.read(&mut trailing)? != 0 {
            return Err("PRE worker trailing frame".into());
        }
        let memory = fs::read_to_string(Path::new(WORKER).join("memory.events"))?;
        if !memory.lines().any(|line| line == "oom_kill 0") {
            return Err("PRE worker memory limit exceeded".into());
        }
        if !libc::WIFEXITED(status) || libc::WEXITSTATUS(status) != 0 {
            return Err("PRE worker failed".into());
        }
        self.active = false;
        envelope.check()
    }
}
impl Drop for Worker {
    fn drop(&mut self) {
        if !self.active {
            return;
        }
        if let Some(child) = self.pid.take() {
            let _ = stop_project(child, Path::new(WORKER), self.cleanup);
        } else {
            let _ = fs::write(Path::new(WORKER).join("cgroup.kill"), "1");
        }
    }
}

fn spawn_worker(root: &Path, view: &Path, envelope: &Envelope) -> Result<Worker> {
    let (parent, child) = socket_pair()?;
    let (stderr, child_stderr) = socket_pair()?;
    envelope.check()?;
    let pid = unsafe { libc::fork() };
    if pid < 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    if pid == 0 {
        // No background threads exist at this fork. A child setup failure must
        // exit here, never unwind into the supervisor's cleanup/response code.
        exec_workload(|| -> Result<()> {
            drop(parent);
            drop(stderr);
            private_mounts()?;
            fs::write(Path::new(WORKER).join("cgroup.procs"), "0")?;
            mount(
                root.to_str().ok_or("PRE root invalid")?,
                root.to_str().ok_or("PRE root invalid")?,
                "",
                libc::MS_BIND,
                "",
            )?;
            mount(
                view.to_str().ok_or("PRE worker view invalid")?,
                root.join("work")
                    .to_str()
                    .ok_or("PRE worker mount invalid")?,
                "",
                libc::MS_BIND | libc::MS_REC,
                "",
            )?;
            syscall_ok(unsafe {
                libc::chroot(c(root.to_str().ok_or("PRE root invalid")?)?.as_ptr())
            })?;
            std::env::set_current_dir("/")?;
            confined_devices()?;
            readonly_filesystem(envelope.limits.worker_scratch_bytes)?;
            // The canonical ZIP projector alone writes this bounded tree. Root
            // and source stay read-only; project code never enters this root.
            mount(
                "",
                "/work/scratch",
                "",
                libc::MS_BIND
                    | libc::MS_REMOUNT
                    | libc::MS_NOSUID
                    | libc::MS_NODEV
                    | libc::MS_NOEXEC,
                "",
            )?;
            drop_privileges(envelope.limits.worker_uid, envelope.limits.worker_gid)?;
            syscall_ok(unsafe { libc::dup2(child.as_raw_fd(), 0) }.min(0))?;
            syscall_ok(unsafe { libc::dup2(child.as_raw_fd(), 1) }.min(0))?;
            syscall_ok(unsafe { libc::dup2(child_stderr.as_raw_fd(), 2) }.min(0))?;
            seal_exec_descriptors()?;
            install_workload_filter()?;
            envelope.check()?;
            let error = Command::new("/opt/venv/bin/python")
                .args(["-I", "/opt/workstream/intake.py"])
                .env_clear()
                .current_dir("/opt/workstream/backend")
                .exec();
            Err(error.into())
        });
    }
    drop(child);
    drop(child_stderr);
    let worker = Worker {
        active: true,
        pid: Some(pid),
        control: parent,
        stderr,
        log_bytes: 0,
        cleanup: envelope.cleanup,
    };
    worker.control.set_nonblocking(true)?;
    worker.stderr.set_nonblocking(true)?;
    Ok(worker)
}

fn terminal(
    worker: &mut Worker,
    envelope: &Envelope,
    bound: &ProjectBinding<'_>,
    project: impl FnOnce(&[u8]) -> Result<Value>,
) -> Result<Vec<u8>> {
    let first = worker.read_frame(envelope)?;
    let frame: WorkerFrame<Value> = serde_json::from_slice(&first)?;
    if frame.protocol_version != "workstream.pre_submit_worker.v1"
        || frame.request_digest != bound.request_digest
        || frame.lease_id != bound.lease_id
        || frame.lease_generation != bound.lease_generation
    {
        return Err("PRE initial worker binding differs".into());
    }
    let ran_project = frame.operation == "project";
    let terminal = if ran_project {
        let response = project(&first)?;
        worker.reply(&response, envelope)?;
        worker.read_frame(envelope)?
    } else {
        first
    };
    let result: WorkerFrame<Value> = serde_json::from_slice(&terminal)?;
    if result.protocol_version != "workstream.pre_submit_worker.v1"
        || result.operation != "completed"
        || result.request_digest != bound.request_digest
        || result.lease_id != bound.lease_id
        || result.lease_generation != bound.lease_generation
        || (!ran_project && result.payload["workstream_default"]["eligible"] != false)
    {
        return Err("PRE terminal worker binding differs".into());
    }
    Ok(terminal)
}

pub(crate) fn run(arguments: impl Iterator<Item = OsString>) -> Result<()> {
    let limits = parse_limits(arguments)?;
    let envelope = Envelope::prepare(limits)?;
    let descriptor = unsafe { libc::dup(0) };
    if descriptor < 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    let mut input = unsafe { File::from_raw_fd(descriptor) };
    trial::set_nonblocking(&input)?;
    let mut length = [0; 4];
    read_staged_bytes(&mut input, &mut length, &|| envelope.check())?;
    let length = u32::from_be_bytes(length) as usize;
    if length == 0 || length > MAX_JOB_BYTES {
        return Err("PRE job unbounded".into());
    }
    let mut bytes = vec![0; length];
    read_staged_bytes(&mut input, &mut bytes, &|| envelope.check())?;
    let job: PreBootstrapJob = serde_json::from_slice(&bytes)?;
    drop(bytes);
    if job.limits != limits {
        return Err("PRE early envelope differs".into());
    }
    let bound = binding(&job)?;
    envelope.check()?;
    private_mounts()?;
    mount_directory(Path::new("/work"))?;
    let mut entropy = [0; 16];
    File::open("/dev/urandom")?.read_exact(&mut entropy)?;
    let suffix: String = entropy.iter().map(|byte| format!("{byte:02x}")).collect();
    let private = PathBuf::from(format!("/.workstream-pre-{suffix}"));
    fs::create_dir(&private)?;
    fs::set_permissions(&private, fs::Permissions::from_mode(0o700))?;
    let mut bundle = spool(
        &mut input,
        &private.join("root.bundle"),
        job.root.bundle_byte_count,
        job.root_limits.maximum_bundle_bytes,
        &envelope,
    )?;
    let root = private.join("root");
    stage_root(&mut bundle, &root, &job.root, &job.root_limits, || {
        envelope.check()
    })?;
    drop(bundle);
    fs::remove_file(private.join("root.bundle"))?;
    let view = private.join("worker-view");
    fs::create_dir(&view)?;
    fs::set_permissions(&view, fs::Permissions::from_mode(0o755))?;
    fs::create_dir(view.join("input"))?;
    let archive_path = view.join("input/archive.zip");
    let archive = spool(
        &mut input,
        &archive_path,
        bound.archive_byte_count,
        limits.maximum_source_bytes,
        &envelope,
    )?;
    own_readonly(&archive, limits.worker_uid, 0o400)?;
    drop(archive);
    // A closed transfer marker prevents extra source frames being interpreted as
    // worker dialogue. The host owns framing and its own exact-source hash.
    let mut end = [0; 4];
    read_staged_bytes(&mut input, &mut end, &|| envelope.check())?;
    if end != [0; 4] {
        return Err("PRE source transfer terminator invalid".into());
    }
    drop(input);
    let workspace = private.join("tree");
    fs::create_dir(&workspace)?;
    let workspace_file = File::open(&workspace)?;
    own_readonly(&workspace_file, limits.worker_uid, 0o700)?;
    fs::create_dir(view.join("scratch"))?;
    mount(
        workspace.to_str().ok_or("PRE workspace invalid")?,
        view.join("scratch").to_str().ok_or("PRE view invalid")?,
        "",
        libc::MS_BIND,
        "",
    )?;
    fs::write(view.join("request.json"), serde_json::to_vec(&job.startup)?)?;
    own_readonly(
        &File::open(view.join("request.json"))?,
        limits.worker_uid,
        0o400,
    )?;
    for name in ["work", "dev", "tmp"] {
        mount_directory(&root.join(name))?;
    }
    transfer_root_owner(&root, limits.worker_uid, limits.worker_gid, &envelope)?;
    // Mask image-owned /work for the later project mount. The private parent
    // containing root/source/control material stays root-owned and mode 0700.
    let project_view = private.join("project-view");
    fs::create_dir(&project_view)?;
    mount(
        project_view.to_str().ok_or("PRE project view invalid")?,
        "/work",
        "",
        libc::MS_BIND,
        "",
    )?;
    let mut worker = spawn_worker(&root, &view, &envelope)?;
    let terminal = terminal(&mut worker, &envelope, &bound, |frame| {
        run_project_phase(
            &bound,
            frame,
            &workspace,
            job.selected.clone(),
            envelope.project_limits(),
        )
    })?;
    worker.finish(&envelope)?;
    envelope.check()?;
    let descriptor = unsafe { libc::dup(1) };
    if descriptor < 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    let mut output = unsafe { File::from_raw_fd(descriptor) };
    trial::set_nonblocking(&output)?;
    for mut remaining in [&(terminal.len() as u32).to_be_bytes()[..], &terminal[..]] {
        while !remaining.is_empty() {
            envelope.check()?;
            match output.write(&remaining[..remaining.len().min(65536)]) {
                Ok(0) => return Err("PRE result pipe closed".into()),
                Ok(count) => remaining = &remaining[count..],
                Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                    thread::sleep(Duration::from_millis(2))
                }
                Err(error) if error.kind() == std::io::ErrorKind::Interrupted => (),
                Err(error) => return Err(error.into()),
            }
        }
    }
    envelope.check()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::fd::OwnedFd;
    use std::sync::atomic::{AtomicU64, Ordering};
    use workstream_checker_guest::trusted_root::{RootDescriptor, RootLimits};
    static NEXT: AtomicU64 = AtomicU64::new(0);

    pub(super) fn limits() -> PreBootstrapLimits {
        // Test-only quantities: no provider qualification or deployment defaults.
        PreBootstrapLimits {
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
        }
    }
    fn envelope() -> Envelope {
        let now = Instant::now();
        Envelope {
            limits: limits(),
            deadline: now + Duration::from_secs(2),
            cleanup: now + Duration::from_secs(3),
        }
    }
    fn job() -> PreBootstrapJob {
        // Python owner canonical serializer, generated from _source_reservation
        // in tests/checkers/external/test_selected_pre_submit_coordination.py.
        let startup: Value =
            serde_json::from_str(include_str!("../../../fixtures/pre_startup.json")).unwrap();
        let reservation = &startup["request"]["reservation"];
        PreBootstrapJob {
            limits: limits(),
            root: RootDescriptor {
                schema_version: "workstream.trusted_root.v1".into(),
                platform_manifest_digest: format!("sha256:{}", "1".repeat(64)),
                config_image_id: format!("sha256:{}", "2".repeat(64)),
                default_behavior_sha256: reservation["policy"]["workstream_default"]
                    ["behavior_sha256"]
                    .as_str()
                    .unwrap()
                    .into(),
                expanded_bytes: 3,
                entries: 1,
                bundle_sha256: reservation["runtime_profile"]["platform_root_sha256"]
                    .as_str()
                    .unwrap()
                    .into(),
                bundle_byte_count: 128,
            },
            root_limits: RootLimits {
                maximum_bundle_bytes: 128,
                maximum_root_bytes: 3,
                maximum_entries: 1,
            },
            selected: GuestJob {
                purpose: GuestPurpose::Project {
                    capabilities: GuestCapabilities {
                        model: false,
                        execution: false,
                    },
                    materials: vec![],
                },
                request: Value::Null,
                command: vec!["/selected-project".into()],
                environment: vec![],
                working_directory: "/".into(),
                uid: 12346,
                gid: 12346,
                directories: vec![],
                files: vec![],
            },
            startup,
        }
    }
    #[test]
    fn early_limits_are_closed_and_reject_unbounded_partitions() {
        let valid = limits();
        parse_limits([OsString::from(serde_json::to_string(&valid).unwrap())].into_iter()).unwrap();
        assert!(parse_limits(std::iter::empty()).is_err());
        assert!(parse_limits([OsString::from("{}"), OsString::from("extra")].into_iter()).is_err());
        let mut extra = serde_json::to_value(valid).unwrap();
        extra["fallback"] = json!(true);
        assert!(parse_limits([OsString::from(extra.to_string())].into_iter()).is_err());
        for invalid in [
            PreBootstrapLimits {
                maximum_source_bytes: 0,
                ..valid
            },
            PreBootstrapLimits {
                worker_uid: 0,
                ..valid
            },
            PreBootstrapLimits {
                control: PrePartition {
                    processes: 2,
                    ..valid.control
                },
                ..valid
            },
            PreBootstrapLimits {
                worker: PrePartition {
                    cpu_millis: u64::MAX,
                    ..valid.worker
                },
                ..valid
            },
            PreBootstrapLimits {
                maximum_control_bytes: 64 * 1024 * 1024 + 1,
                ..valid
            },
            PreBootstrapLimits {
                cleanup_timeout_ms: valid.timeout_ms - 1,
                ..valid
            },
        ] {
            assert!(invalid.validate().is_err());
        }
    }
    #[test]
    fn python_source_request_binds_bootstrap_and_profile_before_input() {
        let valid = job();
        let bound = binding(&valid).unwrap();
        assert_eq!(bound.archive_byte_count, 1024);
        assert_eq!(bound.lease_generation, 1);
        assert_eq!(
            bound.request_digest,
            valid.startup["request"]["request_digest"]
        );
        for case in [
            "request",
            "source",
            "root",
            "source_bound",
            "disk",
            "memory",
            "uid",
            "purpose",
        ] {
            let mut changed = job();
            match case {
                "request" => changed.startup["request"]["request_digest"] = json!("foreign"),
                "source" => {
                    changed.startup["request"]["reservation"]["source"]["provider_generation"] =
                        json!("foreign");
                    changed.startup["request"]["request_digest"] =
                        json!(canonical_hash(&changed.startup["request"]["reservation"]).unwrap());
                }
                "root" => changed.root.bundle_sha256 = format!("sha256:{}", "f".repeat(64)),
                "source_bound" => changed.limits.maximum_source_bytes = 1023,
                "disk" => changed.limits.overlay_bytes = u64::MAX,
                "memory" => changed.limits.worker.memory_bytes = u64::MAX,
                "uid" => changed.selected.uid = changed.limits.worker_uid,
                "purpose" => {
                    changed.selected.purpose = GuestPurpose::TrustedIntake {
                        cpu_millis: 1000,
                        memory_bytes: 1024,
                    }
                }
                _ => unreachable!(),
            }
            assert!(binding(&changed).is_err(), "accepted {case}");
        }
    }

    struct Scratch(PathBuf);
    impl Scratch {
        fn new() -> Self {
            let path = std::env::temp_dir().join(format!(
                "ws-pre-spool-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            fs::create_dir(&path).unwrap();
            Self(path)
        }
    }
    impl Drop for Scratch {
        fn drop(&mut self) {
            fs::remove_dir_all(&self.0).unwrap();
        }
    }
    #[test]
    fn source_spool_reads_exact_count_and_stalled_input_expires() {
        let scratch = Scratch::new();
        let (reader, mut writer) = socket_pair().unwrap();
        reader.set_nonblocking(true).unwrap();
        let payload = vec![0x42; 130_000];
        let sent = payload.clone();
        let sender = thread::spawn(move || {
            writer.write_all(&sent).unwrap();
            writer.write_all(b"END!").unwrap();
        });
        let mut input = File::from(OwnedFd::from(reader));
        let mut staged = spool(
            &mut input,
            &scratch.0.join("source"),
            payload.len() as u64,
            payload.len() as u64,
            &envelope(),
        )
        .unwrap();
        let mut actual = Vec::new();
        staged.read_to_end(&mut actual).unwrap();
        assert_eq!(actual, payload);
        let mut end = [0; 4];
        read_staged_bytes(&mut input, &mut end, &|| Ok(())).unwrap();
        assert_eq!(&end, b"END!");
        sender.join().unwrap();
        assert!(spool(&mut input, &scratch.0.join("excess"), 4, 3, &envelope()).is_err());
        assert!(!scratch.0.join("excess").exists());
        let (reader, mut writer) = socket_pair().unwrap();
        reader.set_nonblocking(true).unwrap();
        writer.write_all(b"x").unwrap();
        let mut input = File::from(OwnedFd::from(reader));
        let mut finite = envelope();
        finite.deadline = Instant::now() + Duration::from_millis(30);
        assert!(spool(&mut input, &scratch.0.join("partial"), 2, 2, &finite)
            .unwrap_err()
            .to_string()
            .contains("deadline"));
        assert!(fs::metadata(scratch.0.join("partial")).unwrap().len() <= 2);
    }

    fn channel() -> (Worker, UnixStream, UnixStream) {
        let (control, peer) = socket_pair().unwrap();
        let (stderr, logs) = socket_pair().unwrap();
        control.set_nonblocking(true).unwrap();
        stderr.set_nonblocking(true).unwrap();
        (
            Worker {
                active: false,
                pid: None,
                control,
                stderr,
                log_bytes: 0,
                cleanup: Instant::now() + Duration::from_secs(2),
            },
            peer,
            logs,
        )
    }
    fn frame(bound: &ProjectBinding<'_>, operation: &str, payload: Value) -> Value {
        json!({"protocol_version":"workstream.pre_submit_worker.v1","operation":operation,
            "request_digest":bound.request_digest,"lease_id":bound.lease_id,"lease_generation":bound.lease_generation,"payload":payload})
    }
    fn send(peer: &mut UnixStream, value: &Value) {
        let bytes = serde_json::to_vec(value).unwrap();
        peer.write_all(&(bytes.len() as u32).to_be_bytes()).unwrap();
        for chunk in bytes.chunks(3) {
            peer.write_all(chunk).unwrap();
        }
    }
    #[test]
    fn worker_dialogue_blocks_project_on_defaults_and_allows_only_one_project_phase() {
        let job = job();
        let bound = binding(&job).unwrap();
        let blocked = frame(
            &bound,
            "completed",
            json!({"workstream_default":{"eligible":false}}),
        );
        let (mut worker, mut peer, _logs) = channel();
        send(&mut peer, &blocked);
        let result = terminal(&mut worker, &envelope(), &bound, |_| {
            panic!("project ran after default blocker")
        })
        .unwrap();
        assert_eq!(serde_json::from_slice::<Value>(&result).unwrap(), blocked);
        for terminal_operation in ["completed", "project"] {
            let (mut worker, mut peer, _logs) = channel();
            let first = frame(&bound, "project", json!({"request":{},"manifest":{}}));
            let last = frame(
                &bound,
                terminal_operation,
                json!({"workstream_default":{"eligible":true}}),
            );
            let peer = thread::spawn(move || {
                send(&mut peer, &first);
                let mut length = [0; 4];
                peer.read_exact(&mut length).unwrap();
                let mut reply = vec![0; u32::from_be_bytes(length) as usize];
                peer.read_exact(&mut reply).unwrap();
                assert_eq!(
                    serde_json::from_slice::<Value>(&reply).unwrap(),
                    json!({"phase_result":true})
                );
                send(&mut peer, &last);
            });
            let mut called = 0;
            let result = terminal(&mut worker, &envelope(), &bound, |_| {
                called += 1;
                Ok(json!({"phase_result":true}))
            });
            assert_eq!(called, 1);
            assert_eq!(result.is_ok(), terminal_operation == "completed");
            peer.join().unwrap();
        }
    }
    #[test]
    fn worker_control_rejects_truncation_oversize_logs_and_rebound_fence() {
        let (mut worker, mut peer, _logs) = channel();
        peer.write_all(&[0, 0]).unwrap();
        drop(peer);
        assert!(worker
            .read_frame(&envelope())
            .unwrap_err()
            .to_string()
            .contains("truncated"));
        let (mut worker, mut peer, _logs) = channel();
        peer.write_all(&u32::MAX.to_be_bytes()).unwrap();
        assert!(worker
            .read_frame(&envelope())
            .unwrap_err()
            .to_string()
            .contains("unbounded"));
        let (mut worker, _peer, mut logs) = channel();
        logs.write_all(b"four").unwrap();
        assert!(worker
            .check_logs(3, envelope().deadline)
            .unwrap_err()
            .to_string()
            .contains("logs"));
        let job = job();
        let bound = binding(&job).unwrap();
        let (mut worker, mut peer, _logs) = channel();
        let mut request = frame(&bound, "project", json!({}));
        request["lease_generation"] = json!(2);
        send(&mut peer, &request);
        assert!(terminal(&mut worker, &envelope(), &bound, |_| panic!(
            "foreign lease launched project"
        ))
        .is_err());
        let (mut worker, _peer, _logs) = channel();
        let mut finite = envelope();
        finite.deadline = Instant::now() + Duration::from_millis(30);
        assert!(worker
            .read_frame(&finite)
            .unwrap_err()
            .to_string()
            .contains("deadline"));
    }
}

#[cfg(all(test, feature = "pre-dialogue-proof"))]
#[path = "dialogue_proof.rs"]
mod dialogue_proof;
