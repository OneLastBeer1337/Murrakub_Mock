"""
Adversarial Stress Test Suite for Online Self-Correcting Profiles (Milestone 2).

Conducted by Profiling Stress Challenger (M2).
Evaluates:
  1. Extreme transient latency spikes (single 5000ms pause, multi-spike bursts)
  2. Zero, negative, and microscopic latencies / telemetry safety
  3. Rapidly oscillating observation sequences (slew-rate damping & EMA stability)
  4. Long-run gradual drift (50 calls with 2x latency -> 0.5x throughput accuracy)
  5. High concurrency / multi-threaded rapid observations & snapshot consistency
  6. Invariants I1-I5 compliance under continuous dynamic profile updates
  7. Adversarial chaos fuzzing under mixed extreme inputs
"""

from __future__ import annotations

from datetime import datetime
import math
import random
import threading
import pytest

from poc.formulation.invariants import check as check_invariants
from poc.formulation.types import Observation, ProfileSpec, Task, TaskId
from poc.tracks import exact_milp, track_c_lp
from prototype.profiling import (
    DEFAULT_ALPHA,
    DEFAULT_BETA,
    DEFAULT_WARMUP_OBSERVATIONS,
    DEFAULT_SLEW_RATE_MAX,
    DEFAULT_ELECTRICITY_PRICE_KWH,
    DriftDetector,
    ExtendedObservation,
    NotProfiled,
    ObservationV5,
    ProfileStore,
    get_baseline_power_watts,
)


def make_spec(pid: str = "m", declared_type: str = "generic", throughput: float = 20.0,
              gpus: int = 1, price: float = 100.0, rel: float = 0.99, lat: float = 50.0,
              obs: int = 5) -> ProfileSpec:
    return ProfileSpec(
        id=pid,
        declared_type=declared_type,
        throughput=throughput,
        gpus=gpus,
        price=price,
        reliability=rel,
        latency=lat,
        observations=obs,
    )


def make_obs(pid: str = "m", latency: float = 50.0, success: bool = True,
              cost: float = 0.0, throughput: float | None = None,
              energy_joules: float | None = None,
              power_watts: float | None = None) -> ExtendedObservation:
    return ExtendedObservation(
        task_id=TaskId("wf", "t1"),
        profile_id=pid,
        latency=latency,
        success=success,
        cost=cost,
        timestamp=datetime.now(),
        throughput=throughput,
        energy_joules=energy_joules,
        power_watts=power_watts,
    )


# =============================================================================
# 1. Extreme Transient Latency Spikes
# =============================================================================

def test_stress_extreme_transient_latency_spike_single_and_burst():
    """Stress test single massive spikes (5000ms, 1e6ms) and multi-spike bursts."""
    initial_thr = 20.0
    initial_lat = 50.0
    store = ProfileStore(
        {"m": make_spec("m", throughput=initial_thr, lat=initial_lat, obs=5)},
        warmup_observations=3,
        beta=0.2,
        slew_rate_max=0.20,
    )

    # 1. Single 5000ms pause: should not drop below 80% (16.0 req/s)
    # Implied rate = 20 * (50 / 5000) = 0.20. Deviation = |0.2 - 20|/20 = 0.99 > 0.5.
    # Huber beta_eff = 0.2 / (1 + 0.99^2) = 0.101. Slew limit clamps to [16.0, 24.0].
    up1 = store.record(make_obs("m", latency=5000.0))
    assert up1.throughput >= 16.0, f"Expected thr >= 16.0, got {up1.throughput}"
    assert up1.throughput <= 24.0
    assert not math.isnan(up1.throughput)
    assert not math.isinf(up1.throughput)

    # 2. Extreme single 1,000,000ms spike
    store_mega = ProfileStore(
        {"m": make_spec("m", throughput=initial_thr, lat=initial_lat, obs=5)},
        warmup_observations=3,
        beta=0.2,
    )
    up_mega = store_mega.record(make_obs("m", latency=1_000_000.0))
    assert up_mega.throughput >= 16.0
    assert not math.isnan(up_mega.throughput)

    # 3. Burst of 5 consecutive 5000ms spikes
    store_burst = ProfileStore(
        {"m": make_spec("m", throughput=initial_thr, lat=initial_lat, obs=5)},
        warmup_observations=3,
        beta=0.2,
    )
    for i in range(5):
        up_burst = store_burst.record(make_obs("m", latency=5000.0))
        # Each step can drop by at most 20%
        assert up_burst.throughput > 0.0

    # After 5 spikes, throughput degraded monotonically but remains well above physiological floor
    assert up_burst.throughput >= max(0.10 * initial_thr, 1.0)
    assert up_burst.throughput < 15.0

    # 4. Rapid recovery: 15 nominal calls restore throughput back towards 20.0
    for _ in range(15):
        up_rec = store_burst.record(make_obs("m", latency=50.0))

    assert up_rec.throughput >= 18.5, f"Throughput should recover to >= 18.5, got {up_rec.throughput}"


