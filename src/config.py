"""Where this user's job-search data lives, and the per-machine settings.

Single source of truth for the **data root** — the directory holding `jobs/`,
`db.sqlite3`, `exports/` and `backups/`. The distinction this module exists to enforce:

    REPO_ROOT   the code — src/, tools/, .claude/, docs/, example-data/
    data_root() this person's job search — jobs/, db.sqlite3, exports/, backups/

They are always different directories. Every data path goes through `data_root()`.

Resolution order, first one set wins:

1. ``$JOBSTUDIO_DATA`` — per shell, most specific
2. ``.jobstudio-data`` in the repo root — per checkout, a single line holding the path
3. ``~/.jobstudio.ini``'s ``data_root`` — per machine

Nothing set is an error that says to run ``/jobstudio init``. Until 2026-11-11 there was a
fourth layer, the repo itself, for the layout from before code and data were split; no
checkout has data in it any more, so it only made the ladder longer (TODO `#75`).

``~/.jobstudio.ini`` does two unrelated jobs, and only the first is one of the layers:

- ``data_root`` — layer 3 above. Not needed where a checkout has its own pointer.
- per-machine settings, read through `setting()`: ``open_command`` (how to open a file
  or folder) and the job-board API keys (``adzuna_app_id``, ``adzuna_app_key``,
  ``reed_api_key``). These have no other layer, and stay out of the data root because
  that is often a git repo with a remote.

Layer 2 sits above layer 3 deliberately: a machine can have several checkouts pointing
at different data roots (a real one and a sandbox), so the per-checkout pointer has to
win over the per-machine default. Layer 3 exists because the working directory is often
*not* the repo — editing ``jobs/companies/<slug>.md`` puts you in the data root, where
there is no pointer file and no ``src/config.py`` to run. ``$HOME`` is reachable from
anywhere.

``.ini`` rather than YAML, which is the house format for everything else, because this
module must stay stdlib-only: ``configparser`` ships with Python, ``PyYAML`` does not,
and ``appfolder.py`` imports this at module level.

A root named by (1) or (2) must exist: a typo there should fail loudly rather than
silently write a second copy of someone's job search into a directory that isn't
theirs. Falling through to (3) is not an error — it's the default.

Module level stays dependency-free (stdlib only, no Django), because
`src/appfolder.py` imports it and is itself deliberately importable by the Django app.
"""

from __future__ import annotations

import configparser
import os
from pathlib import Path

ENV_VAR = "JOBSTUDIO_DATA"
POINTER_FILENAME = ".jobstudio-data"

#: Machine-level settings: layer 3's `data_root`, plus `setting()`'s keys. Written by `init`.
GLOBAL_SETTINGS_FILE = Path.home() / ".jobstudio.ini"
GLOBAL_SECTION = "jobstudio"
GLOBAL_DATA_ROOT_KEY = "data_root"

# src/config.py -> src/ -> the repo
REPO_ROOT = Path(__file__).resolve().parent.parent

POINTER_FILE = REPO_ROOT / POINTER_FILENAME


class DataRootError(RuntimeError):
    """A data root was configured explicitly but doesn't exist."""


def _clean(raw: str) -> Path:
    return Path(raw.strip()).expanduser().resolve()


def _from_global_settings() -> Path | None:
    """`data_root` from ~/.jobstudio.ini, if that file names one.

    A missing file, section or key is not an error — it just means this layer has
    nothing to say. A *malformed* file is, because silently ignoring a settings file
    someone has edited is how you spend an hour wondering why it has no effect.
    """
    if not GLOBAL_SETTINGS_FILE.is_file():
        return None

    # inline_comment_prefixes: without it, `data_root = /path  # note` yields the path
    # WITH the note attached, and the failure is a confusing "does not exist" naming a
    # directory the user can see. Found 2026-09-21 when exactly that happened.
    parser = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
    try:
        parser.read(GLOBAL_SETTINGS_FILE)
    except configparser.Error as exc:
        raise DataRootError(
            f"Could not parse {GLOBAL_SETTINGS_FILE}:\n"
            f"  {exc}\n"
            "Fix the file, or remove it to fall back to the other layers."
        ) from exc

    raw = parser.get(GLOBAL_SECTION, GLOBAL_DATA_ROOT_KEY, fallback="").strip()
    return _clean(raw) if raw else None


def setting(key: str, default: str = "") -> str:
    """Any machine-level setting from ~/.jobstudio.ini's [jobstudio] section.

    For the things that are per-machine rather than per-search: `open_command`, kept as
    a setting rather than a `sys.platform` branch so another platform is data, not code;
    and the job-board API keys, kept out of the data root because it may be pushed.
    """
    if not GLOBAL_SETTINGS_FILE.is_file():
        return default
    parser = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
    try:
        parser.read(GLOBAL_SETTINGS_FILE)
    except configparser.Error:
        return default
    return parser.get(GLOBAL_SECTION, key, fallback=default).strip() or default


