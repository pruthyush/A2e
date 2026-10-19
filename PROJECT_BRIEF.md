# Assurance Expiry Engine (AEE) — Project Brief

## What this is
A small, standalone prototype that detects when compensating controls or their
supporting evidence expire, propagates that change to dependent IEC 62443
assurance claims, invalidates those claims, preserves the prior decision in an
append-only history, and requires an explicit human reassessment.

## What this is NOT
- Not a GRC platform.
- Not a fork of Industrace, CISO Assistant, or Eramba.
- Not a network scanner, PCAP analyzer, or traffic validator.
- Not a novel contribution claim. It is a prototype testing whether a specific
  workflow gap exists in existing OT assurance tools.

## Two boundaries the code must enforce
1. INVALIDATED ≠ NONCOMPLIANT. The engine flags that an assurance decision is
   no longer supported. It never declares an asset unsafe or noncompliant.
   That conclusion requires qualified human review.
2. NO EQUIVALENCE CLAIMS. The tool must never assert that a compensating
   control "offsets" a patch or "achieves" a specific IEC 62443 Security Level.
   Risk and compliance conclusions are out of scope.

## One-sentence purpose
Turn "a compensating control expired" into "here are the exact assurance claims
that are no longer supported, with an audit record an assessor can reproduce"—
and refuse to go any further than that.