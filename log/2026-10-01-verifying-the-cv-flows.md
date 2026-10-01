# Verifying the CV flows, and closing the toolkit milestone

*2026-10-01. Backlog `#23` and `#2`, the two oldest open items, both closed. `#23` was
the one that mattered: it asked whether the agent-native flows had ever been run for
real, and the honest answer for two of them was no. Running them produced two new items
(`#60`, `#61`) and one shipped fix.*

## What was actually open

`#23` had five sub-items. Three were already verified — the default scan, `scan --api`,
functional CV tailoring — and `cv --import` had been closed on 2026-09-29 by the
second-machine install, which is where `#44`–`#47` came from. Two were untouched:
chronological tailoring, and the `cv --rebuild` interview.

Worth noting what the item had drifted on, since it is a lesson about the backlog rather
than the code: `#23` still told a reader to type `/jobs-search`, a command name retired
weeks earlier, and `#2`'s body still said M1.8 was two-thirds done when
`log/2026-09-29-second-machine-findings.md` opens by declaring itself that third pass.
An open item that is wrong about the present is worse than one that is merely stale,
because it is read as instructions.

## Chronological tailoring — and an unreported count

Run against a real application as a `--base chronological` one-off. The flow worked. The
bug was next door.

`render.py --check` existed because of `#44` — the shipped example CVs were written in a
format the parser could not read, and both lost their entire work history silently. It
counts what it read per section, so loss surfaces without being asked for. But
`_parse_skills()` returns two things, skills and languages, and the Languages line is
lifted *out* of the skills list — so `skill groups: 5` says nothing whatsoever about
whether any language survived. Written with dashes instead of parentheses, every language
was dropped, and the summary line was **byte-identical** to a correct parse, down to the
skill-group count, with `CHECK OK` underneath it.

Fixed: `languages: N` is now reported, and a Languages line that parses to nothing is a
warning naming the format. A CV with no languages at all stays a finished CV, same stance
`#47` settled for the header links. Three tests.

Two things about the subcommand came out of the same run, neither a bug. A target area's
`condense_sections` can be actively wrong for a specific role — here it named the one
section the advert's own company description was closest to, so following it would have
buried the best match in the CV. The area profile is a prior, not an instruction, and
`cv.md` reads as the latter. And the "one CV per application" rule has no answer for a
`--base` override on a folder that already holds a sent CV of the other base; that is
`#60`.

Three mistakes in the draft itself are worth recording, because all three were caught by
diffing against the base rather than by any check: roles reordered out of
reverse-chronological order, a bullet dropped from a section the target never asked to
condense, and an achievement bullet invented from a publication. The rules forbid all
three. A CV draft needs reading against its source, not just parsing.

## `cv --rebuild` — the real finding

Run against a scratch data root seeded with copies of the real base CVs and
`stocktake.md`, which is the honest way to exercise a flow whose whole job is to replace
both base CVs. All eight steps, review gate at each. Every safety step behaved: nothing
written until step 8, both files backed up to `archive/` first, `--check` on both,
`CHECK OK` with counts identical to the originals. The real files were confirmed
untouched afterwards.

The design, though, does not survive contact with the data.

`--rebuild` collects one set of facts in steps 1–5 and derives both files from it in step
6 — resting on the format contract's claim that the two files differ in *framing*.
**They differ in content.** The functional file's Core Competencies is the richer
document by a wide margin, carrying a revenue figure, a percentage improvement in
customer-reported errors, a named internal platform initiative, named agency workshops, a
conference keynote, headcount growth and a team-size figure that appear nowhere in the
chronological file. Step 2's pre-fill reads naturally as the chronological role bullets.
So a literal run drops all of it, produces two well-formed files, and reports `CHECK OK`.

That is `#44`'s failure mode moved up a level, from the parser to the interview, and it
is strictly worse: a check can tell whether a section parsed, and cannot tell whether a
file lost a fact it used to carry, because both versions are valid. The guards that exist
are the pre-fill reading *both* files, and the backups — which is exactly how this run
was verified non-destructive. Written up as `#61`, with the fix in three parts and the
honest note that no check will catch it.

