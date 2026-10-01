# Changelog

Dated entries, newest first.

## 2026-10-01

- **The example data exercises the app now, instead of just populating it** (`#64`). It
  held three applications and three status changes — one each, all `"" → current`, all
  stamped at the same second — so nothing had ever moved and every chart that measures
  movement had nothing to draw. The status-flow Sankey had no status-to-status ribbon at
  all, the "from applied onward" view was one node to one node, the stock chart refused to
  render, and the ageing list had a single row. A first-time user met that and reasonably
  read it as broken rather than as empty.

  The fixture now walks each application through a real transition history — driven
  through the model so the `from → to` pairing comes from the actual signal, with only
  `changed_at` backdated — across ten applications and eleven companies: every status
  reached, real outcomes, one application that moves *backwards* so the cycle rule is
  exercised, one applied-and-forgotten past the staleness threshold, and a second
  application at one company so the per-company histogram has more than one bar. Two
  application folders gained a job description and notes, one with two interview rounds so
  the round index has something to index, and the five new companies carry ATS tokens
  verified live against the real API.

  Nine tests failed on the change, and every one was really asserting "the example has no
  transitions" rather than the behaviour in its own docstring — one of them named
  `test_at_example_volume_the_history_charts_say_why_they_cannot_draw`. A test that borrows
  the shipped example's poverty to supply its precondition is a test that forbids improving
  the example; they now state the precondition themselves.

- **Restoring a backup no longer invents status history** (`#65`). The post-save signal had
  no `raw` guard, and `loaddata` saves an application before its status-change rows — so
  the log looked empty, a `(logged) → <current>` row was appended stamped at load time, and
  the real rows loaded underneath it. Quiet and consequential: the invented row is the most
  recent change, so every restored application read as having moved today and the staleness
  flagging silently stopped working. Found because one chart called an application 0 days
  old when its last real change was 16 days earlier.

- **The skill was publishing the maintainer's psychometric results, and every check had
  passed it.** `subcommands/stocktake.md` carried a completed career-anchors
  questionnaire — eight anchors, his averages, his three "most true" picks quoted — plus
  his values exercise ranked into groups; `docs/career-stocktake-profile.md` carried a
  second copy of the anchors. Public since the repo was cut, and reported CLEAN by every
  run of `make-public-tree --check`, because none of its checks had a notion of that
  category: not a company name, not an email, not a home path. Found by the first install
  **by a second person**, whose session flagged it twice and declined to touch the file.

  Both files now describe the method and point at the data root for the answers, and the
  prose no longer refers to its user in the third person — the other half of the problem,
  since a second user running `stocktake` was being handed someone else's completed
  answers as their starting point. `make-public-tree` gained a check that refuses any
  shipping `.md` using *his/him/hers/she's*; `backlog/`, `log/` and this changelog are
  exempt, being dated records where naming the maintainer is correct. It was proved by
  planting a violation, and on its first real run it found the `docs/` copy the second
  person's session never reached.

- **No fetcher loses a whole company to one malformed row any more** (`#63`). All ten
  read a title and a link out of someone else's JSON, and all ten did it with a hard
  subscript, so one bad row raised `KeyError`, surfaced as "unexpected response shape"
  and marked the company NOT SCANNED. A real Workday board did exactly that: 125
  postings, one carrying only `bulletFields`, 124 usable ones discarded. The message was
  its own second problem, since 124 of 125 rows parsed, so it sent you to inspect a board
  that worked.

  Every branch now funnels rows through one `_Postings` sink that skips what it cannot use
  and **counts it** — per `#44`, because a row dropped with no number beside it is
  indistinguishable from a row that was never there. It also closes a quieter hazard the
  Workday fix had not: Ashby and Workable reached their URL through `.get()`, so a posting
  with no link raised nothing at all and instead crashed later, in the caller's
  `_normalize(j["url"])`. A test asserts no fetcher reads a posting field directly, and it
  was proved by planting one and watching it fail. Verified live against Greenhouse,
  Ashby, Workable, Workday and SmartRecruiters: 545 real postings, no malformed row
  surviving.

- **`cv --rebuild` reads both base CVs before it asks anything** (`#61`). The interview
  collected one set of facts and derived both files from it, on the documented assumption
  that the two differ only in framing. They differ in content: the functional file's Core
  Competencies accumulates the load-bearing detail — figures, named initiatives, named
  events, scale numbers — and the chronological file's role bullets are the older,
  plainer version of the same claims. Since step 2's pre-fill reads naturally as the
  chronological career history, a literal run dropped every functional-only fact,
  produced two well-formed files, and reported `CHECK OK`. The pre-fill now reads both and
  collects the union, flagging anything that appears in only one; `--rebuild` says plainly
  that it is a blank-page tool before being run against a good existing pair; and
  `cv-base-format.md` states which file is the source of record instead of implying the
  two are views of one fact set. No check catches this class of loss — both versions are
  valid markdown — so the contract now says that too.

