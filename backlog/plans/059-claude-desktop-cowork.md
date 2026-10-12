# M4 — Claude Desktop / Cowork *(parked)*

> **Status:** `#59` closed as won't do on 2026-10-09 (see `DONE.md`). Kept for reference.

> Extracted from [`002-share-as-toolkit.md`](002-share-as-toolkit.md) on 2026-10-02,
> where this was **milestone M4** and lived as §7. `#2` — the umbrella item that plan
> served — is closed; this is the part still open, so it moves to its own file named for
> the item that owns it.
>
> **Section numbers are kept as they were.** `TODO.md`, `001-drop-direct-anthropic-api.md`
> and `log/2026-09-23-status-menu.md` all cite §7 — renumbering would break every
> one of them for no gain. So this file starts at §7.
>
> **Written 2026-09-20, before the `jobstudio` rename settled** (`002-share-as-toolkit.md`
> §2e). The text below is verbatim and still says `/jobs-search`,
> `.claude/skills/jobs-search/` and `.jobsearch-data`; read those as `/jobstudio`,
> `.claude/skills/jobstudio/` and `.jobstudio-data`. Left as written rather than quietly
> edited, because this is a dated research record and the commands it names were real on
> the day.
>
> Background it refers to — the data root (§3.1), the Dropbox question (§5.2), the
> milestones (§6) — stays in `002-share-as-toolkit.md`.

---

## 7. Stretch goal A — Claude Desktop / Cowork *(parked)*

