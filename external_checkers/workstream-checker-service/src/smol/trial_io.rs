//! Exact host admission of one trusted Smol trial result and its raw export.

use super::io::{self, IoGuard, MaterialSource};
use super::*;
use crate::trial_relay::TrialExportOutcome as HostExportOutcome;
use crate::trial_smol::{SmolTrialChildResult, SmolTrialRuntimeFailure, SmolTrialTermination};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, HashSet};
use std::io::Read;
use std::os::unix::fs::{DirBuilderExt, MetadataExt, OpenOptionsExt};
use std::path::{Component, Path, PathBuf};
use std::process::ChildStdout;
use workstream_checker_guest::{
    GuestJob, MaterialRoot, TrialChildResult, TrialExport, TrialExportHeader, TrialExportOutcome,
    TrialTermination, TRIAL_CHILD_PROTOCOL, TRIAL_EXPORT_PROTOCOL, TRIAL_OUTPUT_MAXIMUM_BYTES,
};
use workstream_checker_sdk::canonical_hash;

const RESULT_MAXIMUM: usize = 1024 * 1024;
const PATH_MAXIMUM: usize = 4096;
const DEPTH_MAXIMUM: usize = 256;

pub(super) enum ExportTarget<'a> {
    Candidate {
        path: &'a Path,
        maximum_bytes: u64,
    },
    Workspace {
        root: &'a Path,
        maximum_bytes: u64,
        maximum_entries: u64,
    },
}

fn valid_digest(value: &str) -> bool {
    value.len() == 71
        && value.starts_with("sha256:")
        && value[7..]
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
}

fn valid_relative(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= PATH_MAXIMUM
        && !value.contains('\\')
        && !value.contains('\0')
        && Path::new(value).components().count() > 0
        && Path::new(value).components().count() <= DEPTH_MAXIMUM
        && Path::new(value)
            .components()
            .all(|component| matches!(component, Component::Normal(_)))
}

fn guard_failure(guard: &IoGuard<'_>) -> SmolTrialRuntimeFailure {
    if guard
        .cancelled
        .iter()
        .any(|value| value.load(Ordering::Acquire))
    {
        SmolTrialRuntimeFailure::Cancelled
    } else if Instant::now() >= guard.deadline {
        SmolTrialRuntimeFailure::DeadlineExceeded
    } else {
        SmolTrialRuntimeFailure::InvalidObservation
    }
}

