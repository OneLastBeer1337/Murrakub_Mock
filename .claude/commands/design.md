---
description: Produce (or revise) the design doc for the current milestone. Never writes implementation code.
argument-hint: [optional milestone number, defaults to current]
---

Read `PROGRESS.md` to find the target milestone (use $ARGUMENTS if a number is given,
otherwise the first row not marked `done`). Delegate to the relevant subagent
(orchestrator-builder, profiler-builder, optimizer-builder, execution-builder, or
executor-lib-builder — pick based on which phase/folder the milestone belongs to).

The subagent must:
1. Write or revise `DESIGN.md` in the relevant phase folder (`/development`, `/optimization`,
   or `/execution`).
2. Explain the design in plain language first — what it does and why — before any schemas,
   pseudocode, or equations.
3. Cite the specific paper section(s)/equation(s)/table(s) being implemented.
4. Explicitly call out any ambiguity in the paper or any place the design deviates from a
   literal reading (and why), rather than silently resolving it.
5. Explicitly flag anything relevant to Arno's known critiques (capacity model, HEFT/
   precedence mismatch) if the milestone touches them.
6. Stop after the design doc is written. Do NOT write implementation code in this command.

Update `PROGRESS.md`'s status for this milestone to `design review pending` when done.
