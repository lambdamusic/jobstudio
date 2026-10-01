# Monzo — Data Platform Engineer · Hiring manager

**Date:** 2026-08-27 · **With:** Engineering manager, Data Platform · **Format:** 60 min video

## Questions and answers

- **Q:** Tell me about a pipeline you made faster, and how you knew it was faster.
  **A:** The six-hours-to-35-minutes story, with the detail that the win was partitioning
  plus dropping two redundant joins, not more compute. Framed the measurement first: there
  was no SLO before, so step one was agreeing what "late" meant with the analysts.

- **Q:** How do you decide a schema is wrong?
  **A:** When consumers start working around it — three teams writing the same CASE
  statement is a schema bug, not an analyst problem. Offered the data-contract version
  of the answer and said we had not got as far as enforcing them.

- **Q:** You have written and spoken a fair amount. Where does that fit here?
  **A:** Honest answer: it does not, much, unless the DX bullet is real. Said I would
  rather know now than discover it in six months.

- **Q:** What would you want to change in your first quarter?
  **A:** Nothing structural — read the event schemas and find out which pipelines the
  analysts distrust, because that list is the real backlog.

## What to do differently

- The advocacy answer landed better than expected; being direct about it was right.
- Still have no clear answer on who owns DX. Asked, and got "it is shared", which
  usually means nobody. Worth one more push in round 3.
- Asked nothing about the team's on-call load. Ask.
