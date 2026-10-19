"""Append-only audit history log interface for Assurance Expiry Engine (AEE)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from aee.models import ReviewRecord


class HistoryIntegrityError(Exception):
    """Raised when an append-only audit log fails integrity validation."""


def verify_integrity(history_path: Path | str) -> list[str]:
    """Verify integrity of the append-only history log.

    Checks:
    - Valid JSONL (each non-empty line must parse as a valid ReviewRecord)
    - Unique record_ids across all lines
    - Non-decreasing timestamps

    Args:
        history_path: Path to the JSONL history file.

    Returns:
        List of error strings describing violations (empty list = OK).
    """
    path = Path(history_path)
    if not path.exists():
        return []

    try:
        content = path.read_text(encoding="utf-8")
    except OSError as e:
        return [f"Unable to read history file '{path}': {e}"]

    errors: list[str] = []
    seen_ids: set[str] = set()
    prev_timestamp: datetime | None = None

    lines = content.splitlines()
    for idx, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            errors.append(f"Line {idx}: empty line in JSONL file")
            continue

        try:
            record = ReviewRecord.model_validate_json(line)
        except Exception as e:
            errors.append(f"Line {idx}: invalid ReviewRecord JSON: {e}")
            continue

        if record.record_id in seen_ids:
            errors.append(f"Line {idx}: duplicate record_id '{record.record_id}'")
        seen_ids.add(record.record_id)

        if prev_timestamp is not None and record.timestamp < prev_timestamp:
            errors.append(
                f"Line {idx}: decreasing timestamp {record.timestamp.isoformat()} "
                f"< previous {prev_timestamp.isoformat()}"
            )
        prev_timestamp = record.timestamp

    return errors


def load(history_path: Path | str) -> list[ReviewRecord]:
    """Load historical review records from the append-only history log.

    Args:
        history_path: Path to the JSONL history file.

    Returns:
        List of historical ReviewRecord entries.

    Raises:
        HistoryIntegrityError: If file is corrupted, malformed, or has integrity errors.
    """
    path = Path(history_path)
    if not path.exists():
        return []

    errors = verify_integrity(path)
    if errors:
        raise HistoryIntegrityError("; ".join(errors))

    content = path.read_text(encoding="utf-8")
    records: list[ReviewRecord] = []
    for line in content.splitlines():
        trimmed = line.strip()
        if trimmed:
            records.append(ReviewRecord.model_validate_json(trimmed))

    return records


def append(history_path: Path | str, record: ReviewRecord) -> None:
    """Append a human review decision record to the audit history.

    Never rewrites or deletes existing records. Refuses if the file is not
    valid JSONL, if record_id already exists, or if timestamps would decrease.

    Args:
        history_path: Path to the JSONL history file.
        record: ReviewRecord documenting the human reassessment.

    Raises:
        HistoryIntegrityError: If the history file has integrity errors or appending
            would violate integrity constraints.
    """
    path = Path(history_path)

    if path.exists():
        errors = verify_integrity(path)
        if errors:
            raise HistoryIntegrityError(
                f"Cannot append to corrupted history: {'; '.join(errors)}"
            )

        existing_records = load(path)
        if any(r.record_id == record.record_id for r in existing_records):
            raise HistoryIntegrityError(
                f"Duplicate record_id '{record.record_id}' already exists in history"
            )

        if existing_records and record.timestamp < existing_records[-1].timestamp:
            raise HistoryIntegrityError(
                f"Record timestamp {record.timestamp.isoformat()} is earlier than "
                f"last record timestamp {existing_records[-1].timestamp.isoformat()}"
            )

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(record.model_dump_json() + "\n")


# Backward compatibility aliases
append_review_record = append
load_review_history = load
