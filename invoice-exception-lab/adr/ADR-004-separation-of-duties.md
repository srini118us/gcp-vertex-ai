# ADR-004: Separation of duties across agent, approver, executor and verifier

Status: Accepted (2026-10-22)

## Context
Policy AP-POL-04 requires approval by role and amount, and an approver who is not the PO
requester. An AI agent with tool access must not become a path around that.

## Decision
Four actors with disjoint permissions (spec/users.json):

| Actor | Identity | Can | Cannot |
|---|---|---|---|
| Investigation agent | svc-ap-agent | read case data, propose, explain | approve, post |
| Approver | a named human with a role | approve if role rank is high enough and not the PO requester | post |
| Executor | svc-ap-executor | post an APPROVED request whose evidence hash matches what was approved | approve |
| Verifier | svc-ap-verifier | read the ledger back and raise alerts | post, approve |

The approval stores the evidence hash the approver saw; the executor refuses if the evidence
changed since. An unknown PO requester fails closed. Every refusal is audited.

## Consequences
- In the lab these are checks in one process (scripts/ap_workflow.py). In production each actor
  is a separate service account, and the checks are backed by IAM: only svc-ap-executor holds
  the database role that can INSERT into the ledger, so a bug in the agent cannot post.
- Approvals in the lab are SIMULATED by a routing table. Production would use a real approval
  inbox (ServiceNow approval or a mail action, planned via MCP) with the same checks server side.
- The normal run shows one refusal: R03 is first routed to r.castillo, who requested PO-4504,
  and is re-routed to d.whitfield.
