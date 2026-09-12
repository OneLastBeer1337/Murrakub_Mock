"""
The solver substitution -- A.5 p.587 solved with Gurobi; `CLAUDE.md` forbids it.

The substitution is only defensible if it provably cannot change the answer. Two properties make
that checkable rather than asserted:

  * **The model is backend-independent.** Every installed backend must return the same objective
    value on the same model, so a backend difference surfaces as a test failure and never as a
    changed headline number.
  * **The backend cannot change the FORMULATION.** CP-SAT was rejected because it is integer-only
    and `x` is `R+` by A.5's own declaration -- using it would discretise request rates, a
    modelling change smuggled in as a backend change. The variable categories are pinned here.
"""

from __future__ import annotations

import pytest

from optimization.milp import Objective, no_budget, solve
from optimization.milp.model import build_model
from optimization.milp.objectives import attach
from optimization.milp.sets import build_admissible
from optimization.milp.solve import (
    CbcBackend,
    DEFAULT_BACKEND,
    MilpStatus,
    available_backends,
    solve_model,
)
from optimization.profiles.profile_sets import baseline
from optimization.profiles.schema import SloMix
from optimization.profiles.sources.tables import SOLVER_TIME_LIMIT_S

SLO = ("accuracy", "good")


def _built(objective=Objective.ENERGY):
    inputs = baseline(SloMix.section_4_2(*SLO)).to_milp_inputs()
    adm = build_admissible(inputs, "video_qa", SLO, objective_needs_energy=True)
    built = build_model(inputs, adm, epoch=0)
    attach(built, objective)
    return built


# ---------------------------------------------------------------------------------------------
# Variable categories are A.5's, not the backend's
# ---------------------------------------------------------------------------------------------


def test_instance_counts_are_integer_and_allocations_continuous() -> None:
    """A.5 declares `n_m in Z+` and `x in R+`. Both readings of `x` are defensible engineering
    and only one is reproduction (DESIGN.md Section 4.1)."""
    built = _built()
    assert built.n, "expected instance variables"
    for v in built.n.values():
        assert v.cat == "Integer"
    for v in built.x_peak.values():
        assert v.cat == "Continuous"
    for v in built.x_avg.values():
        assert v.cat == "Continuous"


def test_variables_are_non_negative() -> None:
    """`Z+` and `R+`."""
    built = _built()
    for v in list(built.n.values()) + list(built.x_peak.values()):
        assert v.lowBound == 0


# ---------------------------------------------------------------------------------------------
# The substitution is confined to the solver
# ---------------------------------------------------------------------------------------------


def test_cbc_is_available_and_is_the_default() -> None:
    assert DEFAULT_BACKEND.name == "CBC"
    assert CbcBackend().solver().available()


def test_all_available_backends_agree_on_the_objective() -> None:
    """The property that makes "no Gurobi" safe.

    If two open-source solvers disagree, the model is numerically fragile and no headline number
    from it is trustworthy -- which is a finding about our model, not about the paper.
    """
    backends = available_backends()
    assert backends, "no solver backend is installed"
    values = []
    for backend in backends:
        outcome = solve_model(_built(), backend)
        assert outcome.status is MilpStatus.OPTIMAL, f"{backend.name} did not solve"
        values.append(outcome.objective_value)
    for value in values[1:]:
        assert value == pytest.approx(values[0], rel=1e-6), (
            f"backends disagree: {dict(zip([b.name for b in backends], values))}"
        )


def test_the_time_limit_is_the_papers_own() -> None:
    """A.5 p.587: "a time limit of 300 seconds". Imported from `sources/tables.py` with its
    citation rather than retyped here."""
    assert SOLVER_TIME_LIMIT_S == 300
    result = solve(
        baseline(SloMix.section_4_2(*SLO)), "video_qa", SLO, Objective.ENERGY, no_budget()
    )
    assert result.time_limit_s == 300


def test_the_backend_name_travels_with_the_result() -> None:
    """A number whose solver is unknown cannot be reproduced."""
    result = solve(
        baseline(SloMix.section_4_2(*SLO)), "video_qa", SLO, Objective.ENERGY, no_budget()
    )
    assert result.solver in {b.name for b in available_backends()}


# ---------------------------------------------------------------------------------------------
# Determinism and tractability
# ---------------------------------------------------------------------------------------------


def test_the_same_model_solves_to_the_same_answer_twice() -> None:
    """A non-deterministic optimum would make every result in the milestone unreproducible in a
    way no single run could reveal."""
    first = solve_model(_built())
    second = solve_model(_built())
    assert first.objective_value == pytest.approx(second.objective_value, rel=1e-9)


def test_the_model_solves_well_inside_the_paper_s_limit() -> None:
    """~20 integers and a tight LP relaxation. If this ever approached 300 s, the claim that the
    solver substitution cannot change the answer would need revisiting."""
    outcome = solve_model(_built())
    assert outcome.wall_clock_s < 30.0


@pytest.mark.parametrize("objective", [Objective.ENERGY, Objective.COST])
def test_both_unbounded_safe_objectives_solve(objective) -> None:
    """(11) and (12) minimise in `n_m`, so eq. (3) alone bounds them and no budget is needed."""
    outcome = solve_model(_built(objective))
    assert outcome.status is MilpStatus.OPTIMAL
    assert outcome.objective_value is not None and outcome.objective_value > 0
