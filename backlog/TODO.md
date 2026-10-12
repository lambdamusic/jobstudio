# TODO

<!-- Open backlog items. Completed ones move to `DONE.md` keeping their section and
     their full text; longer design documents live in `plans/`, named by the ID that
     owns them (`plans/042-dashboard-charts.md` backs `#42`). Not every item has one —
     only those that needed a longer discussion.

     Numbering: `#N` is a permanent ID assigned once when an item is added — never
     renumbered, never reused (checked-off or removed items keep/retire their number).
     Position in the file reflects section grouping, not creation order.
     Next available: #91 -->

## Architecture
- [ ] `#75` **Simplify the config settings — or at least say plainly what each one is for** — raised 2026-10-02 by Michele, after setting the toolkit up on a second machine: *"Shall we consider simplifying the config settings? Unclear to me now what is needed."* Design in [`plans/075-config-layers.md`](plans/075-config-layers.md).

  Three layers resolve the data root (`src/config.py:19-21`): `$JOBSTUDIO_DATA`, then the checkout's `.jobstudio-data`, then `~/.jobstudio.ini`. The layering itself is sound — the second machine has two data roots on it, and layer 2 beating layer 3 is exactly what stops a session acting on the wrong one. The problem is that nothing explains which of the three a given person actually needs.

  **The finding that reframes it: the `.ini` does two unrelated jobs and only one is duplicated.** `data_root` is covered by the other two layers whenever a repo is in the picture; `chrome_path`, `editor_url_scheme` and `open_command` are read through `config.setting()` (`config.py:96`) by four call sites and have no other layer at all. "Do I need the `.ini`?" therefore has two different answers, and the file gives no hint it holds two kinds of thing.

  **Second finding: the `.ini`'s data-root branch is close to unreachable as the skill is installed.** `SKILL.md:88` says to read it directly "only if no repo is reachable" — but the skill is a *project* skill under `.claude/skills/`, with no user-level copy, so a session outside the repo has no `/jobstudio` at all and never reaches that step. Live for a bare `tools/py src/...` run from elsewhere; not for the skill whose instructions describe it. A docs-versus-reality gap rather than a bug.

  - [ ] Decide between the four options in the plan — they range from "change no code, fix what the files say" to "drop `data_root` from the `.ini`". The complaint was comprehension, so the cheapest option may be the right one.
  - [ ] Whichever is chosen, `SKILL.md`, `docs/getting-started.md` and `subcommands/init.md` all describe the `.ini` and would need to agree.
  - [ ] Do **not** fold this into skill installation (`#57`/`#2`) — a user-level install would make layer 3 genuinely reachable, but that is a bigger question and this item should not wait on it.

  **Update 2026-10-06:** `#70` removed PDF export, and `chrome_path` with it — the `.ini`'s non-data-root settings are now `editor_url_scheme` and `open_command`. Then `#81` removed `editor_url_scheme`, leaving `open_command` as the only one.

- [ ] `#57` **M2 — ship `jobstudio` as a pip package** — spun out of `#2` on 2026-10-01, where it was milestone M2; design in [`plans/002-share-as-toolkit.md`](plans/002-share-as-toolkit.md) §2a and §6. Move `src/` under a package namespace, replace the `tools/py src/foo.py` calls with console-script entry points (which retires `tools/py` and most of M1.4), make `init` a real CLI command, add `MANIFEST`/package data for `example-data/` and the skill, publish to PyPI. The bulk of the work is a mechanical pass over the ~104 `tools/py src/...` references in `.claude/skills/jobstudio/subcommands/` — `tools/py src/jobsdb.py status` becomes `jobstudio db status`.

  **It is the half of `#2`'s goal that M1 did not deliver.** M1 made the toolkit public and installable by anyone willing to clone a repo and build a virtualenv; M2 is what makes it installable by anyone. Worth weighing against how much demand there actually is — a template repo that works is a long way past nothing, and `#58` is a depth play on the same codebase that benefits the one confirmed user.

- [ ] `#58` **M3 — drive Claude Code from the Django app** — spun out of `#2` on 2026-10-01, where it was milestone M3 and the recommended stretch goal; design in [`plans/058-drive-claude-code-from-django.md`](plans/058-drive-claude-code-from-django.md) §8. Buttons in the web app that run `/jobstudio` subcommands with Claude Code as the engine: "Tailor CV" on an application page, "Scan now" on the companies list. Reuses the skill unchanged and needs no architectural change — it inverts the Cowork route's limitation (§7), where the web app was what got lost.

  **Start with the `claude -p` subprocess, not the Agent SDK** (§8.1): cwd at the repo root picks up `.claude/skills/jobstudio/` and `CLAUDE.md` exactly as an interactive session does, so the existing skill runs completely unchanged, with `#57` not a prerequisite. ~a day's work, and the cheapest possible test of whether this is actually nice to use. Move to `claude-agent-sdk` only if structured streaming or finer permission control turns out to matter — the SDK loads no filesystem skills by default, which is most of the extra cost.

  **Two things to be clear-eyed about.** (a) Billing is a *different pool*, not a bigger one (§8.2): no API key is needed, but the subscription's monthly Agent SDK credit is a dollar allowance separate from session limits, it does not roll over, and when it is exhausted requests either bill at API rates or stop. Watch it for a month before leaning on it. (b) It is a depth play, not a reach play (§8.4) — it only works where Claude Code is installed and authenticated, so `#2`'s "share it with someone else" is served by M1 and `#57`, not by this.

