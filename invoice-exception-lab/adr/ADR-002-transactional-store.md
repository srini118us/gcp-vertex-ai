# ADR-002: Transactional store for approvals and postings

Status: Accepted (2026-10-22)

## Context
Approvals, postings and the audit trail need: a uniqueness guarantee (never post twice), atomic
multi-row changes (status update plus approval row plus audit row together), and row level locks
for concurrent executors. Reference data already lives in BigQuery.

## Options
1. BigQuery. Already in place. But it has no enforced UNIQUE constraints and DML is not designed
   for high frequency single row transactions; idempotency would rely on application checks,
   which race.
2. Firestore. Transactions exist, but uniqueness is per document id only, and SQL reporting for
   auditors is harder.
3. Cloud SQL for PostgreSQL (or AlloyDB at larger scale). UNIQUE constraints, transactions,
   SELECT ... FOR UPDATE, row level security, point in time recovery.
4. SQLite for the lab only.

## Decision
SQLite in the lab (zero cost, runs in tests), Cloud SQL for PostgreSQL in production. The schema
(scripts/ap_store.py) uses only portable features so the move is a driver change:
`BEGIN IMMEDIATE` becomes a normal transaction with `SELECT ... FOR UPDATE` on the request row.
BigQuery stays the analytics copy, fed from the store (or by Datastream).

## Consequences
- Idempotency is enforced by the database, proven by the concurrent race test.
- SQLite serializes all writers; fine for a lab, not for production throughput.
- Production adds: private IP, IAM database authentication per service identity, INSERT only
  grant on the audit table for the app role, daily audit export to a bucket with a retention lock.
