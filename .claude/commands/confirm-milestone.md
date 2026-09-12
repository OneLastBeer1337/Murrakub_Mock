---
description: Mark the current milestone done in PROGRESS.md after Arno confirms the execution checkpoint. Does not auto-start the next milestone.
---

Read `PROGRESS.md`. The current milestone must be `execution review pending` for this command
to apply — if it isn't, stop and say so.

Update the row's status to `done`. Do not change any other row's status, and do not begin
design or implementation work on the next milestone in this same turn — Arno starts the next
milestone explicitly (via `/design`) in a separate message.

If this milestone surfaced any gap or improvement relevant to Arno's senior-project comparison
(capacity model, HEFT/precedence, or anything new), confirm with Arno whether it should be
added to his `architecture-decisions.md` memory file now, and add a one-line pointer to it in
PROGRESS.md's "Gaps/improvements found so far" section.
