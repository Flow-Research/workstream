//! Invocation-local bounded session relay from a checker image to the trusted model proxy.

use crate::proxy_transport::{connect_private, read_frame, write_frame};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::{HashMap, HashSet};
use std::fmt;
use std::fs::{self, DirBuilder, File};
use std::io::{Read, Write};
use std::os::unix::ffi::OsStrExt;
use std::os::unix::fs::{DirBuilderExt, FileTypeExt, MetadataExt, PermissionsExt};
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread::{self, JoinHandle};
use std::time::{Duration, Instant};

pub(crate) const CONTAINER_MODEL_SOCKET: &str = "/work/model.sock";
const MODEL_PROXY_PROTOCOL: &str = "workstream.model_session.v2";
const MODEL_FRAME_MAXIMUM: usize = 1024 * 1024;
const MODEL_MAXIMUM_RECEIPTS: usize = 1000;
const INVOCATION_DIRECTORY_PREFIX: &str = ".model-";

pub(crate) use crate::proxy_transport::validate_private_socket as validate_proxy_socket;

#[derive(Clone, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(crate) struct ModelGrant {
    pub(crate) grant_id: String,
    pub(crate) binding_digest: String,
}

impl fmt::Debug for ModelGrant {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("ModelGrant(<redacted>)")
    }
}

/// The execute-envelope field uses an explicit deserializer so JSON `null` is
/// valid while an omitted `model_grant` member remains invalid.
#[derive(Clone, Deserialize)]
#[serde(transparent)]
pub(crate) struct RequiredModelGrant(pub(crate) Option<ModelGrant>);

impl fmt::Debug for RequiredModelGrant {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self.0 {
            Some(_) => formatter.write_str("RequiredModelGrant(Some(<redacted>))"),
            None => formatter.write_str("RequiredModelGrant(None)"),
        }
    }
}

pub(crate) fn deserialize_required_model_grant<'de, D>(
    deserializer: D,
) -> Result<RequiredModelGrant, D::Error>
where
    D: serde::Deserializer<'de>,
{
    Option::<ModelGrant>::deserialize(deserializer).map(RequiredModelGrant)
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ImageModelRequest {
    protocol_version: String,
    operation: String,
    call_index: u32,
    prompt: String,
    required_receipt_handles: Vec<String>,
}

impl fmt::Debug for ImageModelRequest {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("ImageModelRequest(<redacted>)")
    }
}

#[derive(Serialize)]
struct ProxyModelRequest<'a> {
    protocol_version: &'static str,
    grant_id: &'a str,
    request_digest: &'a str,
    call_index: u32,
    prompt: &'a str,
    resolved_receipts: &'a [ResolvedModelReceipt],
}

impl fmt::Debug for ProxyModelRequest<'_> {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("ProxyModelRequest(<redacted>)")
    }
}

#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
struct ProxyModelResponse {
    protocol_version: String,
    outcome: String,
    #[serde(deserialize_with = "deserialize_required_optional_string")]
    output: Option<String>,
    #[serde(deserialize_with = "deserialize_required_optional_string")]
    receipt_digest: Option<String>,
    #[serde(deserialize_with = "deserialize_required_optional_string")]
    failure_code: Option<String>,
    call_index: u32,
    session_exhausted: bool,
}

#[derive(Clone, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(crate) struct ResolvedModelReceipt {
    pub(crate) receipt_sha256: String,
    pub(crate) canonical_receipt_utf8: String,
}

impl fmt::Debug for ResolvedModelReceipt {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("ResolvedModelReceipt(<redacted>)")
    }
}

#[derive(Debug, PartialEq, Eq)]
pub(crate) enum ModelReceiptResolutionFailure {
    Invalid,
    Unavailable,
    LimitExceeded,
}

pub(crate) trait ModelReceiptResolver: Send + Sync {
    fn resolve(
        &self,
        request_digest: &str,
        handles: &[String],
        maximum_receipts: usize,
        maximum_bytes: usize,
    ) -> Result<Vec<ResolvedModelReceipt>, ModelReceiptResolutionFailure>;
}

struct RegisteredReceipt {
    request_digest: String,
    receipt: ResolvedModelReceipt,
}

#[derive(Default)]
pub(crate) struct InvocationReceiptRegistry {
    entries: Mutex<HashMap<String, RegisteredReceipt>>,
}

impl InvocationReceiptRegistry {
    pub(crate) fn register(
        &self,
        request_digest: &str,
        canonical_receipt_utf8: &str,
        receipt_sha256: &str,
    ) -> Result<String, ModelReceiptResolutionFailure> {
        if !valid_sha256(request_digest)
            || !valid_sha256(receipt_sha256)
            || canonical_receipt_utf8.is_empty()
            || canonical_receipt_utf8.len() > MODEL_FRAME_MAXIMUM
            || !canonical_json_receipt(canonical_receipt_utf8, receipt_sha256)
        {
            return Err(ModelReceiptResolutionFailure::Invalid);
        }
        let mut entries = self
            .entries
            .lock()
            .map_err(|_| ModelReceiptResolutionFailure::Unavailable)?;
        for _ in 0..8 {
            let mut random = [0_u8; 16];
            File::open("/dev/urandom")
                .and_then(|mut source| source.read_exact(&mut random))
                .map_err(|_| ModelReceiptResolutionFailure::Unavailable)?;
            let handle = format!(
                "trial_receipt_{}",
                random
                    .iter()
                    .map(|byte| format!("{byte:02x}"))
                    .collect::<String>()
            );
            if !entries.contains_key(&handle) {
                entries.insert(
                    handle.clone(),
                    RegisteredReceipt {
                        request_digest: request_digest.into(),
                        receipt: ResolvedModelReceipt {
                            receipt_sha256: receipt_sha256.into(),
                            canonical_receipt_utf8: canonical_receipt_utf8.into(),
                        },
                    },
                );
                return Ok(handle);
            }
        }
        Err(ModelReceiptResolutionFailure::Unavailable)
    }
}

