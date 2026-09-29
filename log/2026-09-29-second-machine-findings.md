# The first install on a second machine

*2026-09-29. `main` fast-forwarded to `dev` (`aeea38e`) and cloned onto a different Mac,
then set up from zero against a CV the toolkit had never seen. This is `#2`'s last
outstanding piece — M1.8's "a second real person" — and, incidentally, the `cv --import`
half of `#23`, which had never been run for real either.*

The install itself was clean. Virtualenv, data root, wiring, `config.py --chain`,
pre-push hook, admin account: every step worked as written, first time, exactly as the
clean-room pass predicted. What the clean room could not predict was everything that
happens *after* the install, because it had no CV to import and no one to hand the
result to. That is where all seven findings are.

## The one that matters

**The shipped example CV is written in a format the parser cannot read.**

`_parse_career_history()` (`src/render.py:280`) reads `### Employer`, then an optional
`*Years*` line, then `- Role — *dates*` bullets. `references/cv-base-format.md:82`
documents exactly that, correctly, in detail. But `example-data`'s functional CV writes
its roles as `**Role** | dates | location`, which matches no branch of the parser and is
dropped without a word. Parsed today, the shipped example yields three employers, zero
roles, zero dates.

That matters more than a wrong example file usually would, because of who reads it. The
session on the second machine did the right thing — it read the shipped example to
infer house style before writing anything, reasoning explicitly that the example was
"known-good" because it ships and therefore must render. It then produced a CV in that
style, rendered it, and found the dates missing. It read the parser, corrected the
format, and hit the same class of failure again on the chronological file. Most of the
import was spent recovering from a file we ship as the reference.

Three things had to be true at once for this to survive:

- the example disagrees with the documented contract, and the docs are the one that's right;
- the parser discards what it cannot match, so a wrong format looks like an empty career;
- nothing checks. No test anywhere calls `parse_functional` or `_parse_career_history` —
  233 tests, zero coverage of the component whose failure mode is silence. `smoke-test`
  renders the functional CV and asserts it is 39103 bytes, which a hollow CV also is.

The fix is all three (`#44`), not the example file alone. A correct example with a silent
parser and a byte-count assertion is the same trap rearmed.

## The rest

**`/cvs/` was empty after a successful import** (`#45`). The page lists `BaseCv` rows, and
`init` creates them by running `import_jobs` at the end of its own run — before on-ramp B
has written any base CV. So the rows never existed, and nothing said so. `scan_report.py`
already solved this for scans by refreshing itself; the CV and area write sites didn't
get the same treatment.

**HTML and PDF are still the default CV outputs** (`#46`), with `.docx` opt-in behind a
flag — backwards, and noticed immediately as "a whole bunch of HTML files, I'm not sure
why". Cover letters flipped to `.docx`-only back in `#37`; CVs never followed.

**Header links are assumed** (`#47`). A CV with no LinkedIn, Scholar, GitHub or site
reads as incomplete rather than as a normal case, because the format, the example and the
import questions all treat their presence as the default.

**`init` asks before it explains** (`#48`) — the data root, the on-ramp and the virtualenv
are all decided before the user has been told what `init` does or which answers are
expensive to change. And the identity questions want free text, which `AskUserQuestion`
cannot express; it errored and the session fell back to asking in prose.

**Nothing says `init` is load-bearing** (`#49`). What it captures drives every tailored CV
and every scan score afterwards, and a thin answer degrades all of it invisibly.

**The docs mix the two layers** (`#50`). Claude commands and `tools/py src/...` sit side by
side, so it isn't clear which one a reader is meant to type — in a toolkit whose whole
premise is that you drive it through Claude. `#51` is the same gap in the web app, which
shows the job search but never how to work it.

One new platform for `#10`: **Pinpoint**, which turned out to be the board behind the
highest-rated company in that tracker — so of the three unbuilt fetchers it's the one
with someone actually waiting on it.

## What to take from it

The clean-room pass verified the install and found nothing, and that was a true result —
the install is genuinely fine. But "can a stranger install it" and "can a stranger use
it" turn out to share almost no surface. Every finding here is downstream of the last
step the clean room could reach.

The parser bug is the sharper lesson. It had been shipping in the example data for as
long as the example data has existed, in a repo with a green test suite and a passing
smoke test, and the thing that finally surfaced it was someone with a different CV. A
component that fails by producing plausible empty output needs a test that reads the
output, not one that weighs it.
