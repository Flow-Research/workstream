//! Generic material projection and build/trial orchestration behind the relay.

use crate::trial_relay::{
    RoleInventoryDigest, TrialBuildObservation, TrialEngine, TrialEngineContext,
    TrialEngineFailure, TrialExecution, TrialExportOutcome, TrialOperationOutcome, TrialPlan,
    TrialRelayFailure, TrialResources, TrialStepObservation,
};
use serde_json::json;
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, HashMap};
use std::fs::{self, DirBuilder, File};
use std::io::Read;
use std::os::unix::fs::{DirBuilderExt, MetadataExt, OpenOptionsExt, PermissionsExt};
use std::path::{Component, Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::time::{Instant, SystemTime, UNIX_EPOCH};
use workstream_checker_sdk::canonical_hash;

static ENGINE_SEQUENCE: AtomicU64 = AtomicU64::new(0);

#[derive(Clone, Debug)]
pub(crate) struct SandboxBuildRequest {
    pub(crate) owner_id: String,
    pub(crate) context_root: PathBuf,
    pub(crate) context_relative: String,
    pub(crate) dockerfile_relative: String,
    pub(crate) output_archive: PathBuf,
    pub(crate) destination: String,
    pub(crate) platform: String,
    pub(crate) resources: TrialResources,
    pub(crate) remaining_cpu_time_ms: u64,
    pub(crate) mutable_disk_bytes: u64,
    pub(crate) mutable_entries: u64,
    pub(crate) launcher_root_bytes: u64,
    pub(crate) launcher_root_entries: u64,
    pub(crate) launcher_candidate_bytes: u64,
    pub(crate) launcher_temporary_bytes: u64,
    pub(crate) launcher_temporary_entries: u64,
    pub(crate) launcher_shared_memory_bytes: u64,
    pub(crate) launcher_shared_memory_entries: u64,
    pub(crate) timeout_ms: u64,
    pub(crate) maximum_output_bytes: usize,
    pub(crate) enforcement_overruns: SandboxEnforcementOverruns,
}

#[derive(Clone, Debug)]
pub(crate) struct SandboxStepRequest {
    pub(crate) owner_id: String,
    pub(crate) slot_id: String,
    pub(crate) candidate_image_digest: String,
    pub(crate) workspace_root: PathBuf,
    pub(crate) export_root: PathBuf,
    pub(crate) visible_roles: Vec<ProjectedRoleMount>,
    pub(crate) visible_role_inventory_digests: Vec<RoleInventoryDigest>,
    pub(crate) command: Vec<String>,
    pub(crate) working_directory: String,
    pub(crate) resources: TrialResources,
    pub(crate) remaining_cpu_time_ms: u64,
    pub(crate) mutable_disk_bytes: u64,
    pub(crate) mutable_entries: u64,
    pub(crate) launcher_root_bytes: u64,
    pub(crate) launcher_root_entries: u64,
    pub(crate) launcher_workspace_bytes: u64,
    pub(crate) launcher_workspace_entries: u64,
    pub(crate) launcher_temporary_bytes: u64,
    pub(crate) launcher_temporary_entries: u64,
    pub(crate) launcher_shared_memory_bytes: u64,
    pub(crate) launcher_shared_memory_entries: u64,
    pub(crate) timeout_ms: u64,
    pub(crate) maximum_output_bytes: usize,
    pub(crate) enforcement_overruns: SandboxEnforcementOverruns,
}

#[derive(Clone, Debug)]
pub(crate) struct ProjectedRoleMount {
    pub(crate) role: String,
    pub(crate) path: PathBuf,
    pub(crate) destination_relative: String,
}

#[derive(Clone, Debug)]
pub(crate) struct SandboxEnforcementOverruns {
    pub(crate) wall_time_ms: u64,
    pub(crate) cpu_time_ms: u64,
    pub(crate) memory_bytes: u64,
    pub(crate) pids: u64,
    pub(crate) disk_bytes: u64,
    pub(crate) entries: u64,
}

#[derive(Clone, Debug)]
pub(crate) struct SandboxBuildResult {
    pub(crate) observation: TrialBuildObservation,
    pub(crate) retained_image_bytes: u64,
    pub(crate) retained_image_entries: u64,
}

#[derive(Clone, Debug)]
pub(crate) struct SandboxStepResult {
    pub(crate) observation: TrialStepObservation,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) struct SandboxFailure {
    pub(crate) code: TrialRelayFailure,
    pub(crate) cleanup_unsettled: bool,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct SandboxBackendIdentity {
    pub(crate) engine_identity_digest: String,
    pub(crate) child_runtime: String,
    pub(crate) child_runtime_config_digest: String,
    pub(crate) child_host_uds: String,
    pub(crate) platform: String,
    pub(crate) platform_identity_digest: String,
    pub(crate) builder_image_digest: String,
    pub(crate) trusted_launcher_digest: String,
    pub(crate) offline_cache_digest: String,
    pub(crate) approved_base_digests: Vec<String>,
}

pub(crate) trait TrialSandboxBackend: Send + Sync + 'static {
    fn identity(&self) -> SandboxBackendIdentity;

    fn build(
        &self,
        request: &SandboxBuildRequest,
        deadline: Instant,
        invocation_cancelled: &AtomicBool,
        relay_cancelled: &AtomicBool,
    ) -> Result<SandboxBuildResult, SandboxFailure>;

    fn run_step(
        &self,
        request: &SandboxStepRequest,
        operation_order: u32,
        deadline: Instant,
        invocation_cancelled: &AtomicBool,
        relay_cancelled: &AtomicBool,
    ) -> Result<SandboxStepResult, SandboxFailure>;

    fn cleanup(&self, owner_id: &str, deadline: Instant) -> Result<(), SandboxFailure>;
}

pub(crate) struct GenericTrialEngine<B: TrialSandboxBackend> {
    backend: B,
}

impl<B: TrialSandboxBackend> GenericTrialEngine<B> {
    pub(crate) fn new(backend: B) -> Self {
        Self { backend }
    }
}

impl<B: TrialSandboxBackend> TrialEngine for GenericTrialEngine<B> {
    fn execute(
        &self,
        context: &TrialEngineContext,
        plan: &TrialPlan,
        deadline: Instant,
        invocation_cancelled: &AtomicBool,
        relay_cancelled: &AtomicBool,
    ) -> Result<TrialExecution, TrialEngineFailure> {
        let owned =
            OwnedTrialScratch::create(&context.trial_scratch_root).map_err(engine_failure)?;
        let owner_id = owned.owner_id.clone();
        let result = self.execute_owned(
            context,
            plan,
            &owned,
            deadline,
            invocation_cancelled,
            relay_cancelled,
        );
        let backend_cleanup = self.backend.cleanup(&owner_id, deadline);
        let scratch_cleanup = owned.cleanup();
        match (result, backend_cleanup, scratch_cleanup) {
            (Ok(mut execution), Ok(()), true) => {
                execution.cleanup_confirmed = true;
                Ok(execution)
            }
            (Err(mut failure), backend, scratch) => {
                failure.cleanup_unsettled |= backend.is_err() || !scratch;
                Err(failure)
            }
            (Ok(_), _, _) => Err(TrialEngineFailure {
                code: TrialRelayFailure::CleanupUnsettled,
                cleanup_unsettled: true,
            }),
        }
    }
}

impl<B: TrialSandboxBackend> GenericTrialEngine<B> {
    #[allow(clippy::too_many_arguments)]
    fn execute_owned(
        &self,
        context: &TrialEngineContext,
        plan: &TrialPlan,
        owned: &OwnedTrialScratch,
        deadline: Instant,
        invocation_cancelled: &AtomicBool,
        relay_cancelled: &AtomicBool,
    ) -> Result<TrialExecution, TrialEngineFailure> {
        require_available(deadline, invocation_cancelled, relay_cancelled)?;
        let backend = self.backend.identity();
        if backend.engine_identity_digest != context.profile.engine_identity_digest
            || backend.child_runtime != context.profile.child_runtime
            || backend.child_runtime_config_digest != context.profile.child_runtime_config_digest
            || backend.child_host_uds != context.profile.child_host_uds
            || backend.platform != context.profile.platform
            || backend.platform_identity_digest != context.profile.platform_identity_digest
            || backend.builder_image_digest != context.profile.builder_image_digest
            || backend.trusted_launcher_digest != context.profile.trusted_launcher_digest
            || backend.offline_cache_digest != context.profile.offline_cache_digest
            || backend.approved_base_digests != context.profile.approved_base_digests
        {
            return Err(implementation_failure());
        }
        inspect_roles(
            &context.verified_material_root,
            &context.profile.source_material_roles,
            plan.resources.maximum_entries,
            plan.resources.disk_bytes,
        )?;
        let mut invocation_budget =
            ProjectionBudget::new(plan.resources.maximum_entries, plan.resources.disk_bytes);
        let projections = materialize_projections(context, owned, &mut invocation_budget)?;
        let inventories = projection_inventories(
            &projections,
            plan.resources.maximum_entries,
            plan.resources.disk_bytes,
        )?;
        let projected = owned.root.join("context");
        create_accounted_directory(&projected, &mut invocation_budget)?;
        for role in &context.profile.build_context_roles {
            let source = projections.get(role).ok_or_else(implementation_failure)?;
            copy_projection(
                &source.path,
                &projected,
                &source.destination_relative,
                &mut invocation_budget,
            )?;
        }
        let output = owned.root.join("output");
        create_accounted_directory(&output, &mut invocation_budget)?;
        create_accounted_directory(&owned.root.join("workspaces"), &mut invocation_budget)?;
        create_accounted_directory(&owned.root.join("exports"), &mut invocation_budget)?;
        let archive = output.join("candidate.tar");
        let destination = format!("workstream-trial:{}", &owned.owner_id[6..]);
        let (build_disk_bytes, build_entries) = invocation_budget.mutable_allowance(&output)?;
        let build_allowances = invocation_budget.build_allowances()?;
        let mut cpu_time_used = 0_u64;
        let build = self
            .backend
            .build(
                &SandboxBuildRequest {
                    owner_id: owned.owner_id.clone(),
                    context_root: projected,
                    context_relative: plan.environment.context.clone(),
                    dockerfile_relative: plan.environment.dockerfile.clone(),
                    output_archive: archive,
                    destination,
                    platform: plan.environment.platform.clone(),
                    resources: plan.resources.clone(),
                    remaining_cpu_time_ms: plan.resources.cpu_time_ms,
                    mutable_disk_bytes: build_disk_bytes,
                    mutable_entries: build_entries,
                    launcher_root_bytes: build_allowances.root_bytes,
                    launcher_root_entries: build_allowances.root_entries,
                    launcher_candidate_bytes: build_allowances.candidate_bytes,
                    launcher_temporary_bytes: build_allowances.temporary_bytes,
                    launcher_temporary_entries: build_allowances.temporary_entries,
                    launcher_shared_memory_bytes: build_allowances.shared_memory_bytes,
                    launcher_shared_memory_entries: build_allowances.shared_memory_entries,
                    timeout_ms: plan.build_timeout_ms,
                    maximum_output_bytes: context.profile.maximum_step_output_bytes,
                    enforcement_overruns: overruns(context),
                },
                deadline,
                invocation_cancelled,
                relay_cancelled,
            )
            .map_err(|value| sandbox_failure("build", value))?;
        cpu_time_used = charge_cpu_time(
            cpu_time_used,
            build.observation.cpu_time_ms,
            plan.resources.cpu_time_ms,
            context.profile.maximum_cpu_time_overrun_ms,
            build.observation.outcome == TrialOperationOutcome::CpuExceeded,
        )?;
        invocation_budget.refresh(
            &owned.root,
            context.profile.maximum_disk_overrun_bytes,
            context.profile.maximum_entries_overrun,
            build.observation.outcome == TrialOperationOutcome::DiskExceeded,
        )?;
        invocation_budget
            .reserve_retained(build.retained_image_bytes, build.retained_image_entries)?;
        let mut steps = Vec::with_capacity(plan.steps.len());
        let mut workspaces: HashMap<String, PathBuf> = HashMap::new();
        let inventory_by_role: HashMap<_, _> = inventories
            .iter()
            .map(|item| (item.role.as_str(), item.digest.as_str()))
            .collect();
        if build.observation.outcome != TrialOperationOutcome::Succeeded {
            for (index, step) in plan.steps.iter().enumerate() {
                steps.push(skipped_observation(step, index, &inventory_by_role)?);
            }
        } else {
            let candidate = build
                .observation
                .candidate_image_digest
                .clone()
                .ok_or_else(implementation_failure)?;
            let mut invocation_capacity_exhausted = false;
            for (index, step) in plan.steps.iter().enumerate() {
                let slot_profile = context
                    .profile
                    .slot_templates
                    .iter()
                    .find(|template| template.slot_kind == step.slot_kind)
                    .ok_or_else(implementation_failure)?;
                require_available(deadline, invocation_cancelled, relay_cancelled)?;
                if cpu_time_used >= plan.resources.cpu_time_ms || invocation_capacity_exhausted {
                    steps.push(skipped_observation(step, index, &inventory_by_role)?);
                    continue;
                }
                if step.state_source != "fresh" && !workspaces.contains_key(&step.state_source) {
                    steps.push(skipped_observation(step, index, &inventory_by_role)?);
                    continue;
                }
                let workspace = owned.root.join("workspaces").join(&step.slot_id);
                let export_root = owned.root.join("exports").join(&step.slot_id);
                if step.state_source == "fresh" {
                    create_accounted_directory(&workspace, &mut invocation_budget)?;
                    for role in &slot_profile.seed_roles {
                        let source = projections.get(role).ok_or_else(implementation_failure)?;
                        copy_projection(
                            &source.path,
                            &workspace,
                            &source.destination_relative,
                            &mut invocation_budget,
                        )?;
                    }
                } else {
                    let source = workspaces
                        .get(&step.state_source)
                        .ok_or_else(implementation_failure)?;
                    copy_tree(source, &workspace, &mut invocation_budget)?;
                }
                let (mutable_disk_bytes, mutable_entries) =
                    invocation_budget.mutable_allowance(&workspace)?;
                create_accounted_directory(&export_root, &mut invocation_budget)?;
                let step_allowances = invocation_budget
                    .step_allowances(&workspace, step.visible_roles.len() as u64)?;
                let visible_roles = step
                    .visible_roles
                    .iter()
                    .map(|role| {
                        let projection =
                            projections.get(role).ok_or_else(implementation_failure)?;
                        Ok(ProjectedRoleMount {
                            role: role.clone(),
                            path: projection.path.clone(),
                            destination_relative: projection.destination_relative.clone(),
                        })
                    })
                    .collect::<Result<Vec<_>, TrialEngineFailure>>()?;
                let visible_role_inventory_digests = step
                    .visible_roles
                    .iter()
                    .map(|role| {
                        inventory_by_role
                            .get(role.as_str())
                            .map(|digest| RoleInventoryDigest {
                                role: role.clone(),
                                digest: (*digest).to_owned(),
                            })
                            .ok_or_else(implementation_failure)
                    })
                    .collect::<Result<Vec<_>, _>>()?;
                let result = self
                    .backend
                    .run_step(
                        &SandboxStepRequest {
                            owner_id: owned.owner_id.clone(),
                            slot_id: step.slot_id.clone(),
                            candidate_image_digest: candidate.clone(),
                            workspace_root: workspace.clone(),
                            export_root,
                            visible_roles,
                            visible_role_inventory_digests,
                            command: step.command.clone(),
                            working_directory: step.working_directory.clone(),
                            resources: plan.resources.clone(),
                            remaining_cpu_time_ms: plan
                                .resources
                                .cpu_time_ms
                                .checked_sub(cpu_time_used)
                                .ok_or_else(capacity_failure)?,
                            mutable_disk_bytes,
                            mutable_entries,
                            launcher_root_bytes: step_allowances.root_bytes,
                            launcher_root_entries: step_allowances.root_entries,
                            launcher_workspace_bytes: step_allowances.workspace_bytes,
                            launcher_workspace_entries: step_allowances.workspace_entries,
                            launcher_temporary_bytes: step_allowances.temporary_bytes,
                            launcher_temporary_entries: step_allowances.temporary_entries,
                            launcher_shared_memory_bytes: step_allowances.shared_memory_bytes,
                            launcher_shared_memory_entries: step_allowances.shared_memory_entries,
                            timeout_ms: step.timeout_ms,
                            maximum_output_bytes: context.profile.maximum_step_output_bytes,
                            enforcement_overruns: overruns(context),
                        },
                        (index + 1) as u32,
                        deadline,
                        invocation_cancelled,
                        relay_cancelled,
                    )
                    .map_err(|value| sandbox_failure("step", value))?;
                let outcome = result.observation.outcome;
                invocation_capacity_exhausted = outcome == TrialOperationOutcome::DiskExceeded;
                cpu_time_used = charge_cpu_time(
                    cpu_time_used,
                    result.observation.cpu_time_ms,
                    plan.resources.cpu_time_ms,
                    context.profile.maximum_cpu_time_overrun_ms,
                    outcome == TrialOperationOutcome::CpuExceeded,
                )?;
                invocation_budget.refresh(
                    &owned.root,
                    context.profile.maximum_disk_overrun_bytes,
                    context.profile.maximum_entries_overrun,
                    outcome == TrialOperationOutcome::DiskExceeded,
                )?;
                let export_outcome = result.observation.export_outcome;
                steps.push(result.observation);
                let retain = export_outcome == TrialExportOutcome::Exported
                    && slot_profile
                        .retain_state_after
                        .iter()
                        .any(|allowed| allowed == operation_outcome_name(outcome));
                if retain {
                    workspaces.insert(step.slot_id.clone(), workspace);
                } else {
                    fs::remove_dir_all(&workspace).map_err(|_| implementation_failure())?;
                    invocation_budget.refresh(&owned.root, 0, 0, false)?;
                }
            }
        }
        if steps.len() != plan.steps.len() {
            return Err(implementation_failure());
        }
        Ok(TrialExecution {
            platform_identity_digest: context.profile.platform_identity_digest.clone(),
            builder_image_digest: context.profile.builder_image_digest.clone(),
            trusted_launcher_digest: context.profile.trusted_launcher_digest.clone(),
            offline_cache_digest: context.profile.offline_cache_digest.clone(),
            base_image_digests: context.profile.approved_base_digests.clone(),
            material_inventory_digests: inventories,
            build: build.observation,
            steps,
            cleanup_confirmed: false,
        })
    }
}

fn overruns(context: &TrialEngineContext) -> SandboxEnforcementOverruns {
    SandboxEnforcementOverruns {
        wall_time_ms: context.profile.maximum_wall_time_overrun_ms,
        cpu_time_ms: context.profile.maximum_cpu_time_overrun_ms,
        memory_bytes: context.profile.maximum_memory_overrun_bytes,
        pids: context.profile.maximum_pids_overrun,
        disk_bytes: context.profile.maximum_disk_overrun_bytes,
        entries: context.profile.maximum_entries_overrun,
    }
}

fn skipped_observation(
    step: &crate::trial_relay::TrialStep,
    index: usize,
    inventories: &HashMap<&str, &str>,
) -> Result<TrialStepObservation, TrialEngineFailure> {
    let empty = sha256_bytes(b"");
    let visible_role_inventory_digests = step
        .visible_roles
        .iter()
        .map(|role| {
            inventories
                .get(role.as_str())
                .map(|digest| RoleInventoryDigest {
                    role: role.clone(),
                    digest: (*digest).to_owned(),
                })
                .ok_or_else(implementation_failure)
        })
        .collect::<Result<Vec<_>, _>>()?;
    Ok(TrialStepObservation {
        slot_id: step.slot_id.clone(),
        operation_order: (index + 1) as u32,
        workspace_identity: format!("skipped_{}", step.slot_id),
        visible_role_inventory_digests,
        outcome: TrialOperationOutcome::DependencySkipped,
        exit_code: None,
        signal: None,
        stdout: String::new(),
        stdout_sha256: empty.clone(),
        stderr: String::new(),
        stderr_sha256: empty,
        workspace_before_sha256: sha256_bytes(b"dependency-skipped"),
        workspace_after_sha256: sha256_bytes(b"dependency-skipped"),
        export_outcome: TrialExportOutcome::NotStarted,
        elapsed_ms: 0,
        cpu_time_ms: 0,
        peak_memory_bytes: 0,
        peak_pids: 0,
        written_bytes: 0,
        written_entries: 0,
        measurement_method: "not_started".into(),
    })
}

struct OwnedTrialScratch {
    owner_id: String,
    root: PathBuf,
    device: u64,
    inode: u64,
}

impl OwnedTrialScratch {
    fn create(parent: &Path) -> Result<Self, TrialRelayFailure> {
        for _ in 0..32 {
            let sequence = ENGINE_SEQUENCE.fetch_add(1, Ordering::Relaxed);
            let time = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .map_err(|_| TrialRelayFailure::ImplementationUnavailable)?
                .as_nanos();
            let owner_id = format!("trial_{:016x}{:016x}", time as u64, sequence);
            let root = parent.join(&owner_id);
            let mut builder = DirBuilder::new();
            builder.mode(0o700);
            match builder.create(&root) {
                Ok(()) => {
                    let metadata = fs::symlink_metadata(&root)
                        .map_err(|_| TrialRelayFailure::ImplementationUnavailable)?;
                    return Ok(Self {
                        owner_id,
                        root,
                        device: metadata.dev(),
                        inode: metadata.ino(),
                    });
                }
                Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
                Err(_) => return Err(TrialRelayFailure::ImplementationUnavailable),
            }
        }
        Err(TrialRelayFailure::CapacityExceeded)
    }

    fn cleanup(self) -> bool {
        let Ok(metadata) = fs::symlink_metadata(&self.root) else {
            return false;
        };
        if !metadata.file_type().is_dir()
            || metadata.file_type().is_symlink()
            || metadata.dev() != self.device
            || metadata.ino() != self.inode
        {
            return false;
        }
        fs::remove_dir_all(&self.root).is_ok()
    }
}

struct MaterializedProjection {
    path: PathBuf,
    destination_relative: String,
}

fn materialize_projections(
    context: &TrialEngineContext,
    owned: &OwnedTrialScratch,
    budget: &mut ProjectionBudget,
) -> Result<HashMap<String, MaterializedProjection>, TrialEngineFailure> {
    let root = owned.root.join("projections");
    create_accounted_directory(&root, budget)?;
    let mut projected = HashMap::new();
    for projection in &context.profile.material_projections {
        let source = context
            .verified_material_root
            .join(&projection.source_role)
            .join(&projection.source_relative);
        let destination = root.join(&projection.role);
        let exclusions = projection
            .exclusions
            .iter()
            .map(PathBuf::from)
            .collect::<Vec<_>>();
        copy_tree_filtered(&source, &destination, Path::new(""), &exclusions, budget)?;
        if projected
            .insert(
                projection.role.clone(),
                MaterializedProjection {
                    path: destination,
                    destination_relative: projection.destination_relative.clone(),
                },
            )
            .is_some()
        {
            return Err(implementation_failure());
        }
    }
    Ok(projected)
}

fn projection_inventories(
    projections: &HashMap<String, MaterializedProjection>,
    maximum_entries: u64,
    maximum_bytes: u64,
) -> Result<Vec<RoleInventoryDigest>, TrialEngineFailure> {
    let mut roles = projections.keys().collect::<Vec<_>>();
    roles.sort();
    let mut budget = ProjectionBudget::new(maximum_entries, maximum_bytes);
    roles
        .into_iter()
        .map(|role| {
            let mut inventory = Vec::new();
            inspect_tree(
                &projections[role].path,
                Path::new(""),
                &mut inventory,
                &mut budget,
            )?;
            Ok(RoleInventoryDigest {
                role: role.clone(),
                digest: canonical_hash(&json!(inventory)).map_err(|_| implementation_failure())?,
            })
        })
        .collect()
}

fn copy_tree_filtered(
    source: &Path,
    destination: &Path,
    relative: &Path,
    exclusions: &[PathBuf],
    budget: &mut ProjectionBudget,
) -> Result<(), TrialEngineFailure> {
    if exclusions.iter().any(|value| value == relative) {
        return Ok(());
    }
    let metadata = fs::symlink_metadata(source).map_err(|_| material_failure())?;
    if metadata.file_type().is_symlink() {
        return Err(material_failure());
    }
    if metadata.file_type().is_dir() {
        budget.charge(0)?;
        create_private_directory(destination)?;
        let mut children: BTreeMap<_, _> = BTreeMap::new();
        for entry in fs::read_dir(source).map_err(|_| material_failure())? {
            let entry = entry.map_err(|_| material_failure())?;
            children.insert(entry.file_name(), entry.path());
        }
        for (name, path) in children {
            if !safe_component(&name) {
                return Err(material_failure());
            }
            copy_tree_filtered(
                &path,
                &destination.join(&name),
                &relative.join(name),
                exclusions,
                budget,
            )?;
        }
    } else if metadata.file_type().is_file() {
        budget.charge(metadata.len())?;
        copy_regular(
            source,
            destination,
            metadata.permissions().mode() & 0o111 != 0,
        )?;
    } else {
        return Err(material_failure());
    }
    Ok(())
}

fn copy_projection(
    source: &Path,
    destination_root: &Path,
    destination_relative: &str,
    budget: &mut ProjectionBudget,
) -> Result<(), TrialEngineFailure> {
    if destination_relative != "." {
        return copy_tree(source, &destination_root.join(destination_relative), budget);
    }
    let metadata = fs::symlink_metadata(source).map_err(|_| material_failure())?;
    if !metadata.file_type().is_dir() || metadata.file_type().is_symlink() {
        return Err(material_failure());
    }
    let mut children: BTreeMap<_, _> = BTreeMap::new();
    for entry in fs::read_dir(source).map_err(|_| material_failure())? {
        let entry = entry.map_err(|_| material_failure())?;
        children.insert(entry.file_name(), entry.path());
    }
    for (name, path) in children {
        if !safe_component(&name) {
            return Err(material_failure());
        }
        copy_tree(&path, &destination_root.join(name), budget)?;
    }
    Ok(())
}

fn operation_outcome_name(outcome: TrialOperationOutcome) -> &'static str {
    match outcome {
        TrialOperationOutcome::Succeeded => "succeeded",
        TrialOperationOutcome::ExitNonzero => "exit_nonzero",
        TrialOperationOutcome::Signalled => "signalled",
        TrialOperationOutcome::DeadlineExceeded => "deadline_exceeded",
        TrialOperationOutcome::CpuExceeded => "cpu_exceeded",
        TrialOperationOutcome::MemoryExceeded => "memory_exceeded",
        TrialOperationOutcome::PidExceeded => "pid_exceeded",
        TrialOperationOutcome::DiskExceeded => "disk_exceeded",
        TrialOperationOutcome::OutputExceeded => "output_exceeded",
        TrialOperationOutcome::ExportInvalid => "export_invalid",
        TrialOperationOutcome::DependencySkipped => "dependency_skipped",
    }
}

