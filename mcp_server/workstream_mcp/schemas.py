from __future__ import annotations

import json
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]

from workstream_mcp.limits import (
    GUIDE_DOCUMENT_MAX_BASE64_CHARS,
    GUIDE_DOCUMENT_MEDIA_TYPES,
    SUBMISSION_BUNDLE_MAX_BASE64_CHARS,
    TASK_IMPORT_SOURCE_MAX_BASE64_CHARS,
)

EMPTY_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}
PROFILE_UPDATE_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "display_name": {"type": ["string", "null"], "maxLength": 200},
        "contact_email": {"type": ["string", "null"], "maxLength": 320},
    },
    "minProperties": 1,
    "additionalProperties": False,
}
AUTHORIZATION_CONTEXT_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "project_id": {
            "type": "string",
            "minLength": 1,
            "maxLength": 100,
            "pattern": r"^[^\u0000]*$",
        }
    },
    "required": ["project_id"],
    "additionalProperties": False,
}

_UUID_INPUT = {"type": "string", "format": "uuid", "minLength": 36, "maxLength": 36}
_REASON_INPUT = {
    "type": "string",
    "minLength": 1,
    "maxLength": 500,
    "pattern": r"^[^\u0000]*$",
}
_IDEMPOTENCY_KEY_INPUT = {
    "type": "string",
    "format": "uuid",
    "minLength": 36,
    "maxLength": 36,
}
_ACTOR_INPUT = {
    "type": "object",
    "properties": {"actor_profile_id": _UUID_INPUT},
    "required": ["actor_profile_id"],
    "additionalProperties": False,
}
_GRANT_PROPERTIES = {
    "scope_type": {"type": "string", "enum": ["system", "project"]},
    "scope_project_id": _UUID_INPUT,
    "status": {"type": "string", "enum": ["active", "revoked", "all"]},
    "limit": {"type": "integer", "minimum": 1, "maximum": 100},
    "cursor": {"type": "string", "maxLength": 512},
}
_GRANT_SCOPE_CONSTRAINTS = [
    {
        "if": {"properties": {"scope_type": {"const": "project"}}, "required": ["scope_type"]},
        "then": {"required": ["scope_project_id"]},
    },
    {
        "if": {"properties": {"scope_type": {"const": "system"}}, "required": ["scope_type"]},
        "then": {"not": {"required": ["scope_project_id"]}},
    },
]
ACCESS_READ_INPUT_SCHEMAS: dict[str, dict[str, Any]] = {
    "permissions_list": EMPTY_INPUT_SCHEMA,
    "admin_roles_list": EMPTY_INPUT_SCHEMA,
    "admin_grants_list": {
        "type": "object",
        "properties": _GRANT_PROPERTIES,
        "required": ["scope_type"],
        "allOf": _GRANT_SCOPE_CONSTRAINTS,
        "additionalProperties": False,
    },
    "actor_admin_grants_list": {
        "type": "object",
        "properties": {"actor_profile_id": _UUID_INPUT, **_GRANT_PROPERTIES},
        "required": ["actor_profile_id", "scope_type"],
        "allOf": _GRANT_SCOPE_CONSTRAINTS,
        "additionalProperties": False,
    },
    "actor_get": _ACTOR_INPUT,
    "actor_identity_link_get": _ACTOR_INPUT,
}

ADMIN_GRANT_INPUT_SCHEMAS: dict[str, dict[str, Any]] = {
    "admin_grants_issue": {
        "type": "object",
        "properties": {
            "body": {
                "type": "object",
                "properties": {
                    "target_actor_profile_id": _UUID_INPUT,
                    "role": {
                        "type": "string",
                        "enum": [
                            "access_administrator",
                            "operator",
                            "project_manager",
                            "finance_authority",
                            "audit_authority",
                        ],
                    },
                    "scope_type": {"type": "string", "enum": ["system", "project"]},
                    "scope_project_id": {"anyOf": [_UUID_INPUT, {"type": "null"}]},
                    "reason": _REASON_INPUT,
                },
                "required": ["target_actor_profile_id", "role", "scope_type", "reason"],
                "allOf": [
                    {
                        "if": {"properties": {"scope_type": {"const": "project"}}},
                        "then": {
                            "required": ["scope_project_id"],
                            "properties": {"scope_project_id": _UUID_INPUT},
                        },
                    },
                    {
                        "if": {"properties": {"scope_type": {"const": "system"}}},
                        "then": {
                            "properties": {
                                "scope_project_id": {"type": "null"},
                            }
                        },
                    },
                    {
                        "if": {
                            "properties": {"role": {"enum": ["access_administrator", "operator"]}}
                        },
                        "then": {"properties": {"scope_type": {"const": "system"}}},
                    },
                ],
                "additionalProperties": False,
            },
            "idempotency_key": _IDEMPOTENCY_KEY_INPUT,
        },
        "required": ["body", "idempotency_key"],
        "additionalProperties": False,
    },
    "admin_grants_revoke": {
        "type": "object",
        "properties": {
            "grant_id": _UUID_INPUT,
            "body": {
                "type": "object",
                "properties": {"reason": _REASON_INPUT},
                "required": ["reason"],
                "additionalProperties": False,
            },
            "idempotency_key": _IDEMPOTENCY_KEY_INPUT,
        },
        "required": ["grant_id", "body", "idempotency_key"],
        "additionalProperties": False,
    },
}

_LIFECYCLE_BODY = {
    "type": "object",
    "properties": {"reason": _REASON_INPUT},
    "required": ["reason"],
    "additionalProperties": False,
}


def _lifecycle_input(resource_key: str) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            resource_key: _UUID_INPUT,
            "body": _LIFECYCLE_BODY,
            "idempotency_key": _IDEMPOTENCY_KEY_INPUT,
        },
        "required": [resource_key, "body", "idempotency_key"],
        "additionalProperties": False,
    }


ACTOR_LIFECYCLE_INPUT_SCHEMAS: dict[str, dict[str, Any]] = {
    "actor_suspend": _lifecycle_input("actor_profile_id"),
    "actor_reactivate": _lifecycle_input("actor_profile_id"),
    "actor_deactivate": _lifecycle_input("actor_profile_id"),
    "identity_link_revoke": _lifecycle_input("identity_link_id"),
    "identity_link_reactivate": _lifecycle_input("identity_link_id"),
}

