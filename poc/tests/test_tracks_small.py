"""
Tracks vs the exact optimum by exhaustion, on instances small enough to enumerate.

Spec: docs/design/System_Architecture_v2.md §6.6 (component + bound levels).
Covers build step 4 now; steps 7-9 as the tracks land. Owner: 089

The brute-force optimum here is independent of PuLP, so this is a real check on the MILP
encoding rather than the solver agreeing with itself. Everything else in the PoC is
measured against the MILP, so if the encoding is wrong, every later result is wrong
quietly.
"""

import itertools
import math

import pytest

from poc.formulation import invariants
from poc.instances.generator import generate
from poc.tracks import (exact_milp, static_baseline, track_a_greedy,
                        track_a_m1, track_c_lp)


def brute_force(tasks, pools, profiles, budget):
    """Enumerate every routing. Returns (cost, routing) or (None, None) if infeasible."""
    best_cost, best_routing = None, None
    task_ids = [t.id for t in tasks]
    load_of = {t.id: t.load for t in tasks}

    for combo in itertools.product(*[pools[tid] for tid in task_ids]):
        routing = dict(zip(task_ids, combo))
        load = {}
        for tid, m in routing.items():
            load[m] = load.get(m, 0.0) + load_of[tid]
        n = {m: math.ceil(round(l / profiles[m].throughput, 9)) for m, l in load.items()}
        gpus = sum(c * profiles[m].gpus for m, c in n.items())
        if gpus > budget:
            continue
        cost = sum(c * profiles[m].price for m, c in n.items())
        if best_cost is None or cost < best_cost - 1e-9:
            best_cost, best_routing = cost, routing

    return best_cost, best_routing


@pytest.mark.parametrize("seed", range(12))
@pytest.mark.parametrize("tightness", [0.35, 0.6, 1.0])
def test_milp_matches_brute_force(seed, tightness):
    inst = generate(n_tasks=6, n_profiles=3, budget_tightness=tightness, seed=seed)
    tasks, pools, profiles, budget = inst.unpack()

    expected_cost, _ = brute_force(tasks, pools, profiles, budget)
    result = exact_milp.allocate(tasks, pools, profiles, budget)

    if expected_cost is None:
        assert not result.feasible, "brute force found nothing; MILP claims a solution"
        assert result.infeasible.constraint == "C3"
        return

    assert result.feasible, f"brute force found {expected_cost}; MILP reported infeasible"
    assert result.total_cost == pytest.approx(expected_cost), (
        f"MILP {result.total_cost} != exhaustive optimum {expected_cost}")
    assert invariants.check(result, tasks, pools, profiles, budget) == []


@pytest.mark.parametrize("seed", range(5))
def test_milp_result_is_internally_consistent(seed):
    """Reported cost and GPUs must follow from the provisioning it returns."""
    inst = generate(n_tasks=7, n_profiles=4, budget_tightness=0.7, seed=seed)
    tasks, pools, profiles, budget = inst.unpack()
    result = exact_milp.allocate(tasks, pools, profiles, budget)
    if not result.feasible:
        pytest.skip("infeasible at this tightness")

    assert result.total_cost == pytest.approx(
        sum(c * profiles[m].price for m, c in result.provisioning.items()))
    assert result.gpus_used == sum(
        c * profiles[m].gpus for m, c in result.provisioning.items())
    assert result.gpus_used <= budget


def test_infeasible_names_the_binding_constraint():
    """A budget too small for any allocation must be reported, not crashed on (§4.1)."""
    inst = generate(n_tasks=6, n_profiles=3, budget_tightness=1.0, seed=2)
    tasks, pools, profiles, _ = inst.unpack()
    result = exact_milp.allocate(tasks, pools, profiles, budget=1)

    if result.feasible:
        pytest.skip("budget=1 happens to be satisfiable for this instance")
    assert result.infeasible.constraint == "C3"
    assert not result.routing and not result.provisioning


# --- heuristic tracks vs ground truth (build steps 7 and 9) ----------------------

HEURISTICS = [("A", track_a_greedy), ("A+M1", track_a_m1),
              ("C", track_c_lp), ("STATIC", static_baseline)]


@pytest.mark.parametrize("name,track", HEURISTICS)
@pytest.mark.parametrize("seed", range(10))
@pytest.mark.parametrize("tightness", [0.35, 0.6, 1.0])
def test_heuristic_never_beats_the_optimum_and_never_violates(name, track, seed, tightness):
    """The two things a heuristic is not allowed to do: undercut the optimum, or lie.

    Costing less than the exact optimum means the result is infeasible in a way the
    invariants missed, so both halves of this matter.
    """
    inst = generate(n_tasks=6, n_profiles=3, budget_tightness=tightness, seed=seed)
    tasks, pools, profiles, budget = inst.unpack()

    optimal = exact_milp.allocate(tasks, pools, profiles, budget)
    result = track.allocate(tasks, pools, profiles, budget)

    assert invariants.check(result, tasks, pools, profiles, budget) == []

    if not result.feasible:
        return          # a heuristic may fail where the exact solver succeeds; that is data

    assert optimal.feasible, f"Track {name} found a solution where the MILP found none"
    assert result.total_cost >= optimal.total_cost - 1e-6, (
        f"Track {name} returned {result.total_cost} below the optimum {optimal.total_cost}")


