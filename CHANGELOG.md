# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

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

### Changed

- `colab-monitor` takes a command: `serve`, `status`, or `watch`. Without one it starts the
  dashboard as before, so existing commands keep working.
- The red orphan banner is now part of the **Needs attention** list, which keeps the command that
  releases an orphan.
- A new icon, `[*]`: the mark a notebook shows next to a cell that is running.
- The agent skill reads `colab-monitor status --json` instead of calling the HTTP API.

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
