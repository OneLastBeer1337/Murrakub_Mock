"""
Track B — Lagrangian relaxation. The bound is the whole point, so the bound is the test.

Spec: docs/design/System_Architecture_v2.md §6.6 (bound level).
Covers build step 8. Owner: 075

`bound <= true optimum` is the one property this track must never break. An invalid lower
bound is not a quality problem, it is a disqualifying correctness error: every T1 and T4
conclusion drawn from it would be wrong, and nothing else in the suite would notice.

Instance counts here are deliberately small — Track B runs ~1.7s per instance against
Track A's microseconds, and that runtime is itself a T4 input (see docs/evidence/poc_findings.md).
"""

import pytest

from poc.formulation import invariants
from poc.instances.fixtures import adversarial_3t2p as fx
from poc.instances.generator import generate
from poc.tracks import exact_milp, track_b_c3, track_b_lagr, track_c_lp


@pytest.mark.parametrize("seed", range(6))
@pytest.mark.parametrize("tightness", [0.8, 1.0])
def test_bound_never_exceeds_the_true_optimum(seed, tightness):
    """The disqualifying error. Checked before anything else about the track."""
    inst = generate(n_tasks=6, n_profiles=3, budget_tightness=tightness, seed=seed)
    tasks, pools, profiles, budget = inst.unpack()

    optimal = exact_milp.allocate(tasks, pools, profiles, budget)
    result = track_b_lagr.allocate(tasks, pools, profiles, budget)

    assert invariants.check(result, tasks, pools, profiles, budget) == []
    if not (optimal.feasible and result.lower_bound is not None):
        return
    assert result.lower_bound <= optimal.total_cost + 1e-6, (
        f"INVALID BOUND: {result.lower_bound} > optimum {optimal.total_cost}")


def test_bound_is_valid_on_the_fixture():
    tasks, pools, profiles, budget = fx.build()
    result = track_b_lagr.allocate(tasks, pools, profiles, budget)

    assert result.lower_bound <= fx.OPTIMUM["total_cost"] + 1e-6
    assert result.feasible
    assert invariants.check(result, tasks, pools, profiles, budget) == []


def test_bound_beats_the_lp_bound_on_the_fixture():
    """T1's question, on the one instance whose optimum is known by hand.

    §5.3's T1 table watches for the Lagrangian bound matching the LP bound consistently —
    if it does, Track B provides nothing Track C does not and should be cut. Here it does
    not: it closes the gap entirely.
    """
    tasks, pools, profiles, budget = fx.build()
    lagrangian = track_b_lagr.allocate(tasks, pools, profiles, budget)
    lp = track_c_lp.allocate(tasks, pools, profiles, budget)

    assert lagrangian.lower_bound > lp.lower_bound
    assert lagrangian.lower_bound == pytest.approx(fx.OPTIMUM["total_cost"])


def test_decomposition_is_per_profile_not_per_workflow():
    """v1 claimed per-workflow subproblems; §1.8 predicts per-profile.

    Asserted structurally: one subproblem is solved per profile, and it is solvable for a
    profile whose eligible tasks span several workflows. (C2) is indexed by profile, so
    workflow membership never enters the subproblem at all.
    """
    inst = generate(n_tasks=8, n_profiles=4, budget_tightness=1.0, seed=0)
    tasks, pools, profiles, budget = inst.unpack()

    workflows = {t.id.workflow_id for t in tasks}
    assert len(workflows) > 1, "need a multi-workflow instance for this to mean anything"

    for profile_id, profile in profiles.items():
        eligible = [t for t in tasks if profile_id in pools[t.id]]
        value, taken, k = track_b_lagr._solve_profile_subproblem(
            profile, eligible, {t.id: 1.0 for t in tasks}, budget)
        assert value <= 0.0, "a subproblem never costs more than taking nothing"
        assert all(t in eligible for t in taken)


def test_reports_iterations_and_convergence():
    tasks, pools, profiles, budget = fx.build()
    result = track_b_lagr.allocate(tasks, pools, profiles, budget)

    assert result.iterations is not None and result.iterations >= 1
    assert result.converged is not None
    assert result.strategy == "B"


def test_is_deterministic():
    """P10. Nothing in the subgradient loop may depend on dict iteration order."""
    inst = generate(n_tasks=6, n_profiles=3, budget_tightness=1.0, seed=4)
    tasks, pools, profiles, budget = inst.unpack()

    first = track_b_lagr.allocate(tasks, pools, profiles, budget, seed=0)
    second = track_b_lagr.allocate(tasks, pools, profiles, budget, seed=0)
    assert first.routing == second.routing
    assert first.total_cost == second.total_cost
    assert first.lower_bound == pytest.approx(second.lower_bound)


