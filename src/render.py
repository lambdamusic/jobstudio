#!/usr/bin/env python3
"""
render.py — Template-based HTML/PDF export for CV markdown and cover letters.

Parses a CV markdown file (functional or chronological) and renders it to HTML/PDF/DOCX
without any API call.

Usage:
    python render.py --functional
    python render.py --chronological --file path/to/file.md --format pdf
    python render.py --docx --functional --file path/to/tailored.md
    python render.py --cover-letter --file path/to/cover-letter.md --label 001-grafana-labs
"""

import argparse
import re
import shutil
import sys
import tempfile
import html as _html
import subprocess
from datetime import date
from pathlib import Path
from string import Template

import appfolder
import config
import identity

DATA_ROOT = config.data_root()
EXPORTS_DIR = DATA_ROOT / "exports"
FUNCTIONAL_CV = DATA_ROOT / "jobs" / "cv" / "base" / "cv_functional.md"
CHRONOLOGICAL_CV = DATA_ROOT / "jobs" / "cv" / "base" / "cv_chronological.md"
# Code, not data — the HTML/PDF templates ship with the repo.
TEMPLATES_DIR = Path(__file__).parent / "templates"

_DOCX_HINT = "python-docx is required for --docx (pip install python-docx)"


BASE_CV_DIR = DATA_ROOT / "jobs" / "cv" / "base"
CV_EXPORT_DIR = DATA_ROOT / "jobs" / "cv" / "export"


def _export_dir(fmt: str) -> Path:
    """exports/<fmt>/<YYYY-MM-DD>/ for today, created on demand."""
    d = EXPORTS_DIR / fmt / date.today().isoformat()
    d.mkdir(parents=True, exist_ok=True)
    return d


def _home(src_path: Path | None, filetype: str, ext: str, *, stem: str) -> Path:
    """Where a render of `src_path` belongs — with whatever it was rendered from, when
    that has a home of its own (2026-09-24):

        jobs/applications/NNN-*/...   ->  <that folder>/export/
        jobs/cv/base/*.md             ->  jobs/cv/export/
        anything else                 ->  exports/<fmt>/<date>/

    Until now every render went to `exports/` and application CVs were *then* copied
    back, leaving two copies of each file and one flat dated tree that named neither its
    source nor the application it was for. The cleanup that followed could not attribute
    22 of those renders to any application at all. So the home is chosen up front and
    written once; `exports/` stays for documents that genuinely belong to no folder —
    a career stocktake, an ad-hoc `--file` from outside the data root.
    """
    if src_path is not None:
        src_path = Path(src_path)
        folder = appfolder.app_folder_of(src_path)
        if folder is not None:
            dest_dir = appfolder.export_dir(folder)
            dest_dir.mkdir(parents=True, exist_ok=True)
            return dest_dir / appfolder.app_filename(folder, filetype, ext)
        if src_path.resolve().parent == BASE_CV_DIR.resolve():
            CV_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
            # Named like jobs/cv/base/archive/, the other place a dated copy of a base
            # CV lives — `cv_functional-2026-09-22.docx` beside `cv_functional-...md`.
            return CV_EXPORT_DIR / f"{src_path.stem}-{date.today().isoformat()}.{ext}"
    return _export_dir(ext) / f"{stem}.{ext}"


# ── Inline markdown → HTML ───────────────────────────────────────────────────

def _inline(text: str) -> str:
    """Convert inline markdown (links, bold, italic) to HTML."""
    pattern = re.compile(r'\[([^\]]+)\]\(([^)]+)\)|\*\*(.+?)\*\*|\*([^*]+)\*')
    parts = []
    last = 0
    for m in pattern.finditer(text):
        parts.append(_html.escape(text[last:m.start()], quote=False))
        last = m.end()
        if m.group(1) is not None:
            parts.append(f'<a href="{_html.escape(m.group(2))}">{_html.escape(m.group(1), quote=False)}</a>')
        elif m.group(3) is not None:
            parts.append(f'<strong>{_html.escape(m.group(3), quote=False)}</strong>')
        else:
            parts.append(f'<em>{_html.escape(m.group(4), quote=False)}</em>')
    parts.append(_html.escape(text[last:], quote=False))
    return ''.join(parts)


def _e(text: str) -> str:
    return _html.escape(text, quote=False)


# ── Section parsers ──────────────────────────────────────────────────────────

