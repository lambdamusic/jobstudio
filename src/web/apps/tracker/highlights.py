"""Highlights: lines worth remembering, marked on the page and kept in the markdown (TODO `#77`).

A highlight is `==text==` in the file — the de facto markdown highlight (Obsidian, Typora,
iA Writer), readable as plain text and rendered here as `<mark>`. The file is the record:
a highlight survives a reload, an editor, and a publish, exactly as a ticked task does.

Adding one starts from a browser selection, which is text as *rendered* — no `**`, no
`[...](url)`, no list markers. `add()` finds that text in the markdown by building a
plain-text view of the file in which every markup character is invisible but still
knows its position in the source, matching there, and mapping the match back. Where the
selection appears more than once, the text either side of it (sent by the page) picks
the occurrence; where that still does not decide, it refuses rather than guess.

Two rules keep the markdown valid:

- **Never split a construct.** A selection that starts or ends inside a link, a code span,
  a bold run or an existing highlight is widened to take the whole of it, so `==` never
  lands between `**` and its partner.
- **One highlight per line.** A selection across paragraphs, list items or table cells
  becomes one `==…==` per line (per cell), each inside its own line's markers, since an
  inline mark cannot cross a block boundary.

Headings and code are never highlighted: a heading becomes a section label the site
renders as plain text, and `==` inside code is literal.
"""

from __future__ import annotations

import html
import re

# `==text==` — content may not start or end with whitespace or `=`, so a setext heading
# underline (`=====`) or a stray `==` in prose is not a highlight.
_MARK = re.compile(r"(?<![=\\])==(?=[^\s=])(.+?)(?<=[^\s=])==(?!=)")
_FENCE = re.compile(r"^\s*(```|~~~)")
_CODE_SPAN = re.compile(r"`[^`\n]+`")

# Markup that renders as nothing. Each pattern's named groups `h`, `h2`… are the
# characters to hide; the rest of the match is visible text.
_HIDDEN = [
    re.compile(r"(?m)^(?P<h>[ \t]*(?:#{1,6}[ \t]+|>[ \t]?|(?:[-*+]|\d+[.)])[ \t]+(?:\[[ xX]\][ \t]+)?))"),
    re.compile(r"<!--.*?-->", re.S),  # whole match hidden — see _hide_whole
    re.compile(r"(?P<h>\[)(?=[^\]\n]*\]\([^)\n]*\))[^\]\n]*(?P<h2>\]\([^)\n]*\))"),
    re.compile(r"(?P<h>`)[^`\n]+(?P<h2>`)"),
    re.compile(r"(?P<h>\*\*\*|___)(?=\S)[^\n]+?(?<=\S)(?P<h2>\*\*\*|___)"),
    re.compile(r"(?P<h>\*\*|__)(?=\S)[^\n]+?(?<=\S)(?P<h2>\*\*|__)"),
    re.compile(r"(?<![*\w])(?P<h>\*)(?=[^\s*])[^*\n]+?(?<=[^\s*])(?P<h2>\*)(?![*\w])"),
    re.compile(r"(?<![_\w])(?P<h>_)(?=[^\s_])[^_\n]+?(?<=[^\s_])(?P<h2>_)(?![_\w])"),
    re.compile(r"(?P<h>==)(?=[^\s=])[^\n]+?(?<=[^\s=])(?P<h2>==)"),
    re.compile(r"(?P<h><[^>\n]+>)"),
    re.compile(r"(?P<h>\\)(?=[\\`*_{}\[\]()#+\-.!|=])"),
    re.compile(r"(?P<h>\|)"),
]
_HIDE_WHOLE = {1}

# Inline constructs a highlight must not cut through.
_ATOMIC = [
    re.compile(r"\[[^\]\n]*\]\([^)\n]*\)"),
    re.compile(r"`[^`\n]+`"),
    re.compile(r"(\*\*\*|___|\*\*|__)(?=\S)[^\n]+?(?<=\S)\1"),
    re.compile(r"(?<![*\w])\*(?=[^\s*])[^*\n]+?(?<=[^\s*])\*(?![*\w])"),
    re.compile(r"<[^>\n]+>"),
]

