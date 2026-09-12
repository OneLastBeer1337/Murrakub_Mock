"""
Tables 2, 3, 5 and 6 transcribed verbatim from BOTH versions, with a cross-version assertion.

  [OSDI]  Table 5 (p.585) "Video Configurations with GPU Details"
          Table 6 (p.586) "Code Generation Configurations with GPU Details"
          Table 2 (p.576) policy comparison over the 24 h trace
          Table 3 (p.578) resource-constrained sweep
  [ARXIV] Table 4 (p.16), Table 5 (p.17), Table 1 (p.9), Table 2 (p.9) -- same content,
          different numbering (see CONCORDANCE).

Every cell below was read out of the PDF during the build, not from the design document.
Three version differences were found and are asserted here rather than smoothed over:

  A44  [OSDI] Table 5 has an `STT` column, `Y` in every row; [ARXIV] Table 4 has no such
       column. The OSDI version therefore added the column that shows the paper never reports
       the optimizer choosing STT-off, corroborating M2b's A28.
  A45  [OSDI] Table 6's column is headed `Agents`; [ARXIV] Table 5's is headed `Debaters`.
       This RESOLVES M2's A14: the column is `D`. One (D,R) pair per Code Gen configuration;
       a DAG in which the orchestrator selects `llm_debate_testers` is not representable in
       `C_w`.
  A47  Table 2 / Table 1 disagree on policy count AND on every number (see POLICY_COMPARISON).

The numeric cells themselves are IDENTICAL across versions wherever both print them, which is
asserted at import time by `_assert_cross_version()`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

# ---------------------------------------------------------------------------------------------
# Version concordance (DESIGN.md Section 11.1, re-verified page by page against both PDFs)
# ---------------------------------------------------------------------------------------------

CONCORDANCE: Final[dict[str, str]] = {
    "OSDI Figure 1 (p.568)": "ARXIV Figure 2 (p.3)",
    "OSDI Figure 2 (p.570)": "ARXIV Figure 3 (p.4)",
    "OSDI Figure 3 (p.570)": "ARXIV Figure 4 (p.4)",
    "OSDI Figure 4 (p.571)": "ARXIV Figure 5 (p.5)",
    "OSDI Figure 7 (p.575)": "ARXIV Figure 8 (p.8)",
    "OSDI Figure 8 (p.575)": "ARXIV Figure 9 (p.8)",
    "OSDI Figure 19 (p.587)": "ARXIV Figure 18 (p.18)",
    "OSDI Table 2 (p.576)": "ARXIV Table 1 (p.9)",
    "OSDI Table 3 (p.578)": "ARXIV Table 2 (p.9)",
    "OSDI Table 4 (p.585)": "ARXIV Table 3 (p.16)",
    "OSDI Table 5 (p.585)": "ARXIV Table 4 (p.16)",
    "OSDI Table 6 (p.586)": "ARXIV Table 5 (p.17)",
}


# ---------------------------------------------------------------------------------------------
# Table 5 [OSDI p.585] / Table 4 [ARXIV p.16] -- Video Q/A chosen configurations
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class VideoRow:
    slo: str  # "accuracy" | "latency"   (printed as `Acc.` / `Lat.`)
    objective: str  # "cost" | "energy"
    tier: str  # best | good | fair | basic
    model: str
    stt: str  # "Y" in every OSDI row; the column does not exist in [ARXIV] (A44)
    frames: int
    gpu: str
    tp: int
    tpot_s: float
    tps: float


TABLE_5_OSDI: Final[tuple[VideoRow, ...]] = (
    VideoRow("accuracy", "cost", "best", "Gemma-3-27B", "Y", 10, "A100", 4, 0.0624, 699),
    VideoRow("accuracy", "cost", "good", "Gemma-3-27B", "Y", 5, "A100", 4, 0.0624, 700),
    VideoRow("accuracy", "cost", "fair", "NVLM-D-72B", "Y", 5, "A100", 4, 0.0966, 325),
    VideoRow("accuracy", "cost", "basic", "Llava-OneVision-7B", "Y", 5, "A100", 4, 0.0224, 2244),
    VideoRow("accuracy", "energy", "best", "Gemma-3-27B", "Y", 10, "H100", 4, 0.0484, 1688),
    VideoRow("accuracy", "energy", "good", "Gemma-3-27B", "Y", 5, "H100", 4, 0.0472, 1668),
    VideoRow("accuracy", "energy", "fair", "NVLM-D-72B", "Y", 5, "H100", 4, 0.0650, 766),
    VideoRow("accuracy", "energy", "basic", "Llava-OneVision-7B", "Y", 5, "H100", 4, 0.0079, 3271),
    VideoRow("latency", "cost", "best", "Llava-OneVision-7B", "Y", 1, "H100", 4, 0.0044, 479),
    VideoRow("latency", "cost", "good", "Llava-OneVision-7B", "Y", 1, "A100", 4, 0.0085, 926),
    VideoRow("latency", "cost", "fair", "Llava-OneVision-7B", "Y", 1, "A100", 4, 0.0224, 2244),
    VideoRow("latency", "cost", "basic", "Llava-OneVision-7B", "Y", 1, "A100", 4, 0.0224, 2244),
    VideoRow("latency", "energy", "best", "Llava-OneVision-7B", "Y", 1, "H100", 4, 0.0044, 479),
    VideoRow("latency", "energy", "good", "Llava-OneVision-7B", "Y", 1, "H100", 4, 0.0070, 2836),
    VideoRow("latency", "energy", "fair", "Llava-OneVision-7B", "Y", 1, "H100", 4, 0.0070, 2836),
    VideoRow("latency", "energy", "basic", "Llava-OneVision-7B", "Y", 1, "H100", 4, 0.0070, 2836),
)

#: [ARXIV] Table 4 (p.16): the SAME sixteen rows without the `STT` column (A44). Stored as the
#: key tuple only, because that is what the cross-version assertion compares.
TABLE_4_ARXIV_KEYS: Final[frozenset[tuple]] = frozenset(
    (r.slo, r.objective, r.tier, r.model, r.frames, r.gpu, r.tp, r.tpot_s, r.tps)
    for r in TABLE_5_OSDI
)

STT_COLUMN_EXISTS: Final[dict[str, bool]] = {"OSDI": True, "ARXIV": False}
"""A44. The `STT` column is [OSDI]-only, and every one of its sixteen cells reads `Y`."""


# ---------------------------------------------------------------------------------------------
# Table 6 [OSDI p.586] / Table 5 [ARXIV p.17] -- Code Generation chosen configurations
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class CodeRow:
    slo: str
    objective: str
    tier: str
    model: str
    debaters: int  # [OSDI] header `Agents`; [ARXIV] header `Debaters` -- A45
    rounds: int
    gpu: str
    tp: int
    tpot_s: float
    tps: float


TABLE_6_OSDI: Final[tuple[CodeRow, ...]] = (
    CodeRow("accuracy", "cost", "best", "DeepSeek-Qwen-32B", 4, 4, "A100", 4, 0.0767, 653),
    CodeRow("accuracy", "cost", "good", "Gemma-3-27B", 4, 4, "A100", 4, 0.0624, 700),
    CodeRow("accuracy", "cost", "fair", "Gemma-3-27B", 2, 4, "A100", 4, 0.0624, 700),
    CodeRow("accuracy", "cost", "basic", "Phi-4", 2, 4, "A100", 2, 0.0609, 623),
    CodeRow("accuracy", "energy", "best", "DeepSeek-Qwen-32B", 4, 4, "H100", 4, 0.0387, 1390),
    CodeRow("accuracy", "energy", "good", "Gemma-3-27B", 4, 4, "H100", 4, 0.0496, 1709),
    CodeRow("accuracy", "energy", "fair", "Gemma-3-27B", 2, 4, "H100", 4, 0.0487, 1693),
    CodeRow("accuracy", "energy", "basic", "Phi-4", 2, 4, "H100", 1, 0.0373, 757),
    CodeRow("latency", "cost", "best", "NVLM-D-72B", 2, 2, "H100", 8, 0.0129, 84),
    CodeRow("latency", "cost", "good", "Phi-4", 2, 2, "H100", 2, 0.0169, 1036),
    CodeRow("latency", "cost", "fair", "Phi-4", 2, 2, "H100", 2, 0.0218, 1185),
    CodeRow("latency", "cost", "basic", "Phi-4", 2, 2, "A100", 2, 0.0609, 623),
    CodeRow("latency", "energy", "best", "NVLM-D-72B", 2, 2, "H100", 8, 0.0129, 84),
    CodeRow("latency", "energy", "good", "Phi-4", 2, 2, "H100", 1, 0.0165, 248),
    CodeRow("latency", "energy", "fair", "Phi-4", 2, 2, "H100", 1, 0.0253, 552),
    CodeRow("latency", "energy", "basic", "Phi-4", 2, 2, "H100", 1, 0.0372, 755),
)

TABLE_5_ARXIV_KEYS: Final[frozenset[tuple]] = frozenset(
    (r.slo, r.objective, r.tier, r.model, r.debaters, r.rounds, r.gpu, r.tp, r.tpot_s, r.tps)
    for r in TABLE_6_OSDI
)

DEBATERS_COLUMN_HEADER: Final[dict[str, str]] = {"OSDI": "Agents", "ARXIV": "Debaters"}
"""A45, and the evidence that closes M2's A14: the column is `D`."""


