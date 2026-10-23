# Command-line reference

## Synopsis

```text
colab-monitor [serve] [SERVE OPTIONS] [DATA OPTIONS] [ALERT OPTIONS]
colab-monitor status  [--json] [--exit-code] [--no-color] [--host HOST] [--port PORT] [DATA OPTIONS] [ALERT OPTIONS]
colab-monitor watch   [--refresh SECONDS] [--no-color] [--host HOST] [--port PORT] [DATA OPTIONS] [ALERT OPTIONS]
colab-monitor --help
```

## Commands

| Command | Description |
|---|---|
| `serve` | Starts the web dashboard. This is the default, so `colab-monitor` and `colab-monitor --port 9000` start the dashboard too. |
| `status` | Prints the machines, compute units, spend, jobs, and the items that need attention, then exits. |
| `watch` | Shows the `status` summary in the terminal and redraws it every few seconds. Press `q` or Ctrl-C to quit. |

`colab-monitor COMMAND -h` prints the options of one command.

## Where status and watch get their data

`status` and `watch` first ask a running dashboard at `--host` and `--port` for its data. A
dashboard answers with the same numbers that its page shows, and no extra request goes to Colab.

If no dashboard answers, or if you pass `--log`, `--log-dir`, `--config`, `--history-dir`,
`--usage-log`, or `--no-api`, the command reads the files itself. Those options choose files that a
running dashboard may not read, so the command skips the dashboard. In that case the command also checks Colab with the sign-in that the `colab` CLI
saved. It never starts a sign-in. Without a saved sign-in, it prints a note to standard error and
shows local files only. `watch` repeats the Colab check every 60 seconds.

The `source` field of `status --json` says which way the data came: `dashboard` or `direct`.

## Data options

All three commands take these options.

| Option | Default | Description |
|---|---|---|
| `--log FILE` | none | A log file to show. Repeat the option to show more files. |
| `--log-dir DIR` | `~/colab-runs` | A folder whose `.log`, `.out`, and `.err` files are shown. Subfolders are not read. Repeat the option to read more folders. Any `--log-dir` replaces the default. |
| `--config FILE` | `~/.config/colab-cli/sessions.json` | A session state file of the `colab` CLI. Repeat the option to read several files, for example the default file and each file passed to `colab --config`. A machine listed in more than one file is shown once. Any `--config` replaces the default. |
| `--history-dir DIR` | `~/.config/colab-cli/history` | The history folder of the `colab` CLI. |
| `--auth {oauth2,adc}` | `oauth2` | Sign-in method. Same as `colab --auth`. |
| `-c FILE`, `--client-oauth-config FILE` | `~/.colab-cli-oauth-config.json` | OAuth client configuration. Same as `colab -c`. |
| `--usage-log FILE` | `~/.config/colab-monitor/usage.jsonl` | File that keeps the usage samples for the chart and the spend figures. |
| `--no-api` | off | Never contact Colab. Only local files are shown. |

## Alert options

These options set when something counts as needing attention. All three commands take them. Each
value must be a positive number.

| Option | Default | An item needs attention when |
|---|---|---|
| `--idle-alert MINUTES` | `30` | A machine has been idle for this long. |
| `--stall-alert MINUTES` | `15` | A running machine's job log has printed nothing for this long. |
| `--runway-alert HOURS` | `12` | Compute units run out within this time at the current usage rate. |

An orphaned machine and a run that failed in the last hour always need attention.

## Serve options

| Option | Default | Description |
|---|---|---|
| `--host HOST` | `127.0.0.1` | Address to listen on. Any address that is not a loopback address prints a warning, because anyone who can reach the port can read your logs. |
| `--port PORT` | `26522` | Port to listen on. If another Colab Monitor already listens on this port, the command prints its address, opens it when `--open` is set, and exits with status 0. |
| `--interval SECONDS` | `60` | Seconds between Colab checks. The minimum is 30. |
| `--open` | off | Open the dashboard in the default browser. |
| `--version` | | Print the version and exit. |

## Status and watch options

