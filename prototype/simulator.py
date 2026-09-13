"""
J5/J6 — a simulated executor that emits Observations.

Outside PoC scope — see prototype/README.md. Owner: 077.

THIS IS A SIMULATION AND IT CANNOT VALIDATE ANY CLAIM ABOUT REAL EXECUTORS.

§4.6's Execution Engine is not built and is not buildable here: nothing can be executed
without real executors, and a mock of one would only test the mock. What this file does
instead is narrower and honest — it lets the **loop logic** be tested:

    does the Profile Store converge to the truth?
    does the Drift Detector fire when reality changes, and stay quiet when it does not?
    does the system thrash?

Every one of those is a question about the *system*, not about any executor. A simulator
answers them; real execution is not required and would not answer them better.

HOW IT WORKS

Each profile has **hidden true** reliability and latency, deliberately different from the
values the registry declares. Execution samples from the hidden truth. The Profile Store
only ever sees samples, exactly as it would in production.

That gap between declared and true is the point. Principle P6 says profiles are measured,
not declared — so a system that works only when the declared values are already correct has
not demonstrated anything. Here the declared values are wrong on purpose.

`degrade()` moves the hidden truth mid-run, which is the regime change the Drift Detector
exists to catch. Nothing else is told that it happened.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np

from poc.formulation.types import Observation, TaskId


@dataclass
class TrueBehaviour:
    """What a profile actually does, as opposed to what the registry claims."""

    reliability: float
    latency_mean: float
    latency_sd: float = 5.0


class SimulatedExecutor:
    """Runs an allocation and emits one Observation per task.

    Deterministic given a seed (P10), so a loop run is reproducible end to end.
    """

    def __init__(self, truth: dict[str, TrueBehaviour], seed: int = 0):
        self._truth = dict(truth)
        self._rng = np.random.default_rng(seed)
        self._clock = datetime(2026, 9, 3, 12, 0, 0)
        self._round = 0
        self._schedule: list[tuple[int, str, float | None, float | None]] = []

    def truth_for(self, profile_id: str) -> TrueBehaviour:
        return self._truth[profile_id]

    def degrade(self, profile_id: str, reliability: float | None = None,
                latency_mean: float | None = None) -> None:
        """Move the hidden truth. The regime change the Drift Detector must catch.

        Nothing outside this object is informed. The only way the rest of the system can
        learn about it is by observing executions — which is the whole point.
        """
        current = self._truth[profile_id]
        self._truth[profile_id] = TrueBehaviour(
            reliability=current.reliability if reliability is None else reliability,
            latency_mean=current.latency_mean if latency_mean is None else latency_mean,
            latency_sd=current.latency_sd)

    def schedule_degradation(self, at_round: int, profile_id: str,
                             reliability: float | None = None,
                             latency_mean: float | None = None) -> None:
        """Move the hidden truth at a given round.

        Scheduling rather than calling degrade() directly is what makes a fair comparison
        possible: two conditions given the same seed and the same schedule experience an
        identical world, so any difference between them is the system, not the weather.
        """
        self._schedule.append((at_round, profile_id, reliability, latency_mean))

    def execute(self, routing: dict[TaskId, str]) -> list[Observation]:
        """One round: run every task on its assigned profile, emit an Observation each.

        Tasks are executed in a deterministic order so a seeded run reproduces exactly.
        Precedence is not simulated — DAG edges determine ordering at execution time but
        nothing here depends on it (§1.9).
        """
        for at_round, profile_id, reliability, latency in self._schedule:
            if at_round == self._round:
                self.degrade(profile_id, reliability, latency)
        self._round += 1

        observations = []
        for task_id in sorted(routing, key=lambda t: (t.workflow_id, t.task_name)):
            profile_id = routing[task_id]
            truth = self._truth[profile_id]

            success = bool(self._rng.random() < truth.reliability)
            latency = float(max(0.1, self._rng.normal(truth.latency_mean, truth.latency_sd)))
            self._clock += timedelta(milliseconds=latency)

            observations.append(Observation(
                task_id=task_id,
                profile_id=profile_id,
                latency=latency,
                success=success,
                cost=0.0,          # provisioning cost is not per-call (O1 closed as "no")
                timestamp=self._clock,
            ))
        return observations