- **An application can hold one CV per base, and the CV tab indexes them** (`#60`).
  Asking for the other base used to leave the folder in the state the
  one-CV-per-application rule exists to prevent — two CVs, no way to tell from a filename
  which is live. Replacement was built first and backed out: two different bases are two
  genuinely different documents for the same role, and the earlier one may be what was
  already sent, so deleting it destroys a record to satisfy a rule aimed at a different
  problem (the same base, twice, differing only by date). The answer is the UI showing
  what is there instead of the toolkit deciding by deleting a file — so the CV tab now
  renders an index above the CVs when there is more than one, the same pattern the
  Interviews tab uses for rounds, with the base label, the date, an `unedited copy`
  marker and an anchor into each full text.

- **`jobsdb.py set-cv-base <num> {functional,chronological}`**, so making a base switch
  permanent has a command behind it. A `--base` override deliberately does not change the
  stored default; `cv_base` was settable at creation and in the Django admin and by
  nothing on the agent-native path, which is where every other tracker write happens —
  the same gap, and the same argument, as `#41`'s missing `update-company`.

- **`render.py --check` counts languages, because nothing was counting them.** The
  Languages line is the one thing `_parse_skills()` lifts *out* of the skills list into
  its own structure, so the skill-group count never spoke for it. Written
  `Italian - native` instead of `Italian (native)` it parsed to zero, every language
  vanished from the rendered CV, `--check` printed `CHECK OK`, and its summary line was
  byte-identical to a correct parse. `--check` now reports `languages: N` and fails with
  a warning naming the required format; a CV that lists no languages at all is still
  finished rather than thin, same stance as the optional header links. Found while
  verifying the CV flows for backlog `#23`, and it is `#44`'s failure mode in the one
  section nothing had a count for.

- **Both agent-native CV flows are now verified against real inputs** (`#23`, closed).
  Chronological tailoring and the `cv --rebuild` interview were the two that had never
  been run live; each found something. The rebuild run is written up as `#61`, which is
  the more serious of the two: the interview collects one set of facts and derives both
  base CVs from it, on the documented assumption that the files differ only in framing —
  and they do not, they differ in content, with the functional file's Core Competencies
  carrying a good deal the chronological file has never had. A literal run drops it,
  parses clean, and reports `CHECK OK`. No check can catch that; the pre-fill has to read
  both files.


- **Logging an application stops tailoring anything** (`#55`). The CV it puts in the
  folder is a mechanical copy of the base, and the cover letter is a thin generic draft:
  the job-ID line, one honest paragraph on why the role is interesting, one line on fit,
  standard close. Both documents get refined by hand before they are sent, so the
  automatic full drafts added on 2026-09-17 were not saving that work — they were
  producing something to read closely and undo. A thin, predictable starting point is
  worth more than a polished wrong one, and logging a role is fast again.

  The full versions are still there, demoted to a request: `/jobstudio cv #N` tailors the
  CV in place, `/jobstudio cover-letter #N` writes the real letter. Deleting working
  capability to simplify a default is a poor trade when the default is the thing that
  was wrong.

- **The copy's one transform is mechanical, so a regex does it, not an agent.** Core
  Competencies bullets carry the role in brackets — `- **Employer (Head of Data):** …` —
  because the master CV has to say which job a piece of work was done in. On a CV going
  out for one role that bracket is noise, and the employer-only form already occurs in
  the base, so `appfolder.strip_competency_roles()` drops it on the way in. Scoped to
  that one section: in Career History the role title is the entire content of the line.
  The base CVs keep their brackets.

- **The copy is named for the application, tailored or not** —
  `NNN-company-<person-slug>-cv-functional-<date>.md`, not the bare `cv_functional.md` it
  used to be. It is the file that gets edited and sent, so it is named for the job it is
  going to; the `.docx` rendered from it always was. Folders scaffolded before this are
  left alone, and a second run never overwrites a CV that is already there.

  Which means the filename no longer says whether anyone has worked on a CV, so
  `is_tailored_cv()` became **`is_app_cv()`** ("belongs to this application") and the real
  question moved to **`is_untouched_copy()`**, which compares the file to a fresh copy of
  each base. The tailored list on `/cvs/` keeps its meaning, the application page's CV tab
  marks an untouched one "unedited copy", and a CV refined *by hand* now counts as worked
  on where before only an agent pass did — which is how these actually get finished.

- **What deliberately did not change:** the gap analysis. `### Fit check`, `### CV gaps`
  and `### Preparation steps` are not part of tailoring — they feed the fit summary on the
  application page and are the main source for `interview` — so they still run on every
  log. Dropping CV tailoring must not drop the analysis that happens to precede it.

## 2026-09-29

- **The docs are two layers now, and say which is which.** They interleaved
  `/jobstudio ...` commands with `python src/...` invocations, so a reader could not tell
  which one they were meant to type — in a toolkit whose premise is that you drive it by
  talking to it. `docs/README.md` now opens on "What you can do, and how" and "How each
  piece actually works", and the whole scripts layer moved into a new
  **`docs/under-the-hood.md`**, framed as something you never need in order to *use* the
  toolkit. `workflow.md` has no Python entry points left. `tools/run-dev-local-db` stays
  where it is, with a line saying why: it is long-running and has no command equivalent.

