"""Unit tests for aee.engine."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from aee.engine import (
    apply_invalidations,
    evaluate_assurance,
    evaluate_states,
    propagate,
)
from aee.models import (
    Asset,
    AssuranceClaim,
    AssuranceModel,
    CompensatingControl,
    Evidence,
    Zone,
)

FIXED_NOW = datetime(2026, 10, 19, 12, 0, 0, tzinfo=timezone.utc)
FORBIDDEN_WORDS = ["noncompliant", "unsafe", "violation", "failed compliance"]


def make_test_model(
    *,
    control_status: str = "active",
    control_expires_at: datetime | None = None,
    evidence_status: str = "current",
    evidence_valid_until: datetime | None = None,
    claim_status: str = "assured",
    claim_supporting_controls: list[str] | None = None,
    claim_supporting_evidence: list[str] | None = None,
) -> AssuranceModel:
    """Helper creating a valid baseline AssuranceModel with customizable parameters."""
    zone = Zone(zone_id="Z1", name="Cell Zone", purdue_level=2)
    asset = Asset(
        asset_id="PLC-01",
        name="Safety PLC",
        zone_id="Z1",
        criticality="safety",
        patch_status="unpatchable",
    )
    control = CompensatingControl(
        control_id="CTRL-01",
        name="Firewall Rule",
        asset_id="PLC-01",
        control_type="firewall",
        description="Port filtering",
        owner="SecOps",
        implemented_at=datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
        expires_at=control_expires_at,
        status=control_status,  # type: ignore[arg-type]
        evidence_ids=["EV-01"],
    )
    evidence = Evidence(
        evidence_id="EV-01",
        control_id="CTRL-01",
        evidence_type="firewall_export",
        collected_at=datetime(2026, 1, 2, 0, 0, tzinfo=timezone.utc),
        valid_until=evidence_valid_until,
        status=evidence_status,  # type: ignore[arg-type]
        source="fw-exporter",
        sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )
    claim = AssuranceClaim(
        claim_id="CLM-01",
        asset_id="PLC-01",
        zone_id="Z1",
        framework="IEC_62443",
        requirement_ref="SR 1.1",
        statement="Network isolation enforced.",
        status=claim_status,  # type: ignore[arg-type]
        supporting_control_ids=(
            claim_supporting_controls if claim_supporting_controls is not None else ["CTRL-01"]
        ),
        supporting_evidence_ids=(
            claim_supporting_evidence if claim_supporting_evidence is not None else ["EV-01"]
        ),
    )
    return AssuranceModel(
        facility="Facility-1",
        standard="IEC 62443",
        zones=[zone],
        assets=[asset],
        controls=[control],
        evidence=[evidence],
        claims=[claim],
    )


def test_control_expires_at_now_invalidates_claim_matching_template_reason() -> None:
    """Proves control with expires_at == now invalidates claim with the exact reason template."""
    model = make_test_model(
        control_expires_at=FIXED_NOW,
        evidence_valid_until=FIXED_NOW + timedelta(days=30),
    )
    changes = evaluate_states(model, FIXED_NOW)
    assert len(changes) == 1
    assert changes[0].entity_type == "control"
    assert changes[0].entity_id == "CTRL-01"
    assert changes[0].new_state == "expired"

    invalidations = propagate(model, changes)
    assert len(invalidations) == 1
    inv = invalidations[0]
    assert inv.claim_id == "CLM-01"
    assert inv.triggering_entity_type == "control"
    assert inv.triggering_entity_id == "CTRL-01"

    expected_reason = (
        "Assurance for claim CLM-01 is no longer supported: "
        "control CTRL-01 expired on 2026-10-19. "
        "Human reassessment required."
    )
    assert inv.reason == expected_reason

    new_model, records = apply_invalidations(model, invalidations, FIXED_NOW)
    assert new_model.claims[0].status == "invalidated"
    assert len(records) == 1
    assert records[0].reason == expected_reason


def test_control_expires_at_now_plus_one_second_boundary_no_invalidation() -> None:
    """Proves boundary condition: control expires at now + 1s produces no invalidation."""
    model = make_test_model(
        control_expires_at=FIXED_NOW + timedelta(seconds=1),
        evidence_valid_until=FIXED_NOW + timedelta(days=30),
    )
    changes = evaluate_states(model, FIXED_NOW)
    assert len(changes) == 0

    invalidations = propagate(model, changes)
    assert len(invalidations) == 0


def test_evidence_goes_stale_transitive_invalidation_of_dependent_claims() -> None:
    """Proves that stale evidence transitively invalidates claims depending on its control."""
    # Claim only lists supporting_control_ids=["CTRL-01"], NOT supporting_evidence_ids directly
    model = make_test_model(
        control_expires_at=FIXED_NOW + timedelta(days=30),
        evidence_valid_until=FIXED_NOW,
        claim_supporting_controls=["CTRL-01"],
        claim_supporting_evidence=[],
    )
    changes = evaluate_states(model, FIXED_NOW)
    assert len(changes) == 1
    assert changes[0].entity_type == "evidence"
    assert changes[0].entity_id == "EV-01"
    assert changes[0].new_state == "stale"

    invalidations = propagate(model, changes)
    assert len(invalidations) == 1
    inv = invalidations[0]
    assert inv.claim_id == "CLM-01"
    assert inv.triggering_entity_type == "evidence"
    assert inv.triggering_entity_id == "EV-01"

    expected_reason = (
        "Assurance for claim CLM-01 is no longer supported: "
        "evidence EV-01 is stale since 2026-10-19. "
        "Human reassessment required."
    )
    assert inv.reason == expected_reason

    new_model, records = apply_invalidations(model, invalidations, FIXED_NOW)
    assert new_model.claims[0].status == "invalidated"
    assert len(records) == 1
    assert records[0].reason == expected_reason


def test_shared_control_supports_three_claims_all_invalidated_in_one_call() -> None:
    """Proves that a single shared expired control invalidates all three dependent claims."""
    zone = Zone(zone_id="Z1", name="Cell Zone", purdue_level=2)
    asset = Asset(
        asset_id="PLC-01",
        name="Safety PLC",
        zone_id="Z1",
        criticality="safety",
        patch_status="unpatchable",
    )
    control = CompensatingControl(
        control_id="CTRL-SHARED",
        name="Shared Firewall",
        asset_id="PLC-01",
        control_type="firewall",
        description="Core segmentation",
        owner="SecOps",
        implemented_at=datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
        expires_at=FIXED_NOW,
        status="active",
        evidence_ids=[],
    )
    claims = [
        AssuranceClaim(
            claim_id=f"CLM-0{i}",
            asset_id="PLC-01",
            zone_id="Z1",
            framework="IEC_62443",
            requirement_ref=f"SR 1.{i}",
            statement=f"Claim {i} assurance statement.",
            status="assured",
            supporting_control_ids=["CTRL-SHARED"],
            supporting_evidence_ids=[],
        )
        for i in range(1, 4)
    ]
    model = AssuranceModel(
        facility="Facility-Shared",
        standard="IEC 62443",
        zones=[zone],
        assets=[asset],
        controls=[control],
        evidence=[],
        claims=claims,
    )

    changes = evaluate_states(model, FIXED_NOW)
    assert len(changes) == 1

    invalidations = propagate(model, changes)
    assert len(invalidations) == 3
    assert [inv.claim_id for inv in invalidations] == ["CLM-01", "CLM-02", "CLM-03"]

    new_model, records = apply_invalidations(model, invalidations, FIXED_NOW)
    assert len(records) == 3
    for clm in new_model.claims:
        assert clm.status == "invalidated"


def test_already_invalidated_claim_is_not_re_emitted() -> None:
    """Proves that a claim already having status 'invalidated' is not re-emitted."""
    model = make_test_model(
        control_expires_at=FIXED_NOW,
        claim_status="invalidated",
    )
    changes = evaluate_states(model, FIXED_NOW)
    assert len(changes) == 1

    invalidations = propagate(model, changes)
    assert len(invalidations) == 0


def test_unrelated_claims_untouched() -> None:
    """Proves that claims depending on unexpired, active controls remain untouched."""
    zone = Zone(zone_id="Z1", name="Cell Zone", purdue_level=2)
    asset = Asset(
        asset_id="PLC-01",
        name="Safety PLC",
        zone_id="Z1",
        criticality="safety",
        patch_status="unpatchable",
    )
    ctrl_expired = CompensatingControl(
        control_id="CTRL-EXP",
        name="Expiring Control",
        asset_id="PLC-01",
        control_type="firewall",
        description="Desc",
        owner="SecOps",
        implemented_at=datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
        expires_at=FIXED_NOW,
        status="active",
    )
    ctrl_active = CompensatingControl(
        control_id="CTRL-ACT",
        name="Active Control",
        asset_id="PLC-01",
        control_type="diode",
        description="Desc",
        owner="SecOps",
        implemented_at=datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
        expires_at=FIXED_NOW + timedelta(days=365),
        status="active",
    )
    claim_affected = AssuranceClaim(
        claim_id="CLM-AFFECTED",
        asset_id="PLC-01",
        zone_id="Z1",
        framework="IEC_62443",
        requirement_ref="SR 1.1",
        statement="Affected statement.",
        status="assured",
        supporting_control_ids=["CTRL-EXP"],
    )
    claim_untouched = AssuranceClaim(
        claim_id="CLM-UNTOUCHED",
        asset_id="PLC-01",
        zone_id="Z1",
        framework="IEC_62443",
        requirement_ref="SR 1.2",
        statement="Untouched statement.",
        status="assured",
        supporting_control_ids=["CTRL-ACT"],
    )
    model = AssuranceModel(
        facility="Facility-1",
        standard="IEC 62443",
        zones=[zone],
        assets=[asset],
        controls=[ctrl_expired, ctrl_active],
        evidence=[],
        claims=[claim_affected, claim_untouched],
    )

    changes = evaluate_states(model, FIXED_NOW)
    assert len(changes) == 1

    invalidations = propagate(model, changes)
    assert len(invalidations) == 1
    assert invalidations[0].claim_id == "CLM-AFFECTED"

    new_model, records = apply_invalidations(model, invalidations, FIXED_NOW)
    clm_affected_new = next(c for c in new_model.claims if c.claim_id == "CLM-AFFECTED")
    clm_untouched_new = next(c for c in new_model.claims if c.claim_id == "CLM-UNTOUCHED")

    assert clm_affected_new.status == "invalidated"
    assert clm_untouched_new.status == "assured"
    assert len(records) == 1


def test_evidence_renewed_before_expiry_no_invalidation() -> None:
    """Proves that evidence with future valid_until produces no state changes or invalidations."""
    model = make_test_model(
        evidence_valid_until=FIXED_NOW + timedelta(days=90),
        control_expires_at=FIXED_NOW + timedelta(days=180),
    )
    changes = evaluate_states(model, FIXED_NOW)
    assert len(changes) == 0

    invalidations = propagate(model, changes)
    assert len(invalidations) == 0


def test_explicit_ineffective_control_produces_invalidation() -> None:
    """Proves that a control explicitly marked 'ineffective' produces an invalidation."""
    model = make_test_model(
        control_status="ineffective",
        control_expires_at=FIXED_NOW + timedelta(days=30),
    )
    changes = evaluate_states(model, FIXED_NOW)
    assert len(changes) == 1
    assert changes[0].entity_type == "control"
    assert changes[0].entity_id == "CTRL-01"
    assert changes[0].reason == "marked ineffective"

    invalidations = propagate(model, changes)
    assert len(invalidations) == 1
    inv = invalidations[0]
    assert inv.claim_id == "CLM-01"
    assert inv.triggering_entity_id == "CTRL-01"
    assert "marked ineffective" in inv.reason

    new_model, records = apply_invalidations(model, invalidations, FIXED_NOW)
    assert new_model.claims[0].status == "invalidated"
    assert len(records) == 1


def test_apply_invalidations_returns_new_model_original_unchanged() -> None:
    """Proves that apply_invalidations returns a deep copy without mutating the original model."""
    model = make_test_model(
        control_expires_at=FIXED_NOW,
        claim_status="assured",
    )
    changes = evaluate_states(model, FIXED_NOW)
    invalidations = propagate(model, changes)
    new_model, records = apply_invalidations(model, invalidations, FIXED_NOW)

    # Original model remains untouched
    assert model.claims[0].status == "assured"
    assert new_model.claims[0].status == "invalidated"
    assert model is not new_model
    assert model.claims[0] is not new_model.claims[0]


def test_exactly_one_review_record_per_invalidated_claim_previous_status_preserved() -> None:
    """Proves exactly one ReviewRecord per claim and preserves previous claim status."""
    zone = Zone(zone_id="Z1", name="Cell Zone", purdue_level=2)
    asset = Asset(
        asset_id="PLC-01",
        name="Safety PLC",
        zone_id="Z1",
        criticality="safety",
        patch_status="unpatchable",
    )
    ctrl = CompensatingControl(
        control_id="CTRL-1",
        name="Firewall",
        asset_id="PLC-01",
        control_type="firewall",
        description="Filter",
        owner="SecOps",
        implemented_at=datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
        expires_at=FIXED_NOW,
        status="active",
    )
    claim1 = AssuranceClaim(
        claim_id="CLM-01",
        asset_id="PLC-01",
        zone_id="Z1",
        framework="IEC_62443",
        requirement_ref="SR 1.1",
        statement="Statement 1",
        status="assured",
        supporting_control_ids=["CTRL-1"],
    )
    claim2 = AssuranceClaim(
        claim_id="CLM-02",
        asset_id="PLC-01",
        zone_id="Z1",
        framework="IEC_62443",
        requirement_ref="SR 1.2",
        statement="Statement 2",
        status="under_review",
        supporting_control_ids=["CTRL-1"],
    )
    model = AssuranceModel(
        facility="Facility-1",
        standard="IEC 62443",
        zones=[zone],
        assets=[asset],
        controls=[ctrl],
        evidence=[],
        claims=[claim1, claim2],
    )

    changes = evaluate_states(model, FIXED_NOW)
    invalidations = propagate(model, changes)
    new_model, records = apply_invalidations(model, invalidations, FIXED_NOW, actor="auditor-lead")

    assert len(records) == 2
    r1 = next(r for r in records if r.claim_id == "CLM-01")
    r2 = next(r for r in records if r.claim_id == "CLM-02")

    assert r1.action == "invalidate"
    assert r1.previous_status == "assured"
    assert r1.new_status == "invalidated"
    assert r1.actor == "auditor-lead"
    assert r1.timestamp == FIXED_NOW
    assert "dependent_controls" in r1.dependency_snapshot

    assert r2.action == "invalidate"
    assert r2.previous_status == "under_review"
    assert r2.new_status == "invalidated"
    assert r2.actor == "auditor-lead"


def test_determinism_identical_inputs_identical_byte_serialized_json() -> None:
    """Proves identical inputs yield byte-for-byte identical serialized JSON output."""
    model = make_test_model(
        control_expires_at=FIXED_NOW,
        evidence_valid_until=FIXED_NOW,
    )

    # First run
    changes1 = evaluate_states(model, FIXED_NOW)
    invs1 = propagate(model, changes1)
    new_model1, records1 = apply_invalidations(model, invs1, FIXED_NOW)

    # Second run
    changes2 = evaluate_states(model, FIXED_NOW)
    invs2 = propagate(model, changes2)
    new_model2, records2 = apply_invalidations(model, invs2, FIXED_NOW)

    # Compare model JSON bytes
    bytes1_model = new_model1.model_dump_json().encode("utf-8")
    bytes2_model = new_model2.model_dump_json().encode("utf-8")
    assert bytes1_model == bytes2_model

    # Compare review records JSON bytes
    records1_dicts = [r.model_dump(mode="json") for r in records1]
    records2_dicts = [r.model_dump(mode="json") for r in records2]
    bytes1_records = json.dumps(records1_dicts, sort_keys=True).encode("utf-8")
    bytes2_records = json.dumps(records2_dicts, sort_keys=True).encode("utf-8")
    assert bytes1_records == bytes2_records


def test_critical_invariants_no_assured_claim_and_no_forbidden_words() -> None:
    """Proves engine never emits 'assured' and reasons contain no forbidden words."""
    test_models = [
        make_test_model(control_expires_at=FIXED_NOW),
        make_test_model(evidence_valid_until=FIXED_NOW),
        make_test_model(control_status="ineffective"),
    ]

    all_reasons: list[str] = []

    for model in test_models:
        changes = evaluate_states(model, FIXED_NOW)
        for c in changes:
            all_reasons.append(c.reason)

        invalidations = propagate(model, changes)
        for inv in invalidations:
            all_reasons.append(inv.reason)

        new_model, records = apply_invalidations(model, invalidations, FIXED_NOW)
        for rec in records:
            all_reasons.append(rec.reason)
            # The engine NEVER sets a claim to "assured"
            assert rec.new_status != "assured"
            assert rec.action != "assured"  # type: ignore[comparison-overlap]

        for claim in new_model.claims:
            # If claim was affected, it must not be assured
            if any(inv.claim_id == claim.claim_id for inv in invalidations):
                assert claim.status == "invalidated"

    assert len(all_reasons) > 0

    # Invariant: no reason string contains forbidden words
    for reason in all_reasons:
        lower_reason = reason.lower()
        for forbidden in FORBIDDEN_WORDS:
            assert forbidden not in lower_reason, (
                f"Forbidden word '{forbidden}' found in reason: '{reason}'"
            )


def test_already_expired_and_already_stale_not_re_emitted() -> None:
    """Proves already-expired controls and already-stale evidence are NOT re-emitted."""
    model = make_test_model(
        control_status="expired",
        control_expires_at=FIXED_NOW - timedelta(days=10),
        evidence_status="stale",
        evidence_valid_until=FIXED_NOW - timedelta(days=10),
    )
    changes = evaluate_states(model, FIXED_NOW)
    assert len(changes) == 0


def test_evaluate_assurance_orchestrator_helper() -> None:
    """Proves evaluate_assurance coordinates full pipeline and returns unified dict."""
    model = make_test_model(control_expires_at=FIXED_NOW)
    result = evaluate_assurance(model, FIXED_NOW)

    assert "changes" in result
    assert "invalidations" in result
    assert "model" in result
    assert "records" in result
    assert len(result["changes"]) == 1  # type: ignore[arg-type]
    assert len(result["invalidations"]) == 1  # type: ignore[arg-type]
    assert len(result["records"]) == 1  # type: ignore[arg-type]


def test_timezone_naive_and_aware_comparisons_and_none_expiry() -> None:
    """Proves that _is_expired handles naive vs aware timestamps and None expiry cleanly."""
    from aee.engine import _is_expired

    assert not _is_expired(None, FIXED_NOW)

    aware_dt = datetime(2026, 10, 19, 10, 0, tzinfo=timezone.utc)
    naive_dt = datetime(2026, 10, 19, 10, 0)
    aware_now = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
    naive_now = datetime(2026, 10, 19, 12, 0)

    # aware dt with naive now
    assert _is_expired(aware_dt, naive_now)
    # naive dt with aware now
    assert _is_expired(naive_dt, aware_now)

