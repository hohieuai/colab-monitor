# Agent guide

Instructions for coding agents working in this repository. People should start with
[CONTRIBUTING.md](CONTRIBUTING.md), which this guide follows.

## Project

Colab Monitor is a local dashboard and command-line monitor for the Colab sessions that the `colab`
CLI runs. It is a Python 3.12+ package with a standard-library HTTP server and a vanilla JavaScript
page. There is no build step for the front end.

| Path | Contents |
|---|---|
| `src/colab_monitor/` | The package: `cli.py` (commands), `server.py` (HTTP API and `serve`), `sources.py` (local files), `metrics.py` (insights), `poller.py` (Colab requests), `usage_log.py` |
| `src/colab_monitor/static/` | The dashboard page: `index.html`, `app.js`, `app.css`, icons, bundled fonts |
| `tests/` | Unit tests, one file per module, and browser tests in `tests/e2e/` |
| `verification/log_access/` | The exhaustive check of what `/api/log` serves; see its README |
| `skills/colab-monitor/` | The agent skill that users install, packaged by `.claude-plugin/` |
| `docs/` | User documentation: command line, how it works, troubleshooting |

## Commands

```bash
uv sync                                       # install dependencies
uv run ruff format . && uv run ruff check .   # format and lint
uv run pytest --ignore=tests/e2e              # unit tests, about 15 seconds
uv run pytest                                 # everything, including browser tests
uv run python verification/log_access/check.py
```

Browser tests need Chrome or Playwright's Chromium (`uv run playwright install chromium`).

## Rules

- **Test first.** Write a test that fails, then make it pass. Every bug fix needs a test that would
  have caught it.
- **Keep the security promises in [SECURITY.md](SECURITY.md).**
  - Never send access tokens or runtime URLs from the `colab` CLI's state file to the page.
  - Keep the server on `127.0.0.1` by default.
  - Keep the `Host` header check.
  - If you change how log files are found, checked, or read, run the log-access check.
- **Never read `~/.config/colab-cli/colab.log`.** It can contain sign-in tokens.
- **Colab costs money.** Don't start Colab machines from tests. If you start one for manual
  testing, use a CPU runtime, and stop it afterwards. `colab sessions` must show no sessions you
  started.
- **Keep versions in sync.** `.claude-plugin/plugin.json` must have the same version as
  `src/colab_monitor/__init__.py`, and a test checks this.
- **Schema 1 is a contract.** Add fields to `colab-monitor status --json`, but never rename or
  remove one.

## Commits and pull requests

- Use [Conventional Commits](https://www.conventionalcommits.org/) for commit messages and pull
  request titles, for example `fix: handle machines where the colab CLI has never run`.
  Pull requests are squash-merged.
- Don't add `Co-authored-by` lines, "Generated with" lines, or other tool credits to commits or
  pull requests.
- Update `CHANGELOG.md` under Unreleased for user-visible changes, and update the docs in `docs/`
  in the same pull request.
