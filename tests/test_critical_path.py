"""
The Section 12.1 critique: makespan over the DAG vs Appendix A.5's eq. (5).

DESIGN.md Section 14 does not list this file. It is added because `critique/critical_path.py`
produces the milestone's headline structural finding and M4 will quote it, so leaving it
unasserted would mean the one artifact most likely to be cited is the one least protected.

The tests are shaped by what the finding actually is. It is NOT "eq. (5) understates latency by
3.35x" -- that number depends on seven invented tool service times and must never be quoted.
It is "eq. (5) has no symbol for three of the terms a critical path needs", which is checkable
without any magnitude at all. So the structural assertions are strict, and the numeric ones only
check internal consistency and that the invented inputs stay labelled.
"""

from __future__ import annotations

import pytest

from optimization.profiles.critique.critical_path import (
    CAPTION_PREFIX,
    MISSING_FROM_EQ5,
    compare_video_qa,
    eq5_seconds,
    overlap_credit,
    report,
    term_gap,
)
from optimization.profiles.critique.tool_latency import TOOL_SERVICE_TIMES
from optimization.profiles.model_profiles import build_model_profiles
from optimization.profiles.provenance import Provenance, Unavailable
from optimization.profiles.schema import ModelProfileKey
from optimization.profiles.workflow_profiles import build_video_profiles


@pytest.fixture(scope="module")
def comparisons():
    return compare_video_qa()


# ---------------------------------------------------------------------------------------------
# The structural claim -- independent of every invented magnitude
# ---------------------------------------------------------------------------------------------


def test_the_gap_is_structural_not_numeric() -> None:
    """The finding survives setting every invented number to zero.

    eq. (5) is `l^TTFT_m + t_c * l^TPOT_m`: one executor, no per-node index, no max over paths.
    No choice of tool service time -- including zero -- gives it a symbol for the parallel
    branch Section 4.6 (p.578) measures.
    """
    gap = term_gap()
    assert gap.is_structural
    assert len(gap.eq5) == 2, "eq. (5) has exactly two terms"
    assert len(gap.critical_path) > len(gap.eq5)
    assert len(MISSING_FROM_EQ5) == 4


def test_the_named_absences_are_about_symbols_not_values() -> None:
    """Each entry must describe something missing from A.5's ALGEBRA, so that a reader can
    verify it by reading the appendix rather than by trusting our arithmetic."""
    joined = " ".join(MISSING_FROM_EQ5).lower()
    assert "precedence" in joined
    assert "max over parallel paths" in joined
    assert "makespan" in joined


def test_eq5_matches_the_appendix_formula() -> None:
    """`l^TTFT_m + t_c * l^TPOT_m`, evaluated directly, must equal the module's own reading."""
    profiles = build_video_profiles()
    models = build_model_profiles()

    # Pick whatever pair the data supports rather than naming one. Llava-OneVision-7B looks like
    # the obvious choice -- it is the model Section 4.6 runs -- but it has NO TTFT at all: no
    # Figure 3 panel exists for it (A35) and no table in either version reports TTFT (A36). So
    # eq. (5) is unevaluable for exactly the model the paper's own parallelism study uses.
    checked = 0
    for key, wp in profiles.items():
        if isinstance(wp.tokens, Unavailable):
            continue
        mk = ModelProfileKey(key.knob["model"], "H100", 4)
        if mk not in models:
            continue
        mp = models[mk]
        ttft, tpot = mp.ttft(), mp.tpot()
        if isinstance(ttft, Unavailable) or isinstance(tpot, Unavailable):
            assert eq5_seconds(wp, mp) is None, f"{key}: unavailable input produced a number"
            continue
        expected = float(ttft.value) + float(wp.tokens.p90().value) * float(tpot.value)
        assert eq5_seconds(wp, mp) == pytest.approx(expected)
        checked += 1
    assert checked, "no (c, m) pair had a complete eq. (5) input"


# ---------------------------------------------------------------------------------------------
# The quarantine, restated at the point of use
# ---------------------------------------------------------------------------------------------


