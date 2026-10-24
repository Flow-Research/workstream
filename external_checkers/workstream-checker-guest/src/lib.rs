//! Private node-to-guest bootstrap protocol. Not a project checker API.
use serde::{Deserialize, Serialize};

pub const MAX_JOB_BYTES: usize = 4 * 1024 * 1024;
pub const CAPACITY_EXIT_CODE: i32 = 201;
pub const INPUT_ROOT: &str = "/work/input";

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MaterialFile {
    pub normalized_path: String,
    pub byte_count: u64,
    pub sha256: String,
    pub executable: bool,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum GuestPurpose {
    Project,
    TrustedIntake { cpu_millis: u64, memory_bytes: u64 },
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GuestJob {
    pub purpose: GuestPurpose,
    pub request: serde_json::Value,
    pub command: Vec<String>,
    pub environment: Vec<String>,
    pub working_directory: String,
    pub uid: u32,
    pub gid: u32,
    pub directories: Vec<String>,
    pub files: Vec<MaterialFile>,
}
