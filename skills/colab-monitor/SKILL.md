---
name: colab-monitor
description: Set up and use Colab Monitor, the local web dashboard and terminal monitor for the `colab` CLI. Use when the user asks to set up, start, open, or stop a dashboard for their Colab sessions, asks how a Colab job is doing, how long it has left, how many compute units are left or were spent, or what is still running or idle, or wants a job's live output. Also use whenever you run Colab jobs for the user, so their output shows up in the dashboard. Works alongside the colab-operator skill, which creates, runs, and stops the machines.
---

# Skill: Colab Monitor

Set up a local dashboard for the user's Colab sessions in one step. The user watches
`http://localhost:26522` in a browser, and you read the same data with `colab-monitor status --json`.

## Installation

If `command -v colab-monitor` finds nothing, install it with
`uv tool install git+https://github.com/hohieuai/colab-monitor`. The setup block below does this for
you, and it reinstalls the latest version when the installed copy is too old for this skill (one
without the `status` command). Running Colab jobs also needs the `colab` CLI itself
(`uv tool install google-colab-cli`).

## When to activate

- The user asks to set up, start, open, or stop Colab Monitor, or "a dashboard for my Colab jobs".
- The user asks how a Colab job is doing, how many compute units are left, or what is still running.
- You start Colab jobs for the user. Send their output to `~/colab-runs` so the dashboard shows it.
- You are about to finish a task that used Colab. Check that nothing you started is idle or orphaned.

## Works with the colab-operator skill

The `colab` CLI ships the colab-operator skill. When both skills are loaded, split the work:

- **colab-operator changes machines.** Use it to create, run code on, sync files with, and stop
  Colab machines.
- **colab-monitor watches them.** Use it to set up the dashboard and to read compute units, machine
  statuses, logs, and history.

Follow these shared conventions, or the dashboard shows the wrong picture:

- **Name every session** with `-s NAME`, as colab-operator requires, and write its output to
  `~/colab-runs/NAME.log`.
- **Use the same sign-in.** The setup block below picks `--auth adc` when the user has Application
  Default Credentials and no `colab` OAuth token, which matches how colab-operator signs in. If the
  user's `colab` commands pass `--auth`, pass the same value to `colab-monitor`.
- **Pass on isolated state files.** colab-operator isolates agent runs with
  `colab --config FILE`. Colab Monitor reads only the state files it is given, so machines from
  `FILE` would show as orphans. Start it with `--config ~/.config/colab-cli/sessions.json --config FILE`.
  A dashboard that is already running reads only the files it started with: stop it, then start it
  again with every file.
- **Keep isolated state files somewhere durable**, such as `~/.config/colab-cli/agent.json`, rather
  than `/tmp`. If a reboot clears `/tmp` while the machine still runs, nothing records it any more,
  and it really is an orphan.
- **Stop what you start.** colab-operator says to run `colab stop -s NAME` when you finish. Run
  `colab-monitor status` to confirm that nothing you started is still `idle`.

## Mental model (read this first)

- **One local server, two readers.** The user opens `http://localhost:26522`. You run
  `colab-monitor status --json`, which reads the running dashboard. Both show the same data.
- **It works out what Colab doesn't report.** Spend today and over 7 and 30 days, when compute
  units run out, each machine's uptime, idle time and estimated cost per hour, each job's progress,
  time left and latest loss, and a list of what needs attention.
- **Read-only.** Colab Monitor never starts, stops, or connects to a machine. Act on machines with
  the `colab` CLI, for example `colab stop -s NAME`.
- **It runs until stopped.** Always start it in the background. It keeps running after your command
  returns, which is what the user wants: the page stays available.
- **Gentle on Colab.** One background loop asks Colab for compute units and machines once per
  interval (60 seconds by default), however often you or the user read the page. Reading the API is
  free, but its Colab data changes only once per interval.
- **Logs are files.** The **Logs** page shows `.log`, `.out`, and `.err` files directly inside
  `~/colab-runs`. Output you don't redirect there is invisible to the user.
- **One copy per port.** The default port is 26522 ("COLAB" on a phone keypad). Starting a second
  copy prints `Colab Monitor is already running at http://localhost:26522/` and exits with status 0.

## Sign-in (the thing that blocks agents)

- Colab Monitor reuses the `colab` CLI's sign-in: the OAuth token in `~/.config/colab-cli/token.json`
  with `--auth oauth2`, or Application Default Credentials with `--auth adc`.