- **The README says why you might want this**, instead of only how to drive it. Led by
  "it is yours to change" — the rubric, the cover-letter structures and the CV format
  contract are prose you edit rather than code you fork, each named by path so the claim
  can be checked.

- **Three stale things the rewrite turned up.** Four docs told you to
  `source tools/env.sh` before the opt-in `--api` scan: that file is gitignored, so it has
  never existed on anyone else's machine, leaving `--api` effectively undocumented — they
  now say to put `ANTHROPIC_API_KEY` in the environment. The published-site list still
  advertised "the three master CVs and all 29 generated variants", from before variants
  were retired. And a section heading still read "Finalise by exporting to PDF".

- **The web app now says how to drive it.** `/help/` — "How to use this" — lays out the
  five steps in the order you actually work them and names the command for each, then
  lists every command. The app showed a job search but never explained how to work one;
  that lived in the docs and the skill, neither of which is open while you are looking at
  a page.

  The command names and descriptions are read from `SKILL.md`'s own help table rather
  than retyped, so the page cannot drift from the commands — `render-html-pdf` became
  `render` the same week. The step ordering stays hand-written: the skill knows what each
  subcommand does, not which one you reach for on a Tuesday.

- **`init` explains itself before it starts asking.** On a fresh clone the first thing a
  user met was a question — data root, on-ramp, virtualenv — answered without knowing
  what was being set up or which answers are hard to change later. It now opens with a
  short plan and only then asks. It also says, at the point of asking, that what it
  captures drives every tailored CV, cover letter and scan score that follows, so a thin
  answer here doesn't fail, it quietly weakens everything downstream. The identity
  questions are asked in prose, since they are free text.

- **A CV with no LinkedIn, site, GitHub or Scholar is finished, not thin.** The code was
  never the problem — `_parse_contact` reads any `**Label:** value` line and every
  renderer iterates whatever it finds, so a link-free header already came out clean. The
  assumption lived in the words: the format contract listed all six header lines as if
  they were the set, and the CV interview asked for each by name, which is why an import
  against a CV that had none of them treated it as a gap to raise. Both now say that a
  name and one way to be contacted are the only requirements, that the labels are open
  (`ORCID`, `Phone`, whatever the person has), and that "none" is an answer to take
  first time.

  The absence that does matter is now checked instead: `--check` warns when a header has
  no email **and** no link — a CV that parses perfectly and still cannot be replied to.

- **A CV renders to `.docx` now, without being asked twice.** `render.py` defaulted to
  HTML with `.docx` behind a `--docx` flag, which had the wanted format as the opt-in one
  and left HTML and PDF files in application folders nobody had asked for and nothing
  downstream read. `--format` now takes `{docx,html,pdf}` and defaults to `docx` for CVs
  and cover letters alike; HTML and PDF have to be named. `--docx` still works as a
  deprecated alias. The `render-html-pdf` subcommand is renamed `render` and rewritten
  around the one format that gets sent to employers.

  The HTML and PDF rendering code is untouched and still reachable by flag — switching
  the default off is reversible in a way that deleting the renderers is not.

- **Both shipped example CVs were losing their work history, and nothing noticed.**
  `render.py`'s parsers are hand-written regexes that discard what they cannot match, so
  a CV in the wrong shape parses to an *empty* CV and renders a well-formed document with
  no jobs in it. `example-data`'s functional CV wrote its roles as `**Role** | dates |
  location`, which matches nothing — three employers, zero roles, zero dates. The
  chronological one used `## Career History` where the parser reads `## Experience`, which
  dropped the lot. Both are the file a new user copies and an agent reads to infer house
  style, and on a first install elsewhere that is exactly what happened: most of a CV
  import spent recovering from our own example. Both rewritten to the contract in
  `references/cv-base-format.md`, which was right all along.

- **`render.py --check`** parses a CV and reports what it read — a count per section, a
  named warning for any section it could not read, and a non-zero exit if content was
  lost. It writes no files, which is the point: verifying an imported CV no longer means
  rendering HTML to eyeball. Every CV render now prints the same report, so silent loss
  has to announce itself. `cv --import` calls it, and it is no longer optional there.

- **The CV and area pages re-sync themselves from disk** (`tracker/derived.py`). `/cvs/`
  lists rows, and `init` creates them before on-ramp B has written any base CV — so a
  first install could finish with a correctly imported CV on disk and an empty CV page,
  with no error anywhere. `ensure_fresh()` compares files against rows and re-imports only
  when they differ, so no write site has to remember. A row whose file is gone is now
  pruned rather than shown as "file missing" forever.

- **`smoke-test` reads the CV it renders.** It asserted the `.docx` was over 10,000 bytes,
  which a CV with no jobs in it also is. It now unzips the document and looks for a job
  title.

Found by installing the toolkit on a second machine against an unfamiliar CV — the last
outstanding piece of `#2`. Write-up in `log/2026-09-29-second-machine-findings.md`;
`#46`–`#51` are the rest of what that run turned up.

## 2026-09-28

