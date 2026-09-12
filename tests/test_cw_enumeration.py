"""
`C_w` -- the configuration set of Appendix A.5 (p.586), and the [OURS] DAG pruning it forces.

Two separable claims are under test:

1. **Cardinality is exact.** |C_codegen| = 20, |C_video| = 24, |C| = 44. These are not round
   numbers chosen for convenience; they are the product of the knob domains the paper names, and
   a change to any domain has to show up here.
2. **The STT dimension is a DAG VARIANT, not a knob (A50), and pruning is legal.** The paper
   describes no pruning step, so `prune_stt` is ours. The test that makes it defensible is the
   one asserting the pruned DAG still TYPE-CHECKS against the executor library -- if `q_a`'s
   variadic port did not accept a subset of its declared sources, Option 5 would be a hack
   rather than a derivation.
"""

from __future__ import annotations

import pytest

from development.executor_lib import video_qa_library
from development.orchestrator import WorkflowOrchestrator
from optimization.profiles.enumerate_cw import (
    CODE_GEN_MODELS,
    DEAD_KNOB_DOMAINS,
    DEBATERS,
    EXPECTED_CARDINALITY,
    FRAMES,
    ROUNDS,
    STT_VARIANTS,
    VIDEO_QA_MODELS,
    PruneError,
    dag_variant_of,
    enumerate_code_generation,
    enumerate_cw,
    enumerate_video_qa,
    prune_stt,
)
from shared.llm_client import MockLLMClient
from shared.workflow import TaskRef

SPEC_PATH = "development/specs/video_qa.py"
EXPECTED_EXECUTORS = {
    "scene_detect": "opencv_scene_detector",
    "frame_extract": "omdet_frame_annotator",
    "stt": "whisper_stt",
    "q_a": "multimodal_llm_qa",
}


@pytest.fixture()
def video_workflow():
    llm = MockLLMClient(mode="fixture", fixture=EXPECTED_EXECUTORS)
    return WorkflowOrchestrator(video_qa_library(), llm).orchestrate_file(SPEC_PATH).workflow


# ---------------------------------------------------------------------------------------------
# Cardinality
# ---------------------------------------------------------------------------------------------


def test_code_generation_cardinality_is_twenty() -> None:
    configs = enumerate_code_generation()
    assert len(configs) == 20 == EXPECTED_CARDINALITY["code_generation"]
    assert len(configs) == len(DEBATERS) * len(ROUNDS) * len(CODE_GEN_MODELS)


def test_video_qa_cardinality_is_twentyfour() -> None:
    configs = enumerate_video_qa()
    assert len(configs) == 24 == EXPECTED_CARDINALITY["video_qa"]
    assert len(configs) == len(STT_VARIANTS) * len(FRAMES) * len(VIDEO_QA_MODELS)


def test_total_configuration_space_is_fortyfour() -> None:
    total = sum(len(enumerate_cw(w)) for w in EXPECTED_CARDINALITY)
    assert total == 44


def test_configurations_are_unique() -> None:
    for workflow in EXPECTED_CARDINALITY:
        configs = enumerate_cw(workflow)
        assert len(set(configs)) == len(configs), f"{workflow}: duplicate ConfigKey"


def test_config_keys_are_hashable_and_sorted() -> None:
    """`ConfigKey` is a join key across four modules, so an unstable ordering would silently
    mis-join `a_c` to `t_c`. `__post_init__` enforces sorted knobs; this checks it holds for
    every enumerated member rather than for a hand-written example."""
    for workflow in EXPECTED_CARDINALITY:
        for c in enumerate_cw(workflow):
            assert list(c.knobs) == sorted(c.knobs)
            assert hash(c) == hash(c)


def test_unknown_workflow_is_refused_with_the_deferral_reason() -> None:
    with pytest.raises(KeyError, match="deferred"):
        enumerate_cw("math_qa")


# ---------------------------------------------------------------------------------------------
# Dead knobs
# ---------------------------------------------------------------------------------------------


def test_dead_knobs_are_excluded_by_default() -> None:
    """A knob the paper never varies must not multiply `C_w`.

    This is the difference between a 44-configuration space and a 1,000+ one. The dead knobs are
    real -- the executor library declares them -- but no figure or table in either version varies
    them, so every value they could take carries identical profile data.
    """
    live = enumerate_code_generation()
    for c in live:
        for dead in DEAD_KNOB_DOMAINS:
            assert dead not in c.knob, f"{c}: dead knob {dead!r} leaked into C_w"


