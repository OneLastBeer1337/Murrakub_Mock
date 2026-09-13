"""
Data model — Task, ProfileSpec, AllocationResult, Infeasible, AdmitCost, Observation.

Spec: docs/design/System_Architecture_v2.md §5.1.
Build step 1. Verified by: types instantiate; no logic to test.
Owner: 083

O1 IS RESOLVED HERE AS "NO". The objective is provisioning cost only:

    minimize  Σ_m n[m] · price(m)

There is no per-invocation `Σ x[t][m]·varcost(t,m)` term, and ProfileSpec carries no
varcost field. This follows CLAUDE.md's stated default, but it is a default, not a team
decision — if the team adopts usage-based pricing, this file and every objective
downstream change together. See CLAUDE.md "Open questions", O1.

Two conventions worth stating, because §4.1 and §6.3 phrase them differently:

  * A track returns AllocationResult with feasible=False rather than raising or returning
    a bare Infeasible, so the harness records failures as data (CLAUDE.md conventions).
    The Infeasible detail rides along on `.infeasible` so the reason, blocking task and
    violated constraint are not lost. Use AllocationResult.failure() to build one.
  * Field names are snake_case, matching the module contracts in §6.3
    (cost_to_admit, build_provisioning), not the camelCase of the §5.1 sketch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, order=True)
class TaskId:
    """Tasks are identified per workflow — two workflows may share a task name."""

    workflow_id: str
    task_name: str

    def __str__(self) -> str:
        return f"{self.workflow_id}/{self.task_name}"


@dataclass(frozen=True)
class Task:
    id: TaskId
    task_type: str
    load: float
    rel_floor: float
    lat_ceil: float
    successors: tuple[TaskId, ...] = ()
    # successors are execution ordering only. Precedence does not enter the
    # optimisation — v2 §1.9, and settled in CLAUDE.md.


@dataclass(frozen=True)
class ProfileSpec:
    """The unit that gets provisioned: a (model, hardware tier, config) triple."""

    id: str
    declared_type: str
    throughput: float       # thr(m)
    gpus: int               # gpu(m)
    price: float            # price(m)
    reliability: float      # rel(m)
    latency: float          # lat(m) — task-independent in the current model
    observations: int = 0   # backing the EMA; 0 means unprofiled


@dataclass(frozen=True)
class Instance:
    profile_id: str
    count: int              # n[m]


@dataclass(frozen=True)
class AdmitCost:
    """What routing one task to one profile costs against the current state.

    Spec: v2 §4.4. extra_instances == 0 when existing headroom already covers the task —
    that state-dependence is the aggregate-coupling problem.
    """

    extra_instances: int
    extra_gpus: int
    extra_cost: float


@dataclass(frozen=True)
class Infeasible:
    reason: str
    blocking_task: TaskId | None = None
    constraint: str | None = None       # "C1" | "C2" | "C3"


@dataclass
class AllocationResult:
    routing: dict[TaskId, str]          # x
    provisioning: dict[str, int]        # n
    total_cost: float
    gpus_used: int
    strategy: str                       # "A" | "B" | "C" | "MILP" | "STATIC"
    lower_bound: float | None = None    # Tracks B, C
    iterations: int | None = None       # Track B
    restarts: int | None = None         # Track A
    converged: bool | None = None       # Track B
    compute_time: float = 0.0
    feasible: bool = True
    infeasible: Infeasible | None = None

    @classmethod
    def failure(cls, strategy: str, detail: Infeasible,
                compute_time: float = 0.0,
                lower_bound: float | None = None) -> AllocationResult:
        """A complete-or-nothing failure. Partial assignments are never valid output (P9).

        `lower_bound` is OPTIONAL AND SEPARATE FROM FEASIBILITY, which is not obvious and was
        originally missed. A dual bound is valid whenever its relaxation solved, regardless of
        whether the track's primal repair then found an allocation. Discarding it conflates
        two different questions — "how tight is this relaxation" (T1) and "can this track
        return an answer" (T4) — and the conflation only becomes visible on instances where
        repair fails often, which is exactly where T1 most needs measuring (F34).

        Pass it wherever a relaxation solved. Leave it None where none was computed, such as
        an empty candidate pool, so that None keeps meaning "no bound exists" rather than
        "no bound survived".
        """
        return cls(routing={}, provisioning={}, total_cost=0.0, gpus_used=0,
                   strategy=strategy, compute_time=compute_time,
                   feasible=False, infeasible=detail, lower_bound=lower_bound)


@dataclass(frozen=True)
class Observation:
    task_id: TaskId
    profile_id: str
    latency: float
    success: bool
    cost: float
    timestamp: datetime
    # Phase C is out of PoC scope (v2 §6.5). Defined so the data model is complete;
    # nothing in the PoC emits one.
