"""Unit tests for aee.history."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from aee.history import HistoryIntegrityError, append, load, verify_integrity
from aee.models import ReviewRecord

NOW = datetime(2026, 10, 19, 12, 0, 0, tzinfo=timezone.utc)


def test_history_append_and_load(tmp_path: Path) -> None:
    """Test standard append and load operations."""
    history_file = tmp_path / "history.jsonl"

    rec1 = ReviewRecord(
        record_id="REV-01",
        timestamp=NOW,
        actor="Alice",
        action="approve",
        claim_id="CLM-01",
        reason="Assessor approval",
        previous_status="invalidated",
        new_status="assured",
        notes="evidence_sha256=abcdef",
    )
    rec2 = ReviewRecord(
        record_id="REV-02",
        timestamp=NOW + timedelta(hours=1),
        actor="Bob",
        action="reject",
        claim_id="CLM-02",
        reason="Insufficient documentation",
        previous_status="invalidated",
        new_status="under_review",
    )

    append(history_file, rec1)
    append(history_file, rec2)

    loaded = load(history_file)
    assert len(loaded) == 2
    assert loaded[0].record_id == "REV-01"
    assert loaded[0].actor == "Alice"
    assert loaded[1].record_id == "REV-02"
    assert loaded[1].action == "reject"
    assert verify_integrity(history_file) == []


def test_history_load_empty_or_nonexistent(tmp_path: Path) -> None:
    """Test loading non-existent file returns empty list."""
    non_existent = tmp_path / "missing.jsonl"
    assert load(non_existent) == []
    assert verify_integrity(non_existent) == []


def test_history_refuses_corrupted_jsonl(tmp_path: Path) -> None:
    """Test append and load refuse malformed JSON lines."""
    history_file = tmp_path / "corrupted.jsonl"
    history_file.write_text("{\"not\": \"a valid review record\"}\n", encoding="utf-8")

    errors = verify_integrity(history_file)
    assert len(errors) > 0

    with pytest.raises(HistoryIntegrityError):
        load(history_file)

    new_rec = ReviewRecord(
        record_id="REV-03",
        timestamp=NOW,
        actor="Carol",
        action="approve",
        claim_id="CLM-03",
        reason="Approval",
        previous_status="invalidated",
        new_status="assured",
    )
    with pytest.raises(HistoryIntegrityError, match="Cannot append to corrupted history"):
        append(history_file, new_rec)


def test_history_refuses_duplicate_record_id(tmp_path: Path) -> None:
    """Test append refuses duplicate record_id."""
    history_file = tmp_path / "dup.jsonl"

    rec1 = ReviewRecord(
        record_id="REV-SAME",
        timestamp=NOW,
        actor="Alice",
        action="approve",
        claim_id="CLM-01",
        reason="First",
        previous_status="invalidated",
        new_status="assured",
    )
    rec2 = ReviewRecord(
        record_id="REV-SAME",
        timestamp=NOW + timedelta(hours=1),
        actor="Bob",
        action="reject",
        claim_id="CLM-02",
        reason="Second",
        previous_status="invalidated",
        new_status="under_review",
    )

    append(history_file, rec1)
    with pytest.raises(HistoryIntegrityError, match="already exists"):
        append(history_file, rec2)


def test_history_verify_integrity_detects_decreasing_timestamps(tmp_path: Path) -> None:
    """Test verify_integrity detects chronological regressions."""
    history_file = tmp_path / "regressing.jsonl"

    rec1 = ReviewRecord(
        record_id="REV-01",
        timestamp=NOW + timedelta(hours=2),
        actor="Alice",
        action="approve",
        claim_id="CLM-01",
        reason="First",
        previous_status="invalidated",
        new_status="assured",
    )
    rec2 = ReviewRecord(
        record_id="REV-02",
        timestamp=NOW,  # 2 hours earlier!
        actor="Bob",
        action="reject",
        claim_id="CLM-02",
        reason="Second",
        previous_status="invalidated",
        new_status="under_review",
    )

    # Write directly to simulate invalid file
    history_file.write_text(
        rec1.model_dump_json() + "\n" + rec2.model_dump_json() + "\n",
        encoding="utf-8",
    )

    errors = verify_integrity(history_file)
    assert any("decreasing timestamp" in e for e in errors)
    with pytest.raises(HistoryIntegrityError):
        load(history_file)
