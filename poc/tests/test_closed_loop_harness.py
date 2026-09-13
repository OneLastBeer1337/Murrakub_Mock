"""
Test Suite for Formal Closed-Loop Benchmark Evaluation Harness (G9).

Spec: docs/design/System_Architecture_v5.md §5, §7.3.
Owner: Benchmark Harness Implementer (Milestone 3).

Verifies:
  - Determinism and reproducibility under identical seeds (Principle P10).
  - Static Baseline freezing under drift (Murakkab 60-min blind epoch).
  - Adaptive Closed Loop detection, sub-100ms re-optimization, and recovery.
  - Comparative advantage: delivered reliability, SLA violation reduction, MTTR.
  - Three distinct drift scenarios: thermal throttling, workload surge, network degradation.
  - Fixed-width ASCII summary table formatting.
  - JSON report Draft-07 schema compliance.
  - Murakkab Invariants I1–I5 compliance on all allocations.
"""

import json
from pathlib import Path

import pytest

from poc.formulation import invariants
from poc.harness.closed_loop_runner import (ClosedLoopConfig,
                                           ClosedLoopRunResult,
                                           ClosedLoopRunner, DriftEvent,
                                           RoundTelemetry,
                                           create_benchmark_instance)


@pytest.fixture
def benchmark_instance():
    return create_benchmark_instance(budget=12, seed=42)


@pytest.fixture
def runner():
    return ClosedLoopRunner()


# -----------------------------------------------------------------------------
# 1. Configuration Validation and Defaults
# -----------------------------------------------------------------------------

def test_closed_loop_config_defaults_and_validation(benchmark_instance):
    """Test default values and validation checks on ClosedLoopConfig."""
    cfg = ClosedLoopConfig()
    assert cfg.total_rounds == 20
    assert cfg.epoch_length == 20
    assert cfg.round_duration_minutes == 3.0
    assert cfg.solver_strategy == "C"
    assert cfg.base_instance is not None
    assert len(cfg.base_instance.tasks) == 8
    assert len(cfg.base_instance.profiles) == 8
    assert cfg.drift_schedule == []

    with pytest.raises(ValueError, match="total_rounds must be positive"):
        ClosedLoopConfig(total_rounds=0)

    with pytest.raises(ValueError, match="epoch_length must be positive"):
        ClosedLoopConfig(epoch_length=-5)

    custom_cfg = ClosedLoopConfig(total_rounds=10, epoch_length=5, base_instance=benchmark_instance)
    assert custom_cfg.total_rounds == 10
    assert custom_cfg.epoch_length == 5
    assert custom_cfg.base_instance is benchmark_instance


# -----------------------------------------------------------------------------
# 2. Determinism and Reproducibility (Principle P10)
# -----------------------------------------------------------------------------

def test_determinism_and_reproducibility(runner, benchmark_instance):
    """Principle P10: Two identical runs with the same seed generate bit-exact telemetry."""
    event = DriftEvent(round_idx=2, task_id=benchmark_instance.tasks[0].id, drift_type="network_degradation", severity=0.35)
    cfg1 = ClosedLoopConfig(total_rounds=6, base_instance=benchmark_instance, drift_schedule=[event], random_seed=999)
    cfg2 = ClosedLoopConfig(total_rounds=6, base_instance=benchmark_instance, drift_schedule=[event], random_seed=999)

    res1 = runner.run_adaptive_closed_loop(cfg1)
    res2 = runner.run_adaptive_closed_loop(cfg2)

    assert res1.total_cost == res2.total_cost
    assert res1.mean_reliability == res2.mean_reliability
    assert res1.sla_violations == res2.sla_violations
    assert res1.recovery_time_rounds == res2.recovery_time_rounds

    for r1, r2 in zip(res1.rounds, res2.rounds):
        assert r1.round_idx == r2.round_idx
        assert r1.reliability == r2.reliability
        assert r1.latency == r2.latency
        assert r1.cost == r2.cost
        assert r1.sla_violations == r2.sla_violations
        assert r1.routing == r2.routing
        assert r1.provisioning == r2.provisioning
        assert r1.reoptimized == r2.reoptimized


