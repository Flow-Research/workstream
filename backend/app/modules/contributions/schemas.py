"""Closed persistence inputs for contribution-policy economic truth."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
import re
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.compensation.api import (
    CompensationInstrumentType as ContributionInstrumentType,
)
from app.modules.contributions.policy_validation import canonical_award_quantity


_PROJECT_ID_PATTERN = r"^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$"
_MONEY_UNIT_PATTERN = re.compile(r"^[A-Z]{3}$")
_POINTS_UNIT_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9._:-]{0,31}$")
# Mirrors the migration-owned SIX ISO 4217 List One snapshot dated 2026-08-04.
ISO_4217_CURRENCY_CODES = frozenset(
    """AED AFN ALL AMD AOA ARS AUD AWG AZN BAM BBD BDT BHD BIF BMD BND BOB BOV
    BRL BSD BTN BWP BYN BZD CAD CDF CHE CHF CHW CLF CLP CNY COP COU CRC CUP CVE
    CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD GNF GTQ GYD
    HKD HNL HTG HUF IDR ILS INR IQD IRR ISK JMD JOD JPY KES KGS KHR KMF KPW
    KRW KWD KYD KZT LAK LBP LKR LRD LSL LYD MAD MDL MGA MKD MMK MNT MOP MRU
    MUR MVR MWK MXN MXV MYR MZN NAD NGN NIO NOK NPR NZD OMR PAB PEN PGK PHP PKR
    PLN PYG QAR RON RSD RUB RWF SAR SBD SCR SDG SEK SGD SHP SLE SOS SRD SSP STN
    SVC SYP SZL THB TJS TMT TND TOP TRY TTD TWD TZS UAH UGX USD USN UYI UYU
    UYW UZS VED VES VND VUV WST XAD XAF XAG XAU XBA XBB XBC XBD XCD XCG XDR
    XOF XPD XPF XPT XSU XTS XUA XXX YER ZAR ZMW ZWG""".split()
)


class ContributionPolicyStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    RETIRED = "retired"


class ContributionPolicyVersionStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    RETIRED = "retired"


class ContributionType(StrEnum):
    ACCEPTED_SUBMISSION = "accepted_submission"
    COMPLETED_REVIEW = "completed_review"


class CompensationMode(StrEnum):
    UNPAID = "unpaid"
    COMPENSATED = "compensated"


class ContributionPolicyInput(BaseModel):
    """Structural policy aggregate facts; grants no publish authority."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    project_id: str = Field(pattern=_PROJECT_ID_PATTERN)
    name: str = Field(min_length=1, max_length=200)
    created_by: str = Field(pattern=_PROJECT_ID_PATTERN)

    @field_validator("name")
    @classmethod
    def reject_blank_name(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("name must not have surrounding whitespace")
        return value


class ContributionPolicyVersionInput(BaseModel):
    """Structural draft version identity; lifecycle behavior is deferred."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    contribution_policy_id: UUID
    project_id: str = Field(pattern=_PROJECT_ID_PATTERN)
    version_number: int = Field(gt=0)
    created_by: str = Field(pattern=_PROJECT_ID_PATTERN)


class ContributionRuleInput(BaseModel):
    """One closed contribution rule for a policy version."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    contribution_policy_version_id: UUID
    project_id: str = Field(pattern=_PROJECT_ID_PATTERN)
    contribution_type: ContributionType
    compensation_mode: CompensationMode


class ProjectCompensationUnitInput(BaseModel):
    """Structural project-unit facts; 03B exposes no lifecycle command."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    project_id: str = Field(pattern=_PROJECT_ID_PATTERN)
    instrument_type: ContributionInstrumentType
    unit_code: str = Field(min_length=1, max_length=32)
    created_by: str = Field(pattern=_PROJECT_ID_PATTERN)

    @model_validator(mode="after")
    def validate_registered_unit(self) -> "ProjectCompensationUnitInput":
        if self.instrument_type is ContributionInstrumentType.MONEY:
            if self.unit_code not in ISO_4217_CURRENCY_CODES:
                raise ValueError("money unit_code must be a current ISO 4217 code")
        elif _POINTS_UNIT_PATTERN.fullmatch(self.unit_code) is None:
            raise ValueError("project_points unit_code is invalid")
        return self


class ContributionAwardDefinitionInput(BaseModel):
    """Canonical fixed-point award definition facts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    contribution_rule_id: UUID
    contribution_policy_version_id: UUID
    project_id: str = Field(pattern=_PROJECT_ID_PATTERN)
    contribution_type: ContributionType
    instrument_type: ContributionInstrumentType
    unit_code: str = Field(min_length=1, max_length=32)
    quantity: str
    adapter_binding_id: UUID

    @field_validator("quantity", mode="before")
    @classmethod
    def require_canonical_decimal_string(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("quantity must be a canonical positive decimal string")
        canonical_award_quantity(value)
        return value

    @model_validator(mode="after")
    def validate_unit_for_instrument(self) -> "ContributionAwardDefinitionInput":
        pattern = (
            _MONEY_UNIT_PATTERN
            if self.instrument_type is ContributionInstrumentType.MONEY
            else _POINTS_UNIT_PATTERN
        )
        if pattern.fullmatch(self.unit_code) is None:
            raise ValueError("unit_code does not match instrument_type")
        if (
            self.instrument_type is ContributionInstrumentType.MONEY
            and self.unit_code not in ISO_4217_CURRENCY_CODES
        ):
            raise ValueError("money unit_code must be a current ISO 4217 code")
        canonical_award_quantity(self.quantity, self.instrument_type)
        return self

    def quantity_decimal(self) -> Decimal:
        """Return the already-validated exact database value without rounding."""
        return Decimal(self.quantity)
