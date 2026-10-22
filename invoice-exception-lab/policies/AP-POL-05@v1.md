# AP-POL-05 Tax and currency

Version: v1. Effective: 2025-01-01.

## AP-POL-05@v1:1.1 Tax
Tax on the invoice must equal the subtotal times the PO tax rate, rounded to cents. A difference
above 1.00 is placed on HOLD with reason TAX_ERROR; the disputed amount is the tax difference.

## AP-POL-05@v1:2.1 Currency
The invoice currency must equal the PO currency. A mismatch is placed on HOLD with reason
CURRENCY_MISMATCH. AP never converts an invoice to fit a PO.
