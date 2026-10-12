"""A reference to a markdown file, in rendered prose, becomes a link to its page (TODO `#78`).

The skill writes cross-references as paths — `jobs/notes/interviewing/interview-technique.md`, usually
in backticks — because a path is what an agent reading the file can follow. On a page it
was dead text, though the note it named had a page of its own. This maps a path to the
page that renders that file, and leaves it as text when there is none: a reference is
only ever turned into a link that works, never into a guess.

Forms resolved, relative to the data root (a leading `<DATA>/` is dropped):

    jobs/notes/[<group>/]<slug>.md        ->  /notes/<slug>/
    jobs/companies/<slug>.md              ->  /companies/<slug>/
    jobs/profile/stocktake.md             ->  /profile/
    jobs/cv/base/<slug>.md                ->  /cvs/base/<slug>/
    jobs/applications/<folder>/<file>     ->  /applications/<num>/#<that file's anchor>

A bare filename (`stocktake.md`, `interview-technique.md`, a file named by the folder
convention) resolves when exactly one of those places holds it. `notes.md` and `job.md`
exist in every application folder, so bare they stay text.

Every target is a page the static build also writes, so the same links hold on the
published site; its link check is what proves it.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

from django.conf import settings

# A path ending in .md: `jobs/notes/x.md`, `<DATA>/jobs/...`, or a bare `x.md`. Path
# characters only, so the match stops at the punctuation that follows it in a sentence.
_REF = re.compile(r"(?:&lt;DATA&gt;/|<DATA>/)?(?:[\w.-]+/)*[\w.-]+\.md\b")
# What prose links are allowed to rewrite: a whole `<code>` span holding just a path, a
# markdown link pointing at a .md file, or a path in running text.
_CODE = re.compile(r"<code>([^<]+)</code>")
_HREF = re.compile(r'(<a\s[^>]*?href=")([^"#]+\.md)(#[^"]*)?(")')
# Text between tags, and the tags whose content is never touched: an existing link, a
# code block, and the bracketed `<code>` spans handled on their own.
_SKIP = re.compile(r"(<a\b.*?</a>|<pre\b.*?</pre>|<code>.*?</code>|<[^>]+>)", re.S | re.I)


def _data_root() -> Path:
    return Path(settings.DATA_ROOT)


def _app_target(folder_rel: str, name: str) -> str | None:
    """`/applications/<num>/#anchor` for `name` in application folder `folder_rel`."""
    from .models import Application, cv_anchor, file_anchor, round_anchor
    from appfolder import is_cover_letter_filename, is_cv_filename, is_interview_filename
    from .parsers import interview_stage, parse_date

    app = Application.objects.filter(folder=folder_rel).only("num").first()
    if app is None or not (_data_root() / folder_rel / name).is_file():
        return None
    base = f"/applications/{app.num}/"
    rel_name = Path(name).name
    if name == "notes.md":
        return base + "#notes"
    if name == "job.md":
        return base + "#job"
    if "/" not in name and is_interview_filename(rel_name):
        return base + "#" + round_anchor(interview_stage(rel_name), parse_date(rel_name))
    if "/" not in name and is_cover_letter_filename(rel_name):
        return base + "#letters"
    if "/" not in name and is_cv_filename(rel_name):
        return base + "#" + cv_anchor(rel_name)
    return base + "#" + file_anchor(name)


def _resolve_path(rel: str) -> str | None:
    """A data-root-relative path to its page, or None."""
    root = _data_root()
    parts = rel.split("/")
    # A note may sit in a group subfolder; its URL is the filename alone either way.
    if parts[:2] == ["jobs", "notes"] and len(parts) in (3, 4):
        return f"/notes/{Path(parts[-1]).stem}/" if (root / rel).is_file() else None
    if parts[:2] == ["jobs", "companies"] and len(parts) == 3:
        from .models import Company

        slug = Path(parts[2]).stem
        return f"/companies/{slug}/" if Company.objects.filter(slug=slug).exists() else None
    if rel == "jobs/profile/stocktake.md":
        return "/profile/" if (root / rel).is_file() else None
    if parts[:3] == ["jobs", "cv", "base"] and len(parts) == 4:
        return f"/cvs/base/{Path(parts[3]).stem}/" if (root / rel).is_file() else None
    if parts[:2] == ["jobs", "applications"] and len(parts) >= 4:
        return _app_target("/".join(parts[:3]), "/".join(parts[3:]))
    return None


def _resolve_bare(name: str) -> str | None:
    """A filename with no directory, when exactly one place holds it."""
    if name in ("notes.md", "job.md"):
        return None
    candidates = [f"jobs/companies/{name}", f"jobs/profile/{name}", f"jobs/cv/base/{name}"]
    notes = _data_root() / "jobs" / "notes"
    if notes.is_dir():
        candidates += [p.relative_to(_data_root()).as_posix() for p in notes.rglob(name)
                       if len(p.relative_to(notes).parts) <= 2]
    # A file named by the folder convention starts with its folder's name.
    m = re.match(r"(\d{3}-[a-z0-9-]+?)-", name)
    if m:
        apps = _data_root() / "jobs" / "applications"
        candidates += [f"jobs/applications/{d.name}/{name}"
                       for d in apps.glob(f"{name[:3]}-*") if name.startswith(f"{d.name}-")]
    hits = {url for c in candidates if (url := _resolve_path(c))}
    return hits.pop() if len(hits) == 1 else None


def resolve(ref: str) -> str | None:
    """The page for a file reference as written in prose, or None."""
    ref = html.unescape(ref).strip().strip("`")
    ref = ref.removeprefix("<DATA>/").removeprefix("./").removeprefix("/")
    if not ref.endswith(".md") or ".." in ref.split("/"):
        return None
    return _resolve_path(ref) if "/" in ref else _resolve_bare(ref)


def link_file_refs(rendered: str) -> str:
    """Rendered HTML with every resolvable file reference turned into a link."""
    if ".md" not in rendered:
        return rendered  # the common case, and it costs nothing

    def code(m: re.Match) -> str:
        url = resolve(m.group(1)) if _REF.fullmatch(m.group(1).strip()) else None
        return f'<a href="{url}">{m.group(0)}</a>' if url else m.group(0)

    def href(m: re.Match) -> str:
        url = resolve(m.group(2))
        return f"{m.group(1)}{url}{m.group(4)}" if url else m.group(0)

    def text(m: re.Match) -> str:
        url = resolve(m.group(0))
        return f'<a href="{url}">{m.group(0)}</a>' if url else m.group(0)

    parts = _SKIP.split(rendered)
    for i, part in enumerate(parts):
        if i % 2 == 0:
            parts[i] = _REF.sub(text, part)
        elif part.startswith("<code>"):
            parts[i] = _CODE.sub(code, part)
        elif part.lower().startswith("<a"):
            parts[i] = _HREF.sub(href, part)
    return "".join(parts)
