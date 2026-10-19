"""Expiry evaluation engine interface for Assurance Expiry Engine (stub)."""

from __future__ import annotations

from datetime import datetime

from aee.models import AssuranceModel


def evaluate_assurance(
    model: AssuranceModel,
    now: datetime,
) -> dict[str, object]:
    """Evaluate controls and propagate expirations to assurance claims.

    Args:
        model: Loaded AssuranceModel to evaluate.
        now: Evaluation timestamp.

    Returns:
        Evaluation summary and invalidated claims mapping.

    Raises:
        NotImplementedError: Always raised in stub skeleton.
    """
    raise NotImplementedError("Assurance evaluation engine is not implemented yet.")
