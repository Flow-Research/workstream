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

impl PreBootstrapLimits {
    pub fn validate(&self) -> Result<(), String> {
        let limits = *self;
        for partition in [limits.control, limits.worker, limits.project] {
            if partition.cpu_millis == 0
                || partition.cpu_millis.checked_mul(100).is_none()
                || partition.memory_bytes == 0
                || partition.processes == 0
            {
                return Err("PRE partition invalid".into());
            }
        }
        if limits.control.processes < 3
            || limits.worker_uid == 0
            || limits.worker_gid == 0
            || limits.worker_scratch_bytes == 0
            || limits.maximum_source_bytes == 0
            || limits.project_scratch_bytes == 0
            || limits.maximum_control_bytes == 0
            || limits.maximum_control_bytes > 64 * 1024 * 1024
            || limits.maximum_control_bytes as u64 > limits.control.memory_bytes
            || limits.maximum_output_bytes == 0
            || limits.maximum_log_bytes == 0
            || u32::try_from(limits.maximum_output_bytes).is_err()
            || u32::try_from(limits.maximum_log_bytes).is_err()
            || limits.timeout_ms == 0
            || limits.timeout_ms > 14_400_000
            || limits.cleanup_timeout_ms < limits.timeout_ms
            || limits.cleanup_timeout_ms > 14_400_000
            || limits.overlay_bytes == 0
            || limits.filesystem_overhead_bytes == 0
        {
            return Err("PRE bootstrap bounds invalid".into());
        }
        Ok(())
    }
}
