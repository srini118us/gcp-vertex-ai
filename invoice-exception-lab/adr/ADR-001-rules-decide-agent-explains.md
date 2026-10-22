# ADR-001: Rules decide, the agent investigates and explains

Status: Accepted (2026-10-22)

## Context
Each invoice gets a disposition (APPROVE, HOLD, REJECT, REQUEST_REVIEW) that can release money.
A wrong APPROVE costs real money; a wrong HOLD costs a day of a clerk's time and maybe a late fee.
The earlier reconciliation lab scored deterministic rules at 100 of 100 and LLMs at 16 or less.

## Options
1. The LLM agent decides the disposition.
2. Rules decide; the agent may override with justification.
3. Rules decide; the agent can only add context (explanation, citations, injection flag) and one
   narrowly gated reason code (UNVERIFIED_APPROVAL_CLAIM, checked by code against the approvals log).

## Decision
Option 3. Guardrails in code (scripts/guardrails.py) keep disposition, amounts and approver role
exactly as the rules set them. An agent proposal that differs is recorded as a disagreement for
the human; a proposal to APPROVE something the rules held is recorded as unsafe.

## Consequences
- Accuracy of money decisions does not depend on model behavior; model upgrades cannot regress it.
- The agent's value is measured separately: explanation quality, injection detection, citation
  validity. On 20 cases: zero unsafe proposals, injection caught on E03 and E10, 33 citations kept.
- Cost: about 0.04 USD and 77 s per case for the agent; the rules alone are free and instant. At
  2,500 invoices a month, running the agent only on exceptions cuts cost by the clean rate.
- New rules need code changes and tests; the agent cannot "learn" a new policy on its own. That
  is intended: policy changes go through review.
