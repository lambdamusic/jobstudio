"""Who this job search belongs to (plan §3.4).

Replaces the hardcoded author-name literals that were baked into
generated filenames, .docx metadata and CV rendering. Nothing about the toolkit should
name its author.

Resolution order — and the second layer is the point:

1. ``<data-root>/config.yaml``, the ``identity:`` block. Written by ``init``.
2. The ``# Name`` heading of the base functional CV. Every user has one, it is already
   the canonical place the name lives, and ``render.py`` has always parsed it.
3. ``IdentityError``, naming both of the above.

Layer 2 is what makes this change safe to land on an existing installation. Without it,
adding ``config.yaml`` as the only source would break every user who does not yet have
one — including the person this was refactored out of — and "run init first" is a poor
answer for someone whose setup already works. With it, an existing data root keeps
working untouched and ``config.yaml`` becomes an override rather than a prerequisite.

Deliberately NOT in ``config.py``: that module is stdlib-only because ``appfolder.py``
imports it at module level, and reading YAML needs PyYAML. Identity is also a different
question from where the data lives — ``config.py`` answers *where*, this answers *who*.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import config


class IdentityError(RuntimeError):
    """No identity could be resolved, and guessing one is not an option."""


@dataclass(frozen=True)
class Identity:
    full_name: str
    slug: str
    email: str = ""
    location: str = ""

    @property
    def footer_name(self) -> str:
        return self.full_name


def slugify(name: str) -> str:
    """"Alex Rivera" -> "alex-rivera". Matches the existing filename convention."""
    s = re.sub(r"[^\w\s-]", "", name.strip().lower(), flags=re.UNICODE)
    return re.sub(r"[\s_]+", "-", s).strip("-")


def _from_config_yaml(root: Path) -> Identity | None:
    path = root / "config.yaml"
    if not path.is_file():
        return None
    try:
        import yaml
    except ImportError:  # pragma: no cover - PyYAML is a hard dependency elsewhere
        return None
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise IdentityError(f"Could not parse {path}:\n  {exc}") from exc

    block = (data.get("identity") or {}) if isinstance(data, dict) else {}
    name = str(block.get("full_name") or "").strip()
    if not name:
        return None
    return Identity(
        full_name=name,
        slug=str(block.get("slug") or "").strip() or slugify(name),
        email=str(block.get("email") or "").strip(),
        location=str(block.get("location") or "").strip(),
    )


def _from_base_cv(root: Path) -> Identity | None:
    """The `# Name` heading of the base functional CV — the pre-config.yaml source."""
    cv = root / "jobs" / "cv" / "base" / "cv_functional.md"
    if not cv.is_file():
        return None
    m = re.search(r"^#\s+(.+)$", cv.read_text(), re.MULTILINE)
    if not m:
        return None
    name = m.group(1).strip()
    return Identity(full_name=name, slug=slugify(name)) if name else None


@lru_cache(maxsize=8)
def _load(root_str: str) -> Identity | None:
    root = Path(root_str)
    return _from_config_yaml(root) or _from_base_cv(root)


def load() -> Identity | None:
    """The identity, or None if nothing on disk names one.

    Cached per data root: this is read once per generated filename otherwise, and the
    key is the root rather than nothing at all so a test that repoints the data root
    still sees the right person.
    """
    return _load(str(config.data_root()))


def require() -> Identity:
    """The identity, or a loud error — never a guess.

    Used where the answer ends up in a filename or a document someone sends to an
    employer. A wrong name there is worse than a failed command.
    """
    found = load()
    if found is not None:
        return found
    root = config.data_root()
    raise IdentityError(
        "Could not work out whose job search this is.\n"
        f"  looked for: {root / 'config.yaml'}  (an `identity:` block)\n"
        f"  then:       {root / 'jobs' / 'cv' / 'base' / 'cv_functional.md'}  (its `# Name` heading)\n"
        "\n"
        "Fix by running `/jobstudio init`, or by adding to config.yaml:\n"
        "    identity:\n"
        "      full_name: Your Name\n"
    )


def slug() -> str:
    """The filename slug — `alex-rivera`."""
    return require().slug


def full_name() -> str:
    return require().full_name


if __name__ == "__main__":
    who = load()
    print(who if who else "no identity found")