# -----------------------------------------------------------------------------
# 3. Static Baseline Freezing Under Drift (Murakkab Replication)
# -----------------------------------------------------------------------------

def test_static_baseline_freezes_assignments_under_drift(runner, benchmark_instance):
    """Murakkab 60-min blind epoch: routing & provisioning remain frozen across epoch rounds.

    Under unannounced drift, SLA violations occur while routing never changes.
    """
    event = DriftEvent(round_idx=2, task_id=benchmark_instance.tasks[0].id, drift_type="thermal_throttling", severity=0.5)
    cfg = ClosedLoopConfig(total_rounds=6, epoch_length=20, base_instance=benchmark_instance, drift_schedule=[event], random_seed=42)

    result = runner.run_static_baseline(cfg)

    # Routing and provisioning remain frozen across all rounds
    initial_routing = result.rounds[0].routing
    initial_provisioning = result.rounds[0].provisioning
    for r in result.rounds:
        assert r.routing == initial_routing
        assert r.provisioning == initial_provisioning
        assert not r.reoptimized
        assert r.reopt_latency_ms == 0.0

    # Post-drift rounds incur SLA violations
    assert result.sla_violations > 0
    post_drift_violations = sum(r.sla_violations for r in result.rounds if r.round_idx >= 2)
    assert post_drift_violations > 0
    # Static system never recovers within the epoch
    assert result.recovery_time_rounds == len(result.rounds) - 2


# -----------------------------------------------------------------------------
# 4. Adaptive Closed Loop Detection, Sub-100ms Re-Optimization, and Recovery
# -----------------------------------------------------------------------------

def test_adaptive_closed_loop_detects_and_recovers(runner, benchmark_instance):
    """Adaptive Closed Loop intercepts telemetry, detects drift, and restores compliance."""
    event = DriftEvent(round_idx=2, task_id=benchmark_instance.tasks[0].id, drift_type="network_degradation", severity=0.4)
    cfg = ClosedLoopConfig(total_rounds=6, base_instance=benchmark_instance, drift_schedule=[event], random_seed=42)

    result = runner.run_adaptive_closed_loop(cfg)

    # Re-optimization must be triggered
    reopt_rounds = [r for r in result.rounds if r.reoptimized]
    assert len(reopt_rounds) > 0

    # Re-optimization latency must be bounded sub-100ms (F13/F16)
    assert result.mean_reopt_latency_ms < 100.0
    for r in reopt_rounds:
        assert r.reopt_latency_ms < 100.0

    # Fast recovery: MTTR <= 2 rounds
    assert result.recovery_time_rounds <= 2

    # In final rounds after adaptation, SLA violations drop to 0
    assert result.rounds[-1].sla_violations == 0


# -----------------------------------------------------------------------------
# 5. Comparative Advantage: Adaptive vs. Static Baseline
# -----------------------------------------------------------------------------

def test_comparative_advantage_over_static(runner, benchmark_instance):
    """Novelty Differentiator (F24): Adaptive delivers higher reliability and fewer SLA breaches."""
    event = DriftEvent(round_idx=2, task_id=benchmark_instance.tasks[0].id, drift_type="network_degradation", severity=0.4)
    cfg = ClosedLoopConfig(total_rounds=8, base_instance=benchmark_instance, drift_schedule=[event], random_seed=42)

    baseline, adaptive = runner.compare(cfg)

    # Adaptive delivers higher or equal reliability
    assert adaptive.mean_reliability >= baseline.mean_reliability
    # Adaptive sharply reduces SLA floor violations
    assert adaptive.sla_violations < baseline.sla_violations
    # Adaptive MTTR is strictly faster than static baseline
    assert adaptive.recovery_time_rounds < baseline.recovery_time_rounds


# -----------------------------------------------------------------------------
# 6. Drift Scenarios: Thermal Throttling
# -----------------------------------------------------------------------------