def _parse_contact(header: str) -> list[dict]:
    items = []
    for m in re.finditer(r'\*\*([^*]+):\*\*\s*(.+)', header):
        key = m.group(1).strip()
        val = m.group(2).strip()
        link_m = re.match(r'\[([^\]]+)\]\(([^)]+)\)', val)
        if link_m:
            items.append({'label': key, 'text': link_m.group(1), 'url': link_m.group(2)})
        else:
            items.append({'label': key, 'text': val, 'url': None})
    return items


def _parse_summary(section: str) -> list[str]:
    paras = []
    for para in re.split(r'\n\n+', section.strip()):
        para = para.strip()
        if para and not para.startswith('---'):
            paras.append(_inline(para))
    return paras


def _parse_experience(section: str) -> tuple[list[dict], dict | None]:
    blocks = re.split(r'\n### ', '\n' + section)
    jobs = []
    early_career = None

    for block in blocks:
        if not block.strip():
            continue
        lines = block.strip().split('\n')

        header_line = lines[0]
        if ' — ' in header_line:
            role_part, company_part = header_line.split(' — ', 1)
        else:
            role_part, company_part = header_line, ''

        role = role_part.strip()
        company_html = _inline(company_part.strip())

        # Date/meta: first bold line after the header
        meta = ''
        for line in lines[1:]:
            m = re.match(r'\*\*(.+?)\*\*\s*(?:\|\s*(.+))?', line.strip())
            if m:
                date_str = _e(m.group(1))
                loc_str = _e(m.group(2).strip()) if m.group(2) else ''
                meta = f'{date_str} · {loc_str}' if loc_str else date_str
                break

        # Bullets and tech line
        bullets = []
        tech = None
        for line in lines:
            if not line.strip().startswith('- '):
                continue
            content = line.strip()[2:].strip()
            if re.match(r'\*\*[Cc]ore [Tt]echnologies', content):
                tech = _inline(content)
            else:
                bullets.append(_inline(content))

        # Prose (for early career block)
        prose_parts = []
        for line in lines[1:]:
            stripped = line.strip()
            if not stripped or stripped.startswith('**') or stripped.startswith('-'):
                continue
            prose_parts.append(_inline(stripped))

        entry = {
            'role': _e(role),
            'company_html': company_html,
            'meta': meta,
            'bullets': bullets,
            'tech': tech,
            'prose': ' '.join(prose_parts),
            'is_early_career': 'early career' in role.lower(),
        }

        if entry['is_early_career']:
            early_career = entry
        else:
            jobs.append(entry)

    return jobs, early_career


def _parse_education(section: str) -> list[dict]:
    entries = []
    current: dict | None = None

    for line in section.strip().split('\n'):
        line = line.strip()
        if not line or line == '---':
            continue

        degree_m = re.match(r'\*\*([^*]+)\*\*\s*(.*)$', line)
        if degree_m:
            if current:
                entries.append(current)
            current = {
                'degree': _e(degree_m.group(1).strip()),
                'extra': _inline(degree_m.group(2).strip()),
                'inst': '', 'years': '', 'focus': '',
            }
        elif current and '|' in line:
            inst, years = line.split('|', 1)
            current['inst'] = _e(inst.strip())
            current['years'] = _e(years.strip())
        elif current and line.lower().startswith('focus:'):
            current['focus'] = _e(line[6:].strip())
        elif current and not current['inst']:
            current['inst'] = _e(line)

    if current:
        entries.append(current)
    return entries


def _parse_skills(section: str) -> tuple[list[dict], list[dict]]:
    skills = []
    languages = []
    for m in re.finditer(r'\*\*([^*]+):\*\*\s*(.+)', section):
        label = m.group(1).strip()
        text = m.group(2).strip()
        if label.lower() == 'languages':
            for lang_m in re.finditer(r'([A-Za-zÀ-ÿ]+(?:\s+[A-Za-zÀ-ÿ]+)*)\s+\(([^)]+)\)', text):
                languages.append({'lang': lang_m.group(1), 'level': lang_m.group(2)})
        else:
            skills.append({'label': _e(label), 'text': _inline(text)})
    return skills, languages


def _parse_publications(section: str) -> list[str]:
    pubs = []
    for m in re.finditer(r'^-\s+(.+)$', section, re.MULTILINE):
        content = m.group(1).strip()
        content = re.sub(r'^\*(.+)\*$', r'\1', content)
        pubs.append(_inline(content))
    return pubs


