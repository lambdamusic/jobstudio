"""Parsers for the parts of jobs/ that are still files on disk.

Applications and companies now live in the database; their markdown parsers were removed
in Phase 6. What remains parses things whose truth is genuinely the filesystem: target
YAMLs, CV variant and base-CV filenames, cover letters, scans, and application folders.

Deliberately free of Django imports so it can be exercised standalone.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

import yaml

from appfolder import is_cover_letter_filename

LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def strip_links(text: str) -> str:
    return LINK_RE.sub(r"\1", text)


def first_url(text: str) -> str:
    m = LINK_RE.search(text)
    if m:
        return m.group(2)
    m = re.search(r"https?://\S+", text)
    return m.group(0).rstrip(".,;·") if m else ""


def parse_date(text: str) -> date | None:
    m = DATE_RE.search(text or "")
    if not m:
        return None
    try:
        return datetime.strptime(m.group(0), "%Y-%m-%d").date()
    except ValueError:
        return None


def _table_rows(text: str, min_cells: int):
    """Yield (cells, current_h2) for every data row of every markdown table in `text`."""
    in_table = False
    heading = ""
    for line in text.splitlines():
        m = re.match(r"^## (.+)$", line)
        if m:
            heading = m.group(1).strip()
            in_table = False
            continue
        if line.startswith("| #") or line.startswith("|---|"):
            in_table = True
            continue
        if in_table:
            if not line.startswith("|"):
                in_table = False
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) < min_cells or cells[0] in ("#", "---"):
                continue
            yield cells, heading


# ---------------------------------------------------------------------------
# areas.md + targets/*.yaml
# ---------------------------------------------------------------------------

def parse_areas_md(path: Path) -> dict[str, dict]:
    """Map area slug -> {heading, fit, notes}, keyed off each section's `Config:` line."""
    if not path.is_file():
        return {}
    out: dict[str, dict] = {}
    sections = re.split(r"^## ", path.read_text(), flags=re.M)[1:]
    for section in sections:
        heading, _, body = section.partition("\n")
        m = re.search(r"targets/([a-z0-9-]+)\.yaml", body)
        if not m:
            continue
        fit_line = re.search(r"^\*\*Fit:\*\*\s*(.*)$", body, re.M)
        notes = ""
        nm = re.search(r"^### Notes\s*\n(.*?)(?=\n###|\Z)", body, re.S | re.M)
        if nm:
            notes = nm.group(1).strip()
        out[m.group(1)] = {
            "heading": heading.strip(),
            "fit": fit_line.group(1).count("★") if fit_line else 0,
            "notes": notes,
        }
    return out


def _flatten_yaml_list(items) -> list[str]:
    """Normalise a YAML list to strings.

    Several target files contain unquoted entries with a colon, e.g.

        - SN SciGraph: 1B+ fact production knowledge graph

    which YAML silently reads as a mapping rather than a string, so the entry arrives as
    {'SN SciGraph': '1B+ fact production knowledge graph'}. Rejoin those as "key: value"
    so they read the way they were written.

    The YAML files were fixed on 2026-09-08 (the six affected entries are now quoted), so
    this should find nothing. It stays as a safety net for this parser's own consumers
    (the web app's target display). test_target_yaml_has_no_unquoted_colon_entries
    guards the source files themselves.
    """
    out: list[str] = []
    for item in items or []:
        if isinstance(item, dict):
            out.extend(f"{k}: {v}" for k, v in item.items())
        else:
            out.append(str(item))
    return out


def parse_targets(targets_dir: Path) -> list[dict]:
    """One dict per jobs/targets/*.yaml."""
    out: list[dict] = []
    for yaml_path in sorted(targets_dir.glob("*.yaml")):
        data = yaml.safe_load(yaml_path.read_text()) or {}
        out.append({
            "slug": yaml_path.stem,
            "name": (data.get("name") or yaml_path.stem).strip(),
            "description": (data.get("description") or "").strip(),
            "emphasis": _flatten_yaml_list(data.get("emphasis")),
            "key_terms": _flatten_yaml_list(data.get("key_terms")),
            "expand_sections": _flatten_yaml_list(data.get("expand_sections")),
            "condense_sections": _flatten_yaml_list(data.get("condense_sections")),
        })
    return out


# ---------------------------------------------------------------------------
# application folders / cover letters / scans / cv variants
# ---------------------------------------------------------------------------

def find_application_folders(applications_dir: Path) -> dict[int, Path]:
    """Map application number -> its folder."""
    folders: dict[int, Path] = {}
    if not applications_dir.is_dir():
        return folders
    for folder in sorted(applications_dir.iterdir()):
        if not folder.is_dir():
            continue
        m = re.match(r"^(\d+)-", folder.name)
        if m:
            folders[int(m.group(1))] = folder
    return folders