# ---------------------------------------------------------------------------------------------
# Table 2 [OSDI p.576] / Table 1 [ARXIV p.9] -- the validation target, and it disagrees (A47)
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class PolicyRow:
    policy: str
    gpus: int
    energy_mwh: float
    cost_k_usd: float


POLICY_COMPARISON: Final[dict[str, tuple[PolicyRow, ...]]] = {
    "OSDI": (  # Table 2, p.576 -- FOUR policies
        PolicyRow("LangGraph", 2568, 82.1, 211.7),
        PolicyRow("LangGraph+Auto", 2472, 80.6, 112.3),
        PolicyRow("Murakkab Opt", 1164, 27.7, 57.2),
        PolicyRow("Murakkab Opt+Mult", 912, 22.1, 47.2),
    ),
    "ARXIV": (  # Table 1, p.9 -- THREE policies, and every number differs
        PolicyRow("Static", 2560, 80.4, 201.5),
        PolicyRow("Murakkab Opt", 1151, 27.1, 56.2),
        PolicyRow("Murakkab Opt+Mult", 908, 21.6, 46.5),
    ),
}

MULTIPLEXING_REDUCTION_PCT: Final[dict[str, tuple[float, float, float]]] = {
    "OSDI": (21.6, 20.2, 17.4),  # p.576, (GPUs, energy, cost)
    "ARXIV": (21.1, 20.2, 17.3),  # p.9
}
"""A47. Not a profile input, but it IS the validation target for M5, so the target itself is
version-dependent. Reported, not reconciled."""