The Skills sections differ too, which step 4 would silently converge; Michele made the
functional wording canonical. And "one employer at a time" assumes a blank page — with
complete pre-fill it costs six round trips to re-approve your own text. Both in `#61`.

**The broader conclusion, and the reason `#23` was worth doing at all:** every one of the
three flows that had never been run live had a real defect in it, and all three defects
were invisible to the code-level smoke tests done while building them. Two were silent
content loss. A flow that exits zero has shown nothing about whether content survived it.

## `#2` — closed, and split

M1.8's third pass, "a second real person", was closed by substitute: the 2026-09-29
second-machine install, recorded in the plan with what it covers and what it does not. It
was the same person on a different machine, so it tests nothing about a second person's
vocabulary or mental model — but it bought the install-and-import confidence the
milestone existed for, and it was by far the most productive of the three passes, which
is the argument for accepting it. The remaining third needs a genuine outside user: a
thing to seek when someone is interested, not a task to carry in a backlog.

With that, M1 is complete and `#2` is closed. M2, M3 and M4 moved out to `#57`, `#58`,
`#59`. Carrying four milestones under one ID had produced an item that could never be
ticked — M1 had been finished for days while the entry still read as open. The plan
remains the design of record for all three; only the bookkeeping changed.


## The two findings, fixed the same day

`#61` first, as the more serious. Three changes, and the shape of them is worth noting:
none is a check.

The pre-fill row in `cv.md` §A.1 now says **read both base CVs, every time**, with the
reason underneath: diff them section by section before asking anything, and where a fact
is in one and not the other, carry it and say so — a fact may be dropped because the user
decided to drop it, never because the pre-fill didn't look. `--rebuild` also now says what
it is *for* when both files already exist: a blank-page tool, whose realistic outcome
against a good existing pair is eight steps of re-approving your own text while the only
thing that really changes is a loss. It names the alternatives and is explicitly a steer,
not a refusal. And `cv-base-format.md` gained a section up front saying the two files are
not two views of one fact set, naming the functional Core Competencies as the source of
record, and stating that `--check` cannot catch this and is not meant to.

That last part is the bit worth keeping hold of. The instinct after `#44` was to reach for
a check, and a check is the wrong instrument here: both the rich version and the
impoverished one are valid markdown, so there is nothing to detect. The guards available
are reading both files before writing either, and the `archive/` backups — which is
exactly how the verification run above was confirmed non-destructive.

`#60` was decided rather than discovered, and decided **twice** — which is the more
interesting part.

The first answer was *replacement*: an override removes the other base's CV, announced in
the review step, with `export/` left alone because the rendered `.docx` is the record of
what was actually sent. It was built, tested and then backed out on Michele's call, and his
argument is the better one. Two different bases are two genuinely different documents for
the same role, and the earlier one may be what has already gone to the employer — so
deleting it destroys a record in order to satisfy a rule aimed at a different problem. The
one-CV-per-application rule is about *the same base*: a tailored pass superseding an earlier
copy of the file it tailored, two files differing only by date. That really is how the wrong
one gets sent. One functional and one chronological CV is not that.

What replaced it is better and smaller: **the UI shows what is there, instead of the
toolkit deciding by deleting a file.** The CV tab now carries an index above the CVs when
there is more than one — the same pattern the Interviews tab has used for rounds, down to
reusing `round-index` and the "only from two up, a list of one is noise" rule — with the
base label, the date, an `unedited copy` marker where it applies, and an anchor into each
full text. `cv_files` grew `label`, `date` and `anchor`; the anchor is built from base plus
date rather than the filename, because every CV in a folder repeats the company and person
slugs, so filenames make poor ids. A test asserts the anchors are distinct, since two links
to one id would scroll to the same CV and the index would quietly lie.

Worth recording that the replacement implementation was not wasted. Building it is what
surfaced the stored-`cv_base` question, and `set-cv-base` survived the reversal on
independent grounds: `cv_base` was settable at creation and in the Django admin and by
nothing on the agent-native path, so "use the chronological base for this role from now on"
had no command behind it. Same gap and same argument as `#41`'s missing `update-company` —
the admin is the editing surface for a person, not for an agent mid-flow. Its docstring now
gives that reason rather than the flip-flop one, which keep-both removed; a justification
that has quietly stopped being true is worse than none.

