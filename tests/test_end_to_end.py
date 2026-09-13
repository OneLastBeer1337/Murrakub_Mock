"""
Milestone 7 -- one request through all three life-cycle phases, and the HEFT gap as a number.

Every previous milestone was forbidden to read the DAG, because A.5 has no precedence constraint
and no makespan term. M7 must read it, because a workflow cannot be executed without respecting
data flow. The distinction these tests defend:

    M7 walks the DAG for DATA-FLOW CORRECTNESS.
    M7 does not schedule by the DAG for RESOURCE ALLOCATION.

And the payoff: M3's `critical_path.py` could only state the gap structurally -- which symbols
eq. (5) lacks. With an observed walk, the gap becomes a measurement, and the measurement turns out
to depend entirely on the workflow (A94).
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from development.executor_lib import code_generation_library, video_qa_library
from development.orchestrator import WorkflowOrchestrator
from execution.critique.observed_path import compare, ttft_undercount, workflow_sensitivity
from execution.workflow_run import TOOL_DURATION_S, execute, llm_invocations_for
from optimization.profiles import profile_set
from optimization.profiles.critique.tool_latency import TOOL_SERVICE_TIMES
from optimization.profiles.provenance import Unavailable
from optimization.profiles.schema import ModelProfileKey
from shared.executor import ExecutorKind
from shared.llm_client import MockLLMClient

EXECUTION = pathlib.Path(__file__).resolve().parent.parent / "execution"
VIDEO_FIXTURE = {
    "scene_detect": "opencv_scene_detector",
    "frame_extract": "omdet_frame_annotator",
    "stt": "whisper_stt",
    "q_a": "multimodal_llm_qa",
}


@pytest.fixture(scope="module")
def profiles():
    return profile_set("baseline")


def _latency(pset, key):
    mp = pset.models[key]
    ttft, tpot = mp.ttft(), mp.tpot()
    return (
        None if isinstance(ttft, Unavailable) else float(ttft.value),
        None if isinstance(tpot, Unavailable) else float(tpot.value),
    )


def _codegen(pset, tools=None):
    lib = code_generation_library()
    wf = (
        WorkflowOrchestrator(lib, MockLLMClient(mode="keyword"))
        .orchestrate_file("development/specs/code_generation.py")
        .workflow
    )
    cfg = next(
        c
        for c in pset.workflow
        if c.workflow_id == "code_generation"
        and c.knob["model"] == "DeepSeek-Qwen-32B"
        and c.knob["D"] == 4
        and c.knob["R"] == 4
    )
    key = ModelProfileKey("DeepSeek-Qwen-32B", "H100", 4)
    ttft, tpot = _latency(pset, key)
    tokens = float(pset.workflow[cfg].tokens.p90().value)
    return execute(wf, lib, cfg, key, ttft_s=ttft, tpot_s=tpot, total_tokens=tokens,
                   tool_durations=tools), ttft


def _video(pset, tools=None):
    lib = video_qa_library()
    wf = (
        WorkflowOrchestrator(lib, MockLLMClient(mode="fixture", fixture=VIDEO_FIXTURE))
        .orchestrate_file("development/specs/video_qa.py")
        .workflow
    )
    cfg = next(
        c
        for c in pset.workflow
        if c.workflow_id == "video_qa"
        and c.knob["model"] == "NVLM-D-72B"
        and c.dag_variant == "stt_on"
        and not isinstance(pset.workflow[c].tokens, Unavailable)
    )
    key = ModelProfileKey("NVLM-D-72B", "H100", 8)
    ttft, tpot = _latency(pset, key)
    tokens = float(pset.workflow[cfg].tokens.p90().value)
    return execute(wf, lib, cfg, key, ttft_s=ttft, tpot_s=tpot, total_tokens=tokens,
                   tool_durations=tools), ttft


# ---------------------------------------------------------------------------------------------
# The DAG is walked for data flow, never for allocation
# ---------------------------------------------------------------------------------------------


def test_a_node_never_starts_before_its_predecessors_finish(profiles) -> None:
    """Data-flow correctness -- the only reason M7 is allowed to read the DAG at all."""
    trace, _ = _video(profiles, tools={n: float(v.value) for n, v in TOOL_SERVICE_TIMES.items()})
    by_id = {n.task_id: n for n in trace.nodes}
    assert by_id["q_a"].start_s >= by_id["frame_extract"].end_s
    assert by_id["q_a"].start_s >= by_id["stt"].end_s
    assert by_id["frame_extract"].start_s >= by_id["scene_detect"].end_s


def test_siblings_overlap_as_section_4_6_measured(profiles) -> None:
    """Q52, overridden to concurrent.

    Section 4.6 (p.578): "The two sub-tasks run in near-perfect parallel, with full overlap in
    execution." Running them serially would contradict the paper's own measurement and disagree
    with M3's `critical_path.py`, which already computes `max(L_frames, L_stt)`.
    """
    tools = {n: float(v.value) for n, v in TOOL_SERVICE_TIMES.items()}
    trace, _ = _video(profiles, tools=tools)
    by_id = {n.task_id: n for n in trace.nodes}
    assert by_id["frame_extract"].start_s == by_id["stt"].start_s
    assert trace.overlap_saving_s > 0
    assert trace.observed_span_s < trace.serial_span_s


def test_the_allocation_is_fixed_before_the_walk_begins(profiles) -> None:
    """A81/Q46. `x_{w,s,c,m}` has ONE `m` per configuration, so every LLM node in a request runs
    on the same model profile. The walk cannot move a node elsewhere to go faster -- that would
    be scheduling, which is the thing M7 must not do."""
    trace, _ = _codegen(profiles)
    llm_models = {n.model for n in trace.nodes if n.kind is not ExecutorKind.TOOL}
    assert len(llm_models) == 1
    assert trace.model in llm_models


def test_no_scheduling_heuristic_exists_in_the_walker() -> None:
    """A critical-path or earliest-finish-time helper here would be precedence-aware allocation
    arriving by the back door. Checked on the AST, since the docstring legitimately names them."""
    tree = ast.parse((EXECUTION / "workflow_run.py").read_text(encoding="utf-8-sig"))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    names |= {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    for banned in ("critical_path", "earliest_finish", "makespan", "heft"):
        assert banned not in names, banned


def test_ties_break_on_declaration_order_not_duration(profiles) -> None:
    """Breaking ties by duration would be a scheduling rule. The tie-break is the order the
    developer wrote the sub-tasks in, which carries no optimisation intent."""
    tools = {"frame_extract": 99.0, "stt": 1.0}
    trace, _ = _video(profiles, tools=tools)
    order = [n.task_id for n in trace.nodes]
    assert order.index("frame_extract") < order.index("stt")


def test_execution_does_not_import_the_observed_path_critique() -> None:
    """Quarantine, same one-way rule as M3/M4/M6."""
    for path in EXECUTION.rglob("*.py"):
        if "critique" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "observed_path" not in node.module, path.name


# ---------------------------------------------------------------------------------------------
# A94 -- the blind spot depends on the workflow, and that IS the finding
# ---------------------------------------------------------------------------------------------


def test_the_blind_spot_is_negligible_on_code_generation(profiles) -> None:
    """`t_c` ~ 40,000 tokens, so the TPOT term swamps everything eq. (5) omits.

    This is why M7's originally-scoped workflow cannot demonstrate the HEFT gap: the defect is
    real and worth about a quarter of one percent.
    """
    trace, _ttft = _codegen(profiles, tools={"execute_tests": 0.8})
    c = compare(trace)
    assert c.eq5_s > 1000.0
    assert c.blind_spot_fraction < 0.01


def test_the_blind_spot_dominates_on_video_qa(profiles) -> None:
    """`t_c` ~ 194 tokens against three tool stages, so eq. (5) misses most of the latency.

    Same formulation, same defect, two orders of magnitude difference in what it is worth. The
    discriminator is `t_c`, which is why a single headline number would be misleading.
    """
    tools = {n: float(v.value) for n, v in TOOL_SERVICE_TIMES.items()}
    trace, _ttft = _video(profiles, tools=tools)
    c = compare(trace)
    assert c.blind_spot_fraction > 0.5
    assert c.free_stage_count == 3


def test_the_video_conclusion_survives_the_invented_band(profiles) -> None:
    """The tool magnitudes are INVENTED (Q16) with a deliberate +/-3x band, so the conclusion
    must not depend on them. At both extremes eq. (5) still misses most of the latency, which
    means the finding rests on the STRUCTURE -- small `t_c`, three tool stages."""
    fractions = []
    for scale in (1 / 3, 3.0):
        tools = {n: float(v.value) * scale for n, v in TOOL_SERVICE_TIMES.items()}
        trace, _ = _video(profiles, tools=tools)
        fractions.append(compare(trace).blind_spot_fraction)
    assert min(fractions) > 0.35, f"blind spot collapsed to {min(fractions):.0%} at the band edge"
    assert max(fractions) > 0.8


def test_the_sensitivity_is_reported_per_workflow(profiles) -> None:
    """Averaging the two would hide the only interesting thing about them."""
    tools = {n: float(v.value) for n, v in TOOL_SERVICE_TIMES.items()}
    cg, _ = _codegen(profiles, tools={"execute_tests": 0.8})
    vq, _ = _video(profiles, tools=tools)
    sensitivity = workflow_sensitivity([compare(cg), compare(vq)])
    assert set(sensitivity) == {"code_generation", "video_qa"}
    assert sensitivity["video_qa"] > 10 * sensitivity["code_generation"]


# ---------------------------------------------------------------------------------------------
# A96 -- the prefill undercount: exact, and small
# ---------------------------------------------------------------------------------------------


def test_a_debate_makes_many_invocations_and_is_charged_one_prefill(profiles) -> None:
    """A95/A96. `D=4, R=4` is 16 debate calls plus test-writing plus ranking. eq. (5) charges
    exactly one `l^TTFT_m` however many there are."""
    trace, ttft = _codegen(profiles)
    assert trace.llm_invocations == 18
    undercount = ttft_undercount(trace.llm_invocations, ttft)
    assert undercount == pytest.approx(17 * ttft)
    assert undercount > 0


def test_the_prefill_undercount_is_real_but_small(profiles) -> None:
    """A96, corrected. It is exact -- integers times a profiled value, no invented magnitude --
    and it is 0.2%-2.6% of eq. (5) wherever `t_c` is large. Worth stating, not worth leading
    with."""
    trace, ttft = _codegen(profiles)
    undercount = ttft_undercount(trace.llm_invocations, ttft)
    assert undercount / trace.eq5_s < 0.03


def test_invocation_counts_come_from_the_configuration_knobs(profiles) -> None:
    """Counted, never timed individually (Q45): timing `D x R` sub-calls needs a per-call token
    count, and A59 says no such split is published."""
    cfg = next(
        c for c in profiles.workflow
        if c.workflow_id == "code_generation" and c.knob["D"] == 2 and c.knob["R"] == 2
    )
    assert llm_invocations_for("propose_solutions", ExecutorKind.COMPOSITION, cfg) == 4
    assert llm_invocations_for("write_tests", ExecutorKind.LLM, cfg) == 1
    assert llm_invocations_for("execute_tests", ExecutorKind.TOOL, cfg) == 0


# ---------------------------------------------------------------------------------------------
# Tools, and what A.5 charges for them
# ---------------------------------------------------------------------------------------------


def test_tool_nodes_cost_the_formulation_nothing_by_default(profiles) -> None:
    """Q44. Zero IS A.5's answer -- Section 3.3 profiles "TTFT and TPOT for LLMs", so a TOOL has
    no profile, no tokens and no cost. A zero-width node in the trace states the blind spot more
    plainly than an invented duration would."""
    assert TOOL_DURATION_S == 0.0
    trace, _ = _codegen(profiles)
    for node in trace.tool_nodes:
        assert node.duration_s == 0.0
        assert "A.5 charges nothing" in node.duration_source


def test_the_invented_overlay_is_opt_in_and_marked(profiles) -> None:
    """Q16's taint must survive into the trace, so no reader mistakes it for profile data."""
    trace, _ = _codegen(profiles, tools={"execute_tests": 0.8})
    tool = trace.tool_nodes[0]
    assert tool.duration_s == pytest.approx(0.8)
    assert "INVENTED" in tool.duration_source
    assert trace.tool_durations_included


