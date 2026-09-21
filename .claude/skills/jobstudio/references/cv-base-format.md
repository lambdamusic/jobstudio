# Base CV markdown format — the exact contract

`<DATA>/jobs/cv/base/cv_functional.md` and `cv_chronological.md` are **not** rendered by a
general markdown engine. `src/render.py` parses them with hand-written regexes
(`parse_functional()` / `parse_variant()` and their section helpers) into a data
dict, which then fills the HTML/PDF/DOCX templates. Follow this file precisely when
writing or rewriting either base CV — a bootstrap interview, an import from an
existing CV, or a per-application tailoring edit.

**This matters because the failure mode is silent.** Get a pattern wrong — a hyphen
instead of an em dash, bold instead of italic, a missing blank line — and the parser
usually doesn't error, it just drops that field or misfiles it, so a section quietly
comes out blank or garbled in the rendered CV. Always spot-check the rendered
output (`/jobstudio render-html-pdf`) after writing or rewriting a base CV, not
just the markdown source.

## Shared: header and contact block

```markdown
# {Full Name}

{Functional only — one plain prose subtitle line, e.g.:}
Technology & Product Leadership · Data Platforms · Applied AI · Knowledge Graphs

- **Location:** {city, region, country}  
- **Email:** {email}  
- **LinkedIn:** [{display text}]({url})  
- **Website:** [{display text}]({url})  
- **Google Scholar:** [{display text}]({url})  
- **GitHub:** [{display text}]({url})  


---
```

- `_parse_contact` finds every `**Label:** value` line anywhere before the first
  `## ` heading — order doesn't matter to the parser, but keep it consistent with
  the existing files. A value can be plain text or a `[text](url)` link.
- **The functional subtitle is positional, not labelled.** `parse_functional` takes
  the *first non-blank line after `# Name`* that doesn't start with `-`, `**`, or
  `#` as the page subtitle. It must sit directly under the name, before the contact
  bullets. Omit it and the subtitle falls back to the most recent job title — fine,
  but less deliberate than writing one.
- The chronological file has no subtitle line at all — go straight from the name to
  the contact bullets.
- Each contact line ends with two trailing spaces (the hard line break) — keep this
  when writing new lines.

## Shared: `## Summary`

Plain prose paragraphs, separated by a blank line. Any paragraph accidentally
starting with `---` is skipped defensively, but don't rely on that. No fixed count —
the functional file uses 2 paragraphs, the chronological one uses 3 — but the two
files' summaries read differently in tone (functional leads with the
competency/leadership framing; chronological leads with delivery/achievement
framing), not just length. Draft both, don't copy one into the other.

## Functional only: `## Core Competencies`

```markdown
### {Cluster title}

{optional prose line(s) — only counted if no bullets have started yet in this cluster}
- **{Employer (Role)}:** {achievement — bold/italic/links all fine inline}
- **{Employer (Role)}:** {achievement}
*Core technologies: {comma list}.*
```

- Each cluster is its own `### ` heading.
- A non-bullet, non-tech line **before any bullets** becomes a `statement` (short
  descriptive prose for the cluster) — the current two files don't use this, but
  it's supported.
- The optional tech line must be **exactly** `*Core technologies: ...*` — single
  asterisks (italic), not bold, lowercase `technologies`, no leading `- `. This is
  a different convention from the chronological file's tech line below — do not
  swap them.
- **Bullet order within a cluster is not free to reorder by relevance** — see
  `[[feedback-cv-tailoring-bullet-order]]` / `subcommands/cv.md`: bullets stay
  strict newest-role-first. This applies when building the cluster too, not just
  when tailoring it later.

## Functional only: `## Career History`

```markdown
### [{Employer}]({url})
*{Years}*
{optional one-line italic prose summarising the tenure — only read if no role bullets have appeared yet}

- {Role title} — *{Role dates}*
- {Role title} — *{Role dates}*
```

- Org header line, then (in this order) a dates line, an optional summary line,
  then role bullets — the parser stops looking for dates/summary once it sees the
  first `- ` bullet, so **that order is not optional**.
