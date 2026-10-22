# AP-POL-03 Vendor bank details

Version: v1. Effective: 2025-03-01.

## AP-POL-03@v1:1.1 Bank detail mismatch
Payment is made only to the bank account held in the vendor master. If an invoice or any
communication shows a different account, the invoice is placed on HOLD with reason BANK_CHANGE.
The account on the invoice is never used.

## AP-POL-03@v1:1.2 Verification
A bank change is verified by a call back to a phone number already on file, not one supplied in
the request, and is entered by vendor master data staff. AP does not change vendor bank data.
