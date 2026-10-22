# Architecture Decision Records

One short record per significant choice: context, options, decision, consequences.
Status values: Accepted, Superseded, Proposed.

| ADR | Decision | Status |
|---|---|---|
| [ADR-001](ADR-001-rules-decide-agent-explains.md) | Deterministic rules decide; the agent investigates and explains | Accepted |
| [ADR-002](ADR-002-transactional-store.md) | SQLite in the lab, Cloud SQL for PostgreSQL in production, not BigQuery, for approvals and postings | Accepted |
| [ADR-003](ADR-003-idempotency-key.md) | Idempotency key = vendor id plus normalized invoice number, enforced by a UNIQUE constraint | Accepted |
| [ADR-004](ADR-004-separation-of-duties.md) | Four separate actors: agent proposes, human approves, executor posts, verifier reads back | Accepted |