def find_cover_letters(folder: Path) -> list[dict]:
    """Cover letters in an application folder — a `cover-letter-*.md` file (old naming) or
    a `*-cover-letter-*.md` file (new naming, decided 2026-09-08), or an older-style
    `cover-letter-*/` directory holding one or more markdown files."""
    out: list[dict] = []
    for entry in sorted(p for p in folder.iterdir() if is_cover_letter_filename(p.name)):
        if entry.is_file() and entry.suffix == ".md":
            out.append({"path": entry, "date": parse_date(entry.name), "label": entry.stem})
        elif entry.is_dir():
            for md in sorted(entry.glob("*.md")):
                out.append({
                    "path": md,
                    "date": parse_date(entry.name) or parse_date(md.name),
                    "label": f"{entry.name}/{md.stem}",
                })
    return out


def find_scans(scans_dir: Path) -> list[dict]:
    out: list[dict] = []
    if not scans_dir.is_dir():
        return out
    for md in sorted(scans_dir.glob("*.md")):
        d = parse_date(md.name)
        if d:
            out.append({"path": md, "date": d, "label": md.stem})
    return out


def find_base_cvs(base_dir: Path) -> list[dict]:
    """Master CVs in jobs/cv/base/ (cv_chronological, cv_functional)."""
    out: list[dict] = []
    if not base_dir.is_dir():
        return out
    for md in sorted(base_dir.glob("*.md")):
        if md.name.startswith("."):
            continue
        out.append({"slug": md.stem, "path": md, "is_functional": "functional" in md.stem})
    return out


# ---------------------------------------------------------------------------
# Scan report structure — jobs/scans/*.md into tabbed sections
# ---------------------------------------------------------------------------

_H1_RE = re.compile(r"\A\s*#\s+.*?\n")
_H2_RE = re.compile(r"(?m)^## (?P<title>.+?)\s*$")
_SLUG_RE = re.compile(r"[^a-z0-9]+")
# Report headings carry a parenthetical explainer for the full-page reader
# ("Unscored (no target profile for this category)") — too long for a tab label, which
# has the same explanation available in the panel heading right below it.
_TRAILING_PAREN_RE = re.compile(r"\s*\([^)]*\)\s*$")

# A section body that amounts to nothing worth its own tab ("_None._" for "Needs
# manual review" when scoring never failed).
_EMPTY_BODIES = {"_none._", "none."}

# Tab labels short enough to sit in the tab bar; the full heading is still shown as the
# panel's own sub-heading (panel-heading), right above the explainer paragraph.
_SHORT_TITLE_OVERRIDES = {
    "filtered-out-before-scoring": "Filtered Out",
    "excluded-by-location": "Excluded",
    "no-open-roles-found": "No open roles",
}

# Rows/bullets that count as one "item" for a tab's count badge: a markdown table row
# opening with a bold company name (`| **Company**`) or a bare link (`| [Title](url)`,
# used by the company-grouped Strong/Other matches tables, where the company is a
# heading rather than repeated per row), or a bullet list item opening the same way
# (`- **Company**`) or with a bare link (`- [Title](url)`, used by "No open roles
# found" and the company-grouped Filtered out/Excluded by location lists).
_COUNTABLE_RE = re.compile(r"(?m)^(?:\| \*\*|\| \[|- \*\*|- \[)")


def _slugify(text: str) -> str:
    return _SLUG_RE.sub("-", text.lower()).strip("-")


# "### Company" or "### Company (12)" — the per-company subheadings scan-portals.py
# emits for Strong/Other matches and the two before-scoring exclusion buckets.
_COMPANY_HEADING_RE = re.compile(r"(?m)^### (?P<name>.+?)(?:\s+\((?P<count>\d+)\))?\s*$")

# The one "### " subheading in "## Strong matches" that isn't a company group — the
# flat "Strong matches — wrong location" list (see scan-portals.py write_report). Kept
# out of the anchor/jump-summary treatment below.
_NON_COMPANY_SUBHEADING_RE = re.compile(r"wrong location", re.IGNORECASE)

# Sections whose "### " subheadings are per-company groups worth an id + a jump-to-company
# summary above the panel body (split_scan_sections attaches `companies` for these).
COMPANY_GROUPED_KEYS = {
    "strong-matches", "other-matches", "filtered-out-before-scoring", "excluded-by-location",
}

# Of those, the two where the postings inside each company are dumped in fetch order
# rather than a meaningful order (Strong/Other matches are sorted by combined score,
# which the web view leaves alone) — here the view alphabetises for easier scanning.
ALPHA_SORT_KEYS = {"filtered-out-before-scoring", "excluded-by-location"}

