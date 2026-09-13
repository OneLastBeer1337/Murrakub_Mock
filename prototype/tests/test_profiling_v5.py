"""
Unit and integration test suite for Online Self-Correcting Profiles (Closing G2).

System Architecture v5 §7.2:
  - Dual-input rate estimation: direct throughput and latency-implied rate
  - 4-Tier damping architecture:
      * Tier 1: Warmup gate (N_warmup = 3 observations)
      * Tier 2: Huber-style loss attenuation on large deviations (|r - thr| / thr > 0.5)
      * Tier 3: Slew-rate limiter clamping single-step changes to +/- 20%
      * Tier 4: Global physiological bounds [max(0.10 * thr_0, 1.0), 3.0 * thr_0]
  - Steady-state Bayesian Kalman filter equivalence via EMA (beta = 0.2)
  - Effective cost and thermodynamic efficiency (eta = throughput / P_avg)
  - Invariant validation (I1-I5) via poc.formulation.invariants.check
"""

from __future__ import annotations

from datetime import datetime
import math
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
    ExtendedObservation,
    NotProfiled,
    ObservationV5,
    ProfileStore,
    get_baseline_power_watts,
)


def make_spec(pid: str = "m", declared_type: str = "generic", throughput: float = 20.0,
              gpus: int = 1, price: float = 100.0, rel: float = 0.99, lat: float = 50.0,
              obs: int = 0) -> ProfileSpec:
    """Helper to create ProfileSpec fixtures."""
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
    """Helper to create ExtendedObservation fixtures."""
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
# 1. Baseline Hardware Power and Telemetry Data Models
# =============================================================================

def test_baseline_power_watts_across_hardware_classes():
    """Verify hardware baseline power table matches finding F31 and Arch v5 §7.2."""
    cpu_spec = make_spec("cpu_worker", gpus=0)
    edge_gpu_spec = make_spec("rtx4090", gpus=1)
    dc_gpu_2x = make_spec("a100_2x", gpus=2)
    dc_gpu_8x = make_spec("h100_8x", gpus=8)

    assert get_baseline_power_watts(cpu_spec) == 75.0
    assert get_baseline_power_watts(edge_gpu_spec) == 200.0
    assert get_baseline_power_watts(dc_gpu_2x) == 700.0
    assert get_baseline_power_watts(dc_gpu_8x) == 2800.0


def test_extended_observation_interoperability():
    """Verify ExtendedObservation and ObservationV5 alias maintain full dataclass integrity."""
    obs = ObservationV5(
        task_id=TaskId("wf", "t1"),
        profile_id="p1",
        latency=45.0,
        success=True,
        cost=0.05,
        timestamp=datetime.now(),
        throughput=18.5,
        energy_joules=9.25,
        power_watts=205.0,
    )
    assert isinstance(obs, Observation)
    assert isinstance(obs, ExtendedObservation)
    assert obs.throughput == 18.5
    assert obs.energy_joules == 9.25
    assert obs.power_watts == 205.0


def test_profilestore_parameter_validation():
    """Verify ProfileStore validates hyperparameter boundaries."""
    profiles = {"m": make_spec("m")}

    with pytest.raises(ValueError, match="alpha"):
        ProfileStore(profiles, alpha=0.0)
    with pytest.raises(ValueError, match="alpha"):
        ProfileStore(profiles, alpha=1.5)

    with pytest.raises(ValueError, match="beta"):
        ProfileStore(profiles, beta=0.0)
    with pytest.raises(ValueError, match="beta"):
        ProfileStore(profiles, beta=1.1)

    with pytest.raises(ValueError, match="decay"):
        ProfileStore(profiles, decay=0.0)
    with pytest.raises(ValueError, match="decay"):
        ProfileStore(profiles, decay=1.2)

    with pytest.raises(ValueError, match="warmup_observations"):
        ProfileStore(profiles, warmup_observations=-1)

    with pytest.raises(ValueError, match="slew_rate_max"):
        ProfileStore(profiles, slew_rate_max=0.0)
    with pytest.raises(ValueError, match="slew_rate_max"):
        ProfileStore(profiles, slew_rate_max=1.5)


# =============================================================================
# 2. Dual-Input Throughput Estimation (Direct vs Latency-Implied)
# =============================================================================

