//! Closed host side of the private Smol guest capability stream.

use super::*;
use crate::model_relay::InvocationDeadline;
use crate::proxy_transport::{
    connect_private, read_frame as read_proxy_frame, validate_private_socket,
    write_frame as write_proxy_frame,
};
use std::cell::Cell;
use std::process::{ChildStderr, ChildStdin, ChildStdout};
use workstream_checker_guest::{
    GuestIoChannel, GuestIoHeader, GuestJob, MaterialRoot, CAPACITY_EXIT_CODE,
    EXECUTION_FRAME_MAXIMUM, GUEST_IO_PROTOCOL, MAX_JOB_BYTES, MODEL_FRAME_MAXIMUM,
};

const HEADER_MAXIMUM: usize = 4096;
const PROCESS_ERROR_MAXIMUM: usize = 64 * 1024;

pub(super) struct MaterialSource {
    pub(super) manifest: MaterialRoot,
    pub(super) root: PathBuf,
}

pub(crate) struct ProjectMaterials<'a> {
    pub(crate) current: (&'a Path, &'a WorkspaceInventory),
    pub(crate) predecessor: Option<(&'a Path, &'a WorkspaceInventory)>,
}

#[derive(Clone, Default)]
pub(crate) struct ProjectCallbacks {
    pub(crate) model: Option<PathBuf>,
    pub(crate) model_deadline: Option<InvocationDeadline>,
    pub(crate) execution: Option<PathBuf>,
}

pub(super) fn material_source(
    name: &str,
    root: &Path,
    expected: &WorkspaceInventory,
    config: &ServiceConfig,
) -> Result<MaterialSource, String> {
    let observed = inspect_workspace(root, config.sandbox_uid, config.sandbox_gid)?;
    if &observed != expected {
        return Err("material changed before Smol transfer".into());
    }
    Ok(MaterialSource {
        manifest: MaterialRoot {
            name: name.into(),
            directories: observed.directories,
            files: observed
                .files
                .into_iter()
                .map(|file| workstream_checker_guest::MaterialFile {
                    normalized_path: file.normalized_path,
                    byte_count: file.byte_count,
                    sha256: file.sha256,
                    executable: file.executable,
                })
                .collect(),
        },
        root: root.to_owned(),
    })
}

pub(super) fn validate_endpoints(endpoints: &ProjectCallbacks) -> Result<(), String> {
    if endpoints.model_deadline.is_some() && endpoints.model.is_none() {
        return Err("model callback deadline binding invalid".into());
    }
    for path in [endpoints.model.as_deref(), endpoints.execution.as_deref()]
        .into_iter()
        .flatten()
    {
        validate_private_socket(path)?;
    }
    Ok(())
}

pub(super) struct IoGuard<'a> {
    pub(super) deadline: Instant,
    pub(super) inactivity: Option<(Cell<Instant>, Duration)>,
    pub(super) client: Option<&'a UnixStream>,
    pub(super) cancelled: &'a [&'a AtomicBool],
}

impl IoGuard<'_> {
    fn cancel(&self) {
        for cancelled in self.cancelled {
            cancelled.store(true, Ordering::Release);
        }
    }

    fn progressed(&self) {
        if let Some((deadline, timeout)) = &self.inactivity {
            deadline.set(Instant::now() + *timeout);
        }
    }

    pub(super) fn check(&self) -> Result<(), String> {
        if self
            .cancelled
            .iter()
            .any(|cancelled| cancelled.load(Ordering::Acquire))
        {
            return Err("guest session cancelled".into());
        }
        let deadline = self
            .inactivity
            .as_ref()
            .map_or(self.deadline, |(deadline, _)| deadline.get());
        if Instant::now() >= deadline {
            self.cancel();
            return Err("deadline_exceeded".into());
        }
        if self
            .client
            .is_some_and(|client| !client_is_connected(client))
        {
            self.cancel();
            return Err("guest client disconnected".into());
        }
        Ok(())
    }
}

