"""
The Auto-Scaler -- Section 3.4, p.575, and the milestone's central finding.

    "To handle such variability, Murakkab includes an auto-scaler that monitors per-model
    instance load over short windows (seconds to minutes) and rapidly scales out when needed."

    "We set thresholds for auto-scaling based on the performance-throughput characteristic in
    executor profiles. This mechanism prioritizes avoiding SLO violations over short-term
    allocation optimality. Murakkab also maintains spare resources to absorb demand spikes and,
    when it detects significant deviations in workload or resource usage, triggers early
    re-optimization to adapt quickly."

Four mechanisms in one paragraph. Exactly one of them is specified (thresholds from the profile
curve, `thresholds.py`). The other three are named and never quantified:

  * **"rapidly scales out"** -- A87. Section 4.7 assumes provisioning takes **20 minutes**. A
    20-minute cold start cannot answer a 60-second window. This module implements the control
    loop the paper describes and the delay the paper assumes, and lets the contradiction produce
    whatever it produces. That is the finding, and turning the delay off (Q40) would erase it.
  * **"maintains spare resources"** -- A88. No size, no parameter. A.5 has nowhere to put one:
    `B_g` is a hard budget and `alpha` is a demand buffer, neither of which is spare capacity.
    Defaults to **zero** (Q36), because zero is the formulation's own answer and because any
    non-zero value would be us quietly repairing A87.
  * **"triggers early re-optimization"** -- A92. No threshold, no metric, no window. Defaults to
    **off** (Q37), so the paper's stated 60-minute cadence is what runs unless an experiment
    names otherwise. Note the trap: early re-optimization *costs* a 20-minute transition, so a
    sensitive trigger makes things worse -- Section 4.7's Zone 1 arriving through another door.

A89 -- "PRIORITIZES AVOIDING SLO VIOLATIONS" IS NOT ALWAYS POSSIBLE. Under an active eq. (7)
budget the auto-scaler can want instances it may not have. The budget wins, because that is what
the formulation says, and the violations are counted rather than avoided.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from execution.monitor import FleetMonitor
from execution.sim.fleet import SimulatedFleet
from execution.thresholds import HYSTERESIS_WINDOWS, ScaleThresholds
from optimization.profiles.schema import ModelProfileKey

SPARE_FRACTION: float = 0.0
"""A88 / Q36. Section 3.4 says spare resources are maintained; it never says how many.

Zero is not a cop-out, it is the formulation's own answer: A.5 has no spare-capacity parameter,
so a reproduction that invented one would be repairing A87's contradiction rather than exhibiting
it. Swept as a sensitivity coordinate; any non-zero value is stamped [INVENTED].
"""


@dataclass
class ScaleEvent:
    at_s: float
    model: ModelProfileKey
    direction: str
    requested: int
    granted: int
    observed_tokens_s: float
    threshold_tokens_s: float
    note: str = ""


@dataclass
class AutoScaler:
    """The control loop. Runs every `control_interval_s`, acts on a 60 s windowed token rate."""

    thresholds: Mapping[ModelProfileKey, ScaleThresholds]
    spare_fraction: float = SPARE_FRACTION
    hysteresis_windows: int = HYSTERESIS_WINDOWS
    events: list[ScaleEvent] = field(default_factory=list)
    _streak: dict[ModelProfileKey, tuple[str, int]] = field(default_factory=dict)

    def control(
        self,
        now_s: float,
        monitor: FleetMonitor,
        fleet: SimulatedFleet,
    ) -> None:
        """One control instant. Decides per model, applies hysteresis, respects the budget."""
        for model, threshold in self.thresholds.items():
            observed = monitor.tokens_per_second(model, now_s)
            decision = threshold.decide(observed)
            decision = self._with_hysteresis(model, decision)
            if decision == "hold":
                continue
            if decision == "out":
                want = self._instances_needed(observed, threshold, fleet, model)
                if want <= 0:
                    continue
                granted = fleet.scale_out(model, want, now_s)
                self.events.append(
                    ScaleEvent(
                        at_s=now_s,
                        model=model,
                        direction="out",
                        requested=want,
                        granted=granted,
                        observed_tokens_s=observed,
                        threshold_tokens_s=threshold.scale_out_at,
                        note=(
                            "A89: eq. (7) budget refused part of this request"
                            if granted < want
                            else ""
                        )
                        + (
                            "  [A86 fallback threshold]" if threshold.is_fallback else ""
                        ),
                    )
                )
            else:
                floor = self._floor(model, fleet)
                have = fleet.active_count(model)
                released = fleet.scale_in(model, max(0, have - max(floor, 1)))
                if released:
                    self.events.append(
                        ScaleEvent(
                            at_s=now_s,
                            model=model,
                            direction="in",
                            requested=released,
                            granted=released,
                            observed_tokens_s=observed,
                            threshold_tokens_s=threshold.scale_in_at,
                        )
                    )

    # -- internals ------------------------------------------------------------------------

    def _with_hysteresis(self, model: ModelProfileKey, decision: str) -> str:
        """Require `k` consecutive agreeing windows before acting.

        Without this a load oscillating around the threshold produces an instance churn storm --
        and with a 20-minute provisioning delay, each spurious scale-out burns 20 minutes of
        GPU-seconds for nothing (A87 compounding A69).
        """
        prev, count = self._streak.get(model, ("hold", 0))
        count = count + 1 if decision == prev else 1
        self._streak[model] = (decision, count)
        if decision == "hold":
            return "hold"
        return decision if count >= self.hysteresis_windows else "hold"

    def _instances_needed(
        self,
        observed_tokens_s: float,
        threshold: ScaleThresholds,
        fleet: SimulatedFleet,
        model: ModelProfileKey,
    ) -> int:
        """How many instances would bring the observed rate back under the scale-out threshold.

        Counts PENDING instances as already on the way -- otherwise the loop re-requests the same
        capacity every 10 s for the whole 20-minute provisioning delay, provisioning ~120x what
        is needed. That guard is [OURS]; the paper describes no such bookkeeping, and without it
        the simulation's failure mode would be our bug rather than A87.
        """
        if threshold.theta_slo_tokens_s <= 0:
            return 0
        target = threshold.scale_out_at
        if target <= 0:
            return 0
        need = observed_tokens_s / target
        need *= 1.0 + self.spare_fraction
        have = fleet.active_count(model) + sum(1 for p in fleet.pending if p.model == model)
        import math

        return max(0, math.ceil(need) - have)

    def _floor(self, model: ModelProfileKey, fleet: SimulatedFleet) -> int:
        """Never scale below the optimizer's plan.

        The plan was sized for projected PEAK demand (Section 3.3.1); a momentary lull is exactly
        the "short-term allocation optimality" Section 3.4 says to sacrifice.
        """
        return fleet.planned.get(model, 0)

    # -- reporting ------------------------------------------------------------------------

    def summary(self) -> Mapping[str, float]:
        out = [e for e in self.events if e.direction == "out"]
        return {
            "scale_out_events": float(len(out)),
            "scale_in_events": float(len(self.events) - len(out)),
            "instances_requested": float(sum(e.requested for e in out)),
            "instances_granted": float(sum(e.granted for e in out)),
            "budget_refusals": float(sum(1 for e in out if e.granted < e.requested)),
            "fallback_threshold_events": float(
                sum(1 for e in self.events if "A86" in e.note)
            ),
        }


__all__ = ["AutoScaler", "SPARE_FRACTION", "ScaleEvent"]
