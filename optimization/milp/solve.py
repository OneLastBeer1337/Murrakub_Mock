"""
Solving -- A.5 p.587: "solved using Gurobi [37] with a time limit of 300 seconds".

`CLAUDE.md` forbids Gurobi, so the backend is CBC via PuLP. The substitution is confined to this
module by design: PuLP lets A.5's equations be written in almost the appendix's own notation
(`model.py`), and the backend is a one-word argument, so "no Gurobi" cannot leak into the
formulation. HiGHS is available as an opt-in cross-check; `test_milp_backend.py` asserts the two
agree on objective value, so a backend difference surfaces as a test failure rather than as a
changed headline number.

CP-SAT was rejected: it is integer-only, and `x^peak`/`x^avg` are `R+` by A.5's own declaration.
Using it would discretise request rates -- a modelling change smuggled in as a backend change.

**Infeasibility is a RESULT here, not an exception.** Under `baseline`, latency-tier runs are
predicted to be infeasible (A37), and reaching that conclusion is the point of the run. Two paths
produce it, and keeping them apart is what makes the finding legible:

  * `INFEASIBLE_STRUCTURAL` -- the admissible set was empty before the solver ran. `sets.py`
    carries the arithmetic of the nearest miss, which IS the A37 result and is far more useful
    than a status code.
  * `INFEASIBLE_SOLVER` -- demand (1)/(2) could not be met inside an active budget (6)/(7). The
    expected failure mode of the Section 4.5 sweep at `a2000_h0`.

Forbidden, explicitly: loosening `tau`, swapping in `derived_tiers` and calling it the headline,
dropping `alpha`, substituting p50 tokens, or falling back to the nearest feasible tier.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Mapping, Protocol

import pulp

from optimization.milp.model import BuiltModel
from optimization.milp.objectives import Objective
from optimization.profiles.sources.tables import SOLVER_TIME_LIMIT_S


class MilpStatus(Enum):
    OPTIMAL = "optimal"
    INFEASIBLE_STRUCTURAL = "infeasible_structural"
    INFEASIBLE_SOLVER = "infeasible_solver"
    TIME_LIMIT = "time_limit"
    UNBOUNDED_GUARD = "unbounded_guard"

    @property
    def is_answer(self) -> bool:
        """Whether an objective value from this status may be quoted."""
        return self is MilpStatus.OPTIMAL


class Backend(Protocol):
    """Keeps CBC swappable so the Gurobi substitution stays auditable."""

    name: str

    def solver(self, time_limit_s: int): ...


class CbcBackend:
    name = "CBC"

    def solver(self, time_limit_s: int = SOLVER_TIME_LIMIT_S):
        return pulp.PULP_CBC_CMD(msg=0, timeLimit=time_limit_s)


class HighsBackend:
    name = "HiGHS"

    def solver(self, time_limit_s: int = SOLVER_TIME_LIMIT_S):
        return pulp.HiGHS_CMD(msg=False, timeLimit=time_limit_s)


DEFAULT_BACKEND: Backend = CbcBackend()


def available_backends() -> tuple[Backend, ...]:
    out: list[Backend] = []
    for backend in (CbcBackend(), HighsBackend()):
        try:
            if backend.solver().available():
                out.append(backend)
        except Exception:  # pragma: no cover - backend simply absent
            continue
    return tuple(out)


_PULP_STATUS = {
    pulp.LpStatusOptimal: MilpStatus.OPTIMAL,
    pulp.LpStatusInfeasible: MilpStatus.INFEASIBLE_SOLVER,
    pulp.LpStatusUnbounded: MilpStatus.UNBOUNDED_GUARD,
    pulp.LpStatusNotSolved: MilpStatus.TIME_LIMIT,
    pulp.LpStatusUndefined: MilpStatus.TIME_LIMIT,
}


class SolveOutcome:
    """What `solve_model` returns before `report.py` dresses it up."""

    def __init__(
        self,
        status: MilpStatus,
        objective_value: float | None,
        n: Mapping,
        x_peak: Mapping,
        x_avg: Mapping,
        wall_clock_s: float,
        backend: str,
        gap: float | None = None,
    ) -> None:
        self.status = status
        self.objective_value = objective_value
        self.n = n
        self.x_peak = x_peak
        self.x_avg = x_avg
        self.wall_clock_s = wall_clock_s
        self.backend = backend
        self.gap = gap


def solve_model(
    built: BuiltModel,
    backend: Backend | None = None,
    time_limit_s: int = SOLVER_TIME_LIMIT_S,
) -> SolveOutcome:
    """Solve an assembled model. Never raises on infeasibility -- it reports it.

    `time_limit_s` defaults to A.5's own 300 s, imported from `sources/tables.py` so the citation
    travels with the number rather than being retyped here.
    """
    backend = backend or DEFAULT_BACKEND

    if built.admissible.is_empty:
        # Nothing was ever built; do not hand an empty problem to a solver and interpret its
        # opinion. The structural reason is already computed and far more informative.
        return SolveOutcome(
            status=MilpStatus.INFEASIBLE_STRUCTURAL,
            objective_value=None,
            n={},
            x_peak={},
            x_avg={},
            wall_clock_s=0.0,
            backend=backend.name,
        )

    started = time.perf_counter()
    built.problem.solve(backend.solver(time_limit_s))
    elapsed = time.perf_counter() - started

    status = _PULP_STATUS.get(built.problem.status, MilpStatus.TIME_LIMIT)
    value = pulp.value(built.problem.objective) if status is MilpStatus.OPTIMAL else None

    return SolveOutcome(
        status=status,
        objective_value=value,
        n={m: int(round(v.value() or 0)) for m, v in built.n.items()},
        x_peak={k: float(v.value() or 0.0) for k, v in built.x_peak.items()},
        x_avg={k: float(v.value() or 0.0) for k, v in built.x_avg.items()},
        wall_clock_s=elapsed,
        backend=backend.name,
    )


def relaxation_probe(built: BuiltModel) -> float | None:
    """The `tau` at which an empty latency run would become feasible. **Computed, never applied.**

    Section 7.4's fourth check against our own bugs. A37 predicts the printed thresholds are
    unreachable by roughly 2-5x; if this probe says 400x, the fault is far more likely ours than
    the paper's. Returning the number lets that judgement be made on evidence.
    """
    adm = built.admissible
    if not adm.eq5_value:
        return None
    return min(adm.eq5_value.values())


__all__ = [
    "Backend",
    "CbcBackend",
    "DEFAULT_BACKEND",
    "HighsBackend",
    "MilpStatus",
    "SolveOutcome",
    "available_backends",
    "relaxation_probe",
    "solve_model",
]