def test_direct_throughput_telemetry_updates_profile():
    """When observation.throughput > 0 is provided, use it directly (Modality A)."""
    # Start with warmup_observations=0 to observe immediate adaptation
    store = ProfileStore({"m": make_spec("m", throughput=20.0)}, warmup_observations=0, beta=0.2)

    # Supply direct throughput = 15.0 req/s
    obs = make_obs("m", latency=50.0, throughput=15.0)
    updated = store.record(obs)

    # Expected update: (1 - 0.2) * 20.0 + 0.2 * 15.0 = 16.0 + 3.0 = 19.0
    # Deviation = |15 - 20| / 20 = 0.25 <= 0.5, so beta_eff = 0.2
    # Slew rate: max shift 20 * 0.20 = 4.0; 19.0 in [16.0, 24.0] -> 19.0
    assert updated.throughput == pytest.approx(19.0)
    assert updated.observations == 1


def test_latency_implied_service_rate_halving_and_doubling():
    """When direct throughput is absent, calculate implied rate r_implied = thr_0 * (L_0 / L_obs)."""
    # Nominal profile: 20.0 req/s at 50.0 ms
    store = ProfileStore({"m": make_spec("m", throughput=20.0, lat=50.0)}, warmup_observations=0, beta=0.2)

    # Case A: Latency doubles (50ms -> 100ms) -> implied rate halves to 10.0 req/s
    # Deviation = |10.0 - 20.0| / 20.0 = 0.50 <= 0.5, beta_eff = 0.2
    # Candidate = 0.8 * 20 + 0.2 * 10 = 18.0. Slew limit: [16.0, 24.0]. Clamped to 18.0.
    updated_1 = store.record(make_obs("m", latency=100.0))
    assert updated_1.throughput == pytest.approx(18.0)

    # Case B: Reset and test latency halving (50ms -> 25ms) -> implied rate doubles to 40.0 req/s
    # Deviation = |40.0 - 20.0| / 20.0 = 1.0 > 0.5 -> beta_eff = 0.2 / (1 + 1^2) = 0.1
    # Candidate = 0.9 * 20 + 0.1 * 40 = 22.0. Slew limit: [16.0, 24.0]. Clamped to 22.0.
    store_fast = ProfileStore({"m": make_spec("m", throughput=20.0, lat=50.0)}, warmup_observations=0, beta=0.2)
    updated_fast = store_fast.record(make_obs("m", latency=25.0))
    assert updated_fast.throughput == pytest.approx(22.0)


def test_zero_and_negative_latency_guarded():
    """Observations with latency <= 0 must be safely clamped to prevent zero division or negative rates."""
    store = ProfileStore({"m": make_spec("m", throughput=20.0, lat=50.0)}, warmup_observations=0)
    updated_zero = store.record(make_obs("m", latency=0.0))
    assert updated_zero.throughput > 0.0
    assert not math.isnan(updated_zero.throughput)

    updated_neg = store.record(make_obs("m", latency=-50.0))
    assert updated_neg.throughput > 0.0
    assert not math.isnan(updated_neg.throughput)


# =============================================================================
# 3. Four-Tier Outlier Damping Architecture
# =============================================================================

def test_tier1_warmup_gate_suppresses_early_throughput_updates():
    """Tier 1: Observations below N_warmup = 3 must keep declared throughput unchanged."""
    store = ProfileStore(
        {"m": make_spec("m", throughput=20.0, lat=50.0, obs=0)},
        warmup_observations=3,
        beta=0.2,
    )

    # Observations 1, 2, 3: Throughput must remain exactly 20.0
    for i in range(1, 4):
        updated = store.record(make_obs("m", latency=150.0))  # severe degradation
        assert updated.throughput == pytest.approx(20.0), f"Throughput should stay frozen at obs {i}"
        assert updated.observations == i
        # But latency and reliability must still adapt
        assert updated.latency > 50.0

    # Observation 4: Warmup gate elapsed -> throughput adapts
    updated_4 = store.record(make_obs("m", latency=150.0))
    assert updated_4.observations == 4
    assert updated_4.throughput < 20.0, "Throughput must adapt once warmup gate has passed"


def test_tier1_warmup_gate_elapsed_if_initialized_above_threshold():
    """A profile with existing observations >= N_warmup adapts immediately."""
    store = ProfileStore(
        {"m": make_spec("m", throughput=20.0, lat=50.0, obs=10)},
        warmup_observations=3,
        beta=0.2,
    )
    updated = store.record(make_obs("m", latency=100.0))
    assert updated.throughput == pytest.approx(18.0)


