"""
Printed figure annotations and prose numbers -- TYPESET TEXT, exact to the digit.

`PAPER_FIGURE_LABEL` exists as a provenance level separate from `PAPER_FIGURE_READ` because of
this module. Figure 8a's "Best >=91.4%" is typeset; the bar next to it is pixels. Collapsing
them would let an exact number inherit a digitization band and a pixel reading claim typeset
exactness.

Everything here was read out of the PDF text layer of BOTH versions during the build.

  Figure 7  [OSDI p.575] = Figure 8  [ARXIV p.8]   Video Q/A, per-SLO results + tier labels
  Figure 8  [OSDI p.575] = Figure 9  [ARXIV p.8]   Code Generation, ditto
  Figure 17 [OSDI p.586] = Figure 16 [ARXIV p.17]  Math Q/A, ditto (DEFERRED workflow; kept
                                                   only as evidence about the tier RULE)

One version difference, cosmetic but worth recording: [OSDI] prints the comparison operator
("Best >=91.4%", "Best <=11.3s"); [ARXIV] prints the bare value ("Best 91.4%", "Best 6.5s").
The numbers agree everywhere.
"""

from __future__ import annotations

from typing import Final

# ---------------------------------------------------------------------------------------------
# SLO tier labels -- tau_{w,s}
# ---------------------------------------------------------------------------------------------

TIER_LABELS: Final[dict[tuple[str, str], dict[str, float]]] = {
    # Figure 7a (p.575) / [ARXIV] Figure 8a (p.8): ">=" accuracy, percent
    ("video_qa", "accuracy"): {"best": 66.2, "good": 64.4, "fair": 61.4, "basic": 54.9},
    # Figure 7b (p.575) / [ARXIV] Figure 8b (p.8): "<=" end-to-end latency, seconds
    ("video_qa", "latency"): {"best": 0.5, "good": 0.9, "fair": 3.0, "basic": 5.8},
    # Figure 8a (p.575) / [ARXIV] Figure 9a (p.8)
    ("code_generation", "accuracy"): {"best": 91.4, "good": 88.9, "fair": 87.1, "basic": 75.5},
    # Figure 8b (p.575) / [ARXIV] Figure 9b (p.8)
    ("code_generation", "latency"): {"best": 11.3, "good": 25.5, "fair": 35.3, "basic": 78.2},
}

TIER_LABEL_FIGURE: Final[dict[tuple[str, str], str]] = {
    ("video_qa", "accuracy"): "7a",
    ("video_qa", "latency"): "7b",
    ("code_generation", "accuracy"): "8a",
    ("code_generation", "latency"): "8b",
}

MATH_QA_TIER_LABELS: Final[dict[str, dict[str, float]]] = {
    # Figure 17 (p.586). Math Q/A is DEFERRED (CLAUDE.md); these are read only as evidence
    # that the tier rule of Section 3.4 is applied uniformly and prints the same way.
    "accuracy": {"best": 78.3, "good": 75.7, "fair": 75.5, "basic": 70.1},
    "latency": {"best": 6.5, "good": 13.9, "fair": 18.5, "basic": 31.3},
}


# ---------------------------------------------------------------------------------------------
# Prose numbers (PAPER_TEXT)
# ---------------------------------------------------------------------------------------------

SLO_TIER_RULE: Final[str] = (
    "We assign four SLO tiers for quality and end-to-end latency: best, good, fair, and "
    "basic. The SLO tiers correspond to the best, 95th, 80th, and 50th percentile values of "
    "accuracy and latency available among the set of all workflow, model, and hardware "
    "configurations."
)
"""Section 3.4, [OSDI] p.575 / [ARXIV] p.7. Verified character-comparable in both versions."""

P90_ALLOCATION_RULE: Final[str] = (
    "We assume the 90th percentile token generation load from our profiles when making "
    "resource allocation decisions for all policies for a fair comparison."
)
"""[OSDI] p.576 ONLY -- **A46**. Verified absent from [ARXIV] (the string "90th percentile"
does not occur anywhere in arXiv:2508.18298v2). `t_c = p90`, the rule that shapes every
capacity number in this reproduction, rests on one sentence in one version."""

