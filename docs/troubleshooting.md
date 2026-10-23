# Troubleshooting

## Fix a sign-in error at startup

If the terminal prints `Couldn't sign in to Colab`, the `colab` CLI has no valid sign-in.

1. Run `colab sessions` and complete the sign-in.
2. Start Colab Monitor again.

To use the dashboard without Colab, start it with `--no-api`. The **Logs** and **History** pages
still work.

## Fix a port conflict

If the terminal prints `Port 26522 is used by another program`, start Colab Monitor on another
port:

```bash
colab-monitor --port 26523 --open
```

If Colab Monitor itself already uses the port, the command prints the address of the running
dashboard instead of an error. Open that address, or run the command again with `--open`.

## Show a job's log on the Logs page

The **Logs** page shows a file only when both of these are true:

- The file name ends in `.log`, `.out`, or `.err`.
- The file sits directly inside a `--log-dir` folder. The default folder is `~/colab-runs`.
  Subfolders are not read.

To show a file in another place, start Colab Monitor with `--log /path/to/file.log`, or add its
folder with `--log-dir /path/to/folder`.

## Respond to the "Can't reach Colab" notice

The notice means that the last check failed. The numbers on screen come from the last successful
check, and the dashboard retries after a wait that doubles up to 10 minutes.

If the notice stays, run `colab sessions`. An error there points to the cause, such as an expired
sign-in or no network connection.

## Release an orphaned machine

An orphaned machine still uses compute units, and the CLI will not stop it.

1. On the **Sessions** page, copy the endpoint shown under the machine's name.
2. Release the machine. Replace `ENDPOINT` with the endpoint that you copied:

   ```bash
   uvx --from google-colab-cli python -c "from colab_cli.common import state; state.client.unassign('ENDPOINT')"
   ```

3. Run `colab sessions` to confirm that the machine is gone.

## Fix "Not signed in to Colab" from status or watch

`status` and `watch` use the sign-in that the `colab` CLI saved, and never start a sign-in
themselves. Without a saved sign-in, they show local files only, with no balance or machines.

1. Run `colab sessions` and complete the sign-in.
2. Run `colab-monitor status` again.

To read local files on purpose and hide the message, pass `--no-api`.

## Make status show the files you passed

If a dashboard runs, `status` and `watch` show the dashboard's data. When you pass an option that
chooses files, such as `--config` or `--log-dir`, they read the files themselves instead. The `source` field of
`colab-monitor status --json` is `dashboard` when the data came from the running dashboard.

To read another dashboard, pass its port with `--port`.

## Understand a machine rate marked with ≈ or shown as –

Colab reports one usage rate for the whole account. A rate marked with `≈` is an estimate for one
machine, worked out from the rise in the account's rate when the machine started. A `–` means that
Colab Monitor could not tell the machines apart, for example because the dashboard was off when the
machine started. [How Colab Monitor works](how-it-works.md#what-a-machine-costs) lists every case.

To get estimates for the machines you start next, keep the dashboard running while they start.

## Show a job's progress

The **Jobs** card and `status` show progress when the log has one of these lines:

- A tqdm bar, such as `45/100 [00:30<00:37, 1.5it/s]`.
- A step counter, such as `step 900/1800`.
- An epoch counter, such as `epoch 3/10`.

Write metrics as `loss=0.25` or `accuracy: 0.91` to show them next to the progress.

## Stop the stalled warning for a quiet job

A job counts as stalled when its machine runs a command and its log has not changed for 15
minutes. If a job prints rarely by design, stop the dashboard and start it again with a higher
threshold:

```bash
colab-monitor --stall-alert 60
```

`status` and `watch` take the same option.

## Use watch in a script

`watch` needs a terminal and exits with status 2 without one. In a script, use
`colab-monitor status`, or `colab-monitor status --json` for output that a program reads.

## Quiet the fan while Colab jobs run

If your computer's fan speeds up while `colab run` or `colab exec` jobs run, the cause is the
`colab` CLI, not the dashboard. Both commands default to `--timeout 30`. Once a job runs longer than
30 seconds, the CLI's local client checks for output in a loop that never waits, and uses a full CPU
core until the job ends. Activity Monitor shows one `python3` process near 100% CPU for each job.

Pass a timeout longer than the job when you start it:

```bash
colab run --timeout 86400 --gpu T4 -s train train.py > ~/colab-runs/train.log 2>&1
```

The job runs the same way, and its client stays near 0% CPU. The option takes effect only when a
job starts, so a job that already runs keeps its client busy until it ends.

## Understand an empty chart or a gap in the chart

The chart draws a line after the second successful Colab check, which takes one interval. It has
data only for the time that Colab Monitor was running, and it leaves a gap where the dashboard was
off. To keep a complete history, leave Colab Monitor running.

## Understand why a busy machine shows as Idle

**Running** means that the CLI is running a command in the machine. If you open a CLI session in
the browser with `colab url` and run code there, the CLI does not see that work, so the machine
shows as **Idle** even while it works.
