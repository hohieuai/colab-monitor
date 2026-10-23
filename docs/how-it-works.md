# How Colab Monitor works

Colab Monitor answers three questions about the Colab machines on your account: what they cost,
which ones still run, and what your jobs print. This page explains where each answer comes from and
why the dashboard is built the way it is.

## Where the data comes from

The dashboard combines two local sources with one remote source.

```text
 colab CLI ── writes ──▶ ~/.config/colab-cli/sessions.json and history/*.jsonl
 your jobs ── write ───▶ ~/colab-runs/*.log
                                │  read on every page refresh
 Colab ◀── 2 requests per interval ── Colab Monitor on 127.0.0.1:26522 ◀── your browser
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
- **Stopping** means that the CLI stopped the machine a moment ago, but the last Colab check still
  listed it. The machine disappears after the next check.
- **Orphan** means that Colab lists the machine but the CLI has no record of it. This happens when
  the CLI crashes or uses a different state file. Nothing will stop an orphan for you, so the
  dashboard shows a red notice until you release it.
- **Released** means that the CLI still has a record of a machine that Colab no longer lists.

Without the **Stopping** status, every machine that you stop would show as an orphan for up to one
interval, and the red notice would appear for no reason.

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
- **Running** reflects only commands that the CLI runs. If you open a CLI session in the browser
  with `colab url` and run code there, the dashboard still shows the machine as **Idle**.
