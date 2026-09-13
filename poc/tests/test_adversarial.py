"""
T2 fixtures — hand-built cases where greedy ordering misleads.

Spec: docs/design/System_Architecture_v2.md §6.6; CLAUDE.md ground-truth instance.
Covers build steps 4 and 9. Owner: 035

Two checkpoints on adversarial_3t2p, belonging to two different build steps — keep them
separate rather than merging into one test:

    step 4  exact_milp returns 280, routing {t1→m2, t2→m2, t3→m1}, n = {m1:1, m2:1}
    step 9  track_a_greedy returns 300

The second is not a bug being tolerated. Greedy returning 300 IS the T2 result. If it ever
returns 280, the myopia is not being reproduced and something is wrong with the fixture or
with cost_to_admit — that is a failure, not an improvement.
"""

import pytest

from poc.formulation import invariants
from poc.instances.fixtures import adversarial_3t2p as fx
from poc.tracks import exact_milp


@pytest.fixture
def instance():
    return fx.build()


def test_milp_finds_the_hand_computed_optimum(instance):
    """Build step 4's checkpoint. The number 280 was computed by exhaustion in CLAUDE.md."""
    tasks, pools, profiles, budget = instance
    result = exact_milp.allocate(tasks, pools, profiles, budget)

    assert result.feasible
    assert result.total_cost == fx.OPTIMUM["total_cost"]
    assert {k.task_name: v for k, v in result.routing.items()} == fx.OPTIMUM["routing"]
    assert result.provisioning == fx.OPTIMUM["provisioning"]
    assert result.gpus_used == fx.OPTIMUM["gpus_used"]
    assert invariants.check(result, tasks, pools, profiles, budget) == []


def test_milp_bound_equals_its_own_optimum(instance):
    """The exact solver's bound is the optimum — every other track's bound is measured
    against this."""
    tasks, pools, profiles, budget = instance
    result = exact_milp.allocate(tasks, pools, profiles, budget)
    assert result.lower_bound == result.total_cost


def test_the_coupling_is_what_makes_this_hard(instance):
    """t1 and t2 are individually cheaper on m1, but together they fit one m2 instance.

    Stated as a test so the fixture's point survives someone 'simplifying' the numbers.
    """
    tasks, pools, profiles, budget = instance
    m1, m2 = profiles["m1"], profiles["m2"]
    t1, t2 = fx.TASKS["t1"]["load"], fx.TASKS["t2"]["load"]

    assert m1.price < m2.price, "m1 must look cheaper to a myopic ranker"
    assert t1 + t2 <= m2.throughput, "but both tasks must fit one m2 instance"
    # routing both to m1 needs two instances; to m2 needs one
    assert -(-int(t1 + t2) // int(m1.throughput)) * m1.price > m2.price


def test_greedy_is_defeated_by_the_coupling(instance):
    """Build step 9's checkpoint: plain greedy returns 300, not 280.

    This failing upward — greedy suddenly returning 280 — is a regression, not a win. It
    would mean the myopia is no longer being reproduced, and T2's evidence is gone.
    """
    from poc.tracks import track_a_greedy
    tasks, pools, profiles, budget = instance
    result = track_a_greedy.allocate(tasks, pools, profiles, budget)

    assert result.feasible
    assert result.total_cost == fx.GREEDY_EXPECTED_COST
    assert result.provisioning == {"m1": 3}, "greedy piles everything onto m1"
    assert result.lower_bound is None, "Track A produces no bound — that is T4's question"
    assert invariants.check(result, tasks, pools, profiles, budget) == []


def test_greedy_is_valid_but_suboptimal(instance):
    """The gap is the finding. Greedy's answer is feasible and 20 more than optimal."""
    from poc.tracks import track_a_greedy
    tasks, pools, profiles, budget = instance
    greedy = track_a_greedy.allocate(tasks, pools, profiles, budget)
    optimal = exact_milp.allocate(tasks, pools, profiles, budget)

    assert greedy.total_cost > optimal.total_cost
    assert greedy.total_cost - optimal.total_cost == 20.0
    assert greedy.gpus_used <= budget


def test_track_c_recovers_the_optimum_here(instance):
    """Not guaranteed in general — recorded because it is the first T4 signal.

    On this instance the LP relaxation plus rounding finds 280 where plain greedy finds
    300. One instance is not a result, but it is the shape T4 is looking for: if the
    solver call keeps matching the optimum that the greedy machinery misses, Track A has
    to justify itself.
    """
    from poc.tracks import track_c_lp
    tasks, pools, profiles, budget = instance
    result = track_c_lp.allocate(tasks, pools, profiles, budget)

    assert result.total_cost == fx.OPTIMUM["total_cost"]
    assert result.lower_bound <= fx.OPTIMUM["total_cost"]
    assert invariants.check(result, tasks, pools, profiles, budget) == []


def test_relocate_does_not_rescue_greedy(instance):
    """T2's method step 2, run rather than asserted.

    CLAUDE.md records by hand-enumeration that single-move relocate cannot recover the
    optimum here: moving t1 alone to m2 costs +180 and saves only 100. The plan's method
    asks for it to be *run*, so it is.
    """
    from poc.tracks import track_a_relocate
    tasks, pools, profiles, budget = instance
    result = track_a_relocate.allocate(tasks, pools, profiles, budget)

    assert result.total_cost == fx.GREEDY_EXPECTED_COST, (
        "relocate recovered the optimum — if this happens, T2's conclusion that a "
        "multi-move neighbourhood is required no longer holds")
    assert invariants.check(result, tasks, pools, profiles, budget) == []
