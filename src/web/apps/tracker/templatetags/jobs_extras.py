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
    """Drop a leading '# Title' — the page already shows it as a heading."""
    if not text:
        return ""
    return re.sub(r"\A\s*#\s+.*?\n", "", text, count=1)


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
