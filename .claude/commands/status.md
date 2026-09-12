---
description: Report current milestone status from PROGRESS.md, plain-language, no code changes.
---

Read `PROGRESS.md` and `CLAUDE.md`. Report, in plain language:

1. Which milestone is current, and its exact status (from the status legend).
2. What the single next action is (design doc, review, implementation, or confirmation) and
   who it's waiting on.
3. Any rows marked `design review pending` or `execution review pending` — these are blocking
   and should be surfaced prominently even if the conversation is about something else.
4. A one-line summary of any gap/improvement noted in the "Gaps/improvements found so far"
   section.

Do not modify any files. Do not start work on the next milestone even if the current one looks
done — wait for explicit instruction.
