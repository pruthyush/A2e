"""Unit tests for AEE domain models and validation."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from aee.cli import app
from aee.clock import resolve_now
from aee.models import (
    Asset,
    AssuranceClaim,
    AssuranceModel,
    CompensatingControl,
    Conduit,
    Evidence,
    ReviewRecord,
    Zone,
)

runner = CliRunner()


def test_dangling_supporting_control_id_raises_validation_error() -> None:
    """Proves that a dangling supporting_control_id raises ValidationError naming the missing ID."""
    missing_ctrl_id = "CTRL-NONEXISTENT-404"
    zone = Zone(zone_id="ZONE-01", name="Cell Zone", purdue_level=2)
    asset = Asset(
        asset_id="PLC-01",
        name="Safety PLC",
        zone_id="ZONE-01",
        criticality="safety",
        patch_status="unpatchable",
    )
    claim = AssuranceClaim(
        claim_id="CLAIM-01",
        asset_id="PLC-01",
        zone_id="ZONE-01",
        framework="IEC_62443",
        requirement_ref="SR 1.1",
        statement="PLC communications restricted to designated conduit.",
        status="assured",
        supporting_control_ids=[missing_ctrl_id],
    )

    with pytest.raises(ValidationError) as exc_info:
        AssuranceModel(
            facility="Facility-Alpha",
            standard="IEC 62443",
            zones=[zone],
            assets=[asset],
            controls=[],
            evidence=[],
            claims=[claim],
        )

    assert missing_ctrl_id in str(exc_info.value)
    assert "supporting_control_id" in str(exc_info.value)


def test_dangling_supporting_evidence_id_raises_validation_error() -> None:
    """Proves that dangling supporting_evidence_id raises ValidationError naming missing ID."""
    missing_evidence_id = "EV-NONEXISTENT-999"
    zone = Zone(zone_id="ZONE-01", name="Cell Zone", purdue_level=2)
    asset = Asset(
        asset_id="PLC-01",
        name="Safety PLC",
        zone_id="ZONE-01",
        criticality="safety",
        patch_status="unpatchable",
    )
    claim = AssuranceClaim(
        claim_id="CLAIM-01",
        asset_id="PLC-01",
        zone_id="ZONE-01",
        framework="IEC_62443",
        requirement_ref="SR 1.1",
        statement="PLC communications restricted to designated conduit.",
        status="assured",
        supporting_evidence_ids=[missing_evidence_id],
    )

    with pytest.raises(ValidationError) as exc_info:
        AssuranceModel(
            facility="Facility-Alpha",
            standard="IEC 62443",
            zones=[zone],
            assets=[asset],
            controls=[],
            evidence=[],
            claims=[claim],
        )

    assert missing_evidence_id in str(exc_info.value)


def test_valid_assurance_model_resolves_all_foreign_keys() -> None:
    """Proves that a fully connected topology validates without error."""
    zone1 = Zone(zone_id="Z1", name="Supervisory", purdue_level=2)
    zone2 = Zone(zone_id="Z2", name="Safety", purdue_level=1)
    conduit = Conduit(
        conduit_id="C1",
        source_zone="Z1",
        destination_zone="Z2",
        allowed_protocols=["MODBUS-TCP"],
    )
    asset = Asset(
        asset_id="A1",
        name="Turbine Controller",
        zone_id="Z2",
        criticality="safety",
        patch_status="unpatchable",
    )
    control = CompensatingControl(
        control_id="CTRL-1",
        name="Network Firewall ACL",
        asset_id="A1",
        control_type="firewall",
        description="Strict inbound IP filtering",
        owner="SecOps",
        implemented_at=datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
        expires_at=datetime(2026, 12, 31, 23, 59, tzinfo=timezone.utc),
        status="active",
        evidence_ids=["EV-1"],
    )
    evidence = Evidence(
        evidence_id="EV-1",
        control_id="CTRL-1",
        evidence_type="firewall_config_export",
        collected_at=datetime(2026, 1, 2, 0, 0, tzinfo=timezone.utc),
        valid_until=datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc),
        status="current",
        source="fw-exporter",
        sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )
    claim = AssuranceClaim(
        claim_id="CLM-1",
        asset_id="A1",
        zone_id="Z2",
        conduit_id="C1",
        framework="IEC_62443",
        requirement_ref="SR 3.1",
        statement="Network segmentation prevents unauthorized access.",
        status="assured",
        supporting_control_ids=["CTRL-1"],
        supporting_evidence_ids=["EV-1"],
    )

    model = AssuranceModel(
        facility="Offshore Platform",
        standard="IEC 62443",
        zones=[zone1, zone2],
        conduits=[conduit],
        assets=[asset],
        controls=[control],
        evidence=[evidence],
        claims=[claim],
    )
    assert model.facility == "Offshore Platform"
    assert len(model.claims) == 1


def test_extra_field_forbidden() -> None:
    """Proves that unexpected extra fields are forbidden by model configuration."""
    with pytest.raises(ValidationError):
        Zone(
            zone_id="Z1",
            name="Zone 1",
            purdue_level=1,
            unrecognized_field="illegal",  # type: ignore[call-arg]
        )


def test_review_record_validation() -> None:
    """Proves that ReviewRecord validates required fields and preserves decisions."""
    record = ReviewRecord(
        record_id="REC-001",
        timestamp=datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc),
        actor="Alice Lead Assessor",
        action="invalidate",
        claim_id="CLM-1",
        reason="Compensating control evidence expired on 2026-06-01",
        previous_status="assured",
        new_status="invalidated",
        dependency_snapshot={"expired_evidence": ["EV-1"]},
        notes="Reassessment requested before next turnaround",
    )
    assert record.action == "invalidate"
    assert record.claim_id == "CLM-1"


def test_clock_resolve_now() -> None:
    """Proves that clock.resolve_now resolves ISO-8601 strings and defaults to current time."""
    parsed = resolve_now("2026-10-19T10:00:00Z")
    assert parsed.year == 2026
    assert parsed.month == 10
    assert parsed.day == 19
    assert parsed.tzinfo is not None

    current = resolve_now(None)
    assert current.tzinfo is not None


def test_cli_help_and_subcommands() -> None:
    """Proves that CLI --help and all subcommand help exits 0."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "check" in result.stdout
    assert "review" in result.stdout
    assert "report" in result.stdout

    for sub in ["check", "review", "report"]:
        sub_result = runner.invoke(app, [sub, "--help"])
        assert sub_result.exit_code == 0


def test_cli_subcommands_exit_zero_with_stub_message() -> None:
    """Proves that invoking stubbed CLI subcommands outputs stub message and exits 0."""
    result = runner.invoke(
        app,
        ["check", "--model", "model.yaml", "--now", "2026-10-19T10:00:00Z"],
    )
    assert result.exit_code == 0
    assert "Not implemented yet." in result.stdout
