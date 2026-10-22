"""Create the Vertex AI Search data store for the AP policy pack and import the documents.

Steps (idempotent, reruns are safe):
  1. bucket gs://<project>-invoice-lab, upload policies/*.md as .txt (unstructured import
     accepts txt, html and pdf)
  2. data store "invoice-policies" (generic, search, content required) in location global
  3. import from the bucket with reconciliation FULL, then wait for the operation
  4. one test query

Run from the lab folder, after:
    gcloud services enable discoveryengine.googleapis.com storage.googleapis.com --project geap-ai-usecases-494501
    python scripts/setup_policy_search.py
Then use it with INV_POLICY_SEARCH=vertex. Indexing can take a few minutes after the import.
Search queries fall under the Vertex AI Search free monthly quota and the GenAI App Builder credit.
"""
import os
import shutil
import subprocess
import tempfile
import time

from common import D, PROJECT, call

STORE = os.getenv("INV_POLICY_STORE", "invoice-policies")
BUCKET = f"{PROJECT}-invoice-lab"
BASE = (f"https://discoveryengine.googleapis.com/v1/projects/{PROJECT}/locations/global/"
        f"collections/default_collection")


def sh(cmd):
    print("  $", " ".join(cmd))
    return subprocess.run(cmd, shell=(os.name == "nt"), capture_output=True, text=True)


def main():
    r = sh(["gcloud", "storage", "buckets", "describe", f"gs://{BUCKET}", f"--project={PROJECT}"])
    if r.returncode != 0:
        r = sh(["gcloud", "storage", "buckets", "create", f"gs://{BUCKET}", f"--project={PROJECT}",
                "--location=US", "--uniform-bucket-level-access"])
        if r.returncode != 0:
            raise SystemExit(r.stderr)
    tmp = tempfile.mkdtemp()
    for fn in os.listdir(D("policies")):
        if fn.endswith(".md"):
            shutil.copy(D("policies", fn), os.path.join(tmp, fn[:-3] + ".txt"))
    r = sh(["gcloud", "storage", "cp", os.path.join(tmp, "*.txt"), f"gs://{BUCKET}/policies/",
            f"--project={PROJECT}"])
    if r.returncode != 0:
        raise SystemExit(r.stderr)
    shutil.rmtree(tmp)

    stores = call("GET", f"{BASE}/dataStores").get("dataStores", [])
    if not any(s["name"].endswith(f"/dataStores/{STORE}") for s in stores):
        op = call("POST", f"{BASE}/dataStores?dataStoreId={STORE}",
                  {"displayName": STORE, "industryVertical": "GENERIC",
                   "solutionTypes": ["SOLUTION_TYPE_SEARCH"], "contentConfig": "CONTENT_REQUIRED"})
        print(f"creating data store: {op.get('name')}")
        time.sleep(15)
    else:
        print(f"data store {STORE} exists")

    op = call("POST", f"{BASE}/dataStores/{STORE}/branches/default_branch/documents:import",
              {"gcsSource": {"inputUris": [f"gs://{BUCKET}/policies/*.txt"], "dataSchema": "content"},
               "reconciliationMode": "FULL"})
    name = op["name"]
    print(f"import started: {name}")
    for _ in range(60):
        st = call("GET", f"https://discoveryengine.googleapis.com/v1/{name}")
        if st.get("done"):
            print("import done:", st.get("metadata", {}), st.get("error", ""))
            break
        time.sleep(10)
    else:
        print("import still running, check the console before searching")

    url = f"{BASE}/dataStores/{STORE}/servingConfigs/default_search:search"
    for attempt in range(6):
        resp = call("POST", url, {"query": "price tolerance for invoice lines", "pageSize": 3})
        links = [(x.get("document", {}).get("derivedStructData", {}) or {}).get("link")
                 for x in resp.get("results", [])]
        if links:
            print("test query results:", links)
            break
        print("index not ready yet, waiting 30s")
        time.sleep(30)
    print(f"console: https://console.cloud.google.com/gen-app-builder/data-stores?project={PROJECT}")


if __name__ == "__main__":
    main()