_HEADING_LINE = re.compile(r"^[ \t]*#{1,6}[ \t]")
_TABLE_RULE = re.compile(r"^[ \t]*\|?[ \t]*:?-{3,}:?[ \t]*(\|[ \t]*:?-{3,}:?[ \t]*)*\|?[ \t]*$")


class HighlightError(ValueError):
    """Why a highlight could not be placed — shown to the user as is."""


# ── Spans: where the highlights are ──────────────────────────────────────────

def _code_lines(text: str) -> set[int]:
    """Line numbers inside (or opening/closing) a fenced code block."""
    out, inside = set(), False
    for n, line in enumerate(text.split("\n")):
        if _FENCE.match(line):
            out.add(n)
            inside = not inside
        elif inside:
            out.add(n)
    return out


def mark_spans(text: str) -> list[tuple[int, int]]:
    """(start, end) of every `==…==` in file order, outside code — the one count both
    the renderer and the remove endpoint use, as `task_spans` is for tasks."""
    spans, pos, code = [], 0, _code_lines(text)
    for n, line in enumerate(text.split("\n")):
        if n not in code:
            in_code = [m.span() for m in _CODE_SPAN.finditer(line)]
            for m in _MARK.finditer(line):
                if not any(s <= m.start() < e for s, e in in_code):
                    spans.append((pos + m.start(), pos + m.end()))
        pos += len(line) + 1
    return spans


def render_marks(text: str, source: str | None) -> str:
    """Each `==…==` as `<mark>`. With `source` (local app) the mark carries its index, so
    `highlight.js` can ask for exactly that one to be removed."""
    out, last = [], 0
    for i, (s, e) in enumerate(mark_spans(text)):
        attrs = f' data-mark="{i}"' if source else ""
        out += [text[last:s], f'<mark class="hl"{attrs}>', text[s + 2:e - 2], "</mark>"]
        last = e
    out.append(text[last:])
    return "".join(out)


def remove(text: str, index: int) -> str:
    """The file text with highlight `index` unwrapped. IndexError when there is no such
    highlight — the page and the file have drifted."""
    s, e = mark_spans(text)[index]
    return text[:s] + text[s + 2:e - 2] + text[e:]


# ── Adding one ───────────────────────────────────────────────────────────────

def _visible(text: str) -> list[bool]:
    """Which characters of the markdown show up as text on the page."""
    vis = [True] * len(text)
    code = _code_lines(text)
    starts = [0]
    for line in text.split("\n"):
        starts.append(starts[-1] + len(line) + 1)
    for n in code:
        for i in range(starts[n], min(starts[n + 1], len(text))):
            vis[i] = False  # code is never a highlight target, so take it out entirely
    for k, rx in enumerate(_HIDDEN):
        for m in rx.finditer(text):
            if k in _HIDE_WHOLE:
                for i in range(*m.span()):
                    vis[i] = False
                continue
            for g in ("h", "h2"):
                if g in rx.groupindex and m.group(g) is not None:
                    for i in range(*m.span(g)):
                        vis[i] = False
    return vis


def _normalise(text: str) -> tuple[str, list[int]]:
    """`text` with every whitespace run as one space, and for each character of the
    result the index it came from."""
    out, idx, space = [], [], False
    for i, ch in enumerate(text):
        if ch.isspace() or ch == "\u00a0":
            if not space and out:
                out.append(" ")
                idx.append(i)
            space = True
        else:
            out.append(ch)
            idx.append(i)
            space = False
    return "".join(out), idx


def _common_suffix(a: str, b: str) -> int:
    n = 0
    while n < len(a) and n < len(b) and a[-1 - n] == b[-1 - n]:
        n += 1
    return n


def _common_prefix(a: str, b: str) -> int:
    n = 0
    while n < len(a) and n < len(b) and a[n] == b[n]:
        n += 1
    return n