PROJECT_INPUT_SCHEMAS: dict[str, dict[str, Any]] = {
    "projects_create": {
        "type": "object",
        "properties": {
            "body": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "maxLength": 200,
                        "pattern": r"^[^\u0000]*$",
                    },
                    "slug": {
                        "type": "string",
                        "maxLength": 120,
                        "pattern": r"^[^\u0000]*$",
                    },
                    "description": {
                        "type": ["string", "null"],
                        "pattern": r"^[^\u0000]*$",
                    },
                },
                "required": ["name", "slug"],
                "additionalProperties": False,
            },
            "idempotency_key": _IDEMPOTENCY_KEY_INPUT,
        },
        "required": ["body", "idempotency_key"],
        "additionalProperties": False,
    },
    "projects_get": {
        "type": "object",
        "properties": {"project_id": _UUID_INPUT},
        "required": ["project_id"],
        "additionalProperties": False,
    },
}

_REFERENCE_TOKEN_INPUT = {
    "type": "string",
    "minLength": 1,
    "maxLength": 120,
    "pattern": r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}$",
    "not": {"pattern": r"://"},
}
_QUALIFICATION_AVAILABILITY_INPUT = {
    "type": "object",
    "properties": {
        "availability": {"type": "string", "enum": ["available", "unavailable"]},
        "reference_ids": {
            "type": "array",
            "items": _REFERENCE_TOKEN_INPUT,
            "maxItems": 20,
        },
        "unavailable_reason": {
            "type": ["string", "null"],
            "enum": ["not_collected", "source_unavailable", "no_record", None],
        },
    },
    "required": ["availability", "reference_ids", "unavailable_reason"],
    "allOf": [
        {
            "if": {"properties": {"availability": {"const": "available"}}},
            "then": {
                "properties": {
                    "reference_ids": {"minItems": 1},
                    "unavailable_reason": {"type": "null"},
                }
            },
        },
        {
            "if": {"properties": {"availability": {"const": "unavailable"}}},
            "then": {
                "properties": {
                    "reference_ids": {"maxItems": 0},
                    "unavailable_reason": {
                        "type": "string",
                        "enum": ["not_collected", "source_unavailable", "no_record"],
                    },
                }
            },
        },
    ],
    "additionalProperties": False,
}
_PROJECT_ROLE_QUALIFICATION_INPUT = {
    "type": "object",
    "properties": {
        "skills_snapshot": _QUALIFICATION_AVAILABILITY_INPUT,
        "reputation_snapshot": _QUALIFICATION_AVAILABILITY_INPUT,
        "prior_project_work_refs": {
            "type": "array",
            "items": _UUID_INPUT,
            "maxItems": 20,
        },
        "external_expertise_refs": {
            "type": "array",
            "items": _REFERENCE_TOKEN_INPUT,
            "maxItems": 20,
        },
    },
    "required": [
        "skills_snapshot",
        "reputation_snapshot",
        "prior_project_work_refs",
        "external_expertise_refs",
    ],
    "additionalProperties": False,
}
_PROJECT_ROLE_PAGE_PROPERTIES = {
    "project_id": _UUID_INPUT,
    "limit": {"type": "integer", "minimum": 1, "maximum": 100},
    "cursor": {"type": "string", "maxLength": 512},
}
PROJECT_GRANT_INPUT_SCHEMAS: dict[str, dict[str, Any]] = {
    "contributor_candidates_list": {
        "type": "object",
        "properties": _PROJECT_ROLE_PAGE_PROPERTIES,
        "required": ["project_id"],
        "additionalProperties": False,
    },
    "project_grants_issue": {
        "type": "object",
        "properties": {
            "project_id": _UUID_INPUT,
            "body": {
                "type": "object",
                "properties": {
                    "target_actor_profile_id": _UUID_INPUT,
                    "role": {"type": "string", "enum": ["submitter", "reviewer"]},
                    "qualification": _PROJECT_ROLE_QUALIFICATION_INPUT,
                    "reason": _REASON_INPUT,
                },
                "required": [
                    "target_actor_profile_id",
                    "role",
                    "qualification",
                    "reason",
                ],
                "additionalProperties": False,
            },
            "idempotency_key": _IDEMPOTENCY_KEY_INPUT,
        },
        "required": ["project_id", "body", "idempotency_key"],
        "additionalProperties": False,
    },
    "project_grants_list": {
        "type": "object",
        "properties": {
            **_PROJECT_ROLE_PAGE_PROPERTIES,
            "status": {"type": "string", "enum": ["active", "revoked"]},
            "role": {"type": "string", "enum": ["submitter", "reviewer"]},
        },
        "required": ["project_id"],
        "additionalProperties": False,
    },
    "project_grants_get": {
        "type": "object",
        "properties": {"project_id": _UUID_INPUT, "grant_id": _UUID_INPUT},
        "required": ["project_id", "grant_id"],
        "additionalProperties": False,
    },
    "project_grants_revoke": {
        "type": "object",
        "properties": {
            "project_id": _UUID_INPUT,
            "grant_id": _UUID_INPUT,
            "body": {
                "type": "object",
                "properties": {"reason": _REASON_INPUT},
                "required": ["reason"],
                "additionalProperties": False,
            },
            "idempotency_key": _IDEMPOTENCY_KEY_INPUT,
        },
        "required": ["project_id", "grant_id", "body", "idempotency_key"],
        "additionalProperties": False,
    },
}

_GUIDE_TASK_EXAMPLE_INPUT = {
    "type": "object",
    "properties": {
        "content": {
            "type": "string",
            "minLength": 1,
            "maxLength": 65_536,
            "pattern": r"^[^\u0000]*$",
        },
        "title": {
            "type": ["string", "null"],
            "maxLength": 500,
            "pattern": r"^[^\u0000]*$",
        },
        "labels": {
            "type": "array",
            "items": {
                "type": "string",
                "minLength": 1,
                "maxLength": 100,
                "pattern": r"^[^\u0000]*$",
            },
            "maxItems": 20,
        },
    },
    "required": ["content"],
    "additionalProperties": False,
}
_GUIDE_DOCUMENT_INPUT = {
    "type": "object",
    "properties": {
        "label": {"type": "string", "minLength": 1, "maxLength": 500},
        "media_type": {
            "type": "string",
            "enum": [
                "application/pdf",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                "text/markdown",
            ],
        },
    },
    "required": ["label", "media_type"],
    "additionalProperties": False,
}
GUIDE_INPUT_SCHEMAS: dict[str, dict[str, Any]] = {
    "guides_create": {
        "type": "object",
        "properties": {
            "project_id": _UUID_INPUT,
            "body": {
                "type": "object",
                "properties": {
                    "version": {
                        "type": "string",
                        "maxLength": 50,
                        "pattern": r"^[^\u0000]*$",
                    },
                    "change_summary": {
                        "type": ["string", "null"],
                        "maxLength": 1000,
                        "pattern": r"^[^\u0000]*$",
                    },
                    "task_examples": {
                        "type": "array",
                        "items": _GUIDE_TASK_EXAMPLE_INPUT,
                        "minItems": 1,
                        "maxItems": 100,
                    },
                    "documents": {
                        "type": "array",
                        "items": _GUIDE_DOCUMENT_INPUT,
                        "minItems": 1,
                        "maxItems": 100,
                    },
                },
                "required": ["version", "task_examples", "documents"],
                "additionalProperties": False,
            },
            "idempotency_key": _IDEMPOTENCY_KEY_INPUT,
        },
        "required": ["project_id", "body", "idempotency_key"],
        "additionalProperties": False,
    },
    "guides_update": {
        "type": "object",
        "properties": {
            "project_id": _UUID_INPUT,
            "guide_id": _UUID_INPUT,
            "body": {
                "type": "object",
                "properties": {
                    "change_summary": {
                        "type": ["string", "null"],
                        "maxLength": 1000,
                        "pattern": r"^[^\u0000]*$",
                    }
                },
                "additionalProperties": False,
            },
            "idempotency_key": _IDEMPOTENCY_KEY_INPUT,
        },
        "required": ["project_id", "guide_id", "body", "idempotency_key"],
        "additionalProperties": False,
    },
}

