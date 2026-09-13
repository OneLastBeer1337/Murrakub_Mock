"""
The execution harness -- one simulated epoch, and the 24-hour trace experiment.

This is where Phases 2 and 3 meet. The optimizer (M4/M5) produces a plan sized on a PROJECTED
peak; the runtime serves REAL arrivals against it. Section 3.3.1 calls the split Murakkab's key
design choice:

    "decouple peak provisioning from average utilization: instance counts nm are sized for
    projected peak demand (ensuring SLO compliance), while routing fractions are optimized
    against average demand"

M6 is where `alpha = 1.15` stops being a constant in an equation and becomes a testable claim:
**is a 15% buffer, plus an auto-scaler that takes 20 minutes to add capacity, enough to absorb
the variance of Figures 2b/2d?** The runner exists to answer that, and the answer is a
measurement rather than an argument.

WHAT THIS SIMULATION CANNOT ESTABLISH. It does not prove Murakkab meets or misses SLOs in
production. There is no GPU, no serving engine, no batching, no KV cache, no network. Every
service time comes from eq. (5) evaluated on digitized profile curves, and the queueing model is
`[OURS]` (`sim/service.py`). What it CAN establish is relational and structural: whether a
20-minute provisioning delay can answer a 60-second monitoring window; how much latency the
optimizer's own latency model cannot see; how much load the EWMA projector misses. Those
conclusions follow from the mechanism, not from the magnitudes.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from execution.autoscaler import AutoScaler
from execution.dispatch import DEFAULT_POLICY, Dispatcher, policy_named
from execution.monitor import FleetMonitor
from execution.registry import ExecutableWorkflow, WorkflowRegistry
from execution.requests import Outcome, Request, RequestOutcome, SloSpec
from execution.sim.clock import (
    CONTROL_INTERVAL_S,
    EPOCH_S,
    MONITOR_WINDOW_S,
    PROVISIONING_DELAY_S,
    SimClock,
    TICK_S,
)
from execution.sim.fleet import SimulatedFleet
from execution.sim.service import ModelServer, TokenSampler, service_params
from execution.thresholds import thresholds_for
from optimization.profiles.provenance import Unavailable
from optimization.profiles.schema import ConfigKey, ModelProfileKey, ProfileSet


@dataclass
class EpochOutcome:
    """What one simulated epoch produced."""

    epoch: int
    arrivals: int
    completed: int
    violated: int
    dropped: int
    gpus_end: int
    wasted_gpu_seconds: float
    scale_events: Mapping[str, float]
    realized_split: Mapping[str, float]
    planned_split: Mapping[str, float]
    max_queue_delay_s: float
    tau_s: float | None

    @property
    def violation_rate(self) -> float:
        served = self.completed + self.violated
        return 0.0 if served == 0 else self.violated / served


@dataclass
class ExecutionRun:
    """One workflow/SLO served for one or more epochs against a fixed plan."""

    profile_set_name: str
    workflow: str
    slo: SloSpec
    dispatch_policy: str
    provisioning_delay_s: float
    spare_fraction: float
    epochs: list[EpochOutcome] = field(default_factory=list)
    outcomes: list[RequestOutcome] = field(default_factory=list)
    fidelity_notes: tuple[str, ...] = ()

    def totals(self) -> Mapping[str, float]:
        served = sum(e.completed + e.violated for e in self.epochs)
        return {
            "arrivals": float(sum(e.arrivals for e in self.epochs)),
            "served": float(served),
            "violated": float(sum(e.violated for e in self.epochs)),
            "dropped": float(sum(e.dropped for e in self.epochs)),
            "violation_rate": (
                0.0 if served == 0 else sum(e.violated for e in self.epochs) / served
            ),
            "wasted_gpu_seconds": sum(e.wasted_gpu_seconds for e in self.epochs),
        }


FIDELITY_NOTES: tuple[str, ...] = (
    "SIMULATED. No GPU, no serving engine, no batching, no KV cache, no network.",
    "Service time is eq. (5) on digitized curves; the queueing model is [OURS] (sim/service.py).",
    "A87: provisioning takes 20 min (Section 4.7) against a 60 s monitoring window (Section 3.4).",
    "A88: spare capacity defaults to 0 -- the paper names it and never sizes it.",
    "A86: 7 profiles have no TTFT, so their scale thresholds fall back to KNEE and are marked.",
    "GPU counts are for LLM executors only; tools have no profile (M3 Section 12.3).",
)


def _sampler_for(
    pset: ProfileSet, config: ConfigKey, rng: random.Random
) -> TokenSampler | None:
    profile = pset.workflow.get(config)
    if profile is None or isinstance(profile.tokens, Unavailable):
        return None
    return TokenSampler(profile.tokens, rng)


def run_epoch(
    pset: ProfileSet,
    plan: ExecutableWorkflow,
    arrivals_per_s: Sequence[float],
    epoch: int = 0,
    tau_s: float | None = None,
    dispatch_policy: str = DEFAULT_POLICY,
    seed: int = 0,
    provisioning_delay_s: float = PROVISIONING_DELAY_S,
    spare_fraction: float = 0.0,
    budget: Mapping[str, float] | None = None,
    duration_s: float = EPOCH_S,
) -> tuple[EpochOutcome, list[RequestOutcome]]:
    """Serve one epoch of arrivals against one deployment plan.

    `arrivals_per_s` is a per-second arrival rate series (len == duration_s/tick). Rates come
    from M3's Figure 19 traces; the per-request TOKEN count is drawn from the profile's own
    distribution, because that variance is what the auto-scaler exists for.
    """
    rng = random.Random(seed)
    clock = SimClock()
    routing = dict(plan.normalised_routing())
    pairs = list(routing)

    gpus_of = {m: int(pset.models[m].parallelism.value) for m in plan.instances if m in pset.models}
    for _c, m in pairs:
        if m in pset.models:
            gpus_of.setdefault(m, int(pset.models[m].parallelism.value))

    fleet = SimulatedFleet(
        gpus_of=gpus_of, budget=budget, provisioning_delay_s=provisioning_delay_s
    )
    fleet.install_plan(dict(plan.instances), now_s=0.0)
    # The plan's instances exist at epoch start -- they were provisioned in a previous epoch.
    fleet.active = dict(plan.instances)
    fleet.pending = []

    servers = {
        m: ModelServer(key=m, params=service_params(pset.models[m]))
        for _c, m in pairs
        if m in pset.models
    }
    samplers = {c: _sampler_for(pset, c, rng) for c, _m in pairs}

    thresholds = {}
    for c, m in pairs:
        if m not in pset.models or m in thresholds:
            continue
        sampler = samplers.get(c)
        t_c = sampler.percentile(90) if sampler else 0.0
        thresholds[m] = thresholds_for(pset.models[m], tau_s, t_c)

    monitor = FleetMonitor(window_s=MONITOR_WINDOW_S)
    scaler = AutoScaler(thresholds=thresholds, spare_fraction=spare_fraction)
    dispatcher = Dispatcher(policy=policy_named(dispatch_policy, seed))

    outcomes: list[RequestOutcome] = []
    request_id = 0
    arrivals = 0
    max_queue_delay = 0.0
    pending: list[tuple[float, RequestOutcome, ModelProfileKey]] = []

    steps = int(duration_s / TICK_S)
    for step in range(steps):
        now = clock.advance()
        rate = arrivals_per_s[min(step, len(arrivals_per_s) - 1)]
        n_arrivals = _poisson(rate * TICK_S, rng)

        for _ in range(n_arrivals):
            request_id += 1
            arrivals += 1
            config, model = dispatcher.dispatch(routing, request_id)
            sampler = samplers.get(config)
            if sampler is None or model not in servers:
                outcomes.append(
                    RequestOutcome(
                        request=Request(request_id, now, plan.slo, plan.workflow_id),
                        outcome=Outcome.DROPPED,
                        reason="no token distribution or model server for the chosen pair",
                    )
                )
                continue
            tokens = sampler.draw()
            server = servers[model]
            active = fleet.active_count(model)
            queue_s = server.queue_delay_s(active)
            service_s = server.params.service_time_s(tokens)
            server.admit(tokens)
            monitor.record(model, now, tokens)
            max_queue_delay = max(max_queue_delay, 0.0 if queue_s == float("inf") else queue_s)
            outcome = RequestOutcome(
                request=Request(request_id, now, plan.slo, plan.workflow_id),
                outcome=Outcome.COMPLETED,
                config=config,
                model=model,
                tokens=tokens,
                queued_s=min(queue_s, 1e6),
                service_s=service_s,
                completed_s=now + min(queue_s, 1e6) + service_s,
                tau_s=tau_s,
            )
            outcomes.append(outcome)

        for model, server in servers.items():
            server.drain(fleet.active_count(model), TICK_S)
        fleet.tick(now, TICK_S)

        if abs(now % CONTROL_INTERVAL_S) < TICK_S / 2.0:
            scaler.control(now, monitor, fleet)

    violated = sum(1 for o in outcomes if o.outcome.served and not o.met_slo)
    completed = sum(1 for o in outcomes if o.outcome.served and o.met_slo)
    dropped = sum(1 for o in outcomes if o.outcome is Outcome.DROPPED)

    realized = {f"{c}|{m}": v for (c, m), v in dispatcher.realized_split().items()}
    planned = {f"{c}|{m}": v for (c, m), v in routing.items()}

    return (
        EpochOutcome(
            epoch=epoch,
            arrivals=arrivals,
            completed=completed,
            violated=violated,
            dropped=dropped,
            gpus_end=fleet.total_gpus(),
            wasted_gpu_seconds=fleet.wasted_gpu_seconds,
            scale_events=scaler.summary(),
            realized_split=realized,
            planned_split=planned,
            max_queue_delay_s=max_queue_delay,
            tau_s=tau_s,
        ),
        outcomes,
    )


def _poisson(mean: float, rng: random.Random) -> int:
    """Arrivals in one tick. Poisson is [OURS] -- Figure 19 gives rates, not an arrival process."""
    if mean <= 0:
        return 0
    if mean > 30:
        return max(0, int(rng.gauss(mean, mean**0.5)))
    import math

    limit = math.exp(-mean)
    k, p = 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1
        if k > 1000:
            return k


__all__ = ["EpochOutcome", "ExecutionRun", "FIDELITY_NOTES", "run_epoch"]