@pytest.mark.parametrize("seed", range(10))
@pytest.mark.parametrize("tightness", [0.35, 0.6, 1.0])
def test_track_c_bound_is_a_valid_lower_bound(seed, tightness):
    """The LP bound must never exceed the true optimum. This is the T1 comparison's
    reference point — Track B's bound is judged against it."""
    inst = generate(n_tasks=6, n_profiles=3, budget_tightness=tightness, seed=seed)
    tasks, pools, profiles, budget = inst.unpack()

    optimal = exact_milp.allocate(tasks, pools, profiles, budget)
    result = track_c_lp.allocate(tasks, pools, profiles, budget)

    if not (optimal.feasible and result.lower_bound is not None):
        return
    assert result.lower_bound <= optimal.total_cost + 1e-6, (
        f"LP bound {result.lower_bound} exceeds the optimum {optimal.total_cost}")


@pytest.mark.parametrize("name,track", HEURISTICS)
def test_tracks_are_deterministic(name, track):
    """P10 — same inputs, same output, every time."""
    inst = generate(n_tasks=7, n_profiles=4, budget_tightness=0.5, seed=11)
    tasks, pools, profiles, budget = inst.unpack()

    first = track.allocate(tasks, pools, profiles, budget, seed=0)
    second = track.allocate(tasks, pools, profiles, budget, seed=0)
    assert first.routing == second.routing
    assert first.provisioning == second.provisioning
    assert first.total_cost == second.total_cost


@pytest.mark.parametrize("name,track", HEURISTICS + [("MILP", exact_milp)])
def test_empty_pool_is_reported_as_c1(name, track):
    """An unservable task names itself and (C1), rather than crashing (§4.1)."""
    inst = generate(n_tasks=4, n_profiles=3, budget_tightness=1.0, seed=1)
    tasks, pools, profiles, budget = inst.unpack()
    blocked = tasks[0].id
    pools = dict(pools)
    pools[blocked] = []

    result = track.allocate(tasks, pools, profiles, budget)
    assert not result.feasible
    assert result.infeasible.constraint == "C1"
    assert result.infeasible.blocking_task == blocked


# --- the ground truth itself (build step 4) --------------------------------------

@pytest.mark.parametrize("seed", range(15))
@pytest.mark.parametrize("tightness", [0.6, 0.8, 1.0])
def test_the_instance_cap_never_binds(seed, tightness, monkeypatch):
    """exact_milp caps n[m] to bound CBC's search. If that cap were ever tighter than the
    optimum needs, CBC would return a suboptimal answer and call it optimal.

    Solving the same instance with a deliberately generous cap must not change the cost.
    Everything in the PoC is measured against this solver, so a silent cap is the worst
    bug available here.
    """
    inst = generate(n_tasks=8, n_profiles=4, budget_tightness=tightness, seed=seed)
    tasks, pools, profiles, budget = inst.unpack()

    tight = exact_milp.allocate(tasks, pools, profiles, budget)

    monkeypatch.setattr(exact_milp, "_instance_upper_bound",
                        lambda profile, total_load, b: b // profile.gpus)
    generous = exact_milp.allocate(tasks, pools, profiles, budget)

    assert tight.feasible == generous.feasible
    if tight.feasible:
        assert tight.total_cost == pytest.approx(generous.total_cost)


@pytest.mark.parametrize("seed", range(30))
def test_milp_matches_brute_force_on_feasible_instances(seed):
    """The wider cross-check, on the tightness where instances actually solve.

    Independent of PuLP entirely — if the encoding drifts, this is what catches it.
    """
    inst = generate(n_tasks=6, n_profiles=3, budget_tightness=1.0, seed=seed)
    tasks, pools, profiles, budget = inst.unpack()

    expected, _ = brute_force(tasks, pools, profiles, budget)
    result = exact_milp.allocate(tasks, pools, profiles, budget)

    assert result.feasible
    assert expected is not None
    assert result.total_cost == pytest.approx(expected)


def test_milp_reports_whether_optimality_was_proven():
    """CBC has no default time limit and will grind unboundedly on a hard instance — a
    statistics run had to be killed after an hour. A limit is now set, which means a solve
    can return an unproven incumbent, and that must never be mistaken for the optimum.
    """
    inst = generate(n_tasks=6, n_profiles=3, budget_tightness=1.0, seed=0)
    result = exact_milp.allocate(*inst.unpack())
    assert result.converged is True, "a small instance must solve to proven optimality"
    assert result.lower_bound == result.total_cost


def test_an_unproven_milp_result_is_not_used_as_ground_truth():
    """With a time limit of zero CBC cannot prove anything. Whatever comes back must not be
    treated as an optimum by the harness, or every gap measured against it is wrong."""
    from poc.harness.runner import run_conditions

    inst = generate(n_tasks=8, n_profiles=4, budget_tightness=1.0, seed=1)
    tasks, pools, profiles, budget = inst.unpack()

    unproven = exact_milp.allocate(tasks, pools, profiles, budget, time_limit=0)
    if unproven.feasible and unproven.converged is False:
        assert unproven.lower_bound is None, "an unproven incumbent is not a lower bound"

    record = run_conditions(inst, strategies=["MILP", "C"])
    if record.conditions["MILP"].result.converged is False:
        assert record.optimum is None
        assert not record.solvable
