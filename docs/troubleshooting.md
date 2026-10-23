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

## Understand an empty chart or a gap in the chart

The chart draws a line after the second successful Colab check, which takes one interval. It has
data only for the time that Colab Monitor was running, and it leaves a gap where the dashboard was
off. To keep a complete history, leave Colab Monitor running.

## Understand why a busy machine shows as Idle

**Running** means that the CLI is running a command in the machine. If you open a CLI session in
the browser with `colab url` and run code there, the CLI does not see that work, so the machine
shows as **Idle** even while it works.
