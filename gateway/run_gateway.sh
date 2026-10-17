#!/usr/bin/env bash
set -Eeuo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
UPSTREAM="${H3_SGLANG_URL:-http://127.0.0.1:30010}"

if [[ -z "${H3_ADMIN_KEY:-}" ]]; then
  echo "H3_ADMIN_KEY must be set" >&2
  exit 2
fi
if [[ "${H3_EMAIL_VERIFICATION_REQUIRED:-1}" == "1" ]] && { [[ -z "${SMTP_HOST:-}" ]] || [[ -z "${SMTP_FROM:-}" ]]; }; then
  echo "SMTP_HOST and SMTP_FROM must be set for email registration" >&2
  exit 2
fi

"${PYTHON_BIN}" - <<'PY'
import os, urllib.request
configured = os.environ.get("H3_SGLANG_URLS", "")
urls = [item.strip().rstrip("/") for item in configured.split(",") if item.strip()]
if not urls:
    urls = [os.environ.get("H3_SGLANG_URL", "http://127.0.0.1:30010").rstrip("/")]
failures = []
for base in urls:
    try:
        with urllib.request.urlopen(base + "/health", timeout=5) as response:
            if response.status != 200:
                failures.append(f"{base}: HTTP {response.status}")
    except Exception as exc:
        failures.append(f"{base}: {exc}")
if len(failures) == len(urls):
    raise SystemExit("no model upstream is healthy: " + "; ".join(failures))
if failures:
    print("warning: unhealthy model upstreams: " + "; ".join(failures), file=__import__("sys").stderr)
PY

mkdir -p "${H3_GATEWAY_DATA_DIR:-/code/minimax-h3-gateway}"
export H3_GATEWAY_DB="${H3_GATEWAY_DB:-${H3_GATEWAY_DATA_DIR:-/code/minimax-h3-gateway}/data.sqlite3}"
cd "${BASE_DIR}"
exec "${PYTHON_BIN}" -m uvicorn app:app --host "${H3_GATEWAY_HOST:-0.0.0.0}" --port "${H3_GATEWAY_PORT:-8080}" --workers 1