Two statements in `cv.md` called a `--base` override "a one-off (this never changes what's
stored)". They were wrong under replacement and are right again under keep-both, but for a
reason the file never gave — so they now say what actually happens: the override adds a CV,
and only an explicit "from now on" moves the stored value.

## Still open, deliberately

`#2`'s third verification pass. Michele is arranging the install on a second machine with
**someone other than himself** driving it. So the substitute closure recorded above is the
floor, not the answer, and the plan's M1.8 section now says so with somewhere for the
findings to land. On the record of the other two passes, the expectation should be findings
rather than a clean bill — every verification pass in this project has produced some, and
the second-machine run produced the most valuable ones in it.


## The second-person pass, same day — and what it found

`#2`'s third verification pass happened a few hours after being closed by substitute: a
second person installed the toolkit from zero on a second machine, with their own CV, and
ran it through to a scored scan.

The setup path worked. Virtualenv reuse, data root, `config.py --chain`, pre-push hook,
both base CVs written and parsing, a drafted profile honest about which sections the CV
could not fill, two target areas, seventeen companies, board lookups for the fourteen
behind corporate careers pages, two scans. Nothing in the install failed, which is the
third pass in a row to say that.

**Then it found the worst thing in this project's history.** The public repo was
publishing the maintainer's completed psychometric results: `subcommands/stocktake.md`
held the career-anchors questionnaire as a ranked table of eight anchors with his
averages, his three "most true" picks quoted verbatim, and his values exercise ranked into
four groups. `docs/career-stocktake-profile.md` held a second copy of the anchors. Public
since the repo was cut.

Every single run of `make-public-tree --check` had passed it — including the ones in this
session, including the pre-push hook. Not because of a bad exemption this time, but
because **no check in it had a notion of that category.** Psychometric results are not a
company name, not an email address, not a home path. They are not any of the things
someone had thought to ask the guard about.

That is §5.7's lesson for the third time, and in its sharpest form. The data-root split
found a denylist that made the verifier skip files it had never read. The clean room found
an `ALLOW_NAME` exemption hiding real company names in a test fixture. Both were about a
check being *pointed at the wrong place*. This one is about a check that was never
written. **A guard refuses only what someone thought to ask it about**, and the way you
discover what you forgot to ask is to put the thing in front of someone who does not share
your assumptions. That is the entire argument for M1.8's third pass, and it took one
afternoon to be proved right after I had argued it could be closed without.

The second person's session was also right about the second half, which I nearly missed:
the file was not only leaking, it was *written about one person*, in the third person
throughout. So a new user running `stocktake` was being handed someone else's completed
answers as their own starting point — a correctness bug sitting underneath the privacy
one.

**The fix, and the guard for the class.** Results gone from both files, which now describe
the method and point at the data root for the answers. All third-person singular rewritten.
`make-public-tree` gained a check refusing any shipping `.md` that uses *his/him/hers/she's*
— the pronoun being the tractable signal, and one that would have fired thirteen times in
that file alone; `backlog/`, `log/` and `CHANGELOG.md` are exempt by path, being dated
records of this project's decisions, where naming the maintainer is correct. Verified by
planting a violation and watching the build refuse, as the clean-room pass established. And
on its first real run it caught the `docs/` copy that the second person's session never
reached — a check earning its keep inside a minute of existing.

**Three more findings.** A Workday board returned one posting among 125 carrying only
`bulletFields`, and `j["title"]` raised `KeyError`, so "unexpected response shape" marked
the whole company NOT SCANNED and threw away 124 usable postings — `#63`, fixed, skipping
and *counting* the unusable rows per `#44`, verified live. `#41`'s missing
`update-company` was hit inside the hour by a user who could not correct two stale careers
URLs and was told to go to the Django admin; independent confirmation from someone who did
not write the item, and it is retitled from "optional". And a scan run before `stocktake`
produces Ideal-Job Scores of ≤ 3 for everything, rendered in the same column shape as the
real scores — noise presented as measurement, caught only because the agent happened to
mention it twice. That is `#62`: the fix is honesty in the output, not better scoring.

