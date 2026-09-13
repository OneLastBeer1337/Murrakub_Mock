"""
The multi-move consolidation pass.

Spec: core/consolidation.py, built from findings F17. Owner: 035 / 075
"""

import pytest

from poc.core.consolidation import consolidate, consolidate_subsets, evaluate
from poc.formulation import invariants
from poc.instances import structured_generator as sg
from poc.instances.fixtures import adversarial_3t2p as fx
from poc.instances.generator import generate
from poc.tracks import (exact_milp, track_a_greedy, track_a_m1_subset, track_a_subset,
                        track_c_consolidate, track_c_lp)


def test_fixes_the_diagnosed_worst_case():
    """F17: the LP routed 7.88 load onto a 4-GPU profile because its price/throughput was
    marginally better, wasting 76% of an instance and costing twice the optimum."""
    inst = sg.generate(8, 4, 1.0, seed=3)
    tasks, pools, profiles, budget = inst.unpack()

    optimum = exact_milp.allocate(*inst.unpack()).total_cost
    plain = track_c_lp.allocate(*inst.unpack())
    fixed = track_c_consolidate.allocate(*inst.unpack())

    assert plain.total_cost > optimum * 1.9, "expected the ~100% gap this test exists for"
    assert fixed.total_cost < optimum * 1.1
    assert invariants.check(fixed, tasks, pools, profiles, budget) == []


def test_does_not_fix_the_adversarial_fixture_and_that_is_expected():
    """The neighbourhood is 'all tasks on a profile', not 'some tasks on a profile'.

    adversarial_3t2p needs t1 and t2 moved to m2 while t3 stays on m1 — a SUBSET move.
    Here t3 is eligible only for m1, so the intersection of destinations over all of m1's
    tasks is empty and no move exists. Two different multi-move neighbourhoods; this pass
    implements one of them. Recorded as a test so the limitation is not mistaken for a bug.
    """
    tasks, pools, profiles, budget = fx.build()
    greedy = track_a_greedy.allocate(tasks, pools, profiles, budget)
    after = consolidate(greedy.routing, tasks, pools, profiles, budget)

    assert evaluate(after, tasks, profiles, budget)[0] == fx.GREEDY_EXPECTED_COST


def test_subset_consolidation_fixes_adversarial_fixture():
    """Subset consolidation moves {t1, t2} to m2 together, achieving the true optimum 280.

    This directly resolves the aggregate-coupling trap that defeats plain greedy and
    single-move relocate on adversarial_3t2p.
    """
    tasks, pools, profiles, budget = fx.build()
    greedy = track_a_greedy.allocate(tasks, pools, profiles, budget)
    assert greedy.total_cost == fx.GREEDY_EXPECTED_COST  # 300

    fixed = track_a_subset.allocate(tasks, pools, profiles, budget)
    assert fixed.feasible
    assert fixed.total_cost == fx.OPTIMUM["total_cost"]  # 280!
    assert fixed.routing[fx.task_id("t1")] == "m2"
    assert fixed.routing[fx.task_id("t2")] == "m2"
    assert fixed.routing[fx.task_id("t3")] == "m1"
    assert invariants.check(fixed, tasks, pools, profiles, budget) == []

    # Verify A+M1+subset also reaches the optimum
    m1_fixed = track_a_m1_subset.allocate(tasks, pools, profiles, budget)
    assert m1_fixed.feasible
    assert m1_fixed.total_cost == fx.OPTIMUM["total_cost"]  # 280!
    assert invariants.check(m1_fixed, tasks, pools, profiles, budget) == []




@pytest.mark.parametrize("seed", range(8))
def test_never_makes_a_result_worse(seed):
    """Only strict improvements are accepted, so this must hold by construction."""
    inst = generate(8, 4, 1.0, seed=seed)
    tasks, pools, profiles, budget = inst.unpack()
    plain = track_c_lp.allocate(*inst.unpack())
    if not plain.feasible:
        pytest.skip("Track C infeasible here")
    fixed = track_c_consolidate.allocate(*inst.unpack())

    assert fixed.total_cost <= plain.total_cost + 1e-9
    assert invariants.check(fixed, tasks, pools, profiles, budget) == []


@pytest.mark.parametrize("seed", range(5))
def test_never_breaks_the_budget(seed):
    inst = sg.generate(8, 4, 0.8, seed=seed)
    tasks, pools, profiles, budget = inst.unpack()
    result = track_c_consolidate.allocate(*inst.unpack())
    if result.feasible:
        assert result.gpus_used <= budget
        assert invariants.check(result, tasks, pools, profiles, budget) == []


def test_is_deterministic():
    inst = sg.generate(8, 4, 1.0, seed=3)
    a = track_c_consolidate.allocate(*inst.unpack())
    b = track_c_consolidate.allocate(*inst.unpack())
    assert a.routing == b.routing and a.total_cost == b.total_cost


def test_leaves_the_bound_untouched():
    """A primal repair cannot change a lower bound."""
    inst = sg.generate(8, 4, 1.0, seed=3)
    plain = track_c_lp.allocate(*inst.unpack())
    fixed = track_c_consolidate.allocate(*inst.unpack())
    assert fixed.lower_bound == plain.lower_bound
