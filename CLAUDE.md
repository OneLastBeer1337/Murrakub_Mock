# Murakkab Reproduction — Project Instructions

## What this project is

A from-scratch, faithful reproduction of the architecture described in:

> Chaudhry, Choukse, Qiu, Goiri, Fonseca, Belay, Bianchini. "Murakkab: Resource-Efficient
> Agentic Workflow Orchestration in Cloud Platforms." OSDI 2026.

There is no source code release for Murakkab — only the paper. "Recreate" means: build an
original implementation that realizes the components, interfaces, and algorithms the paper
*describes* (declarative spec, orchestrator, profiling, MILP optimizer, auto-scaler,
multi-tenant execution), not a copy of code that doesn't exist.

**This is not a standalone exercise.** It is the baseline comparison system for Arno's KMUTT
senior project (a profile-guided multi-workflow LLM resource orchestration platform with its
own Track A / Track B architecture). The point of building this faithfully is to surface and
measure concrete design gaps in Murakkab — starting from ones already identified:

- Capacity model: Murakkab's per-task slot consumption vs. the correct instance-based
  provisioning model (per Murakkab Appendix A.5) — reproduce Murakkab's actual formulation
  exactly here, even if it's the "wrong" one, so the gap is demonstrable.
- HEFT/precedence mismatch: neither Murakkab's nor the comparison formulation has precedence
  constraints or a makespan term, which affects how the DAG scheduling should be reproduced.

Any gap found during this build goes into
`/projects/01a041e5-c75a-7486-9e10-80b7fe31f0d8/architecture-decisions.md` (Arno's memory
file, not a file in this repo) — flag it in the session rather than silently working around it.

## Non-goals right now

- No GPUs. All model/hardware profiles are mocked (see `PROFILES.md` once it exists),
  sourced from the paper's own reported numbers (Tables 4–6, Figures 2–4) where available,
  interpolated/extrapolated elsewhere. Never invent numbers that contradict a paper-reported
  figure — flag the gap instead of quietly extrapolating past what's defensible.
- No Gurobi. Use an open-source MILP solver (PuLP, OR-Tools, or CBC) implementing the exact
  same formulation as Murakkab's Appendix A.5.
- No real orchestrator LLM yet. Build the orchestrator against an abstract LLM-client
  interface (see `orchestrator/llm_client.py` once it exists) with a mock implementation for
  now. The concrete provider (a Chinese model, TBD) is decided later — do not hardcode one.
- Code Generation (paper Figure 1b / 2b) **and Video Q/A (Figure 1a / Listing 2)**. Video Q/A was
  un-deferred on 2026-09-10 for two reasons: M5's multiplexing needs 2+ workflows to reproduce
  Table 2's gain, and Code Generation is a total order with no parallel branch on which to
  demonstrate the HEFT/precedence gap. Math Q/A and the custom OS-log-analysis workflow remain
  explicitly deferred — do not build ahead into them.
- Multiplexing (Mkb Opt+Mult, μ_m in the capacity constraint) IS in scope from the start —
  this is not deferred, unlike the other workflows.

## Repo structure

Mirrors the paper's Section 3.1 life-cycle phases, not a generic package-by-concern layout:

```
/development/     # Declarative spec, Executor Library, Workflow Orchestrator (Section 3.2)
/optimization/    # Workflow & Model Profiles, MILP Optimizer (Section 3.3)
/execution/       # Registry, Auto-Scaler, runtime dispatch (Section 3.4)
/shared/          # Types/interfaces shared across phases (DAG, Executor, Profile dataclasses)
/tests/
PROGRESS.md       # Milestone tracker — read this first every session
```

## How to work in this project (Arno's conventions)

- **Plain language before technical depth.** Explain what a component does and why before
  showing code or equations. Confirm understanding before moving to the next step.
- **Design review, then execution — two separate checkpoints per milestone.** Never write
  implementation code for a milestone until Arno has explicitly approved the design for that
  milestone. When a milestone starts, produce a design document first and stop.
- **File-by-file with confirmation.** When a change touches multiple files, go one file at a
  time and confirm before moving to the next, rather than dumping a large multi-file diff.
- **Push back, don't over-specify.** If something is ambiguous, ask rather than assuming — but
  don't ask about things a reasonable default handles; save questions for real forks.
- **Adversarial review mode on architecture decisions.** When Arno proposes or approves a
  design, treat it as a first draft to stress-test (edge cases, contradictions with the paper,
  hidden assumptions) rather than accepting it at face value — this is expected, not rude.
- **Cite the paper section/equation** for any component you build, so fidelity is traceable
  (e.g. "this implements Section 3.3.1, Constraint 3 — capacity with multiplexing").

## Milestone process

1. Read `PROGRESS.md`.
2. If the current milestone has no design doc yet, write one (in `/development`,
   `/optimization`, or `/execution` as a `DESIGN.md` alongside the code-to-be) and stop for
   review. Do not write implementation code in this step.
3. Once Arno approves the design, implement it, file by file, confirming each.
4. Once implemented and Arno confirms the execution checkpoint, update `PROGRESS.md` and stop.
   Do not auto-start the next milestone.

## Current milestone

**Milestone 1:** Declarative workflow specification (paper Listing 1/2 equivalent — sub-tasks
+ data flow, no config) for the Code Generation workflow, plus the Workflow Orchestrator
(Section 3.2) that maps tasks to executors from a mocked Executor Library via the abstract
LLM-client interface. Status and next action are tracked in `PROGRESS.md`.
