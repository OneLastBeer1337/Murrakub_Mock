"""
Request shapes at the Murakkab boundary -- paper Section 3.4, p.574.

    "At runtime, Murakkab receives incoming requests from end-users with a payload that contains
    the identifier of the agentic workflow being invoked, any input query/data, and the SLOs.
    Murakkab looks up the registry to obtain the corresponding executable workflow and submits
    it for execution."

    "End-users can either invoke a particular agentic workflow or send a request with a natural
    language query ... without specifying an agentic workflow to use."

So there are exactly TWO request shapes, and the difference is whether the workflow is named.
M6 accepts both and does not re-implement the orchestrator: the dynamic shape is handed to M1's
`WorkflowOrchestrator`, which already turns a specification into a `LogicalWorkflow` through the
abstract LLM client.

A82 -- THE SLO KEY IS NOT A PRODUCT. Section 3.4 says a request "has the option to specify a
quality, latency and cost SLOs", which reads as though a request could demand all three at once.
But the optimizer solves per `(workflow, SLO)` pair with ONE `tau_{w,s}` (A68), and every run in
Sections 4.2/4.3 assigns a request exactly one SLO type. There is no MILP solution for a
conjoined key, so serving one would mean inventing a deployment plan nobody solved. Conjunctions
are REJECTED with an error naming A82 rather than silently resolved. Section 4.3's own way of
expressing a mixed population is a 70/30 split ACROSS requests, which `SloMix` already models.

Cost SLOs are rejected outright: `tau_{w,cost}` is undefined in the paper (A67).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from optimization.profiles.schema import SLO_TIERS

VALID_SLO_TYPES: tuple[str, ...] = ("accuracy", "latency")
"""Section 3.4 defines four tiers "for quality and end-to-end latency". Cost is named in the
prose but has no tier ladder and no reported threshold (A67)."""


class SloKeyError(ValueError):
    """A request's SLO cannot be served by any plan the optimizer actually solves."""


@dataclass(frozen=True)
class SloSpec:
    """Exactly one SLO type and tier -- the granularity the optimizer solves at."""

    slo_type: str
    tier: str

    def __post_init__(self) -> None:
        if self.slo_type == "cost":
            raise SloKeyError(
                "cost SLOs are not servable: A.5's Cost_budget depends on tau_{w,cost}, a "
                "cost-type tier Section 3.4 never defines and no table reports (A67)"
            )
        if self.slo_type not in VALID_SLO_TYPES:
            raise SloKeyError(
                f"{self.slo_type!r}: Section 3.4 defines tiers for quality and latency only; "
                f"expected one of {VALID_SLO_TYPES}"
            )
        if self.tier not in SLO_TIERS:
            raise SloKeyError(f"{self.tier!r}: expected one of {SLO_TIERS}")

    @property
    def key(self) -> tuple[str, str]:
        return (self.slo_type, self.tier)

    def __str__(self) -> str:
        return f"{self.slo_type}-{self.tier}"


def parse_slo(spec: Any) -> SloSpec:
    """Accept a request's SLO field, rejecting conjunctions loudly (A82).

    The rejection is the point. Section 3.4's phrasing invites a request that demands both a
    quality and a latency tier; the optimizer has never solved such a thing, so the honest
    response is an error naming the gap -- not a guess about which tier wins.
    """
    if isinstance(spec, SloSpec):
        return spec
    if isinstance(spec, tuple) and len(spec) == 2 and all(isinstance(v, str) for v in spec):
        return SloSpec(*spec)
    if isinstance(spec, Mapping):
        types = [t for t in spec if t in ("accuracy", "latency", "quality", "cost")]
        if len(types) > 1:
            raise SloKeyError(
                f"A82: request names {len(types)} SLO types {sorted(types)}, but the optimizer "
                "solves per (workflow, SLO) pair with ONE tau_{w,s} (A68) and every run in "
                "Sections 4.2/4.3 assigns a request exactly one SLO type. No deployment plan "
                "exists for a conjoined key. Use a POPULATION split across requests instead "
                "(Section 4.3's 70/30), which SloMix models."
            )
        if len(types) == 1:
            t = types[0]
            return SloSpec("accuracy" if t == "quality" else t, spec[t])
    raise SloKeyError(f"{spec!r}: cannot be read as a single (slo_type, tier)")


class Outcome(Enum):
    """How a request ended. `SLO_VIOLATED` is a completion, not a failure (Section 9)."""

    COMPLETED = "completed"
    SLO_VIOLATED = "slo_violated"
    DROPPED = "dropped"
    REJECTED = "rejected"

    @property
    def served(self) -> bool:
        return self in (Outcome.COMPLETED, Outcome.SLO_VIOLATED)


@dataclass(frozen=True)
class Request:
    """One arrival. `workflow_id=None` is the dynamic shape."""

    request_id: int
    arrival_s: float
    slo: SloSpec
    workflow_id: str | None = None
    query: str = ""
    payload: Mapping[str, Any] = field(default_factory=dict)

    @property
    def is_dynamic(self) -> bool:
        """Section 3.4's second shape: a natural-language query with no workflow named."""
        return self.workflow_id is None


@dataclass(frozen=True)
class RequestOutcome:
    """What happened to one request, with enough detail to attribute a violation.

    `tokens` is drawn per request from the profile's token DISTRIBUTION, not from `t_c`'s p90.
    That variance is the auto-scaler's entire reason to exist (Section 3.4 motivates it with
    Llava-OneVision-7B's 600 vs 1200 token spread), so collapsing it here would delete the
    phenomenon under study.
    """

    request: Request
    outcome: Outcome
    config: Any = None
    model: Any = None
    tokens: float = 0.0
    queued_s: float = 0.0
    service_s: float = 0.0
    completed_s: float = 0.0
    tau_s: float | None = None
    reason: str = ""

    @property
    def latency_s(self) -> float:
        return self.queued_s + self.service_s

    @property
    def met_slo(self) -> bool:
        if self.tau_s is None:
            return self.outcome is Outcome.COMPLETED
        return self.outcome.served and self.latency_s <= self.tau_s


__all__ = [
    "Outcome",
    "Request",
    "RequestOutcome",
    "SloKeyError",
    "SloSpec",
    "VALID_SLO_TYPES",
    "parse_slo",
]
