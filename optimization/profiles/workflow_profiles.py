"""
Workflow profiles: `a_c` and `t_c` -- the hardware-independent layer.

Section 3.3 (p.573): "Workflow profiles capture the end-to-end behavior of a workflow under
different configurations... They record response quality measured against benchmark datasets
(e.g., VideoMME [30], HumanEval [15], and Math [39] with ground-truth results) and executor-level
load, including prompt and completion tokens for LLM-based executors, serving as a proxy for
resource usage."

`t_c` IS A p90, NOT A MEAN (A46). Section 4.1/4.2 (p.576): "We assume the 90th percentile token
generation load from our profiles when making resource allocation decisions for all policies for
a fair comparison." That sentence exists ONLY in [OSDI] -- [ARXIV] has no counterpart -- so the
rule shaping every capacity number in this reproduction rests on one sentence in one version.
Figures 2b and 2d are CDFs precisely because the distribution matters, so `TokenDistribution`
carries percentiles and the collapse to a scalar happens at `to_milp_inputs()` time.

`a_c` IS INDEXED BY CONFIGURATION ALONE, AND THAT IS A DEFECT WE REPRODUCE (A51). Figure 2a/2c
plot accuracy per (model, knobs), but A.5 writes `a_c` with no model index and has no constraint
linking `c` to `m`. We keep the model on the profile as `accuracy_measured_on_model`, mark it
NON-MILP, and let `MilpInputs.coherent()` measure how much of the selected mass is incoherent.

WHAT IS Unavailable, AND WHY IT IS THE RIGHT ANSWER (Q19):

  * `a_c` -- 10 of 44. DeepSeek-Llama-70B (4) has exactly one plotted marker in Figure 4b (A54);
    Llama-3.2-90B (6) is separable at only three accuracy levels in Figure 4a, and even those
    give F without STT (A55). The Section 7.3 tier reconstruction independently CONFIRMS the
    first exclusion: admitting DeepSeek-Llama-70B breaks two of the four printed tiers.
  * `t_c` -- 14 of 44. Figure 2d covers three Code Gen models, so NVLM-D-72B (4) and
    DeepSeek-Llama-70B (4) have no token data; Figure 2b covers three Video models, so
    Llama-3.2-90B (6) has none. Section 2.5 (p.570) reports an ~8x spread in generated tokens
    between a reasoning and a non-reasoning model of similar size, so interpolating from
    parameter count would carry an 8x error bar. CLAUDE.md forbids exactly that.

`prompt_tokens` is carried as `Unavailable` on every profile (Q17/A39): Section 3.3 requires a
profile to capture it, A.5 has nowhere to put it, and the only prompt-token figure in the paper
(Figure 16c) is Math Q/A, which is deferred. Omitting the field would hide the gap.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Final, Mapping, Sequence

from optimization.profiles.enumerate_cw import enumerate_code_generation, enumerate_video_qa
from optimization.profiles.provenance import (
    Anchor,
    Citation,
    Measured,
    Provenance,
    Unavailable,
    Value,
)
from optimization.profiles.schema import ConfigKey, TokenDistribution, WorkflowProfile
from optimization.profiles.sources.figures_digitized import (
    ACCURACY_BAND_PP,
    FIG_2A_ACCURACY_PCT,
    FIG_2B_CLUSTERS,
    FIG_2B_STT_Y_SIDE,
    FIG_2C_ACCURACY_PCT,
    FIG_2D_CLUSTERS,
    FIG_2D_R2_SIDE,
    FIG_2D_X_AXIS_LIMIT,
    FIG_4B_ACCURACY_PCT,
    FIG_4B_BAND_PP,
    LINE_HALF_WIDTH_TOKENS_2B,
    LINE_HALF_WIDTH_TOKENS_2D,
)

FIG_2A = Citation(version="BOTH", figure="2a", page=570)
FIG_2B = Citation(version="BOTH", figure="2b", page=570)
FIG_2C = Citation(version="BOTH", figure="2c", page=570)
FIG_2D = Citation(version="BOTH", figure="2d", page=570)
FIG_4A = Citation(version="BOTH", figure="4a", page=571)
FIG_4B = Citation(version="BOTH", figure="4b", page=571)

BENCHMARK: Final[Mapping[str, str]] = {
    "video_qa": "VideoMME",
    "code_generation": "HumanEval",
}
"""Section 3.3 (p.573) names the benchmarks. Recorded per profile and NEVER mixed within a
workflow: Section 4.4 evaluates the dynamic coding pipeline on LiveCodeBench-v5 with pass@1 in
0.15-0.40 (Figure 10, p.577), the same workflow family on a completely different scale, and A.5
pools whatever it is given into one `tau_{w,s}` percentile population (A52)."""

PERCENTILES: Final[tuple[int, ...]] = (25, 50, 75, 90, 95, 99)


# ---------------------------------------------------------------------------------------------
# Token distributions
# ---------------------------------------------------------------------------------------------


def _pick_cluster(
    clusters: Sequence[tuple[float, float]],
    want_side: str | None,
    half_width: float,
) -> tuple[float, float, float]:
    """Choose which of a percentile's clusters belongs to this configuration.

    Returns `(lo, hi, value)` -- the band and the point estimate, which are NOT the same thing
    when two curves share one cluster.

    Three cases, and the third is the one that matters:

    1. Two clusters -> the line styles separated by more than the plotted line width, so the
       configuration's own cluster is taken outright.
    2. `want_side is None` -> the model's two variants are genuinely INSEPARABLE in the figure
       (NVLM-D-72B in Figure 2b: all six curves overlap within the line width at every
       percentile). Both variants share the cluster, and that is a true statement about the
       figure rather than a shortcut.
    3. One cluster but two DISTINGUISHABLE curves -> the curves overlap within the line width at
       this percentile even though their ordering is known and fixed elsewhere in the panel
       (Figure 2d: solid R=2 is left of dashed R=4 in every panel). Assigning both the cluster
       midpoint would erase a difference the figure does assert. Instead the point estimate is
       displaced from the appropriate edge by half the plotted line width -- the smallest
       displacement consistent with the curves being resolvable at all -- while the BAND stays
       the full cluster, because that is genuinely all the figure resolves.
    """
    if want_side is None:
        lo, hi = clusters[0]
        return lo, hi, (lo + hi) / 2.0
    if len(clusters) > 1:
        lo, hi = clusters[0] if want_side == "left" else clusters[-1]
        return lo, hi, (lo + hi) / 2.0
    lo, hi = clusters[0]
    value = lo + half_width if want_side == "left" else hi - half_width
    return lo, hi, min(max(value, lo), hi)


def _distribution(
    clusters_by_pct: Mapping[int, tuple[tuple[float, float], ...]],
    want_side: str | None,
    cite: Citation,
    censored_above: float | None,
    label: str,
    half_width: float,
) -> TokenDistribution:
    pct: dict[int, Value] = {}
    for p in PERCENTILES:
        if p not in clusters_by_pct:
            continue
        lo, hi, value = _pick_cluster(clusters_by_pct[p], want_side, half_width)
        censored = censored_above is not None and hi >= censored_above * 0.99
        pct[p] = Measured(
            value=value,
            unit="tokens",
            provenance=Provenance.PAPER_FIGURE_READ,
            cite=cite,
            lo=lo,
            hi=hi,
            note=(
                f"{label} p{p}; cluster [{lo:g}, {hi:g}] tokens"
                + (
                    f"; single merged cluster, point estimate displaced {half_width:g} tokens "
                    f"from the {want_side} edge (half the plotted line width)"
                    if want_side is not None and len(clusters_by_pct[p]) == 1
                    else ""
                )
                + (
                    "; RIGHT-CENSORED at the panel's x-limit, so this is a LOWER BOUND"
                    if censored
                    else ""
                )
            ),
        )
    if 90 not in pct:
        raise KeyError(f"{label}: no p90 cluster; A.5's t_c binds to the p90 (p.576)")
    pct = _enforce_monotone(pct, label)
    mean = Unavailable(
        reason=(
            "Figures 2b/2d are CDFs; a mean cannot be read from a CDF without the underlying "
            "samples, and the paper reports no mean token count for either workflow"
        ),
        cite=cite,
    )
    return TokenDistribution(percentiles=pct, mean=mean)


def _enforce_monotone(pct: dict[int, Value], label: str) -> dict[int, Value]:
    """A percentile function is non-decreasing. Enforce it, and say where it had to.

    A60. Two of the digitized series come back non-monotone -- Figure 2d's Gemma-3-27B D=2 panel
    (p90 2069 > p95 2038) and Figure 2b's Llava-OneVision-7B F=10 panel (p95 1271 > p99 1198).
    Both are DIGITIZATION artifacts, not findings: these are CDFs, so `p95 >= p90` holds by the
    definition of the object being plotted, and no reading of the figure can legitimately
    violate it. The inversions are 1.5% and 5.7%, both far inside the cluster bands.

    The correction is a running maximum applied to the POINT ESTIMATE only. Bands are untouched,
    and the corrected estimate is clipped into the percentile's own band, so no value leaves the
    range the figure actually resolves. Where a value moves, the note records the original --
    silently repairing a number would be exactly the drift this module exists to prevent.
    """
    out: dict[int, Value] = {}
    running = float("-inf")
    for p in sorted(pct):
        v = pct[p]
        if isinstance(v, Unavailable):
            out[p] = v
            continue
        if v.value >= running:
            running = v.value
            out[p] = v
            continue
        corrected = min(running, v.hi) if v.hi is not None else running
        out[p] = replace(
            v,
            value=corrected,
            note=(
                f"{v.note}; MONOTONICITY-CORRECTED (A60) from {v.value:g} to {corrected:g}: the "
                f"raw reading fell below p{max(q for q in out if q < p)}, which a CDF cannot do. "
                "Correction is a running maximum clipped into this percentile's own band"
            ),
        )
        running = max(running, float(out[p].value))
    return out


def _no_token_data(model: str, figure: str, cite: Citation) -> Unavailable:
    return Unavailable(
        reason=(
            f"{figure} plots no generated-token CDF for {model}, and no table in either version "
            "reports token counts. Section 2.5 (p.570) reports an ~8x spread between a reasoning "
            "and a non-reasoning model of similar size ('~20,000 tokens versus ~2,500'), so "
            "interpolating from parameter count would carry an 8x error bar"
        ),
        cite=cite,
        blocks=("eq3", "eq5", "eq6"),
    )


# ---------------------------------------------------------------------------------------------
# Per-node decomposition (NON-MILP; DESIGN.md Section 12.1)
# ---------------------------------------------------------------------------------------------

TOOL_NODES: Final[Mapping[str, tuple[str, ...]]] = {
    "video_qa": ("scene_detect", "frame_extract", "stt"),
    "code_generation": ("execute_tests",),
}
"""Nodes whose executor is a TOOL in every configuration, so they generate exactly zero tokens.