def test_every_tool_service_time_is_labelled_invented() -> None:
    for name, value in TOOL_SERVICE_TIMES.items():
        assert value.provenance is Provenance.INVENTED, name
        assert value.lo is not None and value.hi is not None, f"{name}: no band"
        assert value.hi / value.lo == pytest.approx(9.0), (
            f"{name}: the +/-3x band is deliberately enormous -- a tight band on a fabricated "
            "number would imply precision that does not exist"
        )


def test_every_caption_is_stamped_invented(comparisons) -> None:
    """Q16's third condition. A figure built from these numbers must say so in its caption,
    every time, without the author having to remember."""
    assert comparisons
    for c in comparisons:
        assert c.caption.startswith(CAPTION_PREFIX)
        assert "INVENTED" in c.caption


# ---------------------------------------------------------------------------------------------
# Internal consistency
# ---------------------------------------------------------------------------------------------


def test_critical_path_is_never_shorter_than_eq5(comparisons) -> None:
    """Tool stages add wall-clock and never remove it, so eq. (5) is a strict UNDER-estimate of
    the DAG's makespan here. The direction is the finding; the magnitude is not."""
    for c in comparisons:
        assert c.critical_path_seconds > c.eq5_seconds
        assert c.understatement_ratio > 1.0


def test_the_unmodelled_time_is_exactly_the_tool_time(comparisons) -> None:
    """eq. (5) charges for the LLM stage and nothing else, so the entire difference between the
    two computations must be tool wall-clock. If it were not, the comparison would be smuggling
    in some other discrepancy and the attribution would be wrong."""
    for c in comparisons:
        assert c.unmodelled_seconds == pytest.approx(c.tool_seconds)
        assert c.llm_seconds == pytest.approx(c.eq5_seconds)


def test_stt_off_configurations_drop_the_stt_branch(comparisons) -> None:
    on = [c for c in comparisons if c.stt_enabled]
    off = [c for c in comparisons if not c.stt_enabled]
    assert on and off
    for c in off:
        assert "stt" not in c.tool_node_breakdown
    for c in on:
        assert "stt" in c.tool_node_breakdown
    assert min(c.tool_seconds for c in on) > max(c.tool_seconds for c in off)


def test_the_parallel_branch_is_a_max_not_a_sum(comparisons) -> None:
    """Section 4.6 (p.578): "The two sub-tasks run in near-perfect parallel, with full overlap in
    execution". The critical path must therefore take the MAX of the two branches.

    A.5 can express neither the max nor the sum -- it has no term for these stages at all -- so
    `overlap_credit` quantifies a choice the formulation never gets to make.
    """
    on = [c for c in comparisons if c.stt_enabled]
    for c in on:
        branch = max(c.tool_node_breakdown["frame_extract"], c.tool_node_breakdown["stt"])
        assert c.tool_seconds == pytest.approx(c.tool_node_breakdown["scene_detect"] + branch)

    credit = overlap_credit(on)
    assert credit["serial_seconds_mean"] > credit["parallel_seconds_mean"]
    assert credit["credit_seconds_mean"] > 0


def test_only_coherent_pairs_are_costed(comparisons) -> None:
    """A51 lets `x_{w,s,c,m}` route a configuration onto a different model's profile entirely.
    That is a real defect and M4 will measure it -- but a critical-path figure built on an
    incoherent pair would argue two defects at once and prove neither."""
    for c in comparisons:
        assert c.config.knob["model"] == c.model.model_id


def test_code_generation_is_absent_by_construction(comparisons) -> None:
    """A59. Its three LLM nodes share one published token total with no reported split, so the
    per-node terms do not exist even in principle, and its DAG is a total order with no parallel
    branch to demonstrate the `max(...)` gap on."""
    assert all(c.config.workflow_id == "video_qa" for c in comparisons)


def test_report_is_generated_and_self_labelling() -> None:
    text = report()
    assert CAPTION_PREFIX in text
    assert "Structural: True" in text
    for missing in MISSING_FROM_EQ5:
        assert missing in text
