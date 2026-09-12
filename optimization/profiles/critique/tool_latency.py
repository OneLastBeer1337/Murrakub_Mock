"""
[INVENTED] Tool service times. **QUARANTINED -- `to_milp_inputs()` MUST NOT REACH THIS MODULE.**

Every number in this file has NO basis in the paper. They exist for exactly one purpose: to make
the precedence/makespan comparison of DESIGN.md Section 12.1 computable at all. Q16 authorised
them on three conditions, all enforced:

  1. they live here, outside the profile layer;
  2. `tests/test_milp_boundary.py` asserts nothing reachable from `to_milp_inputs()` imports this
     module, so no invented number can enter an objective or a constraint;
  3. every figure derived from them is captioned `[INVENTED]`.

WHY THE PAPER FORCES THIS. Section 3.3 (p.573) says model profiles report "TTFT and TPOT for
LLMs". Whisper, OmDet, CLIP and OpenCV are TOOL executors (Section 3.2, p.572) and have no
profile at all -- no tokens, therefore no `t_c`, therefore no contribution to eq. (3)'s capacity,
eq. (5)'s latency or eq. (12)'s cost. A.5 is token-denominated throughout, so a tool is
*invisible* to it: in the formulation, the OpenCV frame extractor takes zero time, consumes zero
resource and costs nothing.

That is the point being made. The critical-path comparison in `critical_path.py` is therefore a
statement about WHICH TERMS EXIST in each model, not about these magnitudes. The magnitudes are
illustrative and must never be quoted as findings.

THE HONEST SHAPE OF THE ARGUMENT:

    eq. (5):        l^TTFT_m + t_c * l^TPOT_m              -- one executor, no DAG
    critical path:  max over paths of SUM of node service times  -- the DAG, with parallelism

Video Q/A's DAG has `frame_extract` and `stt` in parallel (Listing 2, p.572), and Section 4.6
(p.578, Figure 12a) MEASURES that overlap -- "near-perfect parallel, with full overlap in
execution". eq. (5) has no sum over nodes and no max over paths, so it cannot express either the
serialization or the overlap. No invented number is needed to see that; the numbers only make the
gap plottable.
"""

from __future__ import annotations

from typing import Final, Mapping

from optimization.profiles.provenance import Citation, Measured, Provenance

INVENTED_CITE: Final[Citation] = Citation(
    version="EXTERNAL",
    section="INVENTED -- no paper counterpart",
    retrieved="2026-09-12",
    quote=(
        "No table or figure in either version of the paper reports a service time for any TOOL "
        "executor. These values are order-of-magnitude placeholders chosen by us."
    ),
)

_WHY: Final[str] = (
    "INVENTED order-of-magnitude placeholder. Exists only so the critical-path vs eq. (5) "
    "comparison of DESIGN.md Section 12.1 is computable; quarantined from the MILP by "
    "tests/test_milp_boundary.py and never quoted as a finding."
)


def _invented(seconds: float, node: str, rationale: str) -> Measured[float]:
    return Measured(
        value=seconds,
        unit="s",
        provenance=Provenance.INVENTED,
        cite=INVENTED_CITE,
        lo=seconds / 3.0,
        hi=seconds * 3.0,
        note=f"{_WHY} Node `{node}`: {rationale}",
    )


TOOL_SERVICE_TIMES: Final[Mapping[str, Measured[float]]] = {
    "scene_detect": _invented(
        2.0, "scene_detect", "OpenCV shot-boundary pass over a short clip, CPU-bound"
    ),
    "frame_extract": _invented(
        1.0, "frame_extract", "decode and emit F frames; scales with F, which A.5 cannot see"
    ),
    "stt": _invented(
        4.0, "stt", "Whisper transcription of the clip's audio; the parallel branch's long pole"
    ),
    "object_detect": _invented(
        1.5, "object_detect", "OmDet pass over extracted frames (folded into frame_extract, A22)"
    ),
    "frame_annotate": _invented(
        1.2, "frame_annotate", "CLIP embedding/annotation of extracted frames"
    ),
    "execute_tests": _invented(
        0.8, "execute_tests", "Python interpreter running a generated unit-test suite"
    ),
    "rank_solutions": _invented(
        0.3, "rank_solutions", "non-LLM tallying step, if realised as a tool rather than an LLM"
    ),
}
"""Seven invented service times -- the ONLY invented numbers in Milestone 3.

The +/-3x band is deliberately enormous. A tight band on a fabricated number would imply
precision that does not exist, and the comparison these feed is structural anyway.
"""

__all__ = ["INVENTED_CITE", "TOOL_SERVICE_TIMES"]