LLAVA_F10_STT_TOKENS: Final[dict[int, float]] = {50: 600.0, 99: 1200.0}
"""Section 3.4, [OSDI] p.575 / [ARXIV] p.7, identical: "a video Q/A workflow with 10 frames and
STT on Llava-OneVision-7B [47] produces 600 and 1200 tokens in the 50th and 99th percentile,
respectively, highlighting high variance."

The ONLY per-percentile token numbers stated in prose anywhere in either version, and therefore
the only calibration anchor available for the Figure 2b digitization."""

LLAVA_F10_STT_TOKENS_QUOTE: Final[str] = (
    "a video Q/A workflow with 10 frames and STT on Llava-OneVision-7B [47] produces 600 and "
    "1200 tokens in the 50th and 99th percentile, respectively, highlighting high variance"
)

GEMMA_BEST_VIDEO_ACCURACY: Final[float] = 66.2
GEMMA_BEST_VIDEO_QUOTE: Final[str] = (
    "using Gemma-3-27B [81] with 10 frames and STT enabled achieves the highest video Q/A "
    "accuracy (66.2%) but also generates the most tokens compared to other configurations of "
    "the same model"
)
"""Section 2.5, [OSDI] p.570 / [ARXIV] p.3, identical. Two facts in one sentence:
  (1) a_c for (Gemma-3-27B, F=10, STT=Y) is exactly 66.2% -- PAPER_TEXT, not a bar reading;
  (2) for GEMMA, STT=Y generates MORE tokens than the alternatives of the same model. Note
      that the Figure 2b panels do NOT share that ordering: in the Llava-OneVision-7B panel the
      solid (STT:Y) curve lies LEFT of the dashed (STT:N) curve at every percentile, i.e. STT
      on generates FEWER tokens. The STT effect is model-dependent and must be read per panel.
"""

VIDEO_TOKEN_RANGE: Final[tuple[float, float]] = (250.0, 1000.0)
VIDEO_TOKEN_RANGE_QUOTE: Final[str] = (
    "Token counts vary widely across requests, from 250 to nearly 1000, often with a heavy tail"
)
"""Section 2.5, [OSDI] p.570 / [ARXIV] p.3."""

CODEGEN_MEDIAN_TOKENS: Final[dict[str, float]] = {
    "DeepSeek-Qwen-32B": 20000.0,
    "Gemma-3-27B": 2500.0,
}
CODEGEN_MEDIAN_TOKENS_QUOTE: Final[str] = (
    "At the median, it generates ~20,000 tokens versus ~2,500 for Gemma-3-27B under the same "
    "workflow configuration"
)
"""Section 2.5, [OSDI] p.570 / [ARXIV] p.4, identical. "the same workflow configuration" is not
named; the Figure 2d digitization identifies it as (D=4, R=4), where the two models' median
readings are ~20,850 and ~2,540 -- agreement to 4% and 2% respectively, which is what
validates the Figure 2d calibration."""

SLO_MIX_4_3: Final[dict[tuple[str, str], float]] = {
    ("accuracy", "good"): 0.70,
    ("latency", "good"): 0.30,
}
SLO_MIX_4_3_QUOTE: Final[str] = (
    "we run video Q/A and code generation requests together and assign 70% requests to be "
    "high-accuracy and 30% requests to low-latency, both with good tier"
)
"""Section 4.3, [OSDI] p.576 / [ARXIV] p.9, identical."""

RESOURCE_BUDGET_SWEEP_QUOTE: Final[str] = (
    "the cluster always provides 2,000 A100 GPUs, while the number of H100 GPUs varies from 0 "
    "to 500 in increments of 100"
)
"""Section 4.5, [OSDI] p.578. The ONLY statement of `B_g` in either version. Sections 4.2 and
4.3 state no budget, so constraint (7) is inactive there and `B_g` is `Unavailable` -- a budget
must not be invented (A43)."""


# ---------------------------------------------------------------------------------------------
# Legend domains -- printed, therefore PAPER_FIGURE_LABEL, therefore exact
# ---------------------------------------------------------------------------------------------

FIGURE_3_LEGEND_TP: Final[tuple[int, ...]] = (1, 2, 4, 8)
"""Figure 3 (p.570) legend: "A100, TP=1 | A100, TP=2 | A100, TP=4 | A100, TP=8 | H100, TP=1 |
H100, TP=2 | H100, TP=4 | H100, TP=8". The legend is shared by all five model rows; which of
the eight a given row actually PLOTS is `FIGURE_3_COVERAGE` below."""

