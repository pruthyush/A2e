"""Domain models for Assurance Expiry Engine (AEE).

Enforces strict Pydantic v2 validation with extra='forbid' and comprehensive
foreign-key resolution across the assurance topology.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DomainBaseModel(BaseModel):
    """Base class enforcing strict schema with extra='forbid'."""

    model_config = ConfigDict(extra="forbid")


class Asset(DomainBaseModel):
    """OT/ICS Asset within an architectural zone."""

    asset_id: str
    name: str
    zone_id: str
    criticality: Literal["safety", "high", "medium", "low"]
    patch_status: Literal["patchable", "unpatchable", "deferred"]
    notes: str | None = None


class Zone(DomainBaseModel):
    """Security zone defined under IEC 62443."""

    zone_id: str
    name: str
    purdue_level: int | str
    security_level_target: str | int | None = None


class Conduit(DomainBaseModel):
    """Communications conduit between zones under IEC 62443."""

    conduit_id: str
    source_zone: str
    destination_zone: str
    allowed_protocols: list[str] = Field(default_factory=list)


class CompensatingControl(DomainBaseModel):
    """Compensating control offsetting an unpatched or deferred risk."""

    control_id: str
    name: str
    asset_id: str
    control_type: str
    description: str
    owner: str
    implemented_at: datetime
    expires_at: datetime | None = None
    status: Literal["active", "expired", "ineffective"]
    evidence_ids: list[str] = Field(default_factory=list)


class Evidence(DomainBaseModel):
    """Cryptographically verifiable evidence supporting a compensating control."""

    evidence_id: str
    control_id: str
    evidence_type: str
    collected_at: datetime
    valid_until: datetime | None = None
    status: Literal["current", "stale", "missing"]
    source: str
    sha256: str


class AssuranceClaim(DomainBaseModel):
    """Formal IEC 62443 assurance claim supported by controls and evidence."""

    claim_id: str
    asset_id: str
    zone_id: str
    conduit_id: str | None = None
    framework: Literal["IEC_62443"]
    requirement_ref: str
    security_level_target: str | int | None = None
    statement: str
    status: Literal["assured", "under_review", "invalidated"]
    supporting_control_ids: list[str] = Field(default_factory=list)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    last_reviewed_at: datetime | None = None
    reviewer: str | None = None


class ReviewRecord(DomainBaseModel):
    """Append-only audit record documenting human reassessment decisions."""

    record_id: str
    timestamp: datetime
    actor: str
    action: Literal["invalidate", "approve", "reject"]
    claim_id: str
    reason: str
    previous_status: str
    new_status: str
    dependency_snapshot: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None


class AssuranceModel(DomainBaseModel):
    """Complete facility assurance model topology with relational validation."""

    facility: str
    standard: str
    assets: list[Asset] = Field(default_factory=list)
    zones: list[Zone] = Field(default_factory=list)
    conduits: list[Conduit] = Field(default_factory=list)
    controls: list[CompensatingControl] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    claims: list[AssuranceClaim] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_foreign_keys(self) -> AssuranceModel:
        """Enforce that every foreign key resolves, naming any missing IDs precisely."""
        errors: list[str] = []

        zone_ids = {z.zone_id for z in self.zones}
        asset_ids = {a.asset_id for a in self.assets}
        conduit_ids = {c.conduit_id for c in self.conduits}
        control_ids = {c.control_id for c in self.controls}
        evidence_ids = {e.evidence_id for e in self.evidence}

        # 1. Assets -> Zones
        for asset in self.assets:
            if asset.zone_id not in zone_ids:
                errors.append(
                    f"Asset '{asset.asset_id}' references unknown zone_id '{asset.zone_id}'"
                )

        # 2. Conduits -> Zones
        for conduit in self.conduits:
            if conduit.source_zone not in zone_ids:
                errors.append(
                    f"Conduit '{conduit.conduit_id}' references "
                    f"unknown source_zone '{conduit.source_zone}'"
                )
            if conduit.destination_zone not in zone_ids:
                errors.append(
                    f"Conduit '{conduit.conduit_id}' references "
                    f"unknown destination_zone '{conduit.destination_zone}'"
                )

        # 3. CompensatingControls -> Assets, Evidence
        for control in self.controls:
            if control.asset_id not in asset_ids:
                errors.append(
                    f"CompensatingControl '{control.control_id}' references "
                    f"unknown asset_id '{control.asset_id}'"
                )
            for eid in control.evidence_ids:
                if eid not in evidence_ids:
                    errors.append(
                        f"CompensatingControl '{control.control_id}' references "
                        f"unknown evidence_id '{eid}'"
                    )

        # 4. Evidence -> CompensatingControls
        for ev in self.evidence:
            if ev.control_id not in control_ids:
                errors.append(
                    f"Evidence '{ev.evidence_id}' references unknown control_id '{ev.control_id}'"
                )

        # 5. AssuranceClaims -> Assets, Zones, Conduits, Controls, Evidence
        for claim in self.claims:
            if claim.asset_id not in asset_ids:
                errors.append(
                    f"AssuranceClaim '{claim.claim_id}' references "
                    f"unknown asset_id '{claim.asset_id}'"
                )
            if claim.zone_id not in zone_ids:
                errors.append(
                    f"AssuranceClaim '{claim.claim_id}' references "
                    f"unknown zone_id '{claim.zone_id}'"
                )
            if claim.conduit_id is not None and claim.conduit_id not in conduit_ids:
                errors.append(
                    f"AssuranceClaim '{claim.claim_id}' references "
                    f"unknown conduit_id '{claim.conduit_id}'"
                )
            for cid in claim.supporting_control_ids:
                if cid not in control_ids:
                    errors.append(
                        f"AssuranceClaim '{claim.claim_id}' references "
                        f"unknown supporting_control_id '{cid}'"
                    )
            for eid in claim.supporting_evidence_ids:
                if eid not in evidence_ids:
                    errors.append(
                        f"AssuranceClaim '{claim.claim_id}' references "
                        f"unknown supporting_evidence_id '{eid}'"
                    )

        if errors:
            raise ValueError(
                f"Foreign key resolution failed with {len(errors)} error(s): "
                + "; ".join(errors)
            )

        return self
