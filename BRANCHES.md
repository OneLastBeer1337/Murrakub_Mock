# Branch status — read this before merging anything

**As of 3 September 2026.** Two branches are live and they have diverged. Neither is wrong;
they were worked on in parallel without coordination, and about half the work is duplicated.
This page exists so that whoever does the merge understands what they are looking at before
they start.

```
                    6e122ed  "Correct F18"          <- common ancestor
                       |
        +--------------+---------------+
        |                              |
     main (+13)                   mickie (+17)
     optimizer audit,             subset-move, C3 arm,
     closed loop,                 T3 sweep, benchmarks,
     statistical audit            M1 slides, PROGRESS.md
```

Neither branch is merged into the other. **Do not merge without reading the collisions
section.**

---

## What is on each branch

### `mickie` — Arno125456, NipitponPakmaruek, NipponPa

Unique to this branch:

| file | what it is |
|---|---|
| `PROGRESS.md` | Their tracking document, findings F1–F22 |
| `docs/M1_Proposal_Presentation_Slides.md` | Slides and defence script for the milestone |
| `docs/chapter3_benchmark_results.md` | Benchmark tables for Chapter 3 |
| `docs/T0_Formulation_Ratification_Briefing.md` | T0 briefing |
| `docs/pipeline.md` | — |
| `poc/tracks/track_a_subset.py`, `track_a_m1_subset.py` | Subset-move neighbourhood, fused with the M1 lookahead |
| `poc/tracks/track_b_c3.py` | The (C3) budget-relaxation arm |
| `pytest.ini`, `scripts/generate_chapter3_tables.py` | Build and reporting infrastructure |

Also: Track B duality-gap early stopping, and `track_a_m1.py` reconciled against Cheng &
Nguyen (2026, Paper P3).

### `main`

Unique to this branch:

| file | what it is |
|---|---|
| `docs/D11_poc_report.md` | The PoC report, written for the advisor |
| `docs/study_guide.md` | Nine-step guide to being able to defend each choice |
| `docs/component_reference.md` | Per-component behaviour and what each must become |
| `docs/proposal_narrative.md` | What the contribution is and why the optimizer serves it |
| `docs/T0_briefing.md` | T0 briefing |
| `prototype/` — `ingestion.py`, `simulator.py`, `loop.py` | The closed loop, J1→J9, run end to end |
| `poc/tracks/track_b_capacity.py` | The (C2) relaxation arm |
| `poc/tracks/track_b_budget.py`, `track_a_relocate.py`, `core/relocate.py` | (C3) arm, single-move relocate |

Also: solver time limits with proven-optimality reporting, and the statistical audit
(F26/F27).

---

## The collisions — resolve these deliberately

### 1. Finding numbers clash

| | `mickie` | `main` |
|---|---|---|
| **F20** | Subset-move consolidation resolves the aggregate-coupling trap | The closed loop abandons good profiles it can never win back |

`mickie` runs F1–F22 and is referenced from their slides. `main` runs F1–F27.

**Suggested resolution: renumber `main`'s findings**, because the slides and `PROGRESS.md`
already cite the other numbering and changing a presentation is riskier than changing a log.

### 2. The same work exists twice

| purpose | `mickie` | `main` |
|---|---|---|
| (C3) relaxation arm | `track_b_c3.py` | `track_b_budget.py` |
| Multi-move neighbourhood | `track_a_subset.py`, `track_a_m1_subset.py` | `core/consolidation.py`, `core/relocate.py` |
| T0 briefing | `T0_Formulation_Ratification_Briefing.md` | `T0_briefing.md` |
| T3 sweep above the reference | commit `ee44f68` | finding F24 |

**Suggested resolution: keep `mickie`'s implementations.** Nipitpon and Nippon have to defend
that code at the viva, and `track_a_m1_subset` — fusing the feasibility lookahead with a
subset move — is a genuine advance on `main`'s two separate passes. `main`'s versions become
evidence that the alternative was measured, not the shipped implementation.

### 3. Files both branches modified

These will conflict textually and need manual resolution:

```
README.md
docs/evidence/poc_findings.md
docs/evidence/poc_findings_summary.md
poc/harness/runner.py
poc/tests/test_track_b.py
```

`runner.py` is the important one — both sides registered new conditions in `STRATEGIES`, so
the merged registry needs every condition from both, with no duplicates.

---

## One thing that applies to `mickie`'s numbers too

`main` found a systemic statistical defect after `mickie` branched (F26, F27): **several
headline claims were computed as a ratio of means**, which is not a typical ratio when either
distribution has a tail. Three separate claims broke:

| claim | ratio of means | median per-instance |
|---|---|---|
| Track C vs exact solver, speed | 116× | **5×** |
| Lagrangian vs LP bound, uniform | 7.51× | **2.53×** |
| Lagrangian vs LP bound, structured | 3.80× | **2.00×** |

**`docs/chapter3_benchmark_results.md` and the M1 slides were generated before this was
found.** If either quotes a speedup or a "× tighter" figure, it should be recomputed as a
paired per-instance difference with a confidence interval before it is presented.

The rule adopted on `main`: **never divide two means.** Report the paired difference and its
interval, or the median of per-instance ratios.

---

## docs/ was reorganised on `main`, 5 September

Flat `docs/` became purpose folders. Nothing was renamed and nothing was deleted - only moved,
with `git mv`, so history follows. Every cross-reference in every `.md`, `.py` and `.html` file
was rewritten to match, and the link check passes.

| was | is now |
|---|---|
| `docs/System_Architecture_v2.md` | `docs/design/System_Architecture_v2.md` |
| `docs/component_reference.md` | `docs/design/component_reference.md` |
| `docs/pipeline.md` | `docs/design/pipeline.md` |
| `docs/poc_findings.md` | `docs/evidence/poc_findings.md` |
| `docs/poc_findings_summary.md` | `docs/evidence/poc_findings_summary.md` |
| `docs/chapter3_benchmark_results.md` | `docs/evidence/chapter3_benchmark_results.md` |
| `docs/PoC_and_Validation_Plan.md` | `docs/proposal/PoC_and_Validation_Plan.md` |
| `docs/proposal_narrative.md` | `docs/proposal/proposal_narrative.md` |
| `docs/D11_poc_report.md` | `docs/proposal/D11_poc_report.md` |
| `docs/M1_Proposal_Presentation_Slides.md` | `docs/proposal/M1_Proposal_Presentation_Slides.md` |
| `docs/T0_briefing.md` | `docs/sessions/T0_briefing.md` |
| `docs/T0_Formulation_Ratification_Briefing.md` | `docs/sessions/T0_Formulation_Ratification_Briefing.md` |
| `docs/study_guide.md` | `docs/sessions/study_guide.md` |

**If you are merging a branch that edits any of these**, git's rename detection should follow
the move on its own. Five of them are edited on both sides - `poc_findings.md`,
`poc_findings_summary.md`, `proposal_narrative.md`, `chapter3_benchmark_results.md` and
`M1_Proposal_Presentation_Slides.md` - so expect rename/modify conflicts there and resolve
against the new path. The rest are additions on one side only.

---

## Suggested merge order

1. Agree the finding renumbering, so both logs can be concatenated without collision.
2. Agree which duplicate implementation ships.
3. Merge, resolving the five files above by hand.
4. Re-check any ratio in the slides and benchmark tables against the F27 rule.
5. **Then** reorganise the documentation tree — not before, because moving files now would
   turn a five-file merge into an unreviewable one.