- The dates line must match `*{digits, spaces, en/em dashes only}*` — e.g.
  `*2019 – 2026*` — optionally followed by `· {context}` for a department/context
  aside, e.g. `*2008 – 2012* · Department of Digital Humanities`.
- Each role bullet's date suffix needs an **em dash** (`—`) or **en dash** (`–`)
  before the italic date range: `{Role} — *{dates}*`. A hyphen (`-`) won't match.
  A bullet with no dash+italic-date suffix at all still works — it just renders
  with no per-role date (used for a single-role employer, or a bundled "early
  roles" entry where the dash instead separates a role from a company name, e.g.
  `- Data Modeller / Software Developer — Northgate Consulting Ltd`).
- This section carries **no achievement bullets, just titles and dates** — the
  detail lives in Core Competencies instead. Don't duplicate prose here.

## Chronological only: `## Experience`

```markdown
### {Role} — [{Employer}]({url})
**{Date range}** | {Location}

- {Achievement bullet}
- {Achievement bullet}
- **Core technologies:** {comma list}
```

- Header line splits on ` — ` (em dash, spaces both sides) into role / company.
- The meta line must be **bold** dates, e.g. `**February 2021 – December 2024**`,
  optionally followed by `| {location}`.
- Bullets are achievement prose, most-relevant-first is fine here (unlike the
  functional Core Competencies rule above — this file has no cross-application
  reuse to keep consistent, it's just the full chronological record).
- The tech line here is the *other* convention: **bold**, not italic —
  `- **Core technologies:** ...` (or `**core technologies**`, first-letter case is
  flexible) — as its own bullet, not a standalone line. Do not use the functional
  file's italic style here.
- An entry whose role name contains the phrase "early career" (case-insensitive,
  anywhere in the role text before the dash) is treated specially — grouped and
  rendered as a condensed early-career block rather than a full role entry. Use
  this for bundling several short/minor early jobs into one entry, same shape
  otherwise (meta line + bullets).

## Shared: `## Education`

```markdown
**{Degree}**  
{Institution} | {Years}  
Focus: {one line}
```

- A `**bold**` line starts a new entry; the next line is split on `|` into
  institution/years if a `|` is present, otherwise treated as institution alone; a
  line starting `Focus:` (case-insensitive) is optional.
- A miscellaneous one-line entry is also supported — a lone bold line with no
  institution/years/focus lines after it (e.g. `**The University of Edinburgh**
  *(exchange / additional study)*`) still renders, just without those extra
  fields.

## Shared: `## Skills`

```markdown
- **{Label}:** {comma-separated text}  
- **Languages:** {Name} ({Level}), {Name} ({Level}), ...
```

- The parser scans the whole section for any `**Label:** value` occurrence — the
  leading `- ` is just convention, not required by the regex, but keep it for
  readability.
- The `Languages` label (case-insensitive) is special-cased: each `Name (Level)`
  pair inside its value is split out individually for the rendered language list.
  Every other label's value is shown as-is.

## Shared: `## Selected Publications` (or any heading containing "publication")

```markdown
- *{Title, optionally with a [link](url)}*
```

- Any line matching `- {content}` under this heading is one publication. Wrapping
  the title in `*italics*` is optional — stripped automatically if present.

---

## Practical checklist when writing either file

1. Header + contact bullets, functional subtitle if writing the functional file.
2. `## Summary` — draft each file's summary separately, matching its own framing.
3. Functional: `## Core Competencies` (clusters, bullets newest-role-first within
   each) then `## Career History` (titles/dates only). Chronological: `##
   Experience` (full bullets per role, most-relevant-first is fine).
4. `## Education`, `## Skills`, `## Selected Publications` — shared shape, same
   content in both files (these don't need two different framings).
5. Render both (`/jobstudio render-html-pdf`) and eyeball the output before
   considering the rewrite done — this is the only real check, since a shape
   mismatch fails silently.
