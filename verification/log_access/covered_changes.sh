#!/usr/bin/env bash
# List the commits since SYNC_COMMIT that changed code covered by check.py.
# Usage: verification/log_access/covered_changes.sh SYNC_COMMIT
# No output means the covered code is unchanged since SYNC_COMMIT.
set -euo pipefail

sync=${1:?usage: covered_changes.sh SYNC_COMMIT}
sources=src/colab_monitor/sources.py
server=src/colab_monitor/server.py

if [ "$(git rev-list --count "$sync..HEAD")" -eq 0 ]; then
  exit 0
fi
{
  # git log -L follows changes inside a function's body, which a grep of the diff can miss.
  for function in resolve_log discover_logs _log_entry tail_lines; do
    git log --format="%h %s" -s "$sync..HEAD" -L ":${function}:${sources}"
  done
  # Dashboard._log is a method, so it is tracked by its line range.
  git log --format="%h %s" -s "$sync..HEAD" -L "/def _log/,/def _history/:${server}"
  git log --format="%h %s" "$sync..HEAD" -G 'LOG_SUFFIXES|/api/log' -- "$sources" "$server"
} | sort -u
