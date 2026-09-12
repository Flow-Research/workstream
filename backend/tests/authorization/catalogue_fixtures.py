"""Explicit catalogue expectations, independent of production definitions."""

ART_CUSTODY_EXPECTATIONS = {
    "artifact.binding.read": (
        "artifact.binding.read",
        "WS-AUTH-001-ART-02D-OPERATOR",
        "planned",
    ),
    "artifact.replica.read": (
        "artifact.replica.read",
        "WS-AUTH-001-ART-02D-OPERATOR",
        "planned",
    ),
    "artifact.receipt.read": (
        "artifact.receipt.read",
        "WS-AUTH-001-ART-02D-OPERATOR",
        "planned",
    ),
    "artifact.verification_job.read": (
        "artifact.verification_job.read",
        "WS-AUTH-001-ART-02D-OPERATOR",
        "planned",
    ),
    "artifact.verification_job.retry": (
        "artifact.verification_job.retry",
        "WS-AUTH-001-ART-02D-OPERATOR",
        "planned",
    ),
    "artifact.recovery_attempt.read": (
        "artifact.recovery_attempt.read",
        "WS-AUTH-001-ART-02D-OPERATOR",
        "planned",
    ),
    "artifact.audit.read": (
        "artifact.audit.read",
        "WS-AUTH-001-ART-02D-OPERATOR",
        "planned",
    ),
    "operations.artifact_storage_admission.read": (
        "operations.status.read",
        "WS-AUTH-001-ART-02D-OPERATOR",
        "planned",
    ),
    "artifact.verification.execute": (
        "artifact.verification.execute",
        "WS-AUTH-001-ART-02D-INTERNAL",
        "active",
    ),
    "artifact.pending_work.scan": (
        "artifact.pending_work.scan",
        "WS-AUTH-001-ART-02D-INTERNAL",
        "active",
    ),
    "artifact.put_attempt.resolve": (
        "artifact.put_attempt.resolve",
        "WS-AUTH-001-ART-02D-INTERNAL",
        "active",
    ),
    "artifact.guide_source.ingest": (
        "artifact.guide_source.ingest",
        "WS-XINT-002-04A",
        "active",
    ),
    "artifact.guide_source.read": (
        "artifact.guide_source.read",
        "WS-XINT-002-04B",
        "active",
    ),
    "artifact.submission_bundle.prepare": (
        "submission.create",
        "WS-XINT-002-05A",
        "active",
    ),
    "artifact.pre_submit.checker_input.materialize": (
        "artifact.checker_input.materialize",
        "WS-XINT-002-06A",
        "active",
    ),
    "artifact.submission.binding.create": ("artifact.binding.create", "WS-AUTH-001-ART-05", "active"),
    "artifact.post_submit.checker_input.materialize": (
        "artifact.checker_input.materialize",
        "WS-AUTH-001-ART-06A",
        "planned",
    ),
    "artifact.checker_output.write": (
        "artifact.checker_output.write",
        "WS-AUTH-001-ART-06B",
        "planned",
    ),
    "artifact.review_packet.materialize": (
        "artifact.review_packet.materialize",
        "WS-XINT-002-07",
        "planned",
    ),
    "artifact.review_evidence.binding.create": (
        "artifact.binding.create",
        "WS-XINT-002-07",
        "planned",
    ),
    "artifact.checker_output.binding.create": (
        "artifact.binding.create",
        "WS-AUTH-001-ART-06B",
        "planned",
    ),
}

