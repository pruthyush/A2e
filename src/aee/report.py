"""Assurance audit report generator interface for Assurance Expiry Engine (stub)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from aee.models import AssuranceModel, ReviewRecord


def generate_report(
    model: AssuranceModel,
    history: list[ReviewRecord],
    now: datetime,
    output_path: Path | str,
) -> None:
    """Generate an audit-ready assurance status report.

    Args:
        model: Evaluated AssuranceModel instance.
        history: Review history records.
        now: Report timestamp.
        output_path: File path where report will be saved.

    Raises:
        NotImplementedError: Always raised in stub skeleton.
    """
    raise NotImplementedError("Report generation is not implemented yet.")