_POLICY_SELECTOR_INPUT = {
    "type": "string",
    "minLength": 1,
    "pattern": r"^[\u0020-\u007e]+(?![\s\S])",
}
POLICY_INPUT_SCHEMAS: dict[str, dict[str, Any]] = {
    "review_policy_put": {
        "type": "object",
        "properties": {
            "project_id": _UUID_INPUT,
            "guide_id": _UUID_INPUT,
            "body": {
                "type": "object",
                "properties": {
                    "human_review_required": {"type": "boolean"},
                    "review_preference_window_seconds": {
                        "type": "integer",
                        "exclusiveMinimum": 0,
                    },
                    "review_lease_duration_seconds": {
                        "type": "integer",
                        "exclusiveMinimum": 0,
                    },
                    "max_active_review_leases_per_reviewer": {"const": 1},
                    "self_review_allowed": {"const": False},
                    "reject_policy": {"const": "close_task"},
                    "finding_evidence_requirement": {
                        "type": "string",
                        "enum": [
                            "optional",
                            "required_for_blocking",
                            "required_for_all",
                        ],
                    },
                    "requires_second_review": {"const": False},
                    "allowed_decisions": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["accept", "needs_revision", "reject"],
                        },
                    },
                    "minimum_finding_fields": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": [
                    "review_preference_window_seconds",
                    "review_lease_duration_seconds",
                ],
                "additionalProperties": False,
            },
            "idempotency_key": _IDEMPOTENCY_KEY_INPUT,
            "if_match": _POLICY_SELECTOR_INPUT,
        },
        "required": ["project_id", "guide_id", "body", "idempotency_key", "if_match"],
        "additionalProperties": False,
    },
    "revision_policy_put": {
        "type": "object",
        "properties": {
            "project_id": _UUID_INPUT,
            "guide_id": _UUID_INPUT,
            "body": {
                "type": "object",
                "properties": {
                    "max_revision_rounds": {"type": "integer", "minimum": 0},
                    "revision_deadline_hours": {"type": "integer", "minimum": 1},
                    "allowed_resubmission_states": {
                        "type": "array",
                        "items": {"const": "needs_revision"},
                        "minItems": 1,
                        "maxItems": 1,
                    },
                    "reviewer_reassignment_rule": {"type": ["string", "null"]},
                },
                "required": ["max_revision_rounds", "revision_deadline_hours"],
                "additionalProperties": False,
            },
            "idempotency_key": _IDEMPOTENCY_KEY_INPUT,
            "if_match": _POLICY_SELECTOR_INPUT,
        },
        "required": ["project_id", "guide_id", "body", "idempotency_key", "if_match"],
        "additionalProperties": False,
    },
}

_PAGE_PROPERTIES = {
    "limit": {"type": "integer", "minimum": 1, "maximum": 100},
    "cursor": {"type": "string", "minLength": 1, "maxLength": 512},
}
_CONTRIBUTION_FILTERS = {
    "contribution_type": {
        "type": "string",
        "enum": ["accepted_submission", "completed_review"],
    },
    "recorded_from": {"type": "string", "format": "date-time"},
    "recorded_before": {"type": "string", "format": "date-time"},
    "limit": {"type": "integer", "minimum": 1, "maximum": 1000},
    "cursor": {"type": "string", "minLength": 1, "maxLength": 512},
}
WORKSPACE_READ_INPUT_SCHEMAS: dict[str, dict[str, Any]] = {
    "actor_projects_list": {
        "type": "object",
        "properties": _PAGE_PROPERTIES,
        "additionalProperties": False,
    },
    "actor_assignments_list": {
        "type": "object",
        "properties": {
            "project_id": _UUID_INPUT,
            "state": {"type": "string", "enum": ["active", "closed"]},
            "updated_since": {"type": "string", "format": "date-time"},
            **_PAGE_PROPERTIES,
        },
        "additionalProperties": False,
    },
    "actor_submissions_list": {
        "type": "object",
        "properties": {
            "project_id": _UUID_INPUT,
            "task_id": _UUID_INPUT,
            "status": {
                "type": "string",
                "enum": [
                    "evaluation_pending",
                    "review_pending",
                    "accepted",
                    "needs_revision",
                    "rejected",
                ],
            },
            "updated_since": {"type": "string", "format": "date-time"},
            **_PAGE_PROPERTIES,
        },
        "additionalProperties": False,
    },
    "actor_summary_get": {
        "type": "object",
        "properties": {"project_id": _UUID_INPUT},
        "additionalProperties": False,
    },
    "contributions_list": {
        "type": "object",
        "properties": {"project_id": _UUID_INPUT, **_CONTRIBUTION_FILTERS},
        "additionalProperties": False,
    },
    "project_contributions_export": {
        "type": "object",
        "properties": {"project_id": _UUID_INPUT, **_CONTRIBUTION_FILTERS},
        "required": ["project_id"],
        "additionalProperties": False,
    },
    "project_submissions_list": {
        "type": "object",
        "properties": {
            "project_id": _UUID_INPUT,
            "status": {
                "type": "string",
                "enum": [
                    "evaluation_pending",
                    "review_pending",
                    "accepted",
                    "needs_revision",
                    "rejected",
                ],
            },
            "task_id": _UUID_INPUT,
            "submitter_actor_id": _UUID_INPUT,
            "updated_since": {"type": "string", "format": "date-time"},
            **_PAGE_PROPERTIES,
        },
        "required": ["project_id"],
        "additionalProperties": False,
    },
    "project_assignments_list": {
        "type": "object",
        "properties": {
            "project_id": _UUID_INPUT,
            "state": {"type": "string", "enum": ["active", "closed"]},
            **_PAGE_PROPERTIES,
        },
        "required": ["project_id"],
        "additionalProperties": False,
    },
    "project_summary_get": {
        "type": "object",
        "properties": {"project_id": _UUID_INPUT},
        "required": ["project_id"],
        "additionalProperties": False,
    },
    "project_task_import_batches_list": {
        "type": "object",
        "properties": {"project_id": _UUID_INPUT, **_PAGE_PROPERTIES},
        "required": ["project_id"],
        "additionalProperties": False,
    },
    "project_preparations_list": {
        "type": "object",
        "properties": {
            "project_id": _UUID_INPUT,
            "outcome": {
                "type": "string",
                "enum": ["pending", "passed", "failed", "infrastructure_failed"],
            },
            **_PAGE_PROPERTIES,
        },
        "required": ["project_id"],
        "additionalProperties": False,
    },
    "active_guide_get": {
        "type": "object",
        "properties": {"project_id": _UUID_INPUT},
        "required": ["project_id"],
        "additionalProperties": False,
    },
    "ready_tasks_list": {
        "type": "object",
        "properties": {"project_id": _UUID_INPUT, **_PAGE_PROPERTIES},
        "required": ["project_id"],
        "additionalProperties": False,
    },
}

