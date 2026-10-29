# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- The agent skill installs as a Claude Code plugin:
  `/plugin install colab-monitor --marketplace hohieuai/colab-monitor`.
- `colab-monitor status` prints what runs, what it costs, how jobs are doing, and what needs
  attention, then exits. `--json` prints the same report as JSON (schema 1), and `--exit-code`
  exits with status 3 when something needs attention.
- `colab-monitor watch` keeps that summary on screen in the terminal and redraws it every 5
  seconds.
- Numbers that Colab doesn't report: compute units spent today and in the last 7 and 30 days, when
  the balance runs out, each machine's uptime, idle time, and estimated cost per hour, machine hours
  for each kind of hardware, and finished and failed runs.
- Job progress from log files: percentage, time left, speed, the latest metrics such as loss, and
  the last error. A running job whose log goes quiet is marked as stalled.
- A **Needs attention** list on the overview, in `status`, and in `watch`: orphaned machines, a
  balance that runs out soon, idle machines, stalled jobs, and failed runs. `--idle-alert`,
  `--stall-alert`, and `--runway-alert` set the thresholds.
- **Jobs** and **Spending** cards on the overview, and **Uptime** and **Rate** columns on the
  **Sessions** page.
- An agent skill, `skills/colab-monitor/SKILL.md`. Ask a coding agent to "set up Colab Monitor" and
  it installs, starts, and opens the dashboard, sends the output of the Colab jobs it runs to the
  **Logs** page, and checks for idle machines before it finishes. It works alongside the `colab`
  CLI's colab-operator skill.
- `--config` can be repeated, so machines that agents start with `colab --config FILE` no longer
  show as orphans.
- **Machine details:** click a machine on the **Sessions** page or the overview to see its uptime,
  rate, and cost so far, its job's state, loss curve, and latest output, its recent history, and the
  command that stops or releases it. Each machine has its own link, `#/sessions?session=ENDPOINT`.
- Each job has a state: running, stalled, finished, failed, or no new output. A log that ends in an
  error marks its job as failed, needs attention, and links straight to the error line. `status`
  prints `failed` and `finished` next to those jobs, and `status --json` has `jobs[].state`.
- **Loss curves:** the **Logs** page charts every number a job prints, such as `loss` and `acc`, and
  the **Jobs** card shows a small trend line for each job. New endpoint: `/api/metrics`.
- Each item that needs attention links to the machine, the log, or the history, and carries the
  command that deals with it, such as the release command for that orphan, ready to copy. The
  commands sign in the way the dashboard does, so with `--auth adc` they don't wait for an OAuth code. `status
  --json` has `attention[].command`.
- The usage chart marks when each machine started and stopped, and the hover readout names them.
- The tab title and icon show how many things need attention, so a background tab still tells you.
- **Settings** sets the alert thresholds for this browser, and can turn on browser notifications for
  new problems and for jobs that finish or fail.
- **Sessions** has **Idle** and **Cost** columns. Narrower windows show each machine as a card.
- **Logs** lists each file's job state, progress, and machine, and **Go to error** steps through the
  error lines of a log.

### Changed

- `colab-monitor` takes a command: `serve`, `status`, or `watch`. Without one it starts the
  dashboard as before, so existing commands keep working.
- The red orphan banner is now part of the **Needs attention** list. Each orphan carries its own
  release command with its endpoint filled in, instead of one command with an `ENDPOINT` placeholder.
- A running job whose log ends in an error is failed, not stalled.
- A new icon, `[*]`: the mark a notebook shows next to a cell that is running.
- The agent skill reads `colab-monitor status --json` instead of calling the HTTP API.
- Every `colab run` and `colab exec` example, and the agent skill, pass `--timeout 86400`, so the
  CLI waits for long jobs without keeping a CPU core busy.

### Fixed

- Keyboard focus stays on the focused log, session, or job when the page refreshes.
- Switching logs or sessions while one is loading no longer shows the previous one's lines.
- The usage chart's axis labels are distinct for small ranges, such as one CPU machine's rate.
- **Download** on the **Logs** page names the file `NAME-tail.log`, since it holds the lines shown.
- A long progress bar no longer empties the **Logs** page or hides a job's progress once its output
  exceeds the 256 KB read window.
- Session names with spaces or other characters that the `colab` CLI accepts work on the **History**
  and **Overview** pages.
- A machine that Colab still lists 10 minutes after the CLI stopped it shows as an orphan instead of
  staying "Stopping", since it keeps billing.
- Text typed at input prompts, which can be a password, is hidden on the **History** page.
- `--history-dir` accepts `~`.
- The usage log is pruned daily while the dashboard runs, not only at startup.
- The command that releases an orphan works for users who sign in with `--auth adc`.
- `/api/log` reads the same resolved file that it checked, so paths such as `~/colab-runs/a.log` or
  `a.log/` return the file's lines instead of an empty answer.
- A path with a NUL byte gets a 403 answer instead of no answer and a traceback.
- The **Logs** page no longer lists a symlink that leads out of the log folder, which it could not
  open.

## [0.1.0] - 2026-10-24

First release.

### Added

- **Overview:** compute-unit balance, usage rate, runway at the current rate, machines on your
  account, a usage chart (usage rate or balance over 1 hour, 24 hours, 7 days or 30 days, with
  hover details and a table view), active machines and recent activity.
- **Sessions:** every machine on your account with its status (running, idle, stopping, orphan or
  released), hardware, current job and last run, with status filters and search. Shown as cards on
  phones.
- **Logs:** live output from job log files with line numbers, error and warning highlighting,
  filtering, follow mode, copy and download. Progress bars collapse to their latest state and
  terminal colour codes are removed.
- **History:** a timeline of what the colab CLI recorded for each session: code, output, images
  and errors.
- **Settings:** light, dark or system theme, and connection and data-source details.
- Warnings for orphaned machines and for failed Colab checks, with the last good data kept on screen.
- At most two Colab requests per interval however many tabs are open, with backoff on errors.
- `colab-monitor` command with `--port`, `--interval`, `--log`, `--log-dir`, `--auth`, `--no-api`,
  `--open` and `--version`. Opens the running dashboard if it's already started.
- Security: local-only by default, DNS-rebinding guard, tokens never sent to the browser, strict
  Content Security Policy, bundled fonts (no third-party requests).
- Documentation: a command-line reference, an explanation of how the dashboard works, and a
  troubleshooting guide.

[Unreleased]: https://github.com/hohieuai/colab-monitor/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/hohieuai/colab-monitor/releases/tag/v0.1.0
