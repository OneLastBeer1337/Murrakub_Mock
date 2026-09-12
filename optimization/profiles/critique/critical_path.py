"""
Makespan over the DAG vs Appendix A.5's eq. (5) -- DESIGN.md Section 12.1.

**QUARANTINED.** This module imports `tool_latency`, whose every number is `INVENTED`.
`tests/test_milp_boundary.py` asserts that nothing reachable from `ProfileSet.to_milp_inputs()`
reaches either module, so no value computed here can enter a constraint or an objective.

WHAT IS BEING COMPARED, AND WHY IT IS NOT A NUMERIC CLAIM
---------------------------------------------------------

Appendix A.5's latency filter (p.586) is

    l^TTFT_m + t_c * l^TPOT_m  <=  tau_{w,s}

One executor `m`, one token total `t_c`, no sum over sub-tasks and no max over paths. It is a
*per-executor* expression that A.5 applies to a *whole workflow*.

A profile-driven critical path over Video Q/A's DAG (Listing 2, p.572) is

    L_scene + max(L_frames, L_stt) + L_qa

The gap between them is not an approximation error that a better constant would close. Three
terms in the second expression have NO COUNTERPART AT ALL in the first:

  * `L_scene`, `L_frames`, `L_stt` -- TOOL stages. Section 3.3 (p.573) profiles "TTFT and TPOT
    for LLMs"; OpenCV, OmDet/CLIP and Whisper have no profile, generate no tokens, and so
    contribute exactly zero to `t_c` (A59, `workflow_profiles._zero_tokens`). eq. (5) charges
    them nothing.
  * the `max(...)` -- the fan-out/fan-in that Section 4.6 (p.578) MEASURES: "The two sub-tasks
    run in near-perfect parallel, with full overlap in execution". A.5 has no precedence
    relation to express either the overlap or the serialization it replaces.
  * the `+` chain -- precedence. `q_a` cannot start before its predecessors finish. A.5 has no
    term that says so.

So the finding here is STRUCTURAL: `eq5_terms()` and `critical_path_terms()` return the term
lists, and `TermGap` reports which terms one model can represent and the other cannot. The
magnitudes below exist only to make that plottable, and `Comparison.caption` stamps every figure
`[INVENTED]` accordingly.

WHY CODE GENERATION IS ABSENT (A59)
-----------------------------------

It cannot be computed, and the reason is worth stating rather than hiding. Its DAG is a TOTAL
ORDER -- `propose_solutions -> write_tests -> execute_tests -> rank_solutions` -- so there is no
parallel branch to demonstrate the `max(...)` gap on. Worse, three of its four nodes are LLMs
sharing one published per-request token total with no reported split, so `node_tokens` is
`Unavailable` for each (A59) and the per-node `L` terms do not exist even in principle. The
precedence gap is still real for Code Generation; it is simply not QUANTIFIABLE here, and
Section 12.1's Video Q/A case is the one that carries the argument.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Mapping, Sequence

from optimization.profiles.critique.tool_latency import INVENTED_CITE, TOOL_SERVICE_TIMES
from optimization.profiles.enumerate_cw import enumerate_video_qa
from optimization.profiles.model_profiles import build_model_profiles
from optimization.profiles.provenance import Measured, Unavailable
from optimization.profiles.schema import (
    ConfigKey,
    ModelProfile,
    ModelProfileKey,
    OperatingPointPolicy,
    WorkflowProfile,
)
from optimization.profiles.workflow_profiles import build_video_profiles

CAPTION_PREFIX: Final[str] = "[INVENTED tool service times -- structural comparison only]"

EQ5_TERMS: Final[tuple[str, ...]] = ("l^TTFT_m", "t_c * l^TPOT_m")
"""Every term Appendix A.5 eq. (5) contains. Two."""

CRITICAL_PATH_TERMS: Final[tuple[str, ...]] = (
    "L_scene_detect",
    "max(L_frame_extract, L_stt)",
    "L_qa = l^TTFT_m + t_qa * l^TPOT_m",
)

MISSING_FROM_EQ5: Final[tuple[str, ...]] = (
    "per-sub-task service time for TOOL executors (no profile exists: Section 3.3, p.573)",
    "a sum over the nodes of a path (A.5 has no per-node index)",
    "a max over parallel paths (A.5 has no precedence relation)",
    "a makespan variable to minimise or bound (no objective in A.5 mentions completion time)",
)
"""The four structural absences. NONE of them depends on an invented magnitude -- each is a
statement about which symbols appear in Appendix A.5, checkable by reading it."""


@dataclass(frozen=True)
class TermGap:
    """Which terms each model can express. The load-bearing output of this module."""

    eq5: tuple[str, ...]
    critical_path: tuple[str, ...]
    missing_from_eq5: tuple[str, ...]

    @property
    def is_structural(self) -> bool:
        """True when the gap survives setting every invented magnitude to zero.

        It does: the `max(...)` and the per-node sum are absent from eq. (5) as SYMBOLS, so no
        choice of tool service time -- including zero -- makes eq. (5) able to express them.
        """
        return bool(self.missing_from_eq5)


def term_gap() -> TermGap:
    return TermGap(
        eq5=EQ5_TERMS,
        critical_path=CRITICAL_PATH_TERMS,
        missing_from_eq5=MISSING_FROM_EQ5,
    )


@dataclass(frozen=True)
class Comparison:
    """One `(configuration, model profile)` pair costed both ways.

    `eq5_seconds` is admissible; `critical_path_seconds` is NOT, and `caption` says so. The
    ratio is reported only to show the SIGN and rough scale of the omission, never as a result.
    """

    config: ConfigKey
    model: ModelProfileKey
    stt_enabled: bool

    eq5_seconds: float
    tool_seconds: float
    llm_seconds: float
    critical_path_seconds: float

    tool_node_breakdown: Mapping[str, float]

    @property
    def unmodelled_seconds(self) -> float:
        """Wall-clock the latency filter cannot see. Equals `tool_seconds` exactly, because the
        LLM stage is the ONLY stage eq. (5) charges for."""
        return self.critical_path_seconds - self.eq5_seconds

    @property
    def understatement_ratio(self) -> float:
        return self.critical_path_seconds / self.eq5_seconds

    @property
    def caption(self) -> str:
        return (
            f"{CAPTION_PREFIX} {self.config} on {self.model}: eq. (5) admits "
            f"{self.eq5_seconds:.2f}s; a critical path over the DAG gives "
            f"{self.critical_path_seconds:.2f}s ({self.understatement_ratio:.2f}x). The "
            f"{self.unmodelled_seconds:.2f}s difference is TOOL wall-clock that Appendix A.5 has "
            f"no term for. Tool magnitudes are INVENTED ({INVENTED_CITE.section}); the ABSENCE "
            f"of the terms is not."
        )


def _tool_seconds(node: str) -> float:
    return float(TOOL_SERVICE_TIMES[node].value)


def eq5_seconds(
    profile: WorkflowProfile,
    model: ModelProfile,
    percentile: int = 90,
    policy: OperatingPointPolicy = OperatingPointPolicy.TABLE_REPORTED,
) -> float | None:
    """Appendix A.5 eq. (5), evaluated. `None` when any input is `Unavailable`."""
    if isinstance(profile.tokens, Unavailable):
        return None
    parts = (profile.tokens.at(percentile), model.ttft(policy), model.tpot(policy))
    if any(isinstance(p, Unavailable) for p in parts):
        return None
    tokens, ttft, tpot = (float(p.value) for p in parts)
    return ttft + tokens * tpot


def compare(
    profile: WorkflowProfile,
    model: ModelProfile,
    percentile: int = 90,
    policy: OperatingPointPolicy = OperatingPointPolicy.TABLE_REPORTED,
) -> Comparison | None:
    """Cost one `(c, m)` pair under both models. `None` when the paper's data cannot support it.

    The LLM term is computed from `node_tokens["q_a"]`, not from the workflow total, to make the
    decomposition explicit -- on Video Q/A they are equal by construction (A59), and asserting
    that equality is the point: the tool stages contribute zero TOKENS while contributing
    non-zero TIME, which is precisely the conflation eq. (5) makes.
    """
    eq5 = eq5_seconds(profile, model, percentile, policy)
    if eq5 is None:
        return None

    stt_enabled = profile.key.dag_variant == "stt_on"
    breakdown = {"scene_detect": _tool_seconds("scene_detect")}
    branch = [_tool_seconds("frame_extract")]
    breakdown["frame_extract"] = branch[0]
    if stt_enabled:
        breakdown["stt"] = _tool_seconds("stt")
        branch.append(breakdown["stt"])

    tool_total = breakdown["scene_detect"] + max(branch)
    return Comparison(
        config=profile.key,
        model=model.key,
        stt_enabled=stt_enabled,
        eq5_seconds=eq5,
        tool_seconds=tool_total,
        llm_seconds=eq5,
        critical_path_seconds=tool_total + eq5,
        tool_node_breakdown=breakdown,
    )


def compare_video_qa(
    percentile: int = 90,
    policy: OperatingPointPolicy = OperatingPointPolicy.TABLE_REPORTED,
) -> tuple[Comparison, ...]:
    """Every Video Q/A `(c, m)` pair the paper's data can support, costed both ways.

    Restricted to COHERENT pairs -- `c`'s model equals `m`'s model. A.5 imposes no such
    restriction (A51) and M4 will measure how much incoherent mass it selects, but a
    critical-path figure built on `c = Llava` routed to `m = Phi-4` would be arguing two defects
    at once.
    """
    profiles = build_video_profiles()
    models = build_model_profiles()
    out: list[Comparison] = []
    for key in enumerate_video_qa():
        wp = profiles[key]
        for mk, mp in models.items():
            if mk.model_id != key.knob["model"]:
                continue
            cmp_ = compare(wp, mp, percentile, policy)
            if cmp_ is not None:
                out.append(cmp_)
    return tuple(sorted(out, key=lambda c: (str(c.config), str(c.model))))


def overlap_credit(comparisons: Sequence[Comparison]) -> Mapping[str, float]:
    """How much wall-clock the `max(...)` saves versus serializing the parallel branch.

    Section 4.6 (p.578) reports "near-perfect parallel, with full overlap in execution", so the
    parallel reading is the paper's own. A.5 can express NEITHER reading: it has no term for
    these stages at all. This function therefore quantifies a choice the formulation never gets
    to make -- which is the finding.
    """
    stt_on = [c for c in comparisons if c.stt_enabled]
    if not stt_on:
        return {}
    parallel = sum(max(c.tool_node_breakdown["frame_extract"], c.tool_node_breakdown["stt"]) for c in stt_on)
    serial = sum(c.tool_node_breakdown["frame_extract"] + c.tool_node_breakdown["stt"] for c in stt_on)
    n = len(stt_on)
    return {
        "configurations": float(n),
        "parallel_seconds_mean": parallel / n,
        "serial_seconds_mean": serial / n,
        "credit_seconds_mean": (serial - parallel) / n,
    }


def report() -> str:
    """The Section 12.1 write-up, generated rather than asserted in prose."""
    gap = term_gap()
    comps = compare_video_qa()
    lines = [
        "# Critical path vs Appendix A.5 eq. (5) -- Video Q/A",
        "",
        CAPTION_PREFIX,
        "",
        "## Terms",
        "",
        f"eq. (5) contains {len(gap.eq5)}: " + "; ".join(gap.eq5),
        f"a critical path contains {len(gap.critical_path)}: " + "; ".join(gap.critical_path),
        "",
        "## Absent from eq. (5) as SYMBOLS (independent of any magnitude)",
        "",
    ]
    lines += [f"- {m}" for m in gap.missing_from_eq5]
    lines += ["", f"Structural: {gap.is_structural}", "", "## Costed pairs", ""]
    if not comps:
        lines.append("None -- no coherent (c, m) pair has both a token total and a TPOT.")
    else:
        worst = max(comps, key=lambda c: c.understatement_ratio)
        best = min(comps, key=lambda c: c.understatement_ratio)
        lines += [
            f"{len(comps)} coherent pairs costed.",
            f"- largest understatement: {worst.caption}",
            f"- smallest understatement: {best.caption}",
            "",
            "## Overlap credit on the parallel branch (Section 4.6's measured overlap)",
            "",
        ]
        lines += [f"- {k}: {v:.3f}" for k, v in overlap_credit(comps).items()]
    return "\n".join(lines)


__all__ = [
    "CAPTION_PREFIX",
    "CRITICAL_PATH_TERMS",
    "Comparison",
    "EQ5_TERMS",
    "MISSING_FROM_EQ5",
    "TermGap",
    "compare",
    "compare_video_qa",
    "eq5_seconds",
    "overlap_credit",
    "report",
    "term_gap",
]