# ── Functional-CV section parsers ────────────────────────────────────────────

def _parse_competencies(section: str) -> list[dict]:
    """Parse '## Core Competencies' into clusters: title, statement, bullets, tech."""
    clusters = []
    for block in re.split(r'\n### ', '\n' + section):
        block = block.strip()
        if not block:
            continue
        lines = block.split('\n')
        title = _inline(lines[0].strip())
        statement, bullets, tech = '', [], None
        for line in lines[1:]:
            s = line.strip()
            if not s:
                continue
            if s.startswith('- '):
                bullets.append(_inline(s[2:].strip()))
                continue
            tech_m = re.match(r'\*Core technologies:\s*(.+?)\.?\*$', s)
            if tech_m:
                tech = _inline(tech_m.group(1).strip())
            elif not bullets:
                statement = (statement + ' ' + _inline(s)).strip()
        clusters.append({'title': title, 'statement': statement,
                         'bullets': bullets, 'tech': tech})
    return clusters


def _parse_career_history(section: str) -> list[dict]:
    """Parse '## Career History' into employer entries with nested roles."""
    entries = []
    for block in re.split(r'\n### ', '\n' + section):
        block = block.strip()
        if not block:
            continue
        lines = block.split('\n')
        org_html = _inline(lines[0].strip())
        dates, context, summary, roles = '', '', '', []
        for line in lines[1:]:
            s = line.strip()
            if not s:
                continue
            if s.startswith('- '):
                item = s[2:].strip()
                rm = re.match(r'(.+?)\s+[—–]\s+\*(.+?)\*$', item)
                if rm:
                    roles.append({'role': _inline(rm.group(1).strip()),
                                  'dates': _e(rm.group(2).strip())})
                else:
                    roles.append({'role': _inline(item), 'dates': ''})
            elif s.startswith('*') and not roles:
                dm = re.match(r'\*([\d\s—–\-]+)\*(?:\s*·\s*(.+))?$', s)
                if dm:
                    dates = _e(dm.group(1).strip())
                    context = _inline(dm.group(2).strip()) if dm.group(2) else ''
                elif s.endswith('*'):
                    # An italic prose line before the roles: a one-line
                    # summary of the employer / tenure.
                    summary = _inline(s[1:-1].strip())
        entries.append({'org_html': org_html, 'dates': dates,
                        'context': context, 'summary': summary, 'roles': roles})
    return entries


# ── Top-level parse ──────────────────────────────────────────────────────────

def parse_variant(md_path: Path) -> dict:
    """Parse a chronological CV (cv_chronological.md, or a per-application tailored copy)."""
    text = md_path.read_text()

    parts = re.split(r'\n## (.+)\n', text)
    header = parts[0]
    sections: dict[str, str] = {}
    for i in range(1, len(parts), 2):
        sec_name = parts[i].strip()
        sections[sec_name] = parts[i + 1].strip() if i + 1 < len(parts) else ''

    name_m = re.search(r'^# (.+)', header, re.MULTILINE)
    full_name = name_m.group(1).strip() if name_m else identity.full_name()
    name_parts = full_name.rsplit(' ', 1)
    first_name = _e(name_parts[0]) if len(name_parts) > 1 else _e(full_name)
    last_name = _e(name_parts[1]) if len(name_parts) > 1 else ''

    jobs, early_career = _parse_experience(sections.get('Experience', ''))
    pub_key = next((k for k in sections if 'publication' in k.lower()), None)

    return {
        'title': _e(full_name) + ' — CV',
        'first_name': first_name,
        'last_name': last_name,
        'current_role': jobs[0]['role'] if jobs else '',
        'target_subtitle': '',
        'contact': _parse_contact(header),
        'summary': _parse_summary(sections.get('Summary', '')),
        'jobs': jobs,
        'early_career': early_career,
        'education': _parse_education(sections.get('Education', '')),
        'skills': _parse_skills(sections.get('Skills', ''))[0],
        'languages': _parse_skills(sections.get('Skills', ''))[1],
        'publications': _parse_publications(sections[pub_key]) if pub_key else [],
    }