pub(super) fn scan_material(
    name: &str,
    root: &Path,
    maximum_bytes: u64,
    maximum_entries: u64,
    guard: &IoGuard<'_>,
) -> Result<(MaterialSource, u64, u64), SmolTrialRuntimeFailure> {
    guard.check().map_err(|_| guard_failure(guard))?;
    if fs::canonicalize(root).ok().as_deref() != Some(root) {
        return Err(SmolTrialRuntimeFailure::InvalidObservation);
    }
    let metadata =
        fs::symlink_metadata(root).map_err(|_| SmolTrialRuntimeFailure::InvalidObservation)?;
    if !metadata.file_type().is_dir()
        || metadata.file_type().is_symlink()
        || metadata.uid() != unsafe { libc::geteuid() }
        || metadata.gid() != unsafe { libc::getegid() }
        || metadata.mode() & 0o022 != 0
    {
        return Err(SmolTrialRuntimeFailure::InvalidObservation);
    }
    let mut directories = Vec::new();
    let mut files = Vec::new();
    let mut pending = vec![PathBuf::new()];
    let mut bytes = 0_u64;
    let mut entries = 0_u64;
    while let Some(relative) = pending.pop() {
        guard.check().map_err(|_| guard_failure(guard))?;
        let mut children = BTreeMap::new();
        for entry in fs::read_dir(root.join(&relative))
            .map_err(|_| SmolTrialRuntimeFailure::InvalidObservation)?
        {
            let entry = entry.map_err(|_| SmolTrialRuntimeFailure::InvalidObservation)?;
            if children.insert(entry.file_name(), entry.path()).is_some() {
                return Err(SmolTrialRuntimeFailure::InvalidObservation);
            }
        }
        for (name, path) in children.into_iter().rev() {
            guard.check().map_err(|_| guard_failure(guard))?;
            let child = relative.join(name);
            let normalized = child
                .to_str()
                .filter(|value| valid_relative(value))
                .ok_or(SmolTrialRuntimeFailure::InvalidObservation)?
                .to_owned();
            let metadata = fs::symlink_metadata(&path)
                .map_err(|_| SmolTrialRuntimeFailure::InvalidObservation)?;
            if metadata.uid() != unsafe { libc::geteuid() }
                || metadata.gid() != unsafe { libc::getegid() }
                || metadata.mode() & 0o022 != 0
            {
                return Err(SmolTrialRuntimeFailure::InvalidObservation);
            }
            entries = entries
                .checked_add(1)
                .ok_or(SmolTrialRuntimeFailure::CapacityExceeded)?;
            if entries > maximum_entries {
                return Err(SmolTrialRuntimeFailure::CapacityExceeded);
            }
            if metadata.file_type().is_dir() {
                directories.push(normalized);
                pending.push(child);
            } else if metadata.file_type().is_file() && !metadata.file_type().is_symlink() {
                bytes = bytes
                    .checked_add(metadata.len())
                    .ok_or(SmolTrialRuntimeFailure::CapacityExceeded)?;
                if bytes > maximum_bytes {
                    return Err(SmolTrialRuntimeFailure::CapacityExceeded);
                }
                let mut source = OpenOptions::new()
                    .read(true)
                    .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
                    .open(&path)
                    .map_err(|_| SmolTrialRuntimeFailure::InvalidObservation)?;
                let mut digest = Sha256::new();
                let mut observed = 0_u64;
                let mut buffer = [0_u8; 65_536];
                loop {
                    guard.check().map_err(|_| guard_failure(guard))?;
                    let count = source
                        .read(&mut buffer)
                        .map_err(|_| SmolTrialRuntimeFailure::InvalidObservation)?;
                    if count == 0 {
                        break;
                    }
                    observed = observed
                        .checked_add(count as u64)
                        .ok_or(SmolTrialRuntimeFailure::CapacityExceeded)?;
                    digest.update(&buffer[..count]);
                }
                if observed != metadata.len() {
                    return Err(SmolTrialRuntimeFailure::InvalidObservation);
                }
                files.push(workstream_checker_guest::MaterialFile {
                    normalized_path: normalized,
                    byte_count: observed,
                    sha256: format!("sha256:{:x}", digest.finalize()),
                    executable: metadata.mode() & 0o111 != 0,
                });
            } else {
                return Err(SmolTrialRuntimeFailure::InvalidObservation);
            }
        }
    }
    directories.sort();
    files.sort_by(|left, right| left.normalized_path.cmp(&right.normalized_path));
    Ok((
        MaterialSource {
            manifest: MaterialRoot {
                name: name.to_owned(),
                directories,
                files,
            },
            root: root.to_owned(),
        },
        bytes,
        entries,
    ))
}

fn sync_directory(path: &Path) -> Result<(), String> {
    File::open(path)
        .and_then(|directory| directory.sync_all())
        .map_err(|_| "trial export persistence failed".into())
}

fn write_exact_file(
    output: &mut ChildStdout,
    path: &Path,
    byte_count: u64,
    expected_sha256: &str,
    executable: bool,
    guard: &IoGuard<'_>,
) -> Result<(), String> {
    if !valid_digest(expected_sha256) {
        return Err("trial export digest invalid".into());
    }
    let mut destination = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(if executable { 0o500 } else { 0o400 })
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(path)
        .map_err(|_| "trial export destination unavailable")?;
    let mut remaining = byte_count;
    let mut digest = Sha256::new();
    let mut buffer = [0_u8; 65_536];
    while remaining > 0 {
        let count = usize::try_from(remaining.min(buffer.len() as u64))
            .map_err(|_| "trial export size invalid")?;
        io::read_exact(output, &mut buffer[..count], guard)?;
        destination
            .write_all(&buffer[..count])
            .map_err(|_| "trial export write failed")?;
        digest.update(&buffer[..count]);
        remaining -= count as u64;
    }
    destination
        .sync_all()
        .map_err(|_| "trial export persistence failed")?;
    if format!("sha256:{:x}", digest.finalize()) != expected_sha256 {
        return Err("trial export digest differs".into());
    }
    Ok(())
}

