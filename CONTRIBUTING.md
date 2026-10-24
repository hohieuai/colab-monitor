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

To skip the local setup, open the repository in its dev container, with **Dev Containers: Reopen in
Container** in VS Code or in GitHub Codespaces. The container has Python 3.13, uv, the locked
dependencies, and Chromium for the browser tests, and it forwards the dashboard's port 26522.

Coding agents follow [AGENTS.md](AGENTS.md), which summarizes these steps and the project's rules.

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

If you change how log files are found, checked, or read (`sources.resolve_log`,
`sources.discover_logs`, `sources.tail_lines`, or the `/api/log` route), also run the exhaustive
check of what `/api/log` serves. CI runs it too. It takes about 20 seconds and must print `pass` for
every property:

```bash
uv run python verification/log_access/check.py
```

[verification/log_access/README.md](verification/log_access/README.md) explains what the check
covers, how to tell a real bug from an outdated check, and how to update it.

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

Pull requests are squash-merged, so the title becomes the commit message on `main`. Write the title
in [Conventional Commits](https://www.conventionalcommits.org/) form. A check fails the pull
request otherwise.

| Type | Use it for |
|---|---|
| `feat` | A new feature |
| `fix` | A bug fix |
| `docs` | Documentation only |
| `test` | Tests only |
| `refactor` | A code change that neither fixes a bug nor adds a feature |
| `perf` | A performance improvement |
| `style` | Formatting only |
| `build` | Packaging or dependencies |
| `ci` | GitHub Actions and other CI configuration |
| `chore` | Other maintenance |
| `revert` | Reverting an earlier change |

Start the subject with a lowercase word, use the imperative mood, and leave out the final period:
`fix: handle machines where the colab CLI has never run`. Add a scope in parentheses when it
helps, such as `feat(logs): add a line filter`. Mark a breaking change with `!`, as in
`feat!: require Python 3.13`. After merging, GitHub adds the pull request number:
`fix: handle machines where the colab CLI has never run (#4)`.

Keep pull requests focused, describe what changed and how you tested it, and include before/after
screenshots for UI changes. By contributing you agree that your contribution is licensed under the
project's [Apache 2.0 license](LICENSE). Copyright notices name "The Colab Monitor Authors". To be
listed, add yourself to [AUTHORS](AUTHORS) in your pull request.

Please follow the [Code of Conduct](CODE_OF_CONDUCT.md).
