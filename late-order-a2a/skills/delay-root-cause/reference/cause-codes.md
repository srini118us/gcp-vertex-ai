# Cause codes

The deterministic `delay_root_cause` tool assigns exactly one code per order
item. These definitions are for explanation only. The tool is authoritative and
applies the thresholds itself; this skill must not recompute them.

| Code | Meaning |
|---|---|
| `NOT_YET_SHIPPED` | The item has no shipment yet, so no transit could start. |
| `WAREHOUSE_DELAY` | Fulfillment lag inside the distribution center ran well above that center 90 day average before the item shipped. |
| `TRANSIT_DELAY` | The item shipped, but the in transit leg ran beyond the center 90 day average. |
| `WITHIN_NORMAL` | Warehouse lag and transit time were within the center normal range; no operational delay flagged. |

Notes

- Codes are compared against each shipping center own 90 day baseline, not a
  global average, so the same hours can be normal at one center and delayed at
  another.
- A single order can carry different codes across items when it ships split
  from more than one center.
- Report every item code the tool returns. Do not collapse multiple items into
  one code.
