"""An application's dossier: everything in its Documents index as one .docx (`#98`).

For reading, not sending: the whole set an application has gathered (job description, the
CV and cover letter as sent, notes, to-dos, interview rounds, the company page, and the
notes its files link to) in one file that opens anywhere, offline. It came out of one-off
exports made to read on a flight, where the value was having the set together.

The layout follows the first of those, which was read in Google Docs: a contents list of
links on the first page, one section per document starting on a new page, and every link
between documents (a round linking a note, the notes linking a heading in the job
description) turned into a jump within the file. That is done with bookmarks and anchored
hyperlinks rather than a Word TOC field, because a field has to be refreshed in Word
before it shows anything, and Google Docs never does.

Markdown goes through the site's own `markdown` filter and the HTML that comes out is
written into Word paragraphs with python-docx. The sent CV and cover letter are copied in
from their own .docx, styles and all, so the dossier holds what went out; a document with
no .docx yet falls back to its markdown.
"""

from __future__ import annotations

import base64
import io
import re
from copy import deepcopy
from datetime import date
from pathlib import Path

import lxml.html
from django.urls import reverse
from docx import Document
from docx.enum.text import WD_COLOR_INDEX
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

NAVY = RGBColor(0x1B, 0x29, 0x48)
LINK = RGBColor(0x1F, 0x5A, 0xA6)
RED = RGBColor(0xA8, 0x1E, 0x1E)  # a `**Q:**` question, as on the site
BLOCK = {"p", "ul", "ol", "li", "table", "pre", "blockquote", "hr", "h1", "h2", "h3", "h4",
         "h5", "h6", "div", "section", "article", "figure", "details", "aside"}


def sections(app) -> list[dict]:
    """The dossier's parts, in reading order: `key` (its bookmark), `title`, `kind` ("md",
    "docx" or "overview"), `source` (markdown text or a .docx path), `path` (the file, for
    relative images) and `anchors`, the site links that should land on it.

    The order follows the Documents index (`Application.documents`) but reads as a pack:
    the role first, then what was sent, then the prep, then the background. Rounds go
    oldest first for the same reason, where the page lists them newest first.
    """
    page = f"/applications/{app.num}/"
    out = [{"title": "Overview", "kind": "overview", "anchors": [page]}]
    if app.job_md.strip():
        out.append({"title": "Job description", "kind": "md", "source": app.job_md,
                    "path": app._folder_file("job.md"), "anchors": [f"{page}#job"]})
    for cv in app.cv_files:
        title = f"CV as sent: {cv['label']}" + (f" ({cv['date']})" if cv["date"] else "")
        out.append({"title": title, "anchors": [f"{page}#{cv['anchor']}"], "path": cv["path"],
                    **({"kind": "docx", "source": cv["docx"]} if cv["docx"]
                       else {"kind": "md", "source": cv["body_md"]})})
    for letter in app.cover_letter_files:
        title = "Cover letter" + (f" ({letter['date']})" if letter["date"] else "")
        out.append({"title": title, "anchors": [f"{page}#letters"], "path": letter["path"],
                    **({"kind": "docx", "source": letter["docx_path"]} if letter["docx_path"]
                       else {"kind": "md", "source": letter["body_md"]})})
    for f in app.extra_files:
        if f["is_md"] and f["body_md"].strip():
            out.append({"title": f["rel"], "kind": "md", "source": f["body_md"], "path": f["path"],
                        "anchors": [f"{page}#{f['anchor']}"]})
    if app.notes_md.strip():
        out.append({"title": "My notes", "kind": "md", "source": app.notes_md,
                    "path": app._folder_file("notes.md"), "anchors": [f"{page}#notes"]})
    if app.todo_md.strip():
        out.append({"title": "To do", "kind": "md", "source": app.todo_md,
                    "path": app._folder_file("todo.md"), "anchors": [f"{page}#todo"]})
    for r in sorted(app.interview_files, key=lambda r: (r["date"] is None, r["date"], r["name"])):
        url = reverse("tracker:interview_round", args=[app.num, r["anchor"]])
        out.append({"title": f"Interview: {r['label']}" + (f" ({r['date']})" if r["date"] else ""),
                    "kind": "md", "source": r["body_md"], "path": r["path"],
                    "anchors": [url, f"{page}#{r['anchor']}"]})
    if app.company_id and app.company.notes_md.strip():
        out.append({"title": f"Company: {app.company.name}", "kind": "md",
                    "source": app.company.notes_md, "path": app.company.notes_path,
                    "anchors": [reverse("tracker:company_detail", args=[app.company.slug])]})
    for note in app.linked_note_files:
        out.append({"title": f"Note: {note['label']}", "kind": "md", "path": note["path"],
                    "source": note["path"].read_text(encoding="utf-8"), "anchors": [note["href"]]})
    for i, part in enumerate(out, 1):
        part["key"] = f"s{i:02d}"
    return out