- **Every application now starts at `saved`.** 24 of 57 were logged straight into
  `closed`, `applied`, `rejected` — wherever they already were — which is an artefact of
  how the tracker was used while it was being built rather than a real difference: nobody
  applies to a role they never looked at. `manage.py backfill_saved_entry` gives each of
  them a `saved` entry dated the day before its first recorded status, so the flow diagram
  starts in one place. It takes `--dry-run`, it is the only command here that edits
  existing rows rather than adding to them, and re-running it is a no-op.

  The flow diagram lost its "added" column with them — `saved` is simply where the funnel
  starts now. The rule behind it stays, narrowed: an application logged straight into
  `closed` tomorrow still gets its own ribbon, because drawing it as something that passed
  through `saved` would be inventing history.

- **The CV page says something.** The two master CVs are cards rather than a list of two
  links — what each is for, how long it is, how many sections, when it was last edited,
  read off the file rather than stored, so a CV edited in an editor cannot leave a stale
  number behind. The tailored-CV table gained a **status** column: a tailoring effort that
  ended in `rejected` and one still at `interviewing` are worth telling apart on the page
  that lists the effort.

- **Status over time has a second view**: one line per status showing *what moved that
  week*, behind a toggle. Not the same numbers unstacked — a different measure. The stacked
  view answers "what shape is the pipeline"; this one answers "what happened to
  `interviewing`", falls back to zero in a quiet week, and makes a bulk logging session look
  like exactly what it is: a spike that never happened on that scale.

- **Ageing at applied lists its rows again**, under the bars, linked. The bars answer
  whether the quiet end is growing; the rows are what you act on.

- **A company now has three states, not two: `applied`, `reviewing`, `watching`.** Two
  could not tell "I have an application open with them" from "I have never done anything
  about them" — both read as *watching*, which is wrong about the first in the way that
  matters. Derived the same way, off the same signals, so nothing is set by hand:
  `applied` once an application was actually submitted, `reviewing` while one is live but
  unsent, `watching` when nothing is live — which covers both never applied to and every
  application closed or dropped. `/stats/` states that split rather than leaving it.

- **Search, filter and sort on the two long lists.** `/applications/` replaces its row of
  target-area chips with a toolbar: search by company or role, filter by area (and, on the
  full list, by status — everywhere else the page already *is* a status), and sort — including **longest without moving**, which is the one that finds what has
  gone quiet. A **Last moved** column comes from the status-change log, not from
  `Application.date`, which is when the row was logged and never changes again.

  `/companies/` becomes **one table** instead of a tab per category. Category is an
  attribute of a company, not a place some companies live, so it is a column and a filter
  alongside date added, status and application count; long lists page in rather than
  rendering all at once. All of it runs in the browser, so it works exactly the same in
  the published mirror — and needs no URL, which matters because a querystring cannot be
  published as a static page.

- **One set of status colours for the whole site.** The badges and the charts now read the
  same CSS custom properties, so a status is the same colour wherever it appears. Two hues
  moved to make that honest: `closed` from dusty red to amber, because it was a near-twin
  of `rejected` under normal vision and indistinguishable under protanopia — and the two
  mean different things, which is exactly why they are not merged — and `discarded` from
  the same grey as `saved` to slate.

- **Five charts on `/stats/`** — where applications go, which have gone quiet, how much of
  the watchlist has been acted on, how often the same company comes up twice, and how the
  shape of the pipeline has changed. Built on the new page rather than the dashboard, so
  the page used daily does not churn while the designs are judged; moving any of them to
  `/` is a later decision, one at a time.

  **Ageing at applied** bands submitted applications by how long since they last moved,
  breaking at 30 days, and the `applied` stat box now carries a line saying how much of
  that count has gone quiet — on the dashboard and on every applications list, because
  that is where the number it qualifies is shown. The same rows are in `/jobstudio status`
  under "Gone quiet", from the same helper, so the terminal and the page cannot disagree.

  **The status flow** is a Sankey with an entry ribbon per status — applications are
  logged straight into `closed` or `rejected` as often as into `saved`, and one shared
  source node would assert a funnel nobody went through — and everything still sitting in a
  status flowing on to one of two ends, `active` or `inactive`. Those ends are also the
  correctness check: in minus out must equal the status count, and a test deliberately
  breaks it to prove the check still bites. A Sankey cannot draw a re-opened application,
  so backward transitions are dropped **and the number dropped is printed**, because
  silently losing edges is how a diagram starts lying.

  **Status stock over time** replays the change log week by week. Weeks whose history was
  reconstructed are shaded and labelled: the 2026-09-08 backfill dated its rows from the
  day an application was logged, so they sit at exactly midnight, which makes them
  detectable rather than a guess. Without the shading those weeks read as a burst of
  activity that never happened.

  Every chart ships its numbers as a table *before* the drawing, so the page reads with no
  JavaScript, a screen reader gets values rather than a canvas, and the figures can be
  checked against the shape. **Apache ECharts 6.1.0** is vendored into the repo — the web
  app's first runtime dependency, Apache-2.0, no CDN, so a job search stays nobody else's
  business. `src/web/static/vendor/README.md` records version, hash and how to upgrade.

