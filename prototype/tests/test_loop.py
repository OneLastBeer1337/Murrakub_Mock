"""
The closed loop, J1 through J9. Outside PoC scope. Owner: 077.

This is the only place the system runs as a system. The tests here are about behaviours
that do not exist at component level: convergence, thrashing, abandonment, and whether a
genuine regime change is detected.
"""
import pytest

from poc.formulation.types import AllocationResult, ProfileSpec
from poc.tracks import exact_milp
from prototype.ingestion import InvalidBatch, TaskTypeSpec, ingest
from prototype.loop import AssignmentRegistry, run
from prototype.registry import ExecutorRegistry
from prototype.simulator import SimulatedExecutor, TrueBehaviour

MANIFEST = "data/eval_batches/eval_batch_3workflows.json"
SPECS = {
    "parse_log_line":    TaskTypeSpec(6.0, 0.90, 200.0),
    "classify_severity": TaskTypeSpec(4.0, 0.85, 200.0),
    "enrich_context":    TaskTypeSpec(3.0, 0.80, 200.0),
    "generate_report":   TaskTypeSpec(5.0, 0.85, 200.0),
}


def _setup(cheap_true_reliability):
    registry, truth = ExecutorRegistry(), {}
    for task_type in SPECS:
        registry.register(ProfileSpec(f"{task_type}-cheap", task_type, 20.0, 1, 100.0, 0.97, 60.0))
        registry.register(ProfileSpec(f"{task_type}-solid", task_type, 20.0, 2, 260.0, 0.99, 45.0))
        truth[f"{task_type}-cheap"] = TrueBehaviour(cheap_true_reliability, 60.0)
        truth[f"{task_type}-solid"] = TrueBehaviour(0.995, 45.0)
    return registry, truth


@pytest.fixture
def batch():
    return ingest(MANIFEST, SPECS)


# --- J1 -------------------------------------------------------------------------

def test_ingests_the_real_batch(batch):
    assert batch.batch_id == "eval-batch-001"
    assert len(batch.tasks) == 12
    assert len(batch.workflow_ids) == 3


def test_precedence_is_parsed_but_not_used_in_optimisation(batch):
    """DAG edges determine execution order only (§1.9)."""
    assert any(t.successors for t in batch.tasks), "expected real DAG edges"


def test_missing_demand_is_rejected_loudly():
    """The manifest carries no load or floors. If a type has no spec, J1 must fail rather
    than invent one — the gap belongs to 083/035, not to a default."""
    with pytest.raises(InvalidBatch, match="no demand specified"):
        ingest(MANIFEST, {"parse_log_line": SPECS["parse_log_line"]})


# --- J4 -------------------------------------------------------------------------

def test_registry_refuses_to_persist_an_infeasible_allocation():
    """Complete or nothing (P9)."""
    from poc.formulation.types import Infeasible
    registry = AssignmentRegistry()
    with pytest.raises(ValueError):
        registry.persist(AllocationResult.failure("A", Infeasible("nope")))


def test_assignments_are_versioned():
    registry = AssignmentRegistry()
    for cost in (100.0, 200.0):
        registry.persist(AllocationResult({}, {}, cost, 0, "MILP"))
    assert len(registry.versions) == 2
    assert registry.active.total_cost == 200.0


# --- the loop ------------------------------------------------------------------

def test_loop_runs_end_to_end(batch):
    registry, truth = _setup(0.99)
    records = run(batch.as_list(), registry, SimulatedExecutor(truth, seed=0),
                  exact_milp.allocate, budget=8, rounds=6)
    assert len(records) == 6
    assert all(r.successes + r.failures == 12 for r in records)


def test_loop_does_not_thrash(batch):
    """The feedback path — signal, re-allocate, execute, signal — is the obvious
    instability, and nothing else exercises it. Re-allocations must be rare, not constant.
    """
    registry, truth = _setup(0.99)
    records = run(batch.as_list(), registry, SimulatedExecutor(truth, seed=0),
                  exact_milp.allocate, budget=8, rounds=25)
    reallocations = sum(1 for r in records if r.reallocated)
    assert reallocations <= 3, f"re-allocated {reallocations} times in 25 rounds"