# =============================================================================
# 2. Zero, Negative, and Microscopic Latencies & Telemetry Safety
# =============================================================================

def test_stress_zero_and_negative_latencies_division_safety():
    """Verify zero, negative, and microsecond latencies do not cause division-by-zero or crashes."""
    store = ProfileStore({"m": make_spec("m", throughput=20.0, lat=50.0, obs=5)}, warmup_observations=0)

    # Zero latency
    up_zero = store.record(make_obs("m", latency=0.0))
    assert up_zero.throughput > 0.0
    assert not math.isnan(up_zero.throughput)
    assert not math.isinf(up_zero.throughput)
    assert up_zero.price >= 100.0

    # Negative latency
    up_neg = store.record(make_obs("m", latency=-1000.0))
    assert up_neg.throughput > 0.0
    assert not math.isnan(up_neg.throughput)
    assert not math.isinf(up_neg.throughput)

    # Microsecond latency (1e-6 ms)
    up_micro = store.record(make_obs("m", latency=1e-6))
    assert up_micro.throughput > 0.0
    assert not math.isnan(up_micro.throughput)
    assert up_micro.throughput <= 60.0  # bounded by Tier 4 max 3x thr_0


def test_stress_adversarial_telemetry_payloads():
    """Verify adversarial / corrupted observation fields fall back gracefully."""
    store = ProfileStore({"m": make_spec("m", throughput=20.0, lat=50.0, obs=5)}, warmup_observations=0)

    # Negative cost must not reduce price
    initial_price = store.get("m").price
    up1 = store.record(make_obs("m", cost=-999.0))
    assert up1.price >= initial_price

    # Negative energy must fall back to power * exec_sec
    up2 = store.record(make_obs("m", energy_joules=-500.0, latency=50.0))
    assert store.get_cumulative_energy_joules("m") > 0.0

    # Negative or zero power must fall back to baseline hardware table
    up3 = store.record(make_obs("m", power_watts=-200.0))
    assert store.get_power_watts("m") == 200.0  # 1 GPU baseline is 200W

    # Negative or zero throughput must fall back to latency-implied rate
    up4 = store.record(make_obs("m", latency=50.0, throughput=-10.0))
    assert up4.throughput > 0.0


# =============================================================================
# 3. Rapidly Oscillating Observation Sequences
# =============================================================================

def test_stress_rapid_oscillations_damping_and_stability():
    """Verify oscillating inputs are smoothed without resonance or runaway.

    Tests two distinct regimes:
      1. Moderate oscillation (+/- 25%: 15.0 vs 25.0 req/s, dev <= 0.5):
         Analytical steady-state EMA with beta=0.2 dampens input swing by 1/9 (from 10.0 to 1.111 req/s)
         centered exactly at nominal 20.0 req/s.
      2. Severe oscillation (+/- 75%: 5.0 vs 35.0 req/s, dev > 0.5):
         Slew rate strictly clamps every step <= 20%, and Huber attenuation prevents runaway,
         stabilizing into a conservative limit cycle with cycle step amplitude < 0.30 req/s.
    """
    initial_thr = 20.0

    # Regime 1: Moderate oscillation (+/- 25%)
    store_mod = ProfileStore(
        {"m": make_spec("m", throughput=initial_thr, lat=50.0, obs=5)},
        warmup_observations=0,
        beta=0.2,
        slew_rate_max=0.20,
    )
    for i in range(80):
        target = 15.0 if i % 2 == 0 else 25.0
        store_mod.record(make_obs("m", latency=50.0, throughput=target))

    tail_mod = [
        store_mod.record(make_obs("m", latency=50.0, throughput=(15.0 if i % 2 == 0 else 25.0))).throughput
        for i in range(10)
    ]
    mod_min, mod_max = min(tail_mod), max(tail_mod)
    mod_amp = mod_max - mod_min
    mod_mean = (mod_min + mod_max) / 2.0

    # Analytical prediction: mean = 20.0, amp = (1/9) * 10 = 1.1111
    assert mod_mean == pytest.approx(20.0, abs=0.05)
    assert mod_amp == pytest.approx(10.0 / 9.0, abs=0.05)

    # Regime 2: Severe oscillation (+/- 75%: 5.0 vs 35.0 req/s)
    store_sev = ProfileStore(
        {"m": make_spec("m", throughput=initial_thr, lat=50.0, obs=5)},
        warmup_observations=0,
        beta=0.2,
        slew_rate_max=0.20,
    )
    prev_thr = initial_thr
    for i in range(200):
        target_rate = 5.0 if i % 2 == 0 else 35.0
        up = store_sev.record(make_obs("m", latency=50.0, throughput=target_rate))

        # Slew rate constraint: single step change must strictly not exceed 20%
        step_ratio = abs(up.throughput - prev_thr) / prev_thr
        assert step_ratio <= 0.20 + 1e-6, f"Slew rate exceeded at step {i}: {step_ratio}"

        # Step amplitude between consecutive alternating steps must remain heavily damped
        step_amp = abs(up.throughput - prev_thr)
        assert step_amp <= 2.5, f"Adjacent step amplitude {step_amp} exceeded limit 2.5"
        prev_thr = up.throughput

    # Check steady-state limit cycle in the tail
    tail_sev = [
        store_sev.record(make_obs("m", latency=50.0, throughput=(5.0 if i % 2 == 0 else 35.0))).throughput
        for i in range(10)
    ]
    sev_amp = max(tail_sev) - min(tail_sev)
    # In steady state, peak-to-peak oscillation is damped from 30.0 req/s down to < 0.30 req/s!
    assert sev_amp <= 0.30, f"Steady-state limit cycle amplitude {sev_amp} exceeded 0.30"
    assert 5.5 <= min(tail_sev) <= 6.5