**What it did not cover,** since the same honesty applies here: one person, one CV, one
afternoon, and a CV about a decade out of date. Nothing in it speaks to a CV in an unusual
shape, a job search outside the UK, or what someone does when they disagree with what the
toolkit suggests. The pass is closed. It is not exhausted.


## The history is not being rewritten — decided 2026-10-01

Stripping the results from `HEAD` does not remove them from the repository. `git log -p`
on either file still carries them, and anyone who cloned in the ten days or so since the
repo was cut has them on disk. **Michele's call: accept it as published, do not rewrite
history.**

Recording it because the alternative is attractive and wrong to reach for later. A
`filter-repo` pass plus a force-push would scrub the blobs, and it would also invalidate
every existing clone, break any commit hash referenced from `backlog/`, `log/` or the
changelog — which this project leans on heavily as its decision record — and still not
recall a copy anyone already has. Rewriting public history buys an incomplete fix at the
cost of the thing that makes this repo's own documentation checkable.

So the data stays in the history deliberately, not by oversight. **Nobody should propose a
rewrite on the strength of rediscovering this later**: the exposure is understood, the
decision was made by the person whose data it is, and the useful work — getting it out of
`HEAD`, and making the guard refuse the whole class so it cannot recur — is done.

The residual risk is worth stating plainly rather than filed away as closed: career
anchors and ranked personal values are psychometric data about a named individual, they
are in the public history of a repo that will be linked from a CV, and nothing above
changes that. What changes is that a reader of the current tree does not meet them, and a
second person running `stocktake` is no longer handed them as their own starting point.


## The example app, and a bug underneath it

Michele installed the example as a first-time user would, and reported that the charts
did not work. He was right, and the cause was one thing with many symptoms: **the example
had no status history.** Three applications, three `ApplicationStatusChange` rows, one
each, every one `"" -> current`, all stamped at the same second. Nothing had ever moved,
so every chart built on movement had nothing to draw — a Sankey with no status-to-status
ribbon at all, a post-applied view of one node to one node, a stock chart refusing to
render, an ageing list of one row.

Two of the five faults I had written into `#64` turned out to be wrong, and reading
`_fixture_rows.py` before changing it is what caught them. Application `#3`'s null company
and empty folder are deliberate and commented: the tabs test needs an application whose
sections are genuinely empty, and the null FK keeps three application-free companies for
the status tests. And `dbt Labs` showing `reviewing` while its application said `saved` is
correct — `Company.status` has its own vocabulary, in which both `saved` and `reviewing`
on an application mean `reviewing` on the company. Neither was a bug. Had I "fixed" either,
I would have broken working tests to satisfy a misreading.

The fix is a `history` list per application and a `walk()` helper that drives the real
transitions through the model, then backdates each one. That ordering matters: the
`from -> to` pairing is produced by the actual post-save signal rather than re-implemented
in the fixture, and only `changed_at` is set afterwards, which is exactly what that field
is a plain `DateTimeField` for — its own docstring says so, because the 2026-09-08 backfill
needed the same thing. The timestamps are deliberately off-midnight and one per day,
because `_status_stock` reads a midnight stamp as reconstructed rather than observed and
five changes in a day as a bulk logging session. A fixture dated at midnight would have
produced a chart that correctly refused to draw itself, which would have looked like the
original bug and had a different cause.

### The bug underneath

While checking the result, one chart reported an application as 0 days old when its last
recorded change was sixteen days earlier. The arithmetic was right; the data was wrong.
The database held 28 status changes where the dump file held 25.