fn prepare_workspace(
    root: &Path,
    directories: &[String],
    files: &[workstream_checker_guest::MaterialFile],
    maximum_bytes: u64,
    maximum_entries: u64,
) -> Result<PathBuf, String> {
    let entry_count = u64::try_from(directories.len())
        .ok()
        .and_then(|count| count.checked_add(files.len() as u64))
        .ok_or("trial workspace inventory overflow")?;
    let byte_count = files.iter().try_fold(0_u64, |total, file| {
        total
            .checked_add(file.byte_count)
            .ok_or("trial workspace byte count overflow")
    })?;
    if entry_count > maximum_entries || byte_count > maximum_bytes {
        return Err("trial workspace export exceeds capacity".into());
    }
    if directories.windows(2).any(|pair| pair[0] >= pair[1])
        || files
            .windows(2)
            .any(|pair| pair[0].normalized_path >= pair[1].normalized_path)
    {
        return Err("trial workspace inventory is not canonical".into());
    }
    let directory_set: HashSet<_> = directories.iter().map(String::as_str).collect();
    let file_set: HashSet<_> = files
        .iter()
        .map(|file| file.normalized_path.as_str())
        .collect();
    if directory_set.len() != directories.len()
        || file_set.len() != files.len()
        || directory_set.iter().any(|path| file_set.contains(path))
        || directories.iter().any(|path| !valid_relative(path))
        || files.iter().any(|file| {
            !valid_relative(&file.normalized_path)
                || !valid_digest(&file.sha256)
                || Path::new(&file.normalized_path)
                    .parent()
                    .is_some_and(|parent| {
                        !parent.as_os_str().is_empty()
                            && !directory_set.contains(parent.to_str().unwrap_or(""))
                    })
        })
    {
        return Err("trial workspace inventory is invalid".into());
    }
    for directory in directories {
        let parent = Path::new(directory)
            .parent()
            .and_then(Path::to_str)
            .unwrap_or("");
        if !parent.is_empty() && !directory_set.contains(parent) {
            return Err("trial workspace directory parent is absent".into());
        }
    }
    let next = root.join("workspace.next");
    let mut builder = fs::DirBuilder::new();
    builder.mode(0o700);
    builder
        .create(&next)
        .map_err(|_| "trial workspace export destination unavailable")?;
    for directory in directories {
        builder
            .create(next.join(directory))
            .map_err(|_| "trial workspace directory unavailable")?;
    }
    Ok(next)
}

fn receive_export(
    output: &mut ChildStdout,
    export: &Option<TrialExport>,
    target: &ExportTarget<'_>,
    guard: &IoGuard<'_>,
) -> Result<(), String> {
    match (export, target) {
        (
            Some(TrialExport::CandidateArchive { byte_count, sha256 }),
            ExportTarget::Candidate {
                path,
                maximum_bytes,
            },
        ) => {
            if *byte_count == 0 || byte_count > maximum_bytes {
                return Err("trial candidate export exceeds capacity".into());
            }
            write_exact_file(output, path, *byte_count, sha256, false, guard)?;
            sync_directory(
                path.parent()
                    .ok_or("trial candidate export parent unavailable")?,
            )
        }
        (
            Some(TrialExport::Workspace { directories, files }),
            ExportTarget::Workspace {
                root,
                maximum_bytes,
                maximum_entries,
            },
        ) => {
            let next =
                prepare_workspace(root, directories, files, *maximum_bytes, *maximum_entries)?;
            for file in files {
                write_exact_file(
                    output,
                    &next.join(&file.normalized_path),
                    file.byte_count,
                    &file.sha256,
                    file.executable,
                    guard,
                )?;
            }
            for directory in directories.iter().rev() {
                sync_directory(&next.join(directory))?;
            }
            sync_directory(&next)?;
            sync_directory(root)
        }
        (None, _) => Ok(()),
        _ => Err("trial export type differs".into()),
    }
}