def test_including_dead_knobs_multiplies_but_projects_back() -> None:
    """`include_dead_knobs=True` expands the space; projecting the dead dimensions away
    recovers exactly the live set.

    This is the formal statement of "these knobs carry no information": the expansion is a
    product, and the projection is exact with no configuration gained or lost.
    """
    factor = 1
    for domain in DEAD_KNOB_DOMAINS.values():
        factor *= len(domain)
    assert factor > 1, "the point of this test is that there ARE dead knobs"

    for workflow in EXPECTED_CARDINALITY:
        live = enumerate_cw(workflow)
        expanded = enumerate_cw(workflow, include_dead_knobs=True)
        assert len(expanded) == len(live) * factor

        projected = {
            type(c)(
                workflow_id=c.workflow_id,
                knobs=tuple((k, v) for k, v in c.knobs if k not in DEAD_KNOB_DOMAINS),
                dag_variant=c.dag_variant,
            )
            for c in expanded
        }
        assert projected == set(live)


# ---------------------------------------------------------------------------------------------
# The DAG variant dimension
# ---------------------------------------------------------------------------------------------


def test_stt_is_a_dag_variant_not_a_knob() -> None:
    """A50/Q6 Option 5. `stt_enabled` appears nowhere in `knobs`."""
    for c in enumerate_video_qa():
        assert "stt_enabled" not in c.knob
        assert "STT" not in c.knob
        assert c.dag_variant in STT_VARIANTS
        assert dag_variant_of(c) == c.dag_variant


def test_code_generation_has_a_single_dag() -> None:
    for c in enumerate_code_generation():
        assert c.dag_variant == "default"


def test_each_video_configuration_appears_on_both_dag_variants() -> None:
    by_variant: dict[str, set] = {}
    for c in enumerate_video_qa():
        by_variant.setdefault(c.dag_variant, set()).add(c.knobs)
    assert set(by_variant) == set(STT_VARIANTS)
    assert by_variant["stt_on"] == by_variant["stt_off"]


# ---------------------------------------------------------------------------------------------
# Pruning -- the [OURS] obligation
# ---------------------------------------------------------------------------------------------


def test_pruning_removes_exactly_the_stt_node(video_workflow) -> None:
    pruned = prune_stt(video_workflow)
    assert {n.task_id for n in video_workflow.nodes} - {n.task_id for n in pruned.nodes} == {"stt"}
    assert len(pruned.nodes) == len(video_workflow.nodes) - 1


def test_pruned_dag_has_no_dangling_reference(video_workflow) -> None:
    pruned = prune_stt(video_workflow)
    remaining = {n.task_id for n in pruned.nodes}
    for node in pruned.nodes:
        for binding in node.inputs:
            for src in binding.sources:
                if isinstance(src, TaskRef):
                    assert src.task_id in remaining
    for edge in pruned.edges:
        assert edge.src_task in remaining and edge.dst_task in remaining


def test_pruned_dag_still_type_checks_against_the_library(video_workflow) -> None:
    """THE load-bearing assertion of Option 5, and the reason pruning is a derivation rather
    than a hack.

    `q_a` consumes `[frames, transcript]` through one variadic port. Pruning leaves it with one
    source instead of two. That is legal only because the port accepts a SUBSET of its declared
    types -- if it required both, the `stt_off` DAG would be ill-typed and the whole STT
    dimension would have to be modelled some other way. Passing the library makes the checker
    run; `prune_stt` raises `PruneError` if it fails.
    """
    pruned = prune_stt(video_workflow, library=video_qa_library())
    assert "stt" not in {n.task_id for n in pruned.nodes}
    qa = next(n for n in pruned.nodes if n.task_id == "q_a")
    sources = [s for b in qa.inputs for s in b.sources]
    assert sources, "q_a lost every input source"


def test_pruning_is_idempotent_only_once(video_workflow) -> None:
    """Pruning an already-pruned DAG is an error, not a no-op: silently succeeding would let a
    caller lose track of which variant it holds."""
    pruned = prune_stt(video_workflow)
    with pytest.raises(PruneError, match="no 'stt' node"):
        prune_stt(pruned)


def test_pruning_preserves_the_remaining_topology(video_workflow) -> None:
    """`scene_detect -> frame_extract -> q_a` must survive intact. The gap being demonstrated is
    about the PARALLEL branch; if pruning also perturbed the serial chain, any later
    critical-path comparison would be measuring our bug instead of A.5's omission."""
    pruned = prune_stt(video_workflow)
    kept = {(e.src_task, e.dst_task) for e in pruned.edges}
    original = {
        (e.src_task, e.dst_task)
        for e in video_workflow.edges
        if "stt" not in (e.src_task, e.dst_task)
    }
    assert kept == original
