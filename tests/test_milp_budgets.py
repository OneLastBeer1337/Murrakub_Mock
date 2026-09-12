"""
Budgets -- eqs. (6) and (7), the two constraints A.5 needs and never instantiates.

Both are absent from the paper for different reasons, and both are dangerous in different ways:

  * **`B_g`** (eq. 7). Sections 4.2/4.3 state no budget (A43), and eq. (7) is the ONLY thing
    bounding allocation from above. An implementation that quietly omitted it under objective
    (13) would return a large finite number that looks exactly like a result.
  * **`Cost_budget`** (eq. 6). Defined by A.5 in terms of `tau_{w,cost}`, a cost-type SLO
    threshold Section 3.4 never defines and no table reports (A67).

Neither is defaulted. `BudgetChoice` is required, and one of its options is the explicitly named
`no_budget()` -- so the absence is asserted rather than fallen into.
"""

from __future__ import annotations

import pytest

from optimization.milp import Objective, cost_budget, no_budget, solve, table_3
from optimization.milp.objectives import UnboundedObjective
from optimization.milp.scenarios import (
    DEFAULT_COST_MULTIPLIERS,
    NO_BUDGET,
    TABLE_3_ROWS,
    resource_sweep,
)
from optimization.milp.solve import MilpStatus
from optimization.profiles.profile_sets import baseline
from optimization.profiles.schema import SloMix

SLO = ("accuracy", "good")


def _pset():
    return baseline(SloMix.section_4_2(*SLO))


# ---------------------------------------------------------------------------------------------
# Absence is explicit
# ---------------------------------------------------------------------------------------------


def test_no_budget_omits_both_constraints_and_says_so() -> None:
    result = solve(_pset(), "video_qa", SLO, Objective.ENERGY, no_budget())
    inactive = " ".join(result.inactive_constraints)
    assert "eq6" in inactive and "eq7" in inactive
    assert "A43" in inactive, "the omission must cite why the paper states no budget"
    assert "A67" in inactive


def test_omission_is_visible_in_the_rendered_report() -> None:
    """A reader must not have to inspect the object to learn a constraint was dropped."""
    result = solve(_pset(), "video_qa", SLO, Objective.ENERGY, no_budget())
    assert "inactive:" in result.render()


def test_budget_choice_is_required() -> None:
    """Passing nothing is a TypeError, not an unbounded solve."""
    with pytest.raises(TypeError):
        solve(_pset(), "video_qa", SLO, Objective.ENERGY)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------------------------
# eq. (7) -- Table 3's sweep
# ---------------------------------------------------------------------------------------------


def test_table_3_rows_are_the_papers_six() -> None:
    """Section 4.5's sweep: 2,000 A100 with 0-500 H100."""
    assert len(TABLE_3_ROWS) == 6
    assert TABLE_3_ROWS[0] == "a2000_h0"
    assert TABLE_3_ROWS[-1] == "a2000_h500"


def test_a_table_3_budget_activates_eq7() -> None:
    choice = table_3("a2000_h500")
    assert choice.eq7_active
    assert choice.resource == {"A100": 2000.0, "H100": 500.0}
    result = solve(_pset(), "video_qa", SLO, Objective.ENERGY, choice)
    assert "eq7" not in " ".join(result.inactive_constraints)


def test_an_unknown_table_3_row_is_refused() -> None:
    with pytest.raises(KeyError, match="not a Table 3 row"):
        table_3("a9999_h9999")


def test_no_budget_is_not_selectable_as_a_table_3_row() -> None:
    """It is a different kind of thing -- an assertion of absence, not a sweep setting."""
    with pytest.raises(KeyError):
        table_3(NO_BUDGET)


def test_the_resource_sweep_is_ordered() -> None:
    sweep = resource_sweep()
    h100 = [c.resource["H100"] for c in sweep]
    assert h100 == sorted(h100)


def test_a_tight_resource_budget_can_make_a_run_infeasible() -> None:
    """The expected failure mode of the Section 4.5 sweep at its tightest setting: demand
    (1) cannot be met inside eq. (7). Reported by the SOLVER, not structurally, which is the
    distinction Section 7.3 draws."""
    from optimization.milp.scenarios import BudgetChoice

    choke = BudgetChoice(name="choke", resource={"A100": 1.0, "H100": 0.0})
    result = solve(_pset(), "video_qa", SLO, Objective.ENERGY, choke)
    assert result.status in (MilpStatus.INFEASIBLE_SOLVER, MilpStatus.OPTIMAL)
    if result.status is MilpStatus.INFEASIBLE_SOLVER:
        assert result.objective_value is None


# ---------------------------------------------------------------------------------------------
# eq. (6) and objective (13) -- Q23
# ---------------------------------------------------------------------------------------------


def test_objective_13_refuses_to_solve_unbounded() -> None:
    """Section 4.3's guard. Objective (13) does not minimise `n_m`, so with neither eq. (6) nor
    eq. (7) active the fleet is unbounded.

    Refusing is the whole point: a solver handed an unbounded MIP may return a large finite
    value that is indistinguishable from an answer.
    """
    with pytest.raises(UnboundedObjective, match="unbounded"):
        solve(_pset(), "video_qa", SLO, Objective.ACCURACY, no_budget())


def test_objective_13_solves_with_a_resource_budget() -> None:
    result = solve(_pset(), "video_qa", SLO, Objective.ACCURACY, table_3("a2000_h500"))
    assert result.status is MilpStatus.OPTIMAL
    assert result.objective_value is not None


def test_cost_budget_is_relative_to_the_cost_optimum() -> None:
    """Q23. An absolute dollar figure is not comparable across profile sets -- `c_g` alone is
    swept +/-50% -- whereas "1.25x the cheapest feasible fleet" means the same thing in every
    set."""
    choice = cost_budget(1.25, resource={"A100": 2000.0, "H100": 500.0})
    assert choice.eq6_active and choice.cost_multiplier == 1.25
    result = solve(_pset(), "video_qa", SLO, Objective.ACCURACY, choice)
    o2 = solve(_pset(), "video_qa", SLO, Objective.COST, no_budget())
    assert result.cost_budget == pytest.approx(o2.objective_value * 1.25)


def test_the_cost_multiplier_is_labelled_ours() -> None:
    """It has no paper counterpart and every result carrying it must say so."""
    choice = cost_budget(1.5)
    assert "[OURS]" in choice.provenance
    assert "[OURS]" in choice.describe()


def test_a_non_positive_multiplier_is_refused() -> None:
    with pytest.raises(ValueError):
        cost_budget(0.0)


def test_the_default_sweep_starts_at_the_cost_optimum() -> None:
    """1.0x is the tightest interesting budget: exactly the cheapest fleet that meets demand."""
    assert DEFAULT_COST_MULTIPLIERS[0] == 1.0
    assert list(DEFAULT_COST_MULTIPLIERS) == sorted(DEFAULT_COST_MULTIPLIERS)


def test_budget_choice_describes_both_constraints() -> None:
    """So the run's provenance line states the status of eq. (6) and eq. (7) without the reader
    having to infer either."""
    assert "eq6" in no_budget().describe() and "eq7" in no_budget().describe()
    assert "omitted" in no_budget().describe()