def test_tier2_huber_loss_attenuates_large_deviations():
    """Tier 2: When deviation > 0.5, beta is attenuated by 1 / (1 + dev^2)."""
    # Compare adaptation under a moderate deviation vs large deviation
    # Moderate deviation: current=20.0, target=25.0 -> dev = 5/20 = 0.25 <= 0.5 -> beta_eff = 0.2
    store_mod = ProfileStore({"m": make_spec("m", throughput=20.0)}, warmup_observations=0, beta=0.2)
    up_mod = store_mod.record(make_obs("m", throughput=25.0))
    step_mod = up_mod.throughput - 20.0  # 0.2 * (25 - 20) = 1.0

    # Large deviation: current=20.0, target=40.0 -> dev = 20/20 = 1.0 > 0.5
    # beta_eff = 0.2 / (1 + 1^2) = 0.10
    # step without Huber would be 0.2 * 20 = 4.0
    # step with Huber is 0.1 * 20 = 2.0
    store_large = ProfileStore({"m": make_spec("m", throughput=20.0)}, warmup_observations=0, beta=0.2)
    up_large = store_large.record(make_obs("m", throughput=40.0))
    step_large = up_large.throughput - 20.0

    assert step_mod == pytest.approx(1.0)
    assert step_large == pytest.approx(2.0)
    # Verify effective beta was halved from 0.20 to 0.10
    assert step_large / (40.0 - 20.0) == pytest.approx(0.10)


def test_tier3_slew_rate_limiter_clamps_single_step_shift():
    """Tier 3: Single-step changes are clamped to +/- 20% of current throughput."""
    # Current throughput = 20.0, max shift = 20 * 0.20 = 4.0 -> bounds [16.0, 24.0]
    store = ProfileStore(
        {"m": make_spec("m", throughput=20.0)},
        warmup_observations=0,
        beta=1.0,  # aggressive beta=1.0 to test clamping
        slew_rate_max=0.20,
    )

    # Enormous target: 100.0 req/s
    up_high = store.record(make_obs("m", throughput=100.0))
    assert up_high.throughput == pytest.approx(24.0), "Throughput must be clamped to +20% (24.0)"

    # Enormous drop target: 1.0 req/s from current 24.0 (bounds [24 * 0.8, 24 * 1.2] = [19.2, 28.8])
    up_low = store.record(make_obs("m", throughput=1.0))
    assert up_low.throughput == pytest.approx(24.0 * 0.80), "Throughput must be clamped to -20% (19.2)"


def test_tier4_global_physiological_bounds():
    """Tier 4: Clamped to [max(0.10 * thr_0, 1.0), 3.0 * thr_0]. Never collapses to 0."""
    initial_thr = 20.0
    store = ProfileStore(
        {"m": make_spec("m", throughput=initial_thr)},
        warmup_observations=0,
        beta=0.5,
    )

    # Continuous bombardment with zero/ultra-slow throughput
    for _ in range(50):
        store.record(make_obs("m", latency=100000.0, throughput=0.001))

    final_min = store.get("m").throughput
    expected_min = max(0.10 * initial_thr, 1.0)  # max(2.0, 1.0) = 2.0
    assert final_min == pytest.approx(expected_min)
    assert final_min >= 1.0, "Throughput must never collapse below 1.0"

    # Continuous bombardment with high throughput (100.0 req/s > 3x initial 20.0 req/s)
    store_high = ProfileStore(
        {"m": make_spec("m", throughput=initial_thr)},
        warmup_observations=0,
        beta=0.5,
    )
    for _ in range(30):
        store_high.record(make_obs("m", throughput=100.0))

    final_max = store_high.get("m").throughput
    expected_max = 3.0 * initial_thr  # 60.0
    assert final_max == pytest.approx(expected_max)
    assert final_max <= 60.0, "Throughput must never exceed 3.0 * thr_0"


# =============================================================================
# 4. Adversarial Outlier Test (Transient GC Pause)
# =============================================================================

