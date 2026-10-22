# AP-POL-02 Duplicate invoice prevention

Version: v1. Effective: 2025-03-01.

## AP-POL-02@v1:1.1 Exact duplicate
Invoice numbers are normalized by removing spaces and punctuation and converting to upper case.
An invoice with the same vendor and the same normalized number as an invoice already POSTED or
PAID is REJECTED with reason DUPLICATE.

## AP-POL-02@v1:1.2 Suspected duplicate
An invoice from the same vendor with the same total as an invoice POSTED or PAID within the
previous 30 days, but a different normalized number, is placed on HOLD with reason
DUPLICATE_SUSPECTED until AP confirms with the vendor.
