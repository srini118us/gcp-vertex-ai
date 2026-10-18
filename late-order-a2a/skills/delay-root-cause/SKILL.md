---
name: delay-root-cause
description: Diagnose why one order is late by invoking the governed deterministic delay_root_cause tool, then explain the result without changing any code or value.
---

# Delay Root Cause

A reusable skill for any Claude based agent that must explain why a specific
order was delivered late. The authoritative diagnosis comes from a deterministic
tool. The job here is to invoke that tool and describe its output faithfully,
never to compute or judge the cause independently.

## When to use

Use this skill when a request asks why one order is late, or asks for a delay
diagnosis for a single order id. One order per diagnosis.

## How to invoke the diagnosis

1. Always call the `delay_root_cause` tool with the order id from the request.
2. Never answer from memory or estimation. If the tool was not called, the
   answer is not valid.
3. Treat the tool result as the single source of truth.

## How to read the baseline

Each item is compared with the shipping distribution center 90 day baseline.
The result gives the measured warehouse lag and transit time in hours, next to
that center average. Report the measured hours against the baseline hours as
given. Do not recompute ratios or thresholds; the tool already applied them.

## Warehouse delay versus transit delay

- A warehouse delay means the fulfillment lag inside the center ran well above
  that center normal before the item shipped.
- A transit delay means the item shipped on time but the in transit leg ran
  beyond the center normal.
Explain which one drove each item using only the codes and numbers returned.

## Missing or unavailable data

If the tool returns an error or status such as ORDER_NOT_FOUND, INVALID_ORDER_ID,
ACCESS_DENIED, or DATA_UNAVAILABLE, report that status plainly. Do not guess a
cause, do not describe data the tool did not return, and do not expose any raw
system or database detail.

## Preserve exact cause codes

Reproduce each item cause code exactly as returned: one of NOT_YET_SHIPPED,
WAREHOUSE_DELAY, TRANSIT_DELAY, WITHIN_NORMAL. Do not translate them into prose
labels such as "warehouse lag", rename them, or merge them. A downstream agent
reads these exact codes.

## No speculation, no override

Never invent a cause code that is not in the result. Never drop a code that is
in the result. Never override the tool values with a different number or
conclusion. If the explanation would require information the tool did not
provide, say so instead of filling the gap. This agent does not handle refunds,
credits, or customer messaging.

See `reference/cause-codes.md` for the meaning of each code.
