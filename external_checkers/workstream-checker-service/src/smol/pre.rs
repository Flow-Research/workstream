//! Host-owned PRE invocation and durable cleanup custody.
use super::*;
pub(super) mod admission;

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
