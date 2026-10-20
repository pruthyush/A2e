# A2e — Sample reassessment report

This folder shows what the `aee` CLI produces when a compensating control's
evidence expires.

## Files

- `assurance.yaml` — the input model: 5 IEC 62443 assurance claims, 3
  compensating controls, 4 evidence items across 3 assets in 2 zones.
- `empty_history.jsonl` — an empty starting history (0 bytes). The report
  is generated before any human has reviewed the claim, so no decision
  records exist yet.
- `report-before.md` — the output. This is what `aee report` actually
  produced on 2026-11-01.

## What this shows

Claim `AC-07` depends on compensating control `CC-04`, which is supported
by evidence `EVD-12`. `EVD-12` is stale as of `2026-10-01`. The engine
detected the staleness, walked the dependency chain
`EVD-12 → CC-04 → AC-07`, and marked `AC-07` as `invalidated`.

The reason string is fixed:

> "Assurance for claim AC-07 is no longer supported: evidence EVD-12 is
> stale since 2026-10-01. Human reassessment required."

The engine does NOT declare the asset noncompliant or unsafe. It only
records that assurance is no longer supported. A human must reassess.

## Reproduce it yourself

From a fresh clone of this repo, with the CLI installed:

    pip install -e .
    python -m aee report \
        --model samples/assurance.yaml \
        --history samples/empty_history.jsonl \
        --now 2026-11-01T00:00:00Z \
        --output /tmp/report.md
    diff samples/report-before.md /tmp/report.md

The two files should be byte-identical. If they are not, something is
non-deterministic — please open an issue.