# =============================================================================
# 4. Long-Run Gradual Drift Tracking
# =============================================================================

def test_stress_long_run_gradual_drift_tracking_accuracy():
    """Verify 50 calls with 2x latency track throughput down to exactly 0.5x within < 0.01% error."""
    initial_thr = 20.0
    initial_lat = 50.0
    store = ProfileStore(
        {"m": make_spec("m", throughput=initial_thr, lat=initial_lat, obs=5)},
        warmup_observations=0,
        beta=0.2,
    )

    # 50 calls with 2x latency (100.0 ms) -> implied rate is 10.0 req/s
    for _ in range(50):
        up = store.record(make_obs("m", latency=100.0))

    final_thr = up.throughput
    expected_thr = 10.0
    abs_error = abs(final_thr - expected_thr)
    rel_error = abs_error / expected_thr

    # With (1 - 0.2)^50 = 1.43e-5, theoretical error is ~0.00014
    assert rel_error < 0.0001, f"Expected relative error < 0.01%, got {rel_error * 100:.4f}%"
    assert final_thr == pytest.approx(expected_thr, abs=1e-3)

    # Now verify upward drift: 50 calls with 0.5x latency (25.0 ms) -> implied rate is 40.0 req/s
    for _ in range(50):
        up = store.record(make_obs("m", latency=25.0))

    final_up_thr = up.throughput
    # Upward rate approaches 40.0 req/s
    assert final_up_thr >= 35.0, f"Expected thr to adapt upward towards 40.0, got {final_up_thr}"
    assert final_up_thr <= 60.0  # clamped to physiological max


# =============================================================================
# 5. High Concurrency & Multi-Threaded Stress
# =============================================================================

