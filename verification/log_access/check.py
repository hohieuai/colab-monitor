"""Exhaustive check of what /api/log serves, over every request path up to a bound.

    uv run python verification/log_access/check.py            # check the code as it is
    uv run python verification/log_access/check.py --mutants  # show the check catches broken variants

The promise (SECURITY.md): /api/log serves only the files passed with --log, and .log, .out, and
.err files directly inside a --log-dir folder. A break lets any page or process that reaches the
dashboard read private files such as the colab CLI's OAuth token.

The check builds one directory tree that holds every trap we know of (symlinks in and out of the log
folder, a symlinked log folder, subfolders, wrong suffixes, a token file), and labels each file by
hand as allowed or secret. It then sends Dashboard.handle every request path built from a fixed
alphabet of path pieces, up to MAX_DEPTH pieces, under every configuration, and checks:

  P1  No answer contains the text of a secret file.                     (security)
  P2  Every request gets an answer: 200, 400, or 403, never an exception. (robustness)
  P3  Every log that /api/state lists can be opened with /api/log.     (the Logs page works)
  P4  A 200 answer holds the lines of the file the path names.          (the right file is shown)

It runs the real code, not a model of it. A pass covers this tree and every path up to the bound.
"""

import argparse
import contextlib
import itertools
import os
import pathlib
import sys
import tempfile
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from colab_monitor import sources  # noqa: E402
from colab_monitor.server import Dashboard  # noqa: E402

MAX_DEPTH = 3  # folder pieces before the file name; 3 reaches runs/../outside and linkdir/../runs

# Files in the tree: path -> True if the promise allows serving it. Each file's only line is a marker
# naming it, so an answer shows which file was read.
FILES = {
    "runs/a.log": True,
    "runs/b.out": True,
    "runs/c.err": True,
    "runs/.hidden.log": True,
    "runs/notes.txt": False,  # wrong suffix
    "runs/sub/d.log": False,  # in a subfolder
    "outside/secret.log": False,  # outside every log folder
    "outside/token.json": False,  # stands in for ~/.config/colab-cli/token.json
    "outside/explicit.txt": True,  # allowed only because it is passed with --log
}
# Symlinks: link path -> target, relative to the link's folder. What a link serves is decided by
# the file it resolves to, so links carry no label of their own.
LINKS = {
    "runs/link-in.log": "a.log",
    "runs/link-out.log": "../outside/secret.log",
    "runs/link-token.log": "../outside/token.json",
    "runs/link-sub.log": "sub/d.log",
    "runs/linkdir": "../outside",
    "runs-alias": "runs",
    "outside/explicit-link.txt": "explicit.txt",
}
# Configurations: (log files, log folders), relative to the tree.
CONFIGS = [
    ([], ["runs"]),
    ([], ["runs-alias"]),
    (["outside/explicit.txt"], ["runs"]),
    (["outside/explicit-link.txt"], ["runs-alias"]),
]
FOLDERS = ["runs", "runs-alias", "outside", "sub", "linkdir", "..", ".", ""]
NAMES = sorted({pathlib.PurePath(p).name for p in [*FILES, *LINKS]})
NAME_VARIANTS = [lambda n: n, lambda n: n + "/", lambda n: n.upper(), lambda n: n + "\x00"]


def marker(rel: str) -> str:
    return f"MARKER {rel}"


def build(root: pathlib.Path) -> None:
    for rel in FILES:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(marker(rel) + "\n")
    for rel, target in LINKS.items():
        os.symlink(target, root / rel)


def requests(root: pathlib.Path):
    """Every request path: a start (absolute, ~, relative, or doubled slash), folders, a name."""
    starts = [str(root) + "/", "~/", "", "/" + str(root) + "//"]
    for depth in range(MAX_DEPTH + 1):
        for folders in itertools.product(FOLDERS, repeat=depth):
            for name in NAMES:
                for variant in NAME_VARIANTS:
                    for start in starts:
                        yield start + "".join(f + "/" for f in folders) + variant(name)


def marker_of(lines) -> str | None:
    text = "\n".join(lines)
    found = [rel for rel in FILES if marker(rel) in text]
    return found[0] if found else None


