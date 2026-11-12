//! Validate configured PRE identities and bounds before allocation or source IO.
use super::*;
use workstream_checker_guest::pre_bootstrap::{PreBootstrapJob, PreBootstrapLimits};
use workstream_checker_guest::trusted_root::{RootDescriptor, RootLimits};

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Config {
    pub profile: Value,
    pub profile_sha256: String,
    pub root_bundle: PathBuf,
    pub root: RootDescriptor,
    pub root_limits: RootLimits,
    pub limits: PreBootstrapLimits,
    pub smol_binary_sha256: String,
    pub guest_sha256: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Header {
    protocol_version: String,
    operation: String,
    reservation: Value,
    request_digest: String,
    lease_id: String,
    lease_generation: u64,
    lease_expires_at: String,
}

pub(super) struct Prepared<'a> {
    pub cache: &'a CacheEntry,
    pub root_bundle: File,
    pub job: PreBootstrapJob,
    pub invocation: Invocation,
    pub resources: Resources,
    pub overlay_gib: u64,
    pub deadline: Instant,
}

fn text<'a>(value: &'a Value, key: &str) -> Result<&'a str, String> {
    value[key].as_str().ok_or_else(|| "PRE text invalid".into())
}
fn number(value: &Value, key: &str) -> Result<u64, String> {
    value[key]
        .as_u64()
        .filter(|value| *value > 0)
        .ok_or_else(|| "PRE bound invalid".into())
}
fn closed(value: &Value, fields: &[&str]) -> Result<(), String> {
    let object = value.as_object().ok_or("PRE object invalid")?;
    if object.len() != fields.len() || fields.iter().any(|field| !object.contains_key(*field)) {
        return Err("PRE object fields differ".into());
    }
    Ok(())
}
fn sum(values: impl IntoIterator<Item = u64>) -> Result<u64, String> {
    values.into_iter().try_fold(0_u64, |total, value| {
        total
            .checked_add(value)
            .ok_or("PRE capacity overflow".into())
    })
}
fn hash(value: &Value) -> Result<String, String> {
    canonical_hash(value).map_err(|_| "PRE identity invalid".into())
}

// Backend durable UTC timestamps are serialized with Z or +00:00. Reject
// normalization (February 30, leap seconds, excess precision), rather than let
// libc silently move an invalid timestamp into a later admission window.
fn utc_millis(value: &str) -> Result<u64, String> {
    let body = value
        .strip_suffix('Z')
        .or_else(|| value.strip_suffix("+00:00"))
        .ok_or("PRE timestamp must be UTC")?;
    let bytes = body.as_bytes();
    if bytes.len() < 19
        || bytes[4] != b'-'
        || bytes[7] != b'-'
        || bytes[10] != b'T'
        || bytes[13] != b':'
        || bytes[16] != b':'
    {
        return Err("PRE timestamp invalid".into());
    }
    let parse = |start: usize, end: usize| -> Result<i32, String> {
        let part = &bytes[start..end];
        if !part.iter().all(u8::is_ascii_digit) {
            return Err("PRE timestamp invalid".into());
        }
        Ok(part
            .iter()
            .fold(0, |total, digit| total * 10 + i32::from(digit - b'0')))
    };
    let mut tm: libc::tm = unsafe { std::mem::zeroed() };
    tm.tm_year = parse(0, 4)? - 1900;
    tm.tm_mon = parse(5, 7)? - 1;
    tm.tm_mday = parse(8, 10)?;
    tm.tm_hour = parse(11, 13)?;
    tm.tm_min = parse(14, 16)?;
    tm.tm_sec = parse(17, 19)?;
    let original = (
        tm.tm_year, tm.tm_mon, tm.tm_mday, tm.tm_hour, tm.tm_min, tm.tm_sec,
    );
    let seconds = unsafe { libc::timegm(&mut tm) };
    if seconds < 0
        || original
            != (
                tm.tm_year, tm.tm_mon, tm.tm_mday, tm.tm_hour, tm.tm_min, tm.tm_sec,
            )
    {
        return Err("PRE timestamp invalid".into());
    }
    let fraction = &bytes[19..];
    let millis = if fraction.is_empty() {
        0
    } else {
        if fraction[0] != b'.'
            || !(2..=7).contains(&fraction.len())
            || !fraction[1..].iter().all(u8::is_ascii_digit)
        {
            return Err("PRE timestamp invalid".into());
        }
        fraction[1..]
            .iter()
            .take(3)
            .chain(std::iter::repeat(&b'0'))
            .take(3)
            .fold(0_u64, |total, digit| total * 10 + u64::from(digit - b'0'))
    };
    (seconds as u64)
        .checked_mul(1000)
        .and_then(|value| value.checked_add(millis))
        .ok_or("PRE timestamp overflow".into())
}