def test_genuine_degradation_is_detected(batch):
    """Sensitivity: when a profile really goes bad, the loop must route away from it."""
    registry, truth = _setup(0.99)
    executor = SimulatedExecutor(truth, seed=3)
    before = run(batch.as_list(), registry, executor, exact_milp.allocate, budget=8, rounds=8)

    executor.degrade("parse_log_line-cheap", reliability=0.40)
    after = run(batch.as_list(), registry, executor, exact_milp.allocate, budget=8, rounds=8)

    assert after[-1].cost > before[-1].cost, "degradation should force a costlier, safer plan"


def test_a_within_floor_profile_is_abandoned_on_noise(batch):
    """F23, pinned. The cheap profiles are GENUINELY acceptable — true reliability 0.93
    against a 0.90 floor — yet most runs abandon them permanently after early failures.

    If this test starts passing trivially (no abandonment), the loop has gained an
    exploration or confidence mechanism and F23 should be revisited.
    """
    abandoned = 0
    for seed in range(10):
        registry, truth = _setup(0.93)
        records = run(batch.as_list(), registry, SimulatedExecutor(truth, seed=seed),
                      exact_milp.allocate, budget=8, rounds=25)
        if records[-1].cost > records[0].cost + 1e-6:
            abandoned += 1
    assert abandoned >= 5, f"only {abandoned}/10 abandoned; has exploration been added?"


def test_an_abandoned_profile_never_recovers(batch):
    """The mechanism behind F23: a profile that stops being routed to stops being
    observed, so its measured reliability freezes and it can never be re-earned."""
    registry, truth = _setup(0.93)
    records = run(batch.as_list(), registry, SimulatedExecutor(truth, seed=1),
                  exact_milp.allocate, budget=8, rounds=25)

    frozen = [r.measured["parse_log_line-cheap"] for r in records[-10:]]
    assert len(set(round(v, 6) for v in frozen)) == 1, (
        "an unused profile's estimate should be frozen — no observations arrive")


# --- F24: the differentiator ----------------------------------------------------

def test_static_fails_its_floor_without_noticing_and_adaptive_does_not(batch):
    """The project's central claim, pinned.

    Both systems start correct - declared reliability equals true reliability - so this is
    not a strawman. Mid-run the truth drops below the floor. The static system keeps
    executing the same plan, reporting the same cost and a satisfied floor, while actually
    delivering about half the required reliability. The adaptive loop measures, detects and
    re-routes.

    If this test ever fails, the project's differentiator no longer holds and the proposal
    narrative needs rewriting.
    """
    strict = {t: TaskTypeSpec(SPECS[t].load, 0.95, 200.0) for t in SPECS}
    strict_batch = ingest(MANIFEST, strict)
    DRIFT_AT, ROUNDS = 6, 16

    def executor():
        _, truth = _setup(0.99)
        for key in truth:
            truth[key] = TrueBehaviour(0.99, truth[key].latency_mean)
        sim = SimulatedExecutor(truth, seed=0)
        for task_type in SPECS:
            sim.schedule_degradation(DRIFT_AT, f"{task_type}-cheap", reliability=0.55)
        return sim

    def delivered(adaptive):
        registry, _ = _setup(0.99)
        records = run(strict_batch.as_list(), registry, executor(), exact_milp.allocate,
                      budget=8, rounds=ROUNDS, adaptive=adaptive)
        after = records[DRIFT_AT + 2:]
        return sum(r.successes for r in after) / sum(r.successes + r.failures for r in after)

    static_delivered = delivered(adaptive=False)
    adaptive_delivered = delivered(adaptive=True)

    assert static_delivered < 0.75, (
        f"static delivered {static_delivered:.3f} - expected it to fail the 0.95 floor")
    assert adaptive_delivered > 0.90, (
        f"adaptive delivered {adaptive_delivered:.3f} - expected recovery toward the floor")
    assert adaptive_delivered > static_delivered + 0.2


