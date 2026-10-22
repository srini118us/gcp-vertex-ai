"""Day 2: create (or reuse) the Document AI Invoice Parser processor.

Billing for the Invoice Parser is per processed document (see the Document AI pricing page).
Reuses an existing processor with the same display name, so reruns never create duplicates.

Run from the lab folder:
    python scripts/create_processor.py
Writes config/processor.json with the processor resource name.
"""
import json
import os

from common import CONFIG, D, PROJECT, call, docai_base

DISPLAY = "invoice-lab-parser"


def main():
    os.makedirs(D("config"), exist_ok=True)
    existing = call("GET", f"{docai_base()}/processors").get("processors", [])
    proc = next((p for p in existing if p.get("displayName") == DISPLAY), None)
    if proc:
        print(f"reusing existing processor {proc['name']}")
    else:
        proc = call("POST", f"{docai_base()}/processors",
                    {"type": "INVOICE_PROCESSOR", "displayName": DISPLAY})
        print(f"created processor {proc['name']}")
    info = {k: proc.get(k) for k in ("name", "type", "displayName", "state",
                                     "defaultProcessorVersion", "processEndpoint")}
    with open(CONFIG, "w", encoding="utf-8") as fh:
        json.dump(info, fh, indent=1)
    print(json.dumps(info, indent=1))
    print(f"console: https://console.cloud.google.com/ai/document-ai/processors?project={PROJECT}")


if __name__ == "__main__":
    main()