def parse_functional(md_path: Path) -> dict:
    """Parse the functional CV (competencies-first, condensed history)."""
    text = md_path.read_text()
    parts = re.split(r'\n## (.+)\n', text)
    header = parts[0]
    sections: dict[str, str] = {}
    for i in range(1, len(parts), 2):
        sections[parts[i].strip()] = parts[i + 1].strip() if i + 1 < len(parts) else ''

    name_m = re.search(r'^# (.+)', header, re.MULTILINE)
    full_name = name_m.group(1).strip() if name_m else identity.full_name()
    name_parts = full_name.rsplit(' ', 1)
    first_name = _e(name_parts[0]) if len(name_parts) > 1 else _e(full_name)
    last_name = _e(name_parts[1]) if len(name_parts) > 1 else ''

    career = _parse_career_history(sections.get('Career History', ''))

    # Subtitle line under the name: an explicit prose line in the header
    # (first non-blank, non-bullet line after '# Name') wins; otherwise fall
    # back to the most recent job title.
    current_role = ''
    if name_m:
        for line in header[name_m.end():].splitlines():
            s = line.strip()
            if not s or s == '---':
                continue
            if s.startswith(('- ', '**', '#')):
                break
            current_role = s  # plain text; escaped once in the return dict
            break
    if not current_role and career and career[0]['roles']:
        current_role = _html.unescape(
            re.sub(r'<[^>]+>', '', career[0]['roles'][0]['role']))
    pub_key = next((k for k in sections if 'publication' in k.lower()), None)

    return {
        'title': _e(full_name) + ' — CV',
        'first_name': first_name,
        'last_name': last_name,
        'current_role': _e(current_role),
        'contact': _parse_contact(header),
        'summary': _parse_summary(sections.get('Summary', '')),
        'competencies': _parse_competencies(sections.get('Core Competencies', '')),
        'career': career,
        'education': _parse_education(sections.get('Education', '')),
        'skills': _parse_skills(sections.get('Skills', ''))[0],
        'languages': _parse_skills(sections.get('Skills', ''))[1],
        'publications': _parse_publications(sections[pub_key]) if pub_key else [],
    }


# ── HTML section renderers ───────────────────────────────────────────────────

def _r_contact(items: list[dict]) -> str:
    parts = []
    for item in items:
        if item['url']:
            # Use the label as display text (e.g. "LinkedIn", "Website")
            parts.append(f'      <li><a href="{_html.escape(item["url"])}">{_e(item["label"])}</a></li>')
        else:
            # Plain text: show value (email, location, etc.)
            parts.append(f'      <li>{_e(item["text"])}</li>')
    return '\n'.join(parts)


def _r_skills(groups: list[dict]) -> str:
    parts = []
    for sg in groups:
        parts.append(
            f'    <div class="skill-group">\n'
            f'      <span class="skill-label">{sg["label"]}</span>\n'
            f'      <span class="skill-text">{sg["text"]}</span>\n'
            f'    </div>'
        )
    return '\n'.join(parts)


def _r_education(entries: list[dict]) -> str:
    parts = []
    for e in entries:
        lines = [f'    <span class="edu-degree">{e["degree"]}</span>']
        if e['extra']:
            lines.append(f'    <span class="edu-focus">{e["extra"]}</span>')
        if e['inst']:
            lines.append(f'    <span class="edu-inst">{e["inst"]}</span>')
        if e['years']:
            lines.append(f'    <span class="edu-year">{e["years"]}</span>')
        if e['focus']:
            lines.append(f'    <span class="edu-focus">Focus: {e["focus"]}</span>')
        parts.append('\n'.join(lines))
    return '\n\n'.join(parts)


def _r_languages(languages: list[dict]) -> str:
    return '\n'.join(
        f'      <li>{_e(lang["lang"])} — {_e(lang["level"])}</li>'
        for lang in languages
    )


def _r_summary(paras: list[str]) -> str:
    return '\n'.join(f'      <p>{p}</p>' for p in paras)


def _r_job(job: dict) -> str:
    bullets = '\n'.join(f'        <li>{b}</li>' for b in job['bullets'])
    tech = f'\n      <div class="job-tech">{job["tech"]}</div>' if job['tech'] else ''
    return (
        f'    <div class="job">\n'
        f'      <div class="job-header">\n'
        f'        <span class="job-company">{job["company_html"]}</span>\n'
        f'        <span class="job-sep"> — </span>\n'
        f'        <span class="job-role">{job["role"]}</span>\n'
        f'      </div>\n'
        f'      <div class="job-meta">{job["meta"]}</div>\n'
        f'      <ul>\n{bullets}\n      </ul>{tech}\n'
        f'    </div>'
    )