impl ModelReceiptResolver for InvocationReceiptRegistry {
    fn resolve(
        &self,
        request_digest: &str,
        handles: &[String],
        maximum_receipts: usize,
        maximum_bytes: usize,
    ) -> Result<Vec<ResolvedModelReceipt>, ModelReceiptResolutionFailure> {
        if !valid_sha256(request_digest)
            || handles.len() > maximum_receipts
            || maximum_receipts > MODEL_MAXIMUM_RECEIPTS
            || maximum_bytes > MODEL_FRAME_MAXIMUM
        {
            return Err(ModelReceiptResolutionFailure::LimitExceeded);
        }
        let unique = handles.iter().collect::<HashSet<_>>();
        if unique.len() != handles.len()
            || handles.iter().any(|handle| !valid_receipt_handle(handle))
        {
            return Err(ModelReceiptResolutionFailure::Invalid);
        }
        let entries = self
            .entries
            .lock()
            .map_err(|_| ModelReceiptResolutionFailure::Unavailable)?;
        let mut total = 0_usize;
        let mut receipts = Vec::with_capacity(handles.len());
        for handle in handles {
            let entry = entries
                .get(handle)
                .filter(|entry| entry.request_digest == request_digest)
                .ok_or(ModelReceiptResolutionFailure::Unavailable)?;
            total = total
                .checked_add(entry.receipt.canonical_receipt_utf8.len())
                .ok_or(ModelReceiptResolutionFailure::LimitExceeded)?;
            if total > maximum_bytes {
                return Err(ModelReceiptResolutionFailure::LimitExceeded);
            }
            receipts.push(entry.receipt.clone());
        }
        Ok(receipts)
    }
}

impl fmt::Debug for ProxyModelResponse {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("ProxyModelResponse(<redacted>)")
    }
}

fn deserialize_required_optional_string<'de, D>(deserializer: D) -> Result<Option<String>, D::Error>
where
    D: serde::Deserializer<'de>,
{
    Option::<String>::deserialize(deserializer)
}

#[derive(Debug, PartialEq, Eq)]
pub(crate) struct RelayFinish {
    pub(crate) failed: bool,
    pub(crate) cleanup_unsettled: bool,
}

#[derive(Debug)]
pub(crate) struct RelayStartFailure {
    pub(crate) cleanup_unsettled: bool,
}

impl RelayStartFailure {
    fn ordinary() -> Self {
        Self {
            cleanup_unsettled: false,
        }
    }
}

#[derive(Debug)]
struct RelayPaths {
    directory: PathBuf,
    socket: PathBuf,
    directory_device: u64,
    directory_inode: u64,
    socket_device: u64,
    socket_inode: u64,
    sandbox_uid: u32,
    sandbox_gid: u32,
}

pub(crate) struct InvocationRelay {
    paths: RelayPaths,
    cancelled: Arc<AtomicBool>,
    worker: Option<JoinHandle<Result<(), String>>>,
}

impl InvocationRelay {
    pub(crate) fn start(
        relay_root: &Path,
        proxy_path: &Path,
        grant: &ModelGrant,
        request_digest: &str,
        sandbox_uid: u32,
        sandbox_gid: u32,
        deadline: Instant,
    ) -> Result<Self, RelayStartFailure> {
        Self::start_with_resolver(
            relay_root,
            proxy_path,
            grant,
            request_digest,
            Arc::new(InvocationReceiptRegistry::default()),
            sandbox_uid,
            sandbox_gid,
            deadline,
        )
    }

