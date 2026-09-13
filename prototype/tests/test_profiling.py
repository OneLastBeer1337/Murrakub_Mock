"""
Profile Store and Drift Detector (§4.5). Outside PoC scope. Owner: 077.
"""
from datetime import datetime

import pytest

from poc.formulation.types import Observation, ProfileSpec, Task, TaskId
from poc.tracks import exact_milp
from prototype.profiling import DriftDetector, NotProfiled, ProfileStore


def spec(pid, rel=0.95, lat=50.0, obs=0):
    return ProfileSpec(pid, "generic", throughput=20.0, gpus=1, price=100.0,
                       reliability=rel, latency=lat, observations=obs)


def observation(pid, latency=50.0, success=True):
    return Observation(TaskId("wf", "t1"), pid, latency, success, 0.0, datetime.now())


def test_ema_moves_toward_the_observation():
    store = ProfileStore({"m": spec("m", lat=50.0)}, alpha=0.5)
    updated = store.record(observation("m", latency=100.0))
    assert updated.latency == pytest.approx(75.0)
    assert updated.observations == 1


def test_failure_pulls_reliability_down_but_not_off_a_cliff():
    """This test previously asserted the EMA's behaviour — 1.0 to exactly 0.5 on a single
    failure — which was the bug rather than the requirement. What is actually wanted is
    that one failure moves the estimate by about one observation's worth of evidence.
    """
    store = ProfileStore({"m": spec("m", rel=1.0)})
    before = store.get("m").reliability
    after = store.record(observation("m", success=False)).reliability
    assert after < before, "a failure must move the estimate down"
    assert after > 0.6, "but a single failure must not halve it"


def test_unprofiled_raises_rather_than_defaulting():
    """Unprofiled entries return NotProfiled, never a default (CLAUDE.md conventions)."""
    with pytest.raises(NotProfiled):
        ProfileStore({}).get("missing")


def test_snapshot_does_not_alias_the_store():
    """An allocation run reads exactly one snapshot, so a bound stays meaningful (§4.5)."""
    store = ProfileStore({"m": spec("m", lat=50.0)})
    snap = store.snapshot()
    store.record(observation("m", latency=500.0))
    assert snap["m"].latency == 50.0


def _instance():
    tasks = [Task(TaskId("wf", f"t{i}"), "generic", load=8.0, rel_floor=0.0, lat_ceil=1e9)
             for i in range(3)]
    profiles = {"cheap": spec("cheap", obs=99), "dear": spec("dear", obs=99)}
    profiles["dear"] = ProfileSpec("dear", "generic", 20.0, 1, 300.0, 0.99, 50.0, 99)
    pools = {t.id: ["cheap", "dear"] for t in tasks}
    return tasks, pools, profiles


def test_drift_is_suppressed_when_observations_are_thin():
    """A single unlucky call must not re-allocate the batch (§4.5)."""
    tasks, pools, profiles = _instance()
    profiles = {k: ProfileSpec(**{**v.__dict__, "observations": 1}) for k, v in profiles.items()}
    detector = DriftDetector(exact_milp.allocate, min_observations=5)
    signal = detector.check({t.id: "cheap" for t in tasks}, tasks, pools, profiles, 4)
    assert signal.suppressed and not signal.fired


def test_no_drift_when_the_decision_is_unchanged():
    tasks, pools, profiles = _instance()
    detector = DriftDetector(exact_milp.allocate)
    routing = exact_milp.allocate(tasks, pools, profiles, 4).routing
    signal = detector.check(routing, tasks, pools, profiles, 4)
    assert signal.compatibility == pytest.approx(1.0)
    assert not signal.fired


def test_drift_fires_when_the_decision_would_change():
    """The score is a decision-space measure: it moves only when routing would move."""
    tasks, pools, profiles = _instance()
    detector = DriftDetector(exact_milp.allocate)
    stale = {t.id: "dear" for t in tasks}          # pretend we had chosen the dear profile
    signal = detector.check(stale, tasks, pools, profiles, 4)
    assert signal.compatibility < 1.0 and signal.fired


def test_score_is_blind_to_parameter_change_that_flips_no_decision():
    """A documented weakness of the [PROPOSED] definition, asserted so it is not forgotten."""
    tasks, pools, profiles = _instance()
    detector = DriftDetector(exact_milp.allocate)
    routing = exact_milp.allocate(tasks, pools, profiles, 4).routing

    nudged = dict(profiles)
    nudged["dear"] = ProfileSpec("dear", "generic", 20.0, 1, 290.0, 0.99, 50.0, 99)
    signal = detector.check(routing, tasks, pools, nudged, 4)
    assert signal.compatibility == pytest.approx(1.0), "price moved, no decision changed"


# --- the reliability estimator, after §4.5's EMA was found unusable for it ------

def _hammer(store, successes=0, failures=0):
    for _ in range(successes):
        store.record(observation("m", success=True))
    for _ in range(failures):
        store.record(observation("m", success=False))
    return store.get("m").reliability


def test_one_failure_does_not_destroy_a_good_profile():
    """The bug this estimator replaced: an EMA at alpha 0.3 reported 0.70 after 99
    successes and one failure, making the profile ineligible for any floor above 0.7."""
    store = ProfileStore({"m": spec("m", rel=0.99)})
    assert _hammer(store, successes=99, failures=1) > 0.97


