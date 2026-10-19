"""Unit tests for aee.loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from aee.loader import ModelLoadError, load_model
from aee.models import AssuranceModel

VALID_MODEL_YAML = """
facility: "Test Facility Alpha"
standard: "IEC 62443"
zones:
  - zone_id: "Z1"
    name: "Control Zone"
    purdue_level: 2
assets:
  - asset_id: "PLC-01"
    name: "Safety PLC"
    zone_id: "Z1"
    criticality: "safety"
    patch_status: "unpatchable"
controls:
  - control_id: "CTRL-01"
    name: "Firewall Rule"
    asset_id: "PLC-01"
    control_type: "firewall"
    description: "Port filter"
    owner: "SecOps"
    implemented_at: "2026-01-01T00:00:00Z"
    expires_at: "2026-12-31T23:59:59Z"
    status: "active"
    evidence_ids: ["EV-01"]
evidence:
  - evidence_id: "EV-01"
    control_id: "CTRL-01"
    evidence_type: "config"
    collected_at: "2026-01-02T00:00:00Z"
    valid_until: "2026-06-01T00:00:00Z"
    status: "current"
    source: "fw-export"
    sha256: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
claims:
  - claim_id: "CLM-01"
    asset_id: "PLC-01"
    zone_id: "Z1"
    framework: "IEC_62443"
    requirement_ref: "SR 1.1"
    statement: "Access restricted."
    status: "assured"
    supporting_control_ids: ["CTRL-01"]
    supporting_evidence_ids: ["EV-01"]
"""

DANGLING_CONTROL_YAML = """
facility: "Test Facility Alpha"
standard: "IEC 62443"
zones:
  - zone_id: "Z1"
    name: "Control Zone"
    purdue_level: 2
assets:
  - asset_id: "PLC-01"
    name: "Safety PLC"
    zone_id: "Z1"
    criticality: "safety"
    patch_status: "unpatchable"
controls: []
evidence: []
claims:
  - claim_id: "CLM-01"
    asset_id: "PLC-01"
    zone_id: "Z1"
    framework: "IEC_62443"
    requirement_ref: "SR 1.1"
    statement: "Access restricted."
    status: "assured"
    supporting_control_ids: ["CTRL-NONEXISTENT-999"]
"""

MALFORMED_YAML = """
facility: "Test Facility Alpha"
zones: [unclosed list
"""


def test_valid_model_loads(tmp_path: Path) -> None:
    """Proves that a well-formed model YAML file loads into a valid AssuranceModel."""
    model_path = tmp_path / "valid_model.yaml"
    model_path.write_text(VALID_MODEL_YAML, encoding="utf-8")

    model = load_model(model_path)
    assert isinstance(model, AssuranceModel)
    assert model.facility == "Test Facility Alpha"
    assert len(model.zones) == 1
    assert len(model.assets) == 1
    assert len(model.controls) == 1
    assert len(model.evidence) == 1
    assert len(model.claims) == 1
    assert model.claims[0].claim_id == "CLM-01"

    # Also test loading with str path
    model_from_str = load_model(str(model_path))
    assert model_from_str.facility == "Test Facility Alpha"


def test_dangling_supporting_control_ids_raises_model_load_error(tmp_path: Path) -> None:
    """Proves that dangling supporting_control_ids raises ModelLoadError naming the ID."""
    model_path = tmp_path / "dangling_control.yaml"
    model_path.write_text(DANGLING_CONTROL_YAML, encoding="utf-8")

    with pytest.raises(ModelLoadError) as exc_info:
        load_model(model_path)

    err_msg = str(exc_info.value)
    assert "CTRL-NONEXISTENT-999" in err_msg
    assert "supporting_control_id" in err_msg


def test_malformed_yaml_raises_model_load_error_with_file_path(tmp_path: Path) -> None:
    """Proves that malformed YAML raises ModelLoadError containing the file path."""
    model_path = tmp_path / "malformed.yaml"
    model_path.write_text(MALFORMED_YAML, encoding="utf-8")

    with pytest.raises(ModelLoadError) as exc_info:
        load_model(model_path)

    err_msg = str(exc_info.value)
    assert str(model_path) in err_msg
    assert "Malformed YAML" in err_msg


def test_file_not_found_raises_model_load_error(tmp_path: Path) -> None:
    """Proves that attempting to load a missing file raises ModelLoadError with file path."""
    missing_path = tmp_path / "nonexistent.yaml"

    with pytest.raises(ModelLoadError) as exc_info:
        load_model(missing_path)

    assert str(missing_path) in str(exc_info.value)


def test_non_dict_yaml_raises_model_load_error(tmp_path: Path) -> None:
    """Proves that a YAML list or scalar raises ModelLoadError formatted as root: message."""
    list_path = tmp_path / "list.yaml"
    list_path.write_text("- item1\n- item2\n", encoding="utf-8")

    with pytest.raises(ModelLoadError) as exc_info:
        load_model(list_path)

    assert "root: Expected a YAML mapping" in str(exc_info.value)


def test_schema_validation_error_formatting(tmp_path: Path) -> None:
    """Proves that validation errors format as '<yaml.path>: <message>'."""
    bad_schema_yaml = """
facility: 12345
standard: "IEC 62443"
"""
    bad_path = tmp_path / "bad_schema.yaml"
    bad_path.write_text(bad_schema_yaml, encoding="utf-8")

    with pytest.raises(ModelLoadError) as exc_info:
        load_model(bad_path)

    assert "facility: Input should be a valid string" in str(exc_info.value)