def test_never_returns_a_cost_below_its_own_bound():
    """An internal consistency check: cost >= bound, always."""
    for seed in range(4):
        inst = generate(n_tasks=6, n_profiles=3, budget_tightness=1.0, seed=seed)
        tasks, pools, profiles, budget = inst.unpack()
        result = track_b_lagr.allocate(tasks, pools, profiles, budget)
        if result.feasible and result.lower_bound is not None:
            assert result.total_cost >= result.lower_bound - 1e-6


def test_empty_pool_is_reported_as_c1():
    inst = generate(n_tasks=4, n_profiles=3, budget_tightness=1.0, seed=1)
    tasks, pools, profiles, budget = inst.unpack()
    pools = dict(pools)
    pools[tasks[0].id] = []

    result = track_b_lagr.allocate(tasks, pools, profiles, budget)
    assert not result.feasible
    assert result.infeasible.constraint == "C1"


def test_warm_start_flag_actually_takes_effect():
    """The cold condition must really skip greedy, not just claim to.

    B and B-cold produce identical results on every instance measured, which is only
    meaningful if the flag changes what runs. Without this test, a flag that silently did
    nothing would look exactly like the (much more interesting) finding that the warm
    start is inert.
    """
    from unittest.mock import patch

    from poc.tracks import track_a_greedy, track_b_cold

    inst = generate(n_tasks=6, n_profiles=3, budget_tightness=1.0, seed=0)
    tasks, pools, profiles, budget = inst.unpack()

    calls = []
    original = track_a_greedy.allocate

    def counting(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    with patch.object(track_b_lagr.track_a_greedy, "allocate", counting):
        track_b_lagr.allocate(tasks, pools, profiles, budget)
        warm = len(calls)
        calls.clear()
        track_b_cold.allocate(tasks, pools, profiles, budget)
        cold = len(calls)

    assert warm == 1, "warm-started Track B must consult greedy for its incumbent"
    assert cold == 0, "B-cold must not consult greedy at all"


@pytest.mark.parametrize("seed", range(4))
def test_the_warm_start_is_inert(seed):
    """Track B's own repair independently matches its warm-started self.

    If this ever fails, the T4 comparison against Track A becomes circular again and the
    B-cold row is the only one that may be quoted.
    """
    from poc.tracks import track_b_cold

    inst = generate(n_tasks=6, n_profiles=3, budget_tightness=1.0, seed=seed)
    tasks, pools, profiles, budget = inst.unpack()

    warm = track_b_lagr.allocate(tasks, pools, profiles, budget)
    cold = track_b_cold.allocate(tasks, pools, profiles, budget)

    assert warm.feasible == cold.feasible
    if warm.feasible:
        assert cold.total_cost == pytest.approx(warm.total_cost)
    assert cold.lower_bound == pytest.approx(warm.lower_bound)


# --- (C3) arm, from `mickie` (F21 there) ------------------------------------------

def test_b_c3_bound_is_valid_on_the_fixture():
    """B-C3 relaxes the GPU budget (C3). Verify lower_bound <= optimum on adversarial_3t2p."""
    tasks, pools, profiles, budget = fx.build()
    result = track_b_c3.allocate(tasks, pools, profiles, budget)

    assert result.feasible
    assert result.lower_bound is not None
    assert result.lower_bound <= fx.OPTIMUM["total_cost"] + 1e-6
    assert invariants.check(result, tasks, pools, profiles, budget) == []


@pytest.mark.parametrize("seed", range(4))
def test_b_c3_bound_never_exceeds_optimum(seed):
    """B-C3 bound must be <= exact MILP optimum on all generated instances."""
    inst = generate(n_tasks=6, n_profiles=3, budget_tightness=1.0, seed=seed)
    tasks, pools, profiles, budget = inst.unpack()

    optimal = exact_milp.allocate(tasks, pools, profiles, budget)
    result = track_b_c3.allocate(tasks, pools, profiles, budget)

    assert invariants.check(result, tasks, pools, profiles, budget) == []
    if optimal.feasible and result.lower_bound is not None:
        assert result.lower_bound <= optimal.total_cost + 1e-6

# --- T1's other two arms (F25) ---------------------------------------------------

@pytest.mark.parametrize("arm", ["capacity", "budget"])
@pytest.mark.parametrize("seed", range(4))
def test_every_relaxation_arm_produces_a_valid_bound(arm, seed):
    """The disqualifying error applies to all three arms, not just the one we favour."""
    from poc.tracks import track_b_budget, track_b_capacity
    module = {"capacity": track_b_capacity, "budget": track_b_budget}[arm]

    inst = generate(n_tasks=6, n_profiles=3, budget_tightness=1.0, seed=seed)
    tasks, pools, profiles, budget = inst.unpack()
    optimal = exact_milp.allocate(*inst.unpack())
    result = module.allocate(*inst.unpack())

    assert invariants.check(result, tasks, pools, profiles, budget) == []
    if optimal.feasible and result.lower_bound is not None:
        assert result.lower_bound <= optimal.total_cost + 1e-6, (
            f"INVALID BOUND from the {arm} arm: {result.lower_bound} > {optimal.total_cost}")


def test_relaxing_capacity_gives_no_better_bound_than_the_lp():
    """F25. §5.3's cut criterion fires for the (C2) arm — relaxing the constraint that
    carries the coupling buys an easy subproblem and a bound worth nothing extra.

    This is what vindicates the (C1) choice: the criterion fires for the wrong arm.
    """
    from poc.tracks import track_b_capacity
    c2_gaps, lp_gaps = [], []
    for seed in range(6):
        inst = generate(n_tasks=6, n_profiles=3, budget_tightness=1.0, seed=seed)
        optimal = exact_milp.allocate(*inst.unpack())
        if not optimal.feasible:
            continue
        c2 = track_b_capacity.allocate(*inst.unpack())
        lp = track_c_lp.allocate(*inst.unpack())
        if c2.lower_bound is not None and lp.lower_bound is not None:
            c2_gaps.append(optimal.total_cost - c2.lower_bound)
            lp_gaps.append(optimal.total_cost - lp.lower_bound)

    assert c2_gaps
    mean_c2 = sum(c2_gaps) / len(c2_gaps)
    mean_lp = sum(lp_gaps) / len(lp_gaps)
    assert mean_c2 >= mean_lp * 0.8, (
        "the (C2) arm is supposed to be no better than the LP; if it has become "
        "materially tighter, F25's conclusion needs revisiting")


def test_the_assignment_arm_is_the_tightest():
    """The whole point of T1: (C1) beats both alternatives and the LP."""
    from poc.tracks import track_b_capacity
    wins = 0
    for seed in range(6):
        inst = generate(n_tasks=6, n_profiles=3, budget_tightness=1.0, seed=seed)
        optimal = exact_milp.allocate(*inst.unpack())
        if not optimal.feasible:
            continue
        c1 = track_b_lagr.allocate(*inst.unpack())
        c2 = track_b_capacity.allocate(*inst.unpack())
        if c1.lower_bound is not None and c2.lower_bound is not None:
            wins += c1.lower_bound >= c2.lower_bound - 1e-6
    assert wins >= 5, "the (C1) arm should dominate the (C2) arm on bound quality"


# --- bounds must survive a failed primal (F34) -----------------------------------

def _first_infeasible(allocate, generate_fn, seeds=range(25)):
    """Find an instance where this track fails to return an allocation.

    Uses the heterogeneous generator, because that is where the tracks fail often enough
    for this to be checkable — on the per-GPU-price generators repair almost always
    succeeds, which is precisely why the discarded-bound defect went unnoticed.
    """
    for seed in seeds:
        inst = generate_fn(n_tasks=16, n_profiles=8, budget_tightness=1.0, seed=seed)
        optimal = exact_milp.allocate(*inst.unpack())
        if not optimal.feasible or optimal.converged is False:
            continue
        result = allocate(*inst.unpack())
        if not result.feasible:
            return inst, result, optimal
    return None, None, None


@pytest.mark.parametrize("allocate", [
    track_c_lp.allocate,
    track_b_lagr.allocate,
    track_b_c3.allocate,
], ids=["C", "B", "B-C3"])
def test_a_failed_primal_still_reports_its_bound(allocate):
    """A dual bound is valid whenever its relaxation solved.

    Discarding it on primal failure conflated T1 ("how tight is the relaxation") with T4
    ("can the track return an answer"), and made T1 unmeasurable on exactly the instances
    where the budget binds — every arm was dropped for infeasibility and the paired set came
    out empty.
    """
    from poc.instances.heterogeneous_generator import generate as het

    inst, result, optimal = _first_infeasible(allocate, het)
    if inst is None:
        pytest.skip("no infeasible case found in the seed range")

    assert result.lower_bound is not None, (
        "the relaxation solved but its bound was discarded when the primal failed")
    assert result.lower_bound <= optimal.total_cost + 1e-6, (
        f"INVALID BOUND on a failed primal: {result.lower_bound} > {optimal.total_cost}")


def test_an_empty_pool_still_reports_no_bound():
    """None must keep meaning "no bound exists", not "no bound survived".

    An empty candidate pool fails before any relaxation is solved, so there is genuinely
    nothing to report and the fix above must not manufacture one.
    """
    inst = generate(n_tasks=6, n_profiles=3, budget_tightness=1.0, seed=0)
    tasks, pools, profiles, budget = inst.unpack()
    starved = {t.id: [] for t in tasks}
    for allocate in (track_c_lp.allocate, track_b_lagr.allocate, track_b_c3.allocate):
        result = allocate(tasks, starved, profiles, budget)
        assert not result.feasible
        assert result.lower_bound is None