# Short anchor-id prefixes for COMPANY_GROUPED_KEYS. The same company (e.g. "Example
# Corp") shows up under more than one tab, and every tabpanel lives in the DOM at once
# (tabs.js only toggles the `hidden` attribute) — so anchor ids need to be unique across
# the whole page, not just within one section, or the browser jumps to the first (maybe
# hidden) match instead of the one in the tab currently open.
_ANCHOR_PREFIX = {
    "strong-matches": "strong",
    "other-matches": "other",
    "filtered-out-before-scoring": "filtered",
    "excluded-by-location": "excluded",
}


def _sort_bullet_lines(text: str) -> str:
    """Alphabetise runs of consecutive '- [Title](url)...' lines by their link text
    (case-insensitive), leaving blank lines and the italic category line in place."""
    lines = text.split("\n")
    out: list[str] = []
    buf: list[str] = []

    def flush():
        if buf:
            buf.sort(key=lambda line: (
                m.group(1).casefold() if (m := LINK_RE.search(line)) else line.casefold()))
            out.extend(buf)
            buf.clear()

    for line in lines:
        if line.startswith("- "):
            buf.append(line)
        else:
            flush()
            out.append(line)
    flush()
    return "\n".join(out)


def _annotate_companies(body: str, prefix: str, sort_items: bool) -> tuple[str, list[dict]]:
    """Give every '### Company (n)' heading a stable, page-unique anchor id — via
    attr_list, already one of MD_EXTENSIONS — and return the {name, count, anchor} list
    found, for a jump-to-company summary rendered above the panel body. `prefix`
    (see _ANCHOR_PREFIX) keeps ids unique across sections that share a company.

    When `sort_items`, the company blocks and the postings within each are alphabetised
    (ALPHA_SORT_KEYS); otherwise the original order from scan-portals.py — already
    alphabetical by company, sorted by combined score within each — is left untouched.
    """
    matches = [m for m in _COMPANY_HEADING_RE.finditer(body)
               if not _NON_COMPANY_SUBHEADING_RE.search(m.group("name"))]
    if not matches:
        return body, []

    chunks = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        chunks.append((m, body[start:end]))
    if sort_items:
        chunks.sort(key=lambda pair: pair[0].group("name").strip().casefold())

    used_slugs: set[str] = set()
    companies: list[dict] = []
    out_parts: list[str] = [body[:matches[0].start()]]
    for m, chunk in chunks:
        name = m.group("name").strip()
        count = m.group("count")
        slug = f"{prefix}-{_slugify(name) or 'company'}"
        anchor, n = slug, 2
        while anchor in used_slugs:
            anchor = f"{slug}-{n}"
            n += 1
        used_slugs.add(anchor)
        companies.append({"name": name, "count": int(count) if count else None, "anchor": anchor})

        heading_line, sep, rest = chunk.partition("\n")
        if sort_items:
            rest = _sort_bullet_lines(rest)
        out_parts.append(f"{heading_line.rstrip()} {{: #{anchor} }}{sep}{rest}")

    return "".join(out_parts), companies


def split_scan_sections(body_md: str) -> list[dict]:
    """Split a scan report into its top-level ('## ') sections, for a tabbed view.

    Each section: {key, title, short_title, body, count, companies}. `key` is a stable
    slug used both as the tab's data-tab value and, for the Unscored section
    specifically, as a fixed "unscored" key the template can special-case to render the
    location split (see split_unscored_by_location) instead of the raw bullet list.
    `short_title` is a tab-bar-length label — an explicit override for the long
    headings (_SHORT_TITLE_OVERRIDES) or, failing that, the heading with any trailing
    parenthetical dropped ("Unscored (no target profile...)" -> "Unscored"); `title`
    (the full heading) is still shown as the panel's own sub-heading. `companies` is the
    jump-to-company summary list for company-grouped sections (COMPANY_GROUPED_KEYS) —
    empty for every other section. Sections with no real content (an empty body, or the
    literal "_None._" placeholder) are dropped — an empty tab is never worth showing.
    Summary and Matches are then folded into one section (see
    _merge_summary_and_matches) so the landing tab shows both without an extra click.
    """
    text = _H1_RE.sub("", body_md, count=1)
    headings = list(_H2_RE.finditer(text))
    sections: list[dict] = []
    for i, m in enumerate(headings):
        title = m.group("title").strip()
        start = m.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        body = text[start:end].strip("\n")
        if not body or body.strip().lower() in _EMPTY_BODIES:
            continue
        key = "unscored" if title.lower().startswith("unscored") else (_slugify(title) or f"section-{i}")
        companies: list[dict] = []
        if key in COMPANY_GROUPED_KEYS:
            body, companies = _annotate_companies(
                body, prefix=_ANCHOR_PREFIX[key], sort_items=key in ALPHA_SORT_KEYS)
        short_title = _SHORT_TITLE_OVERRIDES.get(key) or (_TRAILING_PAREN_RE.sub("", title).strip() or title)
        sections.append({
            "key": key,
            "title": title,
            "short_title": short_title,
            "body": body,
            "count": len(_COUNTABLE_RE.findall(body)) or None,
            "companies": companies,
        })
    return _merge_summary_and_matches(sections)