def test_stress_concurrent_multithreaded_updates_and_snapshot_isolation():
    """Stress test multi-threaded concurrent updates and verify snapshot immutability."""
    profiles = {
        f"p{i}": make_spec(f"p{i}", declared_type="type_a", throughput=20.0, gpus=1, price=100.0, obs=5)
        for i in range(4)
    }
    store = ProfileStore(profiles, warmup_observations=0, beta=0.2)

    num_threads = 12
    updates_per_thread = 100
    errors: list[Exception] = []
    snapshots_captured: list[dict[str, ProfileSpec]] = []
    stop_event = threading.Event()

    def writer(tid: int):
        rng = random.Random(tid * 42)
        for step in range(updates_per_thread):
            pid = f"p{rng.randint(0, 3)}"
            lat = rng.uniform(20.0, 120.0)
            cost = rng.uniform(0.0, 0.05)
            try:
                store.record(make_obs(pid, latency=lat, cost=cost))
            except Exception as e:
                errors.append(e)

    def reader(rid: int):
        while not stop_event.is_set():
            try:
                snap = store.snapshot()
                # Verify snapshot integrity: all keys exist, no NaNs
                assert len(snap) == 4
                for p in snap.values():
                    assert p.throughput > 0.0
                    assert not math.isnan(p.throughput)
                    assert p.price >= 100.0
                snapshots_captured.append(snap)
            except Exception as e:
                errors.append(e)

    writer_threads = [threading.Thread(target=writer, args=(t,)) for t in range(num_threads)]
    reader_threads = [threading.Thread(target=reader, args=(r,)) for r in range(3)]

    for r in reader_threads:
        r.start()
    for w in writer_threads:
        w.start()

    for w in writer_threads:
        w.join()

    stop_event.set()
    for r in reader_threads:
        r.join()

    assert errors == [], f"Encountered {len(errors)} errors during concurrent execution: {errors[:3]}"
    assert len(snapshots_captured) > 0

    # Verify final store snapshot
    final_snap = store.snapshot()
    total_obs = sum(p.observations for p in final_snap.values())
    expected_obs = 4 * 5 + num_threads * updates_per_thread
    assert total_obs == expected_obs, f"Expected {expected_obs} total observations, got {total_obs}"

    # Verify snapshot immutability: an old snapshot must not match final snapshot
    old_snap = snapshots_captured[0]
    old_total_obs = sum(p.observations for p in old_snap.values())
    assert old_total_obs < total_obs


# =============================================================================
# 6. Invariant Compliance (I1-I5) Under Continuous Dynamic Updating
# =============================================================================

def test_stress_continuous_dynamic_updating_upholds_invariants_i1_to_i5():
    """Verify that throughout 20 rounds of dynamic profile drift, Track C and MILP allocations satisfy I1-I5."""
    tasks = [
        Task(TaskId("wf1", "t1"), "parse", load=8.0, rel_floor=0.85, lat_ceil=250.0),
        Task(TaskId("wf1", "t2"), "classify", load=6.0, rel_floor=0.80, lat_ceil=250.0),
        Task(TaskId("wf2", "t1"), "parse", load=10.0, rel_floor=0.85, lat_ceil=250.0),
        Task(TaskId("wf2", "t2"), "classify", load=8.0, rel_floor=0.80, lat_ceil=250.0),
    ]

    profiles = {
        "parse-cpu": make_spec("parse-cpu", declared_type="parse", throughput=25.0, gpus=0, price=40.0, obs=5),
        "parse-gpu": make_spec("parse-gpu", declared_type="parse", throughput=30.0, gpus=1, price=100.0, obs=5),
        "classify-edge": make_spec("classify-edge", declared_type="classify", throughput=20.0, gpus=1, price=120.0, obs=5),
        "classify-dc": make_spec("classify-dc", declared_type="classify", throughput=50.0, gpus=2, price=280.0, obs=5),
    }

    pools = {
        tasks[0].id: ["parse-cpu", "parse-gpu"],
        tasks[1].id: ["classify-edge", "classify-dc"],
        tasks[2].id: ["parse-cpu", "parse-gpu"],
        tasks[3].id: ["classify-edge", "classify-dc"],
    }
    budget = 6
    store = ProfileStore(profiles, beta=0.2)

    # 20 sequential rounds of dynamic execution with degradation and recovery
    for round_num in range(1, 21):
        if round_num in (3, 4, 5):
            # Degradation on parse-gpu (thermal throttling: 3x latency -> throughput drops)
            store.record(make_obs("parse-gpu", latency=150.0))
        elif round_num in (8, 9, 10):
            # Surge on classify-edge (load surge: direct throughput telemetry drops to 10.0)
            store.record(make_obs("classify-edge", throughput=10.0, latency=90.0))
        elif round_num in (13, 14, 15):
            # Transient spike on classify-dc
            store.record(make_obs("classify-dc", latency=2000.0))
        else:
            # Nominal conditions
            store.record(make_obs("parse-gpu", latency=50.0))
            store.record(make_obs("classify-edge", latency=50.0))

        current_snapshot = store.snapshot()

        # Track C allocation
        res_c = track_c_lp.allocate(tasks, pools, current_snapshot, budget=budget)
        if res_c.feasible:
            violations_c = check_invariants(res_c, tasks, pools, current_snapshot, budget)
            assert violations_c == [], f"Round {round_num} Track C violated invariants: {violations_c}"
            # Verify provisioned capacity covers routed load (Invariant I2 / C2)
            for m_id, count in res_c.provisioning.items():
                if count > 0:
                    assert count * current_snapshot[m_id].throughput >= sum(
                        t.load for t in tasks if res_c.routing.get(t.id) == m_id
                    )

        # Exact MILP allocation
        res_milp = exact_milp.allocate(tasks, pools, current_snapshot, budget=budget)
        if res_milp.feasible:
            violations_milp = check_invariants(res_milp, tasks, pools, current_snapshot, budget)
            assert violations_milp == [], f"Round {round_num} MILP violated invariants: {violations_milp}"