def _configured() -> tuple[Path, str] | None:
    """The explicitly-configured data root and where it came from, if any.

    Order matters and is documented at the top of this module: shell, then checkout,
    then machine. The per-checkout pointer beats the per-machine file on purpose.
    """
    env = os.environ.get(ENV_VAR, "").strip()
    if env:
        return _clean(env), f"${ENV_VAR}"

    if POINTER_FILE.is_file():
        for line in POINTER_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                return _clean(line), str(POINTER_FILE)

    from_global = _from_global_settings()
    if from_global is not None:
        return from_global, f"{GLOBAL_SETTINGS_FILE} [{GLOBAL_SECTION}] {GLOBAL_DATA_ROOT_KEY}"

    return None


#: What a data root must contain to be one. `jobs/` is the tree every subcommand reads;
#: `db.sqlite3` is the tracker. Either alone is enough — a data root mid-`init` may have
#: one without the other.
MARKERS = ("jobs", "db.sqlite3")


def looks_like_data_root(path: Path) -> bool:
    """Does this directory hold job-search data?

    The db.sqlite3 check requires a non-empty file on purpose. Django creates the
    database file the moment it opens a connection, so a single failed run in an
    unconfigured checkout leaves a 0-byte db.sqlite3 behind — which would then make that
    directory look like a valid data root forever after, and turn this check into a
    one-shot. A real database is never empty.
    """
    if (path / "jobs").is_dir():
        return True
    db = path / "db.sqlite3"
    return db.is_file() and db.stat().st_size > 0


def data_root() -> Path:
    """The directory holding this user's job-search data.

    Nothing configured is an error, not a guess: a fresh clone that fell through to some
    default would get an empty sqlite file and `no such table: tracker_application` three
    frames deep in Django, where the useful answer is "run init".
    """
    configured = _configured()

    if configured is None:
        raise DataRootError(
            "No data root configured.\n"
            "\n"
            "If you have a data root already, point at it:\n"
            f"    echo /path/to/your-data > {POINTER_FILE}\n"
            f"  or set ${ENV_VAR}\n"
            f"  or put it in {GLOBAL_SETTINGS_FILE}:\n"
            f"        [{GLOBAL_SECTION}]\n"
            f"        {GLOBAL_DATA_ROOT_KEY} = /path/to/your-data\n"
            "\n"
            "If this is a new setup, create one:\n"
            "    /jobstudio init"
        )

    root, source = configured
    if not root.is_dir():
        raise DataRootError(
            f"Data root does not exist: {root}\n"
            f"  configured by: {source}\n"
            "Fix that path, or remove it to fall back to the next layer."
        )
    if not looks_like_data_root(root):
        raise DataRootError(
            f"Data root has no job-search data in it: {root}\n"
            f"  configured by: {source}\n"
            f"  expected:      {' or '.join(MARKERS)}\n"
            "Check the path is right — an empty directory here usually means a typo."
        )
    return root


def describe() -> str:
    """One-line summary, for diagnostics and `status`."""
    root = data_root()
    return f"data root: {root} (via {_configured()[1]})"


def resolution_chain() -> str:
    """Every layer and what it says — not just the winner.

    Layered config acquires a "why isn't it picking that up" failure mode the moment
    there is more than one layer, and the answer is almost always that something more
    specific is winning silently. So print the whole ladder, marking the layer that won.
    """
    env = os.environ.get(ENV_VAR, "").strip()

    pointer = ""
    if POINTER_FILE.is_file():
        pointer = next(
            (ln.strip() for ln in POINTER_FILE.read_text().splitlines()
             if ln.strip() and not ln.strip().startswith("#")), "")

    try:
        glob = _from_global_settings()
    except DataRootError as exc:
        glob = f"!! {exc}"

    layers = [
        (f"${ENV_VAR}", env),
        (str(POINTER_FILE), pointer),
        (f"{GLOBAL_SETTINGS_FILE} [{GLOBAL_SECTION}] {GLOBAL_DATA_ROOT_KEY}", glob or ""),
    ]

    won = False
    lines = []
    for name, value in layers:
        if value and not won:
            marker, won = "->", True
        else:
            marker = "  "
        lines.append(f"  {marker} {name}: {value or '(not set)'}")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    if "--path" in sys.argv:
        # Bare path, for anything that needs to consume it — the skill's <DATA>,
        # shell scripts, `cd $(...)`. Never decorate this output.
        print(data_root())
    elif "--chain" in sys.argv:
        print(resolution_chain())
    else:
        print(describe())