def _r_early_career(ec: dict | None) -> str:
    if not ec:
        return ''
    if ec['bullets']:
        items = '\n'.join(f'        <li>{b}</li>' for b in ec['bullets'])
        body = f'      <ul>\n{items}\n      </ul>'
    else:
        body = f'      <p>{ec["prose"]}</p>'
    return (
        f'    <div class="early-career">\n'
        f'      <div class="ec-title">{ec["role"]}</div>\n'
        f'      <div class="ec-meta">{ec["meta"]}</div>\n'
        f'{body}\n'
        f'    </div>'
    )


def _r_publications(pubs: list[str]) -> str:
    if not pubs:
        return ''
    items = '\n'.join(f'        <li><em>{p}</em></li>' for p in pubs)
    return (
        f'    <div class="publications">\n'
        f'      <div class="section-title">S E L E C T E D &nbsp; P U B L I C A T I O N S</div>\n'
        f'      <ul>\n{items}\n      </ul>\n'
        f'    </div>'
    )


# ── Main render ──────────────────────────────────────────────────────────────

def render_html(data: dict, template_name: str = "cv_navy.html") -> str:
    template = Template((TEMPLATES_DIR / template_name).read_text())
    jobs_html = '\n\n'.join(_r_job(j) for j in data['jobs'])
    return template.substitute(
        title=data['title'],
        first_name=data['first_name'],
        last_name=data['last_name'],
        current_role=data['current_role'],
        target_subtitle=data['target_subtitle'],
        contact_html=_r_contact(data['contact']),
        skills_html=_r_skills(data['skills']),
        education_html=_r_education(data['education']),
        languages_html=_r_languages(data['languages']),
        summary_html=_r_summary(data['summary']),
        jobs_html=jobs_html,
        early_career_html=_r_early_career(data['early_career']),
        publications_html=_r_publications(data['publications']),
    )


# ── Functional-CV renderers ─────────────────────────────────────────────────

def _r_contact_inline(items: list[dict]) -> str:
    parts = []
    for item in items:
        if item['url']:
            parts.append(f'<a href="{_html.escape(item["url"])}">{_e(item["label"])}</a>')
        else:
            parts.append(_e(item['text']))
    return ' <span class="dot">·</span> '.join(parts)


def _r_competencies(clusters: list[dict]) -> str:
    out = []
    for c in clusters:
        bullets = '\n'.join(f'        <li>{b}</li>' for b in c['bullets'])
        stmt = f'\n      <p class="comp-statement">{c["statement"]}</p>' if c['statement'] else ''
        tech = (f'\n      <p class="comp-tech"><span>Core technologies:</span> {c["tech"]}</p>'
                if c['tech'] else '')
        out.append(
            f'    <div class="comp">\n'
            f'      <h3 class="comp-title">{c["title"]}</h3>{stmt}\n'
            f'      <ul>\n{bullets}\n      </ul>{tech}\n'
            f'    </div>'
        )
    return '\n'.join(out)


def _r_career(entries: list[dict]) -> str:
    out = []
    for e in entries:
        meta = e['dates']
        if e['context']:
            meta = f'{meta} <span class="dot">·</span> {e["context"]}' if meta else e['context']
        roles = []
        for r in e['roles']:
            d = f'<span class="cr-role-date">{r["dates"]}</span>' if r['dates'] else ''
            roles.append(f'        <li><span class="cr-role">{r["role"]}</span>{d}</li>')
        roles_html = f'\n      <ul>\n{chr(10).join(roles)}\n      </ul>' if roles else ''
        summary_html = (
            f'\n      <p class="cr-summary">{e["summary"]}</p>'
            if e.get('summary') else ''
        )
        out.append(
            f'    <div class="cr-entry">\n'
            f'      <div class="cr-head">\n'
            f'        <span class="cr-org">{e["org_html"]}</span>\n'
            f'        <span class="cr-dates">{meta}</span>\n'
            f'      </div>{summary_html}{roles_html}\n'
            f'    </div>'
        )
    return '\n'.join(out)


def _r_pub_list(pubs: list[str]) -> str:
    return '\n'.join(f'        <li>{p}</li>' for p in pubs)


def render_functional(data: dict, template_name: str = "cv_functional.html") -> str:
    template = Template((TEMPLATES_DIR / template_name).read_text())
    return template.substitute(
        title=data['title'],
        first_name=data['first_name'],
        last_name=data['last_name'],
        current_role=data['current_role'],
        contact_html=_r_contact_inline(data['contact']),
        summary_html=_r_summary(data['summary']),
        competencies_html=_r_competencies(data['competencies']),
        career_html=_r_career(data['career']),
        education_html=_r_education(data['education']),
        skills_html=_r_skills(data['skills']),
        languages_html=_r_languages(data['languages']),
        publications_html=_r_pub_list(data['publications']),
    )