#[derive(Clone, Copy)]
struct ProjectionBudget {
    maximum_entries: u64,
    maximum_bytes: u64,
    retained_entries: u64,
    retained_bytes: u64,
    entries_left: u64,
    bytes_left: u64,
}

const LAUNCHER_BOOTSTRAP_BYTES: u64 = 64 * 1024;
// The trusted bootstrap has a fixed mount skeleton; submitted code never sees
// it. Charge every launcher-created top-level entry conservatively.
const LAUNCHER_BOOTSTRAP_ENTRIES: u64 = 8;
const MINIMUM_TMPFS_BYTES: u64 = 4096;

struct BuildAllowances {
    root_bytes: u64,
    root_entries: u64,
    candidate_bytes: u64,
    temporary_bytes: u64,
    temporary_entries: u64,
    shared_memory_bytes: u64,
    shared_memory_entries: u64,
}

struct StepAllowances {
    root_bytes: u64,
    root_entries: u64,
    workspace_bytes: u64,
    workspace_entries: u64,
    temporary_bytes: u64,
    temporary_entries: u64,
    shared_memory_bytes: u64,
    shared_memory_entries: u64,
}

impl ProjectionBudget {
    fn new(entries: u64, bytes: u64) -> Self {
        Self {
            maximum_entries: entries,
            maximum_bytes: bytes,
            retained_entries: 0,
            retained_bytes: 0,
            entries_left: entries,
            bytes_left: bytes,
        }
    }

