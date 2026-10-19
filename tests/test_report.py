"""Unit tests for aee.report."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from aee.engine import Invalidation
from aee.loader import load_model
from aee.models import ReviewRecord
from aee.report import (
    LIMITATIONS_STATEMENT,
    write_audit_report,
    write_findings_json,
)

FIXED_NOW = datetime(2026, 11, 2, 0, 0, 0, tzinfo=timezone.utc)
FORBIDDEN = ["noncompliant", "unsafe", "violation"]


def test_write_audit_report_sections_and_limitations(tmp_path: Path) -> None:
    """Test report generation structure, section ordering, and limitations constant."""
    model_path = Path("fixtures/demo/assurance.yaml")
    model = load_model(model_path)
    output_path = tmp_path / "test_report.md"

    inv = Invalidation(
        claim_id="AC-07",
        triggering_entity_type="evidence",
        triggering_entity_id="EVD-12",
        reason=(
            "Assurance for claim AC-07 is no longer supported: "
            "evidence EVD-12 is stale since 2026-10-01. "
            "Human reassessment required."
        ),
        dependent_controls=["CC-04"],
        dependent_evidence=["EVD-12"],
        previous_status="assured",
    )
    rec = ReviewRecord(
        record_id="REV-01",
        timestamp=FIXED_NOW,
        actor="you",
        action="approve",
        claim_id="AC-07",
        reason="Assessor approval",
        previous_status="invalidated",
        new_status="assured",
        notes="evidence_sha256=123456",
    )

    cmd = (
        "aee report --model fixtures/demo/assurance.yaml "
        "--history /tmp/h.jsonl --now 2026-11-02T00:00:00Z "
        "--output /tmp/report.md"
    )
    write_audit_report(
        model=model,
        history=[rec],
        invalidations=[inv],
        now=FIXED_NOW,
        command=cmd,
        input_hashes={"model": "hash1", "history": "hash2"},
        output_path=output_path,
    )

    content = output_path.read_text(encoding="utf-8")

    # 1. Section order check
    idx_summary = content.find("## Summary")
    idx_inv = content.find("## Invalidated Claims Table")
    idx_dep = content.find("## Dependency Rationale")
    idx_hist = content.find("## Preserved Decision History")
    idx_limit = content.find("## Limitations")
    idx_repro = content.find("## Reproducibility")

    assert -1 < idx_summary < idx_inv < idx_dep < idx_hist < idx_limit < idx_repro

    # 2. Limitations verbatim check
    assert LIMITATIONS_STATEMENT in content

    # 3. Forbidden words scan
    lower_content = content.lower()
    for word in FORBIDDEN:
        assert word not in lower_content, f"Forbidden word '{word}' found in report!"

    # 4. Dependency rationale chain check
    assert "EVD-12 stale since 2026-10-01 → CC-04 → AC-07" in content

    # 5. Summary metrics
    assert "**Facility:** Refinery-Alpha" in content
    assert "**Standard:** IEC 62443" in content


def test_write_findings_json(tmp_path: Path) -> None:
    """Test findings JSON output matches required schema."""
    output_path = tmp_path / "findings.json"
    inv = Invalidation(
        claim_id="AC-07",
        triggering_entity_type="control",
        triggering_entity_id="CC-04",
        reason="Expired control",
        dependent_controls=["CC-04"],
        dependent_evidence=["EVD-03"],
        previous_status="assured",
    )

    write_findings_json([inv], output_path)

    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == "1.0"
    assert len(data["invalidations"]) == 1
    assert data["invalidations"][0]["claim_id"] == "AC-07"
    assert data["invalidations"][0]["triggering_entity_id"] == "CC-04"


def test_report_determinism_golden_scenario_01(tmp_path: Path) -> None:
    """Ensure fixed --now + identical inputs yields byte-identical report."""
    model_path = Path("fixtures/scenarios/01-clean/model.yaml")
    model = load_model(model_path)

    out1 = tmp_path / "report1.md"
    out2 = tmp_path / "report2.md"

    cmd = (
        "aee report --model model.yaml --history h.jsonl "
        "--now 2026-11-02T00:00:00Z --output report.md"
    )
    write_audit_report(
        model=model,
        history=[],
        invalidations=[],
        now=FIXED_NOW,
        command=cmd,
        input_hashes={"model": "fixed_hash", "history": "N/A"},
        output_path=out1,
    )

    write_audit_report(
        model=model,
        history=[],
        invalidations=[],
        now=FIXED_NOW,
        command=cmd,
        input_hashes={"model": "fixed_hash", "history": "N/A"},
        output_path=out2,
    )

    assert out1.read_bytes() == out2.read_bytes()
