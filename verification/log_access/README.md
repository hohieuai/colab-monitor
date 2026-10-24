# Log access verification

`check.py` verifies the promise in [SECURITY.md](../../SECURITY.md): `/api/log` serves only the
files passed with `--log`, and `.log`, `.out`, and `.err` files directly inside a `--log-dir`
folder. If that promise breaks, anything that can reach the dashboard can read private files, such
as the `colab` CLI's OAuth token in `~/.config/colab-cli/token.json`.

Run the check before you merge any change to how log files are found, checked, listed, or read.

## Run the check

```bash
uv run python verification/log_access/check.py            # about 20 seconds
uv run python verification/log_access/check.py --mutants  # about 1 minute
```

The first command prints `pass` or `FAIL` for each property, with up to 3 counterexamples for each
failure. It exits with status 1 if any property fails.

`--mutants` patches three broken versions of `resolve_log` in memory and prints `caught` for each
one that property P1 catches. If it prints `MISSED`, the check can no longer see the faults it is
meant to catch. Fix the check before you trust a pass.

At the sync commit, all four properties pass and `--mutants` prints `caught` three times. Any
`FAIL` is new.

CI runs the first command on every pull request, on Linux and macOS.

## What the check covers

The check calls the real `Dashboard.handle`; it does not model the code. It builds one directory
tree with every trap known so far, and labels each file by hand as allowed or secret:

- symlinks from the log folder to a secret file, to the token, and into a subfolder;
- a symlinked folder inside the log folder;
- a log folder that is itself a symlink;
- a file with the wrong suffix, and a log file in a subfolder;
- a `--log` file reached through a symlink.

It then sends every request path built from an absolute, `~/`, relative, or doubled-slash start,
followed by up to 3 folder pieces from `runs`, `runs-alias`, `outside`, `sub`, `linkdir`, `..`,
`.`, and the empty piece. The file name follows as written, with a trailing `/`, in upper case, or
with a NUL byte. That is 599,040 requests over 4 `--log` and `--log-dir` configurations.

| Property | Statement |
|---|---|
| P1 | No answer contains the text of a secret file. This is the security promise. |
| P2 | Every request gets an answer: 200, 400, or 403, never an exception. |
| P3 | Every log that `/api/state` lists can be opened with `/api/log`. |
| P4 | A 200 answer holds the lines of the file that the path names. |

The check does not cover:

- paths deeper than 3 folders, or names outside the tree;
- the HTTP layer: query decoding in `make_server`'s `do_GET`, and the `Host` check. Any string can
  reach `handle` as `path`, because `parse_qs` decodes percent escapes;
- a file that another local process replaces with a symlink between the check and the read.
  `Dashboard._log` reads the resolved path that `resolve_log` returned, so only the last path piece
  can change in that moment, and only a process that can already write to the log folder can do it;
- Windows paths.

## Coverage and sync commit

| File | Code the check covers |
|---|---|
| `src/colab_monitor/sources.py` | `resolve_log`, `discover_logs`, `_log_entry`, `tail_lines`, `LOG_SUFFIXES` |
| `src/colab_monitor/server.py` | `Dashboard.handle` for `/api/log` and `/api/state` (the `logs` list), `Dashboard._log` |

**Sync commit:** `a8c6cd4`. At this commit, the check was confirmed to describe the code above.

To list the commits since then that changed covered code, run:

```bash
verification/log_access/covered_changes.sh a8c6cd4
```

No output means that the covered code is unchanged. The script follows changes inside each
function's body with `git log -L`, which a search of the diff for the function's name can miss.

Move the sync commit forward only after you read the changed code, confirm that the tree, the
labels, and the four properties still describe it, and run the check at the new commit.

## Investigate a failure

- **P1 fails.** Treat it as a security bug until proven otherwise. The counterexample names the
  request path and the secret file that it returned. Reproduce it in a test with
  `Dashboard(...).handle("/api/log", {"path": ...})` before you change any code.
- **P2, P3, or P4 fails.** The cause is usually in the covered code. Start with the diff since the
  sync commit.
- **The check itself is wrong.** For example, a file that the promise allows is labelled secret in
  `FILES`, or a new kind of path that the code is meant to serve, such as a new suffix in
  `LOG_SUFFIXES`, is missing from the tree. Fix the labels or the tree. Relabel a file only when the
  promise in `SECURITY.md` changes in the same pull request, never just to make P1 pass.

## Update the check

- **A new kind of allowed file,** such as a new suffix or recursive folders: add a file of that kind
  and a secret look-alike to `FILES`, and update `SECURITY.md` in the same pull request.
- **A new kind of trap,** such as a hard link or a new path syntax: add it to `LINKS`, `FILES`,
  `FOLDERS`, or `NAME_VARIANTS`, then run with `--mutants` to confirm that every mutant is still
  caught.
- **Run time:** keep `MAX_DEPTH` at 3 unless a trap needs a deeper path. Each extra level
  multiplies the run time by about 8.
