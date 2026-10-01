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