REV_CUSTODY_EXPECTATIONS = {
    "review.queue.read": ("review.queue.read", "WS-AUTH-001-REV-05", "planned"),
    "review.queue.inspect": ("review.queue.inspect", "WS-AUTH-001-REV-05", "planned"),
    "review.claim": ("review.claim", "WS-AUTH-001-REV-06", "planned"),
    "review.release": ("review.release", "WS-AUTH-001-REV-06", "planned"),
    "review.decline_preference": (
        "review.decline_preference",
        "WS-AUTH-001-REV-06",
        "planned",
    ),
    "review.preference_expiry.run": (
        "operations.timer.run",
        "WS-AUTH-001-REV-06",
        "planned",
    ),
    "review.lease_expiry.run": (
        "operations.timer.run",
        "WS-AUTH-001-REV-06",
        "planned",
    ),
    "review.context.read": (
        "submission.read_for_review",
        "WS-AUTH-001-REV-07",
        "planned",
    ),
    "review.chain.read": ("review.chain.read", "WS-AUTH-001-REV-07", "planned"),
    "review.finding_evidence.ingest": (
        "review.decision",
        "WS-AUTH-001-REV-07",
        "planned",
    ),
    "review.decision": ("review.decision", "WS-AUTH-001-REV-08", "planned"),
    "review.finding_response_evidence.ingest": (
        "submission.create",
        "WS-AUTH-001-REV-09A",
        "planned",
    ),
    "review.lease.force_release": (
        "review.lease.force_release",
        "WS-AUTH-001-REV-11",
        "planned",
    ),
    "review.queue.routing.override": (
        "review.queue.override",
        "WS-AUTH-001-REV-11",
        "planned",
    ),
    "review.queue.routing.correct": (
        "review.queue.override",
        "WS-AUTH-001-REV-11",
        "planned",
    ),
    "review.queue.close": ("review.queue.override", "WS-AUTH-001-REV-11", "planned"),
    "review.reconcile.run": (
        "operations.reconcile.run",
        "WS-AUTH-001-REV-11",
        "planned",
    ),
    "review.artifact_reference.reconcile": (
        "operations.reconcile.run",
        "WS-AUTH-001-REV-12",
        "planned",
    ),
    "review.projection.rebuild": (
        "operations.projection.rebuild",
        "WS-AUTH-001-REV-12",
        "planned",
    ),
    "review.revision_context.repair": (
        "project.task.manage",
        "WS-XINT-003-08A",
        "planned",
    ),
    "review.revision_obligation.close": (
        "project.task.manage",
        "WS-XINT-003-08A",
        "planned",
    ),
    "review.revision_context.legacy_close": (
        "operations.reconcile.run",
        "WS-XINT-003-08A",
        "planned",
    ),
    "review.lifecycle.activation.manage": (
        "operations.reconcile.run",
        "WS-XINT-003-08B",
        "planned",
    ),
}

historical_permissions = frozenset("""actor.profile.read_self actor.profile.update_self actor.profile.read_any
    actor.profile.suspend actor.profile.reactivate actor.profile.deactivate
    actor.identity_link.read actor.identity_link.revoke actor.identity_link.reactivate
    actor.service.provision admin_role.read admin_role.grant admin_role.revoke
    project.create project.read project.update project.archive project.guide.manage
    project.effective_policy.manage project.task.manage project.review_policy.manage
    project.role_grant.read project.role_grant.manage task.queue.read task.claim
    submission.create submission.read_own submission.read_for_review review.queue.read
    review.queue.inspect review.claim review.release review.decline_preference
    review.decision review.lease.force_release review.chain.read contribution.read_self
    contribution.read_project compensation.policy.manage
    compensation.adapter_binding.manage compensation.award.read
    compensation.delivery.reconcile operations.status.read operations.timer.run
    operations.reconcile.run operations.outbox.retry operations.projection.rebuild
    audit.read audit.export""".split())

new_permissions = frozenset(
    """project.setup_diagnostic.read project.effective_policy.read
    operations.task.start_override operations.submission_gate.repair
    operations.checker.retry artifact.binding.read artifact.replica.read
    artifact.receipt.read artifact.verification_job.read
    artifact.verification_job.retry artifact.recovery_attempt.read artifact.audit.read
    artifact.guide_source.ingest artifact.binding.create
    artifact.verification.execute artifact.pending_work.scan artifact.put_attempt.resolve
    artifact.guide_source.read artifact.checker_input.materialize
    artifact.checker_output.write artifact.review_packet.materialize
    review.queue.override project.guide_compilation.request project.guide_compilation.execute""".split()
)