- **A new `/stats/` page**, linked from the sidebar under Tracker. It is where the
  dashboard charts (`#42`) are being built — a staging ground rather than the dashboard
  itself, so the page used daily does not churn while chart designs are still being
  judged, and so each chart can show the raw numbers it was computed from beside it.

  No chart is built yet. What is there is the skeleton every chart will land into: a
  readout of what there is to chart, and one slot per planned chart that states what it
  is waiting for. That order is deliberate. Most people meet a page like this on a tracker
  with almost nothing in it, and the states a chart falls back to when it cannot draw
  honestly are the part hardest to add afterwards — so they exist, and are tested, before
  the first diagram.

  The readout splits **entry events** from **transitions**, which sounds pedantic and is
  not: a status change with no previous status records where an application was first
  logged, not a move between two statuses. Only the second kind is an edge in a flow
  diagram. The example data root has three status changes and no transitions at all, so a
  Sankey drawn there would have nothing to draw — the page says so rather than showing an
  empty frame.

## 2026-09-27

- **The Ashby fetcher was reading only a posting's primary location**, so every
  multi-location Ashby posting lost its other locations — and the location pre-filter,
  seeing no UK or remote signal, dropped it before scoring. Found on a posting whose
  primary location was "San Francisco" and whose `secondaryLocations` were "London" and
  "Remote": silently discarded as non-UK. It read as a location filter working correctly,
  which is why it survived.

  Every Ashby company was affected, not one. On the run that surfaced it, reading
  `secondaryLocations` recovered **eight postings, five of them UK-eligible**, including
  four core safety-research roles with London listed. Locations are joined
  primary-first and de-duplicated.

- **`scan.md` now says to keep `role_target` and `key_terms` to qualifiers rather than
  seniority words.** The pre-filter unions both and passes a title sharing any single
  word, so one generic word swamps a large board: on a live run "Research Engineer" and
  "Member of Technical Staff" in an area's `key_terms` admitted 264 of 353 candidates,
  "engineer" alone accounting for nearly one whole frontier-lab board. Trimming to
  qualifiers cut that run to 113 with no loss at the small, focused companies where a bare
  "Research Engineer" is the relevant job. Generic titles belong to a *company*, where
  they only match that company's own board; an *area's* key terms should only discriminate.

- **A company can be scanned against more than one target area.** Every company got
  exactly one, via its category — so an organisation that genuinely hires into two of
  your positionings forced a choice that dropped half its postings before scoring, on the
  title pre-filter, invisibly. `company_areas` in `<DATA>/jobs/scan-config.yaml` maps a
  company name to a list of area slugs in preference order.

  The company declares which areas are possible; each posting is assigned **one** of them
  by `scan_match.pick_area`, on how many of its title words each area's `key_terms`
  account for — ties and role-target-only matches falling to the first listed. Scoring a
  posting once per area would double the bill to produce two numbers for one job and list
  it twice in the report. For a company with one area the function is exactly the old
  `is_plausible_match`, and a test asserts that, so single-area scanning is unchanged.

  In the report, a company whose postings span areas gets an **Area** column and a
  heading that says "scored per role"; every single-area company's table is byte-identical
  to before.

- **`src/scan_match.py`** — the keyword pre-filter and the area picker, extracted from
  `scan-portals.py` for the reason `scan_sources.py` was in September: the hyphen in that
  filename means nothing can import it, so the function deciding what reaches the scorer
  at all could not be tested.

- **`soft_negatives` in `criteria.yaml`** — the mirror of `bonus_signals`. A reservation
  that nudges the Ideal-Job Score down a point or two and gets named in the note, as
  against `hard_filters.exclude`, which the rubric scores 1–2. "Heavily political large
  organisations" is the case it was added for: worth knowing about a role, never worth
  hiding it. The rubric documents it, because an unread field is decoration.

- **Ashby, SmartRecruiters and Teamtailor are now detected from the careers URL.** The
  comment in `scan_sources.py` had them down as platforms that hide the tenant behind a
  corporate page and must be recorded by hand — true of a company that links to its own
  careers page, false whenever it links straight at the board, which many do. Every such
  company needed an override, including ones whose tracked URL already spelled the token
  out. The pattern table now carries the parameter name each fetcher reads, because
  Teamtailor's wants a whole host in `domain` and emitting `token` for it would have
  raised a KeyError mid-scan.

## 2026-09-25

- **The VS Code workspace `init` writes is now `jobstudio+data.code-workspace`.** The
  `+data` names what opening it actually does: puts a private data root alongside the
  public repo. It is the one file where the two are named together, so the filename is
  the right place to say so. Gitignored, as before — it holds an absolute path into
  someone's job search — and the old `jobstudio.code-workspace` stays in `.gitignore`
  so a checkout that ran the earlier `init` keeps its copy ignored rather than
  suddenly offering to commit it.