FIGURE_3_COVERAGE: Final[dict[str, dict[str, tuple[int, ...]]]] = {
    # Read off the plotted marker shapes panel by panel, at 20x, during the build.
    # Marker shapes: TP=1 diamond, TP=2 triangle, TP=4 circle, TP=8 square.
    "DeepSeek-Qwen-32B": {"A100": (4, 8), "H100": (4, 8)},
    "Gemma-3-27B": {"A100": (4, 8), "H100": (4, 8)},
    "Llama-3.1-70B": {"A100": (8,), "H100": (8,)},
    "Phi-4": {"A100": (1, 2), "H100": (1, 2)},
    "NVLM-D-72B": {"A100": (4, 8), "H100": (4, 8)},
}
"""**CORRECTION TO DESIGN.md Section 6.1.** The design doc asserts Phi-4 has Figure 3 curves at
A100 {1,2,4,8} and H100 {1,2,4,8} -- eight tuples, weighted 2x every other model in the Section
7.3 tier reconstruction. The figure plots only diamonds (TP=1) and triangles (TP=2) in the
Phi-4 row: FOUR tuples, the same as every other 4-tuple model. The PDF wins; logged as A53.

Corroboration from the paper's own tables: every Phi-4 row in Table 6 (p.586) is TP=1 or TP=2
(A100/2, H100/1, H100/2) and none is TP=4 or TP=8.

Consequence: Figure 3 covers 4+4+2+4+4 = 18 (model, GPU, TP) tuples, and the hardware expansion
of Section 3.4's tier rule is UNIFORM across the four Code Gen models that have accuracy data,
so it cannot be what makes the Code Gen tiers reproduce. See `slo_tiers.py`."""

FIGURE_4A_LEGEND: Final[dict[str, tuple]] = {
    "gpu_tp": (("A100", 4), ("A100", 8), ("H100", 4), ("H100", 8)),
    "models": (
        "Gemma-3-27B",
        "Llava-OneVision-7B",
        "Llama-3.2-90B-Vision",
        "NVLM-D-72B",
    ),
    "size": ("1 frames", "10 frames"),
    "hatch": ("STT disabled", "STT enabled"),
}
"""Figure 4a (p.571) / [ARXIV] Figure 5a (p.5). A49: the Video Q/A TP domain is {4, 8} while
Figure 4b's Code Gen domain is {1,2,4,8} and Table 5 uses only TP=4 in every row. A.5's `g_m`
is a property of `m` alone and cannot express a per-workflow restriction.

A48: the legend spells the model `Llama-3.2-90B-Vision`; `shared/model_ids.py` (M2b, approved)
spells it `Llama-3.2-90B`; Listing 1 (p.569) writes `Llama-3.2`. Three spellings, one model.
The M2b id is kept and the aliases recorded, because renaming would break an approved module."""

FIGURE_4B_LEGEND: Final[dict[str, tuple]] = {
    "gpu_tp": tuple(
        (g, t) for g in ("A100", "H100") for t in (1, 2, 4, 8)
    ),
    "models": (
        "DeepSeek-Llama-70B",
        "DeepSeek-Qwen-32B",
        "Gemma-3-27B",
        "Phi-4",
        "NVLM-D-72B",
    ),
    "size": ("2 agents", "4 agents"),
    "hatch": ("2 rounds", "4 rounds"),
}
"""Figure 4b (p.571) / [ARXIV] Figure 5b (p.5). Marker shapes, read at 40x during the build and
needed to attribute any point to a model: DeepSeek-Llama-70B = star, DeepSeek-Qwen-32B =
pentagon, Gemma-3-27B = circle, Phi-4 = diamond, NVLM-D-72B = triangle."""

MODEL_ALIASES: Final[dict[str, tuple[str, ...]]] = {
    "Llama-3.2-90B": ("Llama-3.2-90B-Vision", "Llama-3.2"),
}
"""A48. NOT applied to `DeepSeek-Llama-70B` / `Llama-3.1-70B`: Q13 keeps those DISTINCT, and any
transfer between them is an `ASSUMED_ALIAS` value carried only by the `wide` profile set."""
