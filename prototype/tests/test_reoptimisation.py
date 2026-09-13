"""
J9 scoped vs global re-optimisation — the O9 experiment (§3.3).

Outside PoC scope. Owner: 077.

§3.3 specifies J9 as re-invoking J3 "for affected workflows only" and then doubts whether
that is well-defined under (C2). These tests pin down the answer so it cannot drift.
"""
import dataclasses

import pytest

from poc.instances.generator import generate
from poc.tracks import exact_milp
from prototype.reoptimisation import compare, reoptimise_global, reoptimise_scoped


def _instance(seed, multiplier=1.5, n_tasks=12):
    inst = generate(n_tasks=n_tasks, n_profiles=5, budget_tightness=1.0, seed=seed)
    return dataclasses.replace(
        inst, budget=int(round(inst.reference_gpus * multiplier)))


def test_scoped_never_beats_global():
    """Global re-optimises everything, so it cannot be beaten by a restricted version.

    If this ever fails, the scoped path is not actually respecting its frozen tasks.
    """
    for seed in range(15):
        inst = _instance(seed)
        tasks, pools, profiles, budget = inst.unpack()
        base = exact_milp.allocate(tasks, pools, profiles, budget)
        if not base.feasible:
            continue
        workflows = sorted({t.id.workflow_id for t in tasks})
        if len(workflows) < 2:
            continue
        g, s = compare(exact_milp.allocate, tasks, pools, profiles, budget,
                       {workflows[0]}, base.routing)
        if s.feasible:
            assert s.total_cost >= g.total_cost - 1e-6, f"seed {seed}"


def test_scoping_narrower_than_reality_is_expensive():
    """What scoping costs when the affected set is smaller than the truth.

    This marks ONE arbitrary workflow affected, which is not how J9 is triggered — drift is
    detected on a profile, so the affected set is every workflow using it. That correct
    version is covered by test_affected_set_is_almost_the_whole_batch below, and it comes
    out identical to global.

    This test is the other bracket: it shows the penalty for under-scoping, mean ~22% on
    the instances where it bites. Together the two say scoping is either a no-op or a
    penalty, with no setting in between where it pays.
    """
    worse = comparable = 0
    for seed in range(40):
        inst = _instance(seed, multiplier=2.0)
        tasks, pools, profiles, budget = inst.unpack()
        base = exact_milp.allocate(tasks, pools, profiles, budget)
        if not base.feasible:
            continue
        workflows = sorted({t.id.workflow_id for t in tasks})
        if len(workflows) < 2:
            continue
        g, s = compare(exact_milp.allocate, tasks, pools, profiles, budget,
                       {workflows[0]}, base.routing)
        if not s.feasible:
            continue
        comparable += 1
        if s.total_cost > g.total_cost + 1e-6:
            worse += 1

    assert comparable >= 20
    assert worse >= comparable * 0.3, (
        f"only {worse}/{comparable} worse — if this drops, re-read the O9 finding")


def test_scoped_freezes_the_unaffected_workflows():
    inst = _instance(0)
    tasks, pools, profiles, budget = inst.unpack()
    base = exact_milp.allocate(tasks, pools, profiles, budget)
    workflows = sorted({t.id.workflow_id for t in tasks})
    affected = {workflows[0]}

    outcome = reoptimise_scoped(exact_milp.allocate, tasks, pools, profiles, budget,
                                affected, base.routing)
    if not outcome.feasible:
        pytest.skip("scoped infeasible on this instance")

    for task in tasks:
        if task.id.workflow_id not in affected:
            assert outcome.routing[task.id] == base.routing[task.id], "frozen task moved"


def test_no_affected_workflows_is_a_no_op():
    inst = _instance(1)
    tasks, pools, profiles, budget = inst.unpack()
    base = exact_milp.allocate(tasks, pools, profiles, budget)
    outcome = reoptimise_scoped(exact_milp.allocate, tasks, pools, profiles, budget,
                                set(), base.routing)
    assert outcome.routing == base.routing


def test_both_strategies_return_complete_allocations():
    """Complete or nothing (P9) — a partial allocation is never valid output."""
    inst = _instance(2)
    tasks, pools, profiles, budget = inst.unpack()
    base = exact_milp.allocate(tasks, pools, profiles, budget)
    workflows = sorted({t.id.workflow_id for t in tasks})
    g, s = compare(exact_milp.allocate, tasks, pools, profiles, budget,
                   {workflows[0]}, base.routing)
    for outcome in (g, s):
        if outcome.feasible:
            assert set(outcome.routing) == {t.id for t in tasks}


def test_affected_set_is_almost_the_whole_batch():
    """The corrected O9 finding: "affected workflows only" is close to vacuous.

    J9 is triggered by drift on a PROFILE, so the affected workflows are those with a task
    routed to it. Under (C2) a profile is shared, so that set is nearly everything — which
    is exactly what §3.3 suspected, arriving as vacuousness rather than as undefinedness.
    """
    fractions = []
    for seed in range(20):
        inst = _instance(seed, multiplier=2.0, n_tasks=12)
        tasks, pools, profiles, budget = inst.unpack()
        base = exact_milp.allocate(tasks, pools, profiles, budget)
        if not base.feasible:
            continue
        workflows = {t.id.workflow_id for t in tasks}
        if len(workflows) < 2:
            continue

        counts = {}
        for _, m in base.routing.items():
            counts[m] = counts.get(m, 0) + 1
        drifted = max(sorted(counts), key=lambda m: counts[m])
        affected = {tid.workflow_id for tid, m in base.routing.items() if m == drifted}
        fractions.append(len(affected) / len(workflows))

    assert fractions
    mean = sum(fractions) / len(fractions)
    assert mean > 0.8, (
        f"a drifted profile touched only {mean:.0%} of workflows; if this drops far, "
        f"scoping might actually save something and F18 needs revisiting")


def test_correctly_scoped_matches_global():
    """With the affected set derived from the drifted profile, scoping is a no-op."""
    for seed in range(12):
        inst = _instance(seed, multiplier=2.0, n_tasks=12)
        tasks, pools, profiles, budget = inst.unpack()
        base = exact_milp.allocate(tasks, pools, profiles, budget)
        if not base.feasible:
            continue
        counts = {}
        for _, m in base.routing.items():
            counts[m] = counts.get(m, 0) + 1
        drifted = max(sorted(counts), key=lambda m: counts[m])
        affected = {tid.workflow_id for tid, m in base.routing.items() if m == drifted}

        g, s = compare(exact_milp.allocate, tasks, pools, profiles, budget,
                       affected, base.routing)
        if g.feasible and s.feasible:
            assert s.total_cost == pytest.approx(g.total_cost), f"seed {seed}"