# ── Public API ───────────────────────────────────────────────────────────────

# Headless Chrome renders the PDF export. Supported platforms are macOS and Linux
# (§1 blocker 10); `chrome_path` in ~/.jobstudio.ini overrides the search entirely, which
# is also how anyone on a third platform makes this work without a code change.
_CHROME_PATHS = [
    # macOS
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    # Linux
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/snap/bin/chromium",
]


def _find_chrome() -> str | None:
    configured = config.setting("chrome_path")
    if configured:
        return configured if Path(configured).exists() else None
    found = next((p for p in _CHROME_PATHS if Path(p).exists()), None)
    if found:
        return found
    # Last resort: whatever is on $PATH under any of the usual names.
    return next((shutil.which(n) for n in
                 ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")
                 if shutil.which(n)), None)


def export_chronological(src_path: Path | None = None, label: str | None = None,
                         fmt: str = "html") -> Path:
    """Render the chronological CV to HTML (and optionally PDF) in exports/."""
    src_path = src_path or CHRONOLOGICAL_CV
    if not src_path.exists():
        raise FileNotFoundError(f"Chronological CV not found: {src_path}")

    label_part = f"_{label}" if label else ""
    print(f"  Parsing chronological CV: {src_path.name}")
    html_content = render_html(parse_variant(src_path))

    stem = f"{date.today().isoformat()}_cv_chronological{label_part}"
    html_path = _home(src_path, "cv-chronological", "html", stem=stem)
    html_path.write_text(html_content)
    if fmt != "pdf":
        return html_path

    pdf_path = _home(src_path, "cv-chronological", "pdf", stem=stem)
    _chrome_print_pdf(html_path, pdf_path)
    return pdf_path


def _chrome_print_pdf(html_path: Path, pdf_path: Path) -> None:
    """Print an HTML file to PDF via Chrome headless."""
    chrome = _find_chrome()
    if not chrome:
        raise RuntimeError("Chrome not found. Install Google Chrome or export to HTML instead.")
    cmd = [
        chrome, "--headless", "--disable-gpu", "--no-sandbox",
        "--run-all-compositor-stages-before-draw",
        f"--print-to-pdf={pdf_path}", "--no-pdf-header-footer",
        f"file://{html_path.resolve()}",
    ]
    print(f"  Running Chrome headless → {pdf_path.name}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Chrome headless failed:\n{result.stderr}")


def export_functional(src_path: Path | None = None, label: str | None = None,
                      fmt: str = "html") -> Path:
    """Render the functional CV to HTML (and optionally PDF) in exports/."""
    src_path = src_path or FUNCTIONAL_CV
    if not src_path.exists():
        raise FileNotFoundError(f"Functional CV not found: {src_path}")

    label_part = f"_{label}" if label else ""
    print(f"  Parsing functional CV: {src_path.name}")
    html_content = render_functional(parse_functional(src_path))

    stem = f"{date.today().isoformat()}_cv_functional{label_part}"
    html_path = _home(src_path, "cv-functional", "html", stem=stem)
    html_path.write_text(html_content)
    if fmt != "pdf":
        return html_path

    pdf_path = _home(src_path, "cv-functional", "pdf", stem=stem)
    _chrome_print_pdf(html_path, pdf_path)
    return pdf_path


# ── DOCX export (ATS-friendly) ──────────────────────────────────────────────

def export_docx_functional(src_path: Path | None = None, label: str | None = None) -> Path:
    """Render the functional CV to an ATS-friendly .docx."""
    try:
        import cv_docx
    except ImportError as e:
        raise RuntimeError(_DOCX_HINT) from e

    src_path = src_path or FUNCTIONAL_CV
    if not src_path.exists():
        raise FileNotFoundError(f"Functional CV not found: {src_path}")

    label_part = f"_{label}" if label else ""
    print(f"  Parsing functional CV: {src_path.name}")
    out = _home(src_path, "cv-functional", "docx",
                stem=f"{date.today().isoformat()}_cv_functional{label_part}")
    return cv_docx.build_functional(parse_functional(src_path), out)