## Portal scanning
- [ ] `#7` **Portal scanning — LinkedIn** — investigate a legitimate way to include LinkedIn postings (direct automation is ToS-hostile/technically fragile — login wall, bot detection — so this likely means a different approach: manual-forward workflow, or checking if a compliant partner API exists, not scraping). Re-raised 2026-09-23; the position is unchanged — LinkedIn's Job Posting APIs are partner-only (ATS vendors posting *to* LinkedIn, not reading *from* it), so there is no route for an individual's job search. Realistic outcome here is the manual-forward workflow: paste a LinkedIn URL and have `jobstudio` log it, rather than a fetcher.

- [ ] `#22` Create custom parsers for selected companies in the long tail (bespoke career pages with no public jobs API — see `## Not scanned` in any portal scan report for the current list)

## CV rendering & import
## Onboarding and docs
- [ ] `#68` **Quick Start should be about using the toolkit, not installing it** — raised 2026-10-01 by Michele. The README's Quick Start is currently setup: virtualenv, `init`, start the web app. That answers "how do I get this running" and never "what do I do with it", which is the question somebody reading the README actually has.

  **Split the two.** Quick Start becomes a tour of the things you *do* — log a company, log an application, scan the job boards, tailor a CV, draft a cover letter, prep an interview — each one a `/jobstudio` command with a line on what comes back. Installation moves out of it.

  **`docs/getting-started.md` should probably become `docs/installation.md`** at the same time, since that is what it is. Only three references to update (`README.md`, `docs/README.md`), but `docs/README.md` also calls it *"the [README](../README.md#quick-start)'s quick start is the short version"* — which stops being true once Quick Start is about use and that file is about setup, so the sentence needs rewriting rather than repointing.

  Pairs with `#43` and `#50`, which were the same complaint one layer down: the docs answered "how do I drive it" before "why would I want this".

## Web app / admin site
- [ ] `#76` **A short list of inspiring reads, shown somewhere in the app** — raised 2026-10-04 by Michele. Collect links to pieces that are worth (re)reading while job hunting — the first one is Wait But Why's [*How to Pick a Career (That Actually Fits You)*](https://waitbutwhy.com/2018/04/picking-career.html) — and give them a home in the web app.

  - [ ] **Decide where the list lives.** A curated list shipped with the repo is the same for everyone; a personal one belongs in the data root next to the user's notes. Probably both — a few shipped defaults the user can add to — but that is the question to settle first, since it decides whether this is a template change or a new file the app reads.
  - [ ] **Decide where it shows.** Candidates: a section on the help page (`src/web/apps/tracker/templates/tracker/help.html`), a small panel on the dashboard (`tracker/home.html`), or a page of its own in the sidebar (`src/web/templates-global/base.html`). The dashboard is where it would actually get seen; the help page is where it fits without competing with the tracker.
  - [ ] Links open in a new tab, as everywhere else since `#17`.


## Interview prep
## File naming
- [ ] `#27` **Re-order the application-folder naming convention to `{type}-{date-created}-{username}-{job-slug}`** — e.g. `cover-letter-2026-09-18-michele-pasin-046-bbc-studios.md`, replacing today's `{job-slug}-{username}-{type}-{date}` (`046-bbc-studios-michele-pasin-cover-letter-2026-09-18.md`, the 2026-09-08 convention in `src/appfolder.py`'s `app_filename()`). Putting the type first makes a folder listing sort by kind rather than by a company name every file in the folder already repeats. **Also covers interview-round files** (`<id>-<person>-interview-<stage>-<date>.md`, added 2026-09-24) — whose date is the interview's, not the file's, so the reorder must not assume a creation date. **Also apply it to `notes.md` and `job.md`**, which are currently bare names with no date or owner at all — so `notes-2026-09-18-michele-pasin-046-bbc-studios.md`, `job-2026-09-18-michele-pasin-046-bbc-studios.md`.

  Touches more than `app_filename()`: the recognisers next to it (`is_cv_filename`, `is_cover_letter_filename`, `is_tailored_cv`) and the web parsers in `src/web/apps/tracker/parsers.py` must keep matching **both** old and new names — real application folders already on disk are not renamed — and `notes.md`/`job.md` are currently looked up by exact filename in the parsers, the skill (`subcommands/application.md`), `appfolder.py`'s scaffolding and `src/web/README.md`'s file-map table. Decide up front whether existing folders get a migration pass or are simply left alone; check `src/web/apps/tracker/tests.py` fixtures either way.


## Company tracking
- [ ] `#21` **Idea:** "find similar companies" — pick a company already in the tracker and surface other companies (same space/positioning/stage) worth shortlisting, as a discovery mechanism. Manually prototyped 2026-09-14: given a tracked company in robotics/physical-AI data with no UK presence, asked for similar UK-based alternatives and found one with the same "data layer for physical AI" positioning and a London HQ, via a plain web search — worth automating as a repeatable step (`jobstudio` subcommand or an option on `company`) rather than redoing this research by hand each time
