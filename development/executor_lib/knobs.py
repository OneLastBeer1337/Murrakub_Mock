"""
The knob vocabulary: one definition per configurable parameter, shared across all catalogues.

Implements attribute (3) of Murakkab (OSDI '26), Section 3.2, "Attributes" (p.572):
  "Each model or tool in the library exposes three attributes: (1) a textual description, (2) an
   interface specification, and (3) a key-value list of configurable parameters. For example, the
   frame extraction tool exposes the knobs: F (number of frames to extract) and cores (number of
   CPU cores to run on). The LLM Debate composition exposes the knobs: D (number of debaters),
   R (number of rounds), and model (which LLM to use). The orchestrator uses these descriptions
   and interfaces to rank and assign executors (models or tools) for workflow tasks, DEFERRING
   PARAMETER CONFIGURATION TO A LATER OPTIMIZATION PHASE (Section 3.3)."

Every function here returns a `ParameterSpec`, which has no `value` field by design -- M2 declares
the holes, M4 fills them (`shared/executor.py`; DESIGN.md Section 1.4).

WHY FACTORIES INSTEAD OF LITERALS AT EACH CALL SITE: M3 enumerates the workflow configuration set
`C_w` (Appendix A.5, p.586) as the cross-product of these domains, and keys profiles on the knob
name. If two executors declared `cores` with different domains, M3 would profile two different
things under one name. One definition per knob makes that impossible (DESIGN.md Section 8, point 2).

NO PERFORMANCE NUMBERS APPEAR HERE. A domain says which values are *selectable*, never what
choosing one costs. Accuracy `a_c`, tokens `t_c`, latency, energy and cost are Milestone 3.
"""

from __future__ import annotations

from typing import Final

from shared.executor import ParameterSpec
from shared.model_ids import CODE_GEN_MODELS, VIDEO_QA_MODELS

# ---------------------------------------------------------------------------------------------
# The three-level knob taxonomy -- DOCUMENTATION ONLY (resolved as Q1 on 2026-09-10)
# ---------------------------------------------------------------------------------------------

KNOB_LEVELS: Final[dict[str, str]] = {
    # Section 3.3.1, Decision 1 (p.574) lists the workflow configuration as "number of frames,
    # STT on/off, debaters and rounds".
    "D": "workflow",
    "R": "workflow",
    # Section 3.3.1 Decision 1 (p.574) lists "number of frames" in the WORKFLOW configuration,
    # while Section 2.5 (p.570) gives "how many frames to extract in Frame Extractor" as its
    # example of an AGENT-level knob. The paper places the same knob at two levels (gap A12); the
    # tag below takes Section 3.3.1, which is the one the optimizer section actually uses.
    "F": "workflow",
    # Section 2.5 (p.570), agent-level: "which LLM to use for Q/A".
    "model": "agent",
    # Section 3.2 (p.572) exposes `cores` as an EXECUTOR knob, but Section 2.5 (p.570) classifies
    # "CPU vs. GPU and parallelism degree" as HARDWARE-level. The paper puts it on both sides of
    # its own boundary (DESIGN.md A13).
    "cores": "hardware-exposed-as-executor",
    "timeout_s": "tool-local",  # [INVENTED] -- no level in the paper because no such knob exists
    "segment_s": "tool-local",  # [INVENTED] -- likewise
}
"""Which of Section 2.5's three levels each knob belongs to.

This is a plain dict, NOT a field on `ParameterSpec`. Decision Q1 (2026-09-10): the paper's own
taxonomy is self-contradictory -- Section 2.5 (p.570) calls the frame count *agent-level* while
Section 3.3.1 (p.574) folds "number of frames, STT on/off, debaters and rounds" into the
*workflow* configuration (DESIGN.md A12) -- and Appendix A.5 has no per-knob index anyway: `a_c`
and `t_c` collapse every knob into the opaque configuration `c`. A `level` field would therefore
encode a contradiction and have no consumer. Documented here instead.
"""

HARDWARE_LEVEL_KNOBS: Final[frozenset[str]] = frozenset(
    {"gpu", "gpu_type", "tp", "tensor_parallel", "parallelism", "batch", "n_m", "instances"}
)
"""Knob names that must NEVER appear on an executor.

Section 3.3.1, Decision 3 (p.574): "A profile encodes a specific model, GPU type, and parallelism
strategy, so choosing m implicitly fixes the hardware and parallelism degree." Table 6 (p.586)
packages this as `Model | GPU | TP` on one side and `Agents | Rounds` on the other: M2 owns the
right-hand pair, M3's model profiles own the left-hand triple. Enforced by
`tests/test_executor_lib_contract.py`.
"""


# ---------------------------------------------------------------------------------------------
# Knob factories
# ---------------------------------------------------------------------------------------------


