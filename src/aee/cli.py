"""Command-line interface for the Assurance Expiry Engine (AEE)."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(
    name="aee",
    help="Assurance Expiry Engine (AEE) CLI.",
    no_args_is_help=True,
)


class ReviewDecision(str, Enum):
    """Allowed human review decisions."""

    approve = "approve"
    reject = "reject"


@app.command()
def check(
    model: Path = typer.Option(
        ...,
        "--model",
        help="Path to assurance model file (YAML/JSON).",
    ),
    now: str = typer.Option(
        ...,
        "--now",
        help="Evaluation timestamp (ISO-8601).",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        help="Path to write evaluation output.",
    ),
) -> None:
    """Evaluate model for expired controls/evidence and claim invalidation."""
    typer.echo("Not implemented yet.")
    raise typer.Exit(code=0)


@app.command()
def review(
    model: Path = typer.Option(
        ...,
        "--model",
        help="Path to assurance model file (YAML/JSON).",
    ),
    history: Path = typer.Option(
        ...,
        "--history",
        help="Path to review history log file.",
    ),
    claim: str = typer.Option(
        ...,
        "--claim",
        help="Assurance claim ID to review.",
    ),
    decision: ReviewDecision = typer.Option(
        ...,
        "--decision",
        help="Review decision (approve | reject).",
    ),
    actor: str = typer.Option(
        ...,
        "--actor",
        help="Name or identifier of the reviewer.",
    ),
    evidence: Optional[Path] = typer.Option(
        None,
        "--evidence",
        help="Path to supporting evidence file.",
    ),
    notes: Optional[str] = typer.Option(
        None,
        "--notes",
        help="Optional review notes or justification.",
    ),
    now: str = typer.Option(
        ...,
        "--now",
        help="Review timestamp (ISO-8601).",
    ),
) -> None:
    """Record an assessor review decision for an invalidated or pending claim."""
    typer.echo("Not implemented yet.")
    raise typer.Exit(code=0)


@app.command()
def report(
    model: Path = typer.Option(
        ...,
        "--model",
        help="Path to assurance model file (YAML/JSON).",
    ),
    history: Path = typer.Option(
        ...,
        "--history",
        help="Path to review history log file.",
    ),
    now: str = typer.Option(
        ...,
        "--now",
        help="Report evaluation timestamp (ISO-8601).",
    ),
    output: Path = typer.Option(
        ...,
        "--output",
        help="Path to write report output.",
    ),
) -> None:
    """Generate an audit report for assurance status and expiry history."""
    typer.echo("Not implemented yet.")
    raise typer.Exit(code=0)


if __name__ == "__main__":
    app()