pub(super) fn prepare<'a>(config: &'a ServiceConfig, bytes: &[u8]) -> Result<Prepared<'a>, String> {
    let started = Instant::now();
    let wall = now_ms()?;
    if bytes.is_empty() || bytes.len() > 2 * 1024 * 1024 {
        return Err("PRE header unbounded".into());
    }
    let header: Header = serde_json::from_slice(bytes).map_err(|_| "PRE header invalid")?;
    let configured = config.pre.as_ref().ok_or("PRE configuration unavailable")?;
    configured.limits.validate()?;
    let runtime = settings(config)?;
    let reservation = &header.reservation;
    closed(
        reservation,
        &[
            "schema_version",
            "actor_profile_id",
            "identity_link_id",
            "project_id",
            "task_id",
            "assignment_id",
            "attempt_id",
            "idempotency_key",
            "source",
            "source_sha256",
            "metadata_sha256",
            "locked_context_sha256",
            "foreground_lease_id",
            "foreground_lease_generation",
            "pre_deadline_at",
            "policy",
            "default_context",
            "runtime_profile",
            "admission_lineage",
        ],
    )?;
    let profile = &reservation["runtime_profile"];
    closed(
        profile,
        &[
            "profile_id",
            "platform_root_sha256",
            "cpu_millis",
            "memory_bytes",
            "temporary_disk_bytes",
            "maximum_processes",
            "maximum_output_bytes",
            "maximum_log_bytes",
            "aggregate_deadline_ms",
            "archive_limits",
        ],
    )?;
    let archive_limits = &profile["archive_limits"];
    closed(
        archive_limits,
        &[
            "maximum_central_directory_bytes",
            "maximum_compression_ratio",
            "maximum_entries",
            "maximum_entry_bytes",
            "maximum_expanded_bytes",
            "maximum_inspection_seconds",
            "maximum_path_bytes",
            "maximum_path_depth",
        ],
    )?;
    for field in [
        "maximum_central_directory_bytes",
        "maximum_compression_ratio",
        "maximum_entries",
        "maximum_entry_bytes",
        "maximum_expanded_bytes",
        "maximum_path_bytes",
        "maximum_path_depth",
    ] {
        number(archive_limits, field)?;
    }
    let inspection = archive_limits["maximum_inspection_seconds"]
        .as_f64()
        .ok_or("PRE inspection bound invalid")?;
    let profile_id = text(profile, "profile_id")?;
    if !inspection.is_finite()
        || inspection <= 0.0
        || profile_id.is_empty()
        || profile_id.len() > 100
        || !profile_id.bytes().all(|byte| {
            byte.is_ascii_lowercase() || byte.is_ascii_digit() || matches!(byte, b'_' | b'-')
        })
    {
        return Err("PRE profile invalid".into());
    }
    let source = &reservation["source"];
    closed(
        source,
        &[
            "location",
            "media_type",
            "provider_generation",
            "raw_byte_count",
            "raw_sha256",
            "sealed_upload_fence",
        ],
    )?;
    closed(
        &source["location"],
        &[
            "namespace_fingerprint",
            "namespace_id",
            "operation_id",
            "provider_profile",
        ],
    )?;
    let mut source_body = source.as_object().unwrap().clone();
    source_body.insert(
        "schema_version".into(),
        serde_json::json!("workstream.sealed_submission_source.v1"),
    );
    let profile_digest = hash(profile)?;
    if header.protocol_version != "external_checker_service.v1"
        || header.operation != "execute_pre"
        || reservation["schema_version"] != "workstream.selected_pre_submit_reservation.v2"
        || hash(reservation)? != header.request_digest
        || hash(&Value::Object(source_body))? != text(reservation, "source_sha256")?
        || profile != &configured.profile
        || profile_digest != configured.profile_sha256
        || config.runtime != "smolvm"
        || config.isolation_mode != "smol-microvm"
        || configured.smol_binary_sha256 != runtime.binary_sha256
        || configured.guest_sha256 != runtime.guest_sha256
        || !valid_digest(&configured.smol_binary_sha256)
        || !valid_digest(&configured.guest_sha256)
        || profile["platform_root_sha256"] != configured.root.bundle_sha256
        || source["media_type"] != "application/zip"
        || !valid_digest(text(source, "raw_sha256")?)
        || text(source, "provider_generation")?.is_empty()
        || number(reservation, "foreground_lease_generation")?
            < number(source, "sealed_upload_fence")?
        || number(source, "raw_byte_count")? > configured.limits.maximum_source_bytes
    {
        return Err("PRE configured identity differs".into());
    }
    let remaining = utc_millis(&header.lease_expires_at)?
        .min(utc_millis(text(reservation, "pre_deadline_at")?)?)
        .checked_sub(wall)
        .filter(|value| *value > 0)
        .ok_or("deadline_exceeded")?;
    let budget = number(profile, "aggregate_deadline_ms")?;
    if !(100..=14_400_000).contains(&budget) || configured.limits.cleanup_timeout_ms > budget {
        return Err("PRE deadline bound differs".into());
    }
    let deadline = started + Duration::from_millis(remaining.min(budget));
    let policy = &reservation["policy"];
    closed(
        policy,
        &[
            "schema_version",
            "workstream_default",
            "entries",
            "policy_sha256",
        ],
    )?;
    let mut policy_body = policy.as_object().unwrap().clone();
    policy_body.remove("policy_sha256");
    if policy["schema_version"] != "external_pre_submit_policy.v1"
        || hash(&Value::Object(policy_body))? != text(policy, "policy_sha256")?
    {
        return Err("PRE policy digest differs".into());
    }
    let entries = reservation["policy"]["entries"]
        .as_array()
        .ok_or("PRE policy invalid")?;
    if entries.len() != 1 {
        return Err("PRE cardinality invalid".into());
    }
    let selected = &entries[0];
    closed(
        selected,
        &[
            "stage",
            "requirement_id",
            "configuration",
            "configuration_sha256",
            "registry",
        ],
    )?;
    let registry = &selected["registry"];
    workstream_checker_sdk::validate_registry(
        registry.as_object().ok_or("PRE registry invalid")?,
        "pre_submit",
    )
    .map_err(|_| "PRE registry invalid")?;
    if selected["stage"] != "pre_submit"
        || registry["phase"] != "pre_submit"
        || hash(&selected["configuration"])? != text(selected, "configuration_sha256")?
        || reservation["policy"]["workstream_default"]["behavior_sha256"]
            != configured.root.default_behavior_sha256
    {
        return Err("PRE selection differs".into());
    }
    let matching: Vec<_> = config
        .cache
        .iter()
        .filter(|entry| {
            Some(entry.platform_manifest_digest.as_str()) == registry["image_digest"].as_str()
        })
        .collect();
    if matching.len() != 1 {
        return Err("PRE image unavailable or ambiguous".into());
    }
    let cache = matching[0];
    if cache.operating_system != config.operating_system
        || cache.architecture != config.architecture
    {
        return Err("PRE image platform differs".into());
    }
    let image = image_configuration(cache)?;
    let limits = configured.limits;
    for (field, actual) in [
        (
            "cpu_millis",
            sum([
                limits.control.cpu_millis,
                limits.worker.cpu_millis,
                limits.project.cpu_millis,
            ])?,
        ),
        (
            "memory_bytes",
            sum([
                limits.control.memory_bytes,
                limits.worker.memory_bytes,
                limits.project.memory_bytes,
            ])?,
        ),
        (
            "maximum_processes",
            sum([
                limits.control.processes,
                limits.worker.processes,
                limits.project.processes,
            ])?,
        ),
        ("maximum_output_bytes", limits.maximum_output_bytes as u64),
        ("maximum_log_bytes", limits.maximum_log_bytes as u64),
    ] {
        if actual > number(profile, field)? {
            return Err("PRE partitions exceed profile".into());
        }
    }
    if configured.root.schema_version != "workstream.trusted_root.v1"
        || [
            &configured.root.bundle_sha256,
            &configured.root.platform_manifest_digest,
            &configured.root.config_image_id,
            &configured.root.default_behavior_sha256,
        ]
        .into_iter()
        .any(|value| !valid_digest(value))
        || number(profile, "cpu_millis")?.checked_mul(100).is_none()
        || !configured.root_bundle.is_absolute()
        || configured.root.bundle_byte_count == 0
        || configured.root.bundle_byte_count > configured.root_limits.maximum_bundle_bytes
        || configured.root.expanded_bytes == 0
        || configured.root.expanded_bytes > configured.root_limits.maximum_root_bytes
        || configured.root.entries == 0
        || configured.root.entries > configured.root_limits.maximum_entries
    {
        return Err("PRE root bound differs".into());
    }
    let root_bundle = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK)
        .open(&configured.root_bundle)
        .map_err(|_| "PRE root unavailable")?;
    let root_metadata = root_bundle.metadata().map_err(|_| "PRE root unavailable")?;
    if !root_metadata.is_file()
        || root_metadata.mode() & 0o022 != 0
        || root_metadata.len() != configured.root.bundle_byte_count
    {
        return Err("PRE root custody differs".into());
    }
    let storage = sum([
        configured.root.bundle_byte_count,
        configured.root.expanded_bytes,
        number(source, "raw_byte_count")?,
        number(&profile["archive_limits"], "maximum_expanded_bytes")?,
        limits.worker_scratch_bytes,
        limits.project_scratch_bytes,
        limits.filesystem_overhead_bytes,
    ])?;
    if sum([storage, limits.overlay_bytes])? > number(profile, "temporary_disk_bytes")? {
        return Err("PRE disk exceeds profile".into());
    }
    let gib = |bytes: u64| {
        bytes
            .checked_add((1 << 30) - 1)
            .map(|n| n / (1 << 30))
            .ok_or("PRE capacity overflow")
    };
    let resources = Resources {
        cpu_millis: number(profile, "cpu_millis")?,
        memory_bytes: number(profile, "memory_bytes")?,
        pids: number(profile, "maximum_processes")?,
        storage_gib: gib(storage)?,
    };
    let overlay_gib = gib(limits.overlay_bytes)?;
    resource_capacity(resources, Some(overlay_gib))?;
    let invocation = Invocation {
        operation: Operation::ExecutePre,
        run_id: text(reservation, "attempt_id")?.into(),
        source_operation_id: text(&source["location"], "operation_id")?.into(),
        request_digest: header.request_digest,
        source_sha256: text(reservation, "source_sha256")?.into(),
        profile_sha256: profile_digest,
        image_digest: cache.platform_manifest_digest.clone(),
        config_image_id: cache.config_image_id.clone(),
        lease_id: header.lease_id,
        lease_generation: header.lease_generation,
    };
    if !invocation.valid() {
        return Err("PRE invocation invalid".into());
    }
    let environment = match &image["config"]["Env"] {
        Value::Null => Vec::new(),
        Value::Array(items) => items
            .iter()
            .map(|value| {
                value
                    .as_str()
                    .map(str::to_owned)
                    .ok_or("PRE image environment invalid")
            })
            .collect::<Result<Vec<_>, _>>()?,
        _ => return Err("PRE image environment invalid".into()),
    };
    if config.sandbox_uid == 0
        || config.sandbox_gid == 0
        || config.sandbox_uid == limits.worker_uid
        || config.sandbox_gid == limits.worker_gid
    {
        return Err("PRE workload identities overlap".into());
    }
    let startup = serde_json::json!({"operation":"execute_pre", "request":serde_json::from_slice::<Value>(bytes).map_err(|_| "PRE header invalid")?,
        "isolation": {"runtime":config.runtime,"isolation_mode":config.isolation_mode,"operating_system":config.operating_system,
        "architecture":config.architecture,"sandbox_uid":config.sandbox_uid,"sandbox_gid":config.sandbox_gid,
        "repository":cache.repository,"platform_manifest_digest":cache.platform_manifest_digest,
        "platform_manifest_media_type":cache.platform_manifest_media_type,"platform_manifest_byte_count":cache.platform_manifest_byte_count,"config_image_id":cache.config_image_id}});
    let job = PreBootstrapJob {
        limits,
        root: configured.root.clone(),
        root_limits: configured.root_limits.clone(),
        startup,
        selected: GuestJob {
            purpose: GuestPurpose::Project {
                capabilities: GuestCapabilities {
                    model: false,
                    execution: false,
                },
                materials: Vec::new(),
            },
            request: Value::Null,
            command: image_command(&image)?,
            environment,
            working_directory: image["config"]["WorkingDir"].as_str().unwrap_or("/").into(),
            uid: config.sandbox_uid,
            gid: config.sandbox_gid,
            directories: Vec::new(),
            files: Vec::new(),
        },
    };
    if serde_json::to_vec(&job)
        .map_err(|_| "PRE job invalid")?
        .len()
        > MAX_JOB_BYTES
        || Instant::now() >= deadline
    {
        return Err("PRE admission deadline or size exceeded".into());
    }
    Ok(Prepared {
        cache,
        root_bundle,
        job,
        invocation,
        resources,
        overlay_gib,
        deadline,
    })
}

#[cfg(test)]
mod tests;