def model_knob() -> ParameterSpec:
    """`model` -- which LLM to use. Paper-named, Section 3.2 (p.572).

    Domain: the five Code Generation model ids (`shared/model_ids.py`; Table 6 p.586 +
    Figure 4b p.571).

    KNOWN DEAD-END (DESIGN.md Section 6.2; PROGRESS.md M1 gap): this knob is declared per
    executor, as Section 3.2 attribute (3) and Section 3.3.1 Decision 2 ("the chosen model or tool
    for each executor") both require. But every Appendix A.5 decision variable is `x_{w,s,c,m}` --
    workflow, SLO tier, whole-workflow configuration, and ONE model. There is no executor or
    DAG-node index in the formulation. Nine executors in the Code Gen catalogue declare `model`;
    a faithful M4 can honour one of them. Declared anyway, because removing it would be repairing
    the paper (standing policy: reproduce literally, report the problem).
    """
    return ParameterSpec(
        name="model",
        kind="enum",
        domain=CODE_GEN_MODELS,
        description="which LLM to use",  # Section 3.2, p.572, verbatim
    )


def debaters_knob() -> ParameterSpec:
    """`D` -- number of debaters. Paper-named, Section 3.2 (p.572).

    Domain is the LITERAL enumerated set {2, 4}, not a range. Every place the paper reports this
    knob for Code Generation uses exactly 2 and 4: Table 6's `Agents` column (p.586), Figure 2c
    ("D=2, R=2 | D=2, R=4 | D=4, R=2 | D=4, R=4", p.570) and Figure 4b's "# of agents" legend
    (p.571). Under the reproduce-literally policy we do not generalize to [1..8] (DESIGN.md A21).

    Consequence: there is no `D=1`, so a single non-debating coder cannot be expressed as a
    degenerate parameterization of the debate composition -- it has to be its own executor
    (`llm_single_shot_coder`).
    """
    return ParameterSpec(name="D", kind="int", domain=(2, 4), description="number of debaters")


def rounds_knob() -> ParameterSpec:
    """`R` -- number of rounds. Paper-named, Section 3.2 (p.572).

    Domain {2, 4} for Code Generation: Table 6's `Rounds` column (p.586), Figure 2c, Figure 4b's
    "2 rounds / 4 rounds" legend (p.571).

    NOTE the workflow boundary: Math Q/A's self-refine rounds run over {4, 6, 8} (Figure 16a,
    p.586). That is a different workflow and is deliberately NOT merged into this domain; when
    Math Q/A is un-deferred it needs its own factory rather than a widened one, or M3 will
    enumerate configurations the Code Gen evaluation never profiled.
    """
    return ParameterSpec(name="R", kind="int", domain=(2, 4), description="number of rounds")


def cores_knob() -> ParameterSpec:
    """`cores` -- number of CPU cores to run on. Paper-named, Section 3.2 (p.572).

    The paper names this knob for the OpenCV frame extraction tool; applying it to a Python
    interpreter tool is by analogy (Listing 1, p.569, likewise configures tools with
    `resources={"CPUs": 32}`). The domain below is ours -- the paper gives none.

    KNOWN DEAD-END (DESIGN.md Section 3.3, A13): `cores` can never reach the MILP. Appendix A.5
    (p.586-587) has no CPU resource: its set `G` is resource types with GPU budget `B_g` and
    per-instance cost `c_g` (A100/H100 VMs, Section 4.1 p.575), and `g_m` is the *parallelism* of
    model profile `m`. Capacity eq. (3) is denominated in tokens, the latency filter eq. (5) is
    `l^TTFT_m + t_c * l^TPOT_m`, and the objectives eqs. (11)-(12) sum over GPU instances `n_m`.
    No value of `cores` changes any of them. Murakkab's own worked example of an executor knob is
    one its own optimizer cannot consume. Reproduced as-is.
    """
    return ParameterSpec(
        name="cores",
        kind="int",
        # [DESIGN CHOICE] Enumerated, not a range: M3 must cross-multiply domains to build C_w,
        # so a domain has to be a finite list of selectable values. Upper bound 32 follows
        # Listing 1's `"CPUs": 32` (p.569) and Section 4.1's 64-core host (p.575).
        domain=(1, 2, 4, 8, 16, 32),
        description="number of CPU cores to run on",  # Section 3.2, p.572, verbatim
    )


def timeout_knob() -> ParameterSpec:
    """`timeout_s` -- per-execution wall-clock limit.

    [INVENTED -- DESIGN.md A17] The paper names exactly two tool knobs, `F` and `cores`
    (Section 3.2, p.572). This one has no counterpart anywhere in the paper; both the knob and its
    domain are ours. It exists because a code-execution tool that cannot bound a runaway candidate
    program is not a credible executor.

    Like `cores`, it is unreachable by the MILP (Appendix A.5 has no wall-clock term for tools;
    DESIGN.md Section 6.1). It is declared, shown to the orchestrator, and consumed by nobody.
    """
    return ParameterSpec(
        name="timeout_s",
        kind="int",
        domain=(5, 30, 120),  # [INVENTED] arbitrary; no paper basis
        description="wall-clock limit per execution, in seconds [INVENTED, not from the paper]",
    )