    fn charge(&mut self, bytes: u64) -> Result<(), TrialEngineFailure> {
        self.entries_left = self
            .entries_left
            .checked_sub(1)
            .ok_or_else(capacity_failure)?;
        self.bytes_left = self
            .bytes_left
            .checked_sub(bytes)
            .ok_or_else(capacity_failure)?;
        Ok(())
    }

    fn mutable_allowance(&self, root: &Path) -> Result<(u64, u64), TrialEngineFailure> {
        let (root_bytes, root_entries) = owned_tree_usage(root)?;
        Ok((
            root_bytes
                .checked_add(self.bytes_left)
                .ok_or_else(capacity_failure)?,
            root_entries
                .checked_add(self.entries_left)
                .ok_or_else(capacity_failure)?,
        ))
    }

    fn build_allowances(&self) -> Result<BuildAllowances, TrialEngineFailure> {
        let remaining_bytes = self
            .bytes_left
            .checked_sub(LAUNCHER_BOOTSTRAP_BYTES + MINIMUM_TMPFS_BYTES)
            .and_then(|value| value.checked_sub(MINIMUM_TMPFS_BYTES))
            .ok_or_else(capacity_failure)?;
        let temporary_bytes = (remaining_bytes / 8).clamp(MINIMUM_TMPFS_BYTES, 16 * 1024 * 1024);
        let shared_memory_bytes = (remaining_bytes / 16).clamp(MINIMUM_TMPFS_BYTES, 1024 * 1024);
        let root_and_candidate = self
            .bytes_left
            .checked_sub(LAUNCHER_BOOTSTRAP_BYTES)
            .and_then(|value| value.checked_sub(temporary_bytes))
            .and_then(|value| value.checked_sub(shared_memory_bytes))
            .ok_or_else(capacity_failure)?;
        let candidate_bytes = root_and_candidate / 3;
        let root_bytes = root_and_candidate
            .checked_sub(candidate_bytes)
            .ok_or_else(capacity_failure)?;
        if candidate_bytes == 0 || root_bytes < candidate_bytes {
            return Err(capacity_failure());
        }

        let entries_after_bootstrap = self
            .entries_left
            .checked_sub(LAUNCHER_BOOTSTRAP_ENTRIES)
            .and_then(|value| value.checked_sub(1))
            .ok_or_else(capacity_failure)?;
        let temporary_entries = (entries_after_bootstrap / 8).clamp(4, 256);
        let shared_memory_entries = (entries_after_bootstrap / 16).clamp(4, 64);
        let root_entries = entries_after_bootstrap
            .checked_sub(temporary_entries)
            .and_then(|value| value.checked_sub(shared_memory_entries))
            .ok_or_else(capacity_failure)?;
        if root_entries < 32 {
            return Err(capacity_failure());
        }
        Ok(BuildAllowances {
            root_bytes,
            root_entries,
            candidate_bytes,
            temporary_bytes,
            temporary_entries,
            shared_memory_bytes,
            shared_memory_entries,
        })
    }

