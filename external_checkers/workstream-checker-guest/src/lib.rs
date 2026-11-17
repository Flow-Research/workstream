//! Private node-to-guest bootstrap protocol. Not a project checker API.
use serde::{Deserialize, Serialize};

pub mod confinement;
pub mod pre_bootstrap;
pub mod trusted_root;

pub const MAX_JOB_BYTES: usize = 4 * 1024 * 1024;
pub const CAPACITY_EXIT_CODE: i32 = 201;
pub const INPUT_ROOT: &str = "/work/input";
pub const PREDECESSOR_ROOT: &str = "/work/context/predecessor";
pub const MODEL_SOCKET: &str = "/work/model.sock";
pub const EXECUTION_SOCKET: &str = "/work/execution.sock";
pub const GUEST_IO_PROTOCOL: &str = "workstream.smol_guest_io.v1";
pub const MODEL_FRAME_MAXIMUM: usize = 1024 * 1024;
pub const EXECUTION_FRAME_MAXIMUM: usize = 4 * 1024 * 1024;
pub const TRIAL_LIMITS_ARGUMENT: &str = "--trial-limits";
pub const TRIAL_LIMITS_MAXIMUM_BYTES: usize = 4096;
pub const TRIAL_OUTPUT_MAXIMUM_BYTES: u64 = 4 * 1024 * 1024;
pub const TRIAL_REQUEST_PROTOCOL: &str = "workstream.smol_trial_request.v1";
pub const TRIAL_CHILD_PROTOCOL: &str = "workstream.smol_trial_child.v1";
pub const TRIAL_EXPORT_PROTOCOL: &str = "workstream.smol_trial_export.v1";
/// Trusted supervisor, launcher PID 1 and one candidate process share this cap.
pub const MINIMUM_TRIAL_PIDS: u64 = 3;
/// Minimum independently bounded ext4 partition accepted by the trusted guest.
pub const MINIMUM_TRIAL_FILESYSTEM_BYTES: u64 = 4 * 1024 * 1024;
pub const MINIMUM_TRIAL_FILESYSTEM_ENTRIES: u64 = 32;

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct MaterialFile {
    pub normalized_path: String,
    pub byte_count: u64,
    pub sha256: String,
    pub executable: bool,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MaterialRoot {
    pub name: String,
    pub directories: Vec<String>,
    pub files: Vec<MaterialFile>,
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GuestCapabilities {
    pub model: bool,
    pub execution: bool,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum GuestPurpose {
    Project {
        capabilities: GuestCapabilities,
        materials: Vec<MaterialRoot>,
    },
    TrustedIntake {
        cpu_millis: u64,
        memory_bytes: u64,
    },
    TrialBuild {
        materials: Vec<MaterialRoot>,
    },
    TrialStep {
        materials: Vec<MaterialRoot>,
    },
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GuestJob {
    pub purpose: GuestPurpose,
    pub request: serde_json::Value,
    pub command: Vec<String>,
    pub environment: Vec<String>,
    pub working_directory: String,
    pub uid: u32,
    pub gid: u32,
    // Purpose-specific trusted intake material. Project and trial purposes
    // require these fields to be empty and carry typed roots in their payload.
    pub directories: Vec<String>,
    pub files: Vec<MaterialFile>,
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum GuestIoChannel {
    Model,
    Execution,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum GuestIoHeader {
    Request {
        protocol_version: String,
        sequence: u32,
        channel: GuestIoChannel,
        byte_count: u32,
    },
    Response {
        protocol_version: String,
        sequence: u32,
        channel: GuestIoChannel,
        byte_count: u32,
    },
    Completed {
        protocol_version: String,
        exit_code: Option<i32>,
        signal: Option<i32>,
        oom_kills: u64,
        output_exceeded: bool,
        stdout_bytes: u32,
        stderr_bytes: u32,
    },
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TrialFilesystemLimit {
    pub bytes: u64,
    pub entries: u64,
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct TrialChildLimits {
    pub cpu_quota_millis: u64,
    pub cpu_time_ms: u64,
    pub finalization_cpu_time_ms: u64,
    pub memory_bytes: u64,
    pub pids: u64,
    pub timeout_ms: u64,
    pub finalization_timeout_ms: u64,
    pub output_bytes: u64,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TrialVisibleRole {
    pub role: String,
    pub destination: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum TrialRequest {
    Build {
        schema_version: String,
        operation_id: String,
        context_relative: String,
        dockerfile_relative: String,
        platform: String,
        destination: String,
        limits: TrialChildLimits,
        root: TrialFilesystemLimit,
        tmp: TrialFilesystemLimit,
        shm: TrialFilesystemLimit,
        candidate_archive_max_bytes: u64,
        output_max_bytes: u64,
    },
    Step {
        schema_version: String,
        operation_id: String,
        visible_roles: Vec<TrialVisibleRole>,
        limits: TrialChildLimits,
        root: TrialFilesystemLimit,
        workspace: TrialFilesystemLimit,
        tmp: TrialFilesystemLimit,
        shm: TrialFilesystemLimit,
        output_max_bytes: u64,
    },
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TrialChildOutcome {
    pub exit_code: Option<i32>,
    pub signal: Option<i32>,
}

impl TrialChildOutcome {
    pub fn is_executed(self) -> bool {
        self.exit_code.is_some() != self.signal.is_some()
    }
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum TrialExportOutcome {
    Exported,
    CapacityExceeded,
    Invalid,
    Unavailable,
    NotStarted,
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum TrialTermination {
    Exited,
    Signalled,
    DeadlineExceeded,
    CpuExceeded,
    MemoryExceeded,
    PidExceeded,
    DiskExceeded,
    OutputExceeded,
}

impl TrialTermination {
    pub fn accepts(self, child: TrialChildOutcome) -> bool {
        match self {
            Self::Exited => child.exit_code.is_some() && child.signal.is_none(),
            Self::Signalled => child.exit_code.is_none() && child.signal.is_some(),
            Self::DeadlineExceeded
            | Self::CpuExceeded
            | Self::MemoryExceeded
            | Self::PidExceeded
            | Self::DiskExceeded
            | Self::OutputExceeded => child.exit_code.is_none() && child.signal.is_none(),
        }
    }
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum TrialExport {
    CandidateArchive {
        byte_count: u64,
        sha256: String,
    },
    Workspace {
        directories: Vec<String>,
        files: Vec<MaterialFile>,
    },
}

/// A bounded manifest for the raw payload preceding the final measurement.
/// Only a matching closed terminal result can admit this provisional export.
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TrialExportHeader {
    pub schema_version: String,
    pub operation_id: String,
    pub export: Option<TrialExport>,
    pub stdout_bytes: u64,
    pub stdout_sha256: String,
    pub stderr_bytes: u64,
    pub stderr_sha256: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TrialChildResult {
    pub schema_version: String,
    pub operation_id: String,
    pub child: TrialChildOutcome,
    pub termination: TrialTermination,
    pub elapsed_ms: u64,
    pub cpu_time_ms: u64,
    pub peak_memory_bytes: u64,
    pub peak_pids: u64,
    /// Transported as bounded raw bytes before this terminal frame.
    #[serde(skip)]
    pub stdout: String,
    pub stdout_sha256: String,
    pub stdout_bytes: u64,
    #[serde(skip)]
    pub stderr: String,
    pub stderr_sha256: String,
    pub stderr_bytes: u64,
    pub written_bytes: u64,
    pub written_entries: u64,
    pub measurement_method: String,
    pub export_outcome: TrialExportOutcome,
    pub export: Option<TrialExport>,
    pub guest_cleanup_confirmed: bool,
}

impl TrialChildResult {
    pub fn terminal_facts_are_valid(&self) -> bool {
        self.termination.accepts(self.child)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn project_capabilities_and_materials_are_explicit() {
        let job: GuestJob = serde_json::from_value(serde_json::json!({
            "purpose": {
                "kind": "project",
                "capabilities": {"model": true, "execution": false},
                "materials": [{"name": "current", "directories": [], "files": []}]
            },
            "request": {},
            "command": ["/checker"],
            "environment": [],
            "working_directory": "/",
            "uid": 65532,
            "gid": 65532,
            "directories": [],
            "files": []
        }))
        .unwrap();
        assert!(matches!(
            job.purpose,
            GuestPurpose::Project {
                capabilities: GuestCapabilities {
                    model: true,
                    execution: false
                },
                materials
            } if materials.len() == 1 && materials[0].name == "current"
        ));
    }

    #[test]
    fn guest_io_protocol_rejects_unknown_fields_and_channels() {
        let unknown_field = serde_json::json!({
            "kind": "request",
            "protocol_version": GUEST_IO_PROTOCOL,
            "sequence": 1,
            "channel": "model",
            "byte_count": 1,
            "provider_key": "forbidden"
        });
        assert!(serde_json::from_value::<GuestIoHeader>(unknown_field).is_err());
        let unknown_channel = serde_json::json!({
            "kind": "request",
            "protocol_version": GUEST_IO_PROTOCOL,
            "sequence": 1,
            "channel": "network",
            "byte_count": 1
        });
        assert!(serde_json::from_value::<GuestIoHeader>(unknown_channel).is_err());
    }

    #[test]
    fn trial_outcome_requires_exactly_one_terminal_child_fact() {
        assert!(TrialChildOutcome {
            exit_code: Some(0),
            signal: None,
        }
        .is_executed());
        assert!(TrialChildOutcome {
            exit_code: None,
            signal: Some(9),
        }
        .is_executed());
        assert!(!TrialChildOutcome {
            exit_code: None,
            signal: None,
        }
        .is_executed());
        assert!(TrialTermination::Exited.accepts(TrialChildOutcome {
            exit_code: Some(0),
            signal: None,
        }));
        assert!(
            TrialTermination::DeadlineExceeded.accepts(TrialChildOutcome {
                exit_code: None,
                signal: None,
            })
        );
        assert!(
            !TrialTermination::MemoryExceeded.accepts(TrialChildOutcome {
                exit_code: None,
                signal: Some(9),
            })
        );
        assert!(!TrialChildOutcome {
            exit_code: Some(1),
            signal: Some(9),
        }
        .is_executed());
    }
}
