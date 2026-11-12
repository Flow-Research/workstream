//! Host-owned PRE invocation and durable cleanup custody.
use super::*;
pub(super) mod admission;
mod transport;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct WorkerResult {
    protocol_version: String,
    operation: String,
    request_digest: String,
    lease_id: String,
    lease_generation: u64,
    payload: Value,
}

fn completed(bytes: &[u8], prepared: &admission::Prepared<'_>) -> Result<Value, String> {
    let result: WorkerResult = serde_json::from_slice(bytes).map_err(|_| "PRE result invalid")?;
    let invocation = &prepared.invocation;
    let expected = &prepared.job.startup["request"]["reservation"];
    if result.protocol_version != "workstream.pre_submit_worker.v1"
        || result.operation != "completed"
        || result.request_digest != invocation.request_digest
        || result.lease_id != invocation.lease_id
        || result.lease_generation != invocation.lease_generation
        || result.payload["schema_version"] != "workstream.selected_pre_submit_execution.v2"
        || result.payload["request_digest"] != invocation.request_digest
        || result.payload["lease_id"] != invocation.lease_id
        || result.payload["lease_generation"] != invocation.lease_generation
        || result.payload["observed_source"] != expected["source"]
        || result.payload["policy_sha256"] != expected["policy"]["policy_sha256"]
    {
        return Err("PRE result binding differs".into());
    }
    Ok(result.payload)
}

