"""
The closed loop: J1 -> J2 -> J3 -> J4 -> J5 -> J6 -> J7 -> J8 -> J9 -> J3 ...

Outside PoC scope — see prototype/README.md. Owner: 077.

This is the first place in the repo where the system runs as a system rather than as
components. Every job in §3.1 except J10 participates:

    J1  ingest        prototype/ingestion.py
    J2  resolve       prototype/registry.py
    J3  allocate      poc/tracks/*
    J4  persist       AssignmentRegistry below
    J5  execute       prototype/simulator.py   (simulated — see that module)
    J6  observe       simulator emits Observations
    J7  profile       prototype/profiling.py   ProfileStore
    J8  drift         prototype/profiling.py   DriftDetector
    J9  re-optimise   globally, per F18 — no scoping

WHAT THIS IS FOR

Three questions that only appear when the parts are connected, and that no component test
can ask:

  1. **Does the Profile Store converge?** The registry's declared values are deliberately
     wrong. Measured reliability should approach the hidden truth.
  2. **Does the system thrash?** A drift signal triggers a re-allocation, which changes what
     gets executed, which produces different observations, which can trigger another signal.
     That feedback path is the obvious instability and nothing has ever exercised it.
  3. **Does it respond to a real regime change?** When a profile genuinely degrades, the
     loop should notice and route away from it — and should not do so on noise.

A run returns a `RoundRecord` per round so the trajectory can be inspected rather than only
the endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from poc.formulation.types import AllocationResult, ProfileSpec, Task, TaskId
from prototype.profiling import DriftDetector, ProfileStore
from prototype.registry import ExecutorRegistry, resolve
from prototype.reoptimisation import ReoptOutcome, reoptimise_global
from prototype.simulator import SimulatedExecutor


@dataclass
class AssignmentRegistry:
    """J4 — persist versioned assignments (§2.3). Append-only; the last is active."""

    versions: list[AllocationResult] = field(default_factory=list)

    def persist(self, result: AllocationResult | ReoptOutcome) -> int:
        if not result.feasible:
            raise ValueError("refusing to persist an infeasible allocation (P9)")
        if isinstance(result, ReoptOutcome):
            result = AllocationResult(
                routing=result.routing,
                provisioning=result.provisioning,
                total_cost=result.total_cost,
                gpus_used=result.gpus_used,
                strategy=result.strategy,
                feasible=True,
            )
        self.versions.append(result)
        return len(self.versions) - 1

    @property
    def active(self) -> AllocationResult:
        if not self.versions:
            raise ValueError("no assignment has been persisted")
        return self.versions[-1]


@dataclass(frozen=True)
class RoundRecord:
    round_index: int
    routing: dict[TaskId, str]
    cost: float
    measured: dict[str, float]        # profile_id -> measured reliability
    successes: int
    failures: int
    drift_fired: bool
    drift_compatibility: float
    reallocated: bool
    reason: str


def run(batch_tasks: list[Task],
        registry: ExecutorRegistry,
        executor: SimulatedExecutor,
        allocate,
        budget: int,
        rounds: int = 20,
        drift_threshold: float = 0.9,
        min_observations: int = 5,
        adaptive: bool = True,
        optimistic_eligibility: bool = False) -> list[RoundRecord]:
    """Run the loop for `rounds` execution rounds. Returns one record per round.

    `adaptive=False` is the STATIC comparison, and it is what Murakkab does: allocate once
    from the DECLARED profiles, then execute that same plan forever. Observations are still
    recorded, but only so the evaluator can measure what the plan actually delivered — the
    system itself never sees them, never detects drift, and never re-optimises.

    That distinction is the project's differentiator made concrete. A static system does not
    become wrong when reality drifts; it becomes wrong *without noticing*, which is worse.
    """
    store = ProfileStore(registry.all_profiles())
    detector = DriftDetector(allocate, threshold=drift_threshold,
                             min_observations=min_observations)
    assignments = AssignmentRegistry()
    records: list[RoundRecord] = []

    def current_pools(profiles: dict[str, ProfileSpec]):
        """J2 against the CURRENT measured profiles, not the declared ones.

        This is what makes the loop closed: as measurement moves reliability, pools shrink
        and grow, and a profile can become ineligible for a task it was serving.
        """
        measured_registry = ExecutorRegistry()
        for spec in profiles.values():
            measured_registry.register(spec)
        bound = store.reliability_upper_bound if optimistic_eligibility else None
        return resolve(batch_tasks, measured_registry, reliability_of=bound)

    # --- J2, J3, J4 for the first round -----------------------------------------
    profiles = store.snapshot()
    pools = current_pools(profiles)
    result = allocate(batch_tasks, pools, profiles, budget)
    if not result.feasible:
        return records
    assignments.persist(result)

    for index in range(rounds):
        routing = assignments.active.routing

        # --- J5, J6 ---------------------------------------------------------------
        observations = executor.execute(routing)
        successes = sum(1 for o in observations if o.success)

        # --- J7 -------------------------------------------------------------------
        for observation in observations:
            store.record(observation)
        profiles = store.snapshot()

        if not adaptive:
            # Static: measured, but never acted on. No J2 refresh, no J8, no J9.
            records.append(RoundRecord(
                round_index=index, routing=dict(routing),
                cost=assignments.active.total_cost,
                measured={m: profiles[m].reliability for m in sorted(profiles)},
                successes=successes, failures=len(observations) - successes,
                drift_fired=False, drift_compatibility=1.0, reallocated=False,
                reason="static: observations recorded but not acted on"))
            continue

        # --- J2 again: measurement may have changed eligibility -------------------
        pools = current_pools(profiles)
        starved = [t.id for t in batch_tasks if not pools[t.id]]

        # --- J8 -------------------------------------------------------------------
        signal_candidate = None
        if starved:
            signal_fired, compatibility = True, 0.0
            reason = f"{len(starved)} task(s) have no eligible profile under measurement"
        else:
            signal = detector.check(routing, batch_tasks, pools, profiles, budget)
            signal_fired, compatibility, reason = (
                signal.fired, signal.compatibility, signal.reason)
            signal_candidate = signal.candidate

        # --- J9: global re-optimisation, per F18 / G8 ------------------------------
        reallocated = False
        if signal_fired:
            reopt = reoptimise_global(allocate, batch_tasks, pools, profiles, budget,
                                     candidate=signal_candidate)
            if reopt.feasible:
                assignments.persist(reopt)
                reallocated = True
            else:
                reason += f"; {reopt.reason or 're-optimisation infeasible, keeping the previous assignment'}"

        records.append(RoundRecord(
            round_index=index,
            routing=dict(routing),
            cost=assignments.active.total_cost,
            measured={m: profiles[m].reliability for m in sorted(profiles)},
            successes=successes,
            failures=len(observations) - successes,
            drift_fired=signal_fired,
            drift_compatibility=compatibility,
            reallocated=reallocated,
            reason=reason,
        ))

    return records
