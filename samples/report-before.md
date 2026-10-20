# Assurance Audit Report

## Summary

- **Facility:** Refinery-Alpha
- **Standard:** IEC 62443
- **Claims Status:**
  - Assured: 4
  - Under Review: 0
  - Invalidated: 1
- **Controls:** 3 active, 0 expired
- **Evidence:** 3 current, 1 stale

## Invalidated Claims Table

| Claim ID | Framework | Requirement | Previous status | Triggering control/evidence | Reason | Required action |
|---|---|---|---|---|---|---|
| AC-07 | IEC_62443 | SR 1.1 | assured | EVD-12 | Assurance for claim AC-07 is no longer supported: evidence EVD-12 is stale since 2026-10-01. Human reassessment required. | Human reassessment required |

## Dependency Rationale

- EVD-12 stale since 2026-10-01 → CC-04 → AC-07

## Preserved Decision History

*No review records recorded.*

## Limitations

This report records that assurance is no longer supported; it does not determine safety, compliance, or equivalence to patching. Risk conclusions require qualified human review.

## Reproducibility

- **Model SHA-256:** 771c5d847491ac4e144f948388763f00a1948a9dc98f5ec7b077655e4d7c78ab
- **History SHA-256:** e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
- **Command Line:** aee report --model samples\assurance.yaml --history samples\empty_history.jsonl --now 2026-11-01T00:00:00Z
- **Timestamp (UTC):** 2026-11-01T00:00:00Z