- If the CLI isn't signed in, the start fails within a second with `Couldn't sign in to Colab`. You
  can't sign in for the user: it opens a browser and waits for a pasted code. Ask the user to run
  `colab sessions` in their terminal (in Claude Code they can type `! colab sessions`), then run the
  setup block again.
- If the user can't sign in now, start with `--no-api`. The **Logs** and **History** pages still
  work, but there are no compute units or machine statuses.

## Workflow

### Set up and open the dashboard

Run this block as written. It is safe to run again: it reuses a dashboard that is already running.

```bash
command -v colab-monitor >/dev/null || uv tool install git+https://github.com/hohieuai/colab-monitor
# An older install has no status command; reinstall the latest if so.
colab-monitor status -h >/dev/null 2>&1 \
  || uv tool install --reinstall git+https://github.com/hohieuai/colab-monitor
mkdir -p ~/colab-runs
API=http://127.0.0.1:26522 URL=http://localhost:26522 OUT="${TMPDIR:-/tmp}/colab-monitor.log"
AUTH=oauth2  # same sign-in as the colab CLI: ADC when there is no colab OAuth token
if [ ! -f ~/.config/colab-cli/token.json ] && { [ -n "${GOOGLE_APPLICATION_CREDENTIALS:-}" ] \
    || [ -f ~/.config/gcloud/application_default_credentials.json ]; }; then AUTH=adc; fi
# A dashboard started before an update has no status report: restart it on the new version.
if curl -sf "$API/api/state" >/dev/null && ! curl -sf "$API/api/state" | grep -q '"insights"'; then
  kill $(lsof -t -iTCP:26522 -sTCP:LISTEN); sleep 1
fi
if ! curl -sf "$API/api/state" >/dev/null; then
  nohup colab-monitor --auth "$AUTH" --log-dir ~/colab-runs < /dev/null > "$OUT" 2>&1 &
  for _ in $(seq 1 40); do curl -sf "$API/api/state" >/dev/null && break; sleep 0.5; done
fi
if curl -sf "$API/api/state" >/dev/null; then
  echo "Colab Monitor is running at $URL"
  (open "$URL" || xdg-open "$URL") >/dev/null 2>&1 || true
else
  cat "$OUT"
fi
```

- If it prints `Colab Monitor is running at http://localhost:26522`, tell the user that address and
  that the dashboard keeps running until they ask you to stop it.
- If it prints the server's output instead, find the message in **Recovery**.
- `< /dev/null` matters: without it, a missing sign-in can wait forever for a code.
- If you isolate runs with `colab --config FILE`, add
  `--config ~/.config/colab-cli/sessions.json --config FILE` to the `nohup colab-monitor` line.
  Don't pass `--config` to `colab-monitor status`: with a data option, `status` reads files itself
  instead of the dashboard.
- Keep the default `--host 127.0.0.1`. Any other address serves the user's logs to their network.

### Run jobs so they appear in the dashboard

- Redirect every job's output to `~/colab-runs`, named after the session:
  `nohup colab run --timeout 86400 --gpu T4 -s train train.py > ~/colab-runs/train.log 2>&1 &`. The name links the
  log to its machine, which is how Colab Monitor notices a running job that has gone silent.
- Print progress the way Colab Monitor reads it: a tqdm bar, `step 900/1800`, or `epoch 3/10`, and
  metrics as `loss=0.25`. Then the report shows the job's progress, time left, and loss.
- Do the same for `colab exec`:
  `colab exec --timeout 86400 -s train -f step.py > ~/colab-runs/train-step.log 2>&1`.
- Always pass `--timeout 86400`, or any value longer than the job, to `colab run` and `colab exec`.
  With the default of 30 seconds, the CLI's local client keeps a CPU core busy for the rest of a
  longer job.
- The file appears on the **Logs** page within 3 seconds and streams while the job runs.

### Check on jobs

`colab-monitor status` prints a summary for the user. For yourself, read the JSON report:

```bash
colab-monitor status --json | python3 -c '
import json, sys
r = json.load(sys.stdin)
c, cu, rw = r["colab"], r["compute_units"], r["runway"]
print("colab check:", "ok" if c["ok"] else "off" if not c["enabled"] else "failing: %s" % c["error"])
print("balance", cu["balance"], "CU, rate", cu["rate_per_hour"], "CU/h, runway",
      "%.1f h" % rw["hours"] if rw["hours"] else "-", "| spent today", r["spend"]["today"])
for m in r["machines"]:
    print("%-9s %-20s %-6s up %-6s idle %-6s %s" % (m["status"], m["name"] or m["endpoint"], m["hardware"],
          round((m["uptime_s"] or 0) / 60), round((m["idle_s"] or 0) / 60), m["job"] or ""))
for j in r["jobs"]:
    if j["session"] or j["stalled"] or j["last_error"]:
        print("job", j["name"], "progress", j["progress"], "eta_s", j["eta_s"], j["metrics"],
              "STALLED" if j["stalled"] else "", j["last_error"] or "")
for a in r["attention"]:
    print("ATTENTION", a["severity"], a["kind"], "-", a["message"])
'
```

| `status` | Meaning | What to do |
|---|---|---|
| `busy` | The CLI is running a command in the machine. | Wait, or read its log. |
| `idle` | The machine runs and bills, but nothing runs in it. | If its work is done, stop it with `colab stop -s NAME`. |
| `stopping` | The CLI stopped it, and the last Colab check still listed it. | Nothing. It disappears after the next check. |
| `orphan` | The machine bills, but the CLI has no record of it. | Tell the user. Release it only with their approval (see **Recovery**). |
| `unknown` | Colab hasn't been checked yet. | Wait one interval and check again. |

- `attention` lists what needs a look, critical first: `orphan`, `runway` (compute units run out
  within 12 hours), `idle` (idle over 30 minutes), `stalled` (a running job's log silent over 15
  minutes), and `failed` (a run failed in the last hour). Report each one to the user.
- `colab-monitor status --exit-code` exits with status 3 when `attention` is not empty, so a script
  can check it without parsing.
- A machine's `rate` with `rate_estimated: true` is an estimate. Say "about" when you report it.
- When `colab.ok` is false and `colab.enabled` is true, the numbers come from the last good check
  at `colab.checked_at`. Say so.
- To read a job's output, `tail ~/colab-runs/NAME.log` is enough.
- `curl -s 'http://127.0.0.1:26522/api/history?session=NAME&limit=20'` lists what the CLI recorded
  in a session, oldest first, with errors.

### Stop the dashboard

Only when the user asks:

```bash
kill $(lsof -t -iTCP:26522 -sTCP:LISTEN)
```

## Safety

- **Never start `colab-monitor` in the foreground.** It serves until stopped, so your shell hangs.
- **Never edit `~/.config/colab-cli`.** Those files belong to the `colab` CLI.
- **Never release an orphan without the user's approval.** It may be someone else's running work.
- **Before you finish a task that used Colab**, run `colab-monitor status` and stop idle machines
  that you started. Idle and orphaned machines keep using compute units.

## Recovery

| Message or symptom | Fix |
|---|---|
| `Couldn't sign in to Colab` | Ask the user to run `colab sessions`, then run the setup block again. Or start with `--no-api`. |
| `Port 26522 is used by another program` | Add `--port 26523` to the start command, use port 26523 in every URL, and pass `--port 26523` to `colab-monitor status`. |
| `curl` can't connect | The dashboard isn't running. Run the setup block. |
| `Not signed in to Colab; showing local files only` from `status` | No dashboard runs and the CLI isn't signed in. Ask the user to run `colab sessions`, or run the setup block, which starts the dashboard. |
| `colab-monitor: error: unrecognized arguments` | The installed copy is older than this skill. Run `uv tool install --reinstall git+https://github.com/hohieuai/colab-monitor`, then the setup block. |
| Your own machines show as `orphan` | You started them with `colab --config FILE`. Stop the dashboard and start it again with `--config ~/.config/colab-cli/sessions.json --config FILE`. |
| A job is missing from the **Logs** page | Its output isn't in a `.log`, `.out`, or `.err` file directly inside `~/colab-runs`. Redirect it there. |
| A machine is `orphan` and the user approves releasing it | `uvx --from google-colab-cli python -c "from colab_cli.common import state; state.client.unassign('ENDPOINT')"`, using the machine's `endpoint`. Then confirm with `colab sessions`. |

More detail: [command-line reference](../../docs/command-line.md) and
[how Colab Monitor works](../../docs/how-it-works.md).