def export_docx_chronological(src_path: Path | None = None, label: str | None = None) -> Path:
    """Render the chronological CV to an ATS-friendly .docx."""
    try:
        import cv_docx
    except ImportError as e:
        raise RuntimeError(_DOCX_HINT) from e

    src_path = src_path or CHRONOLOGICAL_CV
    if not src_path.exists():
        raise FileNotFoundError(f"Chronological CV not found: {src_path}")

    label_part = f"_{label}" if label else ""
    print(f"  Parsing chronological CV: {src_path.name}")
    out = _home(src_path, "cv-chronological", "docx",
                stem=f"{date.today().isoformat()}_cv_chronological{label_part}")
    return cv_docx.build_chronological(parse_variant(src_path), out)


# ── Cover letter export ──────────────────────────────────────────────────────

_COVER_LETTER_CSS = """
  body {
    font-family: Georgia, 'Times New Roman', serif;
    font-size: 12pt;
    line-height: 1.7;
    color: #1a1a2e;
    max-width: 680px;
    margin: 60px auto;
    padding: 0 20px;
  }
  hr { border: none; border-top: 1px solid #ccc; margin: 1.4em 0; }
  p  { margin: 0 0 1em 0; text-align: justify; }
  p.letterhead {
    text-align: left;
    font-size: 10.5pt;
    line-height: 1.45;
    color: #555;
    margin: 0 0 0.4em 0;
  }
"""

