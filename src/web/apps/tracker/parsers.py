"""Parsers for the parts of jobs/ that are still files on disk.

Applications and companies now live in the database; their markdown parsers were removed
in Phase 6. What remains parses things whose truth is genuinely the filesystem: target
YAMLs, CV variant and base-CV filenames, cover letters, scans, and application folders.

Deliberately free of Django imports so it can be exercised standalone.
"""

from __future__ import annotations

import html
import re
from datetime import date, datetime
from pathlib import Path

import yaml

from appfolder import (
    interview_label,
    interview_stage,
    is_cover_letter_filename,
    is_interview_filename,
)

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
            "excludes": _flatten_yaml_list(data.get("excludes")),
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


def find_interviews(folder: Path) -> list[dict]:
    """Interview rounds in an application folder — one file per round, named
    `<application-id>-<person-slug>-interview-<stage>-<YYYY-MM-DD>.md` (2026-09-24).

    The date in the name is the date of the interview itself, not the date the file was
    written, so sorting on it is a real chronology of the process. Unlike cover letters
    there is no directory form to support: the convention is new, so there is no older
    layout to stay compatible with.
    """
    out: list[dict] = []
    for entry in sorted(p for p in folder.iterdir() if is_interview_filename(p.name)):
        if not entry.is_file():
            continue
        stage = interview_stage(entry.name)
        out.append({
            "path": entry,
            "date": parse_date(entry.name),
            "stage": stage,
            "label": interview_label(stage),
        })
    return out


# A round is split into collapsible `##` blocks, numbered, and indexed in the order the
# headings appear rather than against a canonical list.
#
# `#66` was planned against the canonical vocabulary from `subcommands/interview.md`
# step 4, with absent sections dimmed in place. The data killed it: rounds come in at
# least two shapes. One written *before* the call uses the prep vocabulary (Details /
# Prep / Questions to ask them / Study before / Outcome); one written *after* records
# what happened (Questions and answers / What to do differently). Indexed against one
# list, a post-interview round renders ten dimmed chips and two live ones.
#
# Document order also keeps the index agreeing with the page, which a highlight tracking
# scroll position depends on.
PRIVATE_SECTION_PREFIX = "private"


def first_heading(body_md: str) -> str:
    """The document's own `# Title`, or "" if it has none (`#73`).

    Notes are titled by their first line, and deriving a title from the filename instead
    mangles it — `ai-safety-pivot` title-cases to "Ai Safety Pivot". The file knows what
    it is called; ask it, and keep the slug only as a fallback.
    """
    for line in body_md.splitlines():
        if line.startswith("# ") and not line.startswith("## "):
            return line[2:].strip().rstrip("#").strip()
        if line.strip():
            break  # a title is the first thing or it is not the title
    return ""


# A full title is often "Short name — the longer description of what is in here". A tab
# can only show the first half, so this is where it is cut.
_TITLE_TAIL_RE = re.compile(r"\s+[—:–]\s+.*$")


def short_title(title: str) -> str:
    """The part of a title a tab label can hold."""
    return _TITLE_TAIL_RE.sub("", title).strip() or title


def section_slug(label: str) -> str:
    """Slug for one section heading. Shared by the parser, the nav's hrefs and the
    `number_sections` filter that stamps ids onto the rendered headings, so the three
    cannot drift. Always fed a label that `section_label()` has already cleaned."""
    return _slugify(label)


# A heading that numbers itself — "## 4. Multi-tenant isolation". Interview rounds never
# do; notes and study files written outside this app often do (`#72`).
_SELF_NUMBERED_RE = re.compile(r"^\d+[.)]\s+")

# Inline emphasis and code spans inside a heading. A pill is plain text, so `**Trend 1**`
# would otherwise show its asterisks (`#73`). Paired delimiters only — a lone `*` in a
# heading is a literal asterisk and stays one.
_EMPHASIS_RE = [
    (re.compile(r"\*\*(.+?)\*\*", re.S), r"\1"),
    (re.compile(r"__(.+?)__", re.S), r"\1"),
    (re.compile(r"(?<![*\w])\*(?!\s)(.+?)(?<!\s)\*(?![*\w])", re.S), r"\1"),
    (re.compile(r"`(.+?)`", re.S), r"\1"),
]