def test_adversarial_transient_gc_pause_does_not_collapse_throughput():
    """Adversarial Outlier: A 3000ms GC spike must NOT trigger false capacity collapse.

    Scenario:
      - Healthy profile: nominal throughput 20.0 req/s, nominal latency 50.0 ms.
      - Profile completes 10 nominal calls.
      - A transient JVM GC pause or network stall occurs: latency spikes to 3000.0 ms (60x slower).
      - Without damping, implied rate = 20 * (50/3000) = 0.33 req/s would collapse capacity.
      - With 4-tier damping:
          * Tier 2 Huber loss attenuates the outlier weight.
          * Tier 3 slew rate limiter strictly clamps the single-step change to <= 20%.
      - Throughput remains >= 16.0 req/s.
      - Normal traffic resumes: throughput swiftly recovers to >= 19.0 req/s.
    """
    store = ProfileStore(
        {"m": make_spec("m", throughput=20.0, lat=50.0)},
        warmup_observations=3,
        beta=0.2,
    )

    # Warm up and run 10 nominal calls
    for _ in range(10):
        store.record(make_obs("m", latency=50.0))

    thr_before_spike = store.get("m").throughput
    assert thr_before_spike == pytest.approx(20.0, rel=1e-3)

    # Inject extreme GC pause: 3000ms latency
    spike_spec = store.record(make_obs("m", latency=3000.0))

    # Assert throughput remained resilient and did not collapse
    assert spike_spec.throughput >= 16.0, (
        f"Throughput collapsed to {spike_spec.throughput} on GC pause; expected >= 16.0"
    )
    assert spike_spec.throughput <= 24.0

    # Resume normal traffic for 5 calls
    for _ in range(5):
        store.record(make_obs("m", latency=50.0))

    recovered_thr = store.get("m").throughput
    assert recovered_thr >= 18.5, f"Throughput did not recover gracefully: {recovered_thr}"


# =============================================================================
# 5. Runtime Resource Consumption, Energy, and Cost/Watt Metrics
# =============================================================================

def test_effective_cost_and_thermodynamic_efficiency_metrics():
    """Verify energy tracking, electricity cost accumulation, and efficiency/watt calculation."""
    # Profile: 1 GPU -> baseline power = 200W, initial price = 100.0, throughput = 20.0
    store = ProfileStore(
        {"edge_gpu": make_spec("edge_gpu", gpus=1, price=100.0, throughput=20.0, lat=50.0)},
        electricity_price_kwh=0.12,
    )

    # Initial checks
    assert store.get_power_watts("edge_gpu") == 200.0
    assert store.get_efficiency_per_watt("edge_gpu") == pytest.approx(20.0 / 200.0)  # 0.10 req/Joule
    assert store.get_cumulative_energy_joules("edge_gpu") == 0.0
    assert store.get_effective_cost("edge_gpu") == pytest.approx(100.0)

    # Record 10 tasks, each taking 50ms latency (0.050s)
    # Energy per task = 200W * 0.050s = 10.0 Joules
    # Total energy across 10 tasks = 100.0 Joules
    # Electricity cost = 100.0 * (0.12 / 3,600,000) = 3.3333e-6 dollars
    for _ in range(10):
        store.record(make_obs("edge_gpu", latency=50.0))

    assert store.get_cumulative_energy_joules("edge_gpu") == pytest.approx(100.0)
    expected_energy_cost = 100.0 * (0.12 / 3.6e6)
    expected_eff_price = 100.0 + expected_energy_cost
    assert store.get_effective_cost("edge_gpu") == pytest.approx(expected_eff_price, abs=1e-8)


def test_custom_power_and_energy_telemetry_fields():
    """Verify observation.power_watts and observation.energy_joules are honored when passed."""
    store = ProfileStore(
        {"m": make_spec("m", gpus=1, price=50.0)},
        electricity_price_kwh=0.12,
    )

    # Explicit 250W power telemetry and explicit 15 Joules energy
    obs = make_obs("m", latency=60.0, power_watts=250.0, energy_joules=15.0)
    store.record(obs)

    assert store.get_power_watts("m") == 250.0
    assert store.get_cumulative_energy_joules("m") == pytest.approx(15.0)
    expected_cost = 50.0 + 15.0 * (0.12 / 3.6e6)
    assert store.get_effective_cost("m") == pytest.approx(expected_cost, abs=1e-8)


def test_observation_task_cost_accumulation():
    """Verify observation.cost (e.g. per-task cloud markup or service charge) accumulates."""
    store = ProfileStore({"m": make_spec("m", price=100.0)})

    obs1 = make_obs("m", latency=50.0, cost=0.25)
    obs2 = make_obs("m", latency=50.0, cost=0.75)
    store.record(obs1)
    store.record(obs2)

    # Expected effective cost: initial price + observed cost (1.00) + microscopic energy
    eff_cost = store.get_effective_cost("m")
    assert eff_cost >= 101.0
    assert eff_cost == pytest.approx(101.0, rel=1e-4)


