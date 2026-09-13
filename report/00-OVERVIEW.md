# Murakkab: Reproduction Report

**A from-scratch reproduction of "Murakkab: Resource-Efficient Agentic Workflow Orchestration in
Cloud Platforms" (OSDI 2026), and what building it taught us about the paper.**

Prepared 2026-09-13. All paper claims in this report were re-verified against the source PDF
(`osdi26-chaudhry.pdf`) on that date, not recalled from earlier sessions.

---

## What this report is

There is no source release for Murakkab. There is only the paper. So "reproducing" it meant
building an original implementation of the components, interfaces and algorithms the paper
*describes* — a declarative specification layer, a workflow orchestrator, a profiling system, a
MILP optimizer, an auto-scaler, and a multi-tenant runtime — and then seeing which of the paper's
claims survive contact with a working implementation.

The result is roughly 8,500 lines of implementation and 570 tests, covering all three of
Murakkab's life-cycle phases. More importantly, it produced a set of findings that are only
visible from the inside: things that look fine on the page and stop working when you try to run
them.

This report has four parts, written to be read in order but usable separately.

| File | What it covers |
|---|---|
| [`01-WHAT-MURAKKAB-DOES.md`](01-WHAT-MURAKKAB-DOES.md) | The paper's actual design, phase by phase and component by component. No critique — just what it says. |
| [`02A-DIRECT-FIDELITY-MAP.md`](02A-DIRECT-FIDELITY-MAP.md) | Start here for a direct, component-by-component comparison of the paper-described system and this repository, with the next evidence pairs to build. |
| [`02-REPRODUCTION-FIDELITY.md`](02-REPRODUCTION-FIDELITY.md) | Where our implementation matches, where it deliberately differs, where it was forced to differ, and the bugs we made. |
| [`03-FINDINGS.md`](03-FINDINGS.md) | What implementing it revealed. Five major findings, each with the measurement behind it. |
| [`04-IMPROVEMENTS.md`](04-IMPROVEMENTS.md) | Ten improvements, each traceable to a sentence in the paper that the formulation fails to encode. |
| [`05-SLIDE-CONTENT-RESEARCH-DIRECTION.md`](05-SLIDE-CONTENT-RESEARCH-DIRECTION.md) | Discussion-ready slide content: fidelity questions, open methods, improvement candidates across scenarios, and an undecided project focus. |
| [`06-TOPIC-2-PAPER-CONFIRMATIONS.md`](06-TOPIC-2-PAPER-CONFIRMATIONS.md) | One-by-one checks of topic 2 claims against the OSDI paper, with presentation relevance left for discussion. |

---

## The one-paragraph summary

Murakkab's central idea is sound and, in our reading, genuinely novel: take configuration away
from workflow developers, give the cloud platform visibility into workflow internals, and let a
periodic optimizer choose models, hardware and parallelism against an SLO. The implementation
confirms that the *architecture* works — the three phases compose, the registry hands off cleanly,
and the MILP solves in well under a second on an open-source solver.

What does not survive is the **formulation in Appendix A.5**. It is systematically narrower than
the system the paper's own prose and evaluation describe. Six specific capabilities are described
in Sections 2–4 and cannot be expressed in the appendix at all. And the paper's headline
multiplexing result — a 21.6% GPU reduction — turns out to enter the model entirely through a
coefficient that is defined in one clause, quantified nowhere, and which we could only obtain by
fitting it to the very number it is supposed to produce.

---

## The five findings, in one table

| # | Finding | Evidence |
|---|---|---|
| **1** | **A.5's structure produces zero multiplexing gain.** Sharing model instances across workflows saves exactly 0.00%. The entire reported 21.6% enters through the undefined `μ_m`. | Measured: 418 → 418 GPUs at μ=1; 326 at μ=0.784 |
| **2** | **eq. (5)'s blind spot is worth 0.3% or 69%**, depending entirely on token count. A single claim about "Murakkab's latency model" is too coarse to be useful. | Code Gen 0.24%; Video Q/A 69% (robust across ±3× band) |
| **3** | **The auto-scaler cannot do what §3.4 claims.** It monitors on a 60-second window; §4.7 assumes provisioning takes 20 minutes. | 81.5% violations with the paper's delay vs 36.5% without |
| **4** | **The appendix is narrower than the paper.** Six capabilities are described in prose and evaluated in §4, and cannot be written in A.5. | Verbatim quotes, Part 3 §4 |
| **5** | **The `c`/`m` decoupling is exploited, not latent.** 100% of allocated mass routed a video configuration onto a text-only model. | Measured under `baseline` |

---

## How to read the numbers in this report

Three levels of confidence, and they are not interchangeable:

**Structural claims are robust.** "Eq. (3) is linear, therefore pooling demand can only save
integrality rounding" follows from the algebra and would hold on real hardware. So does "A.5 has
no index for per-node executor assignment." These are the claims worth citing.

**Measured ratios are directionally sound, with bands.** The 69% blind spot, the 81.5% violation
rate, the 22.01% μ contribution. These come from reconstructed profiles digitized from the paper's
own figures, and each carries an uncertainty band. Where a conclusion depends on an invented
number, we tested it across the full band and say so.

**Absolute magnitudes are not reproductions of the paper's numbers.** We have no GPUs. Every
latency comes from eq. (5) evaluated on digitized curves; every energy figure comes from Table 3
per GPU type. Roughly 14% of the values the optimizer needs are recorded as `Unavailable` because
the paper does not report them — never guessed, never imputed.

One more caveat that applies everywhere: **the reproduction has not been validated against Tables
1–6 or Figures 7–14.** Everything has been checked for internal consistency and against the
paper's *structure*; nothing has been checked against its *reported results*. That remains the
last thing that could invalidate any finding here.

---

## Corrections to earlier drafts

Honesty about our own errors is part of the method, so they are listed rather than silently fixed.
Three claims made during development turned out to be wrong on re-verification:

1. **§4.6's "near-perfect parallel" is about two composed workflows**, not Video Q/A's internal
   `frame_extract ∥ stt` branch. The intra-workflow fan-out is real (it is in Listing 2), but that
   sentence is not evidence for it.
2. **Latency-tier runs DO have a quality floor.** §4.3 states it verbatim. Our claim that they had
   none described A.5's silence, not Murakkab's behaviour.
3. **The "separate" arm of the multiplexing comparison was not separate enough.** Re-measured per
   §4.1's own definition; the result was unchanged.

Details in [`02-REPRODUCTION-FIDELITY.md`](02-REPRODUCTION-FIDELITY.md), Part 4.
