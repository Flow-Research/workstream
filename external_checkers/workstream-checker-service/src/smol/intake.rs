//! ART-only prepared session; project execution cannot enter this protocol.
use super::*;
use serde_json::json;
use std::process::{ChildStderr, ChildStdin, ChildStdout};

const PROTOCOL: &str = "trusted_submission_intake.v1";
const COMMAND_BYTES: usize = 4 * 1024 * 1024;
const FRAME_BYTES: usize = 64 * 1024 * 1024;
const ARCHIVE_BYTES: u64 = 512 * 1024 * 1024;
const BASE_RESOURCES: Resources = Resources {
    cpu_millis: 1000,
    memory_bytes: 2 * 1024 * 1024 * 1024,
    storage_gib: 1,
    pids: 128,
};

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct IntakeConfig {
    pub platform_manifest_digest: String,
    pub default_behavior_sha256: String,
    pub storage_envelope: StorageEnvelope,
}

// Qualification belongs to these exact immutable inputs, never to an image tag.
#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct StorageEnvelope {
    pub archive_sha256: String,
    pub config_image_id: String,
    pub smol_binary_sha256: String,
    pub guest_sha256: String,
    pub maximum_entries: u64,
    pub maximum_path_bytes: u64,
    pub maximum_path_depth: u64,
    pub overhead_bytes: u64,
    pub maximum_storage_gib: u64,
}
impl StorageEnvelope {
    fn validate(&self, runtime: &SmolConfig, cache: &CacheEntry) -> Result<(), String> {
        let source = cache.smol.as_ref().ok_or("intake image unavailable")?;
        if [
            (&self.archive_sha256, &source.archive_sha256),
            (&self.config_image_id, &cache.config_image_id),
            (&self.smol_binary_sha256, &runtime.binary_sha256),
            (&self.guest_sha256, &runtime.guest_sha256),
        ]
        .iter()
        .any(|(qualified, actual)| !valid_digest(qualified) || qualified != actual)
            || self.maximum_entries == 0
            || self.maximum_entries > 100_000
            || self.maximum_path_bytes == 0
            || self.maximum_path_depth == 0
            || self.maximum_path_depth > 256
            || self.overhead_bytes == 0
            || self.maximum_storage_gib == 0
            || self
                .maximum_storage_gib
                .checked_add(1)
                .and_then(|gib| gib.checked_mul(1024 * 1024 * 1024))
                .is_none()
        {
            return Err("intake storage qualification differs".into());
        }
        Ok(())
    }
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Envelope {
    protocol_version: String,
    operation: String,
    lease: Option<String>,
    payload: Value,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Preparation {
    phase: String,
    policy_sha256: String,
    limits: Value,
    deadline_ms: u64,
    archive_byte_count: u64,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Archive {
    archive_sha256: String,
    archive_byte_count: u64,
}

fn envelope(bytes: &[u8], lease: Option<&str>) -> Result<Envelope, String> {
    let value: Envelope = serde_json::from_slice(bytes).map_err(|_| "intake protocol invalid")?;
    if value.protocol_version != PROTOCOL
        || value.lease.as_deref() != lease
        || !value.payload.is_object()
    {
        return Err("intake custody differs".into());
    }
    Ok(value)
}
fn empty(value: &Value) -> Result<(), String> {
    if value == &json!({}) {
        Ok(())
    } else {
        Err("intake protocol invalid".into())
    }
}
fn encoded(
    operation: &str,
    lease: Option<&str>,
    status: &str,
    payload: Value,
) -> Result<Vec<u8>, String> {
    serde_json::to_vec(
        &json!({"protocol_version": PROTOCOL, "operation": operation,
        "lease": lease, "status": status, "payload": payload}),
    )
    .map_err(|_| "intake encoding failed".into())
}
fn send(stream: &mut UnixStream, bytes: &[u8], deadline: Instant) -> Result<(), String> {
    if bytes.is_empty() || bytes.len() > FRAME_BYTES {
        return Err("intake frame unbounded".into());
    }
    let mut header = (bytes.len() as u32).to_be_bytes();
    transfer_until(
        stream,
        &mut header,
        deadline,
        |s, b| s.write(b),
        "intake response failed",
    )?;
    let mut body = bytes.to_vec();
    transfer_until(
        stream,
        &mut body,
        deadline,
        |s, b| s.write(b),
        "intake response failed",
    )
}
fn image(config: &ServiceConfig) -> Result<(&IntakeConfig, &CacheEntry), String> {
    let intake = config
        .trusted_intake
        .as_ref()
        .ok_or("trusted intake unavailable")?;
    if config.runtime != "smolvm"
        || config.isolation_mode != "smol-microvm"
        || !valid_digest(&intake.default_behavior_sha256)
    {
        return Err("trusted intake configuration invalid".into());
    }
    let cache = config
        .cache
        .iter()
        .find(|entry| entry.platform_manifest_digest == intake.platform_manifest_digest)
        .ok_or("trusted intake image missing")?;
    intake.storage_envelope.validate(settings(config)?, cache)?;
    inspect_image(cache)?;
    Ok((intake, cache))
}
fn identity(config: &ServiceConfig) -> Result<Value, String> {
    let (intake, cache) = image(config)?;
    Ok(
        json!({"image_digest": cache.platform_manifest_digest, "config_digest": cache.config_image_id,
        "default_behavior_sha256": intake.default_behavior_sha256, "runtime": config.runtime,
        "isolation_mode": config.isolation_mode, "cpu_millis": BASE_RESOURCES.cpu_millis,
        "memory_bytes": BASE_RESOURCES.memory_bytes}),
    )
}
fn preparation(value: &Value) -> Result<Preparation, String> {
    let request: Preparation =
        serde_json::from_value(value.clone()).map_err(|_| "intake preparation invalid")?;
    if !matches!(request.phase.as_str(), "pre_submit" | "post_submit")
        || !valid_digest(&request.policy_sha256)
        || !(1..=7_200_000).contains(&request.deadline_ms)
        // New uploads are capped at 500 MiB by the public API; retained internal
        // artifacts keep their existing 512 MiB transport allowance.
        || !(1..=ARCHIVE_BYTES).contains(&request.archive_byte_count)
    {
        return Err("intake preparation invalid".into());
    }
    // Only bound transport/resource exposure here. Canonical Python ART owns
    // ZIP path, structure, expansion and compression semantics inside the guest.
    let limits = request.limits.as_object().ok_or("intake limits invalid")?;
    let integer_fields = [
        "maximum_entries",
        "maximum_path_bytes",
        "maximum_path_depth",
        "maximum_central_directory_bytes",
        "maximum_entry_bytes",
        "maximum_expanded_bytes",
        "maximum_compression_ratio",
    ];
    if limits.len() != 8
        || integer_fields.iter().any(|name| {
            limits
                .get(*name)
                .and_then(Value::as_u64)
                .filter(|v| *v > 0)
                .is_none()
        })
        || limits["maximum_entries"].as_u64().unwrap() > 100_000
        || limits["maximum_expanded_bytes"].as_u64().unwrap() > ARCHIVE_BYTES
        || limits
            .get("maximum_inspection_seconds")
            .and_then(Value::as_f64)
            .filter(|v| v.is_finite() && *v > 0.0)
            .is_none()
    {
        return Err("intake limits invalid".into());
    }
    Ok(request)
}

fn resources(request: &Preparation, qualified: &StorageEnvelope) -> Result<Resources, String> {
    for (name, maximum) in [
        ("maximum_entries", qualified.maximum_entries),
        ("maximum_path_bytes", qualified.maximum_path_bytes),
        ("maximum_path_depth", qualified.maximum_path_depth),
    ] {
        if request.limits[name]
            .as_u64()
            .ok_or("intake limits invalid")?
            > maximum
        {
            return Err("intake storage qualification exceeded".into());
        }
    }
    let expanded = request.limits["maximum_expanded_bytes"]
        .as_u64()
        .ok_or("intake limits invalid")?;
    let ratio = request.limits["maximum_compression_ratio"]
        .as_u64()
        .ok_or("intake limits invalid")?;
    let expansion = expanded.min(request.archive_byte_count.saturating_mul(ratio));
    let bytes = request
        .archive_byte_count
        .checked_add(expansion)
        .and_then(|value| value.checked_add(qualified.overhead_bytes))
        .ok_or("intake storage overflow")?;
    let storage_gib = bytes.div_ceil(1024 * 1024 * 1024).max(1);
    if storage_gib > qualified.maximum_storage_gib {
        return Err("intake storage qualification exceeded".into());
    }
    Ok(Resources {
        storage_gib,
        ..BASE_RESOURCES
    })
}

fn archive(value: Value, request: &Preparation) -> Result<Archive, String> {
    let archive: Archive = serde_json::from_value(value).map_err(|_| "intake archive invalid")?;
    if !valid_digest(&archive.archive_sha256)
        || archive.archive_byte_count != request.archive_byte_count
    {
        return Err("intake archive differs".into());
    }
    Ok(archive)
}

/// One prepared VM holds its capacity until the guardian confirms exact absence.
pub(crate) fn serve(
    config: &ServiceConfig,
    mut client: UnixStream,
    bytes: &[u8],
) -> Result<(), String> {
    let first = envelope(bytes, None)?;
    let identity = identity(config)?;
    ready(config)?;
    if first.operation == "health" {
        empty(&first.payload)?;
        return send(
            &mut client,
            &encoded("health", None, "ok", identity)?,
            Instant::now() + SOCKET_IO_TIMEOUT,
        );
    }
    if first.operation != "prepare" {
        return Err("intake operation invalid".into());
    }
    let request = preparation(&first.payload)?;
    let (intake, cache) = image(config)?;
    let resources = resources(&request, &intake.storage_envelope)?;
    let deadline = Instant::now() + Duration::from_millis(request.deadline_ms);
    // Intake explicitly allocates a separate 1 GiB writable root overlay.
    let capacity = resource_capacity(resources, Some(1))?;
    let reservation = match reserve_capacity(config, capacity, None) {
        Ok(value) => value,
        Err(_) => {
            return send(
                &mut client,
                &encoded(
                    "prepare",
                    None,
                    "error",
                    json!({"code":"capacity_unavailable"}),
                )?,
                deadline,
            )
        }
    };
    let lease = format!("{}{}", reservation.admission.epoch, random_token()?);
    let mut machine = None;
    for attempt in 0..3 {
        let mut candidate = match Machine::create(config, resources, deadline) {
            Ok(value) => value,
            Err(error) if !error.cleanup_unsettled => {
                return send(
                    &mut client,
                    &encoded(
                        "prepare",
                        None,
                        "error",
                        json!({"code":"runtime_unavailable"}),
                    )?,
                    deadline,
                );
            }
            Err(_) => {
                // Creation may already have persisted a guardian lease. Keep
                // admission occupied until process exit/restart reconciliation.
                std::mem::forget(reservation);
                return Err(UNSETTLED_RESOURCE_ERROR.into());
            }
        };
        match candidate.prepare(cache, resources, Some(1), &client, deadline) {
            Ok(()) => {
                machine = Some(candidate);
                break;
            }
            Err(error) => {
                if candidate.close().is_err() {
                    std::mem::forget(reservation);
                    return Err(UNSETTLED_RESOURCE_ERROR.into());
                }
                // Only known launch/nonzero control failures before archive input
                // are retryable. Custody/enforcement/unknown execution are final.
                if !matches!(
                    error.as_str(),
                    "runtime launch unavailable" | "runtime command failed"
                ) || attempt == 2
                    || !client_is_connected(&client)
                    || Instant::now() >= deadline
                {
                    return send(
                        &mut client,
                        &encoded(
                            "prepare",
                            None,
                            "error",
                            json!({"code":"runtime_unavailable"}),
                        )?,
                        deadline,
                    );
                }
                let delay = Duration::from_millis(100 * (attempt + 1));
                if Instant::now() + delay >= deadline {
                    return Err("deadline_exceeded".into());
                }
                thread::sleep(delay);
            }
        }
    }
    let mut machine = machine.ok_or("intake preparation failed")?;
    let outcome = (|| {
        send(
            &mut client,
            &encoded("prepare", Some(&lease), "ok", identity)?,
            deadline,
        )?;
        session(
            config,
            &mut machine,
            &mut client,
            &lease,
            first.payload,
            &request,
            intake,
            cache,
            deadline,
        )
    })();
    if machine.close().is_err() {
        std::mem::forget(reservation);
        return Err(UNSETTLED_RESOURCE_ERROR.into());
    }
    // A close ACK is the admission handoff: release both RAM and the VM slot
    // before the caller may connect a project checker to a one-slot node.
    drop(reservation);
    match outcome {
        Ok(()) => send(
            &mut client,
            &encoded("close", Some(&lease), "ok", json!({}))?,
            Instant::now() + SOCKET_IO_TIMEOUT,
        ),
        Err(error) => {
            // Error values are fixed controller codes, never archive contents.
            eprintln!("trusted intake session failed: {error}");
            Ok(()) // Lost/invalid sessions cannot claim confirmed cleanup.
        }
    }
}

fn session_client_connected(stream: &UnixStream) -> bool {
    // Unlike the one-shot execute protocol, this session legitimately has ZIP
    // bytes and later commands waiting on its socket while guest I/O runs.
    let mut byte = 0u8;
    let result = unsafe {
        libc::recv(
            stream.as_raw_fd(),
            (&mut byte as *mut u8).cast(),
            1,
            libc::MSG_PEEK | libc::MSG_DONTWAIT,
        )
    };
    result > 0
        || (result < 0
            && matches!(
                std::io::Error::last_os_error().raw_os_error(),
                Some(libc::EAGAIN)
            ))
}

struct GuestIo {
    child: Child,
    input: ChildStdin,
    output: ChildStdout,
    errors: ChildStderr,
    error_bytes: Vec<u8>,
}
impl GuestIo {
    fn start(machine: &Machine) -> Result<Self, String> {
        let mut child = command(
            &machine.lease.runtime,
            &[
                "machine",
                "exec",
                "--name",
                &machine.lease.name,
                "--user",
                "0:0",
                "--interactive",
                "--stream",
                "--",
                "/.workstream-guest",
            ],
            Some(&machine.lease.cgroup()),
        )?
        .stdin(Stdio::piped())
        .spawn()
        .map_err(|_| "intake launch failed")?;
        let input = child.stdin.take().ok_or("intake stdin missing")?;
        let output = child.stdout.take().ok_or("intake stdout missing")?;
        let errors = child.stderr.take().ok_or("intake stderr missing")?;
        let guest = Self {
            child,
            input,
            output,
            errors,
            error_bytes: Vec::new(),
        };
        set_nonblocking(&guest.input)?;
        set_nonblocking(&guest.output)?;
        set_nonblocking(&guest.errors)?;
        Ok(guest)
    }
    fn tick(&mut self, client: &UnixStream, deadline: Instant) -> Result<(), String> {
        if Instant::now() >= deadline || !session_client_connected(client) {
            return Err("intake interrupted".into());
        }
        read_available(&mut self.errors, &mut self.error_bytes, 64 * 1024)?;
        Ok(())
    }
    fn write(
        &mut self,
        bytes: &[u8],
        client: &UnixStream,
        deadline: Instant,
    ) -> Result<(), String> {
        let mut position = 0;
        while position < bytes.len() {
            self.tick(client, deadline)?;
            match self.input.write(&bytes[position..]) {
                Ok(0) => return Err("intake stdin closed".into()),
                Ok(n) => position += n,
                Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                    thread::sleep(Duration::from_millis(2))
                }
                Err(_) => return Err("intake write failed".into()),
            }
        }
        Ok(())
    }
    fn read(
        &mut self,
        bytes: &mut [u8],
        client: &UnixStream,
        deadline: Instant,
    ) -> Result<(), String> {
        let mut position = 0;
        while position < bytes.len() {
            self.tick(client, deadline)?;
            match self.output.read(&mut bytes[position..]) {
                Ok(0) => return Err("intake stdout closed".into()),
                Ok(n) => position += n,
                Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                    thread::sleep(Duration::from_millis(2))
                }
                Err(_) => return Err("intake read failed".into()),
            }
        }
        Ok(())
    }
    fn frame(&mut self, client: &UnixStream, deadline: Instant) -> Result<Vec<u8>, String> {
        let mut header = [0; 4];
        self.read(&mut header, client, deadline)?;
        let length = u32::from_be_bytes(header) as usize;
        if length == 0 || length > FRAME_BYTES {
            return Err("intake output unbounded".into());
        }
        let mut bytes = vec![0; length];
        self.read(&mut bytes, client, deadline)?;
        Ok(bytes)
    }
    fn write_frame(
        &mut self,
        bytes: &[u8],
        client: &UnixStream,
        deadline: Instant,
    ) -> Result<(), String> {
        self.write(&(bytes.len() as u32).to_be_bytes(), client, deadline)?;
        self.write(bytes, client, deadline)
    }
}
impl Drop for GuestIo {
    fn drop(&mut self) {
        let _ = stop_command_group(&mut self.child, Instant::now() + SOCKET_IO_TIMEOUT);
    }
}
fn response(bytes: &[u8], operation: &str, lease: &str) -> Result<Value, String> {
    let value: Value = serde_json::from_slice(bytes).map_err(|_| "intake output invalid")?;
    let object = value.as_object().ok_or("intake output invalid")?;
    if object.len() != 5
        || value["protocol_version"] != PROTOCOL
        || value["operation"] != operation
        || value["lease"] != lease
        || value["status"] != "ok"
        || !value["payload"].is_object()
    {
        return Err("intake receipt invalid".into());
    }
    Ok(value["payload"].clone())
}

#[allow(clippy::too_many_arguments)]
fn session(
    config: &ServiceConfig,
    machine: &mut Machine,
    client: &mut UnixStream,
    lease: &str,
    preparation: Value,
    request: &Preparation,
    intake: &IntakeConfig,
    cache: &CacheEntry,
    deadline: Instant,
) -> Result<(), String> {
    let mut state = "prepared";
    let mut guest: Option<GuestIo> = None;
    let mut files: Vec<Value> = Vec::new();
    loop {
        let bytes = read_frame_until(client, COMMAND_BYTES, deadline)?;
        let command = envelope(&bytes, Some(lease))?;
        if command.operation == "close" {
            empty(&command.payload)?;
            return Ok(());
        }
        match (command.operation.as_str(), state) {
            ("inspect", "prepared") => {
                // Reject substitution before starting guest I/O or accepting ZIP bytes.
                let archive = archive(command.payload, request)?;
                let source = cache.smol.as_ref().ok_or("intake image unavailable")?;
                let image: Value = serde_json::from_slice(&read_bounded_file(
                    &source.image_config,
                    MAX_REQUEST_BYTES,
                )?)
                .map_err(|_| "intake image invalid")?;
                let job = GuestJob {
                    purpose: GuestPurpose::TrustedIntake {
                        cpu_millis: BASE_RESOURCES.cpu_millis,
                        memory_bytes: BASE_RESOURCES.memory_bytes,
                    },
                    request: json!({"lease":lease, "preparation":preparation, "archive_sha256":archive.archive_sha256,
                                   "archive_byte_count":archive.archive_byte_count}),
                    command: image_command(&image)?,
                    environment: image["config"]["Env"]
                        .as_array()
                        .ok_or("intake environment invalid")?
                        .iter()
                        .map(|v| {
                            v.as_str()
                                .map(str::to_owned)
                                .ok_or("intake environment invalid")
                        })
                        .collect::<Result<Vec<_>, _>>()?,
                    working_directory: image["config"]["WorkingDir"]
                        .as_str()
                        .unwrap_or("/")
                        .to_owned(),
                    uid: config.sandbox_uid,
                    gid: config.sandbox_gid,
                    directories: vec![],
                    files: vec![MaterialFile {
                        normalized_path: "archive.zip".into(),
                        byte_count: archive.archive_byte_count,
                        sha256: archive.archive_sha256.clone(),
                        executable: false,
                    }],
                };
                let mut process = GuestIo::start(machine)?;
                process.write_frame(
                    &serde_json::to_vec(&job).map_err(|_| "intake bootstrap invalid")?,
                    client,
                    deadline,
                )?;
                let mut remaining = archive.archive_byte_count;
                let mut digest = Sha256::new();
                let mut buffer = vec![0; 65536];
                while remaining > 0 {
                    let count = remaining.min(buffer.len() as u64) as usize;
                    transfer_until(
                        client,
                        &mut buffer[..count],
                        deadline,
                        |s, b| s.read(b),
                        "intake upload interrupted",
                    )?;
                    digest.update(&buffer[..count]);
                    process.write(&buffer[..count], client, deadline)?;
                    remaining -= count as u64;
                }
                if format!("sha256:{:x}", digest.finalize()) != archive.archive_sha256 {
                    return Err("intake archive differs".into());
                }
                let ready = response(&process.frame(client, deadline)?, "ready", lease)?;
                if ready != json!({"default_behavior_sha256":intake.default_behavior_sha256}) {
                    return Err("intake behavior differs".into());
                }
                let receipt = process.frame(client, deadline)?;
                // Canonical work rejections are transported unchanged, but cannot
                // turn into exported files or a default result in this session.
                if let Ok(payload) = response(&receipt, "inspect", lease) {
                    if payload["archive_sha256"] != archive.archive_sha256
                        || payload["archive_byte_count"] != archive.archive_byte_count
                    {
                        return Err("intake archive receipt differs".into());
                    }
                    let entries = payload["inspection"]["entries"]
                        .as_array()
                        .ok_or("intake inventory invalid")?;
                    if entries.len() > request.limits["maximum_entries"].as_u64().unwrap() as usize
                    {
                        return Err("intake inventory unbounded".into());
                    }
                    files = entries
                        .iter()
                        .filter(|v| v["entry_type"] == "file")
                        .cloned()
                        .collect();
                    let total = files
                        .iter()
                        .try_fold(0u64, |sum, v| sum.checked_add(v["byte_count"].as_u64()?))
                        .ok_or("intake inventory invalid")?;
                    if total > ARCHIVE_BYTES {
                        return Err("intake export unbounded".into());
                    }
                    state = "inspected";
                } else {
                    let rejected: Value =
                        serde_json::from_slice(&receipt).map_err(|_| "intake rejection invalid")?;
                    if rejected["protocol_version"] != PROTOCOL
                        || rejected["lease"] != lease
                        || rejected["operation"] != "inspect"
                        || rejected["status"] != "error"
                    {
                        return Err("intake rejection invalid".into());
                    }
                    state = "rejected";
                }
                send(client, &receipt, deadline)?;
                guest = Some(process);
            }
            ("export", "inspected") => {
                empty(&command.payload)?;
                let process = guest.as_mut().ok_or("intake guest missing")?;
                process.write_frame(&bytes, client, deadline)?;
                for entry in &files {
                    let receipt = process.frame(client, deadline)?;
                    if response(&receipt, "file", lease)? != *entry {
                        return Err("intake export differs".into());
                    }
                    send(client, &receipt, deadline)?;
                    let mut remaining =
                        entry["byte_count"].as_u64().ok_or("intake size invalid")?;
                    let mut buffer = vec![0; 65536];
                    let mut digest = Sha256::new();
                    while remaining > 0 {
                        let count = remaining.min(buffer.len() as u64) as usize;
                        process.read(&mut buffer[..count], client, deadline)?;
                        digest.update(&buffer[..count]);
                        transfer_until(
                            client,
                            &mut buffer[..count],
                            deadline,
                            |s, b| s.write(b),
                            "intake export interrupted",
                        )?;
                        remaining -= count as u64;
                    }
                    if entry["sha256"] != format!("sha256:{:x}", digest.finalize()) {
                        return Err("intake file differs".into());
                    }
                }
                let receipt = process.frame(client, deadline)?;
                empty(&response(&receipt, "export", lease)?)?;
                send(client, &receipt, deadline)?;
                state = "exported";
            }
            ("default", "exported") if request.phase == "pre_submit" => {
                if command.payload["binding"]["policy_sha256"] != request.policy_sha256 {
                    return Err("intake policy differs".into());
                }
                let process = guest.as_mut().ok_or("intake guest missing")?;
                process.write_frame(&bytes, client, deadline)?;
                let receipt = process.frame(client, deadline)?;
                response(&receipt, "default", lease)?;
                if receipt.len() > MAX_RESPONSE_BYTES {
                    return Err("intake default unbounded".into());
                }
                send(client, &receipt, deadline)?;
                state = "evaluated";
            }
            _ => return Err("intake operation out of sequence".into()),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    const GIB: u64 = 1024 * 1024 * 1024;

    fn qualification() -> StorageEnvelope {
        // Synthetic test qualification only; never a production default.
        StorageEnvelope {
            archive_sha256: format!("sha256:{}", "a".repeat(64)),
            config_image_id: format!("sha256:{}", "b".repeat(64)),
            smol_binary_sha256: format!("sha256:{}", "c".repeat(64)),
            guest_sha256: format!("sha256:{}", "d".repeat(64)),
            maximum_entries: 2000,
            maximum_path_bytes: 1024,
            maximum_path_depth: 32,
            overhead_bytes: 1,
            maximum_storage_gib: 4,
        }
    }

    fn preparation_value(size: u64) -> Value {
        json!({
            "phase":"pre_submit", "policy_sha256":format!("sha256:{}", "a".repeat(64)),
            "deadline_ms": 30000, "archive_byte_count": size,
            "limits": {
                "maximum_entries": 2000, "maximum_path_bytes": 1024,
                "maximum_path_depth": 32, "maximum_central_directory_bytes": 8388608,
                "maximum_entry_bytes": 134217728, "maximum_expanded_bytes": ARCHIVE_BYTES,
                "maximum_compression_ratio": 100, "maximum_inspection_seconds": 300.0,
            }
        })
    }

    #[test]
    fn storage_formula_rounds_at_gib_boundaries_and_bounds_expansion() {
        let mut qualified = qualification();
        let mut value = preparation_value(1);
        value["limits"]["maximum_compression_ratio"] = json!(1);
        let request = preparation(&value).unwrap();
        assert_eq!(resources(&request, &qualified).unwrap().storage_gib, 1);
        qualified.overhead_bytes = GIB - 2;
        assert_eq!(resources(&request, &qualified).unwrap().storage_gib, 1);
        qualified.overhead_bytes += 1;
        assert_eq!(resources(&request, &qualified).unwrap().storage_gib, 2);
        qualified.overhead_bytes = 1;
        let request = preparation(&preparation_value(ARCHIVE_BYTES)).unwrap();
        assert_eq!(resources(&request, &qualified).unwrap().storage_gib, 2);
        // Saturating multiplication still uses the smaller expanded-content cap.
        value = preparation_value(2);
        value["limits"]["maximum_compression_ratio"] = json!(u64::MAX);
        let request = preparation(&value).unwrap();
        assert_eq!(resources(&request, &qualified).unwrap().storage_gib, 1);
        qualified.overhead_bytes = u64::MAX;
        assert_eq!(
            resources(&request, &qualified).err().unwrap(),
            "intake storage overflow"
        );
    }

    #[test]
    fn request_cannot_exceed_qualified_storage_or_inventory_envelope() {
        let mut qualified = qualification();
        let request = preparation(&preparation_value(ARCHIVE_BYTES)).unwrap();
        qualified.maximum_storage_gib = 1;
        assert!(resources(&request, &qualified).is_err());
        qualified.maximum_storage_gib = 4;
        for field in [
            "maximum_entries",
            "maximum_path_bytes",
            "maximum_path_depth",
        ] {
            let mut value = preparation_value(1);
            let maximum = value["limits"][field].as_u64().unwrap();
            value["limits"][field] = json!(maximum + 1);
            assert!(resources(&preparation(&value).unwrap(), &qualified).is_err());
        }
    }

    #[test]
    fn prepare_binds_positive_retained_archive_size_and_inspect_cannot_substitute_it() {
        for size in [0, ARCHIVE_BYTES + 1] {
            assert!(preparation(&preparation_value(size)).is_err());
        }
        let mut value = preparation_value(ARCHIVE_BYTES);
        value.as_object_mut().unwrap().remove("archive_byte_count");
        assert!(preparation(&value).is_err());
        let request = preparation(&preparation_value(ARCHIVE_BYTES)).unwrap();
        let digest = format!("sha256:{}", "a".repeat(64));
        assert!(archive(
            json!({"archive_sha256":digest, "archive_byte_count":ARCHIVE_BYTES}),
            &request
        )
        .is_ok());
        for size in [0, 1, ARCHIVE_BYTES - 1, ARCHIVE_BYTES + 1] {
            assert!(archive(
                json!({"archive_sha256":digest, "archive_byte_count":size}),
                &request
            )
            .is_err());
        }
    }

    #[test]
    fn qualification_is_required_closed_and_bound_to_all_four_immutable_inputs() {
        assert!(serde_json::from_value::<IntakeConfig>(json!({
            "platform_manifest_digest":format!("sha256:{}", "a".repeat(64)),
            "default_behavior_sha256":format!("sha256:{}", "b".repeat(64)),
        }))
        .is_err());
        let (root, mut config) = super::super::super::tests::test_config();
        let qualified = qualification();
        let runtime = SmolConfig {
            binary: root.join("smol"),
            binary_sha256: qualified.smol_binary_sha256.clone(),
            home: root.join("home"),
            guest_binary: root.join("guest"),
            guest_sha256: qualified.guest_sha256.clone(),
            cgroup_root: root.join("group"),
            maximum_parallel: 1,
            maximum_storage_bytes: 8 * GIB,
        };
        let cache = &mut config.cache[0];
        cache.config_image_id = qualified.config_image_id.clone();
        cache.smol = Some(SmolImage {
            archive: root.join("intake.tar"),
            archive_sha256: qualified.archive_sha256.clone(),
            image_config: root.join("intake.json"),
        });
        assert!(qualified.validate(&runtime, cache).is_ok());
        for index in 0..4 {
            let mut stale = qualified.clone();
            let field = match index {
                0 => &mut stale.archive_sha256,
                1 => &mut stale.config_image_id,
                2 => &mut stale.smol_binary_sha256,
                _ => &mut stale.guest_sha256,
            };
            *field = format!("sha256:{}", "e".repeat(64));
            assert!(stale.validate(&runtime, cache).is_err());
        }
        let value = json!({
            "archive_sha256":qualified.archive_sha256, "config_image_id":qualified.config_image_id,
            "smol_binary_sha256":qualified.smol_binary_sha256, "guest_sha256":qualified.guest_sha256,
            "maximum_entries":2000, "maximum_path_bytes":1024, "maximum_path_depth":32,
            "overhead_bytes":1, "maximum_storage_gib":4, "unexpected":true,
        });
        assert!(serde_json::from_value::<StorageEnvelope>(value).is_err());
        for (entries, path_bytes, depth, overhead, storage) in [
            (0, 1024, 32, 1, 4),
            (2000, 0, 32, 1, 4),
            (2000, 1024, 0, 1, 4),
            (2000, 1024, 257, 1, 4),
            (2000, 1024, 32, 0, 4),
            (2000, 1024, 32, 1, 0),
            (2000, 1024, 32, 1, u64::MAX),
        ] {
            let bad = StorageEnvelope {
                maximum_entries: entries,
                maximum_path_bytes: path_bytes,
                maximum_path_depth: depth,
                overhead_bytes: overhead,
                maximum_storage_gib: storage,
                ..qualified.clone()
            };
            assert!(bad.validate(&runtime, cache).is_err());
        }
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn admission_charges_overlay_and_releases_the_whole_charge_after_cleanup_handoff() {
        let resources = resources(
            &preparation(&preparation_value(1)).unwrap(),
            &qualification(),
        )
        .unwrap();
        let data_only = resource_capacity(resources, None).unwrap();
        let intake = resource_capacity(resources, Some(1)).unwrap();
        assert_eq!(intake.storage_bytes, data_only.storage_bytes + GIB);
        assert_eq!(intake.slots, data_only.slots);
        assert_eq!(intake.memory_bytes, data_only.memory_bytes);
        let insufficient = Arc::new(Admission::new(data_only, "a".repeat(64)).unwrap());
        assert!(insufficient.reserve(intake, None).is_err());
        let node = Arc::new(Admission::new(intake, "b".repeat(64)).unwrap());
        let reservation = node.reserve(intake, None).unwrap();
        assert_eq!(node.reserved_storage_bytes().unwrap(), intake.storage_bytes);
        assert!(node.reserve(intake, None).is_err());
        drop(reservation);
        assert_eq!(node.reserved_storage_bytes().unwrap(), 0);
        assert!(node.reserve(intake, None).is_ok());
        assert!(resource_capacity(
            Resources {
                storage_gib: u64::MAX,
                ..resources
            },
            Some(1)
        )
        .is_err());
    }

    #[test]
    fn pending_upload_bytes_are_not_a_disconnected_intake_client() {
        let (mut sender, mut receiver) = UnixStream::pair().unwrap();
        assert!(session_client_connected(&receiver));
        sender.write_all(b"zip input").unwrap();
        assert!(session_client_connected(&receiver));
        // The project execute helper must still reject unsolicited trailing data.
        assert!(!client_is_connected(&receiver));
        let mut bytes = [0; 9];
        receiver.read_exact(&mut bytes).unwrap();
        assert_eq!(&bytes, b"zip input");
        drop(sender);
        assert!(!session_client_connected(&receiver));
    }
}