def section_label(raw: str) -> str:
    """The text of a `##`/`###` heading, as a pill can show it.

    Two things to take off, both found the moment this stopped being interview-only
    (`#72`) and got pointed at notes and study files:

    **Link markup.** A heading written ``## [Multi-tenant](https://en.wikipedia.org/…)
    isolation`` put the whole URL in the pill *and* in the slug, giving an anchor 90
    characters long. The pills render as plain text, so the label has to be plain text.

    **The author's own number.** The pill already carries a generated `1 / 1.1 / 2`, so a
    self-numbered heading rendered as "4 4. Multi-tenant…" — in the summary line as well
    as the pill. Ours is positional and matches the body, so it is the one to keep.

    **Emphasis and code spans** (`#73`), for the same reason as the link markup: a note
    whose subheadings are written `### **Trend 1 — ...**` showed its asterisks in every
    pill. Paired delimiters only, so a lone asterisk in a heading survives as itself.
    """
    out = _SELF_NUMBERED_RE.sub("", strip_links(raw).strip())
    for pattern, repl in _EMPHASIS_RE:
        out = pattern.sub(repl, out)
    return out.strip()


# The Q/A convention of interview files, and of any note or study file that borrows it: a
# line opening `**Q:** …`, optionally as a bullet. Only the five markers the prep template
# uses (Q and A, plus STAR). Shared with `mark_qa`, which colours what this finds — the two
# have to agree on what a question is, because the page numbers questions by position.
QA_OPENER = re.compile(r"^(?P<lead>[ \t]*(?:[-*+][ \t]+)?)\*\*(?P<who>Q|A|S|T|R):\*\*")
# Anything that ends a wrapped question: a blank line, a heading, or a new list item.
QA_BREAK = re.compile(r"^(?:[ \t]*$|[ \t]*#|[ \t]*(?:[-*+]|\d+[.)])[ \t])")

# A heading that is itself the question. Rounds written before the `**Q:**` convention
# (2026-09-24) did this — `#### Why do you want to leave?`, `### A1. "Walk me through a
# platform you architected."` — and so does the answer bank, `### "Tell me about
# yourself"`. Loose for interview rounds, where a heading that asks or quotes anything is
# a question. Strict everywhere else (2026-10-15), where headings are topics and a quoted
# product name is common: the heading has to open with the quote, after an optional
# `A1.`-style label, or end with a question mark.
QUESTION_HEADING = re.compile(r'\?|"[^"]+"|\u201c[^\u201d]+\u201d')
QUESTION_HEADING_STRICT = re.compile(r'^(?:[A-Z]?\d+[.)][ \t]*)?["\u201c]|\?[ \t]*$')


def is_question_heading(label: str, loose: bool = False) -> bool:
    """Whether a heading's text asks the question its section answers."""
    return bool((QUESTION_HEADING if loose else QUESTION_HEADING_STRICT).search(label))


def _is_fence(line: str) -> bool:
    return line.startswith("```") or line.startswith("~~~")


def _unique_sub_anchor(slug: str, block: dict, blocks: list[dict]) -> str:
    """A `###` anchor no other heading in the document already uses (2026-10-14).

    A note that gives every `##` the same subheadings — What it is, Stack, Scale — minted
    the same id once per section, and every pill and link landed on the first. The first
    use keeps the bare slug, so links written before this still resolve; a repeat is
    scoped by its section's slug, and numbered only if that is taken too. Every `###`
    gets an entry, which `number_sections` relies on: it stamps ids by position.
    """
    used = {b["anchor"] for b in blocks} | {s["anchor"] for b in blocks for s in b["subsections"]}
    if slug not in used:
        return slug
    candidate, n = f"{block['anchor']}-{slug}", 2
    while candidate in used:
        candidate, n = f"{block['anchor']}-{slug}-{n}", n + 1
    return candidate


def _add_question(block: dict, text: str) -> None:
    """Record one `**Q:**` question under the heading it sits beneath: the last `###` so
    far, or the `##` itself when it comes before any. Numbered later, once the block is
    complete (see `_number_questions`)."""
    sub = block["subsections"][-1] if block["subsections"] else None
    block["questions"].append({"label": section_label(text), "sub": sub})