expected = {
    "actor.profile.read_self": ("actor.profile.read_self", "WS-AUTH-001-07B"),
    "actor.profile.update_self": ("actor.profile.update_self", "WS-AUTH-001-07B"),
    "operations.task.start_override": ("operations.task.start_override", "task-project-grant-authorization"),
    "task.claim": ("task.claim", "task-project-grant-authorization"),
    "task.start": ("task.claim", "task-project-grant-authorization"),
    "task.work_context.read": ("task.queue.read", "task-project-grant-authorization"),
    "project.task.work_context.read": ("project.task.manage", "task-project-grant-authorization"),
    "operations.submission_gate.repair": (
        "operations.submission_gate.repair",
        "WS-AUTH-001-14",
    ),
    "operations.checker.retry": ("operations.checker.retry", "WS-AUTH-001-14"),
    "submission.create": ("submission.create", "WS-AUTH-001-14"),
    **{
        action: (permission, owner)
        for action, (permission, owner, _availability) in REV_CUSTODY_EXPECTATIONS.items()
    },
    **{
        action: (permission, owner)
        for action, (permission, owner, _availability) in ART_CUSTODY_EXPECTATIONS.items()
    },
    "authorization.permission_catalogue.read": ("admin_role.read", "WS-AUTH-001-08"),
    "authorization.admin_role_definitions.read": ("admin_role.read", "WS-AUTH-001-08"),
    "admin_role_grant.list": ("admin_role.read", "WS-AUTH-001-08"),
    "actor.admin_role_grant_history.read": ("admin_role.read", "WS-AUTH-001-08"),
    "admin_role_grant.issue": ("admin_role.grant", "WS-AUTH-001-08"),
    "admin_role_grant.revoke": ("admin_role.revoke", "WS-AUTH-001-08"),
    "admin_role_grant.bootstrap": ("admin_role.grant", "WS-AUTH-001-08"),
    "actor.profile.read": ("actor.profile.read_any", "WS-AUTH-001-09C"),
    "actor.profile.suspend": ("actor.profile.suspend", "WS-AUTH-001-09D-A"),
    "actor.profile.reactivate": ("actor.profile.reactivate", "WS-AUTH-001-09D-A"),
    "actor.profile.deactivate": ("actor.profile.deactivate", "WS-AUTH-001-09D-A"),
    "actor.identity_link.read": ("actor.identity_link.read", "WS-AUTH-001-09C"),
    "actor.identity_link.revoke": ("actor.identity_link.revoke", "WS-AUTH-001-09D-B"),
    "actor.identity_link.reactivate": (
        "actor.identity_link.reactivate",
        "WS-AUTH-001-09D-B",
    ),
    "actor.service.provision": ("actor.service.provision", "WS-AUTH-001-09B"),
    "project.contributor_candidate.list": (
        "project.role_grant.manage",
        "WS-AUTH-001-10B",
    ),
    "project_role_grant.list": ("project.role_grant.read", "WS-AUTH-001-10B"),
    "project_role_grant.read": ("project.role_grant.read", "WS-AUTH-001-10B"),
    "project_role_grant.issue": ("project.role_grant.manage", "WS-AUTH-001-10C"),
    "project_role_grant.revoke": ("project.role_grant.manage", "WS-AUTH-001-10C"),
    "project.read": ("project.read", "WS-AUTH-001-11B"),
    "actor.authorization_context.read": (
        "actor.profile.read_self",
        "WS-AUTH-001-11B",
    ),
    "project.setup_run.read": (
        "project.setup_diagnostic.read",
        "WS-AUTH-001-11C1",
    ),
    "project.guide_sufficiency_report.list": (
        "project.setup_diagnostic.read",
        "WS-AUTH-001-11C1",
    ),
    "project.guide_sufficiency_report.read": (
        "project.setup_diagnostic.read",
        "WS-AUTH-001-11C1",
    ),
    "project.submission_artifact_policy.list": (
        "project.effective_policy.read",
        "WS-AUTH-001-11C1",
    ),
    "project.submission_artifact_policy.read": (
        "project.effective_policy.read",
        "WS-AUTH-001-11C1",
    ),
    "project.effective_submission_artifact_policy.read": (
        "project.effective_policy.read",
        "WS-AUTH-001-11C2",
    ),
    "project.pre_submit_checker_policy.read": (
        "project.effective_policy.read",
        "WS-AUTH-001-11C2",
    ),
    "project.active_guide.read": ("project.read", "WS-AUTH-001-11C2"),
    "project.create": ("project.create", "WS-AUTH-001-12C"),
    "project.guide.create": ("project.guide.manage", "WS-AUTH-001-12D"),
    "project.guide.update": ("project.guide.manage", "WS-AUTH-001-12D"),
    "project.guide_source_snapshot.create": ("project.guide.manage", "WS-AUTH-001-12D"),
    "project.guide_compilation.request_automatic": ("project.guide_compilation.execute", "WS-AUTH-001-12I"),
    "project.guide_compilation.request": ("project.guide_compilation.request", "WS-AUTH-001-12I"),
    "project.guide_compilation.review_package.read": ("project.guide.manage", "WS-AUTH-001-12F"),
    "project.guide_compilation.correction.request": ("project.guide_compilation.request", "WS-AUTH-001-12F"),
    "project.guide_compilation.execute": ("project.guide_compilation.execute", "WS-AUTH-001-12I"),
    "project.review_policy.update": (
        "project.review_policy.manage",
        "WS-XINT-003-02B",
    ),
    "project.revision_policy.update": (
        "project.review_policy.manage",
        "WS-XINT-003-02B",
    ),
    "project.guide_sufficiency_report.create": (
        "project.guide.manage",
        "WS-AUTH-001-12E",
    ),
    "project.guide_sufficiency.run": (
        "project.guide.manage",
        "WS-AUTH-001-12E",
    ),
    "project.guide_sufficiency.warnings.acknowledge": (
        "project.guide.manage",
        "WS-AUTH-001-12E",
    ),
    "project.submission_artifact_policy.create": (
        "project.effective_policy.manage",
        "WS-AUTH-001-12F2",
    ),
        "project.submission_artifact_policy.derive": (
            "project.effective_policy.manage",
            "WS-AUTH-001-12F3",
    ),
    "project.submission_artifact_policy.update": (
        "project.effective_policy.manage",
        "WS-AUTH-001-12F2",
    ),
    "project.submission_artifact_policy.approve": (
        "project.effective_policy.manage",
        "WS-AUTH-001-12F",
    ),
    "project.post_submit_checker_policy.approve": (
        "project.effective_policy.manage",
        "WS-AUTH-001-12G",
    ),
    "project.post_submit_checker_policy.correction.request": (
        "project.effective_policy.manage",
        "WS-AUTH-001-12G",
    ),
    "project.post_submit_checker_policy.derive": (
        "project.effective_policy.manage",
        "WS-AUTH-001-12G",
    ),
    "project.setup_run.update": ("project.guide.manage", "WS-AUTH-001-12B2"), "project.guide.activate": ("project.guide.manage", "WS-AUTH-001-12H"),  # noqa: E501
    **dict.fromkeys((f"compensation.adapter_binding.{op}" for op in ("read", "create", "suspend", "resume")), ("compensation.adapter_binding.manage", "WS-ARCH-001-CP01A")),  # noqa: E501
    **dict.fromkeys((f"contribution.policy.{op}" for op in ("read", "create_draft", "update_draft", "publish", "retire")), ("compensation.policy.manage", "WS-ARCH-001-CP01B")),  # noqa: E501
}


