"""
A.5's three interchangeable objectives -- eqs. (11), (12) and (13), p.587.

    (11)  min  sum_m n_m * e_m * g_m
    (12)  min  sum_m n_m * g_m * c_g(m)
    (13)  max  ( sum x^avg * a_c ) / ( sum lambda^avg )  -  epsilon * Cost_total

"Interchangeable" is a property the code has to preserve, not a description: the constraint
system must be IDENTICAL across all three, so that comparing their answers compares objectives
rather than models. `model.py` builds the constraints; this module only attaches a sense and an
expression. The one permitted variation is eq. (6), whose presence A.5 itself ties to a supplied
cost budget.

Each objective carries a defect that is reproduced, not repaired:

  * **(11) cannot distinguish two models on the same GPU type.** `e_m` comes from Table 3 per GPU
    TYPE (A41 -- Figure 3's "TPS per Wh" column is dimensionally undefined), so eq. (11)
    degenerates to "minimise GPU-seconds, weighted by GPU type". Two different models on H100 are
    indistinguishable to it.
  * **(12) prices provisioning while eq. (6) prices consumption** (A72). Minimising (12) and
    satisfying (6) are pulling on different quantities, and nothing connects them.
  * **(13) is the objective the quality filter cannot reach** (A66). It maximises over `x^avg`,
    and eqs. (4)/(5) constrain `x^peak` only, so it may place average load on configurations
    whose `a_c` is below `tau`. It is also the only objective that does not minimise `n_m`, which
    is why Section 4.3's bounding guard exists.
"""

from __future__ import annotations

from enum import Enum
from typing import Final

import pulp

from optimization.milp import A5
from optimization.milp.model import BuiltModel
from optimization.milp.units import EPOCH_SECONDS


class Objective(Enum):
    """A.5's three, by equation number."""

    ENERGY = 11
    COST = 12
    ACCURACY = 13

    @property
    def equation(self) -> str:
        return A5.DISTINCT_EQUATIONS[self.value]

    @property
    def minimises_n(self) -> bool:
        """Whether the objective pulls `n_m` DOWN.

        (11) and (12) do, so eq. (3) alone bounds them and no budget is needed for a finite
        optimum. (13) does not -- it is indifferent to fleet size except through the `epsilon`
        tie-breaker -- which is what makes the guard in `attach()` necessary.
        """
        return self in (Objective.ENERGY, Objective.COST)


class AccuracyWeighting(Enum):
    """Which allocation objective (13) weights.

    `AVG` is the paper (Q21(c), settled verbatim against pp.586-587). `PEAK` is **[OURS]** and
    exists only as a sensitivity variant: selecting it would tie the accuracy objective to the
    SLO-filtered variable and thereby REPAIR A66, so it must never be the default and every
    result computed with it is labelled.
    """

    AVG = "avg"
    PEAK = "peak"


class UnboundedObjective(Exception):
    """Section 4.3's guard tripped: nothing bounds `n_m` in the direction the objective pulls."""


def attach(
    built: BuiltModel,
    objective: Objective,
    weighting: AccuracyWeighting = AccuracyWeighting.AVG,
    lam_avg_total: float | None = None,
) -> BuiltModel:
    """Attach one objective to an already-built constraint system.

    Raises `UnboundedObjective` rather than returning a plausible-looking number when the model
    cannot bound the answer. That guard is **[OURS]** (Section 4.3) and is not a change to the
    formulation -- A.5 simply does not contemplate running (13) without a budget, and a solver
    handed an unbounded MIP may return a large finite value that looks like a result.
    """
    adm = built.admissible

    if objective is Objective.ENERGY:
        # eq. (11): min sum_m n_m * e_m * g_m. `e_m` is per GPU-second here (units.py), so the
        # sum is kWh/s; multiplying by the epoch gives kWh, matching Figure 18a's MWh axis.
        expr = pulp.lpSum(
            built.n[m] * float(adm.e_m[m].value) * adm.g_m[m] * EPOCH_SECONDS
            for m in adm.models
            if m in adm.e_m
        )
        built.problem.sense = pulp.LpMinimize
        built.problem += expr, "eq11_energy_kwh"

    elif objective is Objective.COST:
        # eq. (12): min sum_m n_m * g_m * c_g(m). Prices the PROVISIONED fleet -- idle or not.
        expr = pulp.lpSum(
            built.n[m] * adm.g_m[m] * float(adm.c_g[m.gpu].value) * EPOCH_SECONDS
            for m in adm.models
            if m.gpu in adm.c_g
        )
        built.problem.sense = pulp.LpMinimize
        built.problem += expr, "eq12_cost_usd"

    else:
        if not built.bounds_n_above():
            raise UnboundedObjective(
                "objective (13) does not minimise n_m, and neither eq. (6) nor eq. (7) is "
                "active, so the fleet is unbounded. Supply a cost budget (A67/Q23) or a "
                "resource budget (A43). Refusing to return a number that would look like a "
                "result."
            )
        variables = built.x_avg if weighting is AccuracyWeighting.AVG else built.x_peak
        if lam_avg_total is None or lam_avg_total <= 0:
            raise UnboundedObjective(
                "objective (13) divides by sum_{w,s} lambda^avg_{w,s}; it was not supplied"
            )
        accuracy_term = pulp.lpSum(
            variables[(c, m)] * adm.a_c[c]
            for (c, m) in variables
            if c in adm.a_c
        ) / lam_avg_total
        # `Cost_total` is never defined in A.5. Eq. (12)'s expression is the only candidate and
        # is what we use, labelled in every result rather than passed off as the paper's.
        cost_total = pulp.lpSum(
            built.n[m] * adm.g_m[m] * float(adm.c_g[m.gpu].value) * EPOCH_SECONDS
            for m in adm.models
            if m.gpu in adm.c_g
        )
        built.problem.sense = pulp.LpMaximize
        built.problem += accuracy_term - A5.EPSILON * cost_total, "eq13_accuracy_minus_cost"

    return built


#: Objectives that need `e_m`, and therefore exclude models lacking it (A71).
NEEDS_ENERGY: Final[frozenset[Objective]] = frozenset({Objective.ENERGY})


__all__ = [
    "AccuracyWeighting",
    "NEEDS_ENERGY",
    "Objective",
    "UnboundedObjective",
    "attach",
]
