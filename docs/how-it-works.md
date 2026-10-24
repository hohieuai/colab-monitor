# How Colab Monitor works

Colab Monitor answers three questions about the Colab machines on your account: what they cost,
which ones still run, and what your jobs print. The web dashboard and the `status` and `watch`
commands give the same answers. This page explains where each answer comes from, how far you can
trust it, and why the dashboard is built the way it is.

## Where the data comes from

The dashboard combines two local sources with one remote source.

```text
 colab CLI ── writes ──▶ ~/.config/colab-cli/sessions.json and history/*.jsonl
 your jobs ── write ───▶ ~/colab-runs/*.log
                                │  read on every page refresh
 Colab ◀── 2 requests per interval ── Colab Monitor on 127.0.0.1:26522 ◀── your browser
                                                                        ◀── colab-monitor status
```

The `colab` CLI keeps a state file with the sessions it started, and a history file for each
session. Your jobs write their output to log files when you redirect it. Colab itself knows your
compute-unit balance, the usage rate, and every machine on your account. Colab Monitor reads the
local files on every page refresh and asks Colab on a fixed interval.

## What each status means

A machine's status comes from comparing Colab's list of machines with the CLI's state file.

- **Running** means that Colab lists the machine and the CLI is running a command in it, such as
  `colab run` or `colab exec`.
- **Idle** means that Colab lists the machine and the CLI knows it, but nothing runs in it. An idle
  machine still uses compute units.
- **Stopping** means that the CLI stopped the machine in the last 10 minutes, but the last Colab
  check still listed it. The machine usually disappears after the next check. If Colab still lists
  it 10 minutes after the stop, it shows as an **Orphan**, because the CLI records a stop even when
  Colab refused to release the machine, and that machine keeps billing.
- **Orphan** means that Colab lists the machine but the CLI has no record of it. This happens when
  the CLI crashes or uses a different state file. Nothing will stop an orphan for you, so the
  dashboard shows a red notice until you release it.
- **Released** means that the CLI still has a record of a machine that Colab no longer lists.

Without the **Stopping** status, every machine that you stop would show as an orphan for up to one
interval, and the red notice would appear for no reason.

## What you spent

Colab reports only the current balance, not what you spent. Colab Monitor works spend out from the
usage samples that it saves after every check. It adds up each drop in the balance between two
samples. A rise, such as a top-up, is skipped instead of being subtracted.

Spend therefore covers only the time that Colab Monitor was running. A gap in the samples hides what
was spent during it, and the **Spending** card says when the oldest sample was taken. "Today" starts
at local midnight.

## How long your compute units last

The runway is the balance divided by the current usage rate, and the time it runs out is now plus
the runway. The rate changes whenever a machine starts or stops, so the runway is a forecast for the
machines that run now, not for your plans. When nothing uses compute units, there is no runway.

## What a machine costs

Colab reports one usage rate for the whole account. When only one machine runs, that machine uses
the whole rate, and the dashboard shows the rate without a mark.

With several machines, Colab Monitor estimates each machine's rate and marks it with `≈`. It looks
at the two usage samples around the time the machine started. The rise in the account's rate between
them is the machine's rate. For example, if the rate went from 1.76 to 13.53 an hour while an A100
started, the A100 uses about 11.77 an hour. One machine whose start was not seen, such as an orphan,
gets what is left of the current rate.

The estimate is left blank when it would be a guess:

- No sample was taken within 15 minutes of the start, for example because the dashboard was off.
- Two machines started between the same two samples, so the rise cannot be split.
- Two or more machines have no estimate, so the rest of the rate cannot be split either.

A machine's cost is its rate times its uptime, and its idle cost is its rate times its idle time.
Both are estimates whenever the rate is.

## How long a machine has run and idled

Uptime counts from the `session_created` event in the CLI's history. Idle time counts from the end
of the last command that the CLI ran in the machine, or from its start if it has run nothing. A
machine that runs a command has no idle time. An orphan has no history, so its uptime is unknown.

Machine hours add up, for each kind of hardware, the time each session ran in the last 7 days, from
its start to its end or to now. Run counts come from the code runs in the CLI's history. A run fails
when its output has an error. A script that ends with `sys.exit()` or `sys.exit(0)` succeeded, as the
`colab` CLI also treats it.