pub(super) fn write_all(
    stream: &mut ChildStdin,
    bytes: &[u8],
    guard: &IoGuard<'_>,
) -> Result<(), String> {
    let mut offset = 0;
    while offset < bytes.len() {
        guard.check()?;
        match stream.write(&bytes[offset..]) {
            Ok(0) => return Err("guest input closed".into()),
            Ok(count) => {
                offset += count;
                guard.progressed();
            }
            Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                thread::sleep(Duration::from_millis(2));
            }
            Err(_) => return Err("guest input failed".into()),
        }
    }
    Ok(())
}

pub(super) fn read_exact(
    stream: &mut ChildStdout,
    bytes: &mut [u8],
    guard: &IoGuard<'_>,
) -> Result<(), String> {
    let mut offset = 0;
    while offset < bytes.len() {
        guard.check()?;
        match stream.read(&mut bytes[offset..]) {
            Ok(0) => return Err("guest output closed".into()),
            Ok(count) => {
                offset += count;
                guard.progressed();
            }
            Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                thread::sleep(Duration::from_millis(2));
            }
            Err(_) => return Err("guest output failed".into()),
        }
    }
    Ok(())
}

fn encode_header(header: &GuestIoHeader) -> Result<Vec<u8>, String> {
    let bytes = serde_json::to_vec(header).map_err(|_| "guest header encoding failed")?;
    if bytes.is_empty() || bytes.len() > HEADER_MAXIMUM {
        return Err("guest header unbounded".into());
    }
    Ok(bytes)
}

fn write_header(
    input: &mut ChildStdin,
    header: &GuestIoHeader,
    guard: &IoGuard<'_>,
) -> Result<(), String> {
    let bytes = encode_header(header)?;
    write_all(input, &(bytes.len() as u32).to_be_bytes(), guard)?;
    write_all(input, &bytes, guard)
}

fn read_header(output: &mut ChildStdout, guard: &IoGuard<'_>) -> Result<GuestIoHeader, String> {
    let mut length = [0_u8; 4];
    read_exact(output, &mut length, guard)?;
    let length = u32::from_be_bytes(length) as usize;
    if length == 0 || length > HEADER_MAXIMUM {
        return Err("guest header unbounded".into());
    }
    let mut bytes = vec![0_u8; length];
    read_exact(output, &mut bytes, guard)?;
    serde_json::from_slice(&bytes).map_err(|_| "guest header invalid".into())
}

pub(super) fn write_job(
    input: &mut ChildStdin,
    job: &GuestJob,
    materials: &[MaterialSource],
    guard: &IoGuard<'_>,
) -> Result<(), String> {
    let bytes = serde_json::to_vec(job).map_err(|_| "guest job invalid")?;
    if bytes.is_empty() || bytes.len() > MAX_JOB_BYTES {
        return Err("guest job too large".into());
    }
    write_all(input, &(bytes.len() as u32).to_be_bytes(), guard)?;
    write_all(input, &bytes, guard)?;
    for material in materials {
        for file in &material.manifest.files {
            let path = material.root.join(&file.normalized_path);
            let mut source = OpenOptions::new()
                .read(true)
                .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
                .open(path)
                .map_err(|_| "material unavailable")?;
            let mut remaining = file.byte_count;
            let mut buffer = [0_u8; 65536];
            while remaining > 0 {
                let count = remaining.min(buffer.len() as u64) as usize;
                source
                    .read_exact(&mut buffer[..count])
                    .map_err(|_| "material transfer truncated")?;
                write_all(input, &buffer[..count], guard)?;
                remaining -= count as u64;
            }
        }
    }
    Ok(())
}

fn endpoint(endpoints: &ProjectCallbacks, channel: GuestIoChannel) -> Option<&Path> {
    match channel {
        GuestIoChannel::Model => endpoints.model.as_deref(),
        GuestIoChannel::Execution => endpoints.execution.as_deref(),
    }
}

fn channel_maximum(channel: GuestIoChannel) -> usize {
    match channel {
        GuestIoChannel::Model => MODEL_FRAME_MAXIMUM,
        GuestIoChannel::Execution => EXECUTION_FRAME_MAXIMUM,
    }
}

