"""
Structural contract of the Executor Library catalogue (Milestone 2).

Covers Murakkab (OSDI '26), Section 3.2, "Executor Library" and "Attributes" (p.572):
  "Each model or tool in the library exposes three attributes: (1) a textual description, (2) an
   interface specification, and (3) a key-value list of configurable parameters."
and the hardware boundary of Section 3.3.1, Decision 3 (p.574): "A profile encodes a specific
model, GPU type, and parallelism strategy, so choosing m implicitly fixes the hardware and
parallelism degree."
"""

from __future__ import annotations

import dataclasses

import pytest

# RENAMED IN MILESTONE 2b: `GROUNDING` and `NOT_NAMED_BY_THE_PAPER` are now exported PER
# CATALOGUE. With one catalogue the bare names were unambiguous; with Video Q/A registered they
# are not, and merging the two dicts would hide which paper figure grounds which entry. Same
# forcing function as gap A27 for knob domains. The assertions below are unchanged in substance.
from development.executor_lib import (
    CODE_GENERATION_EXECUTORS,
    CODE_GENERATION_GROUNDING as GROUNDING,
    CODE_GENERATION_NOT_NAMED_BY_THE_PAPER as NOT_NAMED_BY_THE_PAPER,
    HARDWARE_LEVEL_KNOBS,
    code_generation_library,
    default_library,
)
from shared.executor import ExecutorKind, ExecutorSpec, ParameterSpec
from shared.model_ids import ALL_MODEL_IDS
from shared.types import TYPE_REGISTRY

# The five names Milestone 1 published. M2 ADDS to the catalogue; it never renames, because these
# strings are join keys for M3's profiles and appear verbatim in the orchestrator prompt.
M1_NAMES = (
    "llm_debate_coders",
    "llm_single_shot_coder",
    "llm_unit_test_writer",
    "python_interpreter",
    "llm_ranker",
)


@pytest.fixture()
def library():
    return code_generation_library()


def test_every_entry_exposes_the_three_attributes():
    """Section 3.2 (p.572), attributes (1)-(3)."""
    for executor in CODE_GENERATION_EXECUTORS:
        assert executor.description.strip()  # (1) textual description
        assert executor.inputs and len(executor.outputs) == 1  # (2) interface specification
        assert isinstance(executor.parameters, tuple)  # (3) key-value list of knobs
        assert isinstance(executor.kind, ExecutorKind)


def test_all_port_types_are_registered():
    for executor in CODE_GENERATION_EXECUTORS:
        for port in executor.inputs + executor.outputs:
            for accepted in port.accepted_types:
                assert accepted in TYPE_REGISTRY


def test_at_most_one_variadic_input_per_executor():
    for executor in CODE_GENERATION_EXECUTORS:
        assert sum(1 for p in executor.inputs if p.variadic) <= 1


def test_names_are_unique_and_stable(library):
    names = [e.name for e in CODE_GENERATION_EXECUTORS]
    assert len(names) == len(set(names))
    # Presence, NOT exclusivity: M1's assertions of an exact five-entry catalogue would now be
    # wrong, but silently dropping an M1 name would break every profile keyed on it (DESIGN.md
    # Section 2, "names are frozen once published").
    for name in M1_NAMES:
        assert library.get(name).name == name


def test_no_parameter_carries_a_value():
    """Section 3.2 (p.572) defers "parameter configuration to a later optimization phase"."""
    for executor in CODE_GENERATION_EXECUTORS:
        for parameter in executor.parameters:
            assert not hasattr(parameter, "value")


def test_parameter_spec_was_not_extended_by_milestone_2():
    """Decision Q1 (2026-09-10): the workflow/agent/hardware level is DOCUMENTATION ONLY.

    M1's approved interface is untouched -- no `level` field -- because the paper's own taxonomy
    contradicts itself (Section 2.5 p.570 vs Section 3.3.1 p.574; DESIGN.md A12) and Appendix A.5
    folds every knob into the opaque configuration `c`, so the tag would have no consumer.
    """
    assert {f.name for f in dataclasses.fields(ParameterSpec)} == {
        "name",
        "kind",
        "domain",
        "description",
    }