def _number_questions(block: dict) -> None:
    """Number and anchor a block's questions, now that its headings are all known (2026-10-15).

    A question is numbered under its heading: the third under `3.1` is `3.1.3`. One that
    comes before the first `###` takes `3.0.n` when the block has subsections, so it can't
    be mistaken for the `3.1` below it, and plain `3.n` when it has none. The anchor
    extends the heading's, so a link to a question survives the section being renumbered.
    """
    counts: dict[str, int] = {}
    for q in block["questions"]:
        sub = q.pop("sub")
        if sub is not None:
            head, anchor = sub["number"], sub["anchor"]
        else:
            head = f"{block['number']}.0" if block["subsections"] else block["number"]
            anchor = block["anchor"]
        counts[anchor] = counts.get(anchor, 0) + 1
        q["number"] = f"{head}.{counts[anchor]}"
        q["anchor"] = f"{anchor}--q{counts[anchor]}"
        q["parent"] = anchor


def split_sections(body_md: str) -> dict:
    """One markdown document, split for the collapsible reading view.

    Written for interview rounds (`#66`) and generalised for My notes and Other files
    (`#72`) — it only ever knew about `##` and `###`, so the generalisation was a rename.
    Use `sectioned()` rather than calling this directly unless you need the raw split.

    Returns `preamble` (anything before the first `##` — the Date/With/Format line in
    most interview rounds, short and always wanted, so it is never collapsed), and
    `blocks`: one per `##`, each carrying its own markdown and its `###` subsections.

    **Sections are numbered** — `1`, `1.1`, `1.2`, `2` — because the index is a flat row
    of pills, where nesting is otherwise invisible: "What they asked" sitting under
    "Outcome" reads as a sibling of it. The number is the only thing in a one-line pill
    that can carry depth. Numbers are positional, so they renumber if a round is edited;
    the slug, not the number, is what anchors a link.

    Anchors are unprefixed here; `sectioned()` scopes them. Every page that uses this
    stacks more than one document — the Interviews tab its rounds, Other files its
    files — so ids have to stay unique across the page, not just within a document.
    """
    lines = body_md.splitlines()
    preamble: list[str] = []
    blocks: list[dict] = []
    in_fence = False
    question: list[str] | None = None  # the lines of a `**Q:**` still being read

    def end_question():
        nonlocal question
        if question is not None and blocks:
            _add_question(blocks[-1], " ".join(question))
        question = None

    for raw in lines:
        line = raw.strip()
        if question is not None:
            opener = QA_OPENER.match(raw)
            if opener or QA_BREAK.match(raw) or _is_fence(line):
                end_question()
            else:
                question.append(line)
        if _is_fence(line):
            in_fence = not in_fence
        is_h2 = not in_fence and line.startswith("## ") and not line.startswith("### ")
        is_h3 = not in_fence and line.startswith("### ") and not line.startswith("#### ")
        opener = None if in_fence else QA_OPENER.match(raw)
        if opener and opener.group("who") == "Q" and blocks and not is_h2:
            question = [raw[opener.end():].strip()]

        if is_h2:
            label = section_label(line[3:].rstrip("#"))
            slug = section_slug(label)
            blocks.append({
                "number": str(len(blocks) + 1),
                "label": label,
                "anchor": slug,
                "private": slug.startswith(PRIVATE_SECTION_PREFIX),
                "lines": [],
                "subsections": [],
                "questions": [],
            })
            continue

        if not blocks:
            preamble.append(raw)
            continue

        block = blocks[-1]
        if is_h3:
            label = section_label(line[4:].rstrip("#"))
            block["subsections"].append({
                "number": f"{block['number']}.{len(block['subsections']) + 1}",
                "label": label,
                "anchor": _unique_sub_anchor(section_slug(label), block, blocks),
                "question": is_question_heading(label),
            })
        block["lines"].append(raw)
    end_question()

    for block in blocks:
        block["body_md"] = "\n".join(block.pop("lines")).strip("\n")
        _number_questions(block)

    # The leading `# Title` is dropped here rather than by `strip_h1` in the template:
    # every round file opens with one, the page renders the title itself, and leaving it
    # in means a preamble that is empty after filtering but still truthy — an empty
    # styled box on most rounds.
    text = "\n".join(preamble).strip("\n")
    text = re.sub(r"\A\s*#\s+.*?(?:\n|\Z)", "", text, count=1).strip("\n")
    return {"preamble": text, "blocks": blocks}


