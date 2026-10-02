"""Template filters — markdown rendering and small display helpers."""

import datetime as dt
import re

import markdown as md_lib
from django import template
from django.utils import timezone
from django.utils.safestring import mark_safe

register = template.Library()

MD_EXTENSIONS = ["tables", "fenced_code", "sane_lists", "attr_list", "nl2br"]

# A list item that directly follows a paragraph line, with no blank line between.
# Python-Markdown treats that as a lazy continuation of the paragraph, so the first
# bullet disappears into the sentence above it. Pasted job descriptions do this
# constantly ("you will be responsible for:" followed straight by bullets), so it is
# fixed here rather than in every source file.
_TIGHT_LIST = re.compile(
    r"""(?m)^(?P<prev>(?!\s*$)      # previous line is not blank
                      (?![ \t]*[-*+][ \t])   # ...and is not itself a bullet
                      (?![ \t]*\d+[.)][ \t]) # ...or a numbered item
                      .*\S)
        [ \t]*\n                 # trailing spaces are common in pasted text
        (?=[ \t]*(?:[-*+]|\d+[.)])[ \t])""",
    re.VERBOSE,
)

# Bare URLs in prose — job descriptions are full of them and markdown leaves them as text.
_BARE_URL = re.compile(r"""(?<![\w"'=/>])(https?://[^\s<>"'\)\]]+)""")
# Split on complete anchors and any tag, so URLs already inside markup are left alone.
_MARKUP = re.compile(r"(<a\b.*?</a>|<[^>]+>)", re.S | re.I)


def _loosen_lists(text: str) -> str:
    """Insert the blank line Python-Markdown needs before a list, outside code fences."""
    chunks = re.split(r"(```.*?```)", text, flags=re.S)
    for i, chunk in enumerate(chunks):
        if not chunk.startswith("```"):
            chunks[i] = _TIGHT_LIST.sub(r"\g<prev>\n\n", chunk)
    return "".join(chunks)


# Sentence boundary: a terminator, whitespace, then something that starts a sentence.
_SENTENCE_END = re.compile(r'(?<=[.!?])\s+(?=["\u201c(\[]?[A-Z0-9])')

# Tokens that end in a full stop without ending a sentence.
_ABBREVIATIONS = (
    "e.g.", "i.e.", "etc.", "vs.", "cf.", "approx.", "Dr.", "Mr.", "Mrs.", "Ms.", "Prof.",
    "St.", "No.", "Inc.", "Ltd.", "Co.", "U.S.", "U.K.", "a.m.", "p.m.",
)


def _paragraphize(text: str, target: int = 380, minimum: int = 500) -> str:
    """Break an unbroken wall of prose into paragraphs at sentence boundaries.

    Application `notes` arrive as one long block — they were promoted from the old
    applications.md detail blocks, which had no internal structure — and 1,500 characters
    with no breaks is unreadable at any line length.

    Only applies when the author has provided no structure of their own: any blank line in
    the text means it is already laid out, and it is left completely alone. Never splits
    mid-sentence, so the worst case is a paragraph break in a slightly odd place.
    """
    if "\n\n" in text or "\n" in text.strip() or len(text) < minimum:
        return text

    pieces = _SENTENCE_END.split(text)
    sentences: list[str] = []
    for piece in pieces:
        # Re-join where the "boundary" was really an abbreviation.
        if sentences and sentences[-1].endswith(_ABBREVIATIONS):
            sentences[-1] = f"{sentences[-1]} {piece}"
        else:
            sentences.append(piece)

    paragraphs, buf = [], ""
    for sentence in sentences:
        buf = f"{buf} {sentence}".strip() if buf else sentence
        if len(buf) >= target:
            paragraphs.append(buf)
            buf = ""
    if buf:
        # Don't leave a stub trailing on its own.
        if paragraphs and len(buf) < 120:
            paragraphs[-1] = f"{paragraphs[-1]} {buf}"
        else:
            paragraphs.append(buf)
    return "\n\n".join(paragraphs)


