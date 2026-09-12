"""The proposal partition replacement permits only its declared module owners."""

import pytest

from scripts import behavior_ownership as ownership
from tests.test_behavior_ownership import _partition


def test_proposal_partition_replaces_only_the_shared_request_owner():
    expected = {
        'backend/app/modules/authorization/api/guide_proposal_review.py',
        'backend/app/modules/checkers/api/artifact_paths.py',
        'backend/app/modules/checkers/api/policy_compilation.py',
        'backend/app/modules/projects/api/compilation_identity.py',
        'backend/app/modules/projects/api/guide_proposal_package.py',
        'backend/app/modules/projects/api/guide_proposals.py',
        'backend/app/modules/projects/guide_compilation/approval_custody.py',
        'backend/app/modules/projects/guide_compilation/correction_feedback.py',
        'backend/app/modules/projects/guide_compilation/correction_request.py',
        'backend/app/modules/projects/guide_compilation/proposal_approval.py',
        'backend/app/modules/projects/guide_compilation/proposal_authority.py',
        'backend/app/modules/projects/guide_compilation/proposal_correction.py',
        'backend/app/modules/projects/guide_compilation/proposal_repository.py',
        'backend/app/modules/projects/guide_compilation/proposal_service.py',
        'backend/app/modules/projects/guide_compilation/request_inputs.py',
    }
    removed = {'backend/app/modules/projects/guide_compilation/automatic_request.py'}
    assert ownership.POL_05A_PARTITION_TARGETS == expected
    assert ownership.POL_05A_REMOVED_TARGETS == removed
    retained = 'backend/app/core/config.py'
    before = _partition(sorted({retained, *removed}))
    ownership._validate_additive_partition_transition(_partition(sorted({retained, *expected})), before)
    with pytest.raises(ownership.BehaviorOwnershipError, match='untrusted_partition_change'):
        ownership._validate_additive_partition_transition(_partition(sorted({
            retained, *expected, 'backend/app/modules/projects/guide_compilation/extra.py',
        })), before)
    with pytest.raises(ownership.BehaviorOwnershipError, match='untrusted_partition_change'):
        ownership._validate_additive_partition_transition(_partition(sorted(expected)), before)