def subsection_md(block_md: str, slug: str) -> str | None:
    """The body of the `###` subsection whose heading slugs to `slug`, from one block's
    markdown — the lines after that heading, up to the next `###` or the block's end.
    None when there is no such heading. Fence-aware, like `split_sections`.

    For pulling one part of a document onto another page: a round's tasks out of
    `notes.md`'s `## To do` (`#84`). Feed it a block already through `sectioned()`, so a
    task checkbox keeps the file-wide index that writes the tick back to the right line.
    """
    out: list[str] | None = None
    in_fence = False
    for raw in block_md.splitlines():
        line = raw.strip()
        if _is_fence(line):
            in_fence = not in_fence
        if not in_fence and line.startswith("### ") and not line.startswith("#### "):
            if out is not None:
                break
            if section_slug(section_label(line[4:].rstrip("#"))) == slug:
                out = []
            continue
        if out is not None:
            out.append(raw)
    return "\n".join(out).strip("\n") if out is not None else None


# A task's round tag, `@hiring-manager`, as the last word of a line that has text before
# it — so an indented `@decorator` in a code sample is left alone. Shown as a badge.
_TASK_TAG = re.compile(r"(?<=\S[ \t])@([a-z][a-z0-9-]*)[ \t]*$", re.M)

# The "How this list works" paragraph that opens `## To do` (`TODO_GUIDE` in
# `src/appfolder.py`). It explains the file to whoever edits it by hand, so on the page it
# is classed as a muted how-to note (`howto-note`, shared with the answer bank's intros)
# rather than read as part of the list.
_TODO_GUIDE = re.compile(r"(?m)^\*How this list works\.\*(?:.+\n?)+")

# A top-level list item, which runs until the next line that is neither blank nor indented.
_ITEM = re.compile(r"^(?:[-*+]|\d+[.)])[ \t]+")


def tagged_md(block_md: str, tag: str) -> str | None:
    """The list items in one block that carry `@<tag>`, still under their `###` theme
    headings — the tag layout of `## To do`, where themes are the headings and the round
    is a marker on the task. None when no item carries the tag.

    Like `subsection_md`, feed it a block already through `sectioned()`, so each checkbox
    keeps its file-wide index: the same task shown here and on My notes is one line in
    notes.md, and ticking it on either page writes that line.
    """
    mark = re.compile(rf"(?<![\w@])@{re.escape(tag)}(?![\w-])", re.I)
    themes: list[tuple[str | None, list[str]]] = [(None, [])]
    item: list[str] | None = None
    in_fence = False

    def close():
        if item and mark.search("\n".join(item)):
            themes[-1][1].append("\n".join(item).rstrip())

    for raw in block_md.splitlines():
        line = raw.strip()
        if _is_fence(line):
            in_fence = not in_fence
            if raw[:1] not in " \t":  # an unindented fence is not part of any item
                close()
                item = None
                continue
        if not in_fence and line.startswith("### ") and not line.startswith("#### "):
            close()
            item = None
            themes.append((raw, []))
            continue
        if not in_fence and _ITEM.match(raw):
            close()
            item = [raw]
        elif item is not None and (not line or raw[:1] in " \t" or in_fence):
            item.append(raw)
        else:
            close()
            item = None
    close()
    parts = [(f"{h}\n\n" if h else "") + "\n".join(items)
             for h, items in themes if items]
    return "\n\n".join(parts) if parts else None