def test_high_floors_remain_achievable():
    """The bug in the FIX. Decay caps the effective sample size, and with too strong a
    prior that caps achievable reliability — at decay 0.98 and a Laplace prior the ceiling
    was 0.981, so a task with rel_floor 0.99 could never be served by a measured profile."""
    store = ProfileStore({"m": spec("m", rel=0.99)})
    assert _hammer(store, successes=500) > 0.99


def test_sustained_degradation_is_still_detected():
    """Robustness must not cost sensitivity — the reason an EMA was chosen in the first
    place. A profile that genuinely goes bad must still register as bad."""
    store = ProfileStore({"m": spec("m", rel=0.99)})
    _hammer(store, successes=200)
    assert _hammer(store, failures=50) < 0.75


def test_latency_still_uses_the_ema_that_4_5_specifies():
    """Only reliability changed. Latency is continuous and an EMA suits it."""
    store = ProfileStore({"m": spec("m", lat=50.0)}, alpha=0.5)
    assert store.record(observation("m", latency=100.0)).latency == pytest.approx(75.0)


def test_reliability_is_bounded():
    store = ProfileStore({"m": spec("m", rel=0.99)})
    for successes, failures in ((0, 300), (300, 0), (50, 50)):
        s = ProfileStore({"m": spec("m", rel=0.99)})
        value = _hammer(s, successes=successes, failures=failures)
        assert 0.0 <= value <= 1.0


# --- the loop, end to end: observe -> profile -> drift -> re-optimise ----------

def test_the_full_profiling_loop_changes_an_allocation():
    """R4 and R5 demonstrated in one test, which nothing else in the repo does.

    Feed failures to the profile a task is currently routed to, watch the measured
    reliability fall below that task's floor, watch the pools shrink, and watch the
    re-optimised allocation move the task. This is the profile-guided premise working.
    """
    from prototype.registry import ExecutorRegistry, resolve

    registry = ExecutorRegistry()
    registry.register(ProfileSpec("cheap", "generic", 20.0, 1, 100.0, 0.99, 50.0))
    registry.register(ProfileSpec("dear", "generic", 20.0, 1, 300.0, 0.99, 50.0))

    tasks = [Task(TaskId("wf", "t1"), "generic", load=8.0, rel_floor=0.95, lat_ceil=1e9)]
    store = ProfileStore(registry.all_profiles())

    pools = resolve(tasks, registry)
    before = exact_milp.allocate(tasks, pools, store.snapshot(), 4)
    assert before.routing[tasks[0].id] == "cheap", "cheapest profile wins initially"

    for _ in range(60):                       # 'cheap' turns out to be unreliable
        store.record(Observation(tasks[0].id, "cheap", 50.0, False, 0.0, datetime.now()))

    measured = store.snapshot()
    assert measured["cheap"].reliability < tasks[0].rel_floor

    registry_after = ExecutorRegistry()
    for spec_ in measured.values():
        registry_after.register(spec_)
    pools_after = resolve(tasks, registry_after)
    assert pools_after[tasks[0].id] == ["dear"], "the floor now excludes the cheap profile"

    after = exact_milp.allocate(tasks, pools_after, measured, 4)
    assert after.routing[tasks[0].id] == "dear"
    assert after.total_cost > before.total_cost, "reliability was bought with cost"


def test_parameter_cliff_drift_flags_directly_without_allocator():
    """R2 / G6, G7: Parameter cliff breach must flag drift directly without calling allocate()."""
    tasks = [Task(TaskId("wf", "t1"), "generic", load=5.0, rel_floor=0.90, lat_ceil=200.0)]
    # Profile reliability 0.88 breaches the 0.90 floor (Delta R = -0.02 < 0.01)
    profiles = {"p1": spec("p1", rel=0.88, lat=50.0, obs=10)}
    pools = {tasks[0].id: ["p1"]}
    routing = {tasks[0].id: "p1"}

    def exploding_allocator(*args, **kwargs):
        raise AssertionError("allocate() must NOT be called when parameter cliff breaches")

    detector = DriftDetector(allocate=exploding_allocator, min_observations=5)
    signal = detector.check(routing, tasks, pools, profiles, budget=4)

    assert signal.fired is True
    assert signal.compatibility == 0.0
    assert signal.candidate is None
    assert "parameter cliff breached" in signal.reason


def test_parameter_cliff_latency_margin_breached():
    """Latency approaching ceiling within safety margin flags drift without calling allocator."""
    tasks = [Task(TaskId("wf", "t1"), "generic", load=5.0, rel_floor=0.80, lat_ceil=100.0)]
    # Latency 98.0ms with ceiling 100.0ms: Delta L = 2.0ms < epsilon_lat (5.0ms)
    profiles = {"p1": spec("p1", rel=0.99, lat=98.0, obs=10)}
    pools = {tasks[0].id: ["p1"]}
    routing = {tasks[0].id: "p1"}

    def exploding_allocator(*args, **kwargs):
        raise AssertionError("allocate() must NOT be called when latency cliff breaches")

    detector = DriftDetector(allocate=exploding_allocator, min_observations=5, epsilon_lat=5.0)
    signal = detector.check(routing, tasks, pools, profiles, budget=4)

    assert signal.fired is True
    assert signal.compatibility == 0.0
    assert signal.candidate is None
    assert "parameter cliff breached" in signal.reason