def test_no_executor_declares_a_hardware_knob():
    """The Section 3.3.1 Decision 3 boundary (p.574): GPU type, parallelism and instance counts
    belong to M3 model profiles, never to an executor."""
    for executor in CODE_GENERATION_EXECUTORS:
        for parameter in executor.parameters:
            assert parameter.name.lower() not in HARDWARE_LEVEL_KNOBS
            for value in parameter.domain or ():
                # a GPU name must never sneak in as a knob value either
                assert not (isinstance(value, str) and value.upper() in {"A100", "H100"})


def test_declared_knob_domains_do_not_drift_between_executors():
    """One definition per knob (`knobs.py`), so M3 cannot profile two things under one name."""
    seen: dict[str, tuple] = {}
    for executor in CODE_GENERATION_EXECUTORS:
        for parameter in executor.parameters:
            previous = seen.setdefault(parameter.name, (parameter.kind, parameter.domain))
            assert previous == (parameter.kind, parameter.domain), parameter.name


def test_grounding_covers_every_entry_and_nothing_else():
    """DESIGN.md A11: the paper names no Code Gen executors beyond Figure 1b's node labels, so
    every entry must declare how it relates to the paper."""
    assert set(GROUNDING) == {e.name for e in CODE_GENERATION_EXECUTORS}
    assert set(GROUNDING.values()) == {"PAPER", "PAPER-FORM", "INVENTED"}
    # the four Figure 1b nodes (p.568) are the only PAPER-grounded entries
    assert {n for n, g in GROUNDING.items() if g == "PAPER"} == {
        "llm_debate_coders",
        "llm_unit_test_writer",
        "python_interpreter",
        "llm_ranker",
    }
    assert len(NOT_NAMED_BY_THE_PAPER) == 9


def test_grounding_markers_never_leak_into_prompt_facing_text():
    """`description` is what the orchestrator LLM selects on (Section 3.2, p.573). Telling it
    which entries the authors invented would bias selection on a signal the real system lacks.

    `timeout_s`'s description is the deliberate exception: it is a knob, shown as a knob NAME plus
    domain, and its invented status is worth carrying (DESIGN.md A17).
    """
    for executor in CODE_GENERATION_EXECUTORS:
        assert "INVENTED" not in executor.description
        assert "PAPER" not in executor.description


def test_library_is_flat_and_finite(library):
    assert len(library) == len(CODE_GENERATION_EXECUTORS) == 13
    assert library.all() == CODE_GENERATION_EXECUTORS  # declaration order is the tie-break order

    # UPDATED IN MILESTONE 2b, exactly as this line's previous comment predicted ("today the only
    # registered catalogue is Code Generation, so these coincide"). Video Q/A is registered now,
    # so `default_library()` is a strict superset: Section 3.2 (p.572) describes ONE shared
    # library of executors, and the per-workflow view is a convenience, not the platform's model.
    from development.executor_lib import VIDEO_QA_EXECUTORS

    union = default_library().all()
    assert union == CODE_GENERATION_EXECUTORS + VIDEO_QA_EXECUTORS
    assert len({e.name for e in union}) == len(union) == 26  # no name collides across catalogues


def test_unknown_executor_raises(library):
    from development.errors import UnknownExecutorError

    with pytest.raises(UnknownExecutorError):
        library.get("gpt-9-omni")


def test_catalogue_contains_no_performance_data():
    """Accuracy, latency, energy, cost and token counts are Milestone 3 (Section 3.3, p.573).

    An `ExecutorSpec` has nowhere to put them, and no free-text field may smuggle one in.
    """
    assert {f.name for f in dataclasses.fields(ExecutorSpec)} == {
        "name",
        "kind",
        "description",
        "inputs",
        "outputs",
        "parameters",
    }
    banned = ("accuracy", "pass@1", "tpot", "ttft", "tokens/", "watt", "wh ", "$", "latency of")
    for executor in CODE_GENERATION_EXECUTORS:
        text = executor.description.lower()
        for token in banned:
            assert token not in text


def test_model_ids_are_names_only():
    """`shared/model_ids.py` is a vocabulary, not a profile: M3 attaches the numbers."""
    assert all(isinstance(name, str) for name in ALL_MODEL_IDS)