# =============================================================================
# 7. Chaos Fuzzing Under Mixed Extreme Inputs
# =============================================================================

def test_stress_chaos_fuzzing_random_inputs():
    """Fuzz ProfileStore with 300 random adversarial combinations of telemetry."""
    store = ProfileStore(
        {"m": make_spec("m", throughput=20.0, lat=50.0, obs=5)},
        warmup_observations=0,
        beta=0.2,
    )

    rng = random.Random(1337)
    latencies = [-100.0, 0.0, 0.001, 10.0, 50.0, 500.0, 5000.0, 100000.0]
    throughputs = [-10.0, 0.0, None, 0.5, 10.0, 20.0, 50.0, 200.0]
    powers = [-50.0, 0.0, None, 100.0, 500.0]
    costs = [-5.0, 0.0, 0.01, 1.0]

    for step in range(300):
        lat = rng.choice(latencies)
        thr = rng.choice(throughputs)
        pwr = rng.choice(powers)
        cst = rng.choice(costs)
        succ = rng.choice([True, False])

        obs = make_obs("m", latency=lat, success=succ, cost=cst, throughput=thr, power_watts=pwr)
        updated = store.record(obs)

        # Invariants on the updated spec
        assert not math.isnan(updated.throughput), f"NaN throughput at step {step}"
        assert not math.isinf(updated.throughput), f"Inf throughput at step {step}"
        assert updated.throughput >= 1.0, f"Throughput collapsed below 1.0 at step {step}: {updated.throughput}"
        assert updated.throughput <= 60.0, f"Throughput exploded above 60.0 at step {step}: {updated.throughput}"
        assert updated.price >= 100.0, f"Price dropped below initial at step {step}"
        assert 0.0 <= updated.reliability <= 1.0, f"Reliability out of bounds at step {step}"
        assert updated.observations == 6 + step


# =============================================================================
# 8. DriftDetector Reactivity Under Self-Corrected Throughput Degradation
# =============================================================================

def test_stress_drift_detector_reacts_to_throughput_degradation():
    """Verify DriftDetector identifies capacity degradation and computes valid candidate re-routing."""
    tasks = [
        Task(TaskId("wf", "t1"), "type_a", load=15.0, rel_floor=0.80, lat_ceil=200.0),
        Task(TaskId("wf", "t2"), "type_a", load=10.0, rel_floor=0.80, lat_ceil=200.0),
    ]
    profiles = {
        "p_fast": make_spec("p_fast", declared_type="type_a", throughput=30.0, gpus=1, price=100.0, obs=5),
        "p_alt": make_spec("p_alt", declared_type="type_a", throughput=25.0, gpus=1, price=120.0, obs=5),
    }
    pools = {t.id: ["p_fast", "p_alt"] for t in tasks}
    budget = 4

    store = ProfileStore(profiles, warmup_observations=0, beta=0.2)
    initial_alloc = track_c_lp.allocate(tasks, pools, store.snapshot(), budget)
    assert initial_alloc.feasible is True
    # Initially, 1 instance of p_fast carries both tasks (load 25 <= 30)
    assert initial_alloc.routing[tasks[0].id] == "p_fast"
    assert initial_alloc.routing[tasks[1].id] == "p_fast"

    # Degrade p_fast throughput via 15 observations with latency 100ms (2x slower)
    for _ in range(15):
        store.record(make_obs("p_fast", latency=100.0))

    updated_snap = store.snapshot()
    assert updated_snap["p_fast"].throughput < 17.0  # throughput calibrated below 17 req/s

    detector = DriftDetector(track_c_lp.allocate, min_observations=5)
    signal = detector.check(initial_alloc.routing, tasks, pools, updated_snap, budget)

    # DriftDetector must fire: tasks must re-route to p_alt to preserve capacity
    assert signal.fired is True
    assert signal.compatibility == 0.0
    assert signal.candidate is not None
    assert signal.candidate.feasible is True

    # Invariants must hold on candidate
    violations = check_invariants(signal.candidate, tasks, pools, updated_snap, budget)
    assert violations == []
    # Both tasks moved to p_alt
    assert signal.candidate.routing[tasks[0].id] == "p_alt"
    assert signal.candidate.routing[tasks[1].id] == "p_alt"