- **A scan can no longer score against nothing without saying so.** `scan-portals.py`
  resolves a company's target-area profile with `profiles.get(area, {})` — so an area
  naming no `jobs/targets/<slug>.yaml` yields an empty profile and the scan carries on:
  the keyword pre-filter falls back to the company's role target alone, the scorer judges
  against no `description`, `emphasis` or `key_terms`, and every row still gets an Area
  Score. Nothing in the report said otherwise. On a fresh data root, where
  `jobs/targets/` is empty and nothing ever wrote into it, that was *every* row — a scan
  that looked like it worked.

  **`tools/py src/scan_config.py --check`** reports the whole chain: no target areas at
  all, a `category_to_area` entry or `default_area` naming a file that doesn't exist, a
  tracked category resolving to no area, a target missing its scoring fields, and the
  unquoted-colon list entry that parses as a mapping instead of a string. Exits non-zero,
  so it can gate a first scan. `scan.md` runs it as step 0 on a data root that has not
  been scanned before.

- **`init.md` §"Define the target areas"** — propose two or three from the stocktake's §6
  and `criteria.yaml`, confirm, write one YAML each, `import_jobs`, check. Areas are
  positionings, not industries: several categories share one, and an area per industry
  produces files that score identically. Placed before "Seed the tracker", which needs
  them to map its categories onto.

- **The shipped example's `category_to_area` was keyed on two category names its own
  fixture never had.** Both entries were dead, every example company fell through to
  `default_area`, and `developer-advocacy` was unreachable in the dataset that exists to
  demonstrate it. Fixed, and the check now runs against the example in the test suite.

- **`init` no longer leaves you with a tracker nothing can scan.** A fresh data root
  finished setup with a CV, a profile and zero companies — and `scan` reads tracked
  companies, so the first run found nothing and the most visible feature in the toolkit
  looked broken on day one, for a reason nothing on screen explained.

  `subcommands/init.md` gains a **"Seed the tracker"** step, placed after `stocktake`
  because that is where the target areas and sectors get written and there is something
  to infer a starting list from. It asks for direction first — sectors, org size,
  geography, companies already in mind — then agrees two or three categories, researches
  10–20 candidates, presents them for a yes per row, and writes only what was approved.
  A tracker seeded with fifty unvetted names is worse than an empty one. `stocktake.md`
  offers the same step at close-out when the tracker is still empty, which is where
  anyone who skipped it at `init` will actually be.

- **`jobsdb.py add-category`** — categories are the user's own taxonomy and the toolkit
  ships none, but until now nothing outside the Django admin could create one. Idempotent,
  and an existing category keeps its hand-set `order`.

- **`add-company` refuses a category that doesn't exist** instead of silently writing the
  company without one. The old behaviour reported success and left an uncategorised row,
  which then scored against `scan-config.yaml`'s `default_area` rather than the area its
  category maps to — a mistake that surfaced far from where it was made. Auto-creating the
  category would have been no better: it turns a typo into a permanent second category
  with one company in it. The error names the tracked categories and the command to add
  the missing one.

- **`scan_sources.py` can be run directly** — `tools/py src/scan_sources.py "<name>"
  "<url>"` prints `scanned via <platform>` or `NOT scanned — <reason>`. The same answer
  the companies page already showed, asked one step earlier: a careers URL is chosen when
  a company is being *added*, and one that resolves to no board makes the company
  invisible to `scan`. Offline, no fetch, so checking twenty candidates costs nothing.

## 2026-09-24

- **A cover letter renders to `.docx` alone unless you ask for more.** HTML was written
  on every render because the PDF path needs something for Chrome to print. That was
  invisible while renders went to `exports/`; once they landed in the application folder
  (above), every cover letter left an `.html` beside its `.docx` that nothing downstream
  reads. The Chrome intermediate is a temp file now, and `--format html` is what puts one
  in the folder for real. `--format` lost its default so the cover-letter path can tell
  "I want HTML" from "I said nothing"; a CV with no `--format` still renders HTML as
  before.

- **A render is written once, where its source lives** — and the 16 MB backlog in
  `exports/` is gone. Every render used to go to `exports/<fmt>/<date>/`, with an
  application's `.docx` copied back afterwards: two copies of each file, under two
  different names, in a flat dated tree that named neither the source nor — for 22 of
  them — any application at all.

  `render._home()` picks the destination up front instead. A source in
  `jobs/applications/NNN-*/` renders into that folder's `export/`; a base CV from
  `jobs/cv/base/` renders into the new `jobs/cv/export/`, named `cv_functional-<date>.docx`
  to match the `base/archive/` convention; anything else still goes to `exports/`, which
  keeps its place as the home for documents belonging to no folder — a career stocktake,
  an ad-hoc `--file` from outside the data root.

  **`manage.py prune_exports`** clears what the old behaviour left behind. Like
  `migrate_exports` it prints its plan and writes nothing without `--apply`. It moves a
  render labelled with an application into that application's `export/`, keeping the date
  it was rendered on; keeps the newest `.docx` of each base CV; deletes the rest —
  superseded base renders, the retired variant library, and unlabelled renders that can't
  be attributed to any application. Anything *not* named the way a render is named was put
  there by a person: it is listed and left alone.

  In the real job search: 40 moved, 220 deleted, 16.0 MB → 48 KB. Eight applications got
  back the only rendered artifacts they had (their PDFs existed nowhere else).

