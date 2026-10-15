"""Template filters — markdown rendering and small display helpers."""

import datetime as dt
import re

import markdown as md_lib
from django import template
from django.utils import timezone
from django.utils.safestring import mark_safe

from ..filelinks import link_file_refs
from ..highlights import render_marks
from ..parsers import QA_BREAK, QA_OPENER, is_question_heading

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

# A line that starts a block of its own, so is never joined onto the line above: a list
# item, table row, heading, quote, fence, block-level HTML (an inline tag — a highlight's
# `<mark>`, which is already rendered by now — continues the line), or a `**Field:**` line (stacked
# metadata — `**Area:**`, `**Location:**` — where the line break is the layout).
_BLOCK_START = re.compile(r"^[ \t]*(?:[-*+][ \t]|\d+[.)][ \t]|#{1,6}[ \t]|[|>]|```|~~~|\*\*|<(?!/?(?:mark|a|span|strong|em|b|i|code)\b))")
# The end of a sentence, allowing a closing quote, bracket or emphasis after it.
_ENDS_SENTENCE = re.compile(r"""[.:!?]["'”’)\]*_]*$""")
# A blockquote's `>` markers, to compare the text inside a quote line by line.
_QUOTE = re.compile(r"^(?:[ \t]*>[ \t]?)*")
# A line that can only be the rest of the sentence above it — or an indented line under
# a non-blank one, which markdown already reads as the same paragraph (a list item's
# continuation), so a break there is only ever the wrap.
_CONTINUES = re.compile(r"^(?:[ \t]*[a-z(—–]|[ \t]+\S)")


def _unwrap(text: str) -> str:
    """Join hard-wrapped prose back into one line per paragraph, outside code fences.

    `nl2br` stays on, because a single line break is often the layout — stacked
    `**Field:**` lines, an address. But files written by an agent (and some by hand)
    are hard-wrapped at ~90 columns, and with `nl2br` every wrap is a visible break
    mid-sentence. A line is joined onto the one above when it can only be a
    continuation: it starts lowercase (or with a bracket or dash), it is indented under
    the line above, or the line above is wrap-length (60+) and does not end a sentence.
    Inside a blockquote the same rules apply to the text after the `>`. Anything else
    keeps its break.
    """
    out: list[str] = []
    fence = False
    for line in text.split("\n"):
        if re.match(r"^[ \t]*(```|~~~)", line):
            fence = not fence
            out.append(line)
            continue
        prev = out[-1] if out else ""
        quote, prev_quote = _QUOTE.match(line).group(), _QUOTE.match(prev).group()
        if quote.replace(" ", "") != prev_quote.replace(" ", ""):
            out.append(line)  # into or out of a quote, or a different depth
            continue
        body, prev_body = line[len(quote):], prev[len(prev_quote):]
        join = (not fence and body.strip() and prev_body.strip() and not prev.endswith("  ")
                and not _BLOCK_START.match(body)
                and not re.match(r"^[ \t]*(```|~~~|#{1,6}[ \t]|\|)", prev_body)
                and (_CONTINUES.match(body)
                     or (len(prev.rstrip()) >= 60 and not _ENDS_SENTENCE.search(prev.rstrip()))))
        if join:
            out[-1] = prev.rstrip() + " " + body.strip()
        else:
            out.append(line)
    return "\n".join(out)


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

    # Never split inside markup. Glossary links arrive here already rendered, and their
    # data-def attribute is a definition that may run to several sentences — a break
    # there leaves half an <a> tag printed on the page as text.
    tags: list[str] = []

    def hide(m):
        tags.append(m.group(0))
        return f"\x00{len(tags) - 1}\x00"

    text = _MARKUP.sub(hide, text)

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
    return re.sub(r"\x00(\d+)\x00", lambda m: tags[int(m.group(1))], "\n\n".join(paragraphs))


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
    # `==text==` as <mark>, for markdown that did not come through `sectioned()` (which
    # has already turned its own into numbered marks the page can remove).
    text = render_marks(text, None)
    html = md_lib.markdown(_loosen_lists(_paragraphize(_unwrap(text))), extensions=MD_EXTENSIONS)
    # After _autolink, so a URL ending in .md is already a link and left alone.
    return mark_safe(link_file_refs(_autolink(html)))


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