def test_drift_scenario_thermal_throttling(runner, benchmark_instance):
    """Scenario A: DVFS frequency throttling causes throughput collapse and latency increase."""
    event = DriftEvent(round_idx=2, task_id=benchmark_instance.tasks[0].id, drift_type="thermal_throttling", severity=0.5)
    cfg = ClosedLoopConfig(total_rounds=6, base_instance=benchmark_instance, drift_schedule=[event], random_seed=42)

    baseline, adaptive = runner.compare(cfg)

    # Baseline exhibits latency ceiling breaches
    base_lat_viols = sum(r.lat_violations for r in baseline.rounds)
    assert base_lat_viols > 0

    # Adaptive loop restores latency compliance
    adapt_lat_viols = sum(r.lat_violations for r in adaptive.rounds)
    assert adapt_lat_viols < base_lat_viols
    assert adaptive.recovery_time_rounds <= 1


# -----------------------------------------------------------------------------
# 7. Drift Scenarios: Workload Surge
# -----------------------------------------------------------------------------

def test_drift_scenario_workload_surge(runner, benchmark_instance):
    """Scenario B: Demand burst multiplies task load, breaching frozen baseline capacity."""
    # Severity 3.5 scales task load by 4.5x, clearly exceeding single-instance capacity of 20.0
    event = DriftEvent(round_idx=2, task_id=benchmark_instance.tasks[0].id, drift_type="workload_surge", severity=3.5)
    cfg = ClosedLoopConfig(total_rounds=6, base_instance=benchmark_instance, drift_schedule=[event], random_seed=42)

    baseline, adaptive = runner.compare(cfg)

    # Baseline exhibits capacity headroom breaches
    base_cap_viols = sum(r.cap_violations for r in baseline.rounds)
    assert base_cap_viols > 0

    # Adaptive loop re-provisions capacity, restoring headroom
    adapt_cap_viols = sum(r.cap_violations for r in adaptive.rounds)
    assert adapt_cap_viols < base_cap_viols
    assert adaptive.recovery_time_rounds <= 2


# -----------------------------------------------------------------------------
# 8. Drift Scenarios: Network Latency Degradation
# -----------------------------------------------------------------------------

def test_drift_scenario_network_degradation(runner, benchmark_instance):
    """Scenario C: Network transit congestion adds +120ms latency and depresses reliability."""
    event = DriftEvent(round_idx=2, task_id=benchmark_instance.tasks[0].id, drift_type="network_degradation", severity=0.35)
    cfg = ClosedLoopConfig(total_rounds=6, base_instance=benchmark_instance, drift_schedule=[event], random_seed=42)

    baseline, adaptive = runner.compare(cfg)

    # Baseline exhibits sustained reliability floor breaches
    base_rel_viols = sum(r.rel_violations for r in baseline.rounds)
    assert base_rel_viols > 0

    # Adaptive loop detects parameter cliff and migrates to reliable profile
    adapt_rel_viols = sum(r.rel_violations for r in adaptive.rounds)
    assert adapt_rel_viols < base_rel_viols
    assert adaptive.mean_reliability > baseline.mean_reliability


# -----------------------------------------------------------------------------
# 9. Structured ASCII Summary Table Formatting
# -----------------------------------------------------------------------------

def test_summary_table_formatting(runner, benchmark_instance):
    """Verify ASCII table renders all required metrics, columns, and invariant status."""
    event = DriftEvent(round_idx=2, task_id=benchmark_instance.tasks[0].id, drift_type="thermal_throttling", severity=0.5)
    cfg = ClosedLoopConfig(total_rounds=4, base_instance=benchmark_instance, drift_schedule=[event], random_seed=42)

    baseline, adaptive = runner.compare(cfg)
    table_str = runner.export_summary_table(baseline, adaptive)

    assert "FORMAL CLOSED-LOOP EVALUATION BENCHMARK (G9)" in table_str
    assert "Delivered Reliability (Overall)" in table_str
    assert "SLA Floor Violations (Count)" in table_str
    assert "Cumulative Fleet Cost" in table_str
    assert "Mean Re-Optimization Latency" in table_str
    assert "Mean Recovery Time (MTTR)" in table_str
    assert "Formal Invariant Compliance" in table_str
    assert "Static Baseline (Murakkab)" in table_str
    assert "Adaptive Closed Loop (Ours)" in table_str
    assert "PASS" in table_str