#[derive(Default)]
struct RelayConnections {
    model: Option<UnixStream>,
}

fn require_execution_eof(
    stream: &mut UnixStream,
    deadline: Instant,
    cancelled: &AtomicBool,
) -> Result<(), String> {
    let guard = IoGuard {
        deadline,
        inactivity: None,
        client: None,
        cancelled: &[cancelled],
    };
    loop {
        guard.check()?;
        match stream.read(&mut [0_u8; 1]) {
            Ok(0) => return Ok(()),
            Ok(_) => return Err("guest execution relay contains trailing bytes".into()),
            Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                thread::sleep(Duration::from_millis(2));
            }
            Err(error) if error.kind() == std::io::ErrorKind::Interrupted => {}
            Err(_) => return Err("guest execution relay read failed".into()),
        }
    }
}

fn bridge(
    endpoints: &ProjectCallbacks,
    connections: &mut RelayConnections,
    channel: GuestIoChannel,
    request: &[u8],
    deadline: Instant,
    cancelled: &AtomicBool,
) -> Result<Vec<u8>, String> {
    let path = endpoint(endpoints, channel).ok_or("guest capability not entitled")?;
    validate_private_socket(path)?;
    let maximum = channel_maximum(channel);
    if channel == GuestIoChannel::Execution {
        let mut relay = connect_private(path, deadline, cancelled)?;
        write_proxy_frame(&mut relay, request, maximum, deadline, cancelled)?;
        let response = read_proxy_frame(&mut relay, maximum, deadline, cancelled)?;
        require_execution_eof(&mut relay, deadline, cancelled)?;
        return Ok(response);
    }
    let relay = &mut connections.model;
    if relay.is_none() {
        *relay = Some(connect_private(path, deadline, cancelled)?);
    }
    let relay = relay.as_mut().ok_or("guest capability unavailable")?;
    write_proxy_frame(relay, request, maximum, deadline, cancelled)?;
    read_proxy_frame(relay, maximum, deadline, cancelled)
}

fn read_process_errors(mut errors: ChildStderr) -> (Vec<u8>, bool) {
    let mut bytes = Vec::new();
    let mut exceeded = false;
    let mut buffer = [0_u8; 8192];
    loop {
        match errors.read(&mut buffer) {
            Ok(0) => break,
            Ok(count) if bytes.len().saturating_add(count) <= PROCESS_ERROR_MAXIMUM => {
                bytes.extend_from_slice(&buffer[..count]);
            }
            Ok(_) => exceeded = true,
            Err(error) if error.kind() == std::io::ErrorKind::Interrupted => continue,
            Err(_) => {
                exceeded = true;
                break;
            }
        }
    }
    (bytes, exceeded)
}

fn expected_guest_status(oom_kills: u64, output_exceeded: bool, exit_code: Option<i32>) -> i32 {
    if oom_kills > 0 {
        CAPACITY_EXIT_CODE
    } else if output_exceeded {
        125
    } else if exit_code == Some(0) {
        0
    } else {
        125
    }
}

fn prepared_runtime_deadline(
    header: GuestIoHeader,
    budget: ProjectExecutionBudget,
    prepared_at: Instant,
) -> Result<Instant, String> {
    match header {
        GuestIoHeader::Prepared { protocol_version } if protocol_version == GUEST_IO_PROTOCOL => {}
        _ => return Err("guest preparation transition invalid".into()),
    }
    Ok(match budget {
        ProjectExecutionBudget::PreparationSeparated(runtime) => prepared_at + runtime,
        ProjectExecutionBudget::Aggregate(deadline) => deadline,
    })
}

fn reject_duplicate_prepared(header: &GuestIoHeader) -> Result<(), String> {
    if matches!(header, GuestIoHeader::Prepared { .. }) {
        Err("duplicate guest preparation transition".into())
    } else {
        Ok(())
    }
}

