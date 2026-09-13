"""
select_profile — known pools with hand-computed answers; all-infeasible returns None.

Spec: docs/design/System_Architecture_v2.md §6.6.
Covers build step 6. Owner: 075
"""

import pytest

from poc.core.decision_rule import select_profile
from poc.core.provisioning import ProvisioningState
from poc.formulation.types import ProfileSpec, Task, TaskId
from poc.instances.fixtures import adversarial_3t2p as fx

TRACK_A_COST = lambda m, admit: admit.extra_cost      # noqa: E731


@pytest.fixture
def fixture():
    tasks, pools, profiles, budget = fx.build()
    return {t.id.task_name: t for t in tasks}, pools, profiles, budget


def test_picks_the_cheapest_marginal_cost(fixture):
    """t1 on an empty state: m1 costs 100, m2 costs 180."""
    tasks, pools, profiles, budget = fixture
    state = ProvisioningState(profiles, budget)
    assert select_profile(tasks["t1"], pools[tasks["t1"].id], state, TRACK_A_COST) == "m1"


def test_prefers_free_headroom_over_a_cheaper_price(fixture):
    """Once m2 is open with headroom, admitting there costs nothing at all."""
    tasks, pools, profiles, budget = fixture
    state = ProvisioningState(profiles, budget)
    state.admit(tasks["t1"], "m2")
    assert select_profile(tasks["t2"], pools[tasks["t2"].id], state, TRACK_A_COST) == "m2"


def test_returns_none_when_nothing_is_admissible(fixture):
    """B=1 affords neither a second m1 instance nor any m2 — the (C3) dead end."""
    tasks, pools, profiles, _ = fixture
    state = ProvisioningState(profiles, budget=1)
    state.admit(tasks["t1"], "m1")                    # uses the only GPU
    assert select_profile(tasks["t3"], pools[tasks["t3"].id], state, TRACK_A_COST) is None


def test_empty_pool_returns_none(fixture):
    tasks, _, profiles, budget = fixture
    state = ProvisioningState(profiles, budget)
    assert select_profile(tasks["t1"], [], state, TRACK_A_COST) is None


def test_ties_break_on_profile_id_not_iteration_order():
    """Two identical profiles must produce the same winner whichever order they arrive in.

    Ties are the common case here, not an edge case: extra_cost is 0 for every profile
    with enough headroom.
    """
    profiles = {
        "mb": ProfileSpec("mb", "generic", 10.0, 1, 100.0, 1.0, 1.0),
        "ma": ProfileSpec("ma", "generic", 10.0, 1, 100.0, 1.0, 1.0),
    }
    task = Task(TaskId("wf", "t"), "generic", 5.0, 0.0, 1e9)

    forward = select_profile(task, ["ma", "mb"], ProvisioningState(profiles, 4), TRACK_A_COST)
    reverse = select_profile(task, ["mb", "ma"], ProvisioningState(profiles, 4), TRACK_A_COST)
    assert forward == reverse == "ma"


def test_cost_adjust_is_the_seam_that_changes_the_winner(fixture):
    """Track B shifts the choice by adding a multiplier — same rule, different answer."""
    tasks, pools, profiles, budget = fixture
    state = ProvisioningState(profiles, budget)

    assert select_profile(tasks["t1"], pools[tasks["t1"].id], state, TRACK_A_COST) == "m1"

    penalise_m1 = lambda m, admit: admit.extra_cost + (500.0 if m == "m1" else 0.0)  # noqa: E731
    assert select_profile(tasks["t1"], pools[tasks["t1"].id], state, penalise_m1) == "m2"


def test_does_not_mutate_the_state(fixture):
    """The rule chooses; only admit() changes anything."""
    tasks, pools, profiles, budget = fixture
    state = ProvisioningState(profiles, budget)
    before = state.snapshot()
    select_profile(tasks["t1"], pools[tasks["t1"].id], state, TRACK_A_COST)
    assert state.snapshot() == before