fn remove_partial(target: &ExportTarget<'_>) {
    match target {
        ExportTarget::Candidate { path, .. } => {
            let _ = fs::remove_file(path);
        }
        ExportTarget::Workspace { root, .. } => {
            let _ = fs::remove_dir_all(root.join("workspace.next"));
        }
    }
}

fn receive_frame<T: serde::de::DeserializeOwned>(
    output: &mut ChildStdout,
    guard: &IoGuard<'_>,
) -> Result<T, String> {
    let mut length = [0_u8; 4];
    io::read_exact(output, &mut length, guard)?;
    let length = u32::from_be_bytes(length) as usize;
    if length == 0 || length > RESULT_MAXIMUM {
        return Err("trial frame is unbounded".into());
    }
    let mut bytes = vec![0_u8; length];
    io::read_exact(output, &mut bytes, guard)?;
    serde_json::from_slice(&bytes).map_err(|_| "trial frame invalid".into())
}

fn receive_output(
    output: &mut ChildStdout,
    byte_count: u64,
    expected_sha256: &str,
    guard: &IoGuard<'_>,
) -> Result<String, String> {
    let mut bytes = vec![0_u8; byte_count as usize];
    io::read_exact(output, &mut bytes, guard)?;
    if format!("sha256:{:x}", Sha256::digest(&bytes)) != expected_sha256 {
        return Err("trial retained output digest differs".into());
    }
    String::from_utf8(bytes).map_err(|_| "trial retained output is not UTF-8".into())
}

pub(super) fn exchange(
    mut child: Child,
    job: &GuestJob,
    materials: &[MaterialSource],
    expected_operation: &str,
    target: ExportTarget<'_>,
    guard: &IoGuard<'_>,
) -> Result<TrialChildResult, String> {
    let mut input = child.stdin.take().ok_or("trial guest input unavailable")?;
    let mut output = child
        .stdout
        .take()
        .ok_or("trial guest output unavailable")?;
    set_nonblocking(&input)?;
    set_nonblocking(&output)?;
    let result = (|| {
        let maximum_output = job.request["limits"]["output_bytes"]
            .as_u64()
            .filter(|value| (1..=TRIAL_OUTPUT_MAXIMUM_BYTES).contains(value))
            .ok_or("trial guest output limit invalid")?;
        io::write_job(&mut input, job, materials, guard)?;
        drop(input);
        let header: TrialExportHeader = receive_frame(&mut output, guard)?;
        if header.schema_version != TRIAL_EXPORT_PROTOCOL
            || header.operation_id != expected_operation
        {
            return Err("trial export identity differs".into());
        }
        if !valid_digest(&header.stdout_sha256)
            || !valid_digest(&header.stderr_sha256)
            || header
                .stdout_bytes
                .checked_add(header.stderr_bytes)
                .is_none_or(|value| value > maximum_output)
        {
            return Err("trial retained output exceeds capacity".into());
        }
        receive_export(&mut output, &header.export, &target, guard)?;
        let stdout = receive_output(
            &mut output,
            header.stdout_bytes,
            &header.stdout_sha256,
            guard,
        )?;
        let stderr = receive_output(
            &mut output,
            header.stderr_bytes,
            &header.stderr_sha256,
            guard,
        )?;
        // Payload remains provisional until the final measurement, cleanup,
        // successful process exit and exact EOF are all verified.
        let mut result: TrialChildResult = receive_frame(&mut output, guard)?;
        if result.schema_version != TRIAL_CHILD_PROTOCOL
            || result.operation_id != expected_operation
            || result.export != header.export
            || (result.export_outcome == TrialExportOutcome::Exported) != header.export.is_some()
            || !result.terminal_facts_are_valid()
            || !result.guest_cleanup_confirmed
            || result.stdout_bytes != header.stdout_bytes
            || result.stdout_sha256 != header.stdout_sha256
            || result.stderr_bytes != header.stderr_bytes
            || result.stderr_sha256 != header.stderr_sha256
        {
            return Err("trial result identity differs".into());
        }
        if !reap_child(&mut child, guard.deadline)?.success() {
            return Err("trial guest execution failed".into());
        }
        let mut extra = [0_u8; 1];
        if !matches!(output.read(&mut extra), Ok(0)) {
            return Err("trial guest output contains trailing bytes".into());
        }
        result.stdout = stdout;
        result.stderr = stderr;
        Ok(result)
    })();
    if result.is_err() {
        remove_partial(&target);
        let _ = stop_command_group(&mut child, Instant::now() + SOCKET_IO_TIMEOUT);
    }
    result
}