_COVER_LETTER_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>{css}</style>
</head>
<body>
{body}
</body>
</html>
"""


def _parse_cover_letter(md_text: str) -> list[tuple]:
    """Parse cover-letter markdown into blocks.

    Returns a list of:
      ('title', text)                              the `# ...` line — a file label, not printed
      ('head', [(inline_html, hard_break), ...])    a letterhead paragraph (before the first ---)
      ('hr',)
      ('p', [(inline_html, hard_break), ...])       a body paragraph (after the first ---)

    Everything before the first `---` is the letterhead zone (name, address, email, date);
    everything after is the letter body. A source line ending in two+ spaces is a hard line
    break within its paragraph.
    """
    blocks: list[tuple] = []
    para: list[tuple[str, bool]] = []
    seen_hr = False
    # The letterhead zone only exists in letters that use `---` to separate it from the
    # body. Older letters with no rule are all body.
    has_hr = any(ln.strip() == "---" for ln in md_text.splitlines())

    def flush():
        if para:
            kind = 'head' if (has_hr and not seen_hr) else 'p'
            blocks.append((kind, para.copy()))
            para.clear()

    for raw in md_text.splitlines():
        line = raw.rstrip('\n')
        if line.startswith("# "):
            flush()
            blocks.append(('title', line[2:].strip()))
        elif line.strip() == "---":
            flush()
            blocks.append(('hr',))
            seen_hr = True
        elif line.strip() == "":
            flush()
        else:
            hard = line.endswith("  ") or line.endswith("\t")
            para.append((_inline(line.strip()), hard))
    flush()
    return blocks


def _join_cover_frags(frags: list[tuple[str, bool]]) -> str:
    buf = []
    for i, (frag, hard) in enumerate(frags):
        buf.append(frag)
        if i < len(frags) - 1:
            buf.append("<br>\n" if hard else " ")
    return "".join(buf)


def _md_to_cover_letter_html(md_text: str) -> str:
    """Convert cover letter markdown to a styled HTML string."""
    parts: list[str] = []
    title = "Cover letter"
    for block in _parse_cover_letter(md_text):
        if block[0] == 'title':
            title = block[1]
        elif block[0] == 'hr':
            parts.append("<hr>")
        elif block[0] == 'head':
            parts.append(f'<p class="letterhead">{_join_cover_frags(block[1])}</p>')
        else:
            parts.append(f"<p>{_join_cover_frags(block[1])}</p>")
    return _COVER_LETTER_TEMPLATE.format(
        css=_COVER_LETTER_CSS, title=_e(title), body="\n".join(parts))


def export_cover_letter(md_path: Path, label: str | None = None,
                        fmt: str = "docx") -> Path | None:
    """Render a cover letter to .docx, plus HTML or PDF when `fmt` asks for one.

    `.docx` is the version that gets sent, so it is always written. The other two are
    opt-in, and for the same reason: the HTML used to be written every time because the
    PDF path needs something for Chrome to print. That was invisible while renders went
    to `exports/`; once they started landing in the application folder (2026-09-24) every
    cover letter left an `.html` nobody had asked for sitting next to its `.docx`. The
    intermediate now goes to a temp file that nothing keeps, and `fmt="html"` is what
    puts one in the folder for real.
    """
    md_text = md_path.read_text()
    label_part = f"_{label}" if label else ""
    stem = f"{date.today().isoformat()}_cover-letter{label_part}"

    docx_path = None
    try:
        import cv_docx
        docx_path = _home(md_path, "cover-letter", "docx", stem=stem)
        cv_docx.build_cover_letter(_parse_cover_letter(md_text), docx_path)
        print(f"  DOCX: {docx_path.name}")
    except ImportError:
        print(f"  DOCX: skipped — {_DOCX_HINT}")

    html_path = None
    if fmt == "html":
        html_path = _home(md_path, "cover-letter", "html", stem=stem)
        html_path.write_text(_md_to_cover_letter_html(md_text))
        print(f"  HTML: {html_path.name}")

    pdf_path = None
    if fmt == "pdf":
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / f"{stem}.html"
            source.write_text(_md_to_cover_letter_html(md_text))
            try:
                pdf_path = _home(md_path, "cover-letter", "pdf", stem=stem)
                _chrome_print_pdf(source, pdf_path)
                print(f"  PDF:  {pdf_path.name}")
            except RuntimeError as e:
                pdf_path = None
                print(f"  PDF:  skipped — {e}")

    return pdf_path or docx_path or html_path


# ── CLI ──────────────────────────────────────────────────────────────────────

def _said(path: Path) -> str:
    """A rendered file's path for the terminal — relative to the data root when it is
    inside it, which since 2026-09-24 is where it usually is. The destination now varies
    with the source, so saying only the directory would no longer tell you much."""
    try:
        return str(Path(path).resolve().relative_to(DATA_ROOT.resolve()))
    except ValueError:
        return str(path)


def main():
    parser = argparse.ArgumentParser(description="Render a CV or cover letter to HTML, PDF, or DOCX.")
    parser.add_argument("--functional", action="store_true",
                        help=f"Render the functional CV ({FUNCTIONAL_CV.name}); --file overrides the source")
    parser.add_argument("--chronological", action="store_true",
                        help=f"Render the chronological CV ({CHRONOLOGICAL_CV.name}); --file overrides the source")
    parser.add_argument("--file", "-i", type=Path, help="Specific CV .md file (default: the base CV)")
    # No default: the branches below want different ones. A CV with no --format renders
    # HTML as it always has; a cover letter renders only the .docx that gets sent, so
    # `--format html` has to mean "I actually want the HTML" rather than "I said nothing".
    parser.add_argument("--format", "-f", choices=["html", "pdf"], default=None,
                        help="Also render this format (CV default: html; cover letter: .docx only)")
    parser.add_argument("--label", "-l", help="Extra label appended to output filename (e.g. 001-grafana-labs)")
    parser.add_argument("--cover-letter", action="store_true", help="Render a cover letter markdown file (requires --file)")
    parser.add_argument("--docx", action="store_true",
                        help="Render an ATS-friendly .docx instead of HTML/PDF (with --functional or --chronological)")
    args = parser.parse_args()

    if args.cover_letter:
        if not args.file:
            print("Error: --cover-letter requires --file")
            sys.exit(1)
        print(f"Rendering cover letter: {Path(args.file).name}")
        out = export_cover_letter(Path(args.file), label=args.label, fmt=args.format or "docx")
        print(f"Saved to: {_said(out)}")
        return

    if args.docx:
        if args.functional:
            print("Rendering functional CV (docx)")
            out = export_docx_functional(args.file, label=args.label)
        elif args.chronological:
            print("Rendering chronological CV (docx)")
            out = export_docx_chronological(args.file, label=args.label)
        else:
            print("Error: --docx requires --functional or --chronological")
            sys.exit(1)
        print(f"DOCX saved to: {_said(out)}")
        return

    if args.functional:
        print(f"Rendering functional CV ({args.format or 'html'})")
        out = export_functional(args.file, label=args.label, fmt=args.format or "html")
        print(f"{(args.format or 'html').upper()} saved to: {_said(out)}")
        return

    if args.chronological:
        print(f"Rendering chronological CV ({args.format or 'html'})")
        out = export_chronological(args.file, label=args.label, fmt=args.format or "html")
        print(f"{(args.format or 'html').upper()} saved to: {_said(out)}")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
