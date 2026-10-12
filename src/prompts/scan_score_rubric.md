You are screening job postings for a candidate, on three independent dimensions.

This is the canonical scoring rubric for the portal scan (see
`backlog/plans/001-drop-direct-anthropic-api.md` §2.3). The `scan` subcommand
(`.claude/skills/jobstudio/subcommands/scan.md`) reads this file as-is and substitutes
each bracketed value below with the real content from the sources named next to it.

Keep this file as the only place the rubric itself is defined — if the methodology
changes, it should only ever need to change here.

## Dimension 1 — Area Score: target-area alignment

Target profile: {area_name}
{description}

Emphasis points:
{emphasis}

Key terms: {key_terms}

Out of scope for this area:
{excludes}

(Source for the four fields above: the candidate's assigned `jobs/targets/<area>.yaml`
— `name`, `description`, `emphasis`, `key_terms`, `excludes`.)

`excludes` is the area's own anti-fit list, and it outranks every positive signal on
this dimension: a posting matching one of its entries scores **2 or below** on
`cv_score` however well the subject matter, key terms or seniority otherwise fit, and
the note must say which exclusion it hit. This is deliberately not the same thing as a
weak match — the postings it catches are usually a *strong* topical match and the wrong
shape of job, which is exactly the case a 1–5 fit score gets wrong on its own. It is
also per-area, unlike `hard_filters.exclude` in Dimension 2: a role shape can be right
for one positioning and wrong for another.

## Dimension 2 — "Ideal job" alignment

The candidate wrote these personal notes on what makes a job satisfying to them
(the nature/type of the role and day-to-day work, not their skills/CV):

{ideal_job_notes}

(Source: the full contents of `jobs/notes/search/ideal-job-notes.md`.)

Structured criteria from the candidate's career profile (`jobs/profile/criteria.yaml`):

{criteria_block}

(Source: `jobs/profile/criteria.yaml`, read and applied as follows —
- **Dealbreakers** (`hard_filters.exclude`) — pull `ideal_score` down hard (1–2), and
  the note must say so if a role clearly looks like one.
- **Salary floor** (`hard_filters.salary_floor_gbp`) — flag a stated range that tops
  out below it.
- **Leap sectors** (`preferences.sectors_open_to_with_a_leap`) — don't penalise an
  unfamiliar domain if it's one of these.
- **Sectors to avoid** (`preferences.avoid_sectors`) — a soft negative, not an
  auto-fail like the dealbreakers above.
- **Weighted motivators** (`weighted_motivators`) — pull `ideal_score` up,
  proportional to weight (1–5).
- **Culture traits** and **personal values** (`preferences.culture` /
  `preferences.values`) — soft nudges from what you know or can reasonably infer
  about the company's reputation/culture, not the JD text itself; say nothing if
  there's no real signal either way.
- **Bonus signals** (`bonus_signals`) — nudge `ideal_score` up if a posting clearly
  hits one, and say so in the note.
- **Soft negatives** (`soft_negatives`) — the mirror of bonus signals: nudge
  `ideal_score` *down* a point or two and name the reason in the note. These are real
  reservations, not dealbreakers, so never score one down to 1–2 the way a dealbreaker
  is scored, and never let one keep a strong role out of the report.
If `jobs/profile/criteria.yaml` doesn't exist, skip this structured half and score
Dimension 2 from the personal notes alone.)

## Dimension 3 — Location

The candidate is UK-based and only wants a UK-based role or a fully (100%) remote role.
Classify each posting's location into exactly one category:
- "uk": role is based in the UK (or the UK is one of the listed locations)
- "remote": fully/globally remote, not restricted to a non-UK region or country
- "other": anything else — non-UK on-site/hybrid, or remote restricted to a non-UK
  region/country (e.g. "remote - US only"), or an unspecified/ambiguous multi-location
  listing with no confirmed UK option

## Candidate postings to evaluate (JSON list of id/company/title/tracked-role-target/location)

{postings}

(Source: the plausible candidates for this area/batch, from the mechanical scan's
candidates file.)

Some postings come from searching a general job board rather than from a tracked company
— they carry a `source` (the board), an empty `role_target`, and in its place the board's
`snippet` of the description and, where advertised, a `salary`. Judge those from the title,
snippet and salary together. `agency: true` means the advertiser looks like a recruitment
agency and the company named is not the employer: score the role, not the agency, and
say in the note when the snippet leaves the employer's sector unclear.

For each posting return:
- "cv_score": 1 (poor) to 5 (excellent) fit against Dimension 1 — the target profile.
  Score this purely on role/domain/seniority fit, ignore location entirely here.
- "ideal_score": 1 (poor) to 5 (excellent) fit against Dimension 2 — the personal notes
  AND the structured criteria above (day-to-day nature of the work: hands-on building vs
  pure management, customer-facing vs backstage, autonomy/ownership, etc.; weighted
  motivators pull it up, dealbreakers pull it down) — judge from the title/role_target,
  you don't have the full job description.
- "location_category": one of "uk" / "remote" / "other", per the rule above.
- "notes": one compact sentence covering both scores' reasoning (not location — that's
  its own field). If the posting looks like it hits a dealbreaker, or clearly hits a
  bonus signal, or the salary looks below floor, say so here.

Write these four fields directly onto each candidate object in the scored file.