> **Status: parked 2026-09-20.** Researched properly (below) and it's more viable than
> the first draft claimed — but three things argue against spending effort here now:
> the egress bugs that break `scan` (§7.1 #4), the direct conflict with the Dropbox
> data root (§7.3), and the fact that Cowork was folded into Claude four days before
> this was written, so the target is moving. **§8 is the better route to the same
> goal.** Keeping this section because the findings are solid and would be tedious to
> re-derive.

Michele's question: what would it take to run this from Claude Desktop or Cowork
instead of Claude Code?

**Researched against current documentation 2026-09-20** (the first draft of this
section was guesswork and got the hardest problem wrong — see 7.2). Sources at the end
of the section. Two things to know before anything else:

- **Cowork stopped being a separate product four days ago.** Anthropic folded it into
  the main Claude interface on 2026-09-16, alongside Claude Docs and Claude Slides;
  requests now route automatically rather than the user picking a tab. The
  *capability* is unchanged and the Cowork docs still stand — but "build for Cowork"
  is now "build for Claude", and the surface is moving. Don't design against details
  that might be a month old.
- **Cowork runs the same agentic architecture as Claude Code**, in Claude Desktop,
  without a terminal. So this is much less of a port than the first draft assumed.

### 7.1 The five requirements, re-checked

| # | Requirement | Verdict |
|---|---|---|
| 1 | **Durable filesystem** | ✅ **Solved — this is a product feature.** The user attaches **workspace folders**; the agent "can then read, create, and modify files anywhere inside those folders, **and run code against them inside the sandbox VM**". Files stay in place on disk — "no uploading or re-downloading, and edits land directly in the folder." So the data root can be an ordinary local folder and the Python scripts can work on it directly. |
| 2 | **Dependencies** | ✅ Workable. `pip` works and PyPI is reachable when egress is configured; network egress exists specifically so Claude "can access the internet to install packages and libraries". Cost is cold-start install time per session, since the sandbox is provisioned per session. Django is heavy but installable. |
| 3 | **The Django web app** | ⚠️ Still the real limitation. No `runserver` + `localhost:8000` browsing. Half-solved already, and this survives now that the site export is being **kept** (§1): `tools/site-build` renders every page to static HTML **in-process, no server, ~2s**, and that output can be handed back as files. So the *viewer* survives; the *Django admin* — editing rows by hand — does not. Worth noting the feature earns part of its keep here. |
| 4 | **Network egress** | ⚠️ Configurable but currently flaky. There's an account-level "Allow network egress → All domains" setting, enforced by a proxy. But there are multiple open bugs (Sept 2026) where cloud containers come up enforcing a **~5-host allowlist regardless of the setting**, and a macOS regression where the sandbox VM starts with no network route at all. `scan` hits 8 ATS platforms, so it's exactly the feature this breaks. Treat as "should work, verify empirically, don't build on it yet". |
| 5 | **Skill packaging & cwd** | ⚠️ Needs work, and M2 does most of it. Custom skills are uploaded as a **ZIP** via Settings → Features / **Customize**, need a paid plan with code execution, and — importantly — **Cowork does not read `~/.claude`**. So `.claude/skills/jobs-search/` can't just be pointed at; it has to become a self-contained, cwd-independent skill bundle. The ~104 repo-root-relative path references in `subcommands/` are the work. |

### 7.2 The fork in the road has moved

The first draft argued that requirements 1 and 3 together meant
sqlite-as-source-of-truth was the wrong shape, forcing a choice between a reduced
desktop mode and reversing the Phase 6 decision (`log/2026-09-07-django-frontend-plan.md`).

**That was wrong, and the reason is requirement 1.** The data root doesn't need to
live in an ephemeral sandbox — it lives on local disk as an attached workspace folder,
and sandboxed code runs against it. sqlite stays exactly where it is. **Option β
(files as truth, DB as index) is not required and should be dropped from
consideration** — it would reverse a decision that solved a real drift problem, to buy
something that's now free.

So this collapses into a much smaller thing:

**Option α, and only α.** Keep sqlite-as-truth. Package the skill as an uploadable
ZIP, make it cwd-independent, point it at the attached data root.
`stocktake`, `cv`, `cover-letter`, `interview`, `application`, `company` and `status`
all work — they're markdown-and-sqlite in, markdown out, and already agent-native
since `#1`. `scan` works if egress cooperates. The web app degrades to
`tools/site-build`'s static output; Django admin editing stays Claude Code–only.

That's a genuinely modest amount of work on top of M2, and most of it is M2's
packaging pass being reused.

### 7.3 Three caveats worth writing down now

1. **⚠️ Cowork and Dropbox conflict — this hits §5.2 directly.** Anthropic's own
   guidance: if your work folder is inside iCloud, Dropbox or Google Drive, Cowork
   "can sometimes get confused about file versions, pending syncs, or sync conflicts…
   a real source of weird bugs." Michele's data root is planned for Dropbox precisely
   because it's synced and shareable. For Claude Code that's fine. For the Cowork
   path it's the discouraged configuration. See the note added to §5.2 — this doesn't
   block M1, but it means M3 may want the data root on local disk with Dropbox used
   for backups/exports only.
2. **sqlite over a sandbox-mounted folder is untested here.** File locking across a VM
   mount is the classic place this goes wrong. Cheap to test early, ugly to discover
   late — make it the first thing M3 tries.
3. **Scheduled tasks can't see local files.** Cowork scheduled tasks run "even when
   your computer is off", and "if the desktop app is offline, the session can't reach
   your computer." So a nightly automated `scan` — the obvious thing to want — can't
   use a local data root. That's an argument for keeping the existing headless
   `scan-portals.py` → `score-candidates.py --api` path (the one remaining use for an
   Anthropic API key) rather than retiring it.

**Sources:**
[Cowork overview](https://claude.com/docs/cowork/overview) ·
[Desktop and filesystem access](https://claude.com/docs/third-party/claude-desktop/local-access) ·
[Get started with Cowork](https://support.claude.com/en/articles/13345190-get-started-with-claude-cowork) ·
[Use Cowork safely](https://support.claude.com/en/articles/13364135-use-claude-cowork-safely) ·
[Use skills in Claude](https://support.claude.com/en/articles/12512180-use-skills-in-claude) ·
[Anthropic merges chat and Cowork (TechCrunch, 2026-09-16)](https://techcrunch.com/2026/09/16/anthropic-merges-claude-chat-and-cowork-in-one-interface/) ·
egress bugs: [#93525](https://github.com/anthropics/claude-code/issues/93525),
[#93512](https://github.com/anthropics/claude-code/issues/93512),
[#93507](https://github.com/anthropics/claude-code/issues/93507)
