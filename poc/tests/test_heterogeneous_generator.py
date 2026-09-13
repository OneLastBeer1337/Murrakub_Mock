"""
The third generator — a local, owned, heterogeneous fleet.

Owner: 083

Same two jobs as test_structured_generator.py: the ordinary contract, plus assertions that
this generator is genuinely different from the two that came before it.

The difference here is not stylistic. This generator exists to close F31, which found that
both existing generators tie price to GPU count and so measure (C3) where it barely binds. If
these instances quietly carried the same correlation, the finding would appear closed while
nothing had changed — and no other test in the suite would notice. So the correlation is
asserted directly, in both directions: near zero here, near one there.
"""

import numpy as np
import pytest

from poc.formulation import invariants
from poc.instances import generator as uniform
from poc.instances import heterogeneous_generator as het
from poc.instances import structured_generator as structured
from poc.tracks import exact_milp


# --- the same contract as the other two generators ------------------------------

@pytest.mark.parametrize("seed", range(15))
def test_pools_are_never_empty(seed):
    inst = het.generate(n_tasks=8, n_profiles=4, budget_tightness=0.8, seed=seed)
    assert all(inst.pools[t.id] for t in inst.tasks)


@pytest.mark.parametrize("seed", range(10))
def test_pools_agree_with_the_floors(seed):
    inst = het.generate(n_tasks=8, n_profiles=4, budget_tightness=0.8, seed=seed)
    for task in inst.tasks:
        derived = sorted(m.id for m in inst.profiles.values()
                         if m.reliability >= task.rel_floor and m.latency <= task.lat_ceil)
        assert derived == inst.pools[task.id]


@pytest.mark.parametrize("seed", range(10))
def test_tightness_of_one_is_always_feasible(seed):
    """The property the shared anchor guarantees, checked on the new distributions."""
    inst = het.generate(n_tasks=8, n_profiles=4, budget_tightness=1.0, seed=seed)
    assert exact_milp.allocate(*inst.unpack()).feasible


@pytest.mark.parametrize("seed", range(8))
def test_the_exact_solver_produces_a_valid_result(seed):
    inst = het.generate(n_tasks=8, n_profiles=4, budget_tightness=1.0, seed=seed)
    tasks, pools, profiles, budget = inst.unpack()
    result = exact_milp.allocate(tasks, pools, profiles, budget, seed=0)
    assert result.feasible
    assert invariants.check(result, tasks, pools, profiles, budget) == []


def test_same_seed_reproduces_exactly():
    a = het.generate(n_tasks=10, n_profiles=5, budget_tightness=0.7, seed=3)
    b = het.generate(n_tasks=10, n_profiles=5, budget_tightness=0.7, seed=3)
    assert [t.load for t in a.tasks] == [t.load for t in b.tasks]
    assert {k: v.price for k, v in a.profiles.items()} == \
           {k: v.price for k, v in b.profiles.items()}
    assert a.budget == b.budget


def test_rejects_an_out_of_range_tightness():
    with pytest.raises(ValueError):
        het.generate(n_tasks=4, n_profiles=2, budget_tightness=0.0, seed=0)
    with pytest.raises(ValueError):
        het.generate(n_tasks=4, n_profiles=2, budget_tightness=3.5, seed=0)


# --- the reason this generator exists: F31 --------------------------------------

def _mean_correlation(generate, seeds=range(30), n_profiles=8):
    values = []
    for seed in seeds:
        inst = generate(n_tasks=16, n_profiles=n_profiles,
                        budget_tightness=1.0, seed=seed)
        c = het.price_gpu_correlation(inst.profiles)
        if c is not None:
            values.append(c)
    assert values
    return float(np.mean(values))


def test_price_is_decorrelated_from_gpu_count():
    """The whole point. F31: both existing generators sit at ~0.95-1.0.

    Asserted loosely (|corr| < 0.35) rather than at the measured ~0.04, so ordinary
    distributional drift does not fail the suite — but a regression to a per-GPU price rate
    would push this back toward 1.0 and trip it immediately.
    """
    assert abs(_mean_correlation(het.generate)) < 0.35


def test_the_other_generators_really_do_correlate():
    """The other half of the claim, asserted rather than assumed.

    Without this, `test_price_is_decorrelated_from_gpu_count` could pass because the metric
    is broken rather than because the generator is different.
    """
    assert _mean_correlation(uniform.generate) > 0.8
    assert _mean_correlation(structured.generate) > 0.8


def test_price_per_gpu_varies_across_the_fleet():
    """Cost per GPU must span a real range — that is what makes (C3) non-redundant.

    If every profile cost the same per GPU, the budget would be a rescaling of the objective
    no matter how the counts were drawn.
    """
    rates = []
    for seed in range(20):
        inst = het.generate(n_tasks=16, n_profiles=8, budget_tightness=1.0, seed=seed)
        rates += [p.price / p.gpus for p in inst.profiles.values()]
    assert max(rates) / min(rates) > 3.0


def test_no_hardware_class_dominates_on_value():
    """Throughput per unit price must not be monotone in price.

    If it were, 'always pick the cheapest class' would solve the routing and the instances
    would be trivial in a way the existing generators are not.
    """
    seen: dict[str, list[float]] = {}
    for seed in range(40):
        inst = het.generate(n_tasks=16, n_profiles=8, budget_tightness=1.0, seed=seed)
        for p in inst.profiles.values():
            seen.setdefault(p.declared_type, []).append(p.throughput / p.price)

    assert set(seen) == {"legacy", "mainstream", "frontier"}
    means = {k: float(np.mean(v)) for k, v in seen.items()}
    # Best value is legacy, but legacy is also the slowest and least reliable, so it cannot
    # simply be preferred. Assert the ordering the module docstring claims.
    assert means["legacy"] > means["mainstream"] > means["frontier"]


def test_frontier_nodes_are_small_and_legacy_nodes_are_large():
    """The anti-correlation between class and node size.

    This is the mechanism that drives corr(price, gpus) to zero; without it the correlation
    survives at roughly 0.5-0.6 because price still rises with count inside each class.
    """
    sizes: dict[str, set[int]] = {}
    for seed in range(40):
        inst = het.generate(n_tasks=16, n_profiles=8, budget_tightness=1.0, seed=seed)
        for p in inst.profiles.values():
            sizes.setdefault(p.declared_type, set()).add(p.gpus)
    assert max(sizes["frontier"]) < min(sizes["legacy"])
