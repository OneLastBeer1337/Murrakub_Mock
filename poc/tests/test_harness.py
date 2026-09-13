"""
Harness — reproduces a known result end-to-end, under matched inputs.

Spec: docs/design/System_Architecture_v2.md §4.7, §6.1.
Covers build step 10. Owner: 089

The end-to-end check is the fixture: whatever the harness does to the tracks, MILP must
still come out at 280 and greedy at 300.
"""

import pytest

from poc.harness import metrics
from poc.harness.runner import STRATEGIES, UNAVAILABLE, run_conditions, sweep
from poc.instances.fixtures import adversarial_3t2p as fx
from poc.instances.generator import ProblemInstance, generate

# Track B runs ~1.7s per instance against microseconds for the others, so the sweep tests
# name the conditions they actually need. Track B's own correctness lives in
# test_track_b.py; test_track_b_integrates_with_the_harness below covers the wiring.
FAST = ["MILP", "STATIC", "A", "A+M1", "C", "C2"]


@pytest.fixture
def fixture_instance():
    tasks, pools, profiles, budget = fx.build()
    return ProblemInstance(tasks=tasks, pools=pools, profiles=profiles, budget=budget,
                           reference_gpus=budget, seed=0, budget_tightness=1.0)


def test_reproduces_the_known_result_end_to_end(fixture_instance):
    """Build step 10's checkpoint, expressed against the hand-verified fixture."""
    record = run_conditions(fixture_instance)

    assert record.optimum == 280.0
    assert record.conditions["MILP"].cost == 280.0
    assert record.conditions["A"].cost == 300.0
    assert record.conditions["C"].cost == 280.0
    assert all(not c.violations for c in record.conditions.values())


def test_every_condition_gets_the_identical_instance(fixture_instance):
    """Matched conditions (§4.7). A comparison across different problems is not a
    comparison, and the failure would be invisible in the output."""
    record = run_conditions(fixture_instance)
    for condition in record.conditions.values():
        assert record.instance is fixture_instance
        assert condition.result.gpus_used <= fixture_instance.budget


def test_unknown_condition_names_why_it_is_missing():
    """Asking for a condition that does not exist should say why, not just fail.

    MURAKKAB is the interesting case: it is absent not because it is unbuilt but because
    §1's formulation IS Murakkab's model, so the MILP condition already is it. A second
    entry would report the same number twice and imply a comparison that does not exist.
    """
    inst = generate(4, 3, 1.0, seed=0)
    with pytest.raises(ValueError, match="MILP"):
        run_conditions(inst, strategies=["MILP", "MURAKKAB"])
    assert "MURAKKAB" in UNAVAILABLE
    assert "MURAKKAB" not in STRATEGIES


def test_all_five_evaluation_conditions_are_present():
    """§4.7 names Tracks A, B, C, a static baseline and the exact MILP. Plus A+M1, which
    §4.7 does not name — it is the M1 analogue kept separate so T4 can price it."""
    for condition in ("MILP", "STATIC", "A", "A+M1", "B", "C", "C2"):
        assert condition in STRATEGIES, condition


def test_track_c_gets_the_same_single_attempt_as_track_a():
    """T4 fairness (findings F6). C must be single-shot; C2 carries the extra attempt."""
    from poc.tracks import track_c_lp, track_c_multi
    inst = generate(8, 4, 0.8, seed=3)
    tasks, pools, profiles, budget = inst.unpack()

    single = track_c_lp.allocate(tasks, pools, profiles, budget)
    multi = track_c_multi.allocate(tasks, pools, profiles, budget)

    assert single.strategy == "C" and multi.strategy == "C2"
    if single.feasible and multi.feasible:
        assert multi.total_cost <= single.total_cost + 1e-6, (
            "more attempts must never produce a worse answer")


def test_gap_is_none_without_an_optimum(fixture_instance):
    record = run_conditions(fixture_instance)
    assert metrics.gap_to_optimum(record.conditions["A"].result, None) is None
    assert metrics.gap_to_optimum(record.conditions["A"].result, 280.0) == pytest.approx(
        (300 - 280) / 280 * 100)


def test_greedy_has_no_bound_gap(fixture_instance):
    """Track A produces no bound — that absence is T4's question, not a missing feature."""
    record = run_conditions(fixture_instance)
    assert metrics.bound_gap(record.conditions["A"].result, 280.0) is None
    assert metrics.bound_gap(record.conditions["C"].result, 280.0) > 0


def test_summary_excludes_unsolvable_instances():
    """A gap against an unknown optimum is not a number."""
    records = sweep(n_tasks=6, n_profiles=3, tightness_values=[0.3, 1.0],
                    seeds=range(6), strategies=FAST)
    summaries = metrics.summarise(records)
    solvable = sum(1 for r in records if r.solvable)

    assert solvable < len(records), "expected some instances to be unsolvable at 0.3"
    for summary in summaries.values():
        assert summary.instances == solvable


