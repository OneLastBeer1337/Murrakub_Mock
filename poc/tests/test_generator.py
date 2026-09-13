"""
Instance generator — well-formed, every C(t) non-empty, reproducible from the seed.

Spec: docs/design/System_Architecture_v2.md §6.4.
Covers build step 3. Owner: 083
"""

import pytest

from poc.instances.generator import generate


@pytest.mark.parametrize("seed", range(20))
def test_pools_are_never_empty(seed):
    """The generator's one hard guarantee (§6.4)."""
    inst = generate(n_tasks=8, n_profiles=4, budget_tightness=0.5, seed=seed)
    assert all(inst.pools[t.id] for t in inst.tasks)


@pytest.mark.parametrize("seed", range(10))
def test_pools_agree_with_the_floors(seed):
    inst = generate(n_tasks=8, n_profiles=4, budget_tightness=0.5, seed=seed)
    for task in inst.tasks:
        derived = sorted(m.id for m in inst.profiles.values()
                         if m.reliability >= task.rel_floor and m.latency <= task.lat_ceil)
        assert derived == inst.pools[task.id]


def test_same_seed_reproduces_exactly():
    """P10 — reproducible given a fixed seed."""
    a = generate(6, 3, 0.4, seed=7)
    b = generate(6, 3, 0.4, seed=7)
    assert a == b


def test_different_seeds_differ():
    assert generate(6, 3, 0.4, seed=7) != generate(6, 3, 0.4, seed=8)


def test_shapes_and_types():
    inst = generate(n_tasks=5, n_profiles=3, budget_tightness=0.6, seed=1)
    assert len(inst.tasks) == 5
    assert len(inst.profiles) == 3
    assert len({t.id for t in inst.tasks}) == 5, "task ids must be unique"
    assert all(p.gpus >= 1 and p.throughput > 0 and p.price > 0
               for p in inst.profiles.values())
    assert all(t.load > 0 for t in inst.tasks)


def test_budget_is_monotone_in_tightness():
    """T3 sweeps this axis; it has to move in one direction."""
    budgets = [generate(8, 4, tightness, seed=3).budget
               for tightness in (0.1, 0.25, 0.5, 0.75, 1.0)]
    assert budgets == sorted(budgets)
    assert budgets[-1] == generate(8, 4, 1.0, seed=3).reference_gpus


@pytest.mark.parametrize("seed", range(25))
@pytest.mark.parametrize("n_tasks", [4, 8, 12])
def test_tightness_of_one_is_always_feasible(seed, n_tasks):
    """The property the §6.4 anchor did not have, and the reason it was replaced.

    At the loosest setting the exact solver must find something, or T3 has no upper end
    to sweep down from. The reference allocation is achievable by construction, so a
    budget equal to it cannot be infeasible.
    """
    from poc.tracks import exact_milp
    inst = generate(n_tasks=n_tasks, n_profiles=4, budget_tightness=1.0, seed=seed)
    result = exact_milp.allocate(*inst.unpack())
    assert result.feasible, f"seed {seed}: infeasible at the loosest budget"
    assert result.gpus_used <= inst.reference_gpus


@pytest.mark.parametrize("seed", range(10))
def test_the_reference_allocation_is_itself_affordable(seed):
    """reference_gpus must describe a real allocation, not an unreachable bound."""
    from poc.tracks import exact_milp
    inst = generate(n_tasks=8, n_profiles=4, budget_tightness=1.0, seed=seed)
    assert inst.budget == inst.reference_gpus
    assert exact_milp.allocate(*inst.unpack()).feasible


@pytest.mark.parametrize("tightness", [0.0, -0.1, 3.5])
def test_rejects_tightness_outside_the_range(tightness):
    with pytest.raises(ValueError):
        generate(4, 2, tightness, seed=0)


@pytest.mark.parametrize("tightness", [1.25, 1.5, 2.0, 3.0])
def test_accepts_budgets_above_the_reference(tightness):
    """F15: the reference allocation is a cliff, not a neutral upper bound. A sweep that
    stops at 1.0 can only ever measure the cliff, so the range must extend past it."""
    inst = generate(6, 3, tightness, seed=0)
    assert inst.budget > inst.reference_gpus or tightness <= 1.0