_POLICY_DEFINITION_INPUT = {
    "type": "object",
    "properties": {
        "instrument_type": {"type": "string", "enum": ["money", "project_points"]},
        "unit_code": {"type": "string"},
        "quantity": {"type": "string"},
        "adapter_binding_id": _UUID_INPUT,
    },
    "required": ["instrument_type", "unit_code", "quantity", "adapter_binding_id"],
    "additionalProperties": False,
}
_POLICY_RULE_INPUT = {
    "type": "object",
    "properties": {
        "contribution_type": {
            "type": "string",
            "enum": ["accepted_submission", "completed_review"],
        },
        "compensation_mode": {"type": "string", "enum": ["unpaid", "compensated"]},
        "definitions": {"type": "array", "items": _POLICY_DEFINITION_INPUT},
    },
    "required": ["contribution_type", "compensation_mode"],
    "additionalProperties": False,
}
CONTRIBUTION_POLICY_INPUT_SCHEMAS: dict[str, dict[str, Any]] = {
    "contribution_policies_list": {
        "type": "object",
        "properties": {"project_id": _UUID_INPUT, **_PAGE_PROPERTIES},
        "required": ["project_id"],
        "additionalProperties": False,
    },
    "contribution_policy_current_get": {
        "type": "object",
        "properties": {"project_id": _UUID_INPUT},
        "required": ["project_id"],
        "additionalProperties": False,
    },
    "contribution_policy_get": {
        "type": "object",
        "properties": {
            "project_id": _UUID_INPUT,
            "policy_id": _UUID_INPUT,
            "version_id": _UUID_INPUT,
        },
        "required": ["project_id", "policy_id"],
        "additionalProperties": False,
    },
    "contribution_policy_create": {
        "type": "object",
        "properties": {
            "project_id": _UUID_INPUT,
            "body": {
                "type": "object",
                "properties": {"name": {"type": "string", "minLength": 1, "maxLength": 200}},
                "required": ["name"],
                "additionalProperties": False,
            },
            "idempotency_key": _IDEMPOTENCY_KEY_INPUT,
        },
        "required": ["project_id", "body", "idempotency_key"],
        "additionalProperties": False,
    },
    "contribution_policy_update": {
        "type": "object",
        "properties": {
            "project_id": _UUID_INPUT,
            "policy_id": _UUID_INPUT,
            "version_id": _UUID_INPUT,
            "body": {
                "type": "object",
                "properties": {
                    "rules": {
                        "type": "array",
                        "items": _POLICY_RULE_INPUT,
                        "minItems": 2,
                        "maxItems": 2,
                    }
                },
                "required": ["rules"],
                "additionalProperties": False,
            },
            "idempotency_key": _IDEMPOTENCY_KEY_INPUT,
        },
        "required": ["project_id", "policy_id", "version_id", "body", "idempotency_key"],
        "additionalProperties": False,
    },
    "contribution_policy_publish": {
        "type": "object",
        "properties": {
            "project_id": _UUID_INPUT,
            "policy_id": _UUID_INPUT,
            "version_id": _UUID_INPUT,
            "body": EMPTY_INPUT_SCHEMA,
            "idempotency_key": _IDEMPOTENCY_KEY_INPUT,
        },
        "required": ["project_id", "policy_id", "version_id", "body", "idempotency_key"],
        "additionalProperties": False,
    },
    "contribution_policy_retire": {
        "type": "object",
        "properties": {
            "project_id": _UUID_INPUT,
            "policy_id": _UUID_INPUT,
            "version_id": _UUID_INPUT,
            "body": EMPTY_INPUT_SCHEMA,
            "idempotency_key": _IDEMPOTENCY_KEY_INPUT,
        },
        "required": ["project_id", "policy_id", "version_id", "body", "idempotency_key"],
        "additionalProperties": False,
    },
}


_TASK_SELECTOR_PROPERTIES = {"task_id": _UUID_INPUT}
_TASK_PAGE_PROPERTIES = {
    **_TASK_SELECTOR_PROPERTIES,
    "limit": {"type": "integer", "minimum": 1, "maximum": 100},
    "cursor": {"type": "string", "minLength": 1, "maxLength": 1024},
}
_TASK_TRANSITION_BODY = {
    "type": "object",
    "properties": {
        "reason": {
            "type": ["string", "null"],
            "maxLength": 1000,
            "pattern": r"^[^\u0000]*$",
        }
    },
    "additionalProperties": False,
}
_ASCII_PACKET_TEXT = {
    "type": "string",
    "maxLength": 4_096,
    "pattern": r"^[\u0020-\u007e]*$(?![\s\S])",
}
_SHA256_INPUT = {
    "type": "string",
    "pattern": r"^sha256:[0-9a-f]{64}$",
    "minLength": 71,
    "maxLength": 71,
}