    fn step_allowances(
        &self,
        workspace: &Path,
        visible_role_count: u64,
    ) -> Result<StepAllowances, TrialEngineFailure> {
        let bootstrap_entries = LAUNCHER_BOOTSTRAP_ENTRIES
            .checked_add(visible_role_count)
            .ok_or_else(capacity_failure)?;
        let root_entries = self
            .retained_entries
            .checked_add(16)
            .map(|value| value.max(32))
            .ok_or_else(capacity_failure)?;
        let root_bytes = root_entries
            .checked_mul(4096)
            .map(|value| value.max(64 * 1024))
            .ok_or_else(capacity_failure)?;
        let bytes_after_fixed = self
            .bytes_left
            .checked_sub(LAUNCHER_BOOTSTRAP_BYTES)
            .and_then(|value| value.checked_sub(root_bytes))
            .ok_or_else(capacity_failure)?;
        let temporary_bytes = (bytes_after_fixed / 8).clamp(MINIMUM_TMPFS_BYTES, 16 * 1024 * 1024);
        let shared_memory_bytes = (bytes_after_fixed / 16).clamp(MINIMUM_TMPFS_BYTES, 1024 * 1024);
        let workspace_bytes = self
            .bytes_left
            .checked_sub(LAUNCHER_BOOTSTRAP_BYTES)
            .and_then(|value| value.checked_sub(root_bytes))
            .and_then(|value| value.checked_sub(temporary_bytes))
            .and_then(|value| value.checked_sub(shared_memory_bytes))
            .ok_or_else(capacity_failure)?
            / 2;

        let entries_after_fixed = self
            .entries_left
            .checked_sub(bootstrap_entries)
            .and_then(|value| value.checked_sub(root_entries))
            .ok_or_else(capacity_failure)?;
        let temporary_entries = (entries_after_fixed / 8).clamp(4, 256);
        let shared_memory_entries = (entries_after_fixed / 16).clamp(4, 64);
        let workspace_entries = entries_after_fixed
            .checked_sub(temporary_entries)
            .and_then(|value| value.checked_sub(shared_memory_entries))
            .ok_or_else(capacity_failure)?
            / 2;
        let (existing_bytes, existing_entries) = owned_tree_usage(workspace)?;
        if workspace_bytes < existing_bytes || workspace_entries < existing_entries {
            return Err(capacity_failure());
        }
        Ok(StepAllowances {
            root_bytes,
            root_entries,
            workspace_bytes,
            workspace_entries,
            temporary_bytes,
            temporary_entries,
            shared_memory_bytes,
            shared_memory_entries,
        })
    }

