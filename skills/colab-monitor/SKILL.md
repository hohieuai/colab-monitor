---
name: colab-monitor
description: Run and query Colab Monitor, the local dashboard for Colab sessions started with the `colab` CLI. Use when asked to watch a Colab job, check compute units or the usage rate, find idle or orphaned machines that still bill, tail a job's log while it runs, or report on recent Colab sessions. Reads a local JSON API, so it adds no requests to Colab.
---

# Colab Monitor

Colab Monitor is a local web server that combines the `colab` CLI's local state, your job logs, and
two cached Colab requests per interval. People use its web page. You use its JSON API on
`http://127.0.0.1:26522`.

It is read-only. It never starts, stops, or connects to a Colab machine. To act on a machine, use
the `colab` CLI.

## When to use this skill

- The user asks how a Colab job is doing, or wants its latest output.
- The user asks how many compute units are left, or how fast they are being used.
- You need to check that no machine is idle or orphaned before you finish a task.
- The user wants a summary of recent Colab sessions.

## Install and check the version

```bash
uv tool install git+https://github.com/hohieuai/colab-monitor
colab-monitor --version
```

The dashboard reuses the `colab` CLI's sign-in. If the CLI has never signed in, a person must run
`colab sessions` once in a terminal, because sign-in opens a browser and waits for a pasted code.
You can't complete it from a non-interactive shell.

## Start the dashboard without blocking your shell

Check whether it already runs:

```bash
curl -sf http://127.0.0.1:26522/api/state >/dev/null && echo running || echo stopped
```

If it is stopped, start it in the background, save its process ID, and wait until it answers:

```bash
mkdir -p ~/colab-runs
nohup colab-monitor --log-dir ~/colab-runs > "${TMPDIR:-/tmp}/colab-monitor.log" 2>&1 &
echo $! > "${TMPDIR:-/tmp}/colab-monitor.pid"
for _ in $(seq 1 40); do curl -sf http://127.0.0.1:26522/api/state >/dev/null && break; sleep 0.5; done
curl -sf http://127.0.0.1:26522/api/state >/dev/null && echo ready || cat "${TMPDIR:-/tmp}/colab-monitor.log"
```

- Never start `colab-monitor` in the foreground. It serves until it is stopped, so your shell would
  hang.
- If the log says `Couldn't sign in to Colab`, ask the user to run `colab sessions`, or restart with
  `--no-api` to read local files only.
- If the log says `Colab Monitor is already running`, another copy serves the port. Use it.
- Keep the default `--host 127.0.0.1`. Any other address serves the user's logs to the network.

## Send job output where the dashboard reads it

Redirect each job's output to a file in `~/colab-runs`. Run long jobs in the background:

```bash
nohup colab run --gpu T4 -s train train.py > ~/colab-runs/train.log 2>&1 &
```

The dashboard shows `.log`, `.out`, and `.err` files that sit directly in `~/colab-runs`.

## Read the state

`/api/state` returns everything at once. This summary prints the account and one line per machine:

```bash
curl -s http://127.0.0.1:26522/api/state | python3 -c '
import json, sys
s = json.load(sys.stdin)
api, u = s["api"], s["api"]["usage"] or {}
print("colab check:", "failing: " + api["error"] if api.get("error") else "ok, at " + str(api.get("updated_at")))
print("balance %.2f CU, rate %.2f CU/h" % (u.get("balance", 0), u.get("rate_per_hour", 0)))
for m in s["sessions"]:
    print("%-9s %-20s %-5s %-18s %s" % (m["status"], m.get("name") or "(no name)",
          m.get("accelerator"), m.get("running") or "", m["endpoint"]))
'
```

Act on each status like this:

| `status` | Meaning | What to do |
|---|---|---|
| `busy` | The CLI is running a command in the machine. | Wait, or read its log. |
| `idle` | The machine runs and bills, but nothing runs in it. | If the work is done, stop it with `colab stop -s NAME`. |
| `stopping` | The CLI stopped it, and the last Colab check still listed it. | Nothing. It disappears after the next check. |
| `orphan` | The machine bills, but the CLI has no record of it. | Tell the user. Release it only with their approval, as shown in Recovery. |
| `gone` | The CLI has a record, but Colab no longer lists the machine. | Nothing. The CLI prunes the record on its next run. |
| `unknown` | Colab has not been checked yet. | Wait one interval and read again. |

When `api.error` is not null, the numbers come from the last successful check at `api.updated_at`.
Report them as stale.

## Read a log or a session's history

You can read a log file directly with `tail`. The API returns the same lines with terminal colour
codes removed and progress bars collapsed to their final state:

```bash
LOG=~/colab-runs/train.log
curl -s "http://127.0.0.1:26522/api/log?lines=40&path=$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1]))' "$LOG")" \
  | python3 -c 'import json, sys; print("\n".join(json.load(sys.stdin)["lines"]))'
```

The path must be a file passed with `--log`, or a `.log`, `.out`, or `.err` file directly inside a
`--log-dir` folder. Any other path returns `403`.

For what the CLI recorded in a session, read its history. Events come oldest first:

```bash
curl -s "http://127.0.0.1:26522/api/history?session=train&limit=20" | python3 -c '
import json, sys
for e in json.load(sys.stdin)["events"]:
    print(e["timestamp"], e["type"], e.get("error") or "")
'
```

`/api/activity?limit=20` returns the latest events across all sessions, newest first.
`/api/usage?range=24h` returns usage-rate and balance samples for `1h`, `24h`, `7d`, or `30d`.

## Safety

- Read the API at most every few seconds. It answers from local files and a cache, but the
  dashboard checks Colab only once per interval, 60 seconds by default, so faster reads show nothing
  new.
- Never edit files in `~/.config/colab-cli`. They belong to the `colab` CLI.
- Before you finish a task that started Colab machines, read `/api/state` and confirm that no
  machine you started is `idle` or `orphan`.
- If you started the dashboard, stop it when the user no longer needs it:
  `kill "$(cat "${TMPDIR:-/tmp}/colab-monitor.pid")"`.

## Recovery

| Problem | Fix |
|---|---|
| `curl` cannot connect | The dashboard is not running. Start it as shown above. |
| `Port 26522 is used by another program` | Start it with `--port 26523` and use that port in every URL. |
| `Couldn't sign in to Colab` | Ask the user to run `colab sessions`, or start with `--no-api`. |
| A log file is missing from `/api/state` | Move the output into `~/colab-runs`, or restart with `--log FILE`. |
| A machine is `orphan` | With the user's approval, release it, replacing `ENDPOINT` with the machine's `endpoint`: `uvx --from google-colab-cli python -c "from colab_cli.common import state; state.client.unassign('ENDPOINT')"`. Then confirm with `colab sessions`. |

More detail: [command-line reference](../../docs/command-line.md) and
[how Colab Monitor works](../../docs/how-it-works.md).