@register.filter(name="data_rel")
def data_rel(path):
    """An absolute path as a path relative to the data root, for an `actions/` URL."""
    from pathlib import Path

    from django.conf import settings
    try:
        return str(Path(path).resolve().relative_to(Path(settings.DATA_ROOT).resolve()))
    except ValueError:
        return ""


@register.filter(name="hl_marks")
def hl_marks(text, source):
    """`==text==` as numbered `<mark>`s the highlighter can remove (`#77`), for a whole
    file rendered without `sectioned()`. Before `strip_h1`, so the numbering counts the
    file as it is on disk. With no `source` (published site) `markdown` does it unnumbered."""
    return render_marks(text, source) if source else text


@register.filter(name="strip_h1")
def strip_h1(text):
    r"""Drop a leading '# Title' — the page already shows it as a heading.

    `(?:\n|\Z)` rather than `\n`: the title may be the whole string, with nothing after
    it. That happens for a round's preamble (`#66`), which is everything before the
    first `##` — in a round that goes straight into its sections, the title is all there
    is, and requiring a trailing newline left it rendered twice.
    """
    if not text:
        return ""
    return re.sub(r"\A\s*#\s+.*?(?:\n|\Z)", "", text, count=1)


# What a question is — the `**Q:**` line, the break that ends one, and a heading that asks
# — lives in parsers.py, because the contents lists the questions and the page numbers them
# by position: the parser and this filter have to agree exactly.
_QA_OPENER = QA_OPENER
_QA_BREAK = QA_BREAK
_HEADING = re.compile(r"^(?P<hashes>\#{2,6}[ \t]+)(?P<text>.+?)[ \t]*$")


def _wrap_questions(text: str, loose: bool = True) -> str:
    """Put a span round each `**Q:** …` line, closing it where the question ends."""
    out: list[str] = []
    open_q = False
    for line in text.split("\n"):
        opener = _QA_OPENER.match(line)
        if open_q and (opener or _QA_BREAK.match(line)):
            out[-1] += "</span>"
            open_q = False
        heading = _HEADING.match(line)
        if heading and is_question_heading(heading.group("text"), loose):
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
def mark_qa(text, rounds=True):
    """Mark up the questions in a document so the page can colour, number and fold them
    — the eye needs to find the questions without reading the answers between them.

    Source-level, like `strip_h1`. A question hard-wrapped over several source lines stays
    inside one span — wrapped prose is the norm in these files, and a colour that stopped
    at the first line would read as a rendering bug.

    On every document since 2026-10-15, not just interview rounds: the answer bank, study
    files and topic notes use the same `**Q:**` convention, and the contents now lists
    questions, which needs them marked wherever they are. What `rounds` still decides is
    which *headings* count as questions — loosely in a round, where any heading that asks
    or quotes is one; strictly elsewhere (see `parsers.QUESTION_HEADING_STRICT`).
    """
    if not text:
        return ""
    chunks = re.split(r"(```.*?```)", text, flags=re.S)
    for i, chunk in enumerate(chunks):
        if not chunk.startswith("```"):
            chunks[i] = _wrap_questions(chunk, bool(rounds))
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


# The pieces of rendered HTML `qa_items` works with. It only ever sees markdown's own output
# for one block, so these are the few shapes that renderer produces, not HTML in general.
_QA_SPAN = '<span class="qa-q">'
_QA_ITEM_START = re.compile(r'(?P<li><li>\s*)?(?P<p><p>)?<span class="qa-q">')
_SPAN_TAG = re.compile(r"<span\b|</span>")
_LI_TAG = re.compile(r"<li\b|</li>")
# Where the answer to a bare-paragraph question stops: the next question, list of
# questions, heading or rule — or the end of whatever holds the paragraph, so an answer
# never swallows a closing tag and breaks the nesting around it.
_QA_P_END = re.compile(r'<h[1-6][\s>]|<details class="qa|<[uo]l>\s*<li class="qa-li"|<hr\b'
                       r'|</li>|</[uo]l>|</blockquote>')
