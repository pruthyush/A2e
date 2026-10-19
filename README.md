# Assurance Expiry Engine (AEE)

A standalone prototype that detects when compensating controls or their supporting evidence expire, propagates that change to dependent **IEC 62443** assurance claims, invalidates those claims, preserves the prior decision in an append-only history, and requires an explicit human reassessment.

## Core Boundaries

The engine rigorously enforces two boundaries:
1. **INVALIDATED ≠ NONCOMPLIANT**: The engine flags that an assurance decision is no longer supported. It never declares an asset unsafe or noncompliant; that conclusion requires qualified human review.
2. **NO EQUIVALENCE CLAIMS**: The tool must never assert that a compensating control "offsets" a patch or "achieves" a specific IEC 62443 Security Level. Risk and compliance conclusions are strictly out of scope.

---

## Installation

Install in editable mode with development dependencies:

```bash
pip install -e ".[dev]"
```

Requirements:
- Python >= 3.10
- Dependencies: `typer>=0.12`, `pydantic>=2.6`, `pyyaml>=6.0`
- Dev dependencies: `pytest>=8`, `ruff>=0.4`, `pytest-cov`

---

## Running the CLI

Inspect CLI commands and flags:

```bash
aee --help
```

Available subcommands:

```bash
# Check assurance claims against model and timestamp
aee check --model path/to/model.yaml --now 2026-10-19T10:00:00Z [--output path/to/out.json]

# Record human review decision for an invalidated claim
aee review --model path/to/model.yaml --history path/to/history.jsonl --claim CLAIM-ID --decision approve --actor "Lead Assessor" --now 2026-10-19T10:00:00Z

# Generate audit-ready assurance status report
aee report --model path/to/model.yaml --history path/to/history.jsonl --now 2026-10-19T10:00:00Z --output path/to/report.md
```

---

## One-Command Demo

Run the check command on any target model with an ISO-8601 evaluation timestamp:

```bash
aee check --model examples/model.yaml --now 2026-10-19T10:00:00Z
```

*(Outputs stub status message while engine core logic is under implementation).*

---

## Testing & Linting

Run unit tests:

```bash
pytest
```

Run code linter:

```bash
ruff check .
```
