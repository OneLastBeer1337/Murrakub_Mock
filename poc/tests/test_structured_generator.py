"""
The second generator — same contract, deliberately different structure.

Owner: 083

These tests do two jobs. The first is the ordinary one: the generator must satisfy the same
guarantees as the original, or the tracks cannot consume it. The second is unusual and is
the point of the file — it asserts that this generator is genuinely DIFFERENT from the
original. A second generator that quietly produced similar instances would answer the
methodological objection it exists for without actually testing anything, and nothing else
in the suite would notice.
"""

import pytest

from poc.instances import generator as uniform
from poc.instances import structured_generator as structured
from poc.tracks import exact_milp


# --- the same contract as generator.py ------------------------------------------

@pytest.mark.parametrize("seed", range(15))
def test_pools_are_never_empty(seed):
    inst = structured.generate(n_tasks=8, n_profiles=4, budget_tightness=0.8, seed=seed)
    assert all(inst.pools[t.id] for t in inst.tasks)


@pytest.mark.parametrize("seed", range(10))
def test_pools_agree_with_the_floors(seed):
    inst = structured.generate(n_tasks=8, n_profiles=4, budget_tightness=0.8, seed=seed)
    for task in inst.tasks:
        derived = sorted(m.id for m in inst.profiles.values()
                         if m.reliability >= task.rel_floor and m.latency <= task.lat_ceil)
        assert derived == inst.pools[task.id]


@pytest.mark.parametrize("seed", range(10))
def test_tightness_of_one_is_always_feasible(seed):
    """The property the shared anchor guarantees, checked on the new distributions."""
    inst = structured.generate(n_tasks=8, n_profiles=4, budget_tightness=1.0, seed=seed)
    assert exact_milp.allocate(*inst.unpack()).feasible


def test_same_seed_reproduces_exactly():
    assert structured.generate(6, 3, 0.8, seed=5) == structured.generate(6, 3, 0.8, seed=5)


def test_does_not_reproduce_the_original_generator():
    """Same seed, same shape, different instances — the streams must not coincide."""
    a = uniform.generate(8, 4, 0.8, seed=1)
    b = structured.generate(8, 4, 0.8, seed=1)
    assert [t.load for t in a.tasks] != [t.load for t in b.tasks]
    assert {p.gpus for p in a.profiles.values()} != {p.gpus for p in b.profiles.values()} \
        or {p.throughput for p in a.profiles.values()} != {p.throughput for p in b.profiles.values()}


# --- and now: it must actually be different --------------------------------------

def _sample(mod, n=40):
    return [mod.generate(8, 4, 1.0, seed=s) for s in range(n)]


def test_large_profiles_are_worse_value_per_gpu():
    """The consequential inversion: sublinear throughput against linear price.

    In the original generator throughput and price both scale linearly with GPUs, so
    profile size is roughly value-neutral. Here bigger is actively worse per GPU, which
    changes what a good allocation looks like.
    """
    by_gpus = {}
    for inst in _sample(structured):
        for p in inst.profiles.values():
            by_gpus.setdefault(p.gpus, []).append(p.throughput / p.gpus)

    means = {g: sum(v) / len(v) for g, v in sorted(by_gpus.items())}
    assert len(means) >= 3, f"expected several GPU tiers, saw {list(means)}"
    tiers = sorted(means)
    assert means[tiers[0]] > means[tiers[-1]], (
        f"throughput per GPU must fall with size: {means}")


def test_loads_are_heavy_tailed_unlike_the_original():
    """A few tasks far larger than the rest, which is what forces a big profile open."""
    def spread(mod):
        loads = sorted(t.load for inst in _sample(mod) for t in inst.tasks)
        return loads[-1] / loads[len(loads) // 2]

    assert spread(structured) > 3 * spread(uniform), (
        f"structured {spread(structured):.1f}x vs uniform {spread(uniform):.1f}x")


def test_pool_size_distribution_differs_from_the_original():
    """Floors cluster here rather than being sprinkled, so pools are shaped differently.

    This is the test that would have caught the original bug in this file: strict tasks
    demanded top reliability AND tightest latency, which is unsatisfiable when the most
    reliable profiles are also the slowest, so every strict instance was silently
    discarded by the regeneration loop and no strict tasks ever appeared.
    """
    def distribution(mod):
        sizes = [len(inst.pools[t.id]) for inst in _sample(mod) for t in inst.tasks]
        return sum(sizes) / len(sizes)

    assert distribution(structured) != pytest.approx(distribution(uniform), abs=0.5)


def test_more_than_one_pool_size_occurs():
    """Guards the same bug from the other side: floors must actually bite sometimes."""
    sizes = {len(inst.pools[t.id]) for inst in _sample(structured) for t in inst.tasks}
    assert len(sizes) > 1, f"floors never restrict anything: pool sizes {sizes}"
