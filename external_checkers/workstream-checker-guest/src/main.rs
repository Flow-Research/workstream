//! Static bootstrap for an untrusted image, invoked before its first instruction.
use sha2::{Digest, Sha256};
use std::ffi::CString;
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::os::fd::FromRawFd;
use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
use std::os::unix::process::CommandExt;
use std::path::{Component, Path};
use std::process::Command;
use workstream_checker_guest::{
    GuestJob, GuestPurpose, CAPACITY_EXIT_CODE, INPUT_ROOT, MAX_JOB_BYTES,
};
use workstream_checker_sdk::parse_request;

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

fn c(value: &str) -> Result<CString> {
    Ok(CString::new(value)?)
}
fn syscall_ok(value: libc::c_int) -> Result<()> {
    if value == 0 {
        Ok(())
    } else {
        Err(std::io::Error::last_os_error().into())
    }
}
fn mount(source: &str, target: &str, kind: &str, flags: libc::c_ulong, data: &str) -> Result<()> {
    // All arguments are owned, terminated strings, valid for this syscall.
    syscall_ok(unsafe {
        libc::mount(
            c(source)?.as_ptr(),
            c(target)?.as_ptr(),
            c(kind)?.as_ptr(),
            flags,
            c(data)?.as_ptr().cast(),
        )
    })
}
fn private_mounts() -> Result<()> {
    syscall_ok(unsafe { libc::unshare(libc::CLONE_NEWNS) })?;
    mount("", "/", "", libc::MS_REC | libc::MS_PRIVATE, "")
}
fn cgroups(cpu: u64, memory: u64) -> Result<()> {
    let root = Path::new("/sys/fs/cgroup");
    fs::write(root.join("cgroup.subtree_control"), "+cpu +memory +pids")?;
    let group = root.join("workstream-checker");
    fs::create_dir(&group)?;
    fs::write(group.join("cpu.max"), format!("{} 100000", cpu * 100))?;
    fs::write(group.join("memory.max"), memory.to_string())?;
    let swap_limit = group.join("memory.swap.max");
    if swap_limit.exists() {
        fs::write(swap_limit, "0")?;
    } else if !fs::read_to_string("/proc/meminfo")?
        .lines()
        .any(|line| line.split_whitespace().collect::<Vec<_>>() == ["SwapTotal:", "0", "kB"])
    {
        return Err("unbounded guest swap".into());
    }
    fs::write(group.join("memory.oom.group"), "1")?;
    fs::write(
        group.join("pids.max"),
        (memory / (16 * 1024 * 1024)).clamp(16, 256).to_string(),
    )?;
    Ok(())
}
fn material_path_is_relative(value: &str) -> bool {
    // ART owns Unicode normalization and project archive limits. Bootstrap only
    // enforces filesystem containment; finding-path presentation rules differ.
    !value.is_empty()
        && !value.contains('\\')
        && !value.contains('\0')
        && value
            .split('/')
            .all(|part| !part.is_empty() && part != "." && part != "..")
        && Path::new(value)
            .components()
            .all(|part| matches!(part, Component::Normal(_)))
}

fn stage(job: &GuestJob, input: &mut impl Read) -> Result<File> {
    // Mask any image-owned /work before handling untrusted paths. Only this
    // trusted process runs in the image until staging and confinement complete.
    fs::create_dir_all("/work")?;
    fs::create_dir_all("/tmp")?;
    // Stage on the VM's bounded ephemeral disk, so immutable input pages can
    // be reclaimed independently of the checker heap. Never put the submitted
    // tree in tmpfs or silently add its expanded size to the workload limit.
    let mut entropy = [0u8; 16];
    File::open("/dev/urandom")?.read_exact(&mut entropy)?;
    let suffix: String = entropy.iter().map(|byte| format!("{byte:02x}")).collect();
    let staging = format!("/.workstream-material-{suffix}");
    fs::create_dir(&staging)?;
    mount(&staging, "/work", "", libc::MS_BIND, "")?;
    fs::create_dir(INPUT_ROOT)?;
    for directory in &job.directories {
        if !material_path_is_relative(directory) {
            return Err("unsafe directory".into());
        }
        fs::create_dir_all(Path::new(INPUT_ROOT).join(directory))?;
    }
    for entry in &job.files {
        if !material_path_is_relative(&entry.normalized_path) {
            return Err("unsafe file".into());
        }
        let path = Path::new(INPUT_ROOT).join(&entry.normalized_path);
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(if entry.executable { 0o555 } else { 0o444 })
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(&path)?;
        let mut remaining = entry.byte_count;
        let mut hash = Sha256::new();
        let mut bytes = [0u8; 65536];
        while remaining > 0 {
            let size = remaining.min(bytes.len() as u64) as usize;
            input.read_exact(&mut bytes[..size])?;
            hash.update(&bytes[..size]);
            file.write_all(&bytes[..size])?;
            remaining -= size as u64;
        }
        if format!("sha256:{:x}", hash.finalize()) != entry.sha256 {
            return Err("material hash differs".into());
        }
    }
    let request = "/work/request.json";
    fs::write(request, serde_json::to_vec(&job.request)?)?;
    fs::set_permissions(request, fs::Permissions::from_mode(0o444))?;
    Ok(File::open(request)?)
}
fn confined_devices() -> Result<()> {
    mount(
        "tmpfs",
        "/dev",
        "tmpfs",
        libc::MS_NOSUID | libc::MS_NOEXEC,
        "size=65536,mode=0755",
    )?;
    for (name, minor) in [
        ("null", 3),
        ("zero", 5),
        ("full", 7),
        ("random", 8),
        ("urandom", 9),
    ] {
        syscall_ok(unsafe {
            libc::mknod(
                c(&format!("/dev/{name}"))?.as_ptr(),
                libc::S_IFCHR | 0o666,
                libc::makedev(1, minor),
            )
        })?;
    }
    for (name, target) in [
        ("fd", "/proc/self/fd"),
        ("stdin", "/proc/self/fd/0"),
        ("stdout", "/proc/self/fd/1"),
        ("stderr", "/proc/self/fd/2"),
    ] {
        std::os::unix::fs::symlink(target, format!("/dev/{name}"))?;
    }
    Ok(())
}

