"""Command-line interface for the Assurance Expiry Engine (AEE)."""

from __future__ import annotations

import hashlib
import sys
from enum import Enum
from pathlib import Path
from typing import Optional

import typer
import yaml

from aee.clock import resolve_now
from aee.engine import (
    Invalidation,
    StateChange,
    apply_invalidations,
    evaluate_states,
    propagate,
)
from aee.history import HistoryIntegrityError
from aee.history import append as append_history
from aee.history import load as load_history
from aee.loader import ModelLoadError, load_model
from aee.models import AssuranceModel, ReviewRecord
from aee.report import write_audit_report, write_findings_json

app = typer.Typer(
    name="aee",
    help="A2e — Assurance Expiry Engine CLI.",
    no_args_is_help=True,
)


class ReviewDecision(str, Enum):
    """Allowed human review decisions."""

    approve = "approve"
    reject = "reject"


def _filter_unreviewed_invalidations(
    model: AssuranceModel,
    invalidations: list[Invalidation],
    changes: list[StateChange],
) -> list[Invalidation]:
    """Filter out invalidations where claim was reviewed after the triggering change."""
    claim_map = {c.claim_id: c for c in model.claims}
    change_map = {c.entity_id: c for c in changes}
    active_invs: list[Invalidation] = []
    for inv in invalidations:
        claim = claim_map.get(inv.claim_id)
        trigger = change_map.get(inv.triggering_entity_id)
        if claim and claim.last_reviewed_at and trigger:
            eff = trigger.effective_at
            rev = claim.last_reviewed_at
            if eff.tzinfo is not None and rev.tzinfo is None:
                rev = rev.replace(tzinfo=eff.tzinfo)
            elif eff.tzinfo is None and rev.tzinfo is not None:
                eff = eff.replace(tzinfo=rev.tzinfo)
            if eff <= rev:
                continue
        active_invs.append(inv)
    return active_invs


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
    try:
        try:
            now_dt = resolve_now(now)
        except ValueError as e:
            sys.stderr.write(f"Invalid timestamp '{now}': {e}\n")
            raise typer.Exit(code=2)

        model_instance = load_model(model)
        changes = evaluate_states(model_instance, now_dt)
        invalidations = propagate(model_instance, changes)
        invalidations = _filter_unreviewed_invalidations(model_instance, invalidations, changes)

        if output is not None:
            write_findings_json(invalidations, output)

        new_model, _ = apply_invalidations(model_instance, invalidations, now_dt)

        new_inv_count = len(invalidations)
        assured_count = sum(1 for c in new_model.claims if c.status == 'assured')
        under_review_count = sum(1 for c in new_model.claims if c.status == "under_review")
        prior_inv_count = sum(1 for c in model_instance.claims if c.status == "invalidated")

        typer.echo(
            f"Claims invalidated: {new_inv_count} | Assured: {assured_count} | "
            f"Under review: {under_review_count} | Invalidated (prior): {prior_inv_count}"
        )

        if new_inv_count > 0:
            raise typer.Exit(code=1)
        raise typer.Exit(code=0)

    except typer.Exit:
        raise
    except ModelLoadError as e:
        sys.stderr.write(f"Model load error: {e}\n")
        raise typer.Exit(code=3)
    except HistoryIntegrityError as e:
        sys.stderr.write(f"History integrity error: {e}\n")
        raise typer.Exit(code=4)
    except OSError as e:
        sys.stderr.write(f"I/O error: {e}\n")
        raise typer.Exit(code=1)
    except Exception as e:
        sys.stderr.write(f"Unexpected error: {e}\n")
        raise typer.Exit(code=1)


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
    try:
        try:
            now_dt = resolve_now(now)
        except ValueError as e:
            sys.stderr.write(f"Invalid timestamp '{now}': {e}\n")
            raise typer.Exit(code=2)

        model_instance = load_model(model)

        # Evaluate temporal states up to now_dt so expired claims are in invalidated state
        changes = evaluate_states(model_instance, now_dt)
        invalidations = propagate(model_instance, changes)
        invalidations = _filter_unreviewed_invalidations(model_instance, invalidations, changes)
        model_instance, _ = apply_invalidations(model_instance, invalidations, now_dt)

        target_claim = next((c for c in model_instance.claims if c.claim_id == claim), None)
        if target_claim is None:
            sys.stderr.write(f"Error: Unknown claim '{claim}'\n")
            raise typer.Exit(code=5)

        # Generate unique record ID
        rec_id = f"REV-{target_claim.claim_id}-{int(now_dt.timestamp())}"
        if history.exists():
            try:
                existing = load_history(history)
                existing_ids = {r.record_id for r in existing}
                if rec_id in existing_ids:
                    suffix = 1
                    while f"{rec_id}-{suffix}" in existing_ids:
                        suffix += 1
                    rec_id = f"{rec_id}-{suffix}"
            except Exception:
                pass

        if decision == ReviewDecision.approve:
            if evidence is None:
                sys.stderr.write("Error: --evidence is required for approve decisions.\n")
                raise typer.Exit(code=2)

            if not evidence.exists():
                sys.stderr.write(f"Error: Evidence file '{evidence}' does not exist.\n")
                raise typer.Exit(code=2)

            if target_claim.status != "invalidated":
                sys.stderr.write(
                    f"Error: Claim '{claim}' is '{target_claim.status}', "
                    "approve is only permitted for 'invalidated' claims.\n"
                )
                raise typer.Exit(code=6)

            ev_bytes = evidence.read_bytes()
            evidence_sha256 = hashlib.sha256(ev_bytes).hexdigest()
            notes_record = (
                f"{notes.strip()} evidence_sha256={evidence_sha256}"
                if notes and notes.strip()
                else f"evidence_sha256={evidence_sha256}"
            )

            prev_status = target_claim.status
            # THIS IS THE ONLY CODE PATH IN THE ENTIRE PROJECT ALLOWED TO SET 'assured'
            target_claim.status = "assured"
            target_claim.last_reviewed_at = now_dt
            target_claim.reviewer = actor

            record = ReviewRecord(
                record_id=rec_id,
                timestamp=now_dt,
                actor=actor,
                action="approve",
                claim_id=target_claim.claim_id,
                reason=f"Assessor approval by {actor}",
                previous_status=prev_status,
                new_status='assured',
                notes=notes_record,
            )
        else:  # reject
            prev_status = target_claim.status
            target_claim.status = "under_review"
            target_claim.last_reviewed_at = now_dt
            target_claim.reviewer = actor

            record = ReviewRecord(
                record_id=rec_id,
                timestamp=now_dt,
                actor=actor,
                action="reject",
                claim_id=target_claim.claim_id,
                reason=f"Assessor rejection by {actor}",
                previous_status=prev_status,
                new_status="under_review",
                notes=notes,
            )

        # Append to audit history
        append_history(history, record)

        # Rewrite model file
        model.parent.mkdir(parents=True, exist_ok=True)
        with open(model, "w", encoding="utf-8") as f:
            yaml.safe_dump(model_instance.model_dump(mode="json"), f, sort_keys=False)

        typer.echo(f"Claim {claim} review recorded: {decision.value}")
        raise typer.Exit(code=0)

    except typer.Exit:
        raise
    except ModelLoadError as e:
        sys.stderr.write(f"Model load error: {e}\n")
        raise typer.Exit(code=3)
    except HistoryIntegrityError as e:
        sys.stderr.write(f"History integrity error: {e}\n")
        raise typer.Exit(code=4)
    except OSError as e:
        sys.stderr.write(f"I/O error: {e}\n")
        raise typer.Exit(code=1)
    except Exception as e:
        sys.stderr.write(f"Unexpected error: {e}\n")
        raise typer.Exit(code=1)


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
    try:
        try:
            now_dt = resolve_now(now)
        except ValueError as e:
            sys.stderr.write(f"Invalid timestamp '{now}': {e}\n")
            raise typer.Exit(code=2)

        model_instance = load_model(model)
        history_records = load_history(history) if history.exists() else []

        # Recompute states from model at `now`
        changes = evaluate_states(model_instance, now_dt)
        invalidations = propagate(model_instance, changes)
        invalidations = _filter_unreviewed_invalidations(model_instance, invalidations, changes)
        evaluated_model, _ = apply_invalidations(model_instance, invalidations, now_dt)

        model_sha = hashlib.sha256(model.read_bytes()).hexdigest()
        history_sha = (
            hashlib.sha256(history.read_bytes()).hexdigest()
            if history.exists()
            else "N/A"
        )
        input_hashes = {
            "model": model_sha,
            "history": history_sha,
        }
        cmd_str = f"aee report --model {model} --history {history} --now {now}"

        write_audit_report(
            model=evaluated_model,
            history=history_records,
            invalidations=invalidations,
            now=now_dt,
            command=cmd_str,
            input_hashes=input_hashes,
            output_path=output,
        )

        typer.echo(f"Report generated: {output}")
        raise typer.Exit(code=0)

    except typer.Exit:
        raise
    except ModelLoadError as e:
        sys.stderr.write(f"Model load error: {e}\n")
        raise typer.Exit(code=3)
    except HistoryIntegrityError as e:
        sys.stderr.write(f"History integrity error: {e}\n")
        raise typer.Exit(code=4)
    except OSError as e:
        sys.stderr.write(f"I/O error: {e}\n")
        raise typer.Exit(code=1)
    except Exception as e:
        sys.stderr.write(f"Unexpected error: {e}\n")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
