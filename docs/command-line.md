# Command-line reference

## Synopsis

```text
colab-monitor [--host HOST] [--port PORT] [--interval SECONDS]
              [--log FILE] [--log-dir DIR] [--config FILE] [--history-dir DIR]
              [--auth {oauth2,adc}] [-c FILE] [--usage-log FILE]
              [--no-api] [--open] [--version] [-h]
```

## Options

| Option | Default | Description |
|---|---|---|
| `--host HOST` | `127.0.0.1` | Address to listen on. Any address that is not a loopback address prints a warning, because anyone who can reach the port can read your logs. |
| `--port PORT` | `26522` | Port to listen on. If another Colab Monitor already listens on this port, the command prints its address, opens it when `--open` is set, and exits with status 0. |
| `--interval SECONDS` | `60` | Seconds between Colab checks. The minimum is 30. |
| `--log FILE` | none | A log file to show. Repeat the option to show more files. |
| `--log-dir DIR` | `~/colab-runs` | A folder whose `.log`, `.out`, and `.err` files are shown. Subfolders are not read. Repeat the option to read more folders. Any `--log-dir` replaces the default. |
| `--config FILE` | `~/.config/colab-cli/sessions.json` | The session state file of the `colab` CLI. |
| `--history-dir DIR` | `~/.config/colab-cli/history` | The history folder of the `colab` CLI. |
| `--auth {oauth2,adc}` | `oauth2` | Sign-in method. Same as `colab --auth`. |
| `-c FILE`, `--client-oauth-config FILE` | `~/.colab-cli-oauth-config.json` | OAuth client configuration. Same as `colab -c`. |
| `--usage-log FILE` | `~/.config/colab-monitor/usage.jsonl` | File that keeps the samples for the usage chart. |
| `--no-api` | off | Never contact Colab. The page shows local files only. |
| `--open` | off | Open the dashboard in the default browser. |
| `--version` | | Print the version and exit. |
| `-h`, `--help` | | Print the options and exit. |

## Exit status

| Status | Meaning |
|---|---|
| `0` | The server stopped after Ctrl-C, the command printed its version or help, or another Colab Monitor already serves the port. |
| `1` | Another program uses the port, the address cannot be used, or sign-in to Colab failed. |
| `2` | An option is invalid, for example `--interval 10`. |

## Files

| Path | Access | Contents |
|---|---|---|
| `~/.config/colab-cli/sessions.json` | Read | The sessions that the CLI tracks. Colab Monitor removes their access tokens and runtime URLs before it sends anything to the page. |
| `~/.config/colab-cli/history/*.jsonl` | Read | One file for each session, with the events that the CLI recorded. |
| `~/.config/colab-cli/token.json` | Read and updated | The CLI's sign-in token, used through the CLI's own sign-in code when `--auth oauth2` is set. |
| Files from `--log` and `--log-dir` | Read | Job output. The page shows at most the last 2,000 lines of the selected file, read from its last 256 KB. |
| `~/.config/colab-monitor/usage.jsonl` | Read and appended | One JSON line for each successful Colab check, with the time, the balance, and the usage rate. Samples older than 30 days are removed at startup. |

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
| `/api/state` | The sessions with their status, the latest Colab usage, the log files, the session names in history, and the configuration. |
| `/api/log?path=FILE&lines=N` | The last `N` lines of a configured log file. `N` is 1 to 5,000, and the default is 300. A missing `path` returns `400`. A file that is not configured returns `403`. |
| `/api/history?session=NAME&limit=N` | The latest `N` events of one session, oldest first. `N` is 1 to 500, and the default is 50. An invalid name returns `400`. |
| `/api/usage?range=R` | Chart samples for `R`, which is `1h`, `24h`, `7d`, or `30d`. The default is `24h`. At most 360 points are returned. Another value returns `400`. |
| `/api/activity?limit=N` | The latest `N` events across all sessions, newest first. `N` is 1 to 200, and the default is 20. |

When the server listens on a loopback address, it refuses any request whose `Host` header is not a
loopback name or address, and returns `403`.