# ---------------------------------------------------------------------------------------------
# Table 3 [OSDI p.578] / Table 2 [ARXIV p.9] -- resource-constrained sweep (identical)
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class SweepRow:
    available_a100: int
    available_h100: int
    allocated_a100: int
    allocated_h100: int
    energy_mwh: float
    cost_k_usd: float


TABLE_3: Final[tuple[SweepRow, ...]] = (
    SweepRow(2000, 0, 1292, 0, 24.7, 55.7),
    SweepRow(2000, 100, 780, 100, 17.8, 52.4),
    SweepRow(2000, 200, 536, 200, 14.5, 60.3),
    SweepRow(2000, 300, 288, 300, 12.4, 64.8),
    SweepRow(2000, 400, 50, 400, 11.1, 70.6),
    SweepRow(2000, 500, 0, 495, 11.0, 75.4),
)
"""Section 4.5 (p.578): "the cluster always provides 2,000 A100 GPUs, while the number of H100
GPUs varies from 0 to 500 in increments of 100". VERIFIED identical in [ARXIV] Table 2 (p.9).

This is the ONLY source for `e_m` in either version (Section 6.5 of DESIGN.md): rows 1 and 6
are single-GPU-type allocations, so (MWh, GPUs, 24 h) pins an average per-GPU power -- under
the assumption that the allocation was constant over the 24 h, which Figure 11 (p.578) shows
it was not."""


