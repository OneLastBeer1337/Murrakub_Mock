"""
The HEFT/precedence critique -- DESIGN.md Section 10, and the prohibition M4 obeys.

M4 adds no precedence constraint and no makespan term, because A.5 has neither. Its only
obligation is to record, from the optimizer's side, the operands that
`profiles/critique/critical_path.py` needs to set eq. (5)'s single number beside a real critical
path over the DAG.

THE PROHIBITION IS THE POINT. `tool_stage_count` is derived from the CONFIGURATION KEY -- the
`stt_on`/`stt_off` variant -- and never from graph structure. That lets M4 record the size of its
own blind spot without reading the thing it is forbidden to read.
"""

from __future__ import annotations

import pytest

from optimization.milp import Objective, no_budget, solve
from optimization.milp.critique.structural_record import build_record, tool_stage_count
from optimization.profiles.enumerate_cw import enumerate_code_generation, enumerate_video_qa
from optimization.profiles.profile_sets import baseline
from optimization.profiles.schema import SloMix


def _run(slo_type="accuracy", tier="good"):
    pset = baseline(SloMix.section_4_2(slo_type, tier))
    return solve(pset, "video_qa", (slo_type, tier), Objective.ENERGY, no_budget())


# ---------------------------------------------------------------------------------------------
# The blind spot is counted without reading a DAG
# ---------------------------------------------------------------------------------------------


def test_tool_stage_count_comes_from_the_configuration_key() -> None:
    """Video Q/A's `stt_off` variant drops a stage, and that is visible in `dag_variant` alone.

    If this ever needed `LogicalWorkflow.edges`, M4 would be violating Section 10.1's
    prohibition in order to describe it -- which would be self-defeating.
    """
    on = [c for c in enumerate_video_qa() if c.dag_variant == "stt_on"][0]
    off = [c for c in enumerate_video_qa() if c.dag_variant == "stt_off"][0]
    assert tool_stage_count(on) == 3
    assert tool_stage_count(off) == 2
    assert tool_stage_count(enumerate_code_generation()[0]) == 1


def test_the_record_reports_the_blind_spot_in_words() -> None:
    """The claim is structural: these stages contribute exactly zero to eq. (5) and A.5 has no
    term in which their wall-clock could appear."""
    record = _run().structural_record
    note = record.blind_spot_note()
    assert "zero" in note
    assert "no per-node sum" in note and "no max over parallel branches" in note
    assert "makespan" in note


def test_the_latency_model_is_declared_single_stream() -> None:
    """Stated as data so a report cannot quietly omit the qualifier."""
    assert _run().structural_record.latency_model_is_single_stream


# ---------------------------------------------------------------------------------------------
# The operands are recorded so eq. (5) can be recomputed by hand
# ---------------------------------------------------------------------------------------------


def test_selected_pairs_carry_the_three_operands_of_eq5() -> None:
    """`l^TTFT_m`, `t_c`, `l^TPOT_m` -- so a reviewer holding Table 5 can redo the arithmetic."""
    record = _run().structural_record
    assert record.selected, "an optimal run must record what it selected"
    for pair in record.selected:
        assert pair.t_c > 0
        assert pair.mass > 0
        assert pair.recomputable


def test_recomputable_shows_the_arithmetic_or_says_why_not() -> None:
    """A62: for Llava-OneVision-7B no TTFT exists anywhere, so eq. (5) is not evaluable at all.
    The record must distinguish "not evaluable" from "evaluated to something"."""
    record = _run().structural_record
    for pair in record.selected:
        if pair.l_ttft is None:
            assert "not evaluable" in pair.recomputable
        else:
            assert "=" in pair.recomputable


def test_slack_is_none_when_no_threshold_applies() -> None:
    """On an accuracy run, eq. (5) has no threshold to be slack against (A68/Q24): `tau` is an
    accuracy, and comparing it to a latency would be dimensional nonsense."""
    record = _run("accuracy", "good").structural_record
    for pair in record.selected:
        if pair.eq5_value is None:
            assert pair.slack is None


def test_the_record_is_empty_for_a_structurally_infeasible_run() -> None:
    record = _run("latency", "best").structural_record
    assert record.selected == ()


# ---------------------------------------------------------------------------------------------
# The handoff to M3's critical-path module
# ---------------------------------------------------------------------------------------------


def test_the_record_is_consumable_by_the_critical_path_comparison() -> None:
    """M3 owns the other half of the comparison. This asserts the shapes line up, so the figure
    can be produced without either side reaching into the other."""
    from optimization.profiles.critique.critical_path import term_gap

    record = _run().structural_record
    gap = term_gap()
    assert gap.is_structural
    # eq. (5) has two terms; the critical path has more, and the difference is what the record's
    # tool_stage_count measures.
    assert len(gap.critical_path) > len(gap.eq5)
    assert record.tool_stage_count > 0


def test_build_record_tolerates_missing_latency_data() -> None:
    """Half the point of the record is describing runs where eq. (5) could not be evaluated."""
    from optimization.profiles.enumerate_cw import enumerate_video_qa

    c = enumerate_video_qa()[0]
    record = build_record(
        workflow="video_qa",
        slo=("latency", "good"),
        x={(c, "m"): 1.0},
        t_c={c: 100.0},
        l_ttft={},
        l_tpot={},
        eq5={},
        tau=None,
    )
    assert len(record.selected) == 1
    assert "not evaluable" in record.selected[0].recomputable


def test_zero_mass_pairs_are_not_recorded() -> None:
    """Only what the optimizer actually chose is part of the comparison."""
    c = enumerate_video_qa()[0]
    record = build_record(
        workflow="video_qa",
        slo=("accuracy", "good"),
        x={(c, "m"): 0.0},
        t_c={c: 100.0},
        l_ttft={},
        l_tpot={},
        eq5={},
        tau=None,
    )
    assert record.selected == ()