def _task_transition_input() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            **_TASK_SELECTOR_PROPERTIES,
            "body": _TASK_TRANSITION_BODY,
            "idempotency_key": _IDEMPOTENCY_KEY_INPUT,
        },
        "required": ["task_id", "idempotency_key"],
        "additionalProperties": False,
    }


TASK_EXECUTION_INPUT_SCHEMAS: dict[str, dict[str, Any]] = {
    "preparation_create": {
        "type": "object",
        "properties": {
            "task_id": _UUID_INPUT,
            "assignment_id": _UUID_INPUT,
            "zip_base64": {
                "type": "string",
                "minLength": 4,
                "maxLength": SUBMISSION_BUNDLE_MAX_BASE64_CHARS,
                "pattern": r"^[A-Za-z0-9+/]*={0,2}$",
            },
            "idempotency_key": _IDEMPOTENCY_KEY_INPUT,
            "summary": _ASCII_PACKET_TEXT,
            "contributor_attestation": _ASCII_PACKET_TEXT,
            "predecessor_submission_id": _UUID_INPUT,
            "revision_preparation_id": _UUID_INPUT,
            "revision_preparation_sha256": _SHA256_INPUT,
        },
        "required": ["task_id", "assignment_id", "zip_base64", "idempotency_key"],
        "allOf": [
            {
                "if": {"required": ["revision_preparation_id"]},
                "then": {"required": ["revision_preparation_sha256"]},
            },
            {
                "if": {"required": ["revision_preparation_sha256"]},
                "then": {"required": ["revision_preparation_id"]},
            },
        ],
        "additionalProperties": False,
    },
    "preparations_list": {
        "type": "object",
        "properties": {
            **_TASK_PAGE_PROPERTIES,
            "cursor": {**_TASK_PAGE_PROPERTIES["cursor"], "maxLength": 512},
        },
        "required": ["task_id"],
        "additionalProperties": False,
    },
    "preparation_get": {
        "type": "object",
        "properties": {"task_id": _UUID_INPUT, "preparation_id": _UUID_INPUT},
        "required": ["task_id", "preparation_id"],
        "additionalProperties": False,
    },
    "task_get": {
        "type": "object",
        "properties": _TASK_SELECTOR_PROPERTIES,
        "required": ["task_id"],
        "additionalProperties": False,
    },
    "task_submission_requirements_get": {
        "type": "object",
        "properties": _TASK_SELECTOR_PROPERTIES,
        "required": ["task_id"],
        "additionalProperties": False,
    },
    "task_screen": _task_transition_input(),
    "task_release": _task_transition_input(),
    "task_claim": _task_transition_input(),
    "task_start": _task_transition_input(),
    "task_work_context_get": {
        "type": "object",
        "properties": _TASK_SELECTOR_PROPERTIES,
        "required": ["task_id"],
        "additionalProperties": False,
    },
    "task_guide_document_content_get": {
        "type": "object",
        "properties": {"task_id": _UUID_INPUT, "document_id": _UUID_INPUT},
        "required": ["task_id", "document_id"],
        "additionalProperties": False,
    },
    "submission_create": {
        "type": "object",
        "properties": {
            "task_id": _UUID_INPUT,
            "body": {
                "type": "object",
                "properties": {
                    "admission_id": _UUID_INPUT,
                    "assignment_id": _UUID_INPUT,
                    "predecessor_submission_id": {"anyOf": [_UUID_INPUT, {"type": "null"}]},
                    "summary": {"type": ["string", "null"]},
                    "contributor_attestation": {"type": ["string", "null"]},
                },
                "required": ["admission_id", "assignment_id"],
                "additionalProperties": False,
            },
        },
        "required": ["task_id", "body"],
        "additionalProperties": False,
    },
    "task_submissions_list": {
        "type": "object",
        "properties": _TASK_PAGE_PROPERTIES,
        "required": ["task_id"],
        "additionalProperties": False,
    },
    "submission_get": {
        "type": "object",
        "properties": {"submission_id": _UUID_INPUT},
        "required": ["submission_id"],
        "additionalProperties": False,
    },
    "management_task_submissions_list": {
        "type": "object",
        "properties": {"project_id": _UUID_INPUT, **_TASK_PAGE_PROPERTIES},
        "required": ["project_id", "task_id"],
        "additionalProperties": False,
    },
    "management_submission_get": {
        "type": "object",
        "properties": {"project_id": _UUID_INPUT, "submission_id": _UUID_INPUT},
        "required": ["project_id", "submission_id"],
        "additionalProperties": False,
    },
    "management_task_work_context_get": {
        "type": "object",
        "properties": {"project_id": _UUID_INPUT, "task_id": _UUID_INPUT},
        "required": ["project_id", "task_id"],
        "additionalProperties": False,
    },
    "management_task_submission_requirements_get": {
        "type": "object",
        "properties": {"project_id": _UUID_INPUT, "task_id": _UUID_INPUT},
        "required": ["project_id", "task_id"],
        "additionalProperties": False,
    },
}
TASK_EXECUTION_CONTRACT_NAMES = tuple(TASK_EXECUTION_INPUT_SCHEMAS)

TASK_OPERATION_CONTRACT_NAMES = (
    "projects_list",
    "service_actor_create",
    "task_import_batch_create",
    "management_tasks_list",
    "management_task_create",
    "operational_tasks_list",
    "task_import_batch_screen",
    "task_import_batch_release",
    "task_import_batch_get",
    "management_task_get",
    "management_task_locked_context_get",
    "operational_task_locked_context_get",
    "audit_task_locked_context_get",
    "task_revision_context_repair",
    "audit_task_evidence_get",
    "operational_task_start_override",
    "project_model_profile_provision",
    "project_model_budget_configure",
    "project_model_usage_effect_get",
    "project_model_recovery_child_create",
    "task_import_source_declare",
    "task_import_source_content_upload",
    "task_import_source_content_get",
    "task_import_source_get",
)


class ContractError(RuntimeError):
    """The reviewed packaged contract is absent or invalid."""


_OUTPUT_FORMAT_CHECKER = FormatChecker()


def _resolve_schema_refs(value: Any, schemas: dict[str, Any]) -> Any:
    if isinstance(value, list):
        return [_resolve_schema_refs(item, schemas) for item in value]
    if not isinstance(value, dict):
        return value
    reference = value.get("$ref")
    prefix = "#/components/schemas/"
    if isinstance(reference, str) and reference.startswith(prefix):
        target = schemas.get(reference.removeprefix(prefix))
        if not isinstance(target, dict):
            raise ContractError("contract contains an unresolved schema reference")
        return _resolve_schema_refs(target, schemas)
    return {key: _resolve_schema_refs(item, schemas) for key, item in value.items()}