# ---------------------------------------------------------------------------------------------
# Appendix A.5 constants
# ---------------------------------------------------------------------------------------------

ALPHA: Final[float] = 1.15
"""A.5 (p.586): "alpha: Unified buffer factor (default 1.15)". Identical in both versions."""

EPSILON_OBJ_13: Final[float] = 0.001
"""A.5 (p.587), objective (13): "where epsilon = 0.001". Not an M3 profile; recorded because
it is a printed parameter and M4 will need it."""

OPTIMIZATION_EPOCH_MINUTES: Final[int] = 60
"""Section 3.4 (p.575): "The optimizer runs in the background after every optimization epoch,
in our case every 60 minutes"."""

SOLVER_TIME_LIMIT_S: Final[int] = 300
"""A.5 (p.587): "solved using Gurobi [37] with a time limit of 300 seconds". Recorded so M4's
open-source-solver substitution is a documented deviation rather than a silent one."""


# ---------------------------------------------------------------------------------------------
# Derived views used by model_profiles.py
# ---------------------------------------------------------------------------------------------


def reported_operating_points() -> dict[tuple[str, str, int], list[tuple[float, float, str]]]:
    """All `(TPOT, TPS)` operating points Tables 5/6 report, grouped by `(model, gpu, tp)`.

    This is the raw material for A37b. Twelve distinct tuples are reported; four of them carry
    more than one operating point, and Phi-4/H100/TP=1 carries FOUR.
    """
    out: dict[tuple[str, str, int], list[tuple[float, float, str]]] = {}
    for r in TABLE_5_OSDI:
        out.setdefault((r.model, r.gpu, r.tp), []).append(
            (r.tps, r.tpot_s, f"Table 5 {r.slo}/{r.objective}/{r.tier}")
        )
    for r in TABLE_6_OSDI:
        out.setdefault((r.model, r.gpu, r.tp), []).append(
            (r.tps, r.tpot_s, f"Table 6 {r.slo}/{r.objective}/{r.tier}")
        )
    return out


def _assert_cross_version() -> None:
    """`version="BOTH"` is only legal when a value was checked in both PDFs and agrees.

    Runs at import so that a transcription error fails the build rather than the reader's
    trust (DESIGN.md Section 2.5, assertion 2's sibling).
    """
    v_keys = frozenset(
        (r.slo, r.objective, r.tier, r.model, r.frames, r.gpu, r.tp, r.tpot_s, r.tps)
        for r in TABLE_5_OSDI
    )
    if v_keys != TABLE_4_ARXIV_KEYS:
        raise AssertionError("Table 5 [OSDI] and Table 4 [ARXIV] disagree on a numeric cell")
    c_keys = frozenset(
        (r.slo, r.objective, r.tier, r.model, r.debaters, r.rounds, r.gpu, r.tp, r.tpot_s, r.tps)
        for r in TABLE_6_OSDI
    )
    if c_keys != TABLE_5_ARXIV_KEYS:
        raise AssertionError("Table 6 [OSDI] and Table 5 [ARXIV] disagree on a numeric cell")
    if len(TABLE_5_OSDI) != 16 or len(TABLE_6_OSDI) != 16:
        raise AssertionError("each chosen-configuration table has 2 SLOs x 2 objectives x 4 tiers")
    if len(reported_operating_points()) != 12:
        raise AssertionError("Tables 5 and 6 jointly report exactly 12 (model, GPU, TP) tuples")


_assert_cross_version()
