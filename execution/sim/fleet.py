"""
The simulated fleet -- instance counts over time, and the 20-minute wall (A87).

Table 1, Phase 3: "Reactive scale-out / scale-in -- Continuous -- Model". So instance counts are
per MODEL PROFILE, and they change continuously rather than only at epoch boundaries. That is
the one thing the auto-scaler actually controls.

THE STATE THAT MATTERS. An instance is not binary. Between the decision to scale out and the
moment capacity exists, there is a **pending** instance that costs GPU-seconds and serves nothing:

    planned   what the MILP said (n_m from the deployment plan)
    active    serving now
    pending   provisioned, not yet ready -- Section 4.7's 20 minutes

Most of the interesting behaviour in Section 3.4 lives in the gap between `active` and `planned`,
and almost all of the damage lives in `pending`. A simulator that modelled only `active` would
show an auto-scaler that always works.

`B_g` IS ENFORCED HERE, AND IT BITES (A89). Section 3.4 says the auto-scaler "prioritizes
avoiding SLO violations over short-term allocation optimality", but eq. (7) is a hard budget. When
the two conflict the budget wins, because that is what the formulation says -- and the resulting
violations are reported rather than avoided.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from execution.sim.clock import PROVISIONING_DELAY_S
from optimization.profiles.schema import ModelProfileKey


@dataclass
class PendingInstance:
    model: ModelProfileKey
    ready_at_s: float
    requested_at_s: float

    def gpu_seconds_wasted(self, now_s: float, gpus: int) -> float:
        """GPU-seconds burned while not yet serving. Real money, zero throughput."""
        return max(0.0, min(now_s, self.ready_at_s) - self.requested_at_s) * gpus


@dataclass
class SimulatedFleet:
    """Instance counts per model profile, with provisioning latency made explicit."""

    planned: dict[ModelProfileKey, int] = field(default_factory=dict)
    active: dict[ModelProfileKey, int] = field(default_factory=dict)
    pending: list[PendingInstance] = field(default_factory=list)
    gpus_of: Mapping[ModelProfileKey, int] = field(default_factory=dict)
    budget: Mapping[str, float] | None = None
    provisioning_delay_s: float = PROVISIONING_DELAY_S

    scale_out_events: int = 0
    scale_in_events: int = 0
    budget_blocked_events: int = 0
    wasted_gpu_seconds: float = 0.0

    # -- installation -----------------------------------------------------------------

    def install_plan(self, plan: Mapping[ModelProfileKey, int], now_s: float) -> None:
        """Apply a new deployment plan at an epoch boundary.

        A.5 has no inter-epoch coupling (A69) -- no warm start, no switching cost, no minimum
        instance lifetime -- so a plan may legally tear the whole fleet down and rebuild it.
        Scale-DOWN is applied instantly (releasing is free); scale-UP pays the 20-minute delay,
        because the paper's own Section 4.7 says provisioning does.
        """
        self.planned = dict(plan)
        for m, want in plan.items():
            have = self.active.get(m, 0) + self._pending_count(m)
            if want > have:
                self._provision(m, want - have, now_s)
            elif want < self.active.get(m, 0):
                self.active[m] = want
        for m in list(self.active):
            if m not in plan:
                self.active[m] = 0

    # -- the auto-scaler's levers ------------------------------------------------------

    def scale_out(self, model: ModelProfileKey, count: int, now_s: float) -> int:
        """Request `count` more instances. Returns how many were actually provisioned.

        Fewer than requested means eq. (7)'s budget refused them (A89).
        """
        allowed = self._budget_headroom(model)
        granted = max(0, min(count, allowed))
        if granted < count:
            self.budget_blocked_events += 1
        if granted:
            self._provision(model, granted, now_s)
            self.scale_out_events += 1
        return granted

    def scale_in(self, model: ModelProfileKey, count: int) -> int:
        released = max(0, min(count, self.active.get(model, 0)))
        if released:
            self.active[model] = self.active.get(model, 0) - released
            self.scale_in_events += 1
        return released

    # -- time ---------------------------------------------------------------------------

    def tick(self, now_s: float, dt_s: float) -> None:
        """Advance: promote pending instances that are ready, and bill the ones that are not."""
        still: list[PendingInstance] = []
        for p in self.pending:
            gpus = self.gpus_of.get(p.model, 1)
            self.wasted_gpu_seconds += min(dt_s, max(0.0, p.ready_at_s - (now_s - dt_s))) * gpus
            if now_s >= p.ready_at_s:
                self.active[p.model] = self.active.get(p.model, 0) + 1
            else:
                still.append(p)
        self.pending = still

    # -- views ---------------------------------------------------------------------------

    def active_count(self, model: ModelProfileKey) -> int:
        return self.active.get(model, 0)

    def total_gpus(self) -> int:
        return sum(n * self.gpus_of.get(m, 1) for m, n in self.active.items())

    def pending_gpus(self) -> int:
        return sum(self.gpus_of.get(p.model, 1) for p in self.pending)

    def gpus_by_type(self) -> Mapping[str, int]:
        out: dict[str, int] = {}
        for m, n in self.active.items():
            out[m.gpu] = out.get(m.gpu, 0) + n * self.gpus_of.get(m, 1)
        for p in self.pending:
            out[p.model.gpu] = out.get(p.model.gpu, 0) + self.gpus_of.get(p.model, 1)
        return out

    # -- internals -----------------------------------------------------------------------

    def _provision(self, model: ModelProfileKey, count: int, now_s: float) -> None:
        for _ in range(count):
            self.pending.append(
                PendingInstance(
                    model=model,
                    ready_at_s=now_s + self.provisioning_delay_s,
                    requested_at_s=now_s,
                )
            )

    def _pending_count(self, model: ModelProfileKey) -> int:
        return sum(1 for p in self.pending if p.model == model)

    def _budget_headroom(self, model: ModelProfileKey) -> int:
        """How many more instances of `model` eq. (7) permits. Unbounded when no budget is set.

        A43: Sections 4.2/4.3 state no budget, so eq. (7) is inactive for the headline runs and
        this returns "as many as you like". That is the paper's own answer, not a shortcut.
        """
        if self.budget is None or model.gpu not in self.budget:
            return 1_000_000
        used = self.gpus_by_type().get(model.gpu, 0)
        per_instance = self.gpus_of.get(model, 1)
        return max(0, int((self.budget[model.gpu] - used) // per_instance))


__all__ = ["PendingInstance", "SimulatedFleet"]