| Option | Commands | Default | Description |
|---|---|---|---|
| `--host HOST` | both | `127.0.0.1` | Where to look for a running dashboard. |
| `--port PORT` | both | `26522` | Port of a running dashboard. |
| `--json` | `status` | off | Print the report as JSON. See [The status report](#the-status-report). |
| `--exit-code` | `status` | off | Exit with status 3 when anything needs attention. |
| `--refresh SECONDS` | `watch` | `5` | Seconds between redraws. The minimum is 1. |
| `--no-color` | both | off | Print without colour. Colour is also off when the output is not a terminal, when `NO_COLOR` is set, or when `TERM` is `dumb`. |

## Exit status

| Status | Meaning |
|---|---|
| `0` | The command finished. For `serve`, the server stopped after Ctrl-C, or another Colab Monitor already serves the port. |
| `1` | `serve` only: another program uses the port, the address cannot be used, or sign-in to Colab failed. |
| `2` | An option or the command name is invalid, or `watch` runs without a terminal. |
| `3` | `status --exit-code` only: at least one item needs attention. |

## The status report

`colab-monitor status --json` prints one JSON object. The `schema` field is `1`. Later versions of
schema 1 may add fields but never rename or remove one. Times are Unix seconds unless the field
says otherwise, and every value that Colab Monitor cannot work out is `null`.

| Field | Type | Contents |
|---|---|---|
| `schema` | number | `1`. |
| `source` | string | `dashboard` or `direct`. See [Where status and watch get their data](#where-status-and-watch-get-their-data). |
| `generated_at` | string | When the report was made, in ISO 8601. |
| `colab.enabled` | boolean | `false` when Colab is not checked, because of `--no-api` or a missing sign-in. |
| `colab.ok` | boolean | `true` when the last Colab check succeeded. |
| `colab.error` | string | The error of the last failed check. |
| `colab.checked_at` | string | When the last successful check ran, in ISO 8601. |
| `compute_units.balance` | number | The compute-unit balance. |
| `compute_units.rate_per_hour` | number | Compute units used per hour by all machines. |
| `runway.hours` | number | Hours until the balance reaches zero at the current rate. `null` when nothing uses compute units. |
| `runway.empty_at` | number | When the balance reaches zero at the current rate. |
| `spend.today`, `spend.7d`, `spend.30d` | number | Compute units spent since local midnight, in the last 7 days, and in the last 30 days. |
| `spend.measured_since` | number | The time of the oldest usage sample. Spend covers only the time after it. |
| `machines[]` | array | Every machine on the account, without released ones. |
| `machines[].name` | string | The CLI's session name. `null` for an orphan that no history file names. |
| `machines[].endpoint` | string | Colab's identifier for the machine. |
| `machines[].status` | string | `busy`, `idle`, `stopping`, `orphan`, or `unknown`. See [Status values](#status-values). |
| `machines[].hardware` | string | `CPU`, or the accelerator such as `T4` or `A100`, with ` High-RAM` added for a high-RAM machine. |
| `machines[].job` | string | The command that the CLI runs in the machine. |
| `machines[].uptime_s` | number | Seconds since the machine started. |
| `machines[].idle_s` | number | Seconds since the last command finished. `0` for a busy machine. |
| `machines[].rate` | number | Compute units per hour for this machine. |
| `machines[].rate_estimated` | boolean | `true` when `rate` is an estimate. See [How Colab Monitor works](how-it-works.md#what-a-machine-costs). |
| `machines[].cost`, `machines[].idle_cost` | number | Compute units used since the machine started, and while it was idle. |
| `jobs[]` | array | One entry for each log file. |
| `jobs[].name`, `jobs[].path` | string | The file name and its full path. |
| `jobs[].session` | string | The machine that the log belongs to, matched by name. |
| `jobs[].silent_s` | number | Seconds since the file last changed. |
| `jobs[].stalled` | boolean | `true` when the job's machine is busy and the file has been silent longer than `--stall-alert`. |
| `jobs[].progress` | number | Progress from 0 to 1, read from the last progress line. |
| `jobs[].eta_s` | number | Seconds left, from the progress line. |
| `jobs[].speed` | string | The speed on the progress line, such as `3.1 it/s`. |
| `jobs[].metrics` | object | The latest numbers such as `loss` and `accuracy`, up to 8. |
| `jobs[].last_error` | string | The last line that looks like an error. |
| `runs["24h"]`, `runs["7d"]` | object | `ok` and `failed` counts of code runs that the CLI recorded. |
| `machine_hours_7d` | object | Machine hours in the last 7 days for each kind of hardware, such as `{"T4": 2.5, "CPU": 9.0}`. |
| `attention[]` | array | The items that need attention, critical ones first. |
| `attention[].severity` | string | `critical` or `warning`. |
| `attention[].kind` | string | `orphan`, `runway`, `idle`, `stalled`, or `failed`. |
| `attention[].subject` | string | The machine, log file, or `compute units`. |
| `attention[].message` | string | One sentence for people. |
| `thresholds` | object | `idle_minutes`, `stall_minutes`, and `runway_hours` in effect. |

For example, a script can stop when something needs attention:

```bash
colab-monitor status --exit-code > /dev/null || echo "Something needs attention"
```

## Files

| Path | Access | Contents |
|---|---|---|
| `~/.config/colab-cli/sessions.json` and other `--config` files | Read | The sessions that the CLI tracks. Colab Monitor removes their access tokens and runtime URLs before it sends anything to the page. |
| `~/.config/colab-cli/history/*.jsonl` | Read | One file for each session, with the events that the CLI recorded. |
| `~/.config/colab-cli/token.json` | Read, and updated by `serve` | The CLI's sign-in token. `serve` uses the CLI's own sign-in code, which can refresh the file. `status` and `watch` only read it. |
| Files from `--log` and `--log-dir` | Read | Job output. The page shows at most the last 2,000 lines of the selected file, read from its last 256 KB. Job progress comes from the last 200 lines. |
| `~/.config/colab-monitor/usage.jsonl` | Read and appended | One JSON line for each successful Colab check, with the time, the balance, and the usage rate. `serve` removes samples older than 30 days at startup. |

## Status values

The API returns one of these values for each session. The page shows the label.

| API value | Label | Condition |
|---|---|---|
| `busy` | Running | Colab lists the machine, and the CLI is running a command in it. |
| `idle` | Idle | Colab lists the machine, and the CLI knows it but runs nothing in it. |
| `stopping` | Stopping | The CLI stopped the machine, and the last Colab check still listed it. |
| `orphan` | Orphan | Colab lists the machine, and the CLI has no record of it. |
| `gone` | Released | The CLI has a record of the machine, and Colab no longer lists it. |
| `unknown` | Unknown | Colab has not been checked yet. |

## HTTP API

The page uses these endpoints. All of them take `GET` and return JSON. Any other path returns
`404`, except the page and its static files.

| Endpoint | Returns |
|---|---|
| `/api/state?idle_alert=M&stall_alert=M&runway_alert=H` | The sessions with their status and `metrics`, the latest Colab usage, the log files, the session names in history, the configuration, and `insights`. The query parameters are optional and override the alert options for this request. A value that is not a positive number returns `400`. |
| `/api/log?path=FILE&lines=N` | The last `N` lines of a configured log file. `N` is 1 to 5,000, and the default is 300. A missing `path` returns `400`. A file that is not configured returns `403`. |
| `/api/history?session=NAME&limit=N` | The latest `N` events of one session, oldest first. `N` is 1 to 500, and the default is 50. An invalid name returns `400`. |
| `/api/usage?range=R` | Chart samples for `R`, which is `1h`, `24h`, `7d`, or `30d`. The default is `24h`. At most 360 points are returned. Another value returns `400`. |
| `/api/activity?limit=N` | The latest `N` events across all sessions, newest first. `N` is 1 to 200, and the default is 20. |

In `/api/state`, each session's `metrics` holds `uptime_s`, `idle_s`, `rate`, `rate_estimated`,
`cost`, and `idle_cost`, and is `null` for a released machine. `insights` holds `spend`, `runway`,
`idle_cost`, `machine_hours_7d`, `runs`, `jobs`, `attention`, and `thresholds`, with the same
meaning as in [the status report](#the-status-report).

When the server listens on a loopback address, it refuses any request whose `Host` header is not a
loopback name or address, and returns `403`.
