"""Unit and integration tests for aee.cli."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from typer.testing import CliRunner

from aee.cli import app
from aee.history import load as load_history
from aee.loader import load_model

runner = CliRunner()
FIXED_NOW = "2026-10-19T12:00:00Z"


def test_cli_check_clean() -> None:
    """Test aee check with zero invalidations exits 0."""
    result = runner.invoke(
        app,
        ["check", "--model", "fixtures/scenarios/01-clean/model.yaml", "--now", FIXED_NOW],
    )
    assert result.exit_code == 0
    assert "Claims invalidated: 0" in result.stdout
    assert "Assured: 2" in result.stdout


def test_cli_check_invalidation_exit_code() -> None:
    """Test aee check with >=1 invalidation exits 1."""
    result = runner.invoke(
        app,
        [
            "check",
            "--model",
            "fixtures/scenarios/02-expired-control/model.yaml",
            "--now",
            FIXED_NOW,
        ],
    )
    assert result.exit_code == 1
    assert "Claims invalidated: 1" in result.stdout


def test_cli_check_model_load_error(tmp_path: Path) -> None:
    """Test aee check with missing or malformed model exits 3 without traceback."""
    bad_model = tmp_path / "bad.yaml"
    bad_model.write_text("invalid: [yaml\n", encoding="utf-8")

    result = runner.invoke(
        app,
        ["check", "--model", str(bad_model), "--now", FIXED_NOW],
    )
    assert result.exit_code == 3
    assert "Model load error" in result.stderr
    assert "Traceback" not in result.stderr


def test_cli_check_output_findings_json(tmp_path: Path) -> None:
    """Test aee check --output generates valid findings JSON."""
    findings_file = tmp_path / "findings.json"
    result = runner.invoke(
        app,
        [
            "check",
            "--model",
            "fixtures/scenarios/02-expired-control/model.yaml",
            "--now",
            FIXED_NOW,
            "--output",
            str(findings_file),
        ],
    )
    assert result.exit_code == 1
    assert findings_file.exists()
    content = findings_file.read_text(encoding="utf-8")
    assert '"schema_version": "1.0"' in content
    assert '"claim_id": "CLM-01"' in content


def test_cli_review_unknown_claim(tmp_path: Path) -> None:
    """Test review on non-existent claim exits 5."""
    history_file = tmp_path / "history.jsonl"
    result = runner.invoke(
        app,
        [
            "review",
            "--model",
            "fixtures/demo/assurance.yaml",
            "--history",
            str(history_file),
            "--claim",
            "UNKNOWN-99",
            "--decision",
            "approve",
            "--actor",
            "tester",
            "--evidence",
            "fixtures/demo/evidence.pdf",
            "--now",
            FIXED_NOW,
        ],
    )
    assert result.exit_code == 5
    assert "Unknown claim 'UNKNOWN-99'" in result.stderr


def test_cli_review_approve_non_invalidated_claim(tmp_path: Path) -> None:
    """Test approve on claim not in 'invalidated' status exits 6."""
    history_file = tmp_path / "history.jsonl"
    result = runner.invoke(
        app,
        [
            "review",
            "--model",
            "fixtures/demo/assurance.yaml",
            "--history",
            str(history_file),
            "--claim",
            "AC-01",  # AC-01 is 'assured'
            "--decision",
            "approve",
            "--actor",
            "tester",
            "--evidence",
            "fixtures/demo/evidence.pdf",
            "--now",
            FIXED_NOW,
        ],
    )
    assert result.exit_code == 6
    assert "approve is only permitted for 'invalidated' claims" in result.stderr


def test_cli_review_approve_requires_evidence(tmp_path: Path) -> None:
    """Test approve without --evidence exits 2."""
    history_file = tmp_path / "history.jsonl"
    result = runner.invoke(
        app,
        [
            "review",
            "--model",
            "fixtures/demo/assurance.yaml",
            "--history",
            str(history_file),
            "--claim",
            "AC-07",
            "--decision",
            "approve",
            "--actor",
            "tester",
            "--now",
            FIXED_NOW,
        ],
    )
    assert result.exit_code == 2
    assert "--evidence is required" in result.stderr


def test_cli_review_approve_success(tmp_path: Path) -> None:
    """Test successful approve transitions status to 'assured' and appends to history."""
    model_copy = tmp_path / "model.yaml"
    shutil.copy("fixtures/demo/assurance.yaml", model_copy)
    history_file = tmp_path / "history.jsonl"

    result = runner.invoke(
        app,
        [
            "review",
            "--model",
            str(model_copy),
            "--history",
            str(history_file),
            "--claim",
            "AC-07",
            "--decision",
            "approve",
            "--actor",
            "assessor_bob",
            "--evidence",
            "fixtures/demo/evidence.pdf",
            "--notes",
            "Verified test report",
            "--now",
            "2026-11-02T00:00:00Z",
        ],
    )
    assert result.exit_code == 0

    # Verify model rewritten with status 'assured'
    updated_model = load_model(model_copy)
    target = next(c for c in updated_model.claims if c.claim_id == "AC-07")
    assert target.status == "assured"
    assert target.reviewer == "assessor_bob"

    # Verify history appended
    records = load_history(history_file)
    assert len(records) == 1
    assert records[0].action == "approve"
    assert records[0].claim_id == "AC-07"
    assert records[0].new_status == "assured"
    assert "evidence_sha256=" in (records[0].notes or "")


def test_cli_review_reject_success(tmp_path: Path) -> None:
    """Test reject transitions status to 'under_review' and appends to history."""
    model_copy = tmp_path / "model.yaml"
    shutil.copy("fixtures/demo/assurance.yaml", model_copy)
    history_file = tmp_path / "history.jsonl"

    result = runner.invoke(
        app,
        [
            "review",
            "--model",
            str(model_copy),
            "--history",
            str(history_file),
            "--claim",
            "AC-07",
            "--decision",
            "reject",
            "--actor",
            "assessor_bob",
            "--notes",
            "Insufficient patch rationale",
            "--now",
            "2026-11-02T00:00:00Z",
        ],
    )
    assert result.exit_code == 0

    # Verify model rewritten with status 'under_review'
    updated_model = load_model(model_copy)
    target = next(c for c in updated_model.claims if c.claim_id == "AC-07")
    assert target.status == "under_review"

    records = load_history(history_file)
    assert len(records) == 1
    assert records[0].action == "reject"
    assert records[0].new_status == "under_review"


def test_cli_report_success(tmp_path: Path) -> None:
    """Test aee report command generates valid markdown and exits 0."""
    history_file = tmp_path / "history.jsonl"
    report_file = tmp_path / "report.md"

    result = runner.invoke(
        app,
        [
            "report",
            "--model",
            "fixtures/demo/assurance.yaml",
            "--history",
            str(history_file),
            "--now",
            "2026-11-02T00:00:00Z",
            "--output",
            str(report_file),
        ],
    )
    assert result.exit_code == 0
    assert report_file.exists()
    content = report_file.read_text(encoding="utf-8")
    assert "## Summary" in content
    assert "## Limitations" in content


def test_honesty_check_only_review_approve_writes_assured() -> None:
    """Grep source tree to ensure only review command in cli.py assigns 'assured'."""
    src_dir = Path("src/aee")
    assignment_pattern = re.compile(r'(\w+(?:\.\w+)*)\s*=\s*["\']assured["\']')

    matches: list[tuple[str, int, str]] = []
    for py_file in src_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        for line_num, line in enumerate(content.splitlines(), start=1):
            # Exclude comments
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if assignment_pattern.search(line):
                matches.append((str(py_file.name), line_num, line))

    for filename, line_num, line in matches:
        assert filename == "cli.py", (
            f"Unauthorized assignment to 'assured' in {filename}:{line_num}: {line}"
        )