- **Rendered exports move into an `export/` subfolder** — a `.docx` rendered from a
  tailored CV or a cover letter used to land flat in the application folder, beside the
  markdown it came from, so `applications/NNN-<company>/` mixed sources and output. The
  copy now goes to `applications/NNN-<company>/export/`, leaving only authored markdown
  (`job.md`, `notes.md`, the CV, the cover letter, the interview rounds) at the top level.

  Existing folders are **not** migrated, so every reader has to accept both shapes. That
  is now one function rather than a `md.with_suffix(".docx")` repeated at each call site:
  `appfolder.exported_file()` looks in `export/` first, then beside the markdown, and the
  CV tab, the Cover letters tab and `extra_files` all go through it.

  `extra_files` — the "nothing saved here goes invisible" tab — keys its exclusions on
  **paths** now, not bare filenames: with the export one directory down, "is this already
  shown on another tab?" became a question a name alone could not answer. Anything else
  left in `export/` still shows there, listed as `export/<name>`.

  `<DATA>/exports/<fmt>/<date>/` (plural, at the data root) is unchanged — it stays the
  global export area every render writes to first.

  **A render is linked even when its name doesn't match its source.** The copy is named
  with the date of the *render*, not of the markdown it renders, so re-rendering a letter
  written last week produces a stem its source doesn't share — nine of 34 exports in one
  real job search were orphaned this way, showing under *Other files* with no "Open .docx"
  on the tab that owns them. `exported_file()` now falls back to the newest export of the
  same kind (CV or cover letter) in `export/`, and holds off when the folder has more than
  one markdown of that kind, where pairing would be a guess. A superseded earlier render
  keeps its place under Other files rather than being linked.

  **`manage.py migrate_exports`** tidies folders written before today. It shows its plan
  and writes nothing until given `--apply`; it moves only top-level files carrying the
  folder's own name as a prefix, so a JD or a recruiter's PDF saved in by hand stays
  where it was put, and it never overwrites a name `export/` already holds. Readers
  accept both layouts either way, so running it is housekeeping, not a prerequisite.

- **Interview rounds are their own files, and their own tab** — an interview used to be
  written into `notes.md` under a single `## Interview prep` heading. That put one
  round's prep, its outcome and its timeline entry in three different places, and had
  pushed one real application's `notes.md` to 63% interview content across two rounds.

  Each round is now one file in the application folder,
  `<application-id>-<person-slug>-interview-<stage>-<YYYY-MM-DD>.md`, where the date is
  the date of the **interview** — not, as with CVs and cover letters, the day the file
  was written, which is what makes sorting on the name a real chronology of the process.
  Stages: `hr-screen`, `hiring-manager`, `technical`, `panel`, `final`, `informal`.

  Each file carries Details / Who I'm meeting / Prep / Questions to ask them / Study
  before / Private / **Outcome**. `## Outcome` is what makes a round self-closing, and
  `/jobstudio interview` now reads every prior round's before prepping the next one — a
  round's outcome outranks the job description wherever they disagree, being what the
  company said about itself out loud.

  The application page grows an **Interviews** tab, rounds stacked newest first, built
  the way Cover letters already was: discovery by naming convention, no database row.
  Prose lives on disk; the tracker keeps status. A round gets a model the day scheduling
  or reminders need one.

  The tab sits between **Job description** and **My notes** — once a process is live the
  rounds are what gets reread, and the JD is what they're read against. From two rounds
  up the panel opens with an index of them. `notes.md` keeps only what is true of the
  *role* rather than of a meeting, with `## Timeline` indexing the rounds.

  Migration covered every application folder: two of them split into two rounds each,
  three whose `## Interview prep` held written answers to application-form questions
  relabelled `## Application questions` (no interview had happened in any of the three),
  and the empty scaffolded heading removed from the remaining 31.

- **Deep links into a tab** — `tabs.js` reads the URL hash on load to choose a tab, and
  used to fall back to the first tab for any hash that wasn't a tab name. So a link to
  something *inside* a panel worked when clicked and broke on reload, landing on the
  wrong tab with its target hidden.

  It now resolves a hash naming an element inside a panel by opening the panel that
  holds it. Interview rounds (`#round-<stage>-<date>`) and the files under Other files
  (`#file-<slug>`) carry ids, so prose anywhere in a folder can link one directly and the
  link survives a reload or a share.

- **`make-public-tree` derives its company denylist from the tracker** — every other
  content check matches a list someone remembered to write. `.private-terms` held five
  terms, and a changelog entry describing this release named three companies from the
  author's own applications: the mechanism was sound, the list simply could not keep up.
  Nobody maintains a denylist of fifty employers that grows every week.

  The new check reads every company name out of the tracker database — read-only, via
  `sqlite3`, so it needs no Django — and refuses to ship a tree that names one. It cannot
  go stale, because the tracker is the list.

  A tracked company can also be a vendor, a standard, or the maker of a tool the project
  depends on, and the check can't tell "I'm interviewing there" from "we call their API".
  So names can be exempted in a gitignored `.tracked-company-exceptions`
  (`.example` shipped), for the same reason `.private-terms` is gitignored: a list of
  companies you track discloses your search whether it marks them allowed or denied. The
  mechanism ships; the names do not.

  It found real leaks on its first run, in files written the same day: an example
  filename in `appfolder.py`, the interview skill, `docs/interview-prep.md` and five
  assertions in `tests.py` all used a real tracked company as the worked example, and
  one doc named the company an answer-bank entry was validated at. Documentation
  examples now use the shipped `example-data` fixture instead, which is what a reader can
  actually run.