    fn reserve_retained(&mut self, bytes: u64, entries: u64) -> Result<(), TrialEngineFailure> {
        self.retained_bytes = self
            .retained_bytes
            .checked_add(bytes)
            .ok_or_else(capacity_failure)?;
        self.retained_entries = self
            .retained_entries
            .checked_add(entries)
            .ok_or_else(capacity_failure)?;
        self.bytes_left = self
            .bytes_left
            .checked_sub(bytes)
            .ok_or_else(capacity_failure)?;
        self.entries_left = self
            .entries_left
            .checked_sub(entries)
            .ok_or_else(capacity_failure)?;
        Ok(())
    }

    fn refresh(
        &mut self,
        root: &Path,
        bytes_overrun: u64,
        entries_overrun: u64,
        exceeded: bool,
    ) -> Result<(), TrialEngineFailure> {
        let (bytes, entries) = owned_tree_usage(root)?;
        let maximum_bytes = self
            .maximum_bytes
            .checked_add(if exceeded { bytes_overrun } else { 0 })
            .ok_or_else(capacity_failure)?;
        let maximum_entries = self
            .maximum_entries
            .checked_add(if exceeded { entries_overrun } else { 0 })
            .ok_or_else(capacity_failure)?;
        let total_bytes = bytes
            .checked_add(self.retained_bytes)
            .ok_or_else(capacity_failure)?;
        let total_entries = entries
            .checked_add(self.retained_entries)
            .ok_or_else(capacity_failure)?;
        if total_bytes > maximum_bytes || total_entries > maximum_entries {
            return Err(capacity_failure());
        }
        self.bytes_left = self.maximum_bytes.saturating_sub(total_bytes);
        self.entries_left = self.maximum_entries.saturating_sub(total_entries);
        Ok(())
    }
}