AUDIT_ALLOWED_ACTION_VALUES = {
    "task.claim",
    "task.start",
    "task.work_context.read",
    "project.task.work_context.read",
    "operations.task.start_override",
    "actor.admin_role_grant_history.read",
    "actor.authorization_context.read",
    "actor.identity_link.reactivate",
    "actor.identity_link.read",
    "actor.identity_link.revoke",
    "actor.profile.deactivate",
    "actor.profile.reactivate",
    "actor.profile.read",
    "actor.profile.read_self",
    "actor.profile.suspend",
    "actor.profile.update_self",
    "actor.service.provision",
    "admin_role_grant.bootstrap",
    "admin_role_grant.issue",
    "admin_role_grant.list",
    "admin_role_grant.revoke",
    "artifact.guide_source.ingest",
    "artifact.guide_source.read",
    "artifact.pending_work.scan",
    "artifact.pre_submit.checker_input.materialize",
    "artifact.put_attempt.resolve",
    "artifact.submission.binding.create",
    "artifact.submission_bundle.prepare",
    "artifact.verification.execute",
    "authorization.admin_role_definitions.read",
    "authorization.permission_catalogue.read",
    "compensation.adapter_binding.create",
    "compensation.adapter_binding.read",
    "compensation.adapter_binding.resume",
    "compensation.adapter_binding.suspend",
    "contribution.policy.create_draft",
    "contribution.policy.publish",
    "contribution.policy.read",
    "contribution.policy.retire",
    "contribution.policy.update_draft",
    "project.active_guide.read",
    "project.contributor_candidate.list",
    "project.create",
    "project.effective_submission_artifact_policy.read",
    "project.guide.create",
    "project.guide.update",
    "project.guide_compilation.execute",
    "project.guide_compilation.request",
    "project.guide_compilation.request_automatic",
    "project.guide_source_snapshot.create",
    "project.guide_sufficiency.run",
    "project.guide_sufficiency.warnings.acknowledge",
    "project.guide_sufficiency_report.create",
    "project.guide_sufficiency_report.list",
    "project.guide_sufficiency_report.read",
    "project.pre_submit_checker_policy.read",
    "project.read",
    "project.review_policy.update",
    "project.revision_policy.update",
    "project.setup_run.read",
    "project.setup_run.update",
    "project.submission_artifact_policy.create",
    "project.submission_artifact_policy.derive",
    "project.submission_artifact_policy.list",
    "project.submission_artifact_policy.read",
    "project.submission_artifact_policy.update",
    "project_role_grant.issue",
    "project_role_grant.list",
    "project_role_grant.read",
    "project_role_grant.revoke",
    "submission.create",
}
