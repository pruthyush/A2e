"""Append-only audit history log interface for Assurance Expiry Engine (stub)."""

from __future__ import annotations

from pathlib import Path

from aee.models import ReviewRecord


def append_review_record(
    history_path: Path | str,
    record: ReviewRecord,
) -> None:
    """Append a human review decision record to the audit history.

    Args:
        history_path: File path to the append-only history log.
        record: ReviewRecord documenting the human reassessment.

    Raises:
        NotImplementedError: Always raised in stub skeleton.
    """
    raise NotImplementedError("History management is not implemented yet.")


def load_review_history(
    history_path: Path | str,
) -> list[ReviewRecord]:
    """Load historical review records from the append-only history log.

    Args:
        history_path: File path to the append-only history log.

    Returns:
        List of historical ReviewRecord entries.

    Raises:
        NotImplementedError: Always raised in stub skeleton.
    """
    raise NotImplementedError("History loading is not implemented yet.")
