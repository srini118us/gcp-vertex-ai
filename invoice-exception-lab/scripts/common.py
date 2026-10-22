"""Shared helpers: project settings, gcloud token, REST calls with retries.

Lessons carried from the RAG lab: fresh token per call (a run can outlive one token), back off
on 429, retry transient network errors, and never swallow an error silently.
"""
import json
import os
import subprocess
import time
import urllib.error
import urllib.request

PROJECT = os.getenv("INV_PROJECT", "geap-ai-usecases-494501")
DOCAI_LOCATION = os.getenv("INV_DOCAI_LOCATION", "us")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = lambda *p: os.path.join(ROOT, *p)
CONFIG = D("config", "processor.json")


def token():
    return subprocess.check_output(["gcloud", "auth", "print-access-token"], text=True,
                                   shell=(os.name == "nt")).strip()


def call(method, url, body=None, retries=5, timeout=120):
    data = json.dumps(body).encode() if body is not None else None
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": f"Bearer {token()}",
            "Content-Type": "application/json",
            "X-Goog-User-Project": PROJECT,
        })
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:600]
            if e.code in (429, 500, 503) and attempt < retries - 1:
                wait = 20 * (attempt + 1)
                print(f"    HTTP {e.code}, retrying in {wait}s")
                time.sleep(wait)
                continue
            raise RuntimeError(f"HTTP {e.code} {method} {url}\n{detail}") from None
        except OSError as e:
            if attempt < retries - 1:
                time.sleep(5 * (attempt + 1))
                continue
            raise RuntimeError(f"network error {method} {url}: {e}") from None


def docai_base():
    return (f"https://{DOCAI_LOCATION}-documentai.googleapis.com/v1/projects/{PROJECT}"
            f"/locations/{DOCAI_LOCATION}")


def processor_name():
    if not os.path.exists(CONFIG):
        raise SystemExit("config/processor.json not found, run scripts/create_processor.py first")
    with open(CONFIG, encoding="utf-8") as fh:
        return json.load(fh)["name"]