fn owned_tree_usage(root: &Path) -> Result<(u64, u64), TrialEngineFailure> {
    let metadata = fs::symlink_metadata(root).map_err(|_| implementation_failure())?;
    if metadata.file_type().is_symlink() || !metadata.file_type().is_dir() {
        return Err(implementation_failure());
    }
    let mut bytes = 0_u64;
    let mut entries = 0_u64;
    let mut children = fs::read_dir(root)
        .map_err(|_| implementation_failure())?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|_| implementation_failure())?;
    children.sort_by_key(std::fs::DirEntry::file_name);
    for child in children {
        owned_entry_usage(&child.path(), &mut bytes, &mut entries)?;
    }
    Ok((bytes, entries))
}

fn owned_entry_usage(
    path: &Path,
    bytes: &mut u64,
    entries: &mut u64,
) -> Result<(), TrialEngineFailure> {
    let metadata = fs::symlink_metadata(path).map_err(|_| implementation_failure())?;
    if metadata.file_type().is_symlink() {
        return Err(implementation_failure());
    }
    *entries = entries.checked_add(1).ok_or_else(capacity_failure)?;
    if metadata.file_type().is_file() {
        *bytes = bytes
            .checked_add(metadata.len())
            .ok_or_else(capacity_failure)?;
    } else if metadata.file_type().is_dir() {
        let mut children = fs::read_dir(path)
            .map_err(|_| implementation_failure())?
            .collect::<Result<Vec<_>, _>>()
            .map_err(|_| implementation_failure())?;
        children.sort_by_key(std::fs::DirEntry::file_name);
        for child in children {
            owned_entry_usage(&child.path(), bytes, entries)?;
        }
    } else {
        return Err(implementation_failure());
    }
    Ok(())
}

