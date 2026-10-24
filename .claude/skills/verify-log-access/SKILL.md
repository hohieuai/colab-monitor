---
name: verify-log-access
description: Check that Colab Monitor's /api/log serves only allowed log files, over every request path up to a bound. Use before you commit any change to how log files are found, checked, listed, or read (sources.resolve_log, sources.discover_logs, sources.tail_lines, LOG_SUFFIXES, Dashboard._log, or the /api/log route), any change to --log or --log-dir handling, and when you review a security report about reading files through the dashboard.
---

# Verify log access

## What is verified

**Promise.** `/api/log` serves only the files passed with `--log`, and `.log`, `.out`, and `.err`
files directly inside a `--log-dir` folder (`SECURITY.md`, "Security model").

**Harm if broken.** Anything that can reach the dashboard reads private files, such as the colab
CLI's OAuth token in `~/.config/colab-cli/token.json`.

`verification/log_access/check.py` runs the real `Dashboard.handle` (no model) against one
directory tree that holds every known trap, and labels each file by hand as allowed or secret.
The traps are:

- symlinks from the log folder to a secret file, to the token, and to a subfolder;
- a symlinked folder inside the log folder;
- a log folder that is itself a symlink;
- a file with the wrong suffix and a log in a subfolder;
- a `--log` file reached through a symlink.

It sends every request path built from absolute, `~/`, relative, and doubled-slash starts, then up
to 3 folder pieces from `runs`, `runs-alias`, `outside`, `sub`, `linkdir`, `..`, `.`, and the empty
piece. The name follows as written, with a trailing `/`, in upper case, or with a NUL byte. That is
599,040 requests over 4 `--log`/`--log-dir` configurations, and it checks four properties:

| Id | Property |
|---|---|
| P1 | No answer contains the text of a secret file. This is the security promise. |
| P2 | Every request gets an answer, 200, 400, or 403, and never an exception. |
| P3 | Every log that `/api/state` lists can be opened with `/api/log`. |
| P4 | A 200 answer holds the lines of the file that the path names. |

The check does not cover:

- Paths deeper than 3 folders, or names outside the tree.
- The HTTP layer: query decoding in `make_server`'s `do_GET` and the `Host` check. Any string can
  reach `handle` as `path`, because `parse_qs` decodes percent escapes.
- A file that another local process replaces with a symlink between the check and the read.
  `Dashboard._log` reads the resolved path that `resolve_log` returned, so only the last path
  piece can still change in that moment. Only a process that can already write to your log folder
  can do this.
- Windows paths.

## Coverage and sync

| File | What the check covers |
|---|---|
| `src/colab_monitor/sources.py` | `resolve_log`, `discover_logs`, `_log_entry`, `tail_lines`, `LOG_SUFFIXES` |
| `src/colab_monitor/server.py` | `Dashboard.handle` for `/api/log` and `/api/state` (the `logs` list), `Dashboard._log` |

**Sync commit:** `d9818dd`. At this commit the check was confirmed to describe the code above.

To see whether covered code changed since then:

```bash
git diff d9818dd -- src/colab_monitor/sources.py src/colab_monitor/server.py \
  | grep -nE "^[-+].*(resolve_log|discover_logs|_log_entry|tail_lines|LOG_SUFFIXES|def _log|/api/log)"
```

Any output means a covered line changed. Read the whole function around it, because a change
inside a function body does not always repeat the function's name.

Move the sync commit forward only after you read the changed covered code, confirm that the tree,
the labels, and the four properties still describe it, and run the check at the new commit.

## Run it

```bash
uv run python verification/log_access/check.py            # about 20 seconds
uv run python verification/log_access/check.py --mutants  # about 1 minute
```

The first command prints `pass` or `FAIL` for each property with up to 3 counterexamples, and
exits with 1 if any property fails. `--mutants` patches three broken versions of `resolve_log`
in memory and prints `caught` for each one that P1 catches. If it prints `MISSED`, the check has
gone blind. Fix the check before you trust a pass.

## Expected result at the sync commit

At the sync commit, all four properties pass, and `--mutants` prints `caught` three times. Any
`FAIL` is new and needs a look.

## Tell a real bug from a check error

- **P1 fails.** Treat it as a security bug until proven otherwise. The counterexample names the
  request path and the secret file that it returned. Reproduce it with
  `Dashboard(...).handle("/api/log", {"path": ...})` in a test before you change anything.
- **A P2, P3, or P4 failure** points to the covered code, so read the diff since the sync commit
  first.
- **A check error** looks like this: a file that the promise allows is labelled secret in `FILES`,
  or a new kind of path that the code means to serve, such as a new suffix in `LOG_SUFFIXES`, is
  missing from the tree. Fix the labels or the tree. Never relabel a file only to make P1 pass. Do
  that only when the promise in `SECURITY.md` changed in the same change.

## Update the check for an intended change

- **A new allowed kind of file,** such as a new suffix or recursive folders: add a file of that
  kind and a secret look-alike to `FILES`. Update `SECURITY.md` in the same change.
- **A new kind of trap,** such as a hard link or a new path syntax: add it to `LINKS`, `FILES`,
  `FOLDERS`, or `NAME_VARIANTS`. Run with `--mutants` to confirm that each mutant is still caught.
- **Keep it fast:** keep `MAX_DEPTH` at 3 unless a trap needs a deeper path. Each extra level
  multiplies the run time by about 8.
