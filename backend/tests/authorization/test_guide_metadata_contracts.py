"""Guide authorization facts reject independently substituted or incomplete targets."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.guide_mutations import (
    ProjectGuideMutationResourceContext,
    ProjectGuideMutationPrepareDenialResourceContext,
    ProjectGuideSourceSnapshotMutationResourceContext,
)
from app.modules.authorization.domain.prepared_guide_mutations import parse_prepared_guide_mutation
from app.modules.authorization.runtime import PreparedAuthorizationHandleInvalid

HASH = "sha256:" + "a" * 64


def create_facts():
    guide = uuid4()
    return dict(resource_type="project_guide_mutation", resource_id=guide, guide_id=guide,
                operation_id=uuid4(), scope_project_id=uuid4(), target_kind="create",
                guide_exists=False, operation_generation=1, request_digest=HASH,
                task_examples_hash=HASH, task_examples_count=1)


@pytest.mark.parametrize("defect", ["lifecycle", "existence", "partial_predecessor", "create_predecessor",
                                   "missing_request", "missing_hash", "missing_count", "update_examples"])
def test_guide_resource_requires_complete_operation_specific_facts(defect):
    facts = create_facts()
    assert ProjectGuideMutationResourceContext(**facts).guide_id == facts["guide_id"]
    if defect == "lifecycle":
        facts.update(guide_exists=True)
        message = "lifecycle facts are inconsistent"
    elif defect == "existence":
        facts.update(guide_exists=True, guide_status="draft", guide_version="v0.1")
        message = "operation and existence are inconsistent"
    elif defect == "partial_predecessor":
        facts.update(predecessor_snapshot_hash=HASH)
        message = "predecessor facts must be bound together"
    elif defect == "create_predecessor":
        facts.update(predecessor_snapshot_id=uuid4(), predecessor_snapshot_hash=HASH)
        message = "creation cannot bind predecessor"
    elif defect == "update_examples":
        facts.update(target_kind="update", guide_exists=True, guide_status="draft", guide_version="v0.1")
        message = "update cannot replace task examples"
    else:
        facts.pop({"missing_request": "request_digest", "missing_hash": "task_examples_hash", "missing_count": "task_examples_count"}[defect])
        message = "creation requires task example commitment"
    with pytest.raises(ValidationError, match=message):
        ProjectGuideMutationResourceContext(**facts)


@pytest.mark.parametrize("kind", ["guide_create", "guide_update", "source_snapshot_create"])
def test_prepare_denial_cannot_identify_a_foreign_resource(kind):
    project, guide = uuid4(), uuid4()
    facts = dict(resource_type="project_guide_mutation_request", scope_project_id=project,
                 resource_id=project if kind == "guide_create" else guide,
                 requested_guide_id=None if kind == "guide_create" else guide, requested_target_kind=kind)
    assert ProjectGuideMutationPrepareDenialResourceContext(**facts).resource_id == facts["resource_id"]
    facts["resource_id"] = uuid4()
    with pytest.raises(ValidationError, match="denial must identify"):
        ProjectGuideMutationPrepareDenialResourceContext(**facts)


@pytest.mark.parametrize("defect", ["snapshot_id", "predecessor_hash"])
def test_source_snapshot_resource_rejects_foreign_or_partial_identity(defect):
    snapshot = uuid4()
    facts = dict(resource_type="project_guide_source_snapshot_mutation", resource_id=snapshot,
                 source_snapshot_id=snapshot, operation_id=uuid4(), scope_project_id=uuid4(),
                 guide_id=uuid4(), guide_version="v0.1", guide_status="draft", source_snapshot_hash=HASH,
                 operation_generation=1)
    assert ProjectGuideSourceSnapshotMutationResourceContext(**facts).source_snapshot_id == snapshot
    if defect == "snapshot_id":
        facts["resource_id"] = uuid4()
        message = "resource must match snapshot"
    else:
        facts["predecessor_snapshot_hash"] = HASH
        message = "predecessor facts must be bound together"
    with pytest.raises(ValidationError, match=message):
        ProjectGuideSourceSnapshotMutationResourceContext(**facts)


@pytest.mark.parametrize("defect", ["target", "missing_project", "invalid_operation", "missing_hash", "boolean_count", "zero_count", "overflow_count", "digest_type"])
def test_prepared_create_parser_rejects_malformed_complete_control(defect):
    guide = uuid4()
    request = dict(project_id=str(uuid4()), guide_id=str(guide), target_resource_id=str(guide),
                   operation_id=str(uuid4()), request_digest=HASH, task_examples_hash=HASH, task_examples_count=1)
    parsed = parse_prepared_guide_mutation(ActionId.PROJECT_GUIDE_CREATE, request)
    assert parsed["guide_mutation_guide_id"] == guide
    assert parsed["guide_create_task_examples_hash"] == HASH
    if defect == "missing_project":
        request.pop("project_id")
    elif defect == "missing_hash":
        request.pop("task_examples_hash")
    else:
        field, value = {"target": ("target_resource_id", str(uuid4())),
                        "invalid_operation": ("operation_id", "not-a-uuid"),
                        "boolean_count": ("task_examples_count", True), "zero_count": ("task_examples_count", 0),
                        "overflow_count": ("task_examples_count", 101), "digest_type": ("request_digest", [])}[defect]
        request[field] = value
    with pytest.raises(PreparedAuthorizationHandleInvalid, match="invalid prepared authorization handle"):
        parse_prepared_guide_mutation(ActionId.PROJECT_GUIDE_CREATE, request)