_QA_HEADING = re.compile(r'<h(?P<n>[34])(?P<attrs>[^>]*)>(?P<inner>(?:(?!</h(?P=n)>).)*?'
                         r'<span class="qa-q">.*?)</h(?P=n)>', re.S)


def _close(html: str, start: int, tag_re: re.Pattern, open_prefix: str) -> int:
    """Index just past the tag that closes the element opened at `start`, counting nested
    tags of the same name. Falls back to the end of the string."""
    depth = 0
    for m in tag_re.finditer(html, start):
        depth += 1 if m.group(0).startswith(open_prefix) else -1
        if depth == 0:
            return m.end()
    return len(html)


def _strip_br(fragment: str) -> str:
    return re.sub(r"\A\s*<br\s*/?>\s*", "", fragment)


@register.filter(name="qa_items")
def qa_items(html, block):
    """Turn each question and its answer into a numbered block that opens and closes
    (2026-10-15). Runs after `number_sections`, on one block's rendered HTML.

    A `**Q:**` question becomes `<details class="qa" open>`: the question is the summary,
    the answer everything after it — the rest of its list item, or for a bare paragraph,
    everything up to the next question or heading. Native `<details>`, like the sections,
    so it folds with no script and the browser's find-in-page opens it. The number goes in
    a `data-n` the CSS shows, not in the text: highlight.js matches a selection against
    the file by its surrounding text, and a number that isn't in the file would break that.

    Numbers and ids come from `block["questions"]`, **by position**, the way
    `number_sections` stamps headings: the parser walked the same markdown in the same
    order. A heading that is itself a question (the answer bank's `### "Tell me about
    yourself"`) folds the same way, and keeps the number and id its heading already has.
    """
    if not html:
        return ""
    html = str(html)
    questions = list((block or {}).get("questions") or [])

    starts = [m for m in _QA_ITEM_START.finditer(html) if m.group("li") or m.group("p")]
    for i in range(len(starts) - 1, -1, -1):  # from the end, so earlier offsets hold
        m = starts[i]
        q = questions[i] if i < len(questions) else None
        span_at = m.end() - len(_QA_SPAN)
        span_end = _close(html, span_at, _SPAN_TAG, "<span")
        number = f' data-n="{q["number"]}"' if q else ""
        summary = (f'<summary class="qa-sum"><span class="qa-q"{number}>'
                   f'{html[m.end():span_end]}</summary>')
        attrs = f' id="{q["anchor"]}"' if q else ""
        if m.group("li"):
            li_end = _close(html, m.start(), _LI_TAG, "<li")
            inner_end = li_end - len("</li>")
            if m.group("p"):
                p_end = html.index("</p>", span_end) + len("</p>")
                first = _strip_br(html[span_end:p_end - len("</p>")])
                answer = (f"<p>{first}</p>" if first.strip() else "") + html[p_end:inner_end]
            else:
                answer = _strip_br(html[span_end:inner_end])
            html = (html[:m.start()] + f'<li class="qa-li"><details class="qa"{attrs} open>'
                    + summary + f'<div class="qa-a">{answer}</div></details></li>'
                    + html[li_end:])
        else:
            p_end = html.index("</p>", span_end) + len("</p>")
            first = _strip_br(html[span_end:p_end - len("</p>")])
            stop = _QA_P_END.search(html, p_end)
            end = stop.start() if stop else len(html)
            answer = (f"<p>{first}</p>" if first.strip() else "") + html[p_end:end]
            html = (html[:m.start()] + f'<details class="qa"{attrs} open>' + summary
                    + f'<div class="qa-a">{answer}</div></details>' + html[end:])

    # Headings that ask: h4 first, so an h3's answer can contain them already folded.
    for level in ("4", "3"):
        out, pos = [], 0
        stop_re = re.compile(rf"<h[1-{level}][\s>]")
        for m in _QA_HEADING.finditer(html):
            if m.group("n") != level or m.start() < pos:
                continue
            stop = stop_re.search(html, m.end())
            end = stop.start() if stop else len(html)
            out += [html[pos:m.start()], '<details class="qa qa-h" open><summary class="qa-sum">',
                    m.group(0), '</summary><div class="qa-a">', html[m.end():end], "</div></details>"]
            pos = end
        out.append(html[pos:])
        html = "".join(out)
    return mark_safe(html)


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
