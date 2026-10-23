<div align="center">

<img src="src/colab_monitor/static/icon.svg" width="72" height="72" alt="">

# Colab Monitor

A local web dashboard for the Colab sessions you run with the `colab` CLI.

[![CI](https://github.com/hohieuai/colab-monitor/actions/workflows/ci.yml/badge.svg)](https://github.com/hohieuai/colab-monitor/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)

<img src="docs/images/demo.gif" width="900" alt="Colab Monitor tour: the Overview page with a usage chart, the Sessions page with three running machines, a training log streaming new lines, and a session's history">

</div>

## What it shows

Colab Monitor reads what the [`colab` CLI](https://pypi.org/project/google-colab-cli/) records on
your computer, asks Colab for your compute units and machines, and shows both on one page.

The page has five sections:

- **Overview** shows your compute-unit balance, the usage rate, how long the balance lasts at that
  rate, and a usage chart for the last hour up to the last 30 days.
- **Sessions** lists every machine on your account with its status: running, idle, stopping,
  orphaned, or released.
- **Logs** streams the output files of your jobs and highlights errors and warnings.
- **History** shows the code, output, and errors that the CLI recorded for each session.
- **Settings** switches between light and dark mode and shows where the data comes from.

Idle and orphaned machines still use compute units, so the dashboard marks them in amber and red.
An orphaned machine runs on your account, but the CLI no longer tracks it, so nothing will stop it
for you.

Colab Monitor is read-only. It never starts, stops, or connects to a machine, and it serves the
page only to your own computer.

## Install and start

Before you start, install Python 3.12 or later and [uv](https://docs.astral.sh/uv/). Then sign in
to the `colab` CLI by running `colab sessions` once. Colab Monitor reuses that sign-in.

1. Install Colab Monitor:

   ```bash
   uv tool install git+https://github.com/hohieuai/colab-monitor
   ```

2. Create the folder that the **Logs** page reads:

   ```bash
   mkdir -p ~/colab-runs
   ```

3. Start the dashboard:

   ```bash
   colab-monitor --open
   ```

   The terminal prints `[colab-monitor] Serving http://localhost:26522/`, and your browser opens
   that address.

To stop the dashboard, press Ctrl-C in its terminal.

## Watch a job's output

To see a job on the **Logs** page, write its output to a file in `~/colab-runs`:

```bash
colab run --gpu T4 -s train train.py > ~/colab-runs/train.log 2>&1
```

The file appears on the **Logs** page within three seconds, and new lines stream in while the job
runs. The page shows files that end in `.log`, `.out`, or `.err`. To read a different folder, start
Colab Monitor with `--log-dir`.

## Documentation

- The [command-line reference](docs/command-line.md) lists every option, the exit codes, the files
  that Colab Monitor reads and writes, and its HTTP API.
- [How Colab Monitor works](docs/how-it-works.md) explains each status, how the dashboard limits
  its requests to Colab, and how it protects your data.
- [Troubleshooting](docs/troubleshooting.md) covers sign-in errors, port conflicts, missing logs,
  and orphaned machines.
- The [agent skill](skills/colab-monitor/SKILL.md) teaches AI coding agents to start Colab Monitor
  and read its API.
- The [security policy](SECURITY.md) explains how to report a vulnerability.
- The [contributing guide](CONTRIBUTING.md) explains how to set up a development copy, run the
  tests, and open a pull request.

## License

Colab Monitor is licensed under the [Apache License 2.0](LICENSE). The bundled Geist fonts use the
[SIL Open Font License](src/colab_monitor/static/fonts/OFL.txt).

Colab Monitor is an unofficial community project and is not affiliated with Colab.
