"""
invariants.check() — hand-built valid and violating results.

Spec: docs/design/System_Architecture_v2.md §6.6.
Covers build step 2. Owner: 083

One test per invariant, each built by taking the known-optimal allocation and breaking
exactly one thing. If a test here starts failing, check() has drifted — every other test
in the suite leans on it.
"""

import pytest

from poc.formulation.invariants import check
from poc.formulation.types import AllocationResult
from poc.instances.fixtures import adversarial_3t2p as fx


@pytest.fixture
def instance():
    return fx.build()


def optimal_result():
    """The verified optimum: {t1→m2, t2→m2, t3→m1}, n={m1:1, m2:1}, 3 GPUs, cost 280."""
    return AllocationResult(
        routing={fx.task_id("t1"): "m2", fx.task_id("t2"): "m2", fx.task_id("t3"): "m1"},
        provisioning={"m1": 1, "m2": 1},
        total_cost=280.0, gpus_used=3, strategy="MILP",
    )


def test_pools_derive_from_the_floors(instance):
    """C(t) is built by construction, not asserted as a constraint (v2 §1.6)."""
    tasks, pools, profiles, _ = instance
    for task in tasks:
        derived = sorted(m.id for m in profiles.values()
                         if m.reliability >= task.rel_floor and m.latency <= task.lat_ceil)
        assert derived == sorted(pools[task.id]), task.id
    # m2 fails t3's 0.98 reliability floor — that is what forces t3 onto m1
    assert pools[fx.task_id("t3")] == ["m1"]


def test_optimal_result_is_clean(instance):
    tasks, pools, profiles, budget = instance
    assert check(optimal_result(), tasks, pools, profiles, budget) == []


def test_greedy_result_is_also_clean(instance):
    """Greedy's 300 is suboptimal but perfectly valid — invariants are not optimality."""
    tasks, pools, profiles, budget = instance
    result = AllocationResult(
        routing={fx.task_id(n): "m1" for n in ("t1", "t2", "t3")},
        provisioning={"m1": 3}, total_cost=300.0, gpus_used=3, strategy="A",
    )
    assert check(result, tasks, pools, profiles, budget) == []


def test_i1_missing_task(instance):
    tasks, pools, profiles, budget = instance
    result = optimal_result()
    del result.routing[fx.task_id("t3")]
    result.provisioning = {"m2": 1}
    assert "I1" in check(result, tasks, pools, profiles, budget)


def test_i2_underprovisioned(instance):
    """t1+t2 = 14 load on m2, thr 25 — one instance covers it, zero does not."""
    tasks, pools, profiles, budget = instance
    result = optimal_result()
    result.provisioning = {"m1": 1, "m2": 0}
    violations = check(result, tasks, pools, profiles, budget)
    assert "I2" in violations and "I5" in violations


def test_i3_over_budget(instance):
    tasks, pools, profiles, budget = instance
    result = optimal_result()
    result.provisioning = {"m1": 3, "m2": 1}       # 3·1 + 1·2 = 5 > B=4
    assert "I3" in check(result, tasks, pools, profiles, budget)


def test_i4_ineligible_profile(instance):
    """t3 on m2 breaks the reliability floor — the exact thing C(t) exists to prevent."""
    tasks, pools, profiles, budget = instance
    result = optimal_result()
    result.routing[fx.task_id("t3")] = "m2"
    result.provisioning = {"m2": 1}
    assert "I4" in check(result, tasks, pools, profiles, budget)


def test_i5_routed_profile_with_no_instances(instance):
    tasks, pools, profiles, budget = instance
    result = optimal_result()
    result.provisioning = {"m1": 1}                # m2 carries t1, t2 but is absent
    violations = check(result, tasks, pools, profiles, budget)
    assert "I5" in violations


def test_declared_failure_is_not_checked(instance):
    """feasible=False is a recorded failure, not a violating allocation."""
    from poc.formulation.types import Infeasible
    tasks, pools, profiles, budget = instance
    failure = AllocationResult.failure("A", Infeasible("over budget", None, "C3"))
    assert check(failure, tasks, pools, profiles, budget) == []