def section_index(blocks: list[dict]) -> list[dict]:
    """The contents: every block and subsection, in page order, with its number — and
    since 2026-10-15 every `**Q:**` question under the heading it sits beneath (level 4),
    so a question can be found without scrolling the answers."""
    out = []
    for block in blocks:
        questions = block.get("questions", [])

        def under(anchor):
            return [{"number": q["number"], "label": q["label"], "anchor": q["anchor"],
                     "level": 4, "question": True, "private": block["private"],
                     "parent": block["anchor"]}
                    for q in questions if q["parent"] == anchor]

        out.append({"number": block["number"], "label": block["label"],
                    "anchor": block["anchor"], "level": 2,
                    "private": block["private"], "parent": block["anchor"]})
        out += under(block["anchor"])
        for sub in block["subsections"]:
            out.append({"number": sub["number"], "label": sub["label"],
                        "anchor": sub["anchor"], "level": 3,
                        "question": sub.get("question", False),
                        "private": block["private"], "parent": block["anchor"]})
            out += under(sub["anchor"])
    return out


# A glossary entry: a bullet opening with a bold label — `- **EHR (Electronic Health Record).**`.
_GLOSS_ENTRY = re.compile(r"^(?P<lead>[ \t]*[-*+][ \t]+)\*\*(?P<label>[^*\n]+?)\*\*", re.M)
# A term marked for linking: ***bold italic***, and nothing else, so ordinary bold or
# italic prose is never touched. The lookarounds keep `****` and nested emphasis out.
_GLOSS_MARK = re.compile(r"(?<!\*)\*\*\*(?!\*)(?P<term>[^*\n]+?)\*\*\*(?!\*)")


def _gloss_keys(label: str) -> list[str]:
    """The names an entry answers to. `Diversity Action Plan (DAP).` → the label, the
    part before the bracket and the abbreviation inside it; `/` splits alternatives, so
    `Medicaid / Medicare` answers to both."""
    label = label.strip().rstrip(".").strip()
    names = [label]
    m = re.match(r"(.+?)\s*\((.+?)\)$", label)
    if m:
        names += [m.group(1), m.group(2)]
    out = []
    for n in names:
        out += [n] + [part for part in re.split(r"\s*/\s*", n) if part]
    return [_gloss_norm(n) for n in out if n.strip()]


# The external reference an entry ends on — `… definition. [Wikipedia](url)` (`#83`).
# A URL may hold one level of balanced brackets: `wiki/Default_(finance)`.
_GLOSS_REF = re.compile(r"\s*\[[^\]]+\]\((?:[^()\s]|\([^()\s]*\))+\)\s*$")