def _selected_schema(document: dict[str, Any]) -> dict[str, Any]:
    for key in ("output_schema", "outputSchema", "schema"):
        candidate = document.get(key)
        if isinstance(candidate, dict):
            return candidate
    if document.get("type") == "object":
        return document
    operation = document.get("operation")
    components = document.get("components")
    if isinstance(operation, dict) and isinstance(components, dict):
        schemas = components.get("schemas")
        responses = operation.get("responses")
        if isinstance(schemas, dict) and isinstance(responses, dict):
            success = next(
                (
                    response
                    for status, response in sorted(responses.items())
                    if status.startswith("2") and isinstance(response, dict)
                ),
                None,
            )
            content = success.get("content") if isinstance(success, dict) else None
            media = content.get("application/json") if isinstance(content, dict) else None
            selected = media.get("schema") if isinstance(media, dict) else None
            if isinstance(selected, dict):
                return cast(dict[str, Any], _resolve_schema_refs(selected, schemas))
    raise ContractError("contract does not contain an output schema")


def _contract_document(name: str) -> dict[str, Any]:
    filename = f"{name}.json"
    resource = files("workstream_mcp").joinpath(f"contracts/{filename}")
    try:
        document = json.loads(resource.read_text(encoding="utf-8"))
    except FileNotFoundError:
        source_contract = Path(__file__).resolve().parents[1] / "contracts" / filename
        try:
            document = json.loads(source_contract.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise ContractError(f"packaged {name} contract is missing or invalid") from exc
    except json.JSONDecodeError as exc:
        raise ContractError(f"packaged {name} contract is missing or invalid") from exc
    if not isinstance(document, dict):
        raise ContractError(f"{name} contract must be a JSON object")
    return document


@lru_cache(maxsize=128)
def _contract_output_schema(name: str) -> dict[str, Any]:
    document = _contract_document(name)
    schema = _selected_schema(document)
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        raise ContractError(f"{name} output schema is invalid") from exc
    return schema


def profile_output_schema() -> dict[str, Any]:
    return _contract_output_schema("profile_get")


def profile_update_output_schema() -> dict[str, Any]:
    return _contract_output_schema("profile_update")


def authorization_context_output_schema() -> dict[str, Any]:
    return _contract_output_schema("authorization_context_get")


@lru_cache(maxsize=128)
def _contract_output_validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(
        _contract_output_schema(name),
        format_checker=_OUTPUT_FORMAT_CHECKER,
    )


def profile_output_validator() -> Draft202012Validator:
    return _contract_output_validator("profile_get")


def profile_update_output_validator() -> Draft202012Validator:
    return _contract_output_validator("profile_update")


def authorization_context_output_validator() -> Draft202012Validator:
    return _contract_output_validator("authorization_context_get")


def access_read_output_schema(name: str) -> dict[str, Any]:
    """Load one of the six reviewed administrative read projections."""
    if name not in ACCESS_READ_INPUT_SCHEMAS:
        raise ContractError("unknown administrative read contract")
    return _contract_output_schema(name)


def access_read_output_validator(name: str) -> Draft202012Validator:
    """Validate a bounded administrative projection, including formats."""
    access_read_output_schema(name)
    return _contract_output_validator(name)


def admin_grant_output_schema(name: str) -> dict[str, Any]:
    """Load one of the reviewed administrative mutation receipts."""
    if name not in ADMIN_GRANT_INPUT_SCHEMAS:
        raise ContractError("unknown administrative grant contract")
    return _contract_output_schema(name)


def admin_grant_output_validator(name: str) -> Draft202012Validator:
    """Validate one administrative mutation receipt, including formats."""
    admin_grant_output_schema(name)
    return _contract_output_validator(name)


def actor_lifecycle_output_schema(name: str) -> dict[str, Any]:
    """Load one reviewed actor or identity-link lifecycle receipt."""
    if name not in ACTOR_LIFECYCLE_INPUT_SCHEMAS:
        raise ContractError("unknown actor lifecycle contract")
    return _contract_output_schema(name)


def actor_lifecycle_output_validator(name: str) -> Draft202012Validator:
    """Validate one actor or identity-link lifecycle receipt."""
    actor_lifecycle_output_schema(name)
    return _contract_output_validator(name)


def project_output_schema(name: str) -> dict[str, Any]:
    """Load one reviewed project-shell response contract."""
    if name not in PROJECT_INPUT_SCHEMAS:
        raise ContractError("unknown project contract")
    schema = _contract_output_schema(name)
    if name == "projects_get" and "type" not in schema:
        # MCP requires object-rooted tool outputs; retain FastAPI's exact union.
        return {"type": "object", **schema}
    return schema


def project_output_validator(name: str) -> Draft202012Validator:
    """Validate one project-shell response projection."""
    return Draft202012Validator(
        project_output_schema(name),
        format_checker=_OUTPUT_FORMAT_CHECKER,
    )


def project_grant_output_schema(name: str) -> dict[str, Any]:
    """Load one reviewed project-participation response contract."""
    if name not in PROJECT_GRANT_INPUT_SCHEMAS:
        raise ContractError("unknown project participation contract")
    return _contract_output_schema(name)


def project_grant_output_validator(name: str) -> Draft202012Validator:
    """Validate one project-participation response projection."""
    return _contract_output_validator(name)


def guide_output_schema(name: str) -> dict[str, Any]:
    """Load one reviewed guide-mutation response contract."""
    if name not in GUIDE_INPUT_SCHEMAS:
        raise ContractError("unknown guide contract")
    return _contract_output_schema(name)


def guide_output_validator(name: str) -> Draft202012Validator:
    """Validate one guide-mutation response projection."""
    return _contract_output_validator(name)


def policy_output_schema(name: str) -> dict[str, Any]:
    """Load one reviewed draft-policy mutation response contract."""
    if name not in POLICY_INPUT_SCHEMAS:
        raise ContractError("unknown policy contract")
    return _contract_output_schema(name)


def policy_output_validator(name: str) -> Draft202012Validator:
    """Validate one draft-policy mutation response projection."""
    return _contract_output_validator(name)


def workspace_read_output_schema(name: str) -> dict[str, Any]:
    if name not in WORKSPACE_READ_INPUT_SCHEMAS:
        raise ContractError("unknown workspace read contract")
    return _contract_output_schema(name)


def workspace_read_output_validator(name: str) -> Draft202012Validator:
    workspace_read_output_schema(name)
    return _contract_output_validator(name)


def contribution_policy_output_schema(name: str) -> dict[str, Any]:
    if name not in CONTRIBUTION_POLICY_INPUT_SCHEMAS:
        raise ContractError("unknown contribution policy contract")
    return _contract_output_schema(name)


def contribution_policy_output_validator(name: str) -> Draft202012Validator:
    contribution_policy_output_schema(name)
    return _contract_output_validator(name)


GUIDE_LIFECYCLE_CONTRACT_NAMES = (
    "project_guides_list",
    "project_guide_get",
    "guide_activate",
    "guide_activation_readiness_get",
    "guide_proposal_correct",
    "guide_correction_dispatch",
    "guide_post_policy_get",
    "guide_post_policy_approve",
    "guide_post_policy_correct",
    "guide_pre_submission_approve",
    "guide_proposal_get",
    "guide_document_upload",
    "guide_document_content_get",
    "guide_effective_submission_artifact_policy_get",
    "guide_pre_submit_checker_policy_get",
    "guide_setup_latest_get",
    "guide_submission_artifact_policies_list",
    "guide_submission_artifact_policy_create",
    "guide_submission_artifact_policy_get",
    "guide_submission_artifact_policy_update",
    "guide_sufficiency_reports_list",
    "guide_sufficiency_report_create",
    "guide_sufficiency_report_get",
    "guide_sufficiency_warnings_acknowledge",
)

GUIDE_DOCUMENT_CONTENT_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "media_type": {"type": "string", "minLength": 1, "maxLength": 200},
        "content_base64": {"type": "string", "minLength": 1},
        "byte_count": {"type": "integer", "minimum": 1},
        "sha256": {"type": "string", "pattern": r"^sha256:[0-9a-f]{64}$"},
    },
    "required": ["media_type", "content_base64", "byte_count", "sha256"],
    "additionalProperties": False,
}

