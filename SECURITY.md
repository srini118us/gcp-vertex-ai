# Security notes

All lab data in this repository is synthetic. Credentials never belong in code: each lab reads
them from environment variables or a local `.env` file (ignored by git), and a deployed service
reads them from Secret Manager.

## Incident log

| Date | Finding | Action |
|---|---|---|
| 2026-10-22 | A ServiceNow developer instance admin password was committed in `mcp-incident-manager/config/settings.py` | Password rotated the same day. Settings moved to environment variables with `.env.example`; live mode now fails closed without them and defaults to mock. The old value remains in git history but is no longer valid. History was not rewritten: rotation is the control, and a force push would break every clone for no added protection. |
| 2026-10-22 | The CI secret scan found two Google Cloud API keys (AQ. format) in four `.env` files committed on 2026-04-11 and untracked later, still readable in history | Keys revoked in the owning project. Gitleaks now runs on every pull request over the full history, with a custom rule for this key format and one for literal passwords (the default rules missed the ServiceNow password). Old findings are listed in `.gitleaksignore` only after revocation. |
| 2026-10-22 | A Python virtual environment (`mcp-incident-manager/venv`, 30 MB, 1,692 files) and `__pycache__` files were tracked despite the ignore rules | Removed from the index; the root `.gitignore` already excludes them. |

## Dependency advisories (Dependabot), reviewed 2026-10-22

Fixed by raising versions: google-cloud-aiplatform, scikit-learn, flask, requests, python-dotenv
(root `requirements.txt`); certifi, litellm, mcp, nltk (`late-order-a2a`, `bq-data-agent`).

Accepted, with reason:

| Package | Advisory | Why it stays | Revisit when |
|---|---|---|---|
| opentelemetry-api 1.42.1 | GHSA-xcq7-p3pf-p88h (CVE-2026-114603): quadratic CPU when parsing a crafted inbound W3C `tracestate` header | Every google-adk release up to 2.12.0 requires `opentelemetry-api<=1.42.1`, so the fix (1.45.1) cannot be installed alongside ADK. The labs run locally and do not accept untrusted inbound trace headers. | google-adk lifts the cap; a lab exposes an HTTP endpoint to untrusted callers (then put a load balancer or Cloud Armor header size limit in front). |

Dependabot alerts for accepted items are dismissed as "tolerable risk" with a link to this file.
