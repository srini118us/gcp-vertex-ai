# AP-POL-01 Three way match and tolerances

Version: v2. Effective: 2026-07-01. Supersedes AP-POL-01@v1.

## AP-POL-01@v2:1.1 Scope
Every supplier invoice that references a purchase order is matched three ways: invoice, purchase
order (PO) and receipt. Goods are matched to goods receipts (GR). Services follow 4.2.

## AP-POL-01@v2:2.1 Price tolerance
For each invoice line, the price excess is (invoice unit price minus PO unit price) times invoiced
quantity. The line is within tolerance when the excess is no more than the LOWER of 2 percent of
(PO unit price times invoiced quantity) and 500.00 USD. A line outside tolerance is placed on
HOLD with reason PRICE_VARIANCE; the disputed amount is the full price excess of that line.
Invoice prices below PO price are accepted.

## AP-POL-01@v2:3.1 Quantity against receipts
Quantity is checked cumulatively per PO line: quantity already invoiced plus quantity on this
invoice must not exceed total quantity received. Excess quantity is placed on HOLD with reason
QTY_OVER_RECEIPT; the disputed amount is the excess quantity times the invoice unit price.

## AP-POL-01@v2:4.1 Missing receipt
A goods line with no goods receipt is placed on HOLD with reason MISSING_GR; the disputed amount
is the line amount before tax.

## AP-POL-01@v2:4.2 Services
Service lines are matched against an approved service entry sheet (SES) instead of a GR. An
approved SES covering the invoiced quantity satisfies the receipt check.