fn syscall_filter() -> Result<()> {
    // x86_64 is the closed node platform. Deny namespace/capability escape
    // operations and guest management transports. clone3 returns ENOSYS so
    // libc can use the filtered clone path for ordinary language threads.
    const LOAD: u16 = 0x20;
    const EQUAL: u16 = 0x15;
    const RETURN: u16 = 0x06;
    const AND: u16 = 0x54;
    const ALLOW: u32 = 0x7fff0000;
    const ERROR: u32 = 0x00050000;
    fn op(code: u16, jt: u8, jf: u8, k: u32) -> libc::sock_filter {
        libc::sock_filter { code, jt, jf, k }
    }
    let mut filter = vec![
        op(LOAD, 0, 0, 4),
        op(EQUAL, 1, 0, 0xc000003e),
        op(RETURN, 0, 0, 0x80000000),
        op(LOAD, 0, 0, 0),
        op(0x35, 0, 1, 0x40000000),
        op(RETURN, 0, 0, ERROR | libc::ENOSYS as u32),
    ];
    for call in [
        libc::SYS_mount,
        libc::SYS_umount2,
        libc::SYS_pivot_root,
        libc::SYS_unshare,
        libc::SYS_setns,
        libc::SYS_bpf,
        libc::SYS_perf_event_open,
        libc::SYS_userfaultfd,
        libc::SYS_ptrace,
        libc::SYS_reboot,
        libc::SYS_kexec_load,
        libc::SYS_init_module,
        libc::SYS_finit_module,
        libc::SYS_delete_module,
        libc::SYS_open_by_handle_at,
        libc::SYS_keyctl,
        libc::SYS_add_key,
        libc::SYS_request_key,
        libc::SYS_mount_setattr,
        libc::SYS_fsopen,
        libc::SYS_fsmount,
        libc::SYS_move_mount,
        libc::SYS_open_tree,
        // io_uring can issue socket/connect operations without passing through
        // the socket syscall rule below. No management-transport bypass.
        libc::SYS_io_uring_setup,
        libc::SYS_io_uring_enter,
        libc::SYS_io_uring_register,
    ] {
        filter.extend([
            op(EQUAL, 0, 1, call as u32),
            op(RETURN, 0, 0, ERROR | libc::EPERM as u32),
        ]);
    }
    filter.extend([
        op(EQUAL, 0, 1, libc::SYS_clone3 as u32),
        op(RETURN, 0, 0, ERROR | libc::ENOSYS as u32),
        op(EQUAL, 0, 4, libc::SYS_clone as u32),
        op(LOAD, 0, 0, 16),
        op(
            AND,
            0,
            0,
            (libc::CLONE_NEWUSER
                | libc::CLONE_NEWNS
                | libc::CLONE_NEWCGROUP
                | libc::CLONE_NEWPID
                | libc::CLONE_NEWNET
                | libc::CLONE_NEWIPC
                | libc::CLONE_NEWUTS) as u32,
        ),
        op(EQUAL, 1, 0, 0),
        op(RETURN, 0, 0, ERROR | libc::EPERM as u32),
        op(LOAD, 0, 0, 0),
        op(EQUAL, 0, 5, libc::SYS_socket as u32),
        op(LOAD, 0, 0, 16),
        op(EQUAL, 3, 0, libc::AF_UNIX as u32),
        op(EQUAL, 2, 0, libc::AF_INET as u32),
        op(EQUAL, 1, 0, libc::AF_INET6 as u32),
        op(RETURN, 0, 0, ERROR | libc::EAFNOSUPPORT as u32),
        op(RETURN, 0, 0, ALLOW),
    ]);
    let program = libc::sock_fprog {
        len: filter.len() as u16,
        filter: filter.as_mut_ptr(),
    };
    syscall_ok(unsafe { libc::prctl(libc::PR_SET_SECCOMP, 2, &program) })
}