Video Q/A: Listing 2's first three sub-tasks map to OpenCV / OmDet+CLIP / Whisper (M2b Q9/A25).
Code Generation: `execute_tests` -> "Python Interp." (Figure 1b, p.568)."""

LLM_NODES: Final[Mapping[str, tuple[str, ...]]] = {
    "video_qa": ("q_a",),
    "code_generation": ("propose_solutions", "write_tests", "rank_solutions"),
}

SECTION_3_3 = Citation(
    version="OSDI",
    section="3.3",
    page=573,
    quote="Each profile reports: (1) latency (TTFT and TPOT for LLMs)",
)

_LLM_INVOCATIONS_AT_A_TOOL_NODE: Final[Measured[float]] = Measured(
    value=0.0,
    unit="LLM invocations",
    provenance=Provenance.PAPER_TEXT,
    cite=SECTION_3_3,
    note=(
        "Section 3.3 scopes the token-bearing half of a profile to LLMs; Section 3.2 (p.572) "
        "classifies OpenCV, Whisper, OmDet, CLIP and the Python interpreter as TOOLS. A TOOL "
        "node therefore issues no LLM invocation. This is the ANCHOR for every per-node zero -- "
        "it is a count of invocations, not of tokens, so the zero below is arithmetic over it "
        "rather than a restatement of itself."
    ),
)


def _zero_tokens(node: str) -> TokenDistribution:
    """The exact zero a TOOL node contributes to `t_c`.

    This zero is the FORMULATION's, not a measurement (DESIGN.md Section 12.1, invariant 3).
    Section 3.3 (p.573) scopes token profiles to "TTFT and TPOT for LLMs"; a tool emits no
    completion tokens, so its contribution to eq. (3)'s `t_c` is zero by construction. The band
    is [0, 0] because the claim is exact -- it is a statement about what A.5 counts, and A.5
    counts nothing here.
    """
    zero = Measured(
        value=0.0,
        unit="tokens",
        provenance=Provenance.DERIVED,
        cite=SECTION_3_3,
        lo=0.0,
        hi=0.0,
        anchors=(
            Anchor(
                profile_key=f"node:{node}",
                field="llm_invocations",
                value=_LLM_INVOCATIONS_AT_A_TOOL_NODE,
            ),
        ),
        assumption=(
            "completion tokens = (LLM invocations at the node) x (tokens per invocation), so a "
            "node with zero LLM invocations contributes exactly zero to `t_c` regardless of how "
            "long it runs"
        ),
        note=(
            f"Node `{node}` is served by a TOOL executor, which generates no completion tokens. "
            "Exact zero by the formulation's own accounting, NOT a measured absence of work: "
            "the stage consumes real wall-clock that A.5 has no term for (Section 12.3)."
        ),
    )
    return TokenDistribution(percentiles={p: zero for p in PERCENTILES}, mean=zero)


def _node_split_unavailable(node: str, workflow_id: str) -> Unavailable:
    extra = (
        " `rank_solutions` may be realised by the `test_pass_rate_ranker` TOOL (zero tokens) or "
        "by an LLM Ranker, and `C_w`'s knobs (D, R, model) do not determine which -- so even the "
        "node's ORDER OF MAGNITUDE is configuration-independent in A.5 (Section 12.3, point 5)."
        if node == "rank_solutions"
        else ""
    )
    return Unavailable(
        reason=(
            f"No figure or table reports a per-sub-task token breakdown. Figure 2d's CDFs are "
            f"per REQUEST ('# of Generated Tokens'), totalling every LLM call in the "
            f"configuration, and {workflow_id} has three LLM nodes with no published split "
            f"between them. Apportioning the total across `{node}` and its siblings would be an "
            f"INVENTED ratio, which Q19 forbids outside critique/.{extra}"
        ),
        cite=FIG_2D,
        blocks=("makespan",),
    )


def _node_tokens(
    workflow_id: str,
    total: TokenDistribution | Unavailable,
    stt_on: bool = True,
) -> dict[str, TokenDistribution | Unavailable]:
    """Decompose `t_c` over the DAG's nodes -- NON-MILP, and mostly not derivable.

    Two regimes, and the difference between them is the whole point of DESIGN.md Section 12.1:

    * **Video Q/A is derivable exactly.** Three of its four nodes are tools, so they are zero,
      and the remainder must therefore sit entirely on `q_a`. `sum(node p90) == total p90`, with
      no invented ratio anywhere.
    * **Code Generation is not.** Three LLM nodes share one published per-request total. Each is
      `Unavailable` (A59) rather than a guessed fraction.

    A59 corrects DESIGN.md Section 12.1's table, which listed `node_tokens` as DERIVED for BOTH
    workflows ("code gen: split across debate/tests/rank"). No such split is published.
    """
    out: dict[str, TokenDistribution | Unavailable] = {}
    for node in TOOL_NODES[workflow_id]:
        if node == "stt" and not stt_on:
            continue
        out[node] = _zero_tokens(node)
    llm = LLM_NODES[workflow_id]
    if len(llm) == 1:
        out[llm[0]] = total
    else:
        for node in llm:
            out[node] = _node_split_unavailable(node, workflow_id)
    return out


# ---------------------------------------------------------------------------------------------
# Accuracy
# ---------------------------------------------------------------------------------------------


def _accuracy_video(model: str, frames: int, stt: str) -> Value:
    key = (model, frames, stt)
    if key in FIG_2A_ACCURACY_PCT:
        v = FIG_2A_ACCURACY_PCT[key]
        return Measured(
            value=v,
            unit="percent",
            provenance=Provenance.PAPER_FIGURE_READ,
            cite=FIG_2A,
            lo=v - ACCURACY_BAND_PP,
            hi=v + ACCURACY_BAND_PP,
            note="bar top; reads ~+0.3 pp high because the edge stroke is included (BAR_EDGE_BIAS_PP)",
        )
    return Unavailable(
        reason=(
            f"Figure 2a omits {model} entirely, and Figure 4a -- its only other appearance -- "
            "separates it at just three accuracy levels, where marker SIZE gives F but the "
            "HATCHING that encodes STT is below the resolution of a 1.3 pp marker (A55). "
            "Assigning STT by the 'Y beats N at equal F' pattern would be an inference from a "
            "pattern, not a reading"
        ),
        cite=FIG_4A,
        blocks=("eq4", "eq8", "eq13"),
    )


def _accuracy_code(model: str, d: int, r: int) -> Value:
    if (model, d, r) in FIG_2C_ACCURACY_PCT:
        v = FIG_2C_ACCURACY_PCT[(model, d, r)]
        return Measured(
            value=v,
            unit="percent",
            provenance=Provenance.PAPER_FIGURE_READ,
            cite=FIG_2C,
            lo=v - ACCURACY_BAND_PP,
            hi=v + ACCURACY_BAND_PP,
        )
    if (model, d, r) in FIG_4B_ACCURACY_PCT:
        v = FIG_4B_ACCURACY_PCT[(model, d, r)]
        return Measured(
            value=v,
            unit="percent",
            provenance=Provenance.PAPER_FIGURE_READ,
            cite=FIG_4B,
            lo=v - FIG_4B_BAND_PP,
            hi=v + FIG_4B_BAND_PP,
            note=(
                "marker centroid in a crowded scatter, resolved by size (D) and hatch density "
                "(R); REQUIRED by the Section 7.3 tier reconstruction -- without this model the "
                "printed `basic` tier is missed by +10 pp"
            ),
        )
    return Unavailable(
        reason=(
            f"Figure 2c plots only three Code Gen models and Figure 4b plots exactly ONE "
            f"{model} marker against the 32 its legend implies (A54), so three of its four (D,R) "
            "configurations have no accuracy reading anywhere and the fourth cannot be attributed "
            "to a specific (D,R). Corroborated by Section 7.3: admitting this model on an aliased "
            "value breaks two of the four printed tiers"
        ),
        cite=FIG_4B,
        blocks=("eq4", "eq8", "eq13"),
    )


# ---------------------------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------------------------


def _prompt_tokens_gap() -> Unavailable:
    return Unavailable(
        reason=(
            "Section 3.3 (p.573) requires a workflow profile to capture 'prompt and completion "
            "tokens', but A.5 has ONE token parameter, `t_c`, used both against `theta_m` (an "
            "output-token throughput) and against `l^TPOT_m` (time per OUTPUT token), so only the "
            "completion reading is dimensionally consistent and prefill load is absent from the "
            "capacity constraint entirely. The paper's only prompt-token figure (16c) is Math "
            "Q/A, which is deferred (A39)"
        ),
        cite=Citation(version="BOTH", section="3.3", page=573),
    )


def build_video_profiles() -> dict[ConfigKey, WorkflowProfile]:
    out: dict[ConfigKey, WorkflowProfile] = {}
    for key in enumerate_video_qa():
        model = key.knob["model"]
        frames = key.knob["F"]
        stt = "Y" if key.dag_variant == "stt_on" else "N"

        clusters = FIG_2B_CLUSTERS.get((model, frames))
        if clusters is None:
            tokens: TokenDistribution | Unavailable = _no_token_data(model, "Figure 2b", FIG_2B)
        else:
            side = FIG_2B_STT_Y_SIDE.get(model, "inseparable")
            if side == "inseparable":
                want = None
            else:
                want = side if stt == "Y" else ("right" if side == "left" else "left")
            tokens = _distribution(
                clusters,
                want,
                FIG_2B,
                None,
                f"Video Q/A {model} F={frames} STT={stt}",
                LINE_HALF_WIDTH_TOKENS_2B,
            )

        out[key] = WorkflowProfile(
            key=key,
            accuracy=_accuracy_video(model, frames, stt),
            accuracy_benchmark=BENCHMARK["video_qa"],
            accuracy_measured_on_model=model,
            tokens=tokens,
            node_tokens=_node_tokens("video_qa", tokens, stt_on=(stt == "Y")),
            prompt_tokens=_prompt_tokens_gap(),
        )
    return out


def build_code_generation_profiles() -> dict[ConfigKey, WorkflowProfile]:
    out: dict[ConfigKey, WorkflowProfile] = {}
    for key in enumerate_code_generation():
        model = key.knob["model"]
        d, r = key.knob["D"], key.knob["R"]

        clusters = FIG_2D_CLUSTERS.get((model, d))
        if clusters is None:
            tokens: TokenDistribution | Unavailable = _no_token_data(model, "Figure 2d", FIG_2D)
        else:
            want = FIG_2D_R2_SIDE if r == 2 else ("right" if FIG_2D_R2_SIDE == "left" else "left")
            tokens = _distribution(
                clusters,
                want,
                FIG_2D,
                FIG_2D_X_AXIS_LIMIT,
                f"Code Gen {model} D={d} R={r}",
                LINE_HALF_WIDTH_TOKENS_2D,
            )

        out[key] = WorkflowProfile(
            key=key,
            accuracy=_accuracy_code(model, d, r),
            accuracy_benchmark=BENCHMARK["code_generation"],
            accuracy_measured_on_model=model,
            tokens=tokens,
            node_tokens=_node_tokens("code_generation", tokens),
            prompt_tokens=_prompt_tokens_gap(),
        )
    return out


def build_workflow_profiles() -> dict[ConfigKey, WorkflowProfile]:
    return {**build_code_generation_profiles(), **build_video_profiles()}


__all__ = [
    "BENCHMARK",
    "PERCENTILES",
    "build_code_generation_profiles",
    "build_video_profiles",
    "build_workflow_profiles",
]