def _locate(text: str, selected: str, before: str, after: str) -> tuple[int, int]:
    """The source range [start, end) the selection was made from."""
    vis = _visible(text)
    plain_idx = [i for i, v in enumerate(vis) if v]
    plain = "".join(text[i] for i in plain_idx)
    norm, norm_idx = _normalise(plain)
    want, _ = _normalise(html.unescape(selected).strip())
    if not want.strip():
        raise HighlightError("Nothing selected.")

    hits = [m.start() for m in re.finditer(re.escape(want), norm)]
    if not hits:
        raise HighlightError("Couldn't find that text in the file. Try a selection "
                             "inside the document's own text, not a heading or label.")
    if len(hits) > 1:
        b, a = _normalise(before)[0].rstrip(), _normalise(after)[0].lstrip()
        scores = [(_common_suffix(norm[:h].rstrip(), b)
                   + _common_prefix(norm[h + len(want):].lstrip(), a), h) for h in hits]
        scores.sort(reverse=True)
        if scores[0][0] == scores[1][0]:
            raise HighlightError("That text appears more than once and the selection "
                                 "doesn't say which. Select a little more of it.")
        hits = [scores[0][1]]
    h = hits[0]
    start = plain_idx[norm_idx[h]]
    end = plain_idx[norm_idx[h + len(want) - 1]] + 1
    return start, end


def _whole_words(text: str, start: int, end: int) -> tuple[int, int]:
    """Grow [start, end) to whole words. A drag that stops a letter short, or a letter
    into the next word, is near-universal with a mouse, and a highlight ending mid-word
    is never what was meant."""
    while start > 0 and text[start - 1].isalnum() and text[start].isalnum():
        start -= 1
    while end < len(text) and text[end].isalnum() and text[end - 1].isalnum():
        end += 1
    return start, end


def _widen(text: str, start: int, end: int) -> tuple[int, int]:
    """Grow [start, end) until no inline construct is cut through."""
    spans = [m.span() for rx in _ATOMIC for m in rx.finditer(text)]
    changed = True
    while changed:
        changed = False
        for s, e in spans:
            if (s < start < e) or (s < end < e):
                start, end, changed = min(start, s), max(end, e), True
    return start, end


def _pieces(text: str, start: int, end: int) -> list[tuple[int, int]]:
    """[start, end) split into one range per line (and per table cell), each trimmed to
    the visible text inside that line's own markers."""
    vis = _visible(text)
    out = []
    code = _code_lines(text)
    pos = 0
    for n, line in enumerate(text.split("\n")):
        line_start, line_end = pos, pos + len(line)
        pos = line_end + 1
        if line_end < start or line_start > end:
            continue
        if n in code or _HEADING_LINE.match(line) or _TABLE_RULE.match(line):
            continue
        s, e = max(start, line_start), min(end, line_end)
        # A table row: one piece per cell.
        cuts = [s] + [i + 1 for i in range(s, e) if text[i] == "|"] + [e + 1]
        for a, b in zip(cuts, cuts[1:]):
            b -= 1
            # Skip the line's own markers (`- `, `1. `, `- [ ] `, `> `), which are hidden,
            # but not the opening of a construct the piece starts with (a link, `**`).
            while a < b and (text[a].isspace() or (not vis[a] and not _opens_construct(text, a))):
                a += 1
            while b > a and (text[b - 1].isspace() or text[b - 1] == "|"):
                b -= 1
            if a < b and any(vis[a:b]):
                out.append((a, b))
    return out


def _opens_construct(text: str, i: int) -> bool:
    """Is position `i` the opening character of an inline construct (a link's `[`, a
    bold run's `*`) rather than a line marker?"""
    return any(m.start() == i for rx in _ATOMIC for m in rx.finditer(text))


def add(text: str, selected: str, before: str = "", after: str = "") -> str:
    """The file text with the selection highlighted."""
    start, end = _widen(text, *_whole_words(text, *_locate(text, selected, before, after)))
    for s, e in mark_spans(text):
        if s < end and start < e:
            raise HighlightError("Part of that is already highlighted. Remove that "
                                 "highlight first, then select again.")
    pieces = _pieces(text, start, end)
    if not pieces:
        raise HighlightError("Headings and code can't be highlighted.")
    for s, e in reversed(pieces):
        text = text[:s] + "==" + text[s:e] + "==" + text[e:]
    return text