fn readonly_filesystem() -> Result<()> {
    // mount_setattr recursively freezes every existing mount, including image
    // overlays and material. Then install the sole writable, bounded scratch.
    #[repr(C)]
    struct Attr {
        set: u64,
        clear: u64,
        propagation: u64,
        userns: u64,
    }
    let attr = Attr {
        set: 1 | 2 | 4,
        clear: 0,
        propagation: 0,
        userns: 0,
    }; // RDONLY,NOSUID,NODEV: image-owned device nodes must never be usable.
    let result = unsafe {
        libc::syscall(
            libc::SYS_mount_setattr,
            libc::AT_FDCWD,
            c("/")?.as_ptr(),
            0x8000u32,
            &attr,
            std::mem::size_of::<Attr>(),
        )
    };
    if result != 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    // Only the trusted, freshly constructed /dev whitelist may contain usable
    // device nodes. Keep its read-only and nosuid attributes in place.
    let devices = Attr {
        set: 0,
        clear: 4,
        propagation: 0,
        userns: 0,
    };
    let result = unsafe {
        libc::syscall(
            libc::SYS_mount_setattr,
            libc::AT_FDCWD,
            c("/dev")?.as_ptr(),
            0u32,
            &devices,
            std::mem::size_of::<Attr>(),
        )
    };
    if result != 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    mount(
        "tmpfs",
        "/tmp",
        "tmpfs",
        libc::MS_NOSUID | libc::MS_NODEV | libc::MS_NOEXEC,
        "size=16777216,mode=1777",
    )?;
    // Hide the management filesystem, cgroup controls and agent storage. Mounts
    // are private, so the supervisor outside this namespace remains functional.
    for target in ["/sys", "/storage", "/workspace", "/run"] {
        if Path::new(target).is_dir() {
            mount(
                "tmpfs",
                target,
                "tmpfs",
                libc::MS_RDONLY | libc::MS_NOSUID | libc::MS_NODEV | libc::MS_NOEXEC,
                "size=4096,mode=0555",
            )?;
        }
    }
    Ok(())
}
fn drop_privileges(uid: u32, gid: u32) -> Result<()> {
    if uid == 0 || gid == 0 {
        return Err("root checker forbidden".into());
    }
    // Drop the bounding set while privileged, then supplementary groups and IDs.
    for capability in 0..=40 {
        syscall_ok(unsafe { libc::prctl(libc::PR_CAPBSET_DROP, capability, 0, 0, 0) })?;
    }
    syscall_ok(unsafe { libc::setgroups(0, std::ptr::null()) })?;
    syscall_ok(unsafe { libc::setresgid(gid, gid, gid) })?;
    syscall_ok(unsafe { libc::setresuid(uid, uid, uid) })?;
    syscall_ok(unsafe { libc::prctl(libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) })?;
    Ok(())
}
fn supervised_exit(status: i32, oom_kills: u64) -> i32 {
    if oom_kills > 0 {
        CAPACITY_EXIT_CODE
    } else if libc::WIFEXITED(status) && libc::WEXITSTATUS(status) == 0 {
        0
    } else {
        125
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn material_containment_does_not_apply_finding_presentation_limits() {
        assert!(material_path_is_relative(&format!(
            "folder/{}",
            "x".repeat(1001)
        )));
        assert!(material_path_is_relative("folder/a\u{200b}b"));
        for path in [
            "/absolute",
            "../outside",
            "a/../outside",
            "a/./b",
            "a//b",
            "a\\b",
        ] {
            assert!(!material_path_is_relative(path));
        }
    }
    #[test]
    fn checker_exit_codes_cannot_forge_trusted_oom_classification() {
        assert_eq!(supervised_exit(CAPACITY_EXIT_CODE << 8, 0), 125);
        assert_eq!(supervised_exit(libc::SIGKILL, 0), 125);
        assert_eq!(supervised_exit(libc::SIGKILL, 1), CAPACITY_EXIT_CODE);
        assert_eq!(supervised_exit(0, 0), 0);
    }
}

fn main() {
    if let Err(error) = run() {
        eprintln!("workstream guest bootstrap failed: {error}");
        std::process::exit(125);
    }
}
fn run() -> Result<()> {
    // Read exactly the bootstrap bytes without userspace read-ahead: trusted
    // intake keeps the remaining command stream as its stdin after exec.
    let descriptor = unsafe { libc::dup(0) };
    if descriptor < 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    let mut input = unsafe { File::from_raw_fd(descriptor) };
    let mut length = [0u8; 4];
    input.read_exact(&mut length)?;
    let length = u32::from_be_bytes(length) as usize;
    if length == 0 || length > MAX_JOB_BYTES {
        return Err("job size invalid".into());
    }
    let mut bytes = vec![0; length];
    input.read_exact(&mut bytes)?;
    let job: GuestJob = serde_json::from_slice(&bytes)?;
    let (cpu, memory, intake) = match job.purpose {
        GuestPurpose::Project => {
            let request = parse_request(&serde_json::to_vec(&job.request)?)?;
            (request.cpu_millis, request.memory_bytes, false)
        }
        GuestPurpose::TrustedIntake {
            cpu_millis,
            memory_bytes,
        } => {
            if cpu_millis != 1000
                || memory_bytes != 2 * 1024 * 1024 * 1024
                || job.files.len() != 1
                || job.files[0].normalized_path != "archive.zip"
                || job.files[0].byte_count > 512 * 1024 * 1024
                || !job.directories.is_empty()
            {
                return Err("trusted intake bootstrap invalid".into());
            }
            (cpu_millis, memory_bytes, true)
        }
    };
    if job.command.is_empty() || job.command.len() > 256 || job.environment.len() > 1024 {
        return Err("image configuration invalid".into());
    }
    private_mounts().map_err(|e| format!("mount namespace: {e}"))?;
    // Stage before applying workload memory: submitted files are immutable input,
    // not checker heap. The enclosing VMM and disk bounds cover staging custody.
    let request_file = stage(&job, &mut input).map_err(|e| format!("staging: {e}"))?;
    drop(input);
    if intake {
        fs::create_dir("/work/scratch")?;
        mount("/work/scratch", "/work/scratch", "", libc::MS_BIND, "")?;
        syscall_ok(unsafe { libc::chown(c("/work/scratch")?.as_ptr(), job.uid, job.gid) })?;
        fs::set_permissions("/work/scratch", fs::Permissions::from_mode(0o700))?;
    }
    cgroups(cpu, memory).map_err(|e| format!("cgroup: {e}"))?;
    // The trusted, single-threaded supervisor stays outside the workload cgroup
    // so an OOM cannot destroy the kernel evidence before it is classified.
    // stdin's lock has been dropped and no other threads exist at this fork.
    let child = unsafe { libc::fork() };
    if child < 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    if child > 0 {
        let mut status = 0;
        loop {
            let waited = unsafe { libc::waitpid(child, &mut status, 0) };
            if waited == child {
                break;
            }
            if waited < 0
                && std::io::Error::last_os_error().kind() != std::io::ErrorKind::Interrupted
            {
                return Err(std::io::Error::last_os_error().into());
            }
        }
        let events = fs::read_to_string("/sys/fs/cgroup/workstream-checker/memory.events")?;
        let oom = events
            .lines()
            .find_map(|line| line.strip_prefix("oom_kill "))
            .ok_or("memory OOM evidence missing")?
            .parse::<u64>()?;
        std::process::exit(supervised_exit(status, oom));
    }
    private_mounts().map_err(|e| format!("workload mount namespace: {e}"))?;
    fs::write(
        "/sys/fs/cgroup/workstream-checker/cgroup.procs",
        std::process::id().to_string(),
    )?;
    confined_devices().map_err(|e| format!("devices: {e}"))?;
    readonly_filesystem().map_err(|e| format!("filesystem: {e}"))?;
    if intake {
        // Only the trusted worker receives private VM-disk scratch. Project
        // workloads retain their existing bounded tmpfs-only writable surface.
        mount(
            "",
            "/work/scratch",
            "",
            libc::MS_BIND | libc::MS_REMOUNT | libc::MS_NOSUID | libc::MS_NODEV | libc::MS_NOEXEC,
            "",
        )?;
    }
    drop_privileges(job.uid, job.gid).map_err(|e| format!("privileges: {e}"))?;
    syscall_filter().map_err(|e| format!("syscall policy: {e}"))?;
    let mut command = Command::new(&job.command[0]);
    command.args(&job.command[1..]).env_clear();
    if !intake {
        command.stdin(request_file);
    }
    for entry in &job.environment {
        let (key, value) = entry.split_once('=').ok_or("invalid image environment")?;
        command.env(key, value);
    }
    command.current_dir(if job.working_directory.is_empty() {
        "/"
    } else {
        &job.working_directory
    });
    let error = command.exec();
    Err(error.into())
}