_GUIDE_DOCUMENT_UPLOAD_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "project_id": _UUID_INPUT,
        "guide_id": _UUID_INPUT,
        "document_id": _UUID_INPUT,
        "media_type": {
            "type": "string",
            "enum": list(GUIDE_DOCUMENT_MEDIA_TYPES),
        },
        "content_base64": {
            "type": "string",
            "minLength": 1,
            "maxLength": GUIDE_DOCUMENT_MAX_BASE64_CHARS,
        },
        "idempotency_key": _IDEMPOTENCY_KEY_INPUT,
    },
    "required": [
        "project_id",
        "guide_id",
        "document_id",
        "media_type",
        "content_base64",
        "idempotency_key",
    ],
    "additionalProperties": False,
}


def guide_lifecycle_input_schema(name: str) -> dict[str, Any]:
    """Build a closed MCP input from one reviewed fixed-route snapshot."""
    if name not in GUIDE_LIFECYCLE_CONTRACT_NAMES:
        raise ContractError("unknown guide lifecycle contract")
    if name == "guide_document_upload":
        return _GUIDE_DOCUMENT_UPLOAD_INPUT_SCHEMA
    document = _contract_document(name)
    operation = document.get("operation")
    components = document.get("components")
    if not isinstance(operation, dict) or not isinstance(components, dict):
        raise ContractError("guide lifecycle contract is missing operation metadata")
    schemas = components.get("schemas")
    if not isinstance(schemas, dict):
        raise ContractError("guide lifecycle contract is missing component schemas")
    properties: dict[str, Any] = {}
    required: list[str] = []
    for parameter in operation.get("parameters", []):
        if not isinstance(parameter, dict):
            raise ContractError("guide lifecycle parameter is invalid")
        location = parameter.get("in")
        wire_name = parameter.get("name")
        if not isinstance(wire_name, str):
            raise ContractError("guide lifecycle parameter name is invalid")
        if location == "header":
            if wire_name.lower() != "idempotency-key":
                continue
            field_name = "idempotency_key"
        elif location in {"path", "query"}:
            field_name = wire_name
        else:
            continue
        raw_schema = parameter.get("schema")
        if not isinstance(raw_schema, dict):
            raise ContractError("guide lifecycle parameter schema is invalid")
        properties[field_name] = _resolve_schema_refs(raw_schema, schemas)
        if parameter.get("required") is True or field_name == "idempotency_key":
            required.append(field_name)
    request_body = operation.get("requestBody")
    if isinstance(request_body, dict):
        content = request_body.get("content")
        media = content.get("application/json") if isinstance(content, dict) else None
        raw_schema = media.get("schema") if isinstance(media, dict) else None
        if isinstance(raw_schema, dict):
            properties["body"] = _resolve_schema_refs(raw_schema, schemas)
            if request_body.get("required") is True:
                required.append("body")
    result: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        result["required"] = list(dict.fromkeys(required))
    Draft202012Validator.check_schema(result)
    return result


def guide_lifecycle_output_schema(name: str) -> dict[str, Any]:
    if name not in GUIDE_LIFECYCLE_CONTRACT_NAMES:
        raise ContractError("unknown guide lifecycle contract")
    if name == "guide_document_content_get":
        return GUIDE_DOCUMENT_CONTENT_OUTPUT_SCHEMA
    schema = _contract_output_schema(name)
    if schema.get("type") == "array":
        return {
            "type": "object",
            "properties": {"items": schema},
            "required": ["items"],
            "additionalProperties": False,
        }
    return schema


def guide_lifecycle_output_validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(
        guide_lifecycle_output_schema(name),
        format_checker=_OUTPUT_FORMAT_CHECKER,
    )


CHECKER_ARTIFACT_CONTRACT_NAMES = (
    "submission_checker_runs_list",
    "submission_checker_runs_get",
    "project_checker_runs_list",
    "project_checker_runs_get",
    "checker_retry_sources_list",
    "checker_runs_retry",
    "post_submit_deliveries_list",
    "post_submit_deliveries_reconcile",
    "checker_registry_read",
    "checker_registry_register",
    "artifact_readiness_get",
    "artifact_bindings_list",
    "artifact_replicas_list",
    "artifact_receipts_list",
    "artifact_verification_job_get",
    "artifact_verification_job_retry",
    "artifact_recovery_attempt_get",
    "artifact_admission_usage_get",
    "artifact_audit_events_list",
)


