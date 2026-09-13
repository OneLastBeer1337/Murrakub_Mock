"""
Regression tests for CPU profiles (profile.gpus == 0).

Verifies that pure CPU and mixed CPU/GPU profiles solve without ZeroDivisionError
across Track A, Track B, Track C, and Exact MILP (R1).
"""

import pytest

from poc.formulation import invariants
from poc.formulation.types import ProfileSpec, Task, TaskId
from poc.tracks import exact_milp, track_a_greedy, track_b_lagr, track_c_lp


@pytest.fixture
def cpu_instance():
    tasks = [
        Task(TaskId("wf1", "t1"), "cpu_task", load=6.0, rel_floor=0.90, lat_ceil=200.0),
        Task(TaskId("wf1", "t2"), "cpu_task", load=4.0, rel_floor=0.85, lat_ceil=200.0),
        Task(TaskId("wf2", "t1"), "cpu_task", load=5.0, rel_floor=0.85, lat_ceil=200.0),
    ]
    profiles = {
        "cpu-small": ProfileSpec("cpu-small", "cpu_task", throughput=10.0, gpus=0,
                                 price=30.0, reliability=0.98, latency=50.0),
        "cpu-large": ProfileSpec("cpu-large", "cpu_task", throughput=25.0, gpus=0,
                                 price=65.0, reliability=0.99, latency=35.0),
    }
    pools = {t.id: ["cpu-small", "cpu-large"] for t in tasks}
    return tasks, pools, profiles


@pytest.mark.parametrize("track_name,solver", [
    ("Track A (Greedy)", track_a_greedy.allocate),
    ("Track B (Lagrangian)", track_b_lagr.allocate),
    ("Track C (LP Relaxation)", track_c_lp.allocate),
    ("Exact MILP", exact_milp.allocate),
])
def test_pure_cpu_profiles_solve_across_all_tracks(cpu_instance, track_name, solver):
    """Pure CPU profiles must solve feasibly with zero GPU usage and no ZeroDivisionError."""
    tasks, pools, profiles = cpu_instance
    budget = 0  # Even with 0 GPU budget, CPU profiles must be fully schedulable

    result = solver(tasks, pools, profiles, budget)

    assert result.feasible, f"{track_name} failed to find feasible allocation: {result.infeasible_reason}"
    assert result.gpus_used == 0, f"{track_name} used GPUs for 0-GPU profiles"
    assert set(result.routing.keys()) == {t.id for t in tasks}

    violations = invariants.check(result, tasks, pools, profiles, budget)
    assert violations == [], f"{track_name} produced invariant violations: {violations}"


@pytest.mark.parametrize("track_name,solver", [
    ("Track A (Greedy)", track_a_greedy.allocate),
    ("Track B (Lagrangian)", track_b_lagr.allocate),
    ("Track C (LP Relaxation)", track_c_lp.allocate),
    ("Exact MILP", exact_milp.allocate),
])
def test_mixed_cpu_gpu_profiles_solve_across_all_tracks(track_name, solver):
    """Mixed CPU and GPU profiles must co-exist within budget without division errors."""
    tasks = [
        Task(TaskId("wf1", "t1"), "mixed", load=8.0, rel_floor=0.90, lat_ceil=200.0),
        Task(TaskId("wf1", "t2"), "mixed", load=12.0, rel_floor=0.90, lat_ceil=200.0),
    ]
    profiles = {
        "cpu-profile": ProfileSpec("cpu-profile", "mixed", throughput=10.0, gpus=0,
                                   price=40.0, reliability=0.98, latency=60.0),
        "gpu-profile": ProfileSpec("gpu-profile", "mixed", throughput=30.0, gpus=1,
                                   price=100.0, reliability=0.99, latency=20.0),
    }
    pools = {t.id: ["cpu-profile", "gpu-profile"] for t in tasks}
    budget = 1

    result = solver(tasks, pools, profiles, budget)

    assert result.feasible, f"{track_name} failed: {result.infeasible_reason}"
    assert result.gpus_used <= budget
    violations = invariants.check(result, tasks, pools, profiles, budget)
    assert violations == [], f"{track_name} invariant violations: {violations}"


def test_exact_milp_instance_upper_bound_cpu():
    """Unit test for exact_milp._instance_upper_bound with gpus == 0."""
    p_cpu = ProfileSpec("cpu", "type", throughput=10.0, gpus=0, price=10.0, reliability=1.0, latency=10.0)
    bound = exact_milp._instance_upper_bound(p_cpu, total_load=35.0, budget=0)
    # total_load 35.0 / 10.0 = 3.5 -> ceil = 4, + 1 = 5
    assert bound == 5


def test_track_b_profile_subproblem_cpu():
    """Unit test for track_b_lagr._solve_profile_subproblem with gpus == 0."""
    p_cpu = ProfileSpec("cpu", "type", throughput=10.0, gpus=0, price=10.0, reliability=1.0, latency=10.0)
    tasks = [Task(TaskId("w", "t1"), "type", load=5.0, rel_floor=0.9, lat_ceil=100.0)]
    lam = {tasks[0].id: 25.0}

    val, chosen, k = track_b_lagr._solve_profile_subproblem(p_cpu, tasks, lam, budget=0)
    assert k == 1
    assert len(chosen) == 1
    assert val < 0  # k*price - lambda = 1*10 - 25 = -15
