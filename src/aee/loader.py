"""Model loading interface for Assurance Expiry Engine (stub)."""

from __future__ import annotations

from pathlib import Path

from aee.models import AssuranceModel


def load_model(path: Path | str) -> AssuranceModel:
    """Load and validate an AssuranceModel from a YAML or JSON file.

    Args:
        path: Path to the model file.

    Returns:
        Validated AssuranceModel instance.

    Raises:
        NotImplementedError: Always raised in stub skeleton.
    """
    raise NotImplementedError("Model loading is not implemented yet.")