def build(app, out_path: Path) -> list[str]:
    """Write `app`'s dossier to `out_path`; return the section titles, in order."""
    parts = sections(app)
    _Dossier(app, parts).save(out_path)
    return [p["title"] for p in parts]


class _Dossier:
    def __init__(self, app, parts):
        self.app, self.parts = app, parts
        self.doc = Document()
        self.bookmarks: set[str] = set()
        self.pending: list[tuple] = []  # (w:hyperlink, part key, heading slug)
        self.next_id = 100
        self.imports = 0
        # Every site address a part answers to. A fragment on the application page names a
        # tab, so its prefix (`#notes--background` → `notes`) is enough to find the part.
        self.urls = {}
        for part in parts:
            for url in part["anchors"]:
                self.urls[url] = part["key"]
        self._setup()

    # -- page and styles ---------------------------------------------------
    def _setup(self):
        doc = self.doc
        section = doc.sections[0]
        section.page_width, section.page_height = Cm(21), Cm(29.7)
        section.left_margin = section.right_margin = Cm(2)
        section.top_margin = section.bottom_margin = Cm(2)
        normal = doc.styles["Normal"]
        normal.font.name = "Calibri"
        normal.font.size = Pt(11)
        normal.paragraph_format.space_after = Pt(6)
        for level, size in zip(range(1, 7), [20, 15, 13, 11.5, 11, 11]):
            h = doc.styles[f"Heading {level}"]
            h.font.name, h.font.size, h.font.color.rgb = "Calibri", Pt(size), NAVY
            h.font.bold, h.font.italic = True, False
            fonts = h.element.get_or_add_rPr().find(qn("w:rFonts"))
            if fonts is not None:  # the template sets theme fonts, which win over a name
                fonts.attrib.clear()
                for a in ("ascii", "hAnsi", "cs", "eastAsia"):
                    fonts.set(qn(f"w:{a}"), "Calibri")
        doc.styles["Heading 1"].paragraph_format.page_break_before = True
        doc.core_properties.title = f"Dossier: {self.app}"

    def save(self, out_path: Path):
        app = self.app
        title = self.doc.add_paragraph()
        run = title.add_run(f"{app.company.name if app.company_id else app.company_name}: "
                            f"application #{app.num}")
        run.bold, run.font.size, run.font.color.rgb = True, Pt(26), NAVY
        self.doc.add_paragraph().add_run(
            f"{app.role}. Everything in one file, exported {date.today():%-d %B %Y}.").italic = True
        self.doc.add_paragraph().add_run("Contents").bold = True
        for part in self.parts:
            p = self.doc.add_paragraph(style="List Bullet")
            p.paragraph_format.space_after = Pt(1)
            self._link(p, part["title"], target=(part["key"], ""))

        for part in self.parts:
            head = self.doc.add_paragraph(part["title"], style="Heading 1")
            self._bookmark(head, part["key"])
            self.part, self.file = part["key"], part.get("path")
            if part["kind"] == "overview":
                self._overview()
            elif part["kind"] == "docx":
                self._import_docx(Path(part["source"]))
            else:
                self._markdown(part["source"])

        for link, key, frag in self.pending:
            name = self._bm_name(key, frag)
            link.set(qn("w:anchor"), name if frag and name in self.bookmarks else key)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        self.doc.save(out_path)

    # -- the parts ---------------------------------------------------------
    def _overview(self):
        from .templatetags.jobs_extras import markdownify

        app = self.app
        rows = [("Role", app.role), ("Company", app.company.name if app.company_id else app.company_name),
                ("Status", app.get_status_display()), ("Next action", app.next_action),
                ("Contact", app.contact), ("Job posting", app.job_url)]
        table = self.doc.add_table(rows=0, cols=2)
        table.style = "Table Grid"
        for label, value in rows:
            if value:
                cells = table.add_row().cells
                cells[0].paragraphs[0].add_run(label).bold = True
                cells[1].text = str(value)
        self.doc.add_paragraph()
        fit = app.fit_summary
        if fit["level_label"]:
            self.doc.add_paragraph().add_run(f"Fit: {fit['level_label']}").bold = True
        for label, key in (("Pros", "pros"), ("Cons", "cons"), ("Unknowns", "unknowns")):
            if fit[key]:
                self.doc.add_paragraph(label, style="Heading 3")
                for line in fit[key]:
                    self.doc.add_paragraph(line, style="List Bullet")
        if app.summary.strip():
            self._walk(lxml.html.fragment_fromstring(str(markdownify(app.summary)), create_parent="div"))

    def _markdown(self, text):
        from .parsers import render_tasks
        from .templatetags.jobs_extras import markdownify

        html = str(markdownify(render_tasks(text, None)))
        self._walk(lxml.html.fragment_fromstring(html, create_parent="div"), skip_h1=True)

    def _import_docx(self, path: Path):
        """Copy the body of the .docx at `path` to the end of the dossier, keeping its look.

        Its styles come along under a prefix (`D1_Heading2`), so a CV's gold section titles
        stay gold without restyling the dossier's own headings. A hyperlink names its
        target by a relationship id that only means something in its own package, so each
        one is re-made here; a dangling id is what makes Word call a file damaged.
        """
        self.imports += 1
        src = Document(path)
        ensure = self._style_importer(src, f"D{self.imports}_")
        default = next((s.get(qn("w:styleId")) for s in src.styles.element.findall(qn("w:style"))
                        if s.get(qn("w:default")) == "1" and s.get(qn("w:type")) == "paragraph"), None)
        anchor = self.doc.element.body.sectPr
        for el in src.element.body.iterchildren():
            if el.tag == qn("w:sectPr"):
                continue
            el = deepcopy(el)
            for ref in el.iter(qn("w:pStyle"), qn("w:rStyle"), qn("w:tblStyle")):
                ref.set(qn("w:val"), ensure(ref.get(qn("w:val"))) or ref.get(qn("w:val")))
            if el.tag == qn("w:p") and default and el.find(f"{qn('w:pPr')}/{qn('w:pStyle')}") is None:
                ppr = el.find(qn("w:pPr"))
                if ppr is None:
                    ppr = OxmlElement("w:pPr")
                    el.insert(0, ppr)
                ref = OxmlElement("w:pStyle")
                ref.set(qn("w:val"), ensure(default))
                ppr.insert(0, ref)
            for node in el.iter():
                for attr in (qn("r:id"), qn("r:embed")):
                    rid = node.get(attr)
                    if rid is None or rid not in src.part.rels:
                        continue
                    rel = src.part.rels[rid]
                    node.set(attr, self.doc.part.relate_to(rel.target_ref, rel.reltype, is_external=True)
                             if rel.is_external else self.doc.part.relate_to(rel.target_part, rel.reltype))
            anchor.addprevious(el)

    def _style_importer(self, src, prefix):
        theirs, ours = src.styles.element, self.doc.styles.element

        def ensure(sid):
            new = prefix + sid
            if any(s.get(qn("w:styleId")) == new for s in ours.findall(qn("w:style"))):
                return new
            style = next((s for s in theirs.findall(qn("w:style")) if s.get(qn("w:styleId")) == sid), None)
            if style is None:
                return None
            style = deepcopy(style)
            style.set(qn("w:styleId"), new)
            style.attrib.pop(qn("w:default"), None)
            style.set(qn("w:customStyle"), "1")
            style.find(qn("w:name")).set(qn("w:val"), new)
            for tag in ("w:link", "w:next", "w:qFormat", "w:uiPriority", "w:semiHidden", "w:unhideWhenUsed"):
                if (x := style.find(qn(tag))) is not None:
                    style.remove(x)
            if (based := style.find(qn("w:basedOn"))) is not None:
                parent = ensure(based.get(qn("w:val")))
                if parent:
                    based.set(qn("w:val"), parent)
                else:
                    style.remove(based)
            ours.append(style)
            return new

        return ensure

    # -- bookmarks and links -----------------------------------------------
    @staticmethod
    def _bm_name(key, frag):
        # Word's limits: 40 characters, letters, digits and underscores.
        return re.sub(r"[^A-Za-z0-9]", "_", f"{key}_{frag}")[:40]

    def _bookmark(self, par, name):
        if name in self.bookmarks:
            return
        self.bookmarks.add(name)
        self.next_id += 1
        start, end = OxmlElement("w:bookmarkStart"), OxmlElement("w:bookmarkEnd")
        start.set(qn("w:id"), str(self.next_id))
        start.set(qn("w:name"), name)
        end.set(qn("w:id"), str(self.next_id))
        par._p.insert(1 if par._p.pPr is not None else 0, start)
        par._p.append(end)

    def _resolve(self, href):
        """(part key, heading slug) for a site link that lands inside the dossier, else None."""
        url, _, frag = href.partition("#")
        if not url:
            key = self.part
            for page, k in self.urls.items():  # `#round-…` in a file names another part
                if "#" in page and frag.split("--")[0] == page.partition("#")[2]:
                    key = k
        else:
            key = self.urls.get(url)
            if key is None and frag:
                key = self.urls.get(f"{url}#{frag.split('--')[0]}")
            if key is None:
                return None
        return key, (frag.split("--")[-1] if frag else "")

    def _link(self, par, text, url=None, target=None, **fmt):
        link = OxmlElement("w:hyperlink")
        if url:
            link.set(qn("r:id"), par.part.relate_to(url, RT.HYPERLINK, is_external=True))
        else:
            self.pending.append((link, *target))
        run = self._style(par.add_run(text), **fmt)
        run.font.color.rgb, run.font.underline = LINK, True
        link.append(run._r)
        par._p.append(link)

    # -- HTML into paragraphs ----------------------------------------------
    def _walk(self, node, level=0, quote=False, skip_h1=False):
        if node.text and node.text.strip():
            self._text(self._para(level, quote), node.text)
        for child in node:
            if isinstance(child.tag, str) and child.tag not in ("script", "style"):
                self._block(child, level, quote, skip_h1)
            if child.tail and child.tail.strip():
                self._text(self._para(level, quote), child.tail)

    def _para(self, level=0, quote=False, style=None):
        p = self.doc.add_paragraph(style=style)
        if level or quote:
            p.paragraph_format.left_indent = Cm(0.63 * (level + 1))
        return p

    def _block(self, el, level, quote, skip_h1=False):
        from .parsers import section_slug

        tag = el.tag
        if re.fullmatch(r"h[1-6]", tag):
            if tag == "h1" and skip_h1:
                return  # the section's own title stands in for the file's
            p = self.doc.add_paragraph(style=f"Heading {max(2, int(tag[1]))}")
            self._inline(p, el)
            self._bookmark(p, self._bm_name(self.part, section_slug(el.text_content())))
        elif tag in ("ul", "ol"):
            for n, li in enumerate(el.findall("li"), 1):
                self._item(li, level, tag == "ol", n)
        elif tag == "table":
            self._table(el)
        elif tag == "pre":
            for line in el.text_content().rstrip("\n").split("\n"):
                p = self._para(level)
                p.paragraph_format.space_after = Pt(0)
                self._style(p.add_run(line), code=True)
        elif tag == "blockquote":
            self._walk(el, level + 1, True)
        elif tag == "hr":
            p = self.doc.add_paragraph()
            border, bottom = OxmlElement("w:pBdr"), OxmlElement("w:bottom")
            for k, v in (("val", "single"), ("sz", "4"), ("space", "1"), ("color", "BBBBBB")):
                bottom.set(qn(f"w:{k}"), v)
            border.append(bottom)
            p._p.get_or_add_pPr().append(border)
        elif tag == "img":
            self._picture(self.doc.add_paragraph(), el)
        elif tag in BLOCK and tag != "p" and any(isinstance(c.tag, str) and c.tag in BLOCK for c in el):
            self._walk(el, level, quote)
        else:
            p = self._para(level, quote)
            if tag in BLOCK:
                self._inline(p, el, i=quote)
            else:  # an inline element standing on its own
                wrap = lxml.html.Element("span")
                wrap.append(deepcopy(el))
                wrap[0].tail = None
                self._inline(p, wrap)

    def _item(self, li, level, ordered, n):
        # Numbers are written out: Word's list numbering runs on across every numbered
        # list in the document, so the second list of the file would start at 7.
        if ordered:
            p = self._para(level)
            p.paragraph_format.first_line_indent = Cm(-0.5)
            p.add_run(f"{n}. ")
        else:
            p = self.doc.add_paragraph(style={0: "List Bullet", 1: "List Bullet 2"}.get(level, "List Bullet 3"))
        p.paragraph_format.space_after = Pt(3)
        if li.text:
            self._text(p, li.text.lstrip())
        first = True
        for child in li:
            if not isinstance(child.tag, str):
                continue
            if child.tag == "p" and first:
                self._inline(p, child)  # a loose list's <p> fills the item's own line
            elif child.tag in ("ul", "ol"):
                for m, sub in enumerate(child.findall("li"), 1):
                    self._item(sub, level + 1, child.tag == "ol", m)
            elif child.tag == "p":
                self._inline(self._para(level), child)
            elif child.tag in BLOCK:
                self._block(child, level + 1, False)
            else:
                wrap = lxml.html.Element("span")
                wrap.append(deepcopy(child))
                wrap[0].tail = None
                self._inline(p, wrap)
            first = False
            if child.tail and child.tail.strip():
                self._text(p, child.tail)

    def _table(self, el):
        rows = el.findall(".//tr")
        if not rows:
            return
        width = max(sum(int(c.get("colspan") or 1) for c in r if c.tag in ("td", "th")) for r in rows)
        table = self.doc.add_table(rows=0, cols=width)
        table.style = "Table Grid"
        for r in rows:
            cells, j = table.add_row().cells, 0
            for c in r:
                if c.tag not in ("td", "th"):
                    continue
                p = cells[j].paragraphs[0]
                p.paragraph_format.space_after = Pt(0)
                self._inline(p, c, b=c.tag == "th", size=9.5)
                j += int(c.get("colspan") or 1)
        self.doc.add_paragraph()

    def _inline(self, par, node, **fmt):
        if node.text:
            self._text(par, node.text, **fmt)
        for c in node:
            if isinstance(c.tag, str):
                g, tag = dict(fmt), c.tag
                if tag in ("strong", "b"):
                    g["b"] = True
                    g["red"] = c.text_content().strip().startswith("Q:")
                elif tag in ("em", "i"):
                    g["i"] = True
                elif tag == "code":
                    g["code"] = True
                elif tag == "mark":
                    g["mark"] = True
                if tag == "br":
                    par.add_run().add_break()
                elif tag == "input":
                    par.add_run("☑ " if c.get("checked") is not None else "☐ ")
                elif tag == "img":
                    self._picture(par, c)
                elif tag == "a":
                    href, text = c.get("href") or "", re.sub(r"\s+", " ", c.text_content())
                    if href.startswith(("http://", "https://", "mailto:")):
                        self._link(par, text, url=href, **g)
                    elif target := self._resolve(href):
                        self._link(par, text, target=target, **g)
                    else:  # a site page the dossier does not hold
                        self._style(par.add_run(text), **g)
                else:
                    self._inline(par, c, **g)
            if c.tail:
                self._text(par, c.tail, **fmt)

    def _text(self, par, text, **fmt):
        text = re.sub(r"[ \t\r\n]+", " ", text)
        if text.strip() or (text == " " and par.runs):
            self._style(par.add_run(text), **fmt)

    @staticmethod
    def _style(run, b=False, i=False, code=False, mark=False, red=False, size=None):
        if b:
            run.bold = True
        if i:
            run.italic = True
        if code:
            run.font.name, run.font.size = "Menlo", Pt(9.5)
        elif size:
            run.font.size = Pt(size)
        if mark:
            run.font.highlight_color = WD_COLOR_INDEX.YELLOW
        if red:
            run.font.color.rgb = RED
        return run

    def _picture(self, par, img):
        src = img.get("src") or ""
        if src.startswith("data:"):
            data = io.BytesIO(base64.b64decode(src.split(",", 1)[1]))
        else:
            found = self.file and (Path(self.file).parent / src)
            if not (found and found.is_file()):
                par.add_run(f"[image: {img.get('alt') or src}]").italic = True
                return
            data = str(found)
        par.add_run().add_picture(data, width=Cm(16))