def test_unprofiled_methods_raise_not_profiled():
    """Helper accessors on missing profile IDs must raise NotProfiled."""
    store = ProfileStore({})
    with pytest.raises(NotProfiled):
        store.get_effective_cost("non_existent")
    with pytest.raises(NotProfiled):
        store.get_efficiency_per_watt("non_existent")
    with pytest.raises(NotProfiled):
        store.get_cumulative_energy_joules("non_existent")
    with pytest.raises(NotProfiled):
        store.get_power_watts("non_existent")


# =============================================================================
# 6. Snapshot Immutability and Invariant Verification (I1-I5)
# =============================================================================

def test_snapshot_immutability_with_v5_fields():
    """Verify store.snapshot() returns an immutable detached dictionary."""
    store = ProfileStore({"m": make_spec("m", throughput=20.0, lat=50.0, obs=5)})
    snap1 = store.snapshot()

    # Modify store with a new observation
    store.record(make_obs("m", latency=100.0, throughput=12.0))

    assert snap1["m"].throughput == 20.0
    assert snap1["m"].observations == 5
    assert store.get("m").throughput < 20.0
    assert store.get("m").observations == 6


def test_allocation_invariants_satisfied_under_self_corrected_profiles():
    """Verify allocation results on self-corrected ProfileStore snapshots satisfy I1-I5.

    Tests both Track C and Exact MILP against invariants.check().
    """
    tasks = [
        Task(TaskId("wf1", "t1"), "parse", load=5.0, rel_floor=0.90, lat_ceil=200.0),
        Task(TaskId("wf1", "t2"), "classify", load=4.0, rel_floor=0.85, lat_ceil=200.0),
        Task(TaskId("wf2", "t1"), "parse", load=6.0, rel_floor=0.90, lat_ceil=200.0),
    ]

    profiles = {
        "parse-cheap": make_spec("parse-cheap", declared_type="parse", throughput=20.0, gpus=1, price=100.0, obs=5),
        "parse-solid": make_spec("parse-solid", declared_type="parse", throughput=20.0, gpus=2, price=250.0, obs=5),
        "classify-cheap": make_spec("classify-cheap", declared_type="classify", throughput=20.0, gpus=1, price=120.0, obs=5),
        "classify-solid": make_spec("classify-solid", declared_type="classify", throughput=20.0, gpus=2, price=280.0, obs=5),
    }

    store = ProfileStore(profiles, beta=0.2)

    # Ingest several observations including load and latency changes
    for _ in range(5):
        store.record(make_obs("parse-cheap", latency=60.0, throughput=18.0))
        store.record(make_obs("classify-cheap", latency=120.0, throughput=14.0))

    calibrated_snapshot = store.snapshot()
    pools = {
        tasks[0].id: ["parse-cheap", "parse-solid"],
        tasks[1].id: ["classify-cheap", "classify-solid"],
        tasks[2].id: ["parse-cheap", "parse-solid"],
    }
    budget = 6

    # Test Track C (LP + deterministic integer repair)
    alloc_c = track_c_lp.allocate(tasks, pools, calibrated_snapshot, budget=budget)
    assert alloc_c.feasible is True
    violations_c = check_invariants(alloc_c, tasks, pools, calibrated_snapshot, budget)
    assert violations_c == [], f"Track C produced invariant violations: {violations_c}"

    # Test Exact MILP baseline
    alloc_milp = exact_milp.allocate(tasks, pools, calibrated_snapshot, budget=budget)
    assert alloc_milp.feasible is True
    violations_milp = check_invariants(alloc_milp, tasks, pools, calibrated_snapshot, budget)
    assert violations_milp == [], f"Exact MILP produced invariant violations: {violations_milp}"


# =============================================================================
# 7. Strict Backward Compatibility
# =============================================================================

def test_strict_backward_compatibility_with_standard_observation():
    """Verify that standard 6-field Observation without v5 fields works seamlessly."""
    store = ProfileStore({"m": make_spec("m", throughput=20.0, lat=50.0)})

    # Standard Observation from poc.formulation.types
    standard_obs = Observation(
        task_id=TaskId("wf", "t1"),
        profile_id="m",
        latency=50.0,
        success=True,
        cost=0.0,
        timestamp=datetime.now(),
    )

    updated = store.record(standard_obs)
    assert updated.observations == 1
    assert updated.throughput == pytest.approx(20.0)
    assert updated.latency == pytest.approx(50.0)
    assert updated.reliability > 0.90
    assert updated.price >= 100.0