# -----------------------------------------------------------------------------
# 10. JSON Report Draft-07 Schema Compliance
# -----------------------------------------------------------------------------

def test_json_report_export_and_schema(runner, benchmark_instance, tmp_path: Path):
    """Verify export_json generates Draft-07 matching structure and serializes to disk."""
    event = DriftEvent(round_idx=2, task_id=benchmark_instance.tasks[0].id, drift_type="network_degradation", severity=0.3)
    cfg = ClosedLoopConfig(total_rounds=4, base_instance=benchmark_instance, drift_schedule=[event], random_seed=42)

    baseline, adaptive = runner.compare(cfg)
    json_path = str(tmp_path / "benchmark_report.json")

    report = runner.export_json(baseline, adaptive, output_path=json_path)

    # Required top-level keys per System Architecture v5 §5.4
    assert "metadata" in report
    assert "scenarios" in report
    assert "static_baseline" in report
    assert "adaptive_closed_loop" in report
    assert "comparison_summary" in report

    # Metadata fields
    meta = report["metadata"]
    assert "timestamp" in meta
    assert meta["seed"] == cfg.random_seed
    assert meta["budget"] == benchmark_instance.budget
    assert meta["task_count"] == len(benchmark_instance.tasks)
    assert meta["profile_count"] == len(benchmark_instance.profiles)

    # Baseline & Adaptive fields
    assert "overall_reliability" in report["static_baseline"]
    assert "total_sla_violations" in report["static_baseline"]
    assert "cumulative_cost" in report["static_baseline"]

    assert "overall_reliability" in report["adaptive_closed_loop"]
    assert "total_sla_violations" in report["adaptive_closed_loop"]
    assert "mean_reopt_latency_ms" in report["adaptive_closed_loop"]

    # Summary deltas
    summary = report["comparison_summary"]
    assert "reliability_delta" in summary
    assert "violation_reduction_pct" in summary
    assert "cost_overhead_pct" in summary
    assert "speedup_factor" in summary

    # Verify file content
    with open(json_path, "r", encoding="utf-8") as f:
        loaded = json.load(f)
    assert loaded["metadata"]["seed"] == cfg.random_seed


# -----------------------------------------------------------------------------
# 11. Murakkab Invariants I1–I5 Compliance
# -----------------------------------------------------------------------------

def test_invariant_compliance_across_all_rounds(runner, benchmark_instance):
    """Verify all allocations produced across rounds satisfy Invariants I1–I5."""
    event = DriftEvent(round_idx=2, task_id=benchmark_instance.tasks[0].id, drift_type="workload_surge", severity=2.0)
    cfg = ClosedLoopConfig(total_rounds=6, base_instance=benchmark_instance, drift_schedule=[event], random_seed=42)

    adaptive_res = runner.run_adaptive_closed_loop(cfg)
    tasks, pools, profiles, budget = benchmark_instance.unpack()

    for r in adaptive_res.rounds:
        alloc = invariants.AllocationResult(
            routing=r.routing,
            provisioning=r.provisioning,
            total_cost=r.hourly_cost,
            gpus_used=sum(r.provisioning[m] * profiles[m].gpus for m in r.provisioning if m in profiles),
            strategy="C",
            feasible=True,
        )
        violations = invariants.check(alloc, tasks, pools, profiles, budget)
        assert violations == [], f"Invariant violation on round {r.round_idx}: {violations}"


# -----------------------------------------------------------------------------
# 12. Multi-Epoch Execution Verification
# -----------------------------------------------------------------------------

def test_multi_epoch_execution(runner, benchmark_instance):
    """Verify multi-epoch execution (e.g. 2 epochs of 4 rounds = 8 rounds)."""
    cfg = ClosedLoopConfig(total_rounds=8, epoch_length=4, base_instance=benchmark_instance, random_seed=42)
    res = runner.run_static_baseline(cfg)

    assert len(res.rounds) == 8
    # Verify epoch indices
    assert [r.epoch_idx for r in res.rounds] == [0, 0, 0, 0, 1, 1, 1, 1]