def test_infeasible_runs_are_counted_not_averaged():
    """A track that only solves the easy instances must not post the best mean gap."""
    records = sweep(n_tasks=8, n_profiles=4, tightness_values=[0.8],
                    seeds=range(15), strategies=FAST)
    summaries = metrics.summarise(records)

    for summary in summaries.values():
        assert summary.feasible + summary.infeasible == summary.instances
        if summary.infeasible:
            assert summary.infeasible_pct > 0

    assert summaries["MILP"].infeasible == 0
    assert summaries["MILP"].mean_gap_pct == pytest.approx(0.0)
    assert summaries["MILP"].optimal == summaries["MILP"].instances


def test_solvability_is_monotone_in_tightness():
    """The T3 view. Loosening the budget can only ever help."""
    tightness = [0.5, 0.7, 0.9, 1.0]
    records = sweep(n_tasks=8, n_profiles=4, tightness_values=tightness,
                    seeds=range(10), strategies=FAST)
    counts = metrics.solvability(records)

    solvable = [counts[t][0] for t in tightness]
    assert solvable == sorted(solvable), counts
    assert counts[1.0][0] == counts[1.0][1], "tightness 1.0 must be fully solvable"


def test_no_track_ever_violates_an_invariant_across_a_sweep():
    """The highest-value test in the PoC (§6.6), run over the whole sweep at once."""
    records = sweep(n_tasks=7, n_profiles=4, tightness_values=[0.6, 0.8, 1.0],
                    seeds=range(10), strategies=FAST)
    offenders = [(r.instance.seed, name, c.violations)
                 for r in records for name, c in r.conditions.items() if c.violations]
    assert offenders == []


def test_table_renders_without_an_optimum_column_lie():
    records = sweep(n_tasks=6, n_profiles=3, tightness_values=[1.0],
                    seeds=range(5), strategies=FAST)
    table = metrics.format_table(metrics.summarise(records))
    assert "MILP" in table and "infeas" in table
    assert len(table.splitlines()) == 2 + len(metrics.summarise(records))


def test_track_b_integrates_with_the_harness():
    """One small B-inclusive run, so the wiring is covered without paying for it 150 times.

    The bound comparison this makes possible is T1's actual question, so it is asserted
    here as well as in test_track_b.py.
    """
    records = sweep(n_tasks=5, n_profiles=3, tightness_values=[1.0], seeds=range(3),
                    strategies=["MILP", "B", "C"])
    for record in records:
        if not record.solvable:
            continue
        b, c = record.conditions["B"].result, record.conditions["C"].result
        assert not record.conditions["B"].violations
        if b.lower_bound is not None:
            assert b.lower_bound <= record.optimum + 1e-6
        if b.lower_bound is not None and c.lower_bound is not None:
            assert b.lower_bound >= c.lower_bound - 1e-6, "Lagrangian bound below LP bound"


def test_scale_sweep_clears_the_anchor_cliff():
    """F15: at budget_multiplier 1.0 the tracks fall off a cliff that is not about scale.

    The default must sit above the reference allocation, or every scale study measures the
    cliff instead of the scaling.
    """
    from poc.harness.runner import scale_sweep

    tight = scale_sweep([(24, 6)], range(3), strategies=["A"], budget_multiplier=1.0)
    loose = scale_sweep([(24, 6)], range(3), strategies=["A"], budget_multiplier=1.25)

    tight_ok = sum(1 for r in tight if r.conditions["A"].feasible)
    loose_ok = sum(1 for r in loose if r.conditions["A"].feasible)
    assert loose_ok >= tight_ok, "loosening the budget must never reduce feasibility"


def test_scale_sweep_results_go_through_metrics():
    """The bias guard: every condition must be scored over the same instance set.

    The first scale runs were ad-hoc scripts that averaged each condition over whichever
    instances it happened to solve, which flatters whichever track fails most (F16).
    Routing through summarise() makes that structurally impossible.
    """
    from poc.harness.runner import scale_sweep

    records = scale_sweep([(16, 6), (24, 6)], range(2),
                          strategies=["MILP", "A", "A+M1", "C"])
    summaries = metrics.summarise(records)
    solvable = sum(1 for r in records if r.solvable)

    assert solvable > 0
    for summary in summaries.values():
        assert summary.instances == solvable, (
            f"{summary.condition} scored over {summary.instances} of {solvable}")
        assert summary.feasible + summary.infeasible == summary.instances


def test_sweep_supports_tightness_above_reference():
    """T3 sweep must cleanly support budget tightness > 1.0 past the cliff edge."""
    tightness = [0.8, 1.0, 1.25, 1.5]
    records = sweep(n_tasks=6, n_profiles=3, tightness_values=tightness,
                    seeds=range(3), strategies=["MILP", "A", "A+subset", "B-C3", "C"])
    counts = metrics.solvability(records)

    for t in tightness:
        assert t in counts
        if t >= 1.0:
            assert counts[t][0] == counts[t][1], f"expected fully solvable at tightness {t}"