    #[allow(clippy::too_many_arguments)]
    pub(crate) fn start_with_resolver(
        relay_root: &Path,
        proxy_path: &Path,
        grant: &ModelGrant,
        request_digest: &str,
        receipt_resolver: Arc<dyn ModelReceiptResolver>,
        sandbox_uid: u32,
        sandbox_gid: u32,
        deadline: Instant,
    ) -> Result<Self, RelayStartFailure> {
        validate_proxy_socket(proxy_path).map_err(|_| RelayStartFailure::ordinary())?;
        validate_relay_root(relay_root).map_err(|_| RelayStartFailure::ordinary())?;
        // The unprivileged service cannot chown after dropping every capability.
        // Requiring the sandbox identity to match makes the newly bound socket
        // inherit its final owner without a privileged operation.
        // SAFETY: effective IDs are read-only process attributes.
        let (effective_uid, effective_gid) = unsafe { (libc::geteuid(), libc::getegid()) };
        if (sandbox_uid, sandbox_gid) != (effective_uid, effective_gid) {
            return Err(RelayStartFailure::ordinary());
        }
        let directory =
            create_invocation_directory(relay_root).map_err(|_| RelayStartFailure::ordinary())?;
        let socket = directory.join("model.sock");
        let listener = match UnixListener::bind(&socket) {
            Ok(listener) => listener,
            Err(_) => {
                return Err(RelayStartFailure {
                    cleanup_unsettled: fs::remove_dir(&directory).is_err(),
                });
            }
        };
        if listener.set_nonblocking(true).is_err()
            || fs::set_permissions(&socket, fs::Permissions::from_mode(0o600)).is_err()
        {
            drop(listener);
            return Err(remove_created_paths(&directory, &socket));
        }
        let directory_metadata = match fs::symlink_metadata(&directory) {
            Ok(metadata) => metadata,
            Err(_) => {
                drop(listener);
                return Err(remove_created_paths(&directory, &socket));
            }
        };
        let socket_metadata = match fs::symlink_metadata(&socket) {
            Ok(metadata) => metadata,
            Err(_) => {
                drop(listener);
                return Err(remove_created_paths(&directory, &socket));
            }
        };
        if !private_process_directory(&directory_metadata)
            || !sandbox_socket(&socket_metadata, sandbox_uid, sandbox_gid)
        {
            drop(listener);
            return Err(remove_created_paths(&directory, &socket));
        }
        let paths = RelayPaths {
            directory,
            socket,
            directory_device: directory_metadata.dev(),
            directory_inode: directory_metadata.ino(),
            socket_device: socket_metadata.dev(),
            socket_inode: socket_metadata.ino(),
            sandbox_uid,
            sandbox_gid,
        };
        let cancelled = Arc::new(AtomicBool::new(false));
        let worker_cancelled = Arc::clone(&cancelled);
        let proxy = proxy_path.to_owned();
        let grant = grant.clone();
        let digest = request_digest.to_owned();
        let worker = match thread::Builder::new()
            .name("checker-model-relay".into())
            .spawn(move || {
                relay_once(
                    listener,
                    &proxy,
                    &grant,
                    &digest,
                    receipt_resolver.as_ref(),
                    deadline,
                    &worker_cancelled,
                )
            }) {
            Ok(worker) => worker,
            Err(_) => {
                return Err(RelayStartFailure {
                    cleanup_unsettled: !cleanup_paths(&paths),
                });
            }
        };
        Ok(Self {
            paths,
            cancelled,
            worker: Some(worker),
        })
    }

    pub(crate) fn mount_spec(&self) -> String {
        format!(
            "type=bind,src={},dst={CONTAINER_MODEL_SOCKET},readonly",
            self.paths.socket.display()
        )
    }

    #[cfg(test)]
    pub(crate) fn socket_path(&self) -> &Path {
        &self.paths.socket
    }

    pub(crate) fn finish(mut self) -> RelayFinish {
        self.cancelled.store(true, Ordering::Release);
        let failed = self
            .worker
            .take()
            .is_some_and(|worker| !matches!(worker.join(), Ok(Ok(()))));
        let cleanup_unsettled = !cleanup_paths(&self.paths);
        RelayFinish {
            failed,
            cleanup_unsettled,
        }
    }
}

fn remove_created_paths(directory: &Path, socket: &Path) -> RelayStartFailure {
    let socket_removed = match fs::remove_file(socket) {
        Ok(()) => true,
        Err(error) => error.kind() == std::io::ErrorKind::NotFound,
    };
    let directory_removed = match fs::remove_dir(directory) {
        Ok(()) => true,
        Err(error) => error.kind() == std::io::ErrorKind::NotFound,
    };
    RelayStartFailure {
        cleanup_unsettled: !socket_removed || !directory_removed,
    }
}

impl Drop for InvocationRelay {
    fn drop(&mut self) {
        self.cancelled.store(true, Ordering::Release);
        if let Some(worker) = self.worker.take() {
            let _ = worker.join();
        }
        let _ = cleanup_paths(&self.paths);
    }
}

pub(crate) fn valid_model_grant(grant: &ModelGrant, request_digest: &str, phase: &str) -> bool {
    phase == "post_submit"
        && grant.binding_digest == request_digest
        && grant.grant_id.len() == 38
        && grant.grant_id.starts_with("model_")
        && grant.grant_id[6..]
            .bytes()
            .all(|item| item.is_ascii_hexdigit() && !item.is_ascii_uppercase())
}

pub(crate) fn validate_relay_root(path: &Path) -> Result<(), String> {
    if !path.is_absolute() || path.as_os_str().as_bytes().contains(&b',') {
        return Err("model relay root invalid".into());
    }
    let canonical = fs::canonicalize(path).map_err(|_| "model relay root unavailable")?;
    let metadata = fs::symlink_metadata(path).map_err(|_| "model relay root unavailable")?;
    if canonical != path || !private_process_directory(&metadata) {
        return Err("model relay root custody invalid".into());
    }
    let maximum_socket_path = path
        .join(format!("{INVOCATION_DIRECTORY_PREFIX}{}", "0".repeat(16)))
        .join("model.sock");
    if maximum_socket_path.as_os_str().as_bytes().len() >= 108 {
        return Err("model relay root path too long".into());
    }
    Ok(())
}

