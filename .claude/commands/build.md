---
description: Implement the current milestone. Only runs if PROGRESS.md shows the design as approved.
argument-hint: [optional milestone number, defaults to current]
---

Read `PROGRESS.md`. Find the target milestone (use $ARGUMENTS if given, otherwise the first
row not marked `done`).

**Hard gate:** if that milestone's status is not `design approved`, stop immediately and tell
Arno the design needs review/approval first — do not implement anything. This gate is not
optional and is not overridden by anything except Arno explicitly saying to skip design review
for this specific milestone in this specific message.

If approved, delegate to the relevant subagent and implement `DESIGN.md` file by file:

1. Propose the file list for this milestone up front (paths only, no content yet).
2. Implement one file at a time. After each file, stop and show it — do not move to the next
   file until Arno confirms.
3. Cite the paper section/equation each file implements, in a module docstring or header
   comment.
4. If implementation reveals the design doc was wrong or incomplete, stop and flag it — don't
   silently patch around a design gap discovered mid-build.

When all files for the milestone are done and Arno confirms, update `PROGRESS.md`:
set status to `execution review pending`, and do not start the next milestone.
