//! Private PRE bootstrap inputs, supplied only by the trusted node supervisor.
use crate::{
    trusted_root::{RootDescriptor, RootLimits},
    GuestJob,
};
use serde::{Deserialize, Serialize};

pub const PRE_LIMITS_ARGUMENT: &str = "--pre-limits";
pub const PRE_LIMITS_MAXIMUM_BYTES: usize = 4096;

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct PrePartition {
    pub cpu_millis: u64,
    pub memory_bytes: u64,
    pub processes: u64,
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct PreBootstrapLimits {
    pub control: PrePartition,
    pub worker: PrePartition,
    pub project: PrePartition,
    pub worker_uid: u32,
    pub worker_gid: u32,
    pub worker_scratch_bytes: u64,
    pub project_scratch_bytes: u64,
    pub maximum_source_bytes: u64,
    pub maximum_control_bytes: usize,
    pub maximum_output_bytes: usize,
    pub maximum_log_bytes: usize,
    pub timeout_ms: u64,
    pub cleanup_timeout_ms: u64,
    pub overlay_bytes: u64,
    pub filesystem_overhead_bytes: u64,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PreBootstrapJob {
    pub limits: PreBootstrapLimits,
    pub root: RootDescriptor,
    pub root_limits: RootLimits,
    pub selected: GuestJob,
    pub startup: serde_json::Value,
}