fn create_invocation_directory(parent: &Path) -> Result<PathBuf, String> {
    for _ in 0..8 {
        let mut random = [0_u8; 8];
        File::open("/dev/urandom")
            .and_then(|mut source| source.read_exact(&mut random))
            .map_err(|_| "model relay randomness unavailable")?;
        let name = random
            .iter()
            .fold(String::with_capacity(16), |mut value, byte| {
                use std::fmt::Write;
                write!(&mut value, "{byte:02x}").expect("writing to String cannot fail");
                value
            });
        let path = parent.join(format!("{INVOCATION_DIRECTORY_PREFIX}{name}"));
        let mut builder = DirBuilder::new();
        builder.mode(0o700);
        match builder.create(&path) {
            Ok(()) => return Ok(path),
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(_) => return Err("model relay directory unavailable".into()),
        }
    }
    Err("model relay directory collision".into())
}

fn relay_once(
    listener: UnixListener,
    proxy_path: &Path,
    grant: &ModelGrant,
    request_digest: &str,
    receipt_resolver: &dyn ModelReceiptResolver,
    deadline: Instant,
    cancelled: &AtomicBool,
) -> Result<(), String> {
    let mut image = loop {
        if Instant::now() >= deadline {
            return Err("model relay deadline exceeded".into());
        }
        match listener.accept() {
            Ok((stream, _)) => break stream,
            Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                if cancelled.load(Ordering::Acquire) {
                    return Ok(());
                }
                thread::sleep(Duration::from_millis(2));
            }
            Err(_) => return Err("model relay accept failed".into()),
        }
    };
    drop(listener); // one bounded session: no second connection can be accepted.
    image
        .set_nonblocking(true)
        .map_err(|_| "model relay image socket invalid")?;
    let mut next_call_index = 0_u32;
    let mut completed_calls = 0_u32;
    loop {
        let request = match read_frame(&mut image, MODEL_FRAME_MAXIMUM, deadline, cancelled) {
            Ok(request) => request,
            Err(_) if cancelled.load(Ordering::Acquire) && completed_calls > 0 => return Ok(()),
            Err(error) => return Err(error),
        };
        let image_request: ImageModelRequest =
            serde_json::from_slice(&request).map_err(|_| "model relay request invalid")?;
        if image_request.protocol_version != MODEL_PROXY_PROTOCOL
            || image_request.operation != "call"
            || image_request.call_index != next_call_index
            || image_request.call_index > 99
            || image_request.prompt.is_empty()
        {
            return Err("model relay request invalid".into());
        }
        let resolved_receipts = receipt_resolver
            .resolve(
                request_digest,
                &image_request.required_receipt_handles,
                MODEL_MAXIMUM_RECEIPTS,
                MODEL_FRAME_MAXIMUM,
            )
            .map_err(|_| "model relay receipt unavailable")?;
        let wrapped = serde_json::to_vec(&ProxyModelRequest {
            protocol_version: MODEL_PROXY_PROTOCOL,
            grant_id: &grant.grant_id,
            request_digest,
            call_index: image_request.call_index,
            prompt: &image_request.prompt,
            resolved_receipts: &resolved_receipts,
        })
        .map_err(|_| "model relay request invalid")?;
        if wrapped.is_empty() || wrapped.len() > MODEL_FRAME_MAXIMUM {
            return Err("model relay request unbounded".into());
        }
        let mut proxy = connect_private(proxy_path, deadline, cancelled)?;
        write_frame(
            &mut proxy,
            &wrapped,
            MODEL_FRAME_MAXIMUM,
            deadline,
            cancelled,
        )?;
        let response = read_frame(&mut proxy, MODEL_FRAME_MAXIMUM, deadline, cancelled)?;
        let response_value: ProxyModelResponse =
            serde_json::from_slice(&response).map_err(|_| "model relay response invalid")?;
        if !valid_proxy_response(&response_value, image_request.call_index) {
            return Err("model relay response invalid".into());
        }
        write_frame(
            &mut image,
            &response,
            MODEL_FRAME_MAXIMUM,
            deadline,
            cancelled,
        )?;
        completed_calls += 1;
        if response_value.session_exhausted || response_value.outcome == "unavailable" {
            return Ok(());
        }
        next_call_index = next_call_index
            .checked_add(1)
            .ok_or_else(|| "model relay session exhausted".to_string())?;
    }
}

fn valid_proxy_response(response: &ProxyModelResponse, call_index: u32) -> bool {
    if response.protocol_version != MODEL_PROXY_PROTOCOL || response.call_index != call_index {
        return false;
    }
    match response.outcome.as_str() {
        "completed" => {
            response
                .output
                .as_ref()
                .is_some_and(|value| !value.is_empty())
                && response.receipt_digest.as_deref().is_some_and(valid_sha256)
                && response.failure_code.is_none()
        }
        "unavailable" => {
            response.output.is_none()
                && response.receipt_digest.is_none()
                && response
                    .failure_code
                    .as_deref()
                    .is_some_and(valid_failure_code)
        }
        _ => false,
    }
}

fn valid_sha256(value: &str) -> bool {
    value.len() == 71
        && value.starts_with("sha256:")
        && value[7..]
            .bytes()
            .all(|item| item.is_ascii_hexdigit() && !item.is_ascii_uppercase())
}

