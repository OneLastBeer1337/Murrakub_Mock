"""
What M4 emits so the HEFT/precedence comparison becomes computable -- DESIGN.md Section 10.2.

M4 itself adds no precedence constraint and no makespan term, because A.5 has neither. Its only
obligation to the critique is to record, from the OPTIMIZER'S SIDE, the operands that
`optimization/profiles/critique/critical_path.py` needs in order to set eq. (5)'s single number
beside a real critical path over the DAG.

**THE RULE THIS MODULE OBEYS.** It never reads `LogicalWorkflow`, node lists, or edges.
`tool_stage_count` is derived from the CONFIGURATION KEY -- the `stt_on`/`stt_off` DAG variant and
the knob set -- not from graph structure. That keeps M4 inside its prohibition while still
recording the size of the blind spot.

WHY THE RECORD IS SHAPED THIS WAY. eq. (5) is `l^TTFT_m + t_c * l^TPOT_m`: one model, one
serialized token stream, no sum over sub-tasks and no max over branches. A critical path over
Video Q/A's DAG is `L_scene + max(L_frames, L_stt) + L_qa`. Three of those four terms have no
counterpart in eq. (5) at all -- they are TOOL stages, and Section 3.3 profiles "TTFT and TPOT for
LLMs". So the comparison is about WHICH TERMS EXIST, and the numbers here exist to make that
plottable, not to be quoted. Tool magnitudes live in `profiles/critique/tool_latency.py` and are
`INVENTED` (Q16).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from optimization.profiles.schema import ConfigKey, ModelProfileKey

PairKey = tuple[ConfigKey, ModelProfileKey]

#: Tool stages per Video Q/A DAG variant. From the CONFIG KEY, never from DAG edges.
_VIDEO_TOOL_STAGES = {"stt_on": 3, "stt_off": 2}
_CODEGEN_TOOL_STAGES = 1
"""`execute_tests` -> "Python Interp." (Figure 1b). The other three Code Gen stages are LLMs."""


@dataclass(frozen=True)
class SelectedPair:
    """One winning `(c, m)` with everything eq. (5) used to admit it."""

    config: ConfigKey
    model: ModelProfileKey
    mass: float
    t_c: float
    l_ttft: float | None
    l_tpot: float | None
    eq5_value: float | None
    tau: float | None

    @property
    def slack(self) -> float | None:
        if self.eq5_value is None or self.tau is None:
            return None
        return self.tau - self.eq5_value

    @property
    def recomputable(self) -> str:
        """The arithmetic, so a reviewer can redo it by hand from Table 5."""
        if self.l_ttft is None or self.l_tpot is None:
            return "eq. (5) not evaluable for this model (A35/A36: no TTFT reported)"
        value = self.eq5_value
        if value is None:
            # An ACCURACY run never evaluates eq. (5) -- A68/Q24 means only the dimension-
            # matching filter applies -- but the quantity still exists and the comparison
            # against a critical path still needs it. Computed here rather than left blank,
            # and it is the same arithmetic the latency filter would have used.
            value = self.l_ttft + self.t_c * self.l_tpot
        return (
            f"{self.l_ttft:g} + {self.t_c:g} x {self.l_tpot:g} = {value:.4g} s"
            + ("" if self.tau is None else f" (tau = {self.tau:g} s)")
        )


@dataclass(frozen=True)
class StructuralRecord:
    """The optimizer-side half of the precedence comparison.

    Consumed by `profiles/critique/critical_path.py`, which owns the other half. Kept as data
    rather than a rendered figure so the comparison can be recomputed when tool magnitudes
    change -- they are invented, so they will.
    """

    workflow: str
    slo: tuple[str, str]
    selected: tuple[SelectedPair, ...]
    tool_stage_count: int
    """Stages contributing exactly ZERO to `eq5_value` -- the size of the blind spot.

    Derived from the configuration key. Video Q/A with STT on has three (scene_detect,
    frame_extract, stt); with STT off, two. Code Generation has one (execute_tests).
    """

    @property
    def latency_model_is_single_stream(self) -> bool:
        """Always true, and stated as data rather than prose.

        eq. (5) has no per-node index and no max over paths, so whatever the DAG looks like, the
        optimizer's latency model is one token stream on one model. This flag exists so a report
        cannot quietly omit the qualifier.
        """
        return True

    def blind_spot_note(self) -> str:
        return (
            f"eq. (5) charges {len(self.selected)} selected pair(s) for LLM generation only; "
            f"{self.tool_stage_count} tool stage(s) in this configuration contribute exactly "
            "zero to it, and A.5 has no term in which their wall-clock could appear "
            "(no per-node sum, no max over parallel branches, no makespan)."
        )


def tool_stage_count(config: ConfigKey) -> int:
    """Tool stages for a configuration, from its KEY -- not from any DAG.

    Video Q/A's `stt_off` variant drops the `stt` stage, which is visible in `dag_variant`
    without consulting edges. This is the whole reason M4 can record the blind spot without
    violating Section 10.1's prohibition.
    """
    if config.workflow_id == "video_qa":
        return _VIDEO_TOOL_STAGES.get(config.dag_variant, 3)
    return _CODEGEN_TOOL_STAGES


def build_record(
    workflow: str,
    slo: tuple[str, str],
    x: Mapping[PairKey, float],
    t_c: Mapping[ConfigKey, float],
    l_ttft: Mapping[ModelProfileKey, float],
    l_tpot: Mapping[ModelProfileKey, float],
    eq5: Mapping[PairKey, float],
    tau: float | None,
    tolerance: float = 1e-9,
) -> StructuralRecord:
    selected = tuple(
        SelectedPair(
            config=c,
            model=m,
            mass=mass,
            t_c=t_c.get(c, 0.0),
            l_ttft=l_ttft.get(m),
            l_tpot=l_tpot.get(m),
            eq5_value=eq5.get((c, m)),
            tau=tau,
        )
        for (c, m), mass in sorted(x.items(), key=lambda kv: -kv[1])
        if mass > tolerance
    )
    stages = max((tool_stage_count(p.config) for p in selected), default=0)
    return StructuralRecord(
        workflow=workflow, slo=slo, selected=selected, tool_stage_count=stages
    )


__all__ = ["SelectedPair", "StructuralRecord", "build_record", "tool_stage_count"]
