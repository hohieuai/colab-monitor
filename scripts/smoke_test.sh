#!/usr/bin/env bash
# Install a built wheel into a fresh virtualenv and check the installed app really serves its page.
# Usage: scripts/smoke_test.sh dist/colab_monitor-*.whl
set -euo pipefail

wheel="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
work="$(mktemp -d)"
trap 'if [[ -n "${pid:-}" ]]; then kill "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true; fi; rm -rf "$work"' EXIT
cd "$work"  # outside the repo, so nothing is imported from the source tree

uv venv -q .venv
uv pip install -q --python .venv/bin/python "$wheel"
.venv/bin/colab-monitor --version

port=$(.venv/bin/python -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')
.venv/bin/colab-monitor --no-api --port "$port" --usage-log "$work/usage.jsonl" --log-dir "$work" &
pid=$!

base="http://127.0.0.1:$port"
for _ in $(seq 1 50); do curl -sf "$base/" >/dev/null && break; sleep 0.2; done

for path in / /app.css /app.js /theme.js /favicon.svg /icon.svg /apple-touch-icon.png \
            /fonts/Geist-Variable.woff2 /fonts/GeistMono-Variable.woff2 /api/state; do
  code=$(curl -s -o /dev/null -w '%{http_code}' "$base$path")
  if [[ "$code" != 200 ]]; then
    echo "FAIL $path -> $code" >&2
    exit 1
  fi
  echo "ok   $path"
done
curl -sf "$base/api/state" | .venv/bin/python -c 'import json, sys; assert json.load(sys.stdin)["config"]["api_enabled"] is False'
.venv/bin/colab-monitor status --port "$port" --json \
  | .venv/bin/python -c 'import json, sys; r = json.load(sys.stdin); assert r["schema"] == 1 and r["source"] == "dashboard"'
echo "ok   status (from the dashboard)"
.venv/bin/colab-monitor status --no-api --usage-log "$work/usage.jsonl" --log-dir "$work" >/dev/null
echo "ok   status (files only)"
echo "Smoke test passed"