`_application_saved` had no `raw` guard. `loaddata` saves an `Application` before its
`ApplicationStatusChange` rows, so the log looks empty, `_log_status_change` appends a
`(logged) -> <current status>` row stamped at load time, and the real rows then load
underneath it. **This is not an example-data problem.** The damage is to anyone restoring a
backup, and it is quiet in the worst direction: the invented row is the most *recent*
change, so every restored application reads as having moved today and the staleness
flagging stops working — the one feature whose whole job is to tell you what you have
forgotten. Nothing errors. The history is simply wrong, and wrong in the direction of
looking healthier than it is. `#65`, fixed with the guard Django provides for exactly this.

Third time this week the same shape: `#44` at the parser, `#61` at the interview, `#65` at
the fixture boundary. In each the output was well-formed and the content was not what it
should have been, and in each no check caught it because every check was asking whether
the thing parsed.

### Nine tests, and what they were actually asserting

The fixture change broke nine tests, and not one of them was testing what its name said.
`test_at_example_volume_the_history_charts_say_why_they_cannot_draw` asserted the charts
*could not* draw. `test_a_band_that_was_never_occupied_is_not_a_series` rested on the
example never having reached `interviewing`. `test_backward_edges_are_dropped_and_counted`
asserted `dropped == 1`, true only while the example contributed none of its own. Each was
borrowing the shipped example's poverty to supply its precondition for free.

**A test that does that is a test that forbids improving the example.** One of them even
said so in a comment — *"if the fixture grows past this, the example-tier assertions below
are the ones to revisit"* — which is an honest note and also an admission that the
fixture's thinness had become load-bearing. They now call `start_from_empty()` and state
the precondition rather than inheriting it, and the example-tier test is flipped to assert
the charts draw.

Verified the way the `#64` entry asked for and the way the old tests could not: by
rendering the pages. Eight status-to-status ribbons, five charts drawing, the backward-edge
note reading "1 of 17 transitions runs backwards and is not shown", three of five ageing
bands populated with one flagged stale, and none of the four "cannot draw" messages present
anywhere on `/stats/`.


## `#62`, and a check that was passing for the wrong reason

The last finding from the second-person pass. A scan on a fresh data root gives every
posting an Ideal-Job Score of three or less, because that column scores against
`criteria.yaml` and `init` leaves it a draft with no motivators. The scores render beside
the Area Scores in the same column shape, so they read as measurement. In the pass the
agent caught it and explained it twice unprompted — the system working by luck rather
than by design.

Fixed as honesty in the output rather than as better scoring, in four places so that it
does not depend on whoever drives the scan noticing: a readiness function in
`scan_config`, a banner above the tables in the report, a warning in
`scan_config.py --check`, and an instruction in `subcommands/scan.md` to say it as well
rather than relying on the banner. The banner names the thing a reader could not possibly
infer from a column of twos: the Strong-matches cut is on the *combined* score, so with
one half flat the bar is effectively Area Score plus a constant. The ordering within a
bucket survives; the position of the line does not. One half of the ranking being absent
is not a smaller version of the right answer.

`init` now says what skipping `stocktake` costs, in those terms rather than as a
suggestion to be thorough — a scan run now will sort the right roles into the wrong
buckets — with an explicit instruction in the skill not to soften it into "for best
results". Dealbreakers alone deliberately do not count as readiness: they can push a
score down, never establish that a role is wanted.

### The check that was passing for the wrong reason

Then `tools/smoke-test` failed: *"status did not report the 3 example applications"*. It
greps for a hardcoded `3 applications tracked`, and `#64` had taken the example to ten.

The part worth recording is not the stale literal, it is *when* it failed. **I reported
SMOKE PASS on the `#64` commit, and it was true and meaningless.** `smoke-test` runs
against a fresh clone, which contains only committed files — so running it before
committing tested the *previous* fixture, which still had three applications. The check
passed by describing a state the working tree had already left. One commit later, with
nothing else changed, it failed.

A hardcoded count in a test that reads from a clone does not merely go stale. It reports
PASS for the previous state of the thing it is checking, and it does so at exactly the
moment you are looking for reassurance that a change was safe. The count now comes from
the fixture file, so it cannot drift, and the comment says why rather than just what.

That is the same shape as the nine tests `#64` broke, one layer out: a check whose
precondition was supplied for free by something that was always going to change, in a way
that made the check agree with whatever that thing used to be.