# ---------------------------------------------------------------------------------------------
# Video Q/A knobs (Milestone 2b -- DESIGN_VIDEO_QA.md Section 4.6)
# ---------------------------------------------------------------------------------------------


def frames_knob() -> ParameterSpec:
    """`F` -- number of frames to extract. Paper-named, Section 3.2 (p.572).

    The paper's own worked example of an executor knob: "the frame extraction tool exposes the
    knobs: F (number of frames to extract) and cores (number of CPU cores to run on)".

    Domain is the literal enumerated set {1, 5, 10}: Table 5's `Frames` column (p.585), Figure 2a's
    x-axis "1,N 1,Y 5,N 5,Y 10,N 10,Y" (p.570), and Figure 4a's "Size = # of frames" legend
    (p.571) all use exactly these three values.

    NOTE (DESIGN_VIDEO_QA.md A29): Listing 1 (p.569) hardcodes `params={"num_frames": 15}` -- a
    value OUTSIDE this domain. Listing 1 is the imperative straw-man, and 15 is never measured
    anywhere in the evaluation, so the literal-reproduction policy takes the measured set.
    """
    return ParameterSpec(
        name="F", kind="int", domain=(1, 5, 10), description="number of frames to extract"
    )


def video_qa_model_knob() -> ParameterSpec:
    """`model` for Video Q/A executors -- domain from Table 5 (p.585) and Figures 2a/4a.

    A SEPARATE factory from `model_knob()`, deliberately (DESIGN_VIDEO_QA.md A27). The two
    catalogues declare the same knob NAME over different domains, so M2's "one definition per
    knob" invariant weakens to "one definition per knob PER CATALOGUE". Re-parameterizing
    `model_knob(domain=...)` would have made the drift silent; two named factories make it
    inspectable.

    The same dead-end as the Code Gen `model` knob applies (DESIGN.md Section 6.2): Appendix A.5's
    `x_{w,s,c,m}` has no executor index, so per-executor model declarations collapse to one model
    per workflow configuration at M4.
    """
    return ParameterSpec(
        name="model",
        kind="enum",
        domain=VIDEO_QA_MODELS,
        description="which multi-modal LLM to use",
    )


def segment_knob() -> ParameterSpec:
    """`segment_s` -- fixed segment length, in seconds, for the interval-based segmenter.

    [INVENTED -- DESIGN_VIDEO_QA.md Section 4.2] Like `timeout_s`, this knob has no counterpart in
    the paper; both the knob and its domain are ours. It belongs to an invented executor
    (`fixed_interval_segmenter`) and, like every tool knob, can never reach the MILP: Appendix A.5
    has no CPU resource type and no wall-clock term for tools.
    """
    return ParameterSpec(
        name="segment_s",
        kind="int",
        domain=(5, 15, 30),  # [INVENTED] arbitrary; no paper basis
        description="fixed segment length in seconds [INVENTED, not from the paper]",
    )


INVENTED_KNOBS: Final[frozenset[str]] = frozenset({"timeout_s", "segment_s"})
"""Knobs with no counterpart in the paper. Machine-readable so tests and readers agree with
DESIGN.md Section 3.2's table. `model`, `D`, `R`, `cores` and `F` are all paper-named."""


NO_STT_ENABLED_KNOB = """Decision Q6 (2026-09-11) -- A18, and the reason there is no `stt_enabled`
factory in this module.

Section 3.3.1 (p.574) names "STT on/off" as a workflow-level knob and Figure 2a (p.570) plots both
halves, but Section 3.2 (p.572) attaches knobs to "each model or tool in the library". An on/off
knob DELETES a node, and no executor can own the knob that annihilates it -- the paper states a
knob it has nowhere to put.

Rather than invent a mechanism and present it as reproduction, the reproduction takes Option 5 of
DESIGN_VIDEO_QA.md Section 5: a workflow CONFIGURATION is a DAG variant. Appendix A.5 defines
`C_w` only as "workflow configurations for w" -- opaque, with `a_c`/`t_c` per configuration -- so
`C_w` for Video Q/A simply contains both the with-`stt` and without-`stt` variants and the MILP
chooses natively through `c`. No knob exists here, on `stt`, on `q_a`, or on `LogicalWorkflow`.

OBLIGATION ON MILESTONE 3: its `C_w` enumeration must prune the `stt` node, and must label that
pruning as OURS -- the paper never describes it, and Section 3.2 (p.573) says the orchestrator
produces *a* logical workflow, singular. The pruned DAG type-checks because `q_a`'s variadic port
accepts a subset of its declared element types."""
