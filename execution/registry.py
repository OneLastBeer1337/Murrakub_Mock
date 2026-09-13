"""
The Workflow Registry -- paper Section 3.3.1 (p.574) and Section 3.4 (p.574).

    "The deployment plan does not prescribe per-request dispatch, which remains a runtime
    responsibility (Section 3.4). Once an executable workflow is generated for all valid SLO
    tiers of an onboarded workflow, it is added to the Murakkab workflow registry and is ready
    to serve requests."

The registry is the handoff between Phase 2 and Phase 3. The optimizer runs hourly and writes a
deployment plan; a request arriving at 10:17 must be served without re-running a MILP. The
registry is simply where the plan is written down.

TWO THINGS THE PAPER'S SENTENCE FIXES, both load-bearing:

**One entry per (workflow, SLO TIER), not per workflow.** Onboarding Video Q/A does not create
one registry entry, it creates one per valid tier. That is why `ExecutableWorkflow` is keyed by
`(workflow_id, slo_type, tier)`.

**"for all VALID SLO tiers".** A tier the optimizer could not solve has no entry. Under
`baseline`, Video Q/A's latency tiers are structurally infeasible (A37), so the registry is
genuinely missing those keys and a request for them is REJECTED. The alternative -- quietly
serving the nearest feasible tier -- would hide the A37 finding at exactly the moment it becomes
user-visible, and M4's design forbids it in the same words.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from execution.requests import SloKeyError, SloSpec
from optimization.milp.report import MilpResult
from optimization.milp.solve import MilpStatus
from optimization.profiles.schema import ConfigKey, ModelProfileKey

RegistryKey = tuple[str, str, str]
"""`(workflow_id, slo_type, tier)`."""


class TierNotServable(SloKeyError):
    """No plan exists for this tier. Under `baseline` this is A37 becoming user-visible."""


@dataclass(frozen=True)
class ExecutableWorkflow:
    """One deployment plan, as the registry holds it.

    Carries the ROUTING FRACTIONS, not a single choice. A.5 declares `x` continuous, so the plan
    may spread one request stream across several `(c, m)` pairs (A70). Turning those fractions
    into a per-request choice is `dispatch.py`'s job, and the paper assigns it to the runtime.

    `caveats` is mandatory and non-empty. Q19 requires the data-excluded set beside every
    headline number, and a registry entry is where a number stops being a research artifact and
    starts serving users -- so the provenance has to travel with it rather than being looked up.
    """

    workflow_id: str
    slo: SloSpec
    routing: Mapping[tuple[ConfigKey, ModelProfileKey], float]
    instances: Mapping[ModelProfileKey, int]
    tau_s: float | None
    profile_set_name: str
    epoch: int
    objective: str
    caveats: tuple[str, ...]
    data_excluded: tuple[str, ...] = ()
    support_size: int = 0

    def __post_init__(self) -> None:
        if not self.caveats:
            raise ValueError(
                "an ExecutableWorkflow without its provenance block cannot be registered "
                "(Q19: the data-excluded set is mandatory beside every number)"
            )
        if not self.routing:
            raise ValueError(
                f"{self.workflow_id}/{self.slo}: a plan with no routing serves nothing"
            )

    @property
    def key(self) -> RegistryKey:
        return (self.workflow_id, self.slo.slo_type, self.slo.tier)

    @property
    def total_gpus(self) -> int:
        return sum(self.instances.values())

    def normalised_routing(self) -> Mapping[tuple[ConfigKey, ModelProfileKey], float]:
        """Routing as fractions summing to 1.

        The MILP's `x` is an absolute rate in req/s, and eq. (1) allows the total to exceed
        `lambda^peak` by up to `alpha` -- so the raw values do NOT sum to 1. Normalising here is
        `[OURS]`, and it is the only reading under which "the fraction of load routed to each
        instance" (Section 3.3.1, Decision 4) is well defined.
        """
        total = sum(self.routing.values())
        if total <= 0:
            return {}
        return {k: v / total for k, v in self.routing.items()}


def build_executable(result: MilpResult) -> ExecutableWorkflow:
    """Turn one solved `MilpResult` into a registry entry.

    Refuses anything that is not `OPTIMAL`. An infeasible or time-limited solve is a RESULT worth
    reporting (M4 Section 7.3), but it is not a plan, and registering one would mean serving
    requests against an answer the solver never vouched for.
    """
    if result.status is not MilpStatus.OPTIMAL:
        raise TierNotServable(
            f"{result.workflow}/{result.slo[0]}-{result.slo[1]}: status "
            f"{result.status.value} -- no plan exists for this tier. Under `baseline` the "
            "latency tiers are structurally infeasible (A37); serving the nearest feasible "
            "tier instead would hide that finding."
        )
    routing = {k: v for k, v in result.x_peak.items() if v > 1e-9}
    return ExecutableWorkflow(
        workflow_id=result.workflow,
        slo=SloSpec(*result.slo),
        routing=routing,
        instances={m: n for m, n in result.n.items() if n > 0},
        tau_s=None,
        profile_set_name=result.profile_set_name,
        epoch=result.epoch,
        objective=f"eq.({result.objective.value})",
        caveats=result.caveats(),
        data_excluded=result.data_excluded,
        support_size=result.support_size,
    )


@dataclass
class WorkflowRegistry:
    """What Phase 3 looks up. Deliberately dumb: it stores plans and reports absences."""

    entries: dict[RegistryKey, ExecutableWorkflow] = field(default_factory=dict)
    rejected: dict[RegistryKey, str] = field(default_factory=dict)
    """Tiers the optimizer could not solve, with the reason. Kept so the registry can say WHY a
    tier is missing rather than merely that it is (A37 becoming user-visible)."""

    def install(self, workflow: ExecutableWorkflow) -> None:
        self.entries[workflow.key] = workflow

    def record_unservable(self, workflow_id: str, slo: SloSpec, reason: str) -> None:
        self.rejected[(workflow_id, slo.slo_type, slo.tier)] = reason

    def lookup(self, workflow_id: str, slo: SloSpec) -> ExecutableWorkflow:
        key = (workflow_id, slo.slo_type, slo.tier)
        if key in self.entries:
            return self.entries[key]
        if key in self.rejected:
            raise TierNotServable(
                f"{workflow_id}/{slo}: no plan. {self.rejected[key]}"
            )
        raise TierNotServable(f"{workflow_id}/{slo}: not onboarded")

    def tiers_for(self, workflow_id: str) -> tuple[RegistryKey, ...]:
        return tuple(sorted(k for k in self.entries if k[0] == workflow_id))

    def coverage(self, workflow_id: str) -> Mapping[str, int]:
        served = len(self.tiers_for(workflow_id))
        missing = sum(1 for k in self.rejected if k[0] == workflow_id)
        return {"servable_tiers": served, "unservable_tiers": missing}

    def install_all(self, results: Sequence[MilpResult]) -> "WorkflowRegistry":
        """Populate from a batch of solves, recording the failures instead of dropping them."""
        for result in results:
            try:
                self.install(build_executable(result))
            except TierNotServable as exc:
                self.record_unservable(
                    result.workflow, SloSpec(*result.slo), str(exc).split(": ", 1)[-1]
                )
        return self


__all__ = [
    "ExecutableWorkflow",
    "RegistryKey",
    "TierNotServable",
    "WorkflowRegistry",
    "build_executable",
]
