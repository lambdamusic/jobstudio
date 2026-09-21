# How cover letters get drafted

Part of the **[docs/](README.md)** guide collection. For *when* to draft one, see
[workflow.md](workflow.md) §3 — this is a deep dive into how `/jobstudio cover-letter`
picks a structure and what it reads to write the draft.

```
/jobstudio cover-letter [company or #N] [--standard2] [extra context]
```

Runs automatically as part of `/jobstudio application` when logging a new
application (revised 2026-09-17) — this command is for re-drafting a one-off later.

## What it reads

| Source | What it's used for |
|---|---|
| The tracker database | Role title, area, notes, job URL — via `src/jobsdb.py list` |
| `job.md` in the application folder | Mirror its wording for the marketing paragraph |
| The tailored functional CV in the folder if one exists, else `jobs/cv/base/cv_functional.md` | Concrete achievements to draw on (functional is the default format — see [cv-pipeline.md](cv-pipeline.md)) |
| `jobs/companies/<slug>.md` | Technology / Where they are now / Fit with my mission — feeds the research/hook paragraph (see [companies.md](companies.md)) |
| `jobs/profile/stocktake.md` | §6 Positioning by audience, §2 achievements/USPs, §7 narratives to have ready |
| `jobs/profile/criteria.yaml` | `bonus_signals` (Asia/China/Japan, e-learning, music tech, foundational AI) — mentioned if the company hits one |
| `.claude/skills/jobstudio/references/cover-letter-structures.md` | Both standard variants in full, letterhead skeleton, and close guidance — read before drafting every time |

## Picking the variant

One structure family — **standard** — with two variants (revised 2026-09-17; the
earlier mirror and advanced structures were retired, see
`backlog/done/drop-direct-anthropic-api-plan.md` §1.2):

| Variant | Chosen when |
|---|---|
| **Standard 1** | Default — used unless the user asks for the alternative |
| **Standard 2** | Only on explicit request (`--standard2`) — a shorter, more compressed alternative; same sourcing and close guidance, different paragraph shape |

Word-count targets: Standard 1 ~280–320 words, Standard 2 ~220–260. The reference
file's numbered structure beats are scaffolding only — they're never printed as
headings in the actual letter.

## Drafting rules worth knowing

- Every letter opens with a direct one-line job identification (role + req number, if
  there is one) — Standard 1 as its own short paragraph with a blank line before the
  research/hook paragraph, Standard 2 folded into the same opening paragraph as the
  self-intro. This is one of the few "padded opener" patterns that's actually
  required, not banned.
- Default close is a plain sign-off, no call-to-action — the older "I will call
  you on Tuesday…" pattern is deliberately retired.
- Voice: casual but precise, first-person, British spelling, contractions fine, no
  buzzwords that don't earn their place ("ontology" yes, "synergy" no). Slightly more
  formal for large traditional orgs (legacy publishers, financial-data firms,
  government departments);
  conversational by default elsewhere.
- Never mentions salary, availability, or "enclosed CV".

Full voice/style rules and both variants verbatim live in
`references/cover-letter-structures.md` — read from there, not copied here, so there's
one place to keep them current.

## Save and export

The draft is shown for review before anything is written — naming which variant was
used and why. On confirmation:

```bash
python src/appfolder.py ensure <row-num>    # folder + empty stub already exist from logging
```

Saved as `{folder}/{folder-name}-<person-slug>-cover-letter-YYYY-MM-DD.md` — the same
application-folder naming convention as everything else in that folder (see
[applications-and-gap-analysis.md](applications-and-gap-analysis.md)), filling in the
empty stub that `/jobstudio application` already created. Then rendered to `.docx`:

```bash
python src/render.py --cover-letter --docx --file "<saved path>"
```

**No `import_jobs` step needed afterward** — cover letters have no database model at
all. They're scanned from the application folder by naming convention
(`is_cover_letter_filename()`, `Application.cover_letter_files` in `models.py`) at
request time, so the new letter appears on the application page immediately; an empty
stub is ignored until it actually has content.
