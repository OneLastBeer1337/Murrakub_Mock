"""
Budget scenarios -- the two absences A.5 requires a caller to fill, and refuses to default.

A.5 has two budget parameters that the paper never instantiates:

  * **`B_g`** (eq. 7). Sections 4.2/4.3 state no resource budget at all, so eq. (7) is INACTIVE
    for the headline experiments (A43). Section 4.5's sweep (Table 3, p.578: 2,000 A100 with
    0-500 H100) is an experiment coordinate, not a profile fact. M3 supplies these through
    `profile_sets.budget_scenarios()`.
  * **`Cost_budget`** (eq. 6). Defined by A.5 as `sum_w tau_{w,cost} * sum_s lambda^avg_{w,s}` --
    so what is missing is `tau_{w,cost}`, a COST-type SLO threshold. Section 3.4 defines four
    tiers for quality and latency only, and no table in either version reports a cost tier (A67).

NEITHER IS DEFAULTED, AND THAT IS THE DESIGN. A default budget would be an invented number
sitting inside a constraint, which is exactly what Q19 forbids; a silently omitted eq. (7) would
let objective (13) provision an unbounded fleet and return a large finite number that looks like a
result. So `BudgetChoice` is a required argument with no default value, and one of its options is
explicitly named "no budget" -- the caller must assert the absence rather than fall into it.

**Q23 resolution.** `tau_{w,cost}` is expressed as a MULTIPLE of objective (12)'s optimum for the
same run, not as an absolute dollar figure. Absolute dollars are not comparable across profile
sets (`c_g` alone is swept +/-50%), whereas "1.25x the cheapest fleet that meets demand" means the
same thing in every set. The multiplier is **[OURS]** and appears in every result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Mapping

from optimization.profiles.profile_sets import budget_scenarios as _resource_scenarios
from optimization.profiles.provenance import Unavailable

NO_BUDGET: Final[str] = "no_budget"
"""Section 4.2/4.3's headline case: eq. (7) omitted because the paper states no budget (A43).

Named, so that choosing it is a decision a reader can see, rather than the consequence of
leaving an argument out.
"""


@dataclass(frozen=True)
class BudgetChoice:
    """What bounds this run, stated explicitly.

    `resource` is `B_g` in GPUs per type, or `None` for "eq. (7) omitted".
    `cost_multiplier` is `[OURS]`: the cost budget as a multiple of objective (12)'s optimum for
    the same run, or `None` for "eq. (6) omitted".
    """

    name: str
    resource: Mapping[str, float] | None = None
    cost_multiplier: float | None = None
    provenance: str = ""

    @property
    def eq7_active(self) -> bool:
        return self.resource is not None

    @property
    def eq6_active(self) -> bool:
        return self.cost_multiplier is not None

    def describe(self) -> str:
        bits = []
        bits.append(
            f"eq7: B_g={dict(self.resource)}" if self.eq7_active else "eq7: omitted (A43)"
        )
        bits.append(
            f"eq6: Cost_budget = {self.cost_multiplier:g} x O2 optimum [OURS]"
            if self.eq6_active
            else "eq6: omitted (A67)"
        )
        return "; ".join(bits)


def no_budget() -> BudgetChoice:
    """The headline case. Eq. (6) and eq. (7) both omitted, deliberately."""
    return BudgetChoice(
        name=NO_BUDGET,
        provenance="Sections 4.2/4.3 state no resource budget and no cost tier (A43, A67)",
    )


def table_3(row: str) -> BudgetChoice:
    """One of Section 4.5's six sweep settings, from Table 3 (p.578).

    Row names are M3's: `a2000_h0` .. `a2000_h500`.
    """
    scenarios = _resource_scenarios()
    if row not in scenarios or row == NO_BUDGET:
        available = sorted(k for k in scenarios if k != NO_BUDGET)
        raise KeyError(f"{row!r} is not a Table 3 row; available: {available}")
    values = scenarios[row]
    return BudgetChoice(
        name=f"table_3[{row}]",
        resource={
            g: float(v.value) for g, v in values.items() if not isinstance(v, Unavailable)
        },
        provenance="Table 3 (p.578), Section 4.5 resource sweep; PAPER_TABLE",
    )


def cost_budget(multiplier: float, resource: Mapping[str, float] | None = None) -> BudgetChoice:
    """A cost budget expressed as a multiple of objective (12)'s optimum. **[OURS]**, Q23.

    Objective (13) needs this or a resource budget: it is the only objective that does not
    minimise `n_m`, so without one of the two the fleet is unbounded and `objectives.attach()`
    refuses to build it.
    """
    if multiplier <= 0:
        raise ValueError("a cost budget multiplier must be positive")
    return BudgetChoice(
        name=f"cost_x{multiplier:g}",
        resource=dict(resource) if resource else None,
        cost_multiplier=float(multiplier),
        provenance=(
            "[OURS] tau_{w,cost} is unreported (A67); expressed as a multiple of eq. (12)'s "
            "optimum so runs stay comparable across profile sets"
        ),
    )


#: The Q23 sweep. 1.0 is the tightest interesting budget -- exactly the cheapest feasible fleet.
DEFAULT_COST_MULTIPLIERS: Final[tuple[float, ...]] = (1.0, 1.25, 1.5, 2.0)

#: Table 3's six rows, in sweep order.
TABLE_3_ROWS: Final[tuple[str, ...]] = tuple(
    k for k in _resource_scenarios() if k != NO_BUDGET
)


def resource_sweep() -> tuple[BudgetChoice, ...]:
    """Section 4.5's sweep as a sequence of runs."""
    return tuple(table_3(row) for row in TABLE_3_ROWS)


__all__ = [
    "BudgetChoice",
    "DEFAULT_COST_MULTIPLIERS",
    "NO_BUDGET",
    "TABLE_3_ROWS",
    "cost_budget",
    "no_budget",
    "resource_sweep",
    "table_3",
]
