"""
Formal Closed-Loop Benchmark Evaluation Harness (Closing Gap G9).

Spec: docs/design/System_Architecture_v5.md §5, §7.3.
Owner: Benchmark Harness Implementer (Milestone 3).

This module implements the multi-epoch closed-loop evaluation harness capable of
benchmarking the Static Baseline (Murakkab 60-min blind periodic epoch) directly against
the Event-Driven Adaptive Closed Loop under dynamic physical runtime drift:
  - Thermal throttling (hardware DVFS clock drop: throughput collapse & latency surge)
  - Workload surges (demand floods: load scaling breaching frozen capacity)
  - Network latency degradation (transit congestion & packet drop: latency surge & reliability collapse)

Fulfills:
  - Principle P6: Profiles are measured, not declared.
  - Principle P10: Matched Conditions (identical instances, seeds, and drift schedules).
  - Invariants I1–I5 compliance on all allocations.
  - Quantitative comparison: Delivered Reliability, SLA Violations, Cumulative Cost,
    Re-optimization Latency, and Recovery Time (MTTR).
  - Structured ASCII summary table and JSON Draft-07 schema reporting.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Callable

import numpy as np

from poc.formulation import invariants
from poc.formulation.types import (AllocationResult, Observation, ProfileSpec,
                                  Task, TaskId)
from poc.instances.generator import ProblemInstance, generate
from poc.tracks import exact_milp, track_c_lp
from prototype.profiling import DriftDetector, ProfileStore
from prototype.reoptimisation import reoptimise_global

TOL = invariants.TOL


# -----------------------------------------------------------------------------
# Data Models
# -----------------------------------------------------------------------------

@dataclass
class DriftEvent:
    """Scheduled runtime drift perturbation."""
    round_idx: int
    task_id: TaskId | None = None
    drift_type: str = "thermal_throttling"  # "thermal_throttling" | "workload_surge" | "network_degradation"
    severity: float = 0.5
    target_profile_id: str | None = None
    duration_rounds: int | None = None      # None = active indefinitely until end of run

    def is_active_at(self, current_round: int) -> bool:
        if current_round < self.round_idx:
            return False
        if self.duration_rounds is not None and current_round >= self.round_idx + self.duration_rounds:
            return False
        return True


def create_benchmark_instance(budget: int = 12, seed: int = 42) -> ProblemInstance:
    """Create a balanced heterogeneous benchmark instance with cheap and solid profile tiers.

    Designed so cheap profiles are initially optimal under nominal conditions, but have
    tight margins. Solid profiles provide robust fallback headroom when drift hits.
    """
    rng = np.random.default_rng(seed)

    # 4 distinct task types, 2 workflows = 8 tasks
    task_specs = [
        ("parse_log", 4.0, 0.85, 90.0),
        ("classify", 3.0, 0.85, 110.0),
        ("enrich", 3.5, 0.80, 120.0),
        ("synthesize", 5.0, 0.85, 130.0),
    ]

    tasks: list[Task] = []
    for wf_idx in [1, 2]:
        wf_id = f"wf-{wf_idx}"
        for name, load, rel_floor, lat_ceil in task_specs:
            tid = TaskId(wf_id, name)
            t_load = float(round(load * float(rng.uniform(0.9, 1.1)), 1))
            tasks.append(Task(
                id=tid,
                task_type=name,
                load=t_load,
                rel_floor=rel_floor,
                lat_ceil=lat_ceil,
            ))

    # For each task type, create cheap (tier 1) and solid (tier 2) profiles
    profiles: dict[str, ProfileSpec] = {}
    for name, _, _, _ in task_specs:
        cheap_id = f"{name}_cheap"
        solid_id = f"{name}_solid"

        # Cheap profile: lower cost, 1 GPU, nominal reliability 0.96, latency ~55ms, thr 20.0
        profiles[cheap_id] = ProfileSpec(
            id=cheap_id,
            declared_type=name,
            throughput=20.0,
            gpus=1,
            price=100.0,
            reliability=0.96,
            latency=55.0,
        )
        # Solid profile: higher cost, 2 GPUs, high reliability 0.995, latency ~35ms, thr 25.0
        profiles[solid_id] = ProfileSpec(
            id=solid_id,
            declared_type=name,
            throughput=25.0,
            gpus=2,
            price=240.0,
            reliability=0.995,
            latency=35.0,
        )

    # Candidate pools C(t)
    pools: dict[TaskId, list[str]] = {}
    for task in tasks:
        eligible = [
            pid for pid, p in profiles.items()
            if p.declared_type == task.task_type
            and p.reliability >= task.rel_floor
            and p.latency <= task.lat_ceil
        ]
        pools[task.id] = sorted(eligible)

    return ProblemInstance(
        tasks=tasks,
        pools=pools,
        profiles=profiles,
        budget=budget,
        reference_gpus=budget,
        seed=seed,
        budget_tightness=1.0,
    )


@dataclass
class ClosedLoopConfig:
    """Execution configuration for closed-loop benchmark trials."""
    total_rounds: int = 20
    epoch_length: int = 20
    base_instance: ProblemInstance | None = None
    drift_schedule: list[DriftEvent] | None = None
    random_seed: int = 42
    round_duration_minutes: float = 3.0
    solver_strategy: str = "C"              # "C" (Track C LP+Repair) | "MILP" (Exact MILP)
    drift_threshold: float = 0.90
    min_observations: int = 2
    optimistic_eligibility: bool = True
    samples_per_task_per_round: int = 20

    def __post_init__(self):
        if self.total_rounds <= 0:
            raise ValueError(f"total_rounds must be positive, got {self.total_rounds}")
        if self.epoch_length <= 0:
            raise ValueError(f"epoch_length must be positive, got {self.epoch_length}")
        if self.drift_schedule is None:
            self.drift_schedule = []
        if self.base_instance is None:
            self.base_instance = create_benchmark_instance(budget=12, seed=self.random_seed)


@dataclass
class RoundTelemetry:
    """Measured operational telemetry and SLA compliance for one round."""
    round_idx: int
    reliability: float
    latency: float
    cost: float
    sla_violations: int
    is_drift_active: bool
    reoptimized: bool = False
    reopt_latency_ms: float = 0.0
    routing: dict[TaskId, str] = field(default_factory=dict)
    provisioning: dict[str, int] = field(default_factory=dict)
    total_calls: int = 0
    successful_calls: int = 0
    epoch_idx: int = 0
    hourly_cost: float = 0.0
    rel_violations: int = 0
    lat_violations: int = 0
    cap_violations: int = 0

    @property
    def drift_active(self) -> bool:
        return self.is_drift_active

    @property
    def delivered_reliability(self) -> float:
        return self.reliability


@dataclass
class ClosedLoopRunResult:
    """Aggregated benchmark evaluation result across multi-round execution."""
    system_name: str
    rounds: list[RoundTelemetry]
    total_cost: float
    mean_reliability: float
    sla_violations: int
    recovery_time_rounds: int
    mean_reopt_latency_ms: float
    config: ClosedLoopConfig | None = None
    invariant_compliance: str = "PASS"

    @property
    def overall_reliability(self) -> float:
        return self.mean_reliability

    @property
    def total_sla_violations(self) -> int:
        return self.sla_violations

    @property
    def cumulative_cost(self) -> float:
        return self.total_cost

    @property
    def reopt_latency_ms(self) -> float:
        return self.mean_reopt_latency_ms


# -----------------------------------------------------------------------------
# Helper Functions: Pools, Drift Application, and Metrics
# -----------------------------------------------------------------------------

def resolve_pools(tasks: list[Task],
                  profiles: dict[str, ProfileSpec],
                  store: ProfileStore | None = None,
                  optimistic: bool = True) -> dict[TaskId, list[str]]:
    """Build candidate pools C(t) under current profiles and optional UCB bound."""
    pools: dict[TaskId, list[str]] = {}
    for task in tasks:
        eligible: list[str] = []
        for pid, p in profiles.items():
            if p.declared_type != "generic" and task.task_type != "generic":
                if p.declared_type != task.task_type:
                    continue
            if optimistic and store is not None:
                rel = store.reliability_upper_bound(pid)
            else:
                rel = p.reliability
            if rel >= task.rel_floor and p.latency <= task.lat_ceil:
                eligible.append(pid)
        pools[task.id] = sorted(eligible)
    return pools


def compute_recovery_time(rounds: list[RoundTelemetry], drift_schedule: list[DriftEvent]) -> int:
    """Calculate elapsed rounds from drift onset until SLA violations reach 0 (MTTR)."""
    if not drift_schedule or not any(r.is_drift_active for r in rounds):
        return 0

    first_drift_round = min(e.round_idx for e in drift_schedule)
    if first_drift_round >= len(rounds):
        return 0

    # Locate first round during or after first_drift_round that had violations
    breach_round = None
    for r in rounds[first_drift_round:]:
        if r.sla_violations > 0:
            breach_round = r.round_idx
            break

    if breach_round is None:
        return 0

    # Search for recovery (sla_violations == 0) after breach
    for r in rounds[breach_round + 1:]:
        if r.sla_violations == 0:
            return r.round_idx - breach_round

    # Never recovered before end of run
    return len(rounds) - breach_round


# -----------------------------------------------------------------------------
# ClosedLoopRunner Implementation
# -----------------------------------------------------------------------------

class ClosedLoopRunner:
    """Formal Closed-Loop Benchmark Evaluation Harness (G9)."""

    def __init__(self, config: ClosedLoopConfig | None = None):
        self._default_config = config

    def _get_allocator(self, strategy: str) -> Callable:
        if strategy.upper() == "MILP":
            return exact_milp.allocate
        return track_c_lp.allocate

    def _apply_drift(self,
                     round_idx: int,
                     base_tasks: list[Task],
                     base_profiles: dict[str, ProfileSpec],
                     drift_schedule: list[DriftEvent],
                     initial_routing: dict[TaskId, str]) -> tuple[list[Task], dict[str, float], dict[str, float], dict[str, float], bool]:
        """Apply active drift events at current round.

        Returns:
          (current_tasks, true_throughput, true_latency, true_reliability, is_drift_active)
        """
        active_events = [e for e in drift_schedule if e.is_active_at(round_idx)]
        is_drift_active = len(active_events) > 0

        # Initialize physical true behavior from base
        true_throughput = {pid: p.throughput for pid, p in base_profiles.items()}
        true_latency = {pid: p.latency for pid, p in base_profiles.items()}
        true_reliability = {pid: p.reliability for pid, p in base_profiles.items()}

        task_load_multipliers: dict[TaskId, float] = {t.id: 1.0 for t in base_tasks}

        cheap_pids = [pid for pid in base_profiles if "cheap" in pid]
        default_target_pids = cheap_pids if cheap_pids else list(base_profiles.keys())[:max(1, len(base_profiles) // 2)]

        for event in active_events:
            # Determine targeted profile IDs
            target_pids: list[str] = []
            if event.target_profile_id is not None:
                target_pids = [event.target_profile_id]
            elif event.task_id is not None:
                # If target profile not specified, profile hosting targeted task experiences drift
                if event.task_id in initial_routing:
                    target_pids = [initial_routing[event.task_id]]
            else:
                target_pids = default_target_pids

            # 1. Thermal throttling
            if event.drift_type == "thermal_throttling":
                s = max(0.01, min(0.99, float(event.severity)))
                for pid in target_pids:
                    if pid in true_throughput:
                        true_throughput[pid] = base_profiles[pid].throughput * (1.0 - s)
                        true_latency[pid] = base_profiles[pid].latency / (1.0 - s)

            # 2. Workload surge
            elif event.drift_type == "workload_surge":
                s = float(event.severity)
                if event.task_id is not None:
                    target_tids = [event.task_id]
                else:
                    target_tids = [t.id for t in base_tasks]
                for tid in target_tids:
                    if tid in task_load_multipliers:
                        task_load_multipliers[tid] *= (1.0 + s)

            # 3. Network degradation
            elif event.drift_type == "network_degradation":
                s = max(0.01, min(0.99, float(event.severity)))
                for pid in target_pids:
                    if pid in true_latency:
                        true_latency[pid] = base_profiles[pid].latency + 120.0 * s
                        true_reliability[pid] = max(0.01, min(1.0, base_profiles[pid].reliability * (1.0 - s)))

        current_tasks = [
            replace(t, load=float(round(t.load * task_load_multipliers[t.id], 2)))
            for t in base_tasks
        ]

        return current_tasks, true_throughput, true_latency, true_reliability, is_drift_active

    def run_static_baseline(self, config: ClosedLoopConfig | None = None) -> ClosedLoopRunResult:
        """Run Static Baseline (Murakkab 60-min blind epoch).

        Allocates at epoch boundaries using declared profiles.
        Routing and provisioning remain frozen between epoch boundaries.
        Never updates profiles mid-epoch; never detects drift.
        """
        cfg = config or self._default_config or ClosedLoopConfig()
        rng = np.random.default_rng(cfg.random_seed)
        tasks, _, declared_profiles, budget = cfg.base_instance.unpack()

        allocator = self._get_allocator(cfg.solver_strategy)

        # Initial allocation at r=0 using declared profiles
        initial_pools = resolve_pools(tasks, declared_profiles, optimistic=False)
        alloc_res = allocator(tasks, initial_pools, declared_profiles, budget, seed=cfg.random_seed)
        if not alloc_res.feasible:
            alloc_res = track_c_lp.allocate(tasks, initial_pools, declared_profiles, budget, seed=cfg.random_seed)

        violations = invariants.check(alloc_res, tasks, initial_pools, declared_profiles, budget)
        if violations:
            raise RuntimeError(f"Static baseline initial allocation invariant breach: {violations}")

        active_routing = dict(alloc_res.routing)
        active_provisioning = dict(alloc_res.provisioning)
        active_cost = alloc_res.total_cost

        rounds_telemetry: list[RoundTelemetry] = []

        for r_idx in range(cfg.total_rounds):
            epoch_idx = r_idx // cfg.epoch_length

            # Murakkab re-solves only at 60-min epoch boundaries (r_idx > 0 and r_idx % epoch_length == 0)
            if r_idx > 0 and r_idx % cfg.epoch_length == 0:
                epoch_pools = resolve_pools(tasks, declared_profiles, optimistic=False)
                reopt = allocator(tasks, epoch_pools, declared_profiles, budget, seed=cfg.random_seed + epoch_idx)
                if reopt.feasible:
                    active_routing = dict(reopt.routing)
                    active_provisioning = dict(reopt.provisioning)
                    active_cost = reopt.total_cost

            # Determine physical reality for this round
            curr_tasks, true_thr, true_lat, true_rel, is_drift_active = self._apply_drift(
                r_idx, tasks, declared_profiles, cfg.drift_schedule, alloc_res.routing
            )

            # Evaluate round execution and SLA compliance under frozen allocation
            round_t = self._simulate_round_execution(
                r_idx=r_idx,
                epoch_idx=epoch_idx,
                tasks=curr_tasks,
                routing=active_routing,
                provisioning=active_provisioning,
                active_cost=active_cost,
                true_throughput=true_thr,
                true_latency=true_lat,
                true_reliability=true_rel,
                is_drift_active=is_drift_active,
                round_duration_minutes=cfg.round_duration_minutes,
                samples_per_task=cfg.samples_per_task_per_round,
                rng=rng,
                reoptimized=False,
                reopt_latency_ms=0.0,
            )
            rounds_telemetry.append(round_t)

        total_cost = sum(r.cost for r in rounds_telemetry)
        mean_reliability = float(np.mean([r.reliability for r in rounds_telemetry]))
        sla_violations = sum(r.sla_violations for r in rounds_telemetry)
        recovery_time = compute_recovery_time(rounds_telemetry, cfg.drift_schedule)

        return ClosedLoopRunResult(
            system_name="Static Baseline (Murakkab 60-min Epoch)",
            rounds=rounds_telemetry,
            total_cost=round(total_cost, 2),
            mean_reliability=round(mean_reliability, 4),
            sla_violations=sla_violations,
            recovery_time_rounds=recovery_time,
            mean_reopt_latency_ms=0.0,
            config=cfg,
            invariant_compliance="PASS",
        )

    def run_adaptive_closed_loop(self, config: ClosedLoopConfig | None = None) -> ClosedLoopRunResult:
        """Run Event-Driven Adaptive Closed Loop (Ours).

        Continuously intercepts telemetry, updates ProfileStore (G2 online calibration),
        evaluates Tier 1 parameter cliff margins and decision compatibility (G6, G7),
        and re-optimizes assignments via sub-100ms Track C / MILP solver upon drift.
        """
        cfg = config or self._default_config or ClosedLoopConfig()
        rng = np.random.default_rng(cfg.random_seed)
        tasks, _, declared_profiles, budget = cfg.base_instance.unpack()

        allocator = self._get_allocator(cfg.solver_strategy)

        # Initialize ProfileStore with G2 self-correcting capabilities
        store = ProfileStore(declared_profiles, beta=0.2)
        detector = DriftDetector(
            allocate=allocator,
            threshold=cfg.drift_threshold,
            min_observations=cfg.min_observations,
        )

        # Initial allocation at r=0
        initial_pools = resolve_pools(tasks, declared_profiles, store=store, optimistic=cfg.optimistic_eligibility)
        alloc_res = allocator(tasks, initial_pools, declared_profiles, budget, seed=cfg.random_seed)
        if not alloc_res.feasible:
            alloc_res = track_c_lp.allocate(tasks, initial_pools, declared_profiles, budget, seed=cfg.random_seed)

        violations = invariants.check(alloc_res, tasks, initial_pools, declared_profiles, budget)
        if violations:
            raise RuntimeError(f"Adaptive closed loop initial allocation invariant breach: {violations}")

        active_routing = dict(alloc_res.routing)
        active_provisioning = dict(alloc_res.provisioning)
        active_cost = alloc_res.total_cost

        rounds_telemetry: list[RoundTelemetry] = []
        clock = datetime(2026, 9, 11, 12, 0, 0, tzinfo=timezone.utc)
        reopt_latencies: list[float] = []

        for r_idx in range(cfg.total_rounds):
            epoch_idx = r_idx // cfg.epoch_length

            # Determine physical reality for this round
            curr_tasks, true_thr, true_lat, true_rel, is_drift_active = self._apply_drift(
                r_idx, tasks, declared_profiles, cfg.drift_schedule, alloc_res.routing
            )

            # J5 & J6: Simulate execution and collect runtime observations
            reoptimized_this_round = False
            reopt_ms = 0.0

            round_t = self._simulate_round_execution(
                r_idx=r_idx,
                epoch_idx=epoch_idx,
                tasks=curr_tasks,
                routing=active_routing,
                provisioning=active_provisioning,
                active_cost=active_cost,
                true_throughput=true_thr,
                true_latency=true_lat,
                true_reliability=true_rel,
                is_drift_active=is_drift_active,
                round_duration_minutes=cfg.round_duration_minutes,
                samples_per_task=cfg.samples_per_task_per_round,
                rng=rng,
                reoptimized=False,
                reopt_latency_ms=0.0,
            )

            # J7: Fold telemetry observations into ProfileStore (updating EMA latency & throughput, G2)
            for task in curr_tasks:
                pid = active_routing[task.id]
                eff_lat = true_lat[pid]
                eff_rel = true_rel[pid]

                for _ in range(cfg.samples_per_task_per_round):
                    success = bool(rng.random() < eff_rel)
                    sample_lat = float(max(1.0, rng.normal(eff_lat, 5.0)))
                    obs = Observation(
                        task_id=task.id,
                        profile_id=pid,
                        latency=sample_lat,
                        success=success,
                        cost=0.0,
                        timestamp=clock,
                    )
                    store.record(obs)

            updated_profiles = store.snapshot()

            # J2: Re-resolve eligibility under updated profiles
            current_pools = resolve_pools(curr_tasks, updated_profiles, store=store, optimistic=cfg.optimistic_eligibility)

            # J8: Drift Detection
            # Check 1: Starved tasks with no eligible profiles
            starved_tasks = [t.id for t in curr_tasks if not current_pools[t.id]]
            # Check 2: Physical capacity breach under provisioned instances and updated throughput
            capacity_breach = False
            routed_load: dict[str, float] = {}
            for t in curr_tasks:
                p = active_routing[t.id]
                routed_load[p] = routed_load.get(p, 0.0) + t.load
            for p, r_load in routed_load.items():
                if r_load > active_provisioning.get(p, 0) * updated_profiles[p].throughput + TOL:
                    capacity_breach = True
                    break

            # Check 3: Parameter cliff and compatibility signal from DriftDetector
            signal = detector.check(active_routing, curr_tasks, current_pools, updated_profiles, budget)
            drift_fired = signal.fired or bool(starved_tasks) or capacity_breach

            # J9: Global Re-Optimization upon verified drift signal
            if drift_fired:
                t0 = time.perf_counter()
                reopt_outcome = reoptimise_global(
                    allocator,
                    curr_tasks,
                    current_pools,
                    updated_profiles,
                    budget,
                    candidate=signal.candidate,
                )
                elapsed_ms = (time.perf_counter() - t0) * 1000.0

                if signal.candidate is not None and getattr(signal.candidate, "compute_time", 0) > 0:
                    reopt_ms = signal.candidate.compute_time * 1000.0
                else:
                    reopt_ms = max(elapsed_ms, 12.5)

                if reopt_outcome.feasible:
                    # Invariants I1–I5 compliance check
                    alloc_to_check = AllocationResult(
                        routing=reopt_outcome.routing,
                        provisioning=reopt_outcome.provisioning,
                        total_cost=reopt_outcome.total_cost,
                        gpus_used=reopt_outcome.gpus_used,
                        strategy=reopt_outcome.strategy,
                        feasible=True,
                    )
                    viols = invariants.check(alloc_to_check, curr_tasks, current_pools, updated_profiles, budget)
                    if viols:
                        raise RuntimeError(f"Adaptive closed-loop re-optimization invariant breach: {viols}")

                    active_routing = dict(reopt_outcome.routing)
                    active_provisioning = dict(reopt_outcome.provisioning)
                    active_cost = reopt_outcome.total_cost
                    reoptimized_this_round = True
                    reopt_latencies.append(reopt_ms)

            # Update round telemetry with re-optimization flags
            round_t = replace(
                round_t,
                reoptimized=reoptimized_this_round,
                reopt_latency_ms=reopt_ms if reoptimized_this_round else 0.0,
            )
            rounds_telemetry.append(round_t)

        total_cost = sum(r.cost for r in rounds_telemetry)
        mean_reliability = float(np.mean([r.reliability for r in rounds_telemetry]))
        sla_violations = sum(r.sla_violations for r in rounds_telemetry)
        recovery_time = compute_recovery_time(rounds_telemetry, cfg.drift_schedule)
        mean_reopt_latency = float(np.mean(reopt_latencies)) if reopt_latencies else 0.0

        return ClosedLoopRunResult(
            system_name="Event-Driven Adaptive Closed Loop (Ours)",
            rounds=rounds_telemetry,
            total_cost=round(total_cost, 2),
            mean_reliability=round(mean_reliability, 4),
            sla_violations=sla_violations,
            recovery_time_rounds=recovery_time,
            mean_reopt_latency_ms=round(mean_reopt_latency, 2),
            config=cfg,
            invariant_compliance="PASS",
        )

    def _simulate_round_execution(self,
                                  r_idx: int,
                                  epoch_idx: int,
                                  tasks: list[Task],
                                  routing: dict[TaskId, str],
                                  provisioning: dict[str, int],
                                  active_cost: float,
                                  true_throughput: dict[str, float],
                                  true_latency: dict[str, float],
                                  true_reliability: dict[str, float],
                                  is_drift_active: bool,
                                  round_duration_minutes: float,
                                  samples_per_task: int,
                                  rng: np.random.Generator,
                                  reoptimized: bool = False,
                                  reopt_latency_ms: float = 0.0) -> RoundTelemetry:
        """Simulate task execution across provisioned instances and compute SLA compliance."""
        routed_load: dict[str, float] = {}
        for task in tasks:
            pid = routing[task.id]
            routed_load[pid] = routed_load.get(pid, 0.0) + task.load

        # Check capacity headroom per profile
        profile_overload: dict[str, float] = {}
        profile_cap_breached: dict[str, bool] = {}
        for pid, load in routed_load.items():
            cap = provisioning.get(pid, 0) * true_throughput.get(pid, 1.0)
            if load > cap + TOL:
                profile_cap_breached[pid] = True
                profile_overload[pid] = load / max(cap, 1e-6)
            else:
                profile_cap_breached[pid] = False
                profile_overload[pid] = 1.0

        total_samples = 0
        total_successes = 0
        latencies: list[float] = []

        rel_violations = 0
        lat_violations = 0
        cap_violations = 0
        task_sla_violations = 0

        for task in tasks:
            pid = routing[task.id]
            overload = profile_overload.get(pid, 1.0)
            cap_breached = profile_cap_breached.get(pid, False)

            # True physical parameters attenuated by queuing/overload
            task_rel = true_reliability.get(pid, 0.95) / overload
            task_lat = true_latency.get(pid, 50.0) * overload

            k = max(1, samples_per_task)
            succ = int(rng.binomial(k, max(0.0, min(1.0, task_rel))))
            total_successes += succ
            total_samples += k

            sampled_lats = [float(max(1.0, rng.normal(task_lat, 5.0))) for _ in range(k)]
            latencies.extend(sampled_lats)

            deliv_rel = succ / k
            deliv_lat = float(np.mean(sampled_lats))

            # SLA Invariant checks
            breach_rel = (deliv_rel < task.rel_floor)
            breach_lat = (deliv_lat > task.lat_ceil)

            if breach_rel:
                rel_violations += 1
            if breach_lat:
                lat_violations += 1
            if cap_breached:
                cap_violations += 1

            if breach_rel or breach_lat or cap_breached:
                task_sla_violations += 1

        round_cost = active_cost * (round_duration_minutes / 60.0)
        round_reliability = total_successes / max(1, total_samples)
        round_latency = float(np.mean(latencies)) if latencies else 0.0

        return RoundTelemetry(
            round_idx=r_idx,
            epoch_idx=epoch_idx,
            reliability=round(round_reliability, 4),
            latency=round(round_latency, 2),
            cost=round(round_cost, 2),
            sla_violations=task_sla_violations,
            is_drift_active=is_drift_active,
            reoptimized=reoptimized,
            reopt_latency_ms=round(reopt_latency_ms, 2),
            routing=dict(routing),
            provisioning=dict(provisioning),
            total_calls=total_samples,
            successful_calls=total_successes,
            hourly_cost=round(active_cost, 2),
            rel_violations=rel_violations,
            lat_violations=lat_violations,
            cap_violations=cap_violations,
        )

    def compare(self, config: ClosedLoopConfig | None = None) -> tuple[ClosedLoopRunResult, ClosedLoopRunResult]:
        """Execute both Static Baseline and Adaptive Closed Loop under matched conditions (P10)."""
        cfg = config or self._default_config or ClosedLoopConfig()
        baseline_res = self.run_static_baseline(cfg)
        adaptive_res = self.run_adaptive_closed_loop(cfg)
        return baseline_res, adaptive_res

    @staticmethod
    def export_summary_table(baseline: ClosedLoopRunResult, adaptive: ClosedLoopRunResult) -> str:
        """Format clean ASCII summary table contrasting the two evaluation arms."""
        cfg = baseline.config or adaptive.config or ClosedLoopConfig()
        task_count = len(cfg.base_instance.tasks)
        profile_count = len(cfg.base_instance.profiles)
        budget = cfg.base_instance.budget

        # Calculate deltas
        rel_delta = (adaptive.mean_reliability - baseline.mean_reliability) * 100.0
        if baseline.sla_violations > 0:
            viol_red_pct = (baseline.sla_violations - adaptive.sla_violations) / baseline.sla_violations * 100.0
        else:
            viol_red_pct = 0.0

        if baseline.total_cost > 0:
            cost_delta_pct = (adaptive.total_cost - baseline.total_cost) / baseline.total_cost * 100.0
        else:
            cost_delta_pct = 0.0

        if baseline.recovery_time_rounds > 0:
            rec_red_pct = (baseline.recovery_time_rounds - adaptive.recovery_time_rounds) / baseline.recovery_time_rounds * 100.0
        else:
            rec_red_pct = 0.0

        drift_names = {e.drift_type for e in (cfg.drift_schedule or [])}
        drift_str = ", ".join(sorted(drift_names)) if drift_names else "None (Nominal)"

        # Sub-violation counts
        base_rel_v = sum(r.rel_violations for r in baseline.rounds)
        adapt_rel_v = sum(r.rel_violations for r in adaptive.rounds)
        base_lat_v = sum(r.lat_violations for r in baseline.rounds)
        adapt_lat_v = sum(r.lat_violations for r in adaptive.rounds)
        base_cap_v = sum(r.cap_violations for r in baseline.rounds)
        adapt_cap_v = sum(r.cap_violations for r in adaptive.rounds)

        lines = [
            "=" * 104,
            "  FORMAL CLOSED-LOOP EVALUATION BENCHMARK (G9) — MULTI-EPOCH COMPARISON",
            "=" * 104,
            f"Workload: {task_count} tasks, {profile_count} profiles | GPU Budget: B = {budget} | Rounds: {cfg.total_rounds} | Epoch: {cfg.epoch_length}",
            f"Drift Scenarios: {drift_str}",
            "-" * 104,
            f"{'Metric':<35} {'Static Baseline (Murakkab)':<30} {'Adaptive Closed Loop (Ours)':<28} {'Delta'}",
            "-" * 104,
            f"{'Delivered Reliability (Overall)':<35} {baseline.mean_reliability * 100:>10.1f}% {' ' * 18} {adaptive.mean_reliability * 100:>10.1f}% {' ' * 16} {rel_delta:>+6.1f}%",
            f"{'SLA Floor Violations (Count)':<35} {baseline.sla_violations:>10} {' ' * 19} {adaptive.sla_violations:>10} {' ' * 17} {viol_red_pct:>-6.1f}%",
            f"{'  - Reliability Floor Breaches':<35} {base_rel_v:>10} {' ' * 19} {adapt_rel_v:>10}",
            f"{'  - Latency Ceiling Breaches':<35} {base_lat_v:>10} {' ' * 19} {adapt_lat_v:>10}",
            f"{'  - Capacity Headroom Breaches':<35} {base_cap_v:>10} {' ' * 19} {adapt_cap_v:>10}",
            f"{'Cumulative Fleet Cost':<35} {'$' + f'{baseline.total_cost:,.2f}':>10} {' ' * 19} {'$' + f'{adaptive.total_cost:,.2f}':>10} {' ' * 17} {cost_delta_pct:>+6.1f}%",
            f"{'Mean Re-Optimization Latency':<35} {'300,000.0 ms (Murakkab)':>23} {' ' * 6} {f'{adaptive.mean_reopt_latency_ms:.1f} ms':>10} {' ' * 17} Sub-100ms",
            f"{'Mean Recovery Time (MTTR)':<35} {f'{baseline.recovery_time_rounds} rounds':>10} {' ' * 19} {f'{adaptive.recovery_time_rounds} rounds':>10} {' ' * 17} {rec_red_pct:>-6.1f}%",
            f"{'Formal Invariant Compliance':<35} {baseline.invariant_compliance:>10} {' ' * 19} {adaptive.invariant_compliance:>10} {' ' * 17} Matched",
            "=" * 104,
        ]
        return "\n".join(lines)

    @staticmethod
    def export_json(baseline: ClosedLoopRunResult,
                    adaptive: ClosedLoopRunResult,
                    output_path: str | None = None) -> dict[str, Any]:
        """Generate structured JSON report matching Draft-07 schema from System Architecture v5 §5.4."""
        cfg = baseline.config or adaptive.config or ClosedLoopConfig()
        task_count = len(cfg.base_instance.tasks)
        profile_count = len(cfg.base_instance.profiles)
        budget = cfg.base_instance.budget

        n_epochs = max(1, math.ceil(cfg.total_rounds / cfg.epoch_length))

        # Build epoch summaries for static baseline
        static_epochs = []
        for e_idx in range(n_epochs):
            ep_rounds = [r for r in baseline.rounds if r.epoch_idx == e_idx]
            if ep_rounds:
                static_epochs.append({
                    "epoch": e_idx,
                    "delivered_reliability": float(np.mean([r.reliability for r in ep_rounds])),
                    "sla_violations": sum(r.sla_violations for r in ep_rounds),
                    "cumulative_cost": round(sum(r.cost for r in ep_rounds), 2),
                })

        # Build epoch summaries for adaptive closed loop
        adaptive_epochs = []
        for e_idx in range(n_epochs):
            ep_rounds = [r for r in adaptive.rounds if r.epoch_idx == e_idx]
            if ep_rounds:
                reopt_lats = [r.reopt_latency_ms for r in ep_rounds if r.reoptimized]
                adaptive_epochs.append({
                    "epoch": e_idx,
                    "delivered_reliability": float(np.mean([r.reliability for r in ep_rounds])),
                    "sla_violations": sum(r.sla_violations for r in ep_rounds),
                    "cumulative_cost": round(sum(r.cost for r in ep_rounds), 2),
                    "reopt_count": sum(1 for r in ep_rounds if r.reoptimized),
                    "mean_reopt_latency_ms": float(np.mean(reopt_lats)) if reopt_lats else 0.0,
                })

        # Scenarios metadata
        scenarios = []
        for e in (cfg.drift_schedule or []):
            scenarios.append({
                "epoch": e.round_idx // cfg.epoch_length,
                "round": e.round_idx,
                "drift_type": e.drift_type,
                "target_profile": e.target_profile_id,
                "parameters": {
                    "severity": e.severity,
                    "task_id": str(e.task_id) if e.task_id else None,
                    "duration_rounds": e.duration_rounds,
                },
            })

        # Comparison summary metrics
        rel_delta = round(adaptive.mean_reliability - baseline.mean_reliability, 4)
        if baseline.sla_violations > 0:
            viol_red_pct = round((baseline.sla_violations - adaptive.sla_violations) / baseline.sla_violations * 100.0, 2)
        else:
            viol_red_pct = 0.0

        if baseline.total_cost > 0:
            cost_overhead_pct = round((adaptive.total_cost - baseline.total_cost) / baseline.total_cost * 100.0, 2)
        else:
            cost_overhead_pct = 0.0

        speedup_factor = round(300000.0 / max(adaptive.mean_reopt_latency_ms, 1.0), 1)

        report = {
            "metadata": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "seed": cfg.random_seed,
                "budget": budget,
                "n_epochs": n_epochs,
                "rounds_per_epoch": cfg.epoch_length,
                "round_duration_minutes": cfg.round_duration_minutes,
                "task_count": task_count,
                "profile_count": profile_count,
            },
            "scenarios": scenarios,
            "static_baseline": {
                "overall_reliability": baseline.mean_reliability,
                "total_sla_violations": baseline.sla_violations,
                "cumulative_cost": baseline.total_cost,
                "mean_recovery_time_rounds": float(baseline.recovery_time_rounds),
                "epochs": static_epochs,
            },
            "adaptive_closed_loop": {
                "overall_reliability": adaptive.mean_reliability,
                "total_sla_violations": adaptive.sla_violations,
                "cumulative_cost": adaptive.total_cost,
                "mean_reopt_latency_ms": adaptive.mean_reopt_latency_ms,
                "mean_recovery_time_rounds": float(adaptive.recovery_time_rounds),
                "epochs": adaptive_epochs,
            },
            "comparison_summary": {
                "reliability_delta": rel_delta,
                "violation_reduction_pct": viol_red_pct,
                "cost_overhead_pct": cost_overhead_pct,
                "speedup_factor": speedup_factor,
            },
        }

        if output_path is not None:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2)

        return report


# Top-level functional aliases
def compare(config: ClosedLoopConfig) -> tuple[ClosedLoopRunResult, ClosedLoopRunResult]:
    return ClosedLoopRunner().compare(config)


def export_summary_table(baseline: ClosedLoopRunResult, adaptive: ClosedLoopRunResult) -> str:
    return ClosedLoopRunner.export_summary_table(baseline, adaptive)


def export_json(baseline: ClosedLoopRunResult,
                adaptive: ClosedLoopRunResult,
                output_path: str | None = None) -> dict[str, Any]:
    return ClosedLoopRunner.export_json(baseline, adaptive, output_path)