def _autolink(html: str) -> str:
    """Turn bare URLs into links, without touching existing markup."""
    def link(m):
        url = m.group(1).rstrip(".,;:")
        trailing = m.group(1)[len(url):]
        return f'<a href="{url}" target="_blank" rel="noopener">{url}</a>{trailing}'

    parts = _MARKUP.split(html)
    for i, part in enumerate(parts):
        if i % 2 == 0:  # text between tags
            parts[i] = _BARE_URL.sub(link, part)
    return "".join(parts)


@register.filter(name="markdown")
def markdownify(text):
    """Render markdown read off disk at request time (see plan §2.2)."""
    if not text:
        return ""
    # Strip HTML comments — the markdown files use them for editor-only notes.
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    html = md_lib.markdown(_loosen_lists(_paragraphize(text)), extensions=MD_EXTENSIONS)
    return mark_safe(_autolink(html))


_PLAIN_EXTERNAL_A_RE = re.compile(r'<a\s+href="(https?://[^"]*)"\s*>')


@register.filter(name="blank_links")
def blank_links(html):
    """Force every http(s) link to open in a new tab — for the scan report pages,
    which are almost entirely outbound links to job postings and ATS boards. Only
    matches a bare `<a href="...">` with no other attributes yet, so links `markdown`
    already blanked (via its own bare-URL autolinking) are left alone."""
    if not html:
        return ""
    html = _PLAIN_EXTERNAL_A_RE.sub(
        lambda m: f'<a href="{m.group(1)}" target="_blank" rel="noopener">', str(html))
    return mark_safe(html)


@register.filter(name="strip_h1")
def strip_h1(text):
    """Drop a leading '# Title' — the page already shows it as a heading.

    `(?:\n|\Z)` rather than `\n`: the title may be the whole string, with nothing after
    it. That happens for a round's preamble (`#66`), which is everything before the
    first `##` — in a round that goes straight into its sections, the title is all there
    is, and requiring a trailing newline left it rendered twice.
    """
    if not text:
        return ""
    return re.sub(r"\A\s*#\s+.*?(?:\n|\Z)", "", text, count=1)


# A line that opens a Q or an A in an interview prep file: `**Q:** …`, optionally as a
# bullet. Only the five markers the prep template actually uses (Q and A, plus STAR).
_QA_OPENER = re.compile(r"^(?P<lead>[ \t]*(?:[-*+][ \t]+)?)\*\*(?P<who>Q|A|S|T|R):\*\*")
# Anything that ends a wrapped question: a blank line, a heading, or a new list item.
_QA_BREAK = re.compile(r"^(?:[ \t]*$|[ \t]*#|[ \t]*(?:[-*+]|\d+[.)])[ \t])")

# Rounds written before the `**Q:**` convention (2026-09-24) put the question in the heading
# instead — `#### Why do you want to leave?`, or `### A1. "Walk me through a platform you
# architected."`. Those are still questions and should still be coloured, so a heading counts
# when it asks something or quotes what was asked. Deliberately narrow: a heading naming a
# topic ("AWS — say it first", "Questions to ask them", "Why this role") has neither mark and
# stays plain. The known false positive is a heading quoting a product name; it would only be
# coloured, never broken.
_HEADING = re.compile(r"^(?P<hashes>\#{2,6}[ \t]+)(?P<text>.+?)[ \t]*$")
_QUESTION_HEADING = re.compile(r'\?|"[^"]+"|\u201c[^\u201d]+\u201d')


def _wrap_questions(text: str) -> str:
    """Put a span round each `**Q:** …` line, closing it where the question ends."""
    out: list[str] = []
    open_q = False
    for line in text.split("\n"):
        opener = _QA_OPENER.match(line)
        if open_q and (opener or _QA_BREAK.match(line)):
            out[-1] += "</span>"
            open_q = False
        heading = _HEADING.match(line)
        if heading and _QUESTION_HEADING.search(heading.group("text")):
            # Wrap the text only — the hashes have to stay at the line start to parse.
            out.append(f'{heading.group("hashes")}<span class="qa-q">'
                       f'{heading.group("text")}</span>')
            continue
        if opener and opener.group("who") == "Q":
            lead = opener.group("lead")
            out.append(f'{lead}<span class="qa-q">{line[len(lead):]}')
            open_q = True
        else:
            out.append(line)
    if open_q:
        out[-1] += "</span>"
    return "\n".join(out)


