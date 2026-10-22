# ADR-003: Idempotency key for postings

Status: Accepted (2026-10-22)

## Context
Retries happen: a network reset (seen on R01 in this lab), a Pub/Sub redelivery, an operator
re-running a batch. Each must not create a second payment. Separately, suppliers resend the same
invoice with a different spelling of the number ("AC 10077" versus "AC-10077", case R07).

## Options
1. A random request id per attempt. Protects nothing on a retry that generates a new id.
2. Request id (one per case). Stops replays of the same request, not a resent invoice that
   arrives as a new case.
3. Business key: sha256(vendor_id | invoice number upper case with every non alphanumeric removed).

## Decision
Option 3, enforced by `UNIQUE (idempotency_key)` on the ledger. The ledger is seeded with
already posted or paid history, so the key also blocks a duplicate the rules engine missed.
The executor tells the two cases apart: same request id means a replay (return the first posting,
audit `replay_blocked`); a different request means a duplicate (audit `duplicate_blocked`, verifier
raises MISMATCH).

## Consequences
- Proven in tests: replay, a two thread race, and a planted APPROVE of R07 that the database
  blocks.
- Two genuinely different invoices with the same vendor and number would be blocked. That is the
  correct failure direction (a human resolves it), and suppliers reusing numbers is itself a
  control finding.
- Normalization is deliberately simple. Near duplicates with different numbers (INV2045A versus
  INV-2045, case E02) are the rules engine's job and the optional X1 experiment's, not the key's.
