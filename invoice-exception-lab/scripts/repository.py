"""Data access for the matcher. Two backends with one interface.

  CsvRepo        reads data/*.csv, used by tests and offline runs
  BigQueryRepo   reads dataset invoice_lab through the BigQuery REST API

Security rule: every value that came from an invoice (vendor id, PO number, invoice number) is
untrusted, because the document author controls it. BigQuery queries therefore use named query
parameters only. Invoice text is never concatenated into SQL.

Select with INV_DATA=csv (default) or INV_DATA=bigquery.
"""
import csv
import os
from decimal import Decimal

from common import D, PROJECT, call

DATASET = os.getenv("INV_DATASET", "invoice_lab")


class CsvRepo:
    name = "csv"

    def _rows(self, f):
        with open(D("data", f), encoding="utf-8") as fh:
            return list(csv.DictReader(fh))

    def vendor(self, vendor_id):
        return next((r for r in self._rows("vendors.csv") if r["vendor_id"] == vendor_id), None)

    def po_lines(self, po_number):
        return [r for r in self._rows("purchase_orders.csv") if r["po_number"] == po_number]

    def received(self, po_number, po_line, receipt_type):
        return sum(int(r["quantity"]) for r in self._rows("goods_receipts.csv")
                   if r["po_number"] == po_number and int(r["po_line"]) == int(po_line)
                   and r["receipt_type"] == receipt_type)

    def invoiced(self, po_number, po_line):
        return sum(int(r["quantity_invoiced"]) for r in self._rows("invoiced_quantities.csv")
                   if r["po_number"] == po_number and int(r["po_line"]) == int(po_line))

    def vendor_history(self, vendor_id):
        return [r for r in self._rows("invoice_history.csv")
                if r["vendor_id"] == vendor_id and r["status"] in ("POSTED", "PAID")]

    def receipts(self, po_number):
        return [r for r in self._rows("goods_receipts.csv") if r["po_number"] == po_number]

    def approvals(self, object_id):
        return [r for r in self._rows("approvals_log.csv") if r["object_id"] == object_id]


class BigQueryRepo:
    name = "bigquery"
    URL = f"https://bigquery.googleapis.com/bigquery/v2/projects/{PROJECT}/queries"

    def _q(self, sql, **params):
        qp = []
        for k, v in params.items():
            typ = "INT64" if isinstance(v, int) else "STRING"
            qp.append({"name": k, "parameterType": {"type": typ},
                       "parameterValue": {"value": str(v)}})
        resp = call("POST", self.URL, {"query": sql, "useLegacySql": False,
                                       "parameterMode": "NAMED", "queryParameters": qp,
                                       "timeoutMs": 30000})
        if not resp.get("jobComplete", False):
            raise RuntimeError(f"BigQuery query did not complete in time: {sql}")
        names = [f["name"] for f in resp["schema"]["fields"]]
        return [{n: c.get("v") for n, c in zip(names, r["f"])} for r in resp.get("rows", [])]

    def vendor(self, vendor_id):
        r = self._q(f"SELECT * FROM {DATASET}.vendors WHERE vendor_id = @v", v=vendor_id)
        return r[0] if r else None

    def po_lines(self, po_number):
        return self._q(f"SELECT * FROM {DATASET}.purchase_orders WHERE po_number = @po "
                       f"ORDER BY po_line", po=po_number)

    def received(self, po_number, po_line, receipt_type):
        r = self._q(f"SELECT IFNULL(SUM(quantity), 0) AS q FROM {DATASET}.goods_receipts "
                    f"WHERE po_number = @po AND po_line = @ln AND receipt_type = @t",
                    po=po_number, ln=int(po_line), t=receipt_type)
        return int(r[0]["q"])

    def invoiced(self, po_number, po_line):
        r = self._q(f"SELECT IFNULL(SUM(quantity_invoiced), 0) AS q FROM {DATASET}.invoiced_quantities "
                    f"WHERE po_number = @po AND po_line = @ln", po=po_number, ln=int(po_line))
        return int(r[0]["q"])

    def vendor_history(self, vendor_id):
        return self._q(f"SELECT invoice_number, vendor_id, po_number, CAST(invoice_date AS STRING) "
                       f"AS invoice_date, CAST(total AS STRING) AS total, status "
                       f"FROM {DATASET}.invoice_history WHERE vendor_id = @v "
                       f"AND status IN ('POSTED', 'PAID')", v=vendor_id)


    def receipts(self, po_number):
        return self._q(f"SELECT receipt_id, receipt_type, po_number, po_line, quantity, "
                       f"CAST(receipt_date AS STRING) AS receipt_date FROM {DATASET}.goods_receipts "
                       f"WHERE po_number = @po ORDER BY receipt_date", po=po_number)

    def approvals(self, object_id):
        return self._q(f"SELECT approval_id, object_id, approval_type, approver, role, "
                       f"CAST(approval_date AS STRING) AS approval_date, note "
                       f"FROM {DATASET}.approvals_log WHERE object_id = @o", o=object_id)


def get_repo():
    return BigQueryRepo() if os.getenv("INV_DATA", "csv") == "bigquery" else CsvRepo()


def dec(x):
    return Decimal(str(x))