pub(crate) fn serve(
    config: &ServiceConfig,
    mut client: UnixStream,
    bytes: &[u8],
) -> Result<(), String> {
    let started = Instant::now();
    let mut prepared = admission::prepare(config, bytes)?;
    let deadline = prepared.deadline;
    let _reservation = reserve_capacity(
        config,
        resource_capacity(prepared.resources, Some(prepared.overlay_gib))?,
        None,
    )?;
    if !transport::connected(&client) || Instant::now() >= deadline {
        return Err("PRE cancelled or expired".into());
    }
    let admission_ms = started.elapsed().as_millis() as u64;
    let preparing = Instant::now();
    let mut machine = match Machine::create_pre(
        config,
        prepared.resources,
        deadline,
        prepared.invocation.clone(),
    ) {
        Ok(machine) => machine,
        Err(error) => {
            if error.cleanup_unsettled {
                quarantine(config);
                return Err(UNSETTLED_RESOURCE_ERROR.into());
            }
            return Err(error.code.into());
        }
    };
    let creation = machine.prepare_with_connection(
        prepared.cache,
        prepared.resources,
        Some(prepared.overlay_gib),
        &client,
        deadline,
        transport::connected,
    );
    let preparation_ms = preparing.elapsed().as_millis() as u64;
    let running = Instant::now();
    let result = creation
        .and_then(|()| machine.run_pre(&mut prepared, &mut client))
        .and_then(|bytes| completed(&bytes, &prepared));
    let execution_ms = running.elapsed().as_millis() as u64;
    let cleaning = Instant::now();
    let cleanup_deadline = deadline
        .min(Instant::now() + Duration::from_millis(prepared.job.limits.cleanup_timeout_ms));
    let destroyed = machine.close_until(cleanup_deadline).is_ok();
    let journal_sha256 = if destroyed {
        machine.journal.sha256.clone()
    } else {
        machine
            .pending_pre_cleanup(config)
            .map_err(|_| UNSETTLED_RESOURCE_ERROR)?
    };
    let cleanup_ms = cleaning.elapsed().as_millis() as u64;
    let (outcome, reason, execution) = match result {
        Ok(value) => ("completed", Value::Null, value),
        Err(error) => {
            let outcome = if error == "deadline_exceeded" {
                "deadline_exceeded"
            } else if error == "cancelled" {
                "cancelled"
            } else {
                "infrastructure_failure"
            };
            (
                outcome,
                Value::String(
                    if outcome == "infrastructure_failure" {
                        "implementation_unavailable"
                    } else {
                        outcome
                    }
                    .into(),
                ),
                Value::Null,
            )
        }
    };
    // Host custody stays outside the worker payload. The backend must retain
    // this invocation envelope along with the typed checker facts at T4.
    let response = serde_json::json!({
        "schema_version":"workstream.pre_submit_invocation.v1", "operation":"execute_pre", "phase":"pre_submit",
        "invocation":prepared.invocation,"provider_invocation_id":machine.lease.name,
        "outcome":outcome,"reason":reason,"execution":execution,
        "runtime":{"provider":"smolvm","version":VERSION,"binary_sha256":machine.lease.runtime.binary_sha256,
            "guest_sha256":machine.lease.runtime.guest_sha256,"profile":prepared.job.startup["request"]["reservation"]["runtime_profile"]},
        "timings_ms":{"admission":admission_ms,"preparation":preparation_ms,"execution":execution_ms,"cleanup":cleanup_ms,"total":started.elapsed().as_millis() as u64},
        "cleanup":{"obligation_id":machine.lease.name,"journal_sha256":journal_sha256,"disposition":if destroyed {"destroyed"} else {"pending"}}
    });
    let response = serde_json::to_vec(&response).map_err(|_| "PRE response invalid")?;
    let sent = if response.len() <= 64 * 1024 * 1024
        && Instant::now() < deadline
        && client_is_connected(&client)
    {
        write_frame_until(&mut client, &response, deadline)
    } else {
        Err("deadline_exceeded".into())
    };
    // A pending receipt may be delivered, but admission stays quarantined and
    // the service exits so recovery reconciles the durable journal on restart.
    if !destroyed {
        Err(UNSETTLED_RESOURCE_ERROR.into())
    } else {
        sent
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Invocation {
    pub operation: Operation,
    pub run_id: String,
    pub source_operation_id: String,
    pub request_digest: String,
    pub source_sha256: String,
    pub profile_sha256: String,
    pub image_digest: String,
    pub config_image_id: String,
    pub lease_id: String,
    pub lease_generation: u64,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub(super) enum Operation {
    #[serde(rename = "execute_pre")]
    ExecutePre,
}

impl Invocation {
    pub(super) fn valid(&self) -> bool {
        fn uuid(value: &str) -> bool {
            value.len() == 36
                && value.bytes().enumerate().all(|(index, byte)| {
                    if matches!(index, 8 | 13 | 18 | 23) {
                        byte == b'-'
                    } else {
                        byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase()
                    }
                })
        }
        [&self.run_id, &self.source_operation_id, &self.lease_id]
            .into_iter()
            .all(|value| uuid(value))
            && [
                &self.request_digest,
                &self.source_sha256,
                &self.profile_sha256,
                &self.image_digest,
                &self.config_image_id,
            ]
            .into_iter()
            .all(|value| valid_digest(value))
            && self.lease_generation > 0
    }
}

// Captured from the fsynced descriptor before guardian or provider creation.
// Neither guest output nor a subsequently discovered pathname supplies this.
pub(super) struct Journal {
    device: u64,
    inode: u64,
    sha256: String,
}

impl Journal {
    pub(super) fn capture(file: &File, bytes: &[u8]) -> Result<Self, String> {
        let metadata = file.metadata().map_err(|_| "lease unavailable")?;
        if !custody(&metadata) || metadata.len() != bytes.len() as u64 {
            return Err("lease custody differs".into());
        }
        Ok(Self {
            device: metadata.dev(),
            inode: metadata.ino(),
            sha256: format!("sha256:{:x}", Sha256::digest(bytes)),
        })
    }

    fn retained(&self, lease: &Lease) -> Result<String, String> {
        if lease.pre.is_none() || !lease.valid() {
            return Err("PRE lease invalid".into());
        }
        private_directory(&lease.root)?;
        let mut file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK)
            .open(lease.path())
            .map_err(|_| "lease unavailable")?;
        let before = file.metadata().map_err(|_| "lease unavailable")?;
        if !custody(&before) || before.dev() != self.device || before.ino() != self.inode {
            return Err("lease custody differs".into());
        }
        let mut bytes = Vec::new();
        Read::by_ref(&mut file)
            .take(MAX_ENVELOPE_BYTES as u64 + 1)
            .read_to_end(&mut bytes)
            .map_err(|_| "lease unavailable")?;
        let expected = serde_json::to_vec(lease).map_err(|_| "lease invalid")?;
        if bytes != expected || format!("sha256:{:x}", Sha256::digest(&bytes)) != self.sha256 {
            return Err("lease binding differs".into());
        }
        let after = fs::symlink_metadata(lease.path()).map_err(|_| "lease unavailable")?;
        if !custody(&after)
            || after.dev() != self.device
            || after.ino() != self.inode
            || after.len() != before.len()
        {
            return Err("lease custody differs".into());
        }
        Ok(self.sha256.clone())
    }
}

fn custody(metadata: &fs::Metadata) -> bool {
    metadata.is_file()
        && metadata.nlink() == 1
        && metadata.uid() == unsafe { libc::geteuid() }
        && metadata.gid() == unsafe { libc::getegid() }
        && metadata.mode() & 0o7777 == 0o600
        && metadata.len() <= MAX_ENVELOPE_BYTES as u64
}

impl Machine {
    fn run_pre(
        &mut self,
        prepared: &mut admission::Prepared<'_>,
        client: &mut UnixStream,
    ) -> Result<Vec<u8>, String> {
        if self.consumed {
            return Err("execution already consumed".into());
        }
        self.consumed = true;
        let remaining = prepared
            .deadline
            .saturating_duration_since(Instant::now())
            .as_millis() as u64;
        if remaining == 0 {
            return Err("deadline_exceeded".into());
        }
        prepared.job.limits.timeout_ms = prepared.job.limits.timeout_ms.min(remaining);
        prepared.job.limits.cleanup_timeout_ms =
            prepared.job.limits.cleanup_timeout_ms.min(remaining);
        prepared.job.limits.validate()?;
        let limits =
            serde_json::to_string(&prepared.job.limits).map_err(|_| "PRE limits invalid")?;
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
                workstream_checker_guest::pre_bootstrap::PRE_LIMITS_ARGUMENT,
                &limits,
            ],
            Some(&self.lease.cgroup()),
        )?;
        cmd.stdin(Stdio::piped());
        let child = cmd.spawn().map_err(|_| "PRE guest launch failed")?;
        transport::exchange(
            child,
            client,
            &mut prepared.root_bundle,
            &prepared.job,
            prepared.deadline,
        )
    }
    fn create_pre(
        config: &ServiceConfig,
        resources: Resources,
        deadline: Instant,
        invocation: Invocation,
    ) -> Result<Self, ExecutionFailure> {
        // PRE has exactly one create attempt; never enter execute's retry loop.
        Self::create_inner(config, resources, deadline, None, Some(invocation))
    }

    fn pending_pre_cleanup(&self, config: &ServiceConfig) -> Result<String, String> {
        // Refuse all further admission even if custody has been lost. The exact
        // retained journal is recoverable by the guardian or startup reaper.
        quarantine(config);
        self.journal.retained(&self.lease)
    }
}

#[cfg(test)]
mod tests;