fn charge_cpu_time(
    used: u64,
    observed: u64,
    maximum: u64,
    overrun: u64,
    exceeded: bool,
) -> Result<u64, TrialEngineFailure> {
    let total = used.checked_add(observed).ok_or_else(capacity_failure)?;
    let allowed = maximum
        .checked_add(if exceeded { overrun } else { 0 })
        .ok_or_else(capacity_failure)?;
    if total > allowed {
        return Err(capacity_failure());
    }
    Ok(total)
}

fn inspect_roles(
    root: &Path,
    roles: &[String],
    maximum_entries: u64,
    maximum_bytes: u64,
) -> Result<Vec<RoleInventoryDigest>, TrialEngineFailure> {
    let mut results = Vec::with_capacity(roles.len());
    let mut budget = ProjectionBudget::new(maximum_entries, maximum_bytes);
    for role in roles {
        let mut inventory = Vec::new();
        inspect_tree(&root.join(role), Path::new(""), &mut inventory, &mut budget)?;
        let digest = canonical_hash(&json!(inventory)).map_err(|_| implementation_failure())?;
        results.push(RoleInventoryDigest {
            role: role.clone(),
            digest,
        });
    }
    Ok(results)
}

fn inspect_tree(
    root: &Path,
    relative: &Path,
    inventory: &mut Vec<serde_json::Value>,
    budget: &mut ProjectionBudget,
) -> Result<(), TrialEngineFailure> {
    let path = root.join(relative);
    let metadata = fs::symlink_metadata(&path).map_err(|_| material_failure())?;
    if metadata.file_type().is_symlink() {
        return Err(material_failure());
    }
    if metadata.file_type().is_file() {
        budget.charge(metadata.len())?;
        let digest = hash_file(&path)?;
        inventory.push(json!({
            "path": normalized(relative)?, "kind": "file", "bytes": metadata.len(),
            "sha256": digest, "executable": metadata.permissions().mode() & 0o111 != 0,
        }));
        return Ok(());
    }
    if !metadata.file_type().is_dir() {
        return Err(material_failure());
    }
    if !relative.as_os_str().is_empty() {
        budget.charge(0)?;
        inventory.push(json!({"path": normalized(relative)?, "kind": "directory"}));
    }
    let mut children: BTreeMap<_, _> = BTreeMap::new();
    for entry in fs::read_dir(&path).map_err(|_| material_failure())? {
        let entry = entry.map_err(|_| material_failure())?;
        children.insert(entry.file_name(), entry.path());
    }
    for name in children.keys() {
        let next = relative.join(name);
        if !safe_relative(&next) {
            return Err(material_failure());
        }
        inspect_tree(root, &next, inventory, budget)?;
    }
    Ok(())
}