@lru_cache(maxsize=32)
def checker_artifact_input_schema(name: str) -> dict[str, Any]:
    """Build a closed MCP input from one reviewed public operation."""
    if name not in CHECKER_ARTIFACT_CONTRACT_NAMES:
        raise ContractError("unknown checker or artifact contract")
    document = _contract_document(name)
    operation = document.get("operation")
    components = document.get("components")
    if not isinstance(operation, dict) or not isinstance(components, dict):
        raise ContractError(f"{name} contract is missing its operation")
    schemas = components.get("schemas")
    if not isinstance(schemas, dict):
        raise ContractError(f"{name} contract is missing schemas")

    properties: dict[str, Any] = {}
    required: list[str] = []
    parameters = operation.get("parameters", [])
    if not isinstance(parameters, list):
        raise ContractError(f"{name} parameters are invalid")
    for parameter in parameters:
        if not isinstance(parameter, dict):
            raise ContractError(f"{name} parameter is invalid")
        location = parameter.get("in")
        parameter_name = parameter.get("name")
        if location == "header":
            if parameter_name == "Idempotency-Key":
                properties["idempotency_key"] = _IDEMPOTENCY_KEY_INPUT
                if parameter.get("required") is True:
                    required.append("idempotency_key")
            continue
        if location not in {"path", "query"} or not isinstance(parameter_name, str):
            continue
        parameter_schema = parameter.get("schema")
        if not isinstance(parameter_schema, dict):
            raise ContractError(f"{name} parameter schema is invalid")
        properties[parameter_name] = _resolve_schema_refs(parameter_schema, schemas)
        if parameter.get("required") is True:
            required.append(parameter_name)

    request_body = operation.get("requestBody")
    if isinstance(request_body, dict):
        content = request_body.get("content")
        media = content.get("application/json") if isinstance(content, dict) else None
        body_schema = media.get("schema") if isinstance(media, dict) else None
        if not isinstance(body_schema, dict):
            raise ContractError(f"{name} request body schema is invalid")
        properties["body"] = _resolve_schema_refs(body_schema, schemas)
        if request_body.get("required") is True:
            required.append("body")

    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    Draft202012Validator.check_schema(schema)
    return schema


def checker_artifact_output_schema(name: str) -> dict[str, Any]:
    if name not in CHECKER_ARTIFACT_CONTRACT_NAMES:
        raise ContractError("unknown checker or artifact contract")
    return _contract_output_schema(name)


def checker_artifact_output_validator(name: str) -> Draft202012Validator:
    checker_artifact_output_schema(name)
    return _contract_output_validator(name)


def task_execution_output_schema(name: str) -> dict[str, Any]:
    """Load one reviewed task/submission response or the bounded binary projection."""
    if name not in TASK_EXECUTION_INPUT_SCHEMAS:
        raise ContractError("unknown task execution contract")
    if name == "task_guide_document_content_get":
        return GUIDE_DOCUMENT_CONTENT_OUTPUT_SCHEMA
    return _contract_output_schema(name)


def task_execution_output_validator(name: str) -> Draft202012Validator:
    """Validate one task/submission response projection."""
    return Draft202012Validator(
        task_execution_output_schema(name),
        format_checker=_OUTPUT_FORMAT_CHECKER,
    )


TASK_IMPORT_SOURCE_CONTENT_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "media_type": {"const": "application/json"},
        "content_base64": {
            "type": "string",
            "minLength": 1,
            "maxLength": TASK_IMPORT_SOURCE_MAX_BASE64_CHARS,
        },
        "byte_count": {
            "type": "integer",
            "minimum": 1,
            "maximum": 8 * 1024 * 1024,
        },
        "sha256": {"type": "string", "pattern": r"^sha256:[0-9a-f]{64}$"},
    },
    "required": ["media_type", "content_base64", "byte_count", "sha256"],
    "additionalProperties": False,
}


@lru_cache(maxsize=32)
def task_operation_input_schema(name: str) -> dict[str, Any]:
    """Build a closed input from one reviewed task-operation contract."""
    if name not in TASK_OPERATION_CONTRACT_NAMES:
        raise ContractError("unknown task operation contract")
    document = _contract_document(name)
    operation = document.get("operation")
    components = document.get("components")
    if not isinstance(operation, dict) or not isinstance(components, dict):
        raise ContractError(f"{name} contract is missing its operation")
    schemas = components.get("schemas")
    if not isinstance(schemas, dict):
        raise ContractError(f"{name} contract is missing schemas")

    properties: dict[str, Any] = {}
    required: list[str] = []
    parameters = operation.get("parameters", [])
    if not isinstance(parameters, list):
        raise ContractError(f"{name} parameters are invalid")
    for parameter in parameters:
        if not isinstance(parameter, dict):
            raise ContractError(f"{name} parameter is invalid")
        location = parameter.get("in")
        wire_name = parameter.get("name")
        if location == "header":
            if wire_name == "Idempotency-Key":
                properties["idempotency_key"] = _IDEMPOTENCY_KEY_INPUT
                if parameter.get("required") is True:
                    required.append("idempotency_key")
            continue
        if location not in {"path", "query"} or not isinstance(wire_name, str):
            continue
        raw_schema = parameter.get("schema")
        if not isinstance(raw_schema, dict):
            raise ContractError(f"{name} parameter schema is invalid")
        resolved = _resolve_schema_refs(raw_schema, schemas)
        if name == "audit_task_evidence_get" and wire_name == "cursor":
            resolved = {
                "anyOf": [
                    {"type": "string", "minLength": 1, "maxLength": 512},
                    {"type": "null"},
                ]
            }
        properties[wire_name] = resolved
        if parameter.get("required") is True:
            required.append(wire_name)

    request_body = operation.get("requestBody")
    if isinstance(request_body, dict):
        if name == "task_import_source_content_upload":
            properties["content_base64"] = {
                "type": "string",
                "minLength": 1,
                "maxLength": TASK_IMPORT_SOURCE_MAX_BASE64_CHARS,
            }
            required.append("content_base64")
        else:
            content = request_body.get("content")
            media = content.get("application/json") if isinstance(content, dict) else None
            raw_schema = media.get("schema") if isinstance(media, dict) else None
            if not isinstance(raw_schema, dict):
                raise ContractError(f"{name} request body schema is invalid")
            properties["body"] = _resolve_schema_refs(raw_schema, schemas)
            if request_body.get("required") is True:
                required.append("body")

    result: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        result["required"] = list(dict.fromkeys(required))
    Draft202012Validator.check_schema(result)
    return result


def task_operation_output_schema(name: str) -> dict[str, Any]:
    if name not in TASK_OPERATION_CONTRACT_NAMES:
        raise ContractError("unknown task operation contract")
    if name == "task_import_source_content_get":
        return TASK_IMPORT_SOURCE_CONTENT_OUTPUT_SCHEMA
    return _contract_output_schema(name)


def task_operation_output_validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(
        task_operation_output_schema(name),
        format_checker=_OUTPUT_FORMAT_CHECKER,
    )