#[allow(clippy::too_many_arguments)]
pub(super) fn run_project(
    mut child: Child,
    job: &GuestJob,
    materials: &[MaterialSource],
    endpoints: &ProjectCallbacks,
    execution_budget: ProjectExecutionBudget,
    maximum_output: usize,
    client: &UnixStream,
    cancelled: &AtomicBool,
) -> Result<BoundedCommandOutput, String> {
    let mut input = child.stdin.take().ok_or("guest input unavailable")?;
    let mut output = child.stdout.take().ok_or("guest output unavailable")?;
    let errors = child.stderr.take().ok_or("guest errors unavailable")?;
    set_nonblocking(&input)?;
    set_nonblocking(&output)?;
    let mut error_reader = Some(thread::spawn(move || read_process_errors(errors)));
    let cancellation = [cancelled];
    let (preparation_deadline, progress_timeout) = match execution_budget {
        ProjectExecutionBudget::PreparationSeparated(_) => {
            (Instant::now() + SOCKET_IO_TIMEOUT, Some(SOCKET_IO_TIMEOUT))
        }
        ProjectExecutionBudget::Aggregate(deadline) => (deadline, None),
    };
    let preparation_guard = IoGuard {
        deadline: preparation_deadline,
        inactivity: progress_timeout.map(|timeout| (Cell::new(preparation_deadline), timeout)),
        client: Some(client),
        cancelled: &cancellation,
    };
    let mut child_reaped = false;
    let result = (|| {
        write_job(&mut input, job, materials, &preparation_guard)?;
        let deadline = prepared_runtime_deadline(
            read_header(&mut output, &preparation_guard)?,
            execution_budget,
            Instant::now(),
        )?;
        if let Some(model_deadline) = &endpoints.model_deadline {
            model_deadline.arm(deadline)?;
        }
        let guard = IoGuard {
            deadline,
            inactivity: None,
            client: Some(client),
            cancelled: &cancellation,
        };
        write_header(
            &mut input,
            &GuestIoHeader::Start {
                protocol_version: GUEST_IO_PROTOCOL.into(),
            },
            &guard,
        )?;
        let mut next_sequence = 1_u32;
        let mut relay_connections = RelayConnections::default();
        loop {
            let header = read_header(&mut output, &guard)?;
            reject_duplicate_prepared(&header)?;
            match header {
                GuestIoHeader::Request {
                    protocol_version,
                    sequence,
                    channel,
                    byte_count,
                } => {
                    let maximum = channel_maximum(channel);
                    let byte_count = byte_count as usize;
                    if protocol_version != GUEST_IO_PROTOCOL
                        || sequence != next_sequence
                        || byte_count == 0
                        || byte_count > maximum
                    {
                        return Err("guest capability request invalid".into());
                    }
                    next_sequence = next_sequence
                        .checked_add(1)
                        .ok_or("guest I/O sequence exhausted")?;
                    let mut request = vec![0_u8; byte_count];
                    read_exact(&mut output, &mut request, &guard)?;
                    let response = bridge(
                        endpoints,
                        &mut relay_connections,
                        channel,
                        &request,
                        deadline,
                        cancelled,
                    )?;
                    write_header(
                        &mut input,
                        &GuestIoHeader::Response {
                            protocol_version: GUEST_IO_PROTOCOL.into(),
                            sequence,
                            channel,
                            byte_count: response.len() as u32,
                        },
                        &guard,
                    )?;
                    write_all(&mut input, &response, &guard)?;
                }
                GuestIoHeader::Completed {
                    protocol_version,
                    exit_code,
                    signal,
                    oom_kills,
                    output_exceeded,
                    stdout_bytes,
                    stderr_bytes,
                } => {
                    let stdout_bytes = stdout_bytes as usize;
                    let stderr_bytes = stderr_bytes as usize;
                    if protocol_version != GUEST_IO_PROTOCOL
                        || stdout_bytes > maximum_output
                        || stderr_bytes > PROCESS_ERROR_MAXIMUM
                        || (output_exceeded && (stdout_bytes != 0 || stderr_bytes != 0))
                        || (exit_code.is_some() == signal.is_some())
                    {
                        return Err("guest completion invalid".into());
                    }
                    let mut stdout = vec![0_u8; stdout_bytes];
                    let mut stderr = vec![0_u8; stderr_bytes];
                    read_exact(&mut output, &mut stdout, &guard)?;
                    read_exact(&mut output, &mut stderr, &guard)?;
                    let status = reap_child(&mut child, deadline)?;
                    child_reaped = true;
                    if status.code()
                        != Some(expected_guest_status(oom_kills, output_exceeded, exit_code))
                    {
                        return Err("guest completion status differs".into());
                    }
                    let (process_errors, errors_exceeded) = error_reader
                        .take()
                        .ok_or("guest error reader unavailable")?
                        .join()
                        .map_err(|_| "guest error reader failed")?;
                    if errors_exceeded
                        || stderr.len().saturating_add(process_errors.len()) > PROCESS_ERROR_MAXIMUM
                    {
                        return Err("guest process errors unbounded".into());
                    }
                    stderr.extend_from_slice(&process_errors);
                    if output_exceeded && oom_kills == 0 {
                        return Err("invalid_output".into());
                    }
                    return Ok(BoundedCommandOutput {
                        status,
                        stdout,
                        _stderr: stderr,
                    });
                }
                GuestIoHeader::Response { .. } => {
                    return Err("unsolicited guest capability response".into())
                }
                GuestIoHeader::Prepared { .. } => unreachable!("checked above"),
                GuestIoHeader::Start { .. } => return Err("unsolicited guest project start".into()),
            }
        }
    })();
    if result.is_err() {
        cancelled.store(true, Ordering::Release);
    }
    if result.is_err() && !child_reaped {
        let _ = stop_command_group(&mut child, Instant::now() + SOCKET_IO_TIMEOUT);
    }
    // On failures the reader may still be draining process stderr; joining
    // after process-group stop proves no descriptor remains live.
    if result.is_err() {
        let (_, exceeded) = error_reader
            .take()
            .ok_or("guest error reader unavailable")?
            .join()
            .map_err(|_| "guest error reader failed")?;
        if exceeded {
            return Err("guest process errors unbounded".into());
        }
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::{DirBuilderExt, PermissionsExt};

    #[test]
    fn channel_limits_are_closed_and_distinct() {
        assert_eq!(channel_maximum(GuestIoChannel::Model), 1024 * 1024);
        assert_eq!(channel_maximum(GuestIoChannel::Execution), 4 * 1024 * 1024);
        assert!(endpoint(&ProjectCallbacks::default(), GuestIoChannel::Model).is_none());
        assert!(endpoint(&ProjectCallbacks::default(), GuestIoChannel::Execution).is_none());
    }

    #[test]
    fn headers_are_bounded_closed_protocol_values() {
        let bytes = encode_header(&GuestIoHeader::Request {
            protocol_version: GUEST_IO_PROTOCOL.into(),
            sequence: 1,
            channel: GuestIoChannel::Model,
            byte_count: 7,
        })
        .unwrap();
        assert!(bytes.len() < HEADER_MAXIMUM);
        let decoded: GuestIoHeader = serde_json::from_slice(&bytes).unwrap();
        assert!(matches!(
            decoded,
            GuestIoHeader::Request {
                sequence: 1,
                channel: GuestIoChannel::Model,
                byte_count: 7,
                ..
            }
        ));
    }

    #[test]
    fn duplicate_keys_and_oversized_headers_are_rejected_before_producer_eof() {
        let valid = br#"{"kind":"request","protocol_version":"workstream.smol_guest_io.v1","sequence":1,"channel":"execution","byte_count":1}"#;
        let duplicate = br#"{"kind":"request","protocol_version":"workstream.smol_guest_io.v1","sequence":1,"sequence":2,"channel":"execution","byte_count":1}"#;
        for (length, body, expected) in [
            (valid.len() as u32, valid.as_slice(), None),
            (
                duplicate.len() as u32,
                duplicate.as_slice(),
                Some("guest header invalid"),
            ),
            (
                (HEADER_MAXIMUM + 1) as u32,
                &[][..],
                Some("guest header unbounded"),
            ),
        ] {
            let mut producer = Command::new("/bin/cat")
                .stdin(Stdio::piped())
                .stdout(Stdio::piped())
                .stderr(Stdio::null())
                .spawn()
                .unwrap();
            let mut input = producer.stdin.take().unwrap();
            let mut output = producer.stdout.take().unwrap();
            set_nonblocking(&output).unwrap();
            input.write_all(&length.to_be_bytes()).unwrap();
            input.write_all(body).unwrap();
            input.flush().unwrap();
            // Keep input open: neither invalid frame may wait for its producer
            // to close or consume an oversized body before rejecting it.
            let guard = IoGuard {
                deadline: Instant::now() + Duration::from_secs(2),
                inactivity: None,
                client: None,
                cancelled: &[],
            };
            let result = read_header(&mut output, &guard);
            let producer_still_open = producer.try_wait().unwrap().is_none();
            producer.kill().unwrap();
            producer.wait().unwrap();
            assert!(producer_still_open);
            match expected {
                Some(error) => assert_eq!(result.unwrap_err(), error),
                None => assert!(matches!(
                    result.unwrap(),
                    GuestIoHeader::Request {
                        sequence: 1,
                        channel: GuestIoChannel::Execution,
                        byte_count: 1,
                        ..
                    }
                )),
            }
        }
    }

    #[test]
    fn trusted_completion_codes_distinguish_capacity_and_output_bounds() {
        assert_eq!(expected_guest_status(0, false, Some(0)), 0);
        assert_eq!(expected_guest_status(0, true, Some(0)), 125);
        assert_eq!(expected_guest_status(1, true, None), CAPACITY_EXIT_CODE);
    }

    #[test]
    fn prepared_transition_starts_only_the_declared_runtime_and_is_single_use() {
        let prepared_at = Instant::now();
        let runtime = Duration::from_secs(30);
        assert_eq!(
            prepared_runtime_deadline(
                GuestIoHeader::Prepared {
                    protocol_version: GUEST_IO_PROTOCOL.into(),
                },
                ProjectExecutionBudget::PreparationSeparated(runtime),
                prepared_at,
            )
            .unwrap(),
            prepared_at + runtime,
        );
        let aggregate = prepared_at + Duration::from_secs(5);
        assert_eq!(
            prepared_runtime_deadline(
                GuestIoHeader::Prepared {
                    protocol_version: GUEST_IO_PROTOCOL.into(),
                },
                ProjectExecutionBudget::Aggregate(aggregate),
                prepared_at,
            )
            .unwrap(),
            aggregate,
        );
        assert!(prepared_runtime_deadline(
            GuestIoHeader::Prepared {
                protocol_version: "wrong".into(),
            },
            ProjectExecutionBudget::PreparationSeparated(runtime),
            prepared_at,
        )
        .is_err());
        assert!(prepared_runtime_deadline(
            GuestIoHeader::Completed {
                protocol_version: GUEST_IO_PROTOCOL.into(),
                exit_code: Some(0),
                signal: None,
                oom_kills: 0,
                output_exceeded: false,
                stdout_bytes: 0,
                stderr_bytes: 0,
            },
            ProjectExecutionBudget::PreparationSeparated(runtime),
            prepared_at,
        )
        .is_err());
        assert!(reject_duplicate_prepared(&GuestIoHeader::Prepared {
            protocol_version: GUEST_IO_PROTOCOL.into(),
        })
        .is_err());
    }

    #[test]
    fn guard_cancels_every_owner_on_terminal_deadline() {
        let first = AtomicBool::new(false);
        let second = AtomicBool::new(false);
        let cancellation = [&first, &second];
        let guard = IoGuard {
            deadline: Instant::now(),
            inactivity: None,
            client: None,
            cancelled: &cancellation,
        };
        assert!(guard.check().is_err());
        assert!(first.load(Ordering::Acquire));
        assert!(second.load(Ordering::Acquire));
    }

    #[test]
    fn sequential_execution_relays_close_beside_one_persistent_model_relay() {
        let root = std::env::temp_dir().join(format!(
            "ws-smol-io-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::DirBuilder::new().mode(0o700).create(&root).unwrap();
        let socket = root.join("model.sock");
        let listener = UnixListener::bind(&socket).unwrap();
        fs::set_permissions(&socket, fs::Permissions::from_mode(0o600)).unwrap();
        let execution_socket = root.join("execution.sock");
        let execution_listener = UnixListener::bind(&execution_socket).unwrap();
        fs::set_permissions(&execution_socket, fs::Permissions::from_mode(0o600)).unwrap();
        let deadline = Instant::now() + Duration::from_secs(5);
        let server = thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            let cancelled = AtomicBool::new(false);
            assert_eq!(
                read_proxy_frame(&mut stream, 32, deadline, &cancelled).unwrap(),
                b"first"
            );
            write_proxy_frame(&mut stream, b"one", 32, deadline, &cancelled).unwrap();
            let (mut execution, _) = execution_listener.accept().unwrap();
            assert_eq!(
                read_proxy_frame(&mut execution, 32, deadline, &cancelled).unwrap(),
                b"execute-one"
            );
            write_proxy_frame(&mut execution, b"execution-one", 32, deadline, &cancelled).unwrap();
            drop(execution);
            assert_eq!(
                read_proxy_frame(&mut stream, 32, deadline, &cancelled).unwrap(),
                b"second"
            );
            write_proxy_frame(&mut stream, b"two", 32, deadline, &cancelled).unwrap();
            let (mut execution, _) = execution_listener.accept().unwrap();
            assert_eq!(
                read_proxy_frame(&mut execution, 32, deadline, &cancelled).unwrap(),
                b"execute-two"
            );
            write_proxy_frame(&mut execution, b"execution-two", 32, deadline, &cancelled).unwrap();
        });
        let endpoints = ProjectCallbacks {
            model: Some(socket.clone()),
            model_deadline: None,
            execution: Some(execution_socket.clone()),
        };
        let cancelled = AtomicBool::new(false);
        let mut connections = RelayConnections::default();
        assert_eq!(
            bridge(
                &endpoints,
                &mut connections,
                GuestIoChannel::Model,
                b"first",
                deadline,
                &cancelled,
            )
            .unwrap(),
            b"one"
        );
        assert_eq!(
            bridge(
                &endpoints,
                &mut connections,
                GuestIoChannel::Execution,
                b"execute-one",
                deadline,
                &cancelled,
            )
            .unwrap(),
            b"execution-one"
        );
        assert_eq!(
            bridge(
                &endpoints,
                &mut connections,
                GuestIoChannel::Model,
                b"second",
                deadline,
                &cancelled,
            )
            .unwrap(),
            b"two"
        );
        assert_eq!(
            bridge(
                &endpoints,
                &mut connections,
                GuestIoChannel::Execution,
                b"execute-two",
                deadline,
                &cancelled,
            )
            .unwrap(),
            b"execution-two"
        );
        drop(connections);
        server.join().unwrap();
        fs::remove_file(socket).unwrap();
        fs::remove_file(execution_socket).unwrap();
        fs::remove_dir(root).unwrap();
    }

    #[test]
    fn execution_eof_rejects_trailing_bytes_and_obeys_cancellation_and_deadline() {
        for fault in ["none", "trailing", "cancelled", "deadline"] {
            let (mut reader, mut writer) = UnixStream::pair().unwrap();
            reader.set_nonblocking(true).unwrap();
            if fault == "trailing" {
                writer.write_all(b"extra").unwrap();
            }
            if fault == "none" {
                writer.shutdown(std::net::Shutdown::Write).unwrap();
            }
            let cancelled = AtomicBool::new(fault == "cancelled");
            let deadline = if fault == "deadline" {
                Instant::now()
            } else {
                Instant::now() + Duration::from_secs(1)
            };
            let result = require_execution_eof(&mut reader, deadline, &cancelled);
            assert_eq!(result.is_ok(), fault == "none", "{fault}: {result:?}");
            if fault == "deadline" {
                assert!(cancelled.load(Ordering::Acquire));
            }
        }
    }
}