fn termination(value: TrialTermination) -> SmolTrialTermination {
    match value {
        TrialTermination::Exited => SmolTrialTermination::Exited,
        TrialTermination::Signalled => SmolTrialTermination::Signalled,
        TrialTermination::DeadlineExceeded => SmolTrialTermination::DeadlineExceeded,
        TrialTermination::CpuExceeded => SmolTrialTermination::CpuExceeded,
        TrialTermination::MemoryExceeded => SmolTrialTermination::MemoryExceeded,
        TrialTermination::PidExceeded => SmolTrialTermination::PidExceeded,
        TrialTermination::DiskExceeded => SmolTrialTermination::DiskExceeded,
        TrialTermination::OutputExceeded => SmolTrialTermination::OutputExceeded,
    }
}

fn export_outcome(value: TrialExportOutcome) -> HostExportOutcome {
    match value {
        TrialExportOutcome::Exported => HostExportOutcome::Exported,
        TrialExportOutcome::CapacityExceeded => HostExportOutcome::CapacityExceeded,
        TrialExportOutcome::Invalid => HostExportOutcome::Invalid,
        TrialExportOutcome::Unavailable => HostExportOutcome::Unavailable,
        TrialExportOutcome::NotStarted => HostExportOutcome::NotStarted,
    }
}

pub(super) fn child_result(
    value: TrialChildResult,
    before: Option<String>,
    after: Option<String>,
) -> SmolTrialChildResult {
    SmolTrialChildResult {
        termination: termination(value.termination),
        exit_code: value.child.exit_code,
        signal: value.child.signal,
        stdout: value.stdout,
        stderr: value.stderr,
        stdout_sha256: value.stdout_sha256,
        stderr_sha256: value.stderr_sha256,
        stdout_bytes: value.stdout_bytes,
        stderr_bytes: value.stderr_bytes,
        export_outcome: export_outcome(value.export_outcome),
        elapsed_ms: value.elapsed_ms,
        cpu_time_ms: value.cpu_time_ms,
        peak_memory_bytes: value.peak_memory_bytes,
        peak_pids: value.peak_pids,
        written_bytes: value.written_bytes,
        written_entries: value.written_entries,
        measurement_method: value.measurement_method,
        workspace_before_sha256: before,
        workspace_after_sha256: after,
        cleanup_confirmed: true,
    }
}

pub(super) fn workspace_digest(
    result: &TrialChildResult,
) -> Result<String, SmolTrialRuntimeFailure> {
    let Some(TrialExport::Workspace { directories, files }) = &result.export else {
        return Err(SmolTrialRuntimeFailure::InvalidObservation);
    };
    let value = serde_json::to_value(MaterialRoot {
        name: "workspace".into(),
        directories: directories.clone(),
        files: files.clone(),
    })
    .map_err(|_| SmolTrialRuntimeFailure::InvalidObservation)?;
    canonical_hash(&value).map_err(|_| SmolTrialRuntimeFailure::InvalidObservation)
}

pub(super) fn material_digest(manifest: &MaterialRoot) -> Result<String, SmolTrialRuntimeFailure> {
    let value =
        serde_json::to_value(manifest).map_err(|_| SmolTrialRuntimeFailure::InvalidObservation)?;
    canonical_hash(&value).map_err(|_| SmolTrialRuntimeFailure::InvalidObservation)
}

