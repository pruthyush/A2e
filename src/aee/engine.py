"""Deterministic core evaluation engine for Assurance Expiry Engine (AEE).

Pure functions for temporal evaluation of compensating controls and evidence,
transitive invalidation propagation, and atomic review record generation.
No I/O, no printing, no datetime.now() calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from aee.models import AssuranceModel, ReviewRecord


@dataclass
class StateChange:
    """Represents a temporal state transition for a control or evidence."""

    entity_type: str  # "control" | "evidence"
    entity_id: str
    previous_state: str
    new_state: str
    reason: str
    effective_at: datetime


@dataclass
class Invalidation:
    """Represents an invalidation event for a dependent assurance claim."""

    claim_id: str
    triggering_entity_type: str  # "control" | "evidence"
    triggering_entity_id: str
    reason: str
    dependent_controls: list[str]
    dependent_evidence: list[str]
    previous_status: str


def _is_expired(dt: datetime | None, now: datetime) -> bool:
    """Check if a datetime is at or before the evaluation reference time."""
    if dt is None:
        return False
    if dt.tzinfo is not None and now.tzinfo is None:
        now_aware = now.replace(tzinfo=timezone.utc)
        return dt <= now_aware
    if dt.tzinfo is None and now.tzinfo is not None:
        dt_aware = dt.replace(tzinfo=now.tzinfo)
        return dt_aware <= now
    return dt <= now


def evaluate_states(
    model: AssuranceModel,
    now: datetime,
) -> list[StateChange]:
    """Evaluate controls and evidence against reference time `now`.

    - Control with expires_at <= now -> "expired".
    - Evidence with valid_until <= now -> "stale".
    - Control explicitly marked "ineffective" -> StateChange with reason "marked ineffective".
    - Already-expired / already-stale entities are NOT re-emitted.
    - Deterministic order: entity_type, then entity_id.

    Args:
        model: AssuranceModel to evaluate.
        now: Explicit evaluation timestamp.

    Returns:
        List of StateChange events sorted by entity_type, then entity_id.
    """
    changes: list[StateChange] = []

    # Evaluate compensating controls
    for control in model.controls:
        if control.status == "ineffective":
            effective_at = control.expires_at if control.expires_at is not None else now
            changes.append(
                StateChange(
                    entity_type="control",
                    entity_id=control.control_id,
                    previous_state="active",
                    new_state="ineffective",
                    reason="marked ineffective",
                    effective_at=effective_at,
                )
            )
        elif control.status == "expired":
            # Already-expired entities are NOT re-emitted
            continue
        elif control.expires_at is not None and _is_expired(control.expires_at, now):
            date_str = control.expires_at.strftime("%Y-%m-%d")
            changes.append(
                StateChange(
                    entity_type="control",
                    entity_id=control.control_id,
                    previous_state=control.status,
                    new_state="expired",
                    reason=f"control {control.control_id} expired on {date_str}",
                    effective_at=control.expires_at,
                )
            )

    # Evaluate evidence
    for ev in model.evidence:
        if ev.status == "stale":
            # Already-stale entities are NOT re-emitted
            continue
        if ev.valid_until is not None and _is_expired(ev.valid_until, now):
            date_str = ev.valid_until.strftime("%Y-%m-%d")
            changes.append(
                StateChange(
                    entity_type="evidence",
                    entity_id=ev.evidence_id,
                    previous_state=ev.status,
                    new_state="stale",
                    reason=f"evidence {ev.evidence_id} is stale since {date_str}",
                    effective_at=ev.valid_until,
                )
            )

    # Deterministic order: entity_type, then entity_id
    changes.sort(key=lambda c: (c.entity_type, c.entity_id))
    return changes


def propagate(
    model: AssuranceModel,
    changes: list[StateChange],
) -> list[Invalidation]:
    """Propagate control/evidence state changes to dependent assurance claims.

    - Claim is dependent if any supporting_control_id is a changed control,
      OR any supporting_evidence_id is changed evidence,
      OR any supporting evidence belongs to a changed control (evidence -> control -> claim).
    - Claims already "invalidated" are NOT re-emitted.
    - Pure function: does not modify the model.
    - Deterministic order: sorted by claim_id.

    Args:
        model: AssuranceModel topology.
        changes: Computed state changes from evaluate_states.

    Returns:
        List of Invalidation events sorted by claim_id.
    """
    if not changes:
        return []

    control_map = {c.control_id: c for c in model.controls}
    evidence_map = {e.evidence_id: e for e in model.evidence}

    invalidations: list[Invalidation] = []

    for claim in model.claims:
        if claim.status == "invalidated":
            # Already-invalidated claims are NOT re-emitted
            continue

        claim_ctrl_ids = set(claim.supporting_control_ids)
        claim_ev_ids = set(claim.supporting_evidence_ids)

        # Transitive evidence: direct evidence + evidence from supporting controls
        assoc_ev_ids = set(claim_ev_ids)
        for cid in claim_ctrl_ids:
            ctrl = control_map.get(cid)
            if ctrl:
                assoc_ev_ids.update(ctrl.evidence_ids)
        for ev in model.evidence:
            if ev.control_id in claim_ctrl_ids:
                assoc_ev_ids.add(ev.evidence_id)

        # Transitive controls: direct controls + controls that claim evidence belongs to
        assoc_ctrl_ids = set(claim_ctrl_ids)
        for eid in claim_ev_ids:
            ev = evidence_map.get(eid)
            if ev:
                assoc_ctrl_ids.add(ev.control_id)

        # Check which changes affect this claim
        matching_changes: list[StateChange] = []
        for ch in changes:
            if ch.entity_type == "control" and ch.entity_id in assoc_ctrl_ids:
                matching_changes.append(ch)
            elif ch.entity_type == "evidence" and ch.entity_id in assoc_ev_ids:
                matching_changes.append(ch)

        if not matching_changes:
            continue

        trigger = matching_changes[0]

        if trigger.entity_type == "control":
            if trigger.reason == "marked ineffective":
                reason = (
                    f"Assurance for claim {claim.claim_id} is no longer supported: "
                    f"control {trigger.entity_id} marked ineffective. "
                    "Human reassessment required."
                )
            else:
                date_str = trigger.effective_at.strftime("%Y-%m-%d")
                reason = (
                    f"Assurance for claim {claim.claim_id} is no longer supported: "
                    f"control {trigger.entity_id} expired on {date_str}. "
                    "Human reassessment required."
                )
        else:
            date_str = trigger.effective_at.strftime("%Y-%m-%d")
            reason = (
                f"Assurance for claim {claim.claim_id} is no longer supported: "
                f"evidence {trigger.entity_id} is stale since {date_str}. "
                "Human reassessment required."
            )

        invalidations.append(
            Invalidation(
                claim_id=claim.claim_id,
                triggering_entity_type=trigger.entity_type,
                triggering_entity_id=trigger.entity_id,
                reason=reason,
                dependent_controls=sorted(assoc_ctrl_ids),
                dependent_evidence=sorted(assoc_ev_ids),
                previous_status=claim.status,
            )
        )

    invalidations.sort(key=lambda inv: inv.claim_id)
    return invalidations


def apply_invalidations(
    model: AssuranceModel,
    invalidations: list[Invalidation],
    now: datetime,
    actor: str = "system",
) -> tuple[AssuranceModel, list[ReviewRecord]]:
    """Apply invalidations to a copy of the model and generate review records.

    - Returns a NEW model (deep copy) with affected claims set to "invalidated".
    - Returns exactly one ReviewRecord per claim with action="invalidate",
      previous_status preserved, reason from Invalidation, dependency_snapshot populated,
      timestamp=now.
    - Deterministic order preserving invalidations order.
    - NEVER sets any claim to "assured".

    Args:
        model: Original AssuranceModel (not modified).
        invalidations: Computed invalidations from propagate.
        now: Explicit timestamp for review records.
        actor: Identifier of actor recording invalidation (default "system").

    Returns:
        Tuple of (new_model, list_of_review_records).
    """
    new_model = model.model_copy(deep=True)
    inv_map = {inv.claim_id: inv for inv in invalidations}

    for claim in new_model.claims:
        if claim.claim_id in inv_map:
            claim.status = "invalidated"

    records: list[ReviewRecord] = []
    for inv in invalidations:
        records.append(
            ReviewRecord(
                record_id=f"REV-{inv.claim_id}",
                timestamp=now,
                actor=actor,
                action="invalidate",
                claim_id=inv.claim_id,
                reason=inv.reason,
                previous_status=inv.previous_status,
                new_status="invalidated",
                dependency_snapshot={
                    "triggering_entity_type": inv.triggering_entity_type,
                    "triggering_entity_id": inv.triggering_entity_id,
                    "dependent_controls": inv.dependent_controls,
                    "dependent_evidence": inv.dependent_evidence,
                },
            )
        )

    return new_model, records


def evaluate_assurance(
    model: AssuranceModel,
    now: datetime,
) -> dict[str, Any]:
    """Execute full assurance evaluation pipeline returning model, changes, and audit records.

    Args:
        model: Loaded AssuranceModel.
        now: Evaluation timestamp.

    Returns:
        Dict containing changes, invalidations, new_model, and review records.
    """
    changes = evaluate_states(model, now)
    invalidations = propagate(model, changes)
    new_model, records = apply_invalidations(model, invalidations, now)
    return {
        "changes": changes,
        "invalidations": invalidations,
        "model": new_model,
        "records": records,
    }