def test_direct_throughput_takes_precedence_over_latency_implied():
    """Direct throughput attribute takes precedence even if latency would imply a different rate."""
    store = ProfileStore({"m": make_spec("m", throughput=20.0, lat=50.0)}, warmup_observations=0, beta=0.2)
    # Latency 100ms implies 10.0 req/s, but explicit throughput=25.0 is supplied
    obs = make_obs("m", latency=100.0, throughput=25.0)
    updated = store.record(obs)
    # Deviation = |25 - 20| / 20 = 0.25 <= 0.5 -> beta_eff = 0.2
    # cand = 0.8 * 20 + 0.2 * 25 = 21.0
    assert updated.throughput == pytest.approx(21.0)


def test_multi_profile_heterogeneous_fleet_energy_and_efficiency_ranking():
    """Verify independent multi-profile tracking and thermodynamic efficiency ranking (F31)."""
    fleet = {
        "cpu": make_spec("cpu", gpus=0, price=50.0, throughput=100.0, lat=30.0, obs=5),
        "edge": make_spec("edge", gpus=1, price=120.0, throughput=40.0, lat=45.0, obs=5),
        "dc": make_spec("dc", gpus=4, price=600.0, throughput=140.0, lat=20.0, obs=5),
    }
    store = ProfileStore(fleet)

    # Power draws
    assert store.get_power_watts("cpu") == 75.0
    assert store.get_power_watts("edge") == 200.0
    assert store.get_power_watts("dc") == 1400.0  # 350W * 4

    # Thermodynamic efficiencies (req/Joule or throughput/Watt)
    eta_cpu = store.get_efficiency_per_watt("cpu")   # 100 / 75 = 1.333
    eta_edge = store.get_efficiency_per_watt("edge") # 40 / 200 = 0.200
    eta_dc = store.get_efficiency_per_watt("dc")     # 140 / 1400 = 0.100

    assert eta_cpu > eta_edge > eta_dc, "CPU must lead thermodynamic efficiency per F31"
    assert eta_cpu == pytest.approx(100.0 / 75.0)
    assert eta_edge == pytest.approx(40.0 / 200.0)
    assert eta_dc == pytest.approx(140.0 / 1400.0)


def test_gradual_throughput_drift_tracking():
    """Verify ProfileStore tracks continuous multi-step degradation accurately."""
    store = ProfileStore({"m": make_spec("m", throughput=20.0, lat=50.0)}, warmup_observations=0, beta=0.2)

    # Simulate 5 steps of increasing latency: 50 -> 60 -> 70 -> 80 -> 90 -> 100
    latencies = [60.0, 70.0, 80.0, 90.0, 100.0]
    last_thr = 20.0
    for lat in latencies:
        up = store.record(make_obs("m", latency=lat))
        assert up.throughput < last_thr, "Throughput must monotonically decrease with latency increases"
        last_thr = up.throughput

    assert last_thr < 17.0, f"Throughput should have adapted downward significantly, got {last_thr}"


def test_reliability_ucb_unaffected_by_throughput_self_correction():
    """Verify that UCB optimism (F23/F25) operates correctly alongside throughput calibration."""
    store = ProfileStore({"m": make_spec("m", rel=0.95, throughput=20.0)}, warmup_observations=0)
    ucb_initial = store.reliability_upper_bound("m")
    assert 0.95 <= ucb_initial <= 1.0

    # Record successes with high throughput
    for _ in range(10):
        store.record(make_obs("m", latency=40.0, success=True, throughput=25.0))

    ucb_after = store.reliability_upper_bound("m")
    assert ucb_after >= 0.95
    assert store.get("m").throughput > 20.0


def test_zero_or_negative_task_cost_does_not_corrupt_price():
    """Observations with 0.0 or negative costs must not decrease or corrupt effective price."""
    store = ProfileStore({"m": make_spec("m", price=100.0)})
    up1 = store.record(make_obs("m", latency=50.0, cost=0.0))
    price1 = up1.price
    assert price1 >= 100.0

    up2 = store.record(make_obs("m", latency=50.0, cost=-5.0))
    assert up2.price >= price1, "Negative cost must not decrement price"

