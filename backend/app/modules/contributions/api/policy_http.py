"""Closed delivery inputs using the canonical owner rule graph."""

import re

from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator
from uuid import UUID

from app.modules.compensation.api.instruments import CompensationInstrumentType
from app.modules.contributions.api.quantities import canonical_award_quantity

from app.modules.contributions.api.policies import PolicyRuleInput

_POLICY_GRAPH_SCHEMA = {
    "allOf": [
        *[
            {
                "properties": {
                    "rules": {
                        "contains": {
                            "properties": {"contribution_type": {"const": kind}},
                            "required": ["contribution_type"],
                        },
                        "minContains": 1,
                        "maxContains": 1,
                    }
                }
            }
            for kind in ("accepted_submission", "completed_review")
        ],
        {
            "if": {
                "properties": {
                    "rules": {
                        "contains": {
                            "properties": {"compensation_mode": {"const": "compensated"}},
                            "required": ["compensation_mode"],
                        }
                    }
                }
            },
            "then": {
                "properties": {
                    "instrument_type": {"type": "string"},
                    "unit_code": {
                        "type": "string",
                        "pattern": r"^[A-Za-z][A-Za-z0-9._:-]{0,31}$",
                        "not": {"pattern": r"[^A-Za-z0-9._:-]"},
                    },
                    "adapter_binding_id": {"type": "string"},
                }
            },
            "else": {
                "properties": {
                    name: {"type": "null"}
                    for name in (
                        "instrument_type",
                        "unit_code",
                        "adapter_binding_id",
                    )
                }
            },
        },
        {
            "if": {"properties": {"instrument_type": {"const": "money"}}},
            "then": {
                "properties": {
                    "unit_code": {
                        "type": "string",
                        "pattern": r"^[A-Z]{3}$",
                        "not": {"pattern": "[^A-Z]"},
                    }
                }
            },
        },
        {
            "if": {"properties": {"instrument_type": {"const": "project_points"}}},
            "then": {
                "properties": {
                    "rules": {
                        "items": {
                            "properties": {
                                "quantity": {
                                    "pattern": r"^[1-9][0-9]{0,19}$",
                                    "not": {"pattern": "[^0-9]"},
                                },
                                "quantities": {
                                    "properties": {
                                        size: {
                                            "pattern": r"^[1-9][0-9]{0,19}$",
                                            "not": {"pattern": "[^0-9]"},
                                        }
                                        for size in ("small", "medium", "large")
                                    }
                                },
                            }
                        }
                    }
                }
            },
        },
    ],
}


class PolicyCreateInput(BaseModel):
    """Initialize a new policy name; successor drafts retain the aggregate name."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str = Field(min_length=1, max_length=200)


class PolicyUpdateInput(BaseModel):
    """Replace the complete graph without client-generated row identifiers."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=_POLICY_GRAPH_SCHEMA)
    instrument_type: CompensationInstrumentType | None
    unit_code: StrictStr | None
    adapter_binding_id: UUID | None
    rules: tuple[PolicyRuleInput, ...] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def exact_policy_header_and_rules(self):
        if {rule.contribution_type for rule in self.rules} != {
            "accepted_submission",
            "completed_review",
        }:
            raise ValueError("one rule of each contribution type is required")
        paid = any(rule.compensation_mode == "compensated" for rule in self.rules)
        header = (self.instrument_type, self.unit_code, self.adapter_binding_id)
        if not paid:
            if any(value is not None for value in header):
                raise ValueError("wholly unpaid policy has null financial headers")
        else:
            if any(value is None for value in header):
                raise ValueError("compensated policy requires its common financial headers")
            pattern = (
                r"[A-Z]{3}"
                if self.instrument_type is CompensationInstrumentType.MONEY
                else r"[A-Za-z][A-Za-z0-9._:-]{0,31}"
            )
            if re.fullmatch(pattern, self.unit_code) is None:
                raise ValueError("invalid policy unit")
            for rule in self.rules:
                if rule.compensation_mode == "compensated":
                    quantities = (
                        rule.quantities.model_dump().values()
                        if rule.contribution_type == "accepted_submission"
                        else (rule.quantity,)
                    )
                    for quantity in quantities:
                        canonical_award_quantity(quantity, self.instrument_type)
        return self


class PolicyDecisionInput(BaseModel):
    """An explicit decision on the path-selected version; no replacement graph."""

    model_config = ConfigDict(extra="forbid", frozen=True)