def test_apportioned_token_splits_are_labelled_ours(profiles) -> None:
    """A59: Code Generation's three LLM nodes share one published per-request total with no
    reported split. Apportioning by invocation count is OURS and every node says so."""
    trace, _ = _codegen(profiles)
    llm_nodes = [n for n in trace.nodes if n.kind is not ExecutorKind.TOOL]
    assert len(llm_nodes) == 3
    for node in llm_nodes:
        assert "[OURS]" in node.duration_source


def test_video_qa_needs_no_apportionment(profiles) -> None:
    """One LLM node, so the split is exact rather than apportioned -- which is why Video Q/A
    carries the critical-path arm and Code Generation cannot."""
    trace, _ = _video(profiles)
    llm_nodes = [n for n in trace.nodes if n.kind is not ExecutorKind.TOOL]
    assert len(llm_nodes) == 1
    assert "ONE LLM node" in llm_nodes[0].duration_source


# ---------------------------------------------------------------------------------------------
# The mock selector is load-bearing, so it is pinned
# ---------------------------------------------------------------------------------------------


def test_code_generation_executor_assignment_is_pinned(profiles) -> None:
    """Q53. The mock selector is biased (it scores overlap / description length) and its choices
    drive `llm_invocations`, hence `ttft_undercount`. Pinning the assignment does not FIX the
    bias -- the standing policy says leave it visible -- but it stops the bias being volatile:
    editing any executor description now breaks this test with a diff instead of silently moving
    a published number.
    """
    trace, _ = _codegen(profiles)
    assignment = {n.task_id: n.executor for n in trace.nodes}
    assert assignment == {
        "propose_solutions": "llm_debate_coders",
        "write_tests": "llm_unit_test_writer",
        "execute_tests": "python_interpreter",
        "rank_solutions": "llm_ranker",
    }