pub(super) fn operation_id(owner: &crate::trial_smol::SmolTrialOwner, suffix: &str) -> String {
    let mut digest = Sha256::new();
    for value in [
        owner.deployment_owner.as_str(),
        owner.request_digest.as_str(),
        owner.attempt_id.as_str(),
        owner.trial_owner_id.as_str(),
        suffix,
    ] {
        digest.update((value.len() as u64).to_be_bytes());
        digest.update(value.as_bytes());
    }
    format!("trial_{:x}", digest.finalize())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};
    use workstream_checker_guest::MaterialFile;

    struct Scratch(PathBuf);

    impl Scratch {
        fn new() -> Self {
            let nonce = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos();
            let path = std::env::temp_dir().join(format!(
                "workstream-trial-io-{}-{nonce}",
                std::process::id()
            ));
            fs::create_dir(&path).unwrap();
            Self(path)
        }
    }

    impl Drop for Scratch {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    fn file(path: &str, bytes: u64) -> MaterialFile {
        MaterialFile {
            normalized_path: path.into(),
            byte_count: bytes,
            sha256: format!("sha256:{}", "1".repeat(64)),
            executable: false,
        }
    }

    #[test]
    fn workspace_inventory_is_canonical_and_bounded_before_creation() {
        let root = Scratch::new();
        assert!(prepare_workspace(
            &root.0,
            &["nested".into()],
            &[file("nested/value", 4)],
            4,
            2,
        )
        .is_ok());
        fs::remove_dir_all(root.0.join("workspace.next")).unwrap();
        assert!(prepare_workspace(
            &root.0,
            &["nested".into()],
            &[file("missing/value", 4)],
            4,
            2,
        )
        .is_err());
        assert!(prepare_workspace(&root.0, &["z".into(), "a".into()], &[], 4, 2,).is_err());
        assert!(prepare_workspace(&root.0, &[], &[file("value", 5)], 4, 1).is_err());
        assert!(!root.0.join("workspace.next").exists());
    }

    #[test]
    fn relative_paths_and_digests_are_closed() {
        assert!(valid_relative("nested/value"));
        assert!(!valid_relative("../value"));
        assert!(!valid_relative("/absolute"));
        assert!(valid_digest(&format!("sha256:{}", "a".repeat(64))));
        assert!(!valid_digest(&format!("sha256:{}", "A".repeat(64))));
    }

    #[test]
    fn export_is_admitted_only_after_matching_final_result_and_clean_eof() {
        use workstream_checker_guest::{GuestPurpose, TrialChildOutcome};
        for fault in [
            "none",
            "missing_final",
            "wrong_identity",
            "wrong_export",
            "unclean",
            "trailing",
            "exit",
            "altered_raw_output",
            "output_over_limit",
            "output_overflow",
            "wrong_final_length",
            "wrong_final_digest",
            "invalid_utf8",
            "json_output_substitution",
            "maximum_raw_output",
            "absolute_output_limit",
        ] {
            let root = Scratch::new();
            let payload = b"verified candidate";
            let export = TrialExport::CandidateArchive {
                byte_count: payload.len() as u64,
                sha256: format!("sha256:{:x}", Sha256::digest(payload)),
            };
            let stderr = b"actual diagnostic\n";
            let stdout = match fault {
                "invalid_utf8" => vec![0xff],
                "maximum_raw_output" => vec![0; TRIAL_OUTPUT_MAXIMUM_BYTES as usize - stderr.len()],
                _ => b"actual output\n".to_vec(),
            };
            let mut header = TrialExportHeader {
                schema_version: TRIAL_EXPORT_PROTOCOL.into(),
                operation_id: "operation".into(),
                export: Some(export.clone()),
                stdout_bytes: stdout.len() as u64,
                stdout_sha256: format!("sha256:{:x}", Sha256::digest(&stdout)),
                stderr_bytes: stderr.len() as u64,
                stderr_sha256: format!("sha256:{:x}", Sha256::digest(stderr)),
            };
            let mut terminal = TrialChildResult {
                schema_version: TRIAL_CHILD_PROTOCOL.into(),
                operation_id: "operation".into(),
                child: TrialChildOutcome {
                    exit_code: Some(0),
                    signal: None,
                },
                termination: TrialTermination::Exited,
                elapsed_ms: 1,
                cpu_time_ms: 1,
                peak_memory_bytes: 1,
                peak_pids: 1,
                stdout: String::new(),
                stdout_sha256: header.stdout_sha256.clone(),
                stdout_bytes: header.stdout_bytes,
                stderr: String::new(),
                stderr_sha256: header.stderr_sha256.clone(),
                stderr_bytes: header.stderr_bytes,
                written_bytes: payload.len() as u64,
                written_entries: 1,
                measurement_method: "test_framing_only".into(),
                export_outcome: TrialExportOutcome::Exported,
                export: Some(export),
                guest_cleanup_confirmed: true,
            };
            match fault {
                "wrong_identity" => terminal.operation_id = "foreign".into(),
                "wrong_export" => terminal.export = None,
                "unclean" => terminal.guest_cleanup_confirmed = false,
                "wrong_final_length" => terminal.stdout_bytes += 1,
                "wrong_final_digest" => terminal.stderr_sha256 = header.stdout_sha256.clone(),
                "output_over_limit" => header.stdout_bytes = 1025,
                "output_overflow" => header.stdout_bytes = u64::MAX,
                _ => {}
            }
            let mut wire = Vec::new();
            let append = |wire: &mut Vec<u8>, value: Vec<u8>| {
                wire.extend_from_slice(&(value.len() as u32).to_be_bytes());
                wire.extend_from_slice(&value);
            };
            append(&mut wire, serde_json::to_vec(&header).unwrap());
            wire.extend_from_slice(payload);
            let output_offset = wire.len();
            wire.extend_from_slice(&stdout);
            wire.extend_from_slice(stderr);
            if fault == "altered_raw_output" {
                wire[output_offset] ^= 1;
            }
            if fault != "missing_final" {
                let mut document = serde_json::to_value(&terminal).unwrap();
                if fault == "json_output_substitution" {
                    document["stdout"] = "substituted output".into();
                }
                append(&mut wire, serde_json::to_vec(&document).unwrap());
            }
            if fault == "trailing" {
                wire.push(42);
            }
            let source = root.0.join("wire");
            fs::write(&source, wire).unwrap();
            let child = Command::new("/bin/sh")
                .args(["-c", "cat >/dev/null; cat \"$1\"; exit \"$2\"", "wire-test"])
                .arg(&source)
                .arg(if fault == "exit" { "7" } else { "0" })
                .stdin(Stdio::piped())
                .stdout(Stdio::piped())
                .stderr(Stdio::null())
                .process_group(0)
                .spawn()
                .unwrap();
            let job = GuestJob {
                purpose: GuestPurpose::TrialBuild { materials: vec![] },
                request: serde_json::json!({"limits": {"output_bytes": match fault {
                    "maximum_raw_output" => TRIAL_OUTPUT_MAXIMUM_BYTES,
                    "absolute_output_limit" => TRIAL_OUTPUT_MAXIMUM_BYTES + 1,
                    _ => 1024,
                }}}),
                command: vec!["unused".into()],
                environment: vec![],
                working_directory: "/".into(),
                uid: 1000,
                gid: 1000,
                directories: vec![],
                files: vec![],
            };
            let target = root.0.join("candidate.tar");
            let guard = IoGuard {
                deadline: Instant::now() + Duration::from_secs(5),
                inactivity: None,
                client: None,
                cancelled: &[],
            };
            let result = exchange(
                child,
                &job,
                &[],
                "operation",
                ExportTarget::Candidate {
                    path: &target,
                    maximum_bytes: 1024,
                },
                &guard,
            );
            let expected_success = matches!(fault, "none" | "maximum_raw_output");
            assert_eq!(result.is_ok(), expected_success, "{fault}: {result:?}");
            if expected_success {
                let result = child_result(result.unwrap(), None, None);
                assert!(result.stdout.as_bytes() == stdout.as_slice());
                assert_eq!(result.stderr.as_bytes(), stderr);
                assert_eq!(result.stdout_bytes, stdout.len() as u64);
                assert_eq!(result.stderr_bytes, stderr.len() as u64);
                assert_eq!(fs::read(target).unwrap(), payload);
            } else {
                assert!(!target.exists(), "partial payload retained after {fault}");
            }
        }
    }
}
