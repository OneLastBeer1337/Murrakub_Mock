"""
ProvisioningState — admit sequences, headroom arithmetic, budget rejection,
snapshot/restore round-trip.

Spec: docs/design/System_Architecture_v2.md §6.6.
Covers build step 5. Owner: 083

cost_to_admit is the operation everything else leans on, so these tests are written
against numbers computed by hand in CLAUDE.md rather than against the implementation.
"""

import pytest

from poc.core.provisioning import ProvisioningState
from poc.formulation.types import ProfileSpec, Task, TaskId
from poc.instances.fixtures import adversarial_3t2p as fx


@pytest.fixture
def fixture():
    tasks, pools, profiles, budget = fx.build()
    return {t.id.task_name: t for t in tasks}, profiles, budget


@pytest.fixture
def state(fixture):
    _, profiles, budget = fixture
    return ProvisioningState(profiles, budget)


def test_empty_state(state):
    assert state.build_provisioning() == {}
    assert state.gpus_used() == 0
    assert state.total_cost() == 0.0
    assert state.instances("m1") == 0


def test_cost_to_admit_matches_the_hand_trace(fixture, state):
    """CLAUDE.md: 't1: m1 costs 100 (open 1 instance), m2 costs 180 -> picks m1'."""
    tasks, _, _ = fixture
    on_m1 = state.cost_to_admit(tasks["t1"], "m1")
    on_m2 = state.cost_to_admit(tasks["t1"], "m2")

    assert (on_m1.extra_instances, on_m1.extra_gpus, on_m1.extra_cost) == (1, 1, 100.0)
    assert (on_m2.extra_instances, on_m2.extra_gpus, on_m2.extra_cost) == (1, 2, 180.0)


def test_headroom_then_second_admit(fixture, state):
    """CLAUDE.md: 't2: m1 headroom 2 < 6 -> +1 instance = 100'."""
    tasks, _, _ = fixture
    state.admit(tasks["t1"], "m1")

    assert state.instances("m1") == 1
    assert state.headroom("m1") == pytest.approx(2.0)      # 1*10 - 8

    admit = state.cost_to_admit(tasks["t2"], "m1")
    assert (admit.extra_instances, admit.extra_cost) == (1, 100.0)


def test_headroom_absorbs_a_task_for_free(fixture, state):
    """extra_instances == 0 when existing headroom covers the task — the whole point."""
    tasks, _, _ = fixture
    state.admit(tasks["t1"], "m2")                          # load 8 on thr 25

    assert state.headroom("m2") == pytest.approx(17.0)
    admit = state.cost_to_admit(tasks["t2"], "m2")          # load 6 <= 17
    assert admit.extra_instances == 0
    assert admit.extra_cost == 0.0
    assert admit.extra_gpus == 0


def test_marginal_cost_depends_on_what_came_before(fixture, state):
    """The same task on the same profile prices differently depending on state.

    This is the aggregate-coupling problem stated as an assertion.
    """
    tasks, _, _ = fixture
    fresh = state.cost_to_admit(tasks["t2"], "m2").extra_cost
    state.admit(tasks["t1"], "m2")
    after = state.cost_to_admit(tasks["t2"], "m2").extra_cost

    assert fresh == 180.0 and after == 0.0


def test_instances_are_derived_from_load(fixture):
    """n[m] = ceil(load/thr), checked at both exact-fit boundaries.

    Cumulative load after each admit: 10.0 exactly fills one instance; a hair over forces
    a second; 20.0 exactly still fits two. That last one is the case float error would
    break, turning a full instance into a third one nobody is paying for.
    """
    profiles = {"m": ProfileSpec("m", "generic", throughput=10.0, gpus=1, price=1.0,
                                 reliability=1.0, latency=1.0)}
    state = ProvisioningState(profiles, budget=99)
    for i, (load, cumulative, expected) in enumerate(
            [(10.0, 10.0, 1), (0.001, 10.001, 2), (9.999, 20.0, 2)]):
        state.admit(Task(TaskId("wf", f"t{i}"), "generic", load, 0.0, 1e9), "m")
        assert state.load("m") == pytest.approx(cumulative)
        assert state.instances("m") == expected, (cumulative, expected)


def test_budget_rejection_returns_none(fixture):
    """(C3) rejection. B=1 cannot afford m2, which needs 2 GPUs."""
    tasks, profiles, _ = fixture
    state = ProvisioningState(profiles, budget=1)
    assert state.cost_to_admit(tasks["t1"], "m2") is None
    assert state.cost_to_admit(tasks["t1"], "m1") is not None


def test_admit_over_budget_raises(fixture):
    tasks, profiles, _ = fixture
    state = ProvisioningState(profiles, budget=1)
    with pytest.raises(ValueError, match="budget"):
        state.admit(tasks["t1"], "m2")


def test_release_is_the_exact_inverse_of_admit(fixture, state):
    """Including giving back an instance the task alone had forced open."""
    tasks, _, _ = fixture
    before = state.snapshot()
    state.admit(tasks["t1"], "m1")
    assert state.build_provisioning() == {"m1": 1}
    state.release(tasks["t1"], "m1")

    assert state.snapshot() == before
    assert state.build_provisioning() == {}
    assert state.gpus_used() == 0


def test_release_leaves_no_stranded_instance(fixture, state):
    """Admit three, release one, and the count must follow the remaining load."""
    tasks, _, _ = fixture
    for name in ("t1", "t2"):
        state.admit(tasks[name], "m1")
    assert state.instances("m1") == 2                       # ceil(14/10)
    state.release(tasks["t2"], "m1")
    assert state.instances("m1") == 1                       # ceil(8/10), not 2


def test_snapshot_restore_round_trip(fixture, state):
    tasks, _, _ = fixture
    state.admit(tasks["t1"], "m1")
    snap = state.snapshot()

    state.admit(tasks["t2"], "m1")
    state.admit(tasks["t3"], "m1")
    assert state.total_cost() == 300.0

    state.restore(snap)
    assert state.total_cost() == 100.0
    assert state.routing() == {tasks["t1"].id: "m1"}


def test_snapshot_is_not_a_live_view(fixture, state):
    tasks, _, _ = fixture
    snap = state.snapshot()
    state.admit(tasks["t1"], "m1")
    assert snap["load"]["m1"] == 0.0, "snapshot must not alias the live state"


def test_double_admit_raises(fixture, state):
    tasks, _, _ = fixture
    state.admit(tasks["t1"], "m1")
    with pytest.raises(ValueError, match="already admitted"):
        state.admit(tasks["t1"], "m2")


def test_release_of_a_task_that_was_never_admitted_raises(fixture, state):
    tasks, _, _ = fixture
    with pytest.raises(ValueError, match="not admitted"):
        state.release(tasks["t1"], "m1")


def test_float_load_does_not_drift(fixture):
    """Repeated admit/release of fractional loads must return to exactly zero."""
    profiles = {"m": ProfileSpec("m", "generic", 10.0, 1, 1.0, 1.0, 1.0)}
    state = ProvisioningState(profiles, budget=99)
    task = Task(TaskId("wf", "t"), "generic", 0.1, 0.0, 1e9)
    for _ in range(50):
        state.admit(task, "m")
        state.release(task, "m")
    assert state.load("m") == 0.0
    assert state.instances("m") == 0