- **The publish check runs on every push** — `make-public-tree` was built to *cut* the
  public repo out of the old private one, a one-off. That job is long done: this repo
  now **is** the public repo, and it pushes `dev` as well as `main`, so every push is a
  publication. The valuable half was the checks, welded to a copier that demanded an
  empty destination — the wrong shape for a recurring gate.

  `tools/make-public-tree --check` now builds into a temp directory, runs every check
  against it, and deletes it. Same script, so the two paths cannot drift into different
  ideas of "clean". In check mode it also pulls in untracked-but-not-ignored files rather
  than refusing on a dirty tree: the point is to catch a leak *before* the commit that
  publishes it, not after.

  `tools/git-hooks/pre-push` runs it and blocks the push on a hit. The hook is versioned
  in the repo rather than left in `.git/hooks` — not backed up, not shared, empty on a
  fresh clone — and `git config core.hooksPath tools/git-hooks` turns it on, which `init`
  now does when the checkout has a remote. `git push --no-verify` bypasses it.

  It cannot run in CI, and that is not an oversight: the tracked-company check reads the
  tracker database in the data root, which is gitignored by design. A GitHub Action has
  no access to it and could not enforce this even in principle. The gate is local.

- **A guard against linking a bare markdown file** — files in an application folder are
  *rendered into* the application page, never published beside it, so a relative
  `[…](notes-something.md)` link resolves to nothing in the web view and fails
  `build_static`'s link checker. Easy to write by accident and invisible until a publish.
  `test_no_folder_markdown_links_a_bare_md_file` now scans every markdown file in every
  application folder and fails on one. Link the anchor instead.

  Note what it can and can't do: the suite runs against `example-data/`, so this guards
  the convention and the shipped example, not a user's own data root. `build_static`
  remains the check for that — worth running before a publish.

## 2026-09-23

- **BambooHR is scanned** — a fetcher for the public JSON behind every BambooHR careers
  page, plus tenant detection from the careers subdomain. Ten ATS integrations now.

- **A careers link on the companies a scan can't reach** — the rows that have to be
  checked by hand now link straight out to the company's careers page, instead of a trip
  through the company page to find the URL.

- **The sidebar has icons, and a link to the repo** — each top-level section carries a
  line glyph that picks up the active item's colour; sub-items stay text-only so the
  indent still reads as hierarchy. The footer links to the GitHub repo, on the published
  site as well as locally.

- **The app is called Job Studio** — the sidebar, the dashboard heading, every browser
  tab and the admin header said "Job search". The name now lives in one place
  (`settings.APP_NAME`), and the sidebar carries a logo of its own — a briefcase glyph
  and the two-tone wordmark as one lockup. The package, repo and command stay
  `jobstudio`.
- **Scan coverage on the companies list** — a new column says whether `scan` picks each
  company up automatically and on which ATS, or the specific reason it doesn't, with a
  count at the top of the page.

- **Any status can be set from the application page** — the page offered one hardcoded
  action, "Mark reviewing"; every other transition meant a trip to the Django admin. A
  "Set status" menu now lists all seven statuses (bar the current one), logging the
  change to the History tab the same way an admin edit does.

- **Every tailored CV is listed on `/cvs/`** — the page showed only the two master CVs,
  so a CV written for a role was invisible unless you knew which application folder it
  was in. It now also lists all tailored CVs, newest first, each naming the application
  it belongs to and linking through to that application's CV tab.

## 2026-09-21

Initial public release.

`jobstudio` is an agent-native job-search toolkit: track companies, log applications,
tailor a CV per role, draft cover letters, run gap analysis, and scan ATS job boards for
new postings — driven end to end from a Claude Code session, with a local Django app for
browsing.

It grew out of one person's job search over several months, then had that person's data
separated from it so anyone could run it. Code and data are two directories: this repo is
the toolkit, and your job search lives in a data root you choose, outside it.

- **Nine ATS integrations** — Greenhouse, Lever, Workable, Workday, Ashby,
  SmartRecruiters, Teamtailor, Rippling, plus a generic first-party-JSON fetcher —
  with two-dimension scoring and a location filter.
- **Two base CVs** (functional and chronological), tailored per application on demand
  rather than kept as a variant library.
- **A local Django app** for browsing applications, companies, CVs and scan reports,
  with an optional static-site export.
- **`/jobstudio init`** sets up a data root from scratch, from an existing CV, or from a
  complete fictional example job search so there is something to look at first.
- **No API key needed.** Every default workflow runs inside your Claude Code session;
  one opt-in path (`scan --api`) wants an Anthropic key for headless scoring.
