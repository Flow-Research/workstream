"""Exact immutable v2 reward selection; values never confer owner authority."""

import re
from typing import Annotated, Literal, Protocol, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator

from app.core.financial_wire import require_canonical_quantity
from app.modules.compensation.api.instruments import CompensationInstrumentType

TaskSize = Literal["small", "medium", "large"]
_STRICT = ConfigDict(frozen=True, extra="forbid", strict=True, revalidate_instances="always")
_Unit = Annotated[StrictStr, Field(pattern=r"^[A-Za-z][A-Za-z0-9._:-]{0,31}$")]


class RewardSelectionRequest(BaseModel):
    """Caller-selected exact policy and size; never a current-policy lookup."""

    model_config = _STRICT

    project_id: UUID
    policy_version_id: UUID
    task_size: TaskSize


class RewardSelectionFacts(BaseModel):
    """Complete selected terms copied into locked work and revision evidence."""

    model_config = _STRICT

    policy_version_id: UUID
    task_size: TaskSize
    compensation_mode: Literal["unpaid", "compensated"]
    award_definition_id: UUID | None
    instrument_type: CompensationInstrumentType | None
    unit_code: _Unit | None
    quantity: StrictStr | None
    adapter_binding_id: UUID | None

    @model_validator(mode="after")
    def exact_financial_shape(self) -> Self:
        """Unpaid is explicit null; compensated is one exact canonical definition."""
        financial = (
            self.award_definition_id,
            self.instrument_type,
            self.unit_code,
            self.quantity,
            self.adapter_binding_id,
        )
        if self.compensation_mode == "unpaid":
            if any(value is not None for value in financial):
                raise ValueError("unpaid selection cannot contain financial terms")
        else:
            if any(value is None for value in financial):
                raise ValueError("compensated selection requires every exact financial fact")
            require_canonical_quantity(self.quantity, self.instrument_type.value)
            if (
                self.instrument_type is CompensationInstrumentType.MONEY
                and re.fullmatch(r"[A-Z]{3}", self.unit_code) is None
            ):
                raise ValueError("money selection requires its exact currency code")
        return self


class RewardSelectionPort(Protocol):
    """Resolve only an exact v2 policy under the caller's existing transaction."""

    async def resolve_reward_selection(
        self, request: RewardSelectionRequest
    ) -> RewardSelectionFacts:
        """Verify project, policy and tier ownership; never select by wall-clock time."""
        ...