def _merge_summary_and_matches(sections: list[dict]) -> list[dict]:
    """Fold the Matches section into Summary, so the landing tab shows the stats and
    the scored matches together instead of splitting them across two clicks. Keeps
    Summary's key/position (first tab, stable #summary link) and Matches' count (more
    useful on the badge than Summary's, which has none of its own). A no-op if either
    section is missing — no crash on a report shape that doesn't have both.

    scan-portals.py stopped emitting "## Summary" / "## Matches" headings on 2026-09-14
    (Summary's stats moved into Coverage notes; Matches split into Strong/Other matches
    directly, no merge needed) — so for any report generated since, this is a no-op.
    Left in place because it's still needed for every report from before that date.
    """
    by_key = {s["key"]: i for i, s in enumerate(sections)}
    if "summary" not in by_key or "matches" not in by_key:
        return sections
    summary_i, matches_i = by_key["summary"], by_key["matches"]
    summary, matches = sections[summary_i], sections[matches_i]
    summary["body"] = f"{summary['body']}\n\n## {matches['title']}\n\n{matches['body']}"
    summary["count"] = matches["count"]
    return [s for i, s in enumerate(sections) if i != matches_i]


_UNSCORED_BULLET_RE = re.compile(
    r"^- \*\*(?P<company>.+?)\*\* — \[(?P<title>.+?)\]\((?P<url>.+?)\)"
    r"(?: — (?P<location>.+))?$",
    re.MULTILINE,
)

# A coarse keyword check on raw, unclassified ATS location text — not the per-posting
# LLM location judgement the scored Matches table gets (which reads the full listing
# and distinguishes globally-remote from country-restricted remote). Good enough for
# "worth a look" triage on the Unscored section only.
_UK_OR_REMOTE_HINT_RE = re.compile(
    r"\b(united kingdom|u\.k\.|uk|england|scotland|wales|northern ireland|london|"
    r"edinburgh|glasgow|manchester|birmingham|belfast|cardiff|bracknell|remote)\b",
    re.IGNORECASE,
)


def split_unscored_by_location(body: str) -> tuple[list[dict], list[dict]]:
    """Bullet-list entries in the Unscored section, split into "mentions UK or
    remote" vs "other" by a plain keyword check on the raw location text. Returns
    (likely, other) — each a list of {company, title, url, location}."""
    likely: list[dict] = []
    other: list[dict] = []
    for m in _UNSCORED_BULLET_RE.finditer(body):
        entry = {k: (v or "").strip() for k, v in m.groupdict().items()}
        bucket = likely if _UK_OR_REMOTE_HINT_RE.search(entry["location"]) else other
        bucket.append(entry)
    return likely, other


_SUMMARY_STAT_RE = re.compile(
    r"^- (?P<key>Companies scanned|Roles found|Scored matches): (?P<value>\d+)"
    r"(?: \((?P<strong>\d+) strong, (?P<other>\d+) other\))?",
    re.MULTILINE,
)
_SUMMARY_STAT_KEYS = {
    "Companies scanned": "companies_scanned",
    "Roles found": "roles_found",
    "Scored matches": "scored_matches",
}


def scan_summary_stats(body_md: str) -> dict:
    """Pull the headline coverage numbers out of a scan report's Summary bullets, for
    the dashboard's "Latest portal scans" panel. Works whether the report has a
    top-level '## Summary' (reports before 2026-09-14) or the stats nested under
    '## Coverage notes' / '### Summary' (from then on) — it just scans the whole body
    for the three bullet lines by name rather than anchoring to a heading. A report
    missing a stat (or of a shape this doesn't recognise) simply omits that key, so the
    template can tell "zero" from "not found"."""
    stats: dict[str, int] = {}
    for m in _SUMMARY_STAT_RE.finditer(body_md):
        stats[_SUMMARY_STAT_KEYS[m.group("key")]] = int(m.group("value"))
        if m.group("strong") is not None:
            stats["strong_matches"] = int(m.group("strong"))
            stats["other_matches"] = int(m.group("other"))
    return stats
