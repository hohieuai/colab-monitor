# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- An agent skill, `skills/colab-monitor/SKILL.md`, that teaches AI coding agents to start Colab
  Monitor in the background and read its API.

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
