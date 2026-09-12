"""
Knob declarations: names, domains, and the boundaries around them.

Covers Murakkab (OSDI '26), Section 3.2, "Attributes" (p.572): "the frame extraction tool exposes
the knobs: F (number of frames to extract) and cores (number of CPU cores to run on). The LLM
Debate composition exposes the knobs: D (number of debaters), R (number of rounds), and model
(which LLM to use)", with domains read off Table 6 (p.586) and Figures 2c/2d (p.570) / 4b (p.571).
"""

from __future__ import annotations

from development.executor_lib import (
    CODE_GENERATION_EXECUTORS,
    INVENTED_KNOBS,
    KNOB_LEVELS,
    code_generation_library,
)
from shared.model_ids import CODE_GEN_MODELS

MODEL_KNOB_HOLDERS = tuple(
    e.name for e in CODE_GENERATION_EXECUTORS if "model" in e.parameter_names
)


def test_debate_composition_exposes_exactly_the_papers_three_knobs():
    """Section 3.2 (p.572), verbatim knob set for the LLM Debate composition."""
    debate = code_generation_library().get("llm_debate_coders")
    assert debate.parameter_names == ("D", "R", "model")


def test_debaters_and_rounds_domains_are_the_literal_set_from_table_6():
    """Table 6 (p.586) `Agents` and `Rounds` columns are both in {2, 4}; Figure 2c (p.570) sweeps
    D=2/4 x R=2/4; Figure 4b (p.571) likewise. Declared as an enumerated set, not a range
    (DESIGN.md A21) -- so there is no D=1, hence `llm_single_shot_coder` as its own entry."""
    for executor in CODE_GENERATION_EXECUTORS:
        for parameter in executor.parameters:
            if parameter.name in {"D", "R"}:
                assert parameter.domain == (2, 4), (executor.name, parameter.name)
    assert "llm_single_shot_coder" in {e.name for e in CODE_GENERATION_EXECUTORS}


def test_model_domain_is_the_five_model_code_gen_set():
    """Decision Q4 (2026-09-10): Figure 4b's full plotted space (five models), not Table 6's four
    chosen ones -- a knob domain is an input space, so baking in the paper's own outcome would beg
    the question at M4 (DESIGN.md A16)."""
    assert CODE_GEN_MODELS == (
        "DeepSeek-Qwen-32B",
        "Gemma-3-27B",
        "Phi-4",
        "NVLM-D-72B",
        "DeepSeek-Llama-70B",  # Figure 4b only; never a chosen Table 6 row
    )
    for executor in CODE_GENERATION_EXECUTORS:
        for parameter in executor.parameters:
            if parameter.name == "model":
                assert parameter.domain == CODE_GEN_MODELS


def test_nine_executors_declare_a_model_knob_and_the_milp_can_honour_one():
    """DESIGN.md Section 6.2 / PROGRESS.md M1 gap, pinned in a test so it cannot be forgotten.

    Section 3.2 attribute (3) and Section 3.3.1 Decision 2 (p.574, "the chosen model or tool for
    each executor") both require a per-executor model knob. But every Appendix A.5 decision
    variable is `x_{w,s,c,m}` -- workflow, SLO tier, whole-workflow configuration, and ONE model.
    There is no executor index in the formulation, and Table 6 (p.586) reports a single `Model`
    per configuration row. So these nine declarations collapse to one at M4.

    Reproduced, not repaired. This test asserts the declaration exists; the collapse is
    documented, and M4 must log it rather than invent a node index.
    """
    assert len(MODEL_KNOB_HOLDERS) == 9
    assert set(MODEL_KNOB_HOLDERS) >= {"llm_debate_coders", "llm_unit_test_writer", "llm_ranker"}


def test_compositions_expose_one_model_knob_not_a_per_agent_list():
    """Decision Q2 (2026-09-10): keep the paper's singular `model`.

    Section 2.2 (p.569) says agents "may employ the same or different LLMs", but Section 3.2's
    knob set is singular and Table 6 has one `Model` column. Intra-composition heterogeneity is
    describable in prose and not declarable in the knobs (DESIGN.md A15, Section 6.3). A `models`
    tuple would be a repair; barred by the reproduce-literally policy.
    """
    for executor in CODE_GENERATION_EXECUTORS:
        assert "models" not in executor.parameter_names
        assert sum(1 for p in executor.parameters if p.name == "model") <= 1


def test_cores_is_paper_named_and_timeout_is_marked_invented():
    """`cores` is Section 3.2's own example knob (p.572); `timeout_s` has no counterpart anywhere
    in the paper (DESIGN.md A17). Both are unreachable by the MILP -- Appendix A.5 has no CPU
    resource type and no wall-clock term for tools (Section 6.1)."""
    # UPDATED IN MILESTONE 2b: `segment_s` joins the set (an invented knob on the invented
    # `fixed_interval_segmenter`). Still an EXACT set assertion -- the point is that the inventory
    # of inventions is closed and matches the design docs, not that it has one element.
    assert INVENTED_KNOBS == frozenset({"timeout_s", "segment_s"})
    interpreter = code_generation_library().get("python_interpreter")
    assert interpreter.parameter_names == ("cores", "timeout_s")
    timeout = next(p for p in interpreter.parameters if p.name == "timeout_s")
    assert "INVENTED" in timeout.description  # identifiable from the source alone


def test_knob_levels_documents_every_declared_knob():
    """Decision Q1: the three-level taxonomy of Section 2.5 (p.570) / Section 3.3.1 (p.574) is
    recorded as documentation, not as a field. It must still be complete."""
    declared = {p.name for e in CODE_GENERATION_EXECUTORS for p in e.parameters}
    assert declared <= set(KNOB_LEVELS)
    assert KNOB_LEVELS["D"] == KNOB_LEVELS["R"] == "workflow"  # Section 3.3.1 Decision 1
    assert KNOB_LEVELS["model"] == "agent"  # Section 2.5
    # Section 3.2 exposes `cores` as an executor knob while Section 2.5 calls CPU allocation
    # hardware-level: the paper sits on both sides of its own boundary (DESIGN.md A12/A13).
    assert KNOB_LEVELS["cores"] == "hardware-exposed-as-executor"


def test_a_tool_only_workflow_would_expose_no_model_knob_at_all():
    """The degenerate configuration that Appendix A.5 prices at zero (DESIGN.md Section 6.1)."""
    library = code_generation_library()
    tool_stages = ("property_test_generator", "test_pass_rate_ranker", "python_interpreter")
    for name in tool_stages:
        assert "model" not in library.get(name).parameter_names