@register.filter(name="mark_qa")
def mark_qa(text, enabled=True):
    """Mark up the questions in an interview round so the Interviews tab can colour them
    — the eye needs to find the questions without reading the answers between them.

    Source-level, like `strip_h1`, and applied only to interview rounds: `**Q:**` is that
    file's convention, not the site's. A question hard-wrapped over several source lines
    stays inside one span — wrapped prose is the norm in these files, and a colour that
    stopped at the first line would read as a rendering bug.

    `enabled` exists so `_doc_body.html` can stay one template with one filter chain
    (`#72`). My notes and Other files pass false: a `**Q:**` in a note is somebody's
    prose, not this convention. Branching in the template instead would mean writing the
    whole chain out twice, which is how the two copies drift.
    """
    if not text or not enabled:
        return text or ""
    chunks = re.split(r"(```.*?```)", text, flags=re.S)
    for i, chunk in enumerate(chunks):
        if not chunk.startswith("```"):
            chunks[i] = _wrap_questions(chunk)
    return "".join(chunks)


_H3_RE = re.compile(r"<h3(?![^>]*\bid=)([^>]*)>(.*?)</h3>", re.DOTALL)


@register.filter(name="number_sections")
def number_sections(html, block):
    """Stamp each `<h3>` in a collapsed block with its id and section number.

    Matched **by position**, not by re-slugging the heading text: the subsection list was
    built by walking the same markdown in the same order, so the Nth `<h3>` here is the
    Nth entry there. Re-deriving the slug from the rendered HTML would mean the same
    string being slugged by two different code paths — the drift this is written to
    avoid, since the nav's href and the heading's id have to be character-identical.

    A heading that already carries an id is left alone, so this is safe to chain.
    """
    if not html:
        return ""
    subs = list(block.get("subsections") or [])
    i = 0

    def one(m):
        nonlocal i
        if i >= len(subs):
            return m.group(0)
        sub = subs[i]
        i += 1
        return (f'<h3{m.group(1)} id="{sub["anchor"]}">'
                f'<span class="sec-n">{sub["number"]}</span> {m.group(2)}</h3>')

    return mark_safe(_H3_RE.sub(one, str(html)))


@register.filter
def stars(value):
    try:
        n = int(value)
    except (TypeError, ValueError):
        return ""
    return mark_safe("★" * n + '<span class="star-off">' + "☆" * (5 - n) + "</span>")


@register.filter
def pct(part, whole):
    try:
        return round(100 * float(part) / float(whole))
    except (TypeError, ValueError, ZeroDivisionError):
        return 0


@register.filter(name="ago")
def ago(value):
    """Render a date/datetime as 'today' / 'N days|weeks|months|years ago' — the
    dashboard's relative-date columns (recently logged / applied / added companies)."""
    if not value:
        return "—"
    if isinstance(value, dt.datetime):
        value = timezone.localtime(value).date() if timezone.is_aware(value) else value.date()
    delta = (timezone.localdate() - value).days
    if delta < 0:
        return value.strftime("%d %b %Y")
    if delta == 0:
        return "today"
    if delta == 1:
        return "yesterday"
    if delta < 7:
        return f"{delta} days ago"
    if delta < 31:
        weeks = delta // 7
        return f"{weeks} week{'s' if weeks != 1 else ''} ago"
    if delta < 365:
        months = delta // 30
        return f"{months} month{'s' if months != 1 else ''} ago"
    years = delta // 365
    return f"{years} year{'s' if years != 1 else ''} ago"
