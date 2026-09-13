<<<<<<< HEAD
# Murakkab Reproduction — How to Use This With Claude Code

## Setup

1. Unzip this into a folder, `cd` into it, run `claude` (or open it in Claude Code / Claude
   Desktop's Code tab).
2. Claude Code auto-reads `CLAUDE.md` and `PROGRESS.md` at session start — you don't need to
   paste anything.

## Day-to-day commands

- `/status` — see where things stand. Safe to run anytime, makes no changes.
- `/design` — produces (or revises) the design doc for the current milestone. Never writes code.
  Read it, push back, ask it to revise, repeat until you're happy.
- `/build` — implements the current milestone, but only if `PROGRESS.md` shows the design as
  `design approved`. You need to manually flip that status (or tell Claude "approved, mark
  Milestone 1 as design approved") after reviewing `/design`'s output.
- `/confirm-milestone` — once `/build` finishes and you've reviewed the code, run this to mark
  the milestone `done` and stop. It will NOT auto-start the next milestone — that's deliberate.

## The gate, explicitly

`/build` refuses to run unless `PROGRESS.md` says `design approved`. This is intentional
friction: it forces you to actually read and approve the design before code gets written,
per your own working style (design review, then execution, as two separate checkpoints).

If you ever want to skip this for a specific milestone, you have to say so explicitly in the
message — the command file (`.claude/commands/build.md`) does not have a silent bypass.

## Resuming after a break / hitting a usage limit

Just start a new session in the same folder and run `/status`. `PROGRESS.md` is the single
source of truth for where things left off — nothing is tracked only in conversation memory.

## Subagents (you don't call these directly — commands delegate to them)

| Subagent | Owns |
|---|---|
| `orchestrator-builder` | `/development/` — declarative spec, Workflow Orchestrator |
| `executor-lib-builder` | `/development/executor_lib/` — mocked models/tools/compositions |
| `profiler-builder` | `/optimization/profiles/` — Workflow & Model Profiles |
| `optimizer-builder` | `/optimization/milp/` — MILP formulation, Appendix A.5 |
| `execution-builder` | `/execution/` — Registry, Auto-Scaler, dispatch |

Each has the full paper-fidelity requirements and Arno's known critiques baked into its
instructions, so it won't quietly "fix" Murakkab's design while reproducing it.

## Where gaps/improvements go

Anything a subagent flags as a design gap gets raised in-conversation and, once you confirm
it's real, added to your `architecture-decisions.md` (outside this repo, in your memory
files) — `/confirm-milestone` will prompt for this at each milestone boundary.
=======
# Murrakub_Mockup
>>>>>>> 57e06bfd0a6d55401f50a372d136d24071f3020b