fn copy_tree(
    source: &Path,
    destination: &Path,
    budget: &mut ProjectionBudget,
) -> Result<(), TrialEngineFailure> {
    let metadata = fs::symlink_metadata(source).map_err(|_| material_failure())?;
    if metadata.file_type().is_symlink() {
        return Err(material_failure());
    }
    if metadata.file_type().is_dir() {
        budget.charge(0)?;
        create_private_directory(destination)?;
        let mut children: BTreeMap<_, _> = BTreeMap::new();
        for entry in fs::read_dir(source).map_err(|_| material_failure())? {
            let entry = entry.map_err(|_| material_failure())?;
            children.insert(entry.file_name(), entry.path());
        }
        for (name, path) in children {
            if !safe_component(&name) {
                return Err(material_failure());
            }
            copy_tree(&path, &destination.join(name), budget)?;
        }
    } else if metadata.file_type().is_file() {
        budget.charge(metadata.len())?;
        copy_regular(
            source,
            destination,
            metadata.permissions().mode() & 0o111 != 0,
        )?;
    } else {
        return Err(material_failure());
    }
    Ok(())
}

fn copy_regular(
    source: &Path,
    destination: &Path,
    executable: bool,
) -> Result<(), TrialEngineFailure> {
    let mut input = File::open(source).map_err(|_| material_failure())?;
    let opened = input.metadata().map_err(|_| material_failure())?;
    if !opened.file_type().is_file() {
        return Err(material_failure());
    }
    let mut output = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(if executable { 0o500 } else { 0o400 })
        .open(destination)
        .map_err(|_| implementation_failure())?;
    std::io::copy(&mut input, &mut output).map_err(|_| implementation_failure())?;
    output.sync_all().map_err(|_| implementation_failure())
}

fn create_private_directory(path: &Path) -> Result<(), TrialEngineFailure> {
    let mut builder = DirBuilder::new();
    builder.mode(0o700);
    builder.create(path).map_err(|_| implementation_failure())
}

fn create_accounted_directory(
    path: &Path,
    budget: &mut ProjectionBudget,
) -> Result<(), TrialEngineFailure> {
    budget.charge(0)?;
    create_private_directory(path)
}

fn hash_file(path: &Path) -> Result<String, TrialEngineFailure> {
    let mut file = File::open(path).map_err(|_| material_failure())?;
    let mut digest = Sha256::new();
    let mut buffer = [0_u8; 16 * 1024];
    loop {
        let count = file.read(&mut buffer).map_err(|_| material_failure())?;
        if count == 0 {
            break;
        }
        digest.update(&buffer[..count]);
    }
    Ok(format!("sha256:{:x}", digest.finalize()))
}

fn sha256_bytes(value: &[u8]) -> String {
    format!("sha256:{:x}", Sha256::digest(value))
}

fn normalized(path: &Path) -> Result<String, TrialEngineFailure> {
    path.to_str()
        .map(|value| value.replace('\\', "/"))
        .filter(|value| !value.is_empty())
        .ok_or_else(material_failure)
}

fn safe_relative(path: &Path) -> bool {
    !path.is_absolute()
        && path
            .components()
            .all(|item| matches!(item, Component::Normal(_)))
}

fn safe_component(value: &std::ffi::OsStr) -> bool {
    Path::new(value)
        .components()
        .all(|item| matches!(item, Component::Normal(_)))
}

fn require_available(
    deadline: Instant,
    invocation_cancelled: &AtomicBool,
    relay_cancelled: &AtomicBool,
) -> Result<(), TrialEngineFailure> {
    if invocation_cancelled.load(Ordering::Acquire) || relay_cancelled.load(Ordering::Acquire) {
        Err(TrialEngineFailure {
            code: TrialRelayFailure::Cancelled,
            cleanup_unsettled: false,
        })
    } else if Instant::now() >= deadline {
        Err(TrialEngineFailure {
            code: TrialRelayFailure::DeadlineExceeded,
            cleanup_unsettled: false,
        })
    } else {
        Ok(())
    }
}

fn sandbox_failure(stage: &str, value: SandboxFailure) -> TrialEngineFailure {
    eprintln!("trial engine stage={stage} failure={:?}", value.code);
    TrialEngineFailure {
        code: value.code,
        cleanup_unsettled: value.cleanup_unsettled,
    }
}

fn engine_failure(code: TrialRelayFailure) -> TrialEngineFailure {
    TrialEngineFailure {
        code,
        cleanup_unsettled: false,
    }
}

fn material_failure() -> TrialEngineFailure {
    engine_failure(TrialRelayFailure::MaterialUnavailable)
}

fn capacity_failure() -> TrialEngineFailure {
    engine_failure(TrialRelayFailure::CapacityExceeded)
}

fn implementation_failure() -> TrialEngineFailure {
    engine_failure(TrialRelayFailure::ImplementationUnavailable)
}