# --- F25: optimistic eligibility -------------------------------------------------

def _healthy_run(floor, rounds, optimistic, seed):
    strict = {t: TaskTypeSpec(SPECS[t].load, floor, 200.0) for t in SPECS}
    registry, truth = _setup(0.99)
    for key in truth:
        truth[key] = TrueBehaviour(0.99, truth[key].latency_mean)
    return run(ingest(MANIFEST, strict).as_list(), registry,
               SimulatedExecutor(truth, seed=seed), exact_milp.allocate,
               budget=8, rounds=rounds, optimistic_eligibility=optimistic)


def test_point_estimate_overpays_on_healthy_profiles():
    """F25. With no drift and true reliability comfortably above the floor, filtering on
    the point estimate still abandons good profiles and settles at a permanently higher
    cost. 400 is the optimum; anything above it is money spent reacting to noise."""
    tail = [_healthy_run(0.95, 40, optimistic=False, seed=s)[-1].cost for s in range(6)]
    assert sum(tail) / len(tail) > 420, "expected the documented overpayment"


def test_optimistic_eligibility_removes_the_overpayment():
    """Excluding a profile only when confident it is below floor recovers the optimum."""
    tail = [_healthy_run(0.95, 40, optimistic=True, seed=s)[-1].cost for s in range(6)]
    assert sum(tail) / len(tail) == pytest.approx(400.0, abs=1.0)


def test_optimism_does_not_blind_the_system_to_real_failure():
    """The obvious risk: keep trying a profile because evidence is thin, and miss a genuine
    collapse. It does not happen — the bound converges down once evidence accumulates."""
    strict = {t: TaskTypeSpec(SPECS[t].load, 0.95, 200.0) for t in SPECS}
    strict_batch = ingest(MANIFEST, strict)
    registry, truth = _setup(0.99)
    for key in truth:
        truth[key] = TrueBehaviour(0.99, truth[key].latency_mean)
    sim = SimulatedExecutor(truth, seed=0)
    for task_type in SPECS:
        sim.schedule_degradation(6, f"{task_type}-cheap", reliability=0.55)

    records = run(strict_batch.as_list(), registry, sim, exact_milp.allocate,
                  budget=8, rounds=26, optimistic_eligibility=True)
    after = records[10:]
    delivered = sum(r.successes for r in after) / sum(r.successes + r.failures for r in after)
    assert delivered > 0.90, f"optimism missed a genuine collapse: delivered {delivered:.3f}"


def test_loop_does_not_run_allocator_twice_in_drift_rounds(batch):
    """G6 / Task 2: Allocator must not be run twice on rounds where drift fires."""
    registry, truth = _setup(0.99)
    sim = SimulatedExecutor(truth, seed=0)
    sim.schedule_degradation(4, "parse_log_line-cheap", reliability=0.40)

    round_calls = []
    current_calls = [0]

    def tracked_allocate(*args, **kwargs):
        current_calls[0] += 1
        return exact_milp.allocate(*args, **kwargs)

    # Patch detector.check or observe per-round call increment
    # Wrap executor to observe round boundaries
    real_execute = sim.execute
    def execute_and_snapshot(routing):
        round_calls.append(current_calls[0])
        current_calls[0] = 0
        return real_execute(routing)

    sim.execute = execute_and_snapshot

    records = run(batch.as_list(), registry, sim, tracked_allocate, budget=8, rounds=8)
    round_calls.append(current_calls[0])  # final round calls

    # round_calls[0] is before round 0 (initial v0 solve)
    # round_calls[1:] are calls during rounds 0 through 7
    for r_idx, calls in enumerate(round_calls[1:]):
        assert calls <= 1, f"Round {r_idx} called allocator {calls} times (> 1, G6 regression!)"