def check(root: pathlib.Path, limit: int = 3) -> dict[str, list[str]]:
    """Counterexamples for each property, at most `limit` each."""
    failures: dict[str, list[str]] = {"P1": [], "P2": [], "P3": [], "P4": []}

    def fail(prop: str, text: str) -> None:
        if len(failures[prop]) < limit:
            failures[prop].append(text)

    for files, dirs in CONFIGS:
        config = f"--log {files or '(none)'} --log-dir {dirs}"
        app = Dashboard(
            None,
            sessions_path=str(root / "none.json"),
            history_dir=str(root / "history"),
            log_files=[str(root / f) for f in files],
            log_dirs=[str(root / d) for d in dirs],
        )
        allowed = {rel for rel, ok in FILES.items() if ok and (rel != "outside/explicit.txt" or files)}

        for path in requests(root):
            shown = path.replace(str(root), "ROOT")
            try:
                status, body = app.handle("/api/log", {"path": path, "lines": "5000"})
            except Exception as e:  # noqa: BLE001 - P2 is about exactly this
                fail("P2", f"{config}: path {shown!r} raises {type(e).__name__}: {e}")
                continue
            if status not in (200, 400, 403):
                fail("P2", f"{config}: path {shown!r} answers {status}")
                continue
            if status != 200:
                continue
            read = marker_of(body["lines"])
            if read is not None and read not in allowed:
                fail("P1", f"{config}: path {shown!r} returns the secret file {read}")
            target = os.path.realpath(os.path.expanduser(path))
            expected = next((rel for rel in FILES if os.path.realpath(root / rel) == target), None)
            if read != expected:
                fail("P4", f"{config}: path {shown!r} names {expected}, but the answer holds {read}")

        for log in app.handle("/api/state", {})[1]["logs"]:
            status, _ = app.handle("/api/log", {"path": log["path"]})
            if status != 200:
                fail("P3", f"{config}: the Logs page lists {log['name']}, but opening it answers {status}")
    return failures


# Broken variants of sources.resolve_log. P1 must catch each one.
def _no_realpath(path, files, dirs):
    real = os.path.abspath(os.path.expanduser(path))
    if real in {os.path.abspath(os.path.expanduser(f)) for f in files}:
        return real
    dirs_abs = {os.path.abspath(os.path.expanduser(d)) for d in dirs}
    return real if real.endswith(sources.LOG_SUFFIXES) and os.path.dirname(real) in dirs_abs else None


def _no_suffix_check(path, files, dirs):
    real = os.path.realpath(os.path.expanduser(path))
    if real in {os.path.realpath(os.path.expanduser(f)) for f in files}:
        return real
    return real if os.path.dirname(real) in {os.path.realpath(os.path.expanduser(d)) for d in dirs} else None


def _subfolders_allowed(path, files, dirs):
    real = os.path.realpath(os.path.expanduser(path))
    if real in {os.path.realpath(os.path.expanduser(f)) for f in files}:
        return real
    inside = any(real.startswith(os.path.realpath(os.path.expanduser(d))) for d in dirs)
    return real if real.endswith(sources.LOG_SUFFIXES) and inside else None


MUTANTS = {
    "resolve_log compares unresolved paths": _no_realpath,
    "resolve_log drops the suffix check": _no_suffix_check,
    "resolve_log allows subfolders": _subfolders_allowed,
}


@contextlib.contextmanager
def tree():
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(os.path.realpath(tmp)) / "home"
        root.mkdir()
        build(root)
        old_cwd, old_home = os.getcwd(), os.environ.get("HOME")
        os.chdir(root)
        os.environ["HOME"] = str(root)  # "~/" requests land in the tree
        try:
            yield root
        finally:
            os.chdir(old_cwd)
            if old_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = old_home


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--mutants", action="store_true", help="check that P1 catches broken variants")
    args = parser.parse_args()

    with tree() as root:
        total = sum(1 for _ in requests(root)) * len(CONFIGS)
        if args.mutants:
            missed = 0
            for name, broken in MUTANTS.items():
                with mock.patch.object(sources, "resolve_log", broken):
                    caught = check(root, limit=1)["P1"]
                print(f"{'caught' if caught else 'MISSED'}  {name}")
                if caught:
                    print(f"        {caught[0]}")
                missed += not caught
            return 1 if missed else 0

        failures = check(root)
    print(f"Checked {total:,} requests: {len(CONFIGS)} configurations, paths up to {MAX_DEPTH} folders deep.")
    titles = {
        "P1": "No answer contains a secret file",
        "P2": "Every request gets an answer",
        "P3": "Every listed log opens",
        "P4": "A 200 answer holds the named file",
    }
    for prop, title in titles.items():
        print(f"{'FAIL' if failures[prop] else 'pass'}  {prop}  {title}")
        for example in failures[prop]:
            print(f"        {example}")
    return 1 if any(failures.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