def _gloss_plain(md: str, limit: int = 280) -> str:
    """An entry's definition as one line of plain text, for a tooltip: the trailing
    reference link dropped (a tooltip ending "… Wikipedia" reads as part of the
    definition, and cannot be clicked anyway), other links reduced to their label,
    emphasis and code markers dropped, cut at a word near `limit`."""
    text = _GLOSS_REF.sub("", md.strip())
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[*_`]+", "", text)
    text = " ".join(text.split())
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return text


def _gloss_norm(text: str) -> str:
    text = re.sub(r"[^a-z0-9 ]+", " ", text.lower())
    return " ".join(w[:-1] if len(w) > 3 and w.endswith("s") else w for w in text.split())


def tag_glossary(gloss_block: dict, prefix: str, href_base: str = "") -> list[dict]:
    """Give each entry of a `## Glossary` block an id, and return the entries.

    Each entry is `{keys, href, norm, definition}`: the names it answers to, where a link
    to it should point (`href_base` + `#<prefix>--gloss-<slug>` — empty base for the same
    page, `/companies/<slug>/` for another), its normalised text for the last-resort match,
    and its definition as plain text for the tooltip. Mutates the block's `body_md`.
    """
    entries = []
    def tag(m):
        label = m.group("label")
        anchor = f"{prefix}--gloss-{section_slug(label.rstrip('.'))}"
        entries.append({"keys": _gloss_keys(label), "anchor": anchor,
                        "href": f"{href_base}#{anchor}"})
        return f'{m.group("lead")}<strong id="{anchor}" class="gloss-term">{label}</strong>'
    gloss_block["body_md"] = _GLOSS_ENTRY.sub(tag, gloss_block["body_md"])

    # Entry text — split on the ids just inserted; an entry runs to the next bullet.
    parts = re.split(r'id="([^"]+)"', gloss_block["body_md"])
    text_of = {}
    for i in range(1, len(parts) - 1, 2):
        text_of[parts[i]] = re.split(r"\n[ \t]*[-*+][ \t]", parts[i + 1])[0]
    for entry in entries:
        text = text_of.get(entry["anchor"], "")
        entry["norm"] = _gloss_norm(text)
        entry["definition"] = _gloss_plain(text.split("</strong>", 1)[-1])
    return entries


def glossary_of(body_md: str, prefix: str, href_base: str) -> list[dict]:
    """The glossary entries of a whole document, for linking *other* documents to it —
    an application's notes and interview rounds to its company page's glossary."""
    split = split_sections(body_md)
    gloss = next((b for b in split["blocks"] if b["anchor"] == "glossary"), None)
    return tag_glossary(gloss, prefix, href_base) if gloss else []


def link_glossary(blocks: list[dict], preamble: str, prefix: str,
                  fallback: list[dict] | None = None) -> str:
    """Link every ***term*** in a document to its glossary entry, with the definition as
    a tooltip.

    Done on the markdown, not the HTML, because only here are the glossary's entries
    still recognisable as entries. The document's own `## Glossary` wins; without one,
    `fallback` — the company page's glossary, for an application's notes and rounds —
    is used, and the link leaves the page. Each marked term becomes a link with class
    `gloss` and a `data-def` that site.css shows on hover; both are styled apart from
    external links. Matching is forgiving — plurals, an abbreviation, or the first words
    of a longer label all resolve — and falls back to the entry whose text mentions the
    term (`feasibility` lives inside the `Site` entry). A term that matches nothing is
    left as plain bold italic rather than linked somewhere wrong.

    Mutates the blocks' `body_md` and returns the preamble.
    """
    gloss = next((b for b in blocks if b["anchor"].endswith("--glossary")), None)
    entries = tag_glossary(gloss, prefix) if gloss else (fallback or [])
    if not entries:
        return preamble

    def find(term):
        t = _gloss_norm(term)
        for test in (lambda k: k == t,
                     lambda k: t.startswith(k + " ") or k.startswith(t + " "),
                     lambda k: f" {t} " in f" {k} "):
            for entry in entries:
                if any(test(k) for k in entry["keys"]):
                    return entry
        for entry in entries:
            if f" {t} " in f" {entry['norm']} ":
                return entry
        return None

    def link(m):
        term = m.group("term")
        entry = find(term)
        if not entry:
            return m.group(0)
        tip = html.escape(entry["definition"], quote=True)
        return f'<a class="gloss" href="{entry["href"]}" data-def="{tip}">{term}</a>'

    for b in blocks:
        if b is not gloss:
            b["body_md"] = _GLOSS_MARK.sub(link, b["body_md"])
    return _GLOSS_MARK.sub(link, preamble)


# A task-list item: `- [ ] …` / `- [x] …` (or a numbered `1. [ ]`). Found line by line,
# outside code fences, by `task_spans` — the one function both the renderer and the
# write-back endpoint use, so "the third box on the page" and "the third marker in the
# file" can never disagree.
_TASK = re.compile(r"^(?P<lead>[ \t]*(?:[-*+]|\d+[.)])[ \t]+)\[(?P<mark>[ xX])\](?=[ \t])")


def task_spans(text: str) -> list[tuple[int, int, bool]]:
    """(start, end, checked) of each task marker's `[ ]`/`[x]`, in file order."""
    spans, pos, in_fence = [], 0, False
    for line in text.splitlines(keepends=True):
        s = line.strip()
        if s.startswith("```") or s.startswith("~~~"):
            in_fence = not in_fence
        elif not in_fence:
            m = _TASK.match(line)
            if m:
                start = pos + m.start("mark") - 1
                spans.append((start, start + 3, m.group("mark") != " "))
        pos += len(line)
    return spans


def render_tasks(text: str, source: str | None) -> str:
    """Swap each task marker for a checkbox. With `source` (the file's path under the
    data root, local app only) the box is live and `js/tasks.js` writes a tick back to the
    file; without it — the published site — it is shown but disabled."""
    out, last = [], 0
    for i, (start, end, checked) in enumerate(task_spans(text)):
        attrs = f'type="checkbox" class="task-box" data-task="{i}"'
        if source:
            attrs += f' data-source="{html.escape(source, quote=True)}"'
        else:
            attrs += " disabled"
        if checked:
            attrs += " checked"
        out += [text[last:start], f"<input {attrs}>"]
        last = end
    out.append(text[last:])
    return "".join(out)


def set_task(text: str, index: int, checked: bool) -> str:
    """The file text with task `index` ticked or unticked. IndexError if there is no such
    task — the page and the file have drifted, and guessing would tick the wrong line."""
    start, end, _ = task_spans(text)[index]
    return text[:start] + ("[x]" if checked else "[ ]") + text[end:]


def sectioned(body_md: str, prefix: str, glossary: list[dict] | None = None,
              source: str | None = None) -> dict:
    """A markdown document ready for `_doc_sections.html` + `_doc_body.html`.

    Splits it, scopes every anchor under `prefix`, and builds the pill index — the three
    steps every caller needs, in the one order that works. `prefix` must be unique on the
    page: two documents both carrying `## Notes` would otherwise mint the same id and the
    browser would send every link to whichever rendered first. An interview round uses its
    own `round-<stage>-<date>` anchor, Other files the per-file anchor `extra_files`
    already builds, My notes the constant `notes` (there is only ever one).

    Returns the template's three keys directly, so a caller is one line and no view has to
    remember that prefixing comes before indexing.
    """
    from .highlights import render_marks

    # Marks before tasks, and both before splitting: each is counted across the whole
    # file, so an index on the page is an index into the file.
    body_md = _TASK_TAG.sub(r'<span class="task-tag">@\1</span>',
                            render_tasks(render_marks(body_md, source), source))
    body_md = _TODO_GUIDE.sub(lambda m: m[0].rstrip("\n") + "\n{: .howto-note }\n", body_md)
    split = split_sections(body_md)
    blocks = [
        {**b,
         "anchor": f"{prefix}--{b['anchor']}",
         "subsections": [{**sub, "anchor": f"{prefix}--{sub['anchor']}"}
                         for sub in b["subsections"]],
         "questions": [{**q, "anchor": f"{prefix}--{q['anchor']}",
                        "parent": f"{prefix}--{q['parent']}"}
                       for q in b["questions"]]}
        for b in split["blocks"]
    ]
    preamble = link_glossary(blocks, split["preamble"], prefix, glossary)
    return {"preamble_md": preamble, "blocks": blocks,
            "sections": section_index(blocks), "body_md": body_md, "source": source}


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
    "discovered-on-job-boards": "Job boards",
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


# ---------------------------------------------------------------------------
# The skill's own command list — so the in-app help can't drift from it
# ---------------------------------------------------------------------------

_SKILL_ROW_RE = re.compile(r"^\|\s*`([a-z-]+)`\s*\|\s*(.+?)\s*\|\s*$", re.MULTILINE)


def parse_skill_commands(skill_md: Path) -> list[dict]:
    """The `| \\`name\\` | description |` rows from the skill's help table.

    Read rather than retyped: the help page and the skill would otherwise drift apart
    silently, and they already have — `render-html-pdf` became `render` on 2026-09-29.
    A renamed or retired subcommand now changes the page by changing one file.

    Returns [] if the skill isn't reachable (a published mirror, a checkout without
    it) — the page has a sensible thing to show either way.
    """
    if not skill_md.is_file():
        return []
    text = skill_md.read_text()
    # Only the first table: the "## help Command" block printed verbatim to the user.
    # The second table below it repeats the same commands with invocation syntax.
    head = text.split("## Subcommands")[0]
    seen, out = set(), []
    for name, desc in _SKILL_ROW_RE.findall(head):
        if name in seen:
            continue
        seen.add(name)
        out.append({"name": name, "description": desc})
    return out


def skill_command_html(description: str) -> str:
    """A help-table description as HTML: `backticks` become <code>, nothing else.

    The descriptions are markdown written for a terminal, and the only markup they
    use is inline code. Running them through a full markdown renderer would be more
    machinery than that earns.
    """
    import html as _h
    parts = re.split(r"`([^`]+)`", description)
    out = []
    for i, part in enumerate(parts):
        out.append(f"<code>{_h.escape(part)}</code>" if i % 2 else _h.escape(part))
    return "".join(out)
