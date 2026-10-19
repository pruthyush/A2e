"""Assurance model loader for Assurance Expiry Engine (AEE)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from aee.models import AssuranceModel


class ModelLoadError(Exception):
    """Raised when an AssuranceModel fails to load or validate."""


def load_model(path: Path | str) -> AssuranceModel:
    """Parse YAML, validate against Pydantic models.

    Args:
        path: Path to the model file.

    Returns:
        Validated AssuranceModel instance.

    Raises:
        ModelLoadError: If file cannot be read, YAML parsing fails, or validation fails.
            Validation failure messages list every error as '<yaml.path>: <message>'.
    """
    path_obj = Path(path)
    try:
        content = path_obj.read_text(encoding="utf-8")
    except OSError as e:
        raise ModelLoadError(f"Failed to read model file '{path_obj}': {e}") from e

    try:
        data: Any = yaml.safe_load(content)
    except yaml.YAMLError as e:
        raise ModelLoadError(f"Malformed YAML in '{path_obj}': {e}") from e

    if not isinstance(data, dict):
        raise ModelLoadError(
            f"root: Expected a YAML mapping in '{path_obj}', got {type(data).__name__}"
        )

    try:
        return AssuranceModel.model_validate(data)
    except ValidationError as e:
        error_lines: list[str] = []
        for err in e.errors():
            loc = ".".join(str(p) for p in err["loc"]) if err["loc"] else "root"
            msg = err["msg"]
            error_lines.append(f"{loc}: {msg}")
        raise ModelLoadError("\n".join(error_lines)) from e