## What a job's log tells the dashboard

Colab Monitor reads the last 200 lines of each log file:

- **Progress** comes from the last progress line: a tqdm bar such as `45/100 [00:30<00:37, 1.5it/s]`,
  or `step 900/1800`, or `epoch 3/10`. A tqdm bar also gives the time left and the speed. For a
  `step` or `epoch` line, the time left comes from the steps left and the speed on the line.
- **Metrics** are the latest numbers written as `name=value`, `name: value`, a quoted key as in
  Hugging Face's `{'loss': 0.41}` or JSON, or a known name such as `loss 0.25`. Counters like `step`
  and `epoch`, one-letter names, numbers with a unit such as `15.2GB`, percentages, and lines with
  an error are skipped. At most 8 metrics are kept.
- **Last error** is the last line with a Python exception such as `ValueError:`, a traceback,
  `out of memory`, or a line that starts with `error`, `fatal`, or `failed`. Metric names such as
  `val_error` don't count.

A log belongs to a machine when its name, without the extension, is the machine's session name or
starts with it followed by `-`, `_`, or `.`. For example, `train-gpu.log` and `train-gpu-run2.log`
belong to `train-gpu`. A job is **stalled** when its machine runs a command and the log has not
changed for longer than the stall threshold. Only the machine's newest log can be stalled, because
older logs with the same session name come from earlier runs. A stalled job often means a hung process, but a job
that prints rarely, such as a long evaluation, looks the same.

## When something needs attention

The overview, `status`, and `watch` list the same items, critical ones first:

| Item | Severity | When |
|---|---|---|
| Orphan | Critical | Colab lists a machine that the CLI has no record of. |
| Runway | Critical | Compute units run out sooner than the runway threshold, 12 hours by default. |
| Idle | Warning | A machine has been idle longer than the idle threshold, 30 minutes by default. |
| Stalled | Warning | A running job's log has been silent longer than the stall threshold, 15 minutes by default. |
| Failed | Warning | A run failed in the last hour. |

The [command-line reference](command-line.md#alert-options) shows how to change the thresholds.

## Why requests to Colab are limited

Colab does not publish rate limits, so the dashboard asks for as little as possible. One background
loop sends two requests per interval, `GET /tun/m/ccu-info` for the balance and the usage rate and
`GET /tun/m/assignments` for the machines. The number of open tabs makes no difference, because the
page only talks to the local server.

When a check fails, the loop doubles the wait, up to 10 minutes, and the page keeps the last good
numbers on screen with a notice. One successful check resets the wait.

The default interval is 60 seconds and the minimum is 30. Colab measures usage in compute units
per hour, so a minute between checks hides little, and a shorter interval would only add load on
Colab.

## How the usage chart gets its data

Each successful check appends one sample to `~/.config/colab-monitor/usage.jsonl`. The chart
therefore covers only the time that Colab Monitor was running. Where no sample exists for more
than three intervals or five minutes, whichever is longer, the chart leaves a gap instead of drawing
a line across the missing time.

The usage rate holds steady between checks, so the chart draws it as steps. Colab updates the
balance less often than the rate, so the balance line can stay flat for some minutes after a
machine starts.

## Why it is read-only and local

A dashboard that can stop machines needs a confirmation flow, an audit trail, and stronger
protection against a page in another tab sending requests to it. Colab Monitor leaves those actions
to the CLI, which already has them, and only reads.

The server listens on `127.0.0.1` by default and refuses requests whose `Host` header is not local.
That check stops a malicious website from reading your logs through DNS rebinding. Access tokens and
runtime URLs from the CLI's state file never reach the page. The page loads nothing from other
sites and runs under a strict Content Security Policy. [SECURITY.md](../SECURITY.md) lists every
protection.

## Limits

- The CLI writes a session's history when a command finishes, so a long `colab run` shows its live
  output only through a log file.
- Per-machine rates, costs, and spend are worked out on your computer from Colab's account totals,
  so they can differ from Colab's own billing by a few hundredths of a unit.
- **Running** reflects only commands that the CLI runs. If you open a CLI session in the browser
  with `colab url` and run code there, the dashboard still shows the machine as **Idle**.