fn valid_failure_code(value: &str) -> bool {
    matches!(
        value,
        "model_request_invalid"
            | "model_request_too_large"
            | "model_receipt_unavailable"
            | "model_tool_limit_exceeded"
            | "model_session_exhausted"
            | "model_session_deadline"
            | "model_budget_unavailable"
            | "model_call_unavailable"
            | "model_call_operator_recovery_required"
            | "model_provider_no_effect"
            | "model_provider_delivery_uncertain"
            | "model_provider_pending"
            | "model_provider_recovery_unavailable"
            | "model_provider_usage_unavailable"
            | "model_provider_failed"
            | "model_response_too_large"
            | "model_transport_unavailable"
    )
}

fn valid_receipt_handle(value: &str) -> bool {
    value.len() == 46
        && value.starts_with("trial_receipt_")
        && value[14..]
            .bytes()
            .all(|item| item.is_ascii_hexdigit() && !item.is_ascii_uppercase())
}

fn canonical_json_receipt(value: &str, expected_sha256: &str) -> bool {
    let parsed: serde_json::Value = match serde_json::from_str(value) {
        Ok(parsed) => parsed,
        Err(_) => return false,
    };
    if !matches!(serde_json::to_string(&parsed), Ok(encoded) if encoded == value) {
        return false;
    }
    let mut digest = Sha256::new();
    digest.update(value.as_bytes());
    format!("sha256:{:x}", digest.finalize()) == expected_sha256
}
fn cleanup_paths(paths: &RelayPaths) -> bool {
    let socket_ok = match fs::symlink_metadata(&paths.socket) {
        Ok(metadata)
            if sandbox_socket(&metadata, paths.sandbox_uid, paths.sandbox_gid)
                && (metadata.dev(), metadata.ino())
                    == (paths.socket_device, paths.socket_inode) =>
        {
            fs::remove_file(&paths.socket).is_ok()
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => true,
        _ => false,
    };
    let directory_ok = match fs::symlink_metadata(&paths.directory) {
        Ok(metadata)
            if private_process_directory(&metadata)
                && (metadata.dev(), metadata.ino())
                    == (paths.directory_device, paths.directory_inode) =>
        {
            fs::remove_dir(&paths.directory).is_ok()
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => true,
        _ => false,
    };
    socket_ok && directory_ok
}

fn private_process_directory(metadata: &fs::Metadata) -> bool {
    // SAFETY: effective IDs are read-only process attributes.
    let (uid, gid) = unsafe { (libc::geteuid(), libc::getegid()) };
    metadata.file_type().is_dir()
        && metadata.mode() & 0o777 == 0o700
        && metadata.uid() == uid
        && metadata.gid() == gid
}

fn sandbox_socket(metadata: &fs::Metadata, uid: u32, gid: u32) -> bool {
    metadata.file_type().is_socket()
        && metadata.mode() & 0o777 == 0o600
        && metadata.uid() == uid
        && metadata.gid() == gid
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::AtomicU64;
    use std::time::{SystemTime, UNIX_EPOCH};

    static NEXT_ROOT: AtomicU64 = AtomicU64::new(0);

    fn private_root() -> PathBuf {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!(
            "ws-model-relay-{}-{unique}-{}",
            std::process::id(),
            NEXT_ROOT.fetch_add(1, Ordering::Relaxed),
        ));
        fs::create_dir(&root).unwrap();
        fs::set_permissions(&root, fs::Permissions::from_mode(0o700)).unwrap();
        root
    }

    fn frame(stream: &mut UnixStream, value: &[u8]) {
        stream
            .write_all(&(value.len() as u32).to_be_bytes())
            .unwrap();
        stream.write_all(value).unwrap();
    }

    fn receive(stream: &mut UnixStream) -> Vec<u8> {
        stream.set_nonblocking(false).unwrap();
        let mut header = [0_u8; 4];
        stream.read_exact(&mut header).unwrap();
        let mut body = vec![0; u32::from_be_bytes(header) as usize];
        stream.read_exact(&mut body).unwrap();
        body
    }

    #[test]
    fn grant_is_exactly_post_submit_and_request_bound() {
        let digest = format!("sha256:{}", "a".repeat(64));
        let grant = ModelGrant {
            grant_id: format!("model_{}", "1".repeat(32)),
            binding_digest: digest.clone(),
        };
        assert!(valid_model_grant(&grant, &digest, "post_submit"));
        assert!(!valid_model_grant(&grant, &digest, "pre_submit"));
        assert!(!valid_model_grant(
            &grant,
            &format!("sha256:{}", "b".repeat(64)),
            "post_submit"
        ));
        for invalid in [
            "model_0123456789abcdef0123456789abcde",
            "model_0123456789abcdef0123456789abcdef0",
            "model_0123456789abcdef0123456789abcdeG",
            "other_0123456789abcdef0123456789abcdef",
        ] {
            let mut changed = grant.clone();
            changed.grant_id = invalid.into();
            assert!(!valid_model_grant(&changed, &digest, "post_submit"));
        }
    }

    #[test]
    fn receipt_registry_is_request_bound_canonical_unique_and_bounded() {
        let registry = InvocationReceiptRegistry::default();
        let request = format!("sha256:{}", "a".repeat(64));
        let foreign = format!("sha256:{}", "b".repeat(64));
        let canonical = r#"{"facts":{"exit_code":0},"schema":"trial.v1"}"#;
        let mut digest = Sha256::new();
        digest.update(canonical.as_bytes());
        let receipt_sha = format!("sha256:{:x}", digest.finalize());
        let handle = registry
            .register(&request, canonical, &receipt_sha)
            .unwrap();
        assert!(valid_receipt_handle(&handle));
        assert_eq!(
            registry.resolve(&request, std::slice::from_ref(&handle), 1, canonical.len()),
            Ok(vec![ResolvedModelReceipt {
                receipt_sha256: receipt_sha.clone(),
                canonical_receipt_utf8: canonical.into(),
            }])
        );
        assert_eq!(
            registry.resolve(&foreign, std::slice::from_ref(&handle), 1, canonical.len()),
            Err(ModelReceiptResolutionFailure::Unavailable)
        );
        assert_eq!(
            registry.resolve(&request, &[handle.clone(), handle], 2, canonical.len() * 2),
            Err(ModelReceiptResolutionFailure::Invalid)
        );
        assert_eq!(registry.resolve(&request, &[], 0, 0), Ok(Vec::new()));
        assert_eq!(
            registry.register(&request, "{\"z\":0,\"a\":1}", &receipt_sha),
            Err(ModelReceiptResolutionFailure::Invalid)
        );
    }

    #[test]
    fn diagnostic_output_redacts_model_grants_prompts_and_results() {
        let grant_id = format!("model_{}", "1".repeat(32));
        let digest = format!("sha256:{}", "a".repeat(64));
        let prompt = "private image prompt";
        let output = "private model output";
        let grant = ModelGrant {
            grant_id: grant_id.clone(),
            binding_digest: digest.clone(),
        };
        let required = RequiredModelGrant(Some(grant.clone()));
        let image = ImageModelRequest {
            protocol_version: MODEL_PROXY_PROTOCOL.into(),
            operation: "call".into(),
            call_index: 0,
            prompt: prompt.into(),
            required_receipt_handles: vec![],
        };
        let request = ProxyModelRequest {
            protocol_version: MODEL_PROXY_PROTOCOL,
            grant_id: &grant.grant_id,
            request_digest: &digest,
            call_index: 0,
            prompt,
            resolved_receipts: &[],
        };
        let response = ProxyModelResponse {
            protocol_version: MODEL_PROXY_PROTOCOL.into(),
            outcome: "completed".into(),
            output: Some(output.into()),
            receipt_digest: Some(format!("sha256:{}", "b".repeat(64))),
            failure_code: None,
            call_index: 0,
            session_exhausted: true,
        };

        for diagnostic in [
            format!("{grant:?}"),
            format!("{required:?}"),
            format!("{image:?}"),
            format!("{request:?}"),
            format!("{response:?}"),
        ] {
            assert!(!diagnostic.contains(&grant_id));
            assert!(!diagnostic.contains(&digest));
            assert!(!diagnostic.contains(prompt));
            assert!(!diagnostic.contains(output));
        }
        assert_eq!(
            format!("{:?}", RequiredModelGrant(None)),
            "RequiredModelGrant(None)"
        );
    }

    #[test]
    fn proxy_response_has_a_closed_non_provider_contract() {
        let completed = ProxyModelResponse {
            protocol_version: MODEL_PROXY_PROTOCOL.into(),
            outcome: "completed".into(),
            output: Some("answer".into()),
            receipt_digest: Some(format!("sha256:{}", "a".repeat(64))),
            failure_code: None,
            call_index: 0,
            session_exhausted: true,
        };
        assert!(valid_proxy_response(&completed, 0));
        let unavailable = ProxyModelResponse {
            protocol_version: MODEL_PROXY_PROTOCOL.into(),
            outcome: "unavailable".into(),
            output: None,
            receipt_digest: None,
            failure_code: Some("model_budget_unavailable".into()),
            call_index: 0,
            session_exhausted: true,
        };
        assert!(valid_proxy_response(&unavailable, 0));
        for invalid in [
            ProxyModelResponse {
                failure_code: Some("provider_error: secret".into()),
                ..unavailable.clone()
            },
            ProxyModelResponse {
                receipt_digest: None,
                ..completed.clone()
            },
        ] {
            assert!(!valid_proxy_response(&invalid, 0));
        }
        assert!(serde_json::from_slice::<ProxyModelResponse>(
            br#"{"protocol_version":"workstream.model_session.v2","outcome":"unavailable","output":null,"receipt_digest":null,"failure_code":"model_provider_failed","call_index":0,"session_exhausted":true,"provider_id":"secret"}"#
        )
        .is_err());
        assert!(serde_json::from_slice::<ProxyModelResponse>(
            br#"{"protocol_version":"workstream.model_session.v2","outcome":"unavailable","output":null,"failure_code":"model_provider_failed","call_index":0,"session_exhausted":true}"#
        )
        .is_err());
    }

    #[test]
    fn relay_wraps_bounded_sequential_calls_and_cleans_invocation_socket() {
        let root = private_root();
        let proxy_path = root.join("proxy.sock");
        let proxy = UnixListener::bind(&proxy_path).unwrap();
        fs::set_permissions(&proxy_path, fs::Permissions::from_mode(0o600)).unwrap();
        let digest = format!("sha256:{}", "a".repeat(64));
        let grant = ModelGrant {
            grant_id: format!("model_{}", "1".repeat(32)),
            binding_digest: digest.clone(),
        };
        let uid = fs::metadata(&root).unwrap().uid();
        let gid = fs::metadata(&root).unwrap().gid();
        let relay = InvocationRelay::start(
            &root,
            &proxy_path,
            &grant,
            &digest,
            uid,
            gid,
            Instant::now() + Duration::from_secs(2),
        )
        .unwrap();
        let relay_path = relay.socket_path().to_owned();
        let mut image = UnixStream::connect(&relay_path).unwrap();
        frame(&mut image, br#"{"protocol_version":"workstream.model_session.v2","operation":"call","call_index":0,"prompt":"review this","required_receipt_handles":[]}"#);
        let (mut backend, _) = proxy.accept().unwrap();
        let wrapped: serde_json::Value = serde_json::from_slice(&receive(&mut backend)).unwrap();
        assert_eq!(wrapped["protocol_version"], MODEL_PROXY_PROTOCOL);
        assert_eq!(wrapped["grant_id"], grant.grant_id);
        assert_eq!(wrapped["request_digest"], digest);
        assert_eq!(wrapped["call_index"], 0);
        assert_eq!(wrapped["prompt"], "review this");
        assert_eq!(wrapped["resolved_receipts"], serde_json::json!([]));
        let response = format!(
            r#"{{"protocol_version":"{MODEL_PROXY_PROTOCOL}","outcome":"completed","output":"bounded","receipt_digest":"sha256:{}","failure_code":null,"call_index":0,"session_exhausted":false}}"#,
            "b".repeat(64)
        );
        frame(&mut backend, response.as_bytes());
        assert_eq!(receive(&mut image), response.as_bytes());
        frame(&mut image, br#"{"protocol_version":"workstream.model_session.v2","operation":"call","call_index":1,"prompt":"assess this","required_receipt_handles":[]}"#);
        let (mut backend, _) = proxy.accept().unwrap();
        let wrapped: serde_json::Value = serde_json::from_slice(&receive(&mut backend)).unwrap();
        assert_eq!(wrapped["call_index"], 1);
        assert_eq!(wrapped["prompt"], "assess this");
        let response = format!(
            r#"{{"protocol_version":"{MODEL_PROXY_PROTOCOL}","outcome":"completed","output":"complete","receipt_digest":"sha256:{}","failure_code":null,"call_index":1,"session_exhausted":true}}"#,
            "c".repeat(64)
        );
        frame(&mut backend, response.as_bytes());
        assert_eq!(receive(&mut image), response.as_bytes());
        assert!(UnixStream::connect(&relay_path).is_err());
        assert_eq!(
            relay.finish(),
            RelayFinish {
                failed: false,
                cleanup_unsettled: false
            }
        );
        assert!(!relay_path.exists());
        fs::remove_file(proxy_path).unwrap();
        fs::remove_dir(root).unwrap();
    }

    #[test]
    fn distinct_invocations_and_frame_bounds_do_not_cross() {
        let root = private_root();
        let proxy_path = root.join("proxy.sock");
        let _proxy = UnixListener::bind(&proxy_path).unwrap();
        fs::set_permissions(&proxy_path, fs::Permissions::from_mode(0o600)).unwrap();
        let uid = fs::metadata(&root).unwrap().uid();
        let gid = fs::metadata(&root).unwrap().gid();
        let digest = format!("sha256:{}", "a".repeat(64));
        let grant = ModelGrant {
            grant_id: format!("model_{}", "1".repeat(32)),
            binding_digest: digest.clone(),
        };
        let mut first = InvocationRelay::start(
            &root,
            &proxy_path,
            &grant,
            &digest,
            uid,
            gid,
            Instant::now() + Duration::from_secs(5),
        )
        .unwrap();
        let second = InvocationRelay::start(
            &root,
            &proxy_path,
            &grant,
            &digest,
            uid,
            gid,
            Instant::now() + Duration::from_secs(5),
        )
        .unwrap();
        assert_ne!(first.socket_path(), second.socket_path());
        let mut attacker = UnixStream::connect(first.socket_path()).unwrap();
        attacker
            .write_all(&((MODEL_FRAME_MAXIMUM + 1) as u32).to_be_bytes())
            .unwrap();
        // Wait for the relay to close its accepted peer before inspecting the
        // worker result. Calling `finish` immediately would cancel a thread
        // that had not necessarily accepted the queued connection yet.
        attacker
            .set_read_timeout(Some(Duration::from_secs(5)))
            .unwrap();
        let mut closed = [0_u8; 1];
        assert_eq!(attacker.read(&mut closed).unwrap(), 0);
        let result = first.worker.take().unwrap().join().unwrap();
        assert_eq!(result, Err("private proxy frame unbounded".into()));
        assert!(!first.finish().cleanup_unsettled);
        assert!(!second.finish().cleanup_unsettled);
        fs::remove_file(proxy_path).unwrap();
        fs::remove_dir(root).unwrap();
    }

    #[test]
    fn incomplete_exchange_obeys_deadline_and_cleanup() {
        let root = private_root();
        let proxy_path = root.join("proxy.sock");
        let _proxy = UnixListener::bind(&proxy_path).unwrap();
        fs::set_permissions(&proxy_path, fs::Permissions::from_mode(0o600)).unwrap();
        let uid = fs::metadata(&root).unwrap().uid();
        let gid = fs::metadata(&root).unwrap().gid();
        let digest = format!("sha256:{}", "a".repeat(64));
        let grant = ModelGrant {
            grant_id: format!("model_{}", "1".repeat(32)),
            binding_digest: digest.clone(),
        };
        let started = Instant::now();
        let relay = InvocationRelay::start(
            &root,
            &proxy_path,
            &grant,
            &digest,
            uid,
            gid,
            Instant::now() + Duration::from_millis(50),
        )
        .unwrap();
        let mut image = UnixStream::connect(relay.socket_path()).unwrap();
        image.write_all(&20_u32.to_be_bytes()).unwrap();
        assert!(relay.finish().failed);
        assert!(started.elapsed() < Duration::from_millis(500));
        fs::remove_file(proxy_path).unwrap();
        fs::remove_dir(root).unwrap();
    }

    #[test]
    fn relay_rejects_a_non_object_proxy_response() {
        let root = private_root();
        let proxy_path = root.join("proxy.sock");
        let proxy = UnixListener::bind(&proxy_path).unwrap();
        fs::set_permissions(&proxy_path, fs::Permissions::from_mode(0o600)).unwrap();
        let owner = fs::metadata(&root).unwrap();
        let digest = format!("sha256:{}", "a".repeat(64));
        let grant = ModelGrant {
            grant_id: format!("model_{}", "1".repeat(32)),
            binding_digest: digest.clone(),
        };
        let relay = InvocationRelay::start(
            &root,
            &proxy_path,
            &grant,
            &digest,
            owner.uid(),
            owner.gid(),
            Instant::now() + Duration::from_secs(2),
        )
        .unwrap();
        let mut image = UnixStream::connect(relay.socket_path()).unwrap();
        frame(&mut image, br#"{"protocol_version":"workstream.model_session.v2","operation":"call","call_index":0,"prompt":"review this","required_receipt_handles":[]}"#);
        let (mut backend, _) = proxy.accept().unwrap();
        let _ = receive(&mut backend);
        frame(&mut backend, br#"["not","a","contract"]"#);
        assert!(relay.finish().failed);
        fs::remove_file(proxy_path).unwrap();
        fs::remove_dir(root).unwrap();
    }

    #[test]
    fn proxy_path_must_be_an_absolute_socket() {
        let root = private_root();
        assert!(validate_relay_root(&root).is_ok());
        assert!(validate_proxy_socket(Path::new("relative.sock")).is_err());
        let regular = root.join("regular");
        fs::write(&regular, b"not a socket").unwrap();
        assert!(validate_proxy_socket(&regular).is_err());
        let socket = root.join("proxy.sock");
        let _listener = UnixListener::bind(&socket).unwrap();
        assert!(validate_proxy_socket(&socket).is_err());
        fs::set_permissions(&socket, fs::Permissions::from_mode(0o600)).unwrap();
        assert!(validate_proxy_socket(&socket).is_ok());
        let trusted = root.join("trusted");
        fs::create_dir(&trusted).unwrap();
        fs::set_permissions(&trusted, fs::Permissions::from_mode(0o700)).unwrap();
        let linked = root.join("linked");
        std::os::unix::fs::symlink(&trusted, &linked).unwrap();
        let linked_socket = trusted.join("proxy.sock");
        let _linked_listener = UnixListener::bind(&linked_socket).unwrap();
        fs::set_permissions(&linked_socket, fs::Permissions::from_mode(0o600)).unwrap();
        assert!(validate_proxy_socket(&linked.join("proxy.sock")).is_err());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn relay_root_is_private_bounded_and_does_not_need_chown() {
        let root = private_root();
        let proxy_path = root.join("proxy.sock");
        let _proxy = UnixListener::bind(&proxy_path).unwrap();
        fs::set_permissions(&proxy_path, fs::Permissions::from_mode(0o600)).unwrap();
        let owner = fs::metadata(&root).unwrap();
        let digest = format!("sha256:{}", "a".repeat(64));
        let grant = ModelGrant {
            grant_id: format!("model_{}", "1".repeat(32)),
            binding_digest: digest.clone(),
        };
        let different_uid = owner.uid().wrapping_add(1);
        assert!(InvocationRelay::start(
            &root,
            &proxy_path,
            &grant,
            &digest,
            different_uid,
            owner.gid(),
            Instant::now() + Duration::from_secs(1),
        )
        .is_err());
        assert_eq!(
            fs::read_dir(&root)
                .unwrap()
                .filter_map(Result::ok)
                .filter(|entry| entry.file_name().to_string_lossy().starts_with(".model-"))
                .count(),
            0
        );

        let comma_root = root.join("relay,invalid");
        fs::create_dir(&comma_root).unwrap();
        fs::set_permissions(&comma_root, fs::Permissions::from_mode(0o700)).unwrap();
        assert!(validate_relay_root(&comma_root).is_err());

        let long_root = root.join("x".repeat(100));
        fs::create_dir(&long_root).unwrap();
        fs::set_permissions(&long_root, fs::Permissions::from_mode(0o700)).unwrap();
        assert!(validate_relay_root(&long_root).is_err());
        fs::remove_dir_all(root).unwrap();
    }
}
