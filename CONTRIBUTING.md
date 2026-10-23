# Contributing to Colab Monitor

Thanks for helping. Bug reports, fixes and small focused features are all welcome.

## Before you start

- For anything bigger than a small fix, open an issue first so we can agree on the approach.
- Colab Monitor is deliberately small: a Python standard-library server and a page with no build
  step. Please keep it that way. New runtime dependencies need a strong reason.
- It is read-only by design. It never creates, stops or connects to Colab machines.

## Set up

You need Python 3.12+, [uv](https://docs.astral.sh/uv/) and Chrome (for the browser tests).

```bash
git clone https://github.com/hohieuai/colab-monitor
cd colab-monitor
uv sync
uv run colab-monitor --no-api --open   # runs without a Colab account, local files only
```

To see every state without a Colab account, run the browser tests: they start a dashboard with
fixture data (running, idle, stopping and orphaned machines, logs, history and a usage chart).

## Checks

Run these before opening a pull request. CI runs the same commands.

```bash
uv run ruff format .
uv run ruff check .
uv run pytest                      # unit and browser tests
```

- **Unit tests** (`tests/test_*.py`) cover the server: files it reads, the Colab poller, the
  HTTP API and the command line.
- **Browser tests** (`tests/e2e/`) drive the real page with Playwright, one test per feature, in
  light and dark mode at phone, tablet and desktop widths. They use your installed Chrome, or
  Playwright's Chromium after `uv run playwright install chromium`.

Write the test first, watch it fail, then make it pass. Every bug fix needs a test that would have
caught it.

## Code layout

| Path | What it is |
|---|---|
| `src/colab_monitor/server.py` | HTTP server, routes and the command line |
| `src/colab_monitor/sources.py` | Read-only views of the colab CLI's local files |
| `src/colab_monitor/poller.py` | The only code that calls Colab, with caching and backoff |
| `src/colab_monitor/usage_log.py` | Compute-unit samples kept on disk for the chart |
| `src/colab_monitor/static/` | The page: `index.html`, `app.css`, `app.js` and assets |

## Guidelines

- **Never send secrets to the page.** Session tokens and runtime proxy URLs must be stripped on the
  server; there are tests for this.
- **Be gentle with Colab.** Only `poller.py` may call Colab, and only on its interval.
- **Insert text with `textContent`**, never `innerHTML`, for anything that comes from files or
  Colab. The page runs under a strict Content Security Policy with no inline scripts.
- **UI changes:** check light and dark mode and a phone width, and add a browser test. If the change
  is visible in the README tour, regenerate it with `uv run python scripts/demo_gif.py`.
- Update `CHANGELOG.md` under *Unreleased* for any user-visible change.

## Pull requests

Keep them focused, describe what changed and how you tested it, and include before/after
screenshots for UI changes. By contributing you agree that your contribution is licensed under the
project's [Apache 2.0 license](LICENSE).

Please follow the [Code of Conduct](CODE_OF_CONDUCT.md).
