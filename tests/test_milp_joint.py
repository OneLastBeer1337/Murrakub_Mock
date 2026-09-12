"""
The joint, multi-workflow solve -- A.5 with `|W| = 2`, and Section 4.3's experiment.

Three properties are defended here, and each is a finding rather than a feature:

  * **A75** -- widening `W` was NOT the one-line change M4's design predicted. The `mu` scalar
    was; the mechanism was not. A.5 names the coefficient and never names the mechanism.
  * **The infeasibility coupling** -- eq. (1) is a `for all`, so one empty `(w,s)` takes the
    whole joint problem down. Under `baseline` that is the predicted outcome (A37).
  * **A76** -- objective (13) averages `a_c` values from two different benchmarks.
"""

from __future__ import annotations

import pytest

from optimization.milp.joint import build_joint_admissible, solve_joint
from optimization.milp.mu import from_table_2, no_multiplexing, sweep
from optimization.milp.objectives import Objective
from optimization.milp.scenarios import no_budget, table_3
from optimization.milp.solve import MilpStatus
from optimization.profiles.profile_sets import baseline, derived_tiers

SLOS = [("accuracy", "good"), ("latency", "good")]
BOTH = ["video_qa", "code_generation"]


def _joint(pset, mu=None, objective=Objective.ENERGY, workflows=BOTH, budget=None):
    return solve_joint(
        pset, workflows, SLOS, objective, budget or no_budget(), mu or no_multiplexing()
    )


# ---------------------------------------------------------------------------------------------
# What is shared
# ---------------------------------------------------------------------------------------------


def test_instance_counts_are_shared_across_workflows() -> None:
    """`n_m` is keyed by `m` alone and eq. (3) sums over all `(w,s,c)`. That IS the sharing --
    and A.5 always wrote it this way; M4 simply had one workflow to sum over."""
    result = _joint(derived_tiers())
    assert result.status is MilpStatus.OPTIMAL
    carrying: dict[str, set[str]] = {}
    for (w, _s, _c, m), mass in result.x_peak.items():
        if mass > 1e-9:
            carrying.setdefault(str(m), set()).add(w)
    shared = [m for m, ws in carrying.items() if len(ws) > 1]
    assert shared, "no model carried both workflows -- sharing was not exercised"


def test_variables_carry_the_full_four_index_key() -> None:
    """A.5's `x_{w,s,c,m}`. M4 elided `w` and `s`; M5 restores them (A75)."""
    result = _joint(derived_tiers())
    for key in result.x_peak:
        assert len(key) == 4
        w, s, _c, _m = key
        assert w in BOTH
        assert isinstance(s, tuple) and len(s) == 2


def test_demand_constraints_are_families_not_scalars() -> None:
    """Eq. (1) is `for all w in W, s in S` -- four two-sided pairs here, not one.

    M4 emitted a single scalar pair because it had a single `(w,s)`. That elision is exactly why
    widening `W` touched five files rather than one (A75).
    """
    from optimization.milp.joint import build_joint_model

    inputs = derived_tiers().to_milp_inputs()
    adm = build_joint_admissible(inputs, BOTH, SLOS, Objective.ENERGY)
    built = build_joint_model(inputs, adm, no_multiplexing(), epoch=0)
    names = list(built.problem.constraints)
    assert sum(1 for n in names if n.startswith("eq1_lo")) == 4
    assert sum(1 for n in names if n.startswith("eq2_lo")) == 4


def test_one_capacity_constraint_per_model_not_per_workflow() -> None:
    """The structural precondition for sharing: if eq. (3) were per `(w, m)`, the two workflows
    would provision independently and multiplexing could not exist at all."""
    from optimization.milp.joint import build_joint_model

    inputs = derived_tiers().to_milp_inputs()
    adm = build_joint_admissible(inputs, BOTH, SLOS, Objective.ENERGY)
    built = build_joint_model(inputs, adm, no_multiplexing(), epoch=0)
    eq3 = [n for n in built.problem.constraints if n.startswith("eq3_")]
    assert len(eq3) == len(adm.models())


# ---------------------------------------------------------------------------------------------
# The infeasibility coupling
# ---------------------------------------------------------------------------------------------


def test_one_empty_slo_makes_the_whole_joint_problem_infeasible() -> None:
    """Eq. (1) is a `for all`, so Code Generation goes down with Video Q/A.

    We do not repair this by dropping the latency share or solving the workflows separately and
    calling the result joint. Under `baseline` -- the paper's own printed tiers -- Section 4.3's
    headline experiment is structurally infeasible before the solver starts, via A37.
    """
    result = _joint(baseline())
    assert result.status is MilpStatus.INFEASIBLE_STRUCTURAL
    assert result.empty_slos
    assert any(w == "video_qa" and s == ("latency", "good") for (w, s) in result.empty_slos)


def test_the_offending_slo_is_named_rather_than_a_global_failure() -> None:
    """A solver status code would say "infeasible". This says which `(w,s)` and by how much."""
    result = _joint(baseline())
    assert result.nearest_misses
    key = "video_qa/latency-good"
    assert key in result.nearest_misses
    assert ">" in result.nearest_misses[key] and "tau" in result.nearest_misses[key]


def test_code_generation_alone_would_have_been_feasible() -> None:
    """The coupling is real: Code Generation is feasible on its own at the same tier and is
    taken down only by being in the same problem as Video Q/A."""
    alone = _joint(baseline(), workflows=["code_generation"])
    assert alone.status is MilpStatus.OPTIMAL


def test_the_control_set_runs_the_full_experiment() -> None:
    """`derived_tiers` is M4 Section 7.4's control. If the joint experiment were infeasible
    there too, M5 would have no runnable multiplexing comparison at all."""
    result = _joint(derived_tiers())
    assert result.status is MilpStatus.OPTIMAL
    assert result.total_gpus > 0


# ---------------------------------------------------------------------------------------------
# `mu` moves the answer in the right direction
# ---------------------------------------------------------------------------------------------


def test_multiplexing_reduces_the_shared_fleet() -> None:
    """`mu < 1` relaxes eq. (3), so fewer instances carry the same demand."""
    plain = _joint(derived_tiers(), no_multiplexing())
    mult = _joint(derived_tiers(), from_table_2())
    assert mult.total_gpus < plain.total_gpus


def test_mu_above_one_increases_the_fleet() -> None:
    """Permitted because A.5 bounds `mu_m` nowhere (Q31). Never a headline number."""
    plain = _joint(derived_tiers(), no_multiplexing())
    penalised = _joint(derived_tiers(), sweep(1.25))
    assert penalised.total_gpus >= plain.total_gpus


def test_mu_is_algebraically_a_throughput_bonus() -> None:
    """A78, demonstrated rather than argued.

    `mu * sum(...) <= n * theta` is identical to `sum(...) <= n * (theta / mu)`. So scaling `mu`
    is indistinguishable from scaling `theta_m`: multiplexing, in A.5, is a throughput bonus
    under another name, and the "gain" is exogenous -- the optimizer is told it rather than
    deriving it from the sharing it chose.
    """
    half = _joint(derived_tiers(), sweep(0.5))
    plain = _joint(derived_tiers(), no_multiplexing())
    # Halving mu should roughly halve the fleet, exactly as doubling theta would.
    ratio = half.total_gpus / plain.total_gpus
    assert 0.4 < ratio < 0.65, f"expected ~0.5x, got {ratio:.2f}x"


# ---------------------------------------------------------------------------------------------
# A76 -- objective (13) across two workflows
# ---------------------------------------------------------------------------------------------


def test_accuracy_objective_blends_two_benchmarks() -> None:
    """A76. `a_c` for Code Generation is HumanEval pass@1; for Video Q/A it is VideoMME. Eq.
    (13)'s numerator adds them and its denominator divides by total requests, so the optimizer
    trades quality across workflows at an exchange rate with no meaning. Reproduced as written.
    """
    result = _joint(
        derived_tiers(), from_table_2(), Objective.ACCURACY, budget=table_3("a2000_h500")
    )
    assert result.status is MilpStatus.OPTIMAL
    workflows_with_mass = {w for (w, _s, _c, _m), v in result.x_avg.items() if v > 1e-9}
    assert len(workflows_with_mass) >= 1


def test_accuracy_objective_still_refuses_to_run_unbounded() -> None:
    """M4's Section 4.3 guard survives the widening: (13) does not minimise `n_m`."""
    from optimization.milp.objectives import UnboundedObjective

    with pytest.raises(UnboundedObjective):
        _joint(derived_tiers(), from_table_2(), Objective.ACCURACY)


# ---------------------------------------------------------------------------------------------
# Regression: M4's guarantees survive
# ---------------------------------------------------------------------------------------------


def test_single_workflow_joint_matches_the_m4_path() -> None:
    """THE ANCHOR. `mu = 1` on one workflow must reproduce M4's answer.

    This is what proves the re-keying changed the index space and nothing else -- if the joint
    builder had altered a coefficient, this would diverge and every M5 number would be suspect.
    """
    from optimization.milp import Objective as O, no_budget as nb, solve

    pset = derived_tiers()
    joint = solve_joint(
        pset, ["video_qa"], [("accuracy", "good")], O.ENERGY, nb(), no_multiplexing()
    )
    single = solve(pset, "video_qa", ("accuracy", "good"), O.ENERGY, nb())
    assert joint.status is single.status
    assert joint.objective_value == pytest.approx(single.objective_value, rel=1e-6)
    assert joint.total_gpus == single.total_gpus


def test_gpus_by_workflow_is_labelled_as_ours() -> None:
    """A GPU serves an `m`, and `n_m` is shared by construction -- that IS the multiplexing. Any
    attribution to a workflow needs a rule A.5 does not supply, so ours is labelled."""
    result = _joint(derived_tiers())
    share = result.gpus_by_workflow()
    assert set(share) == set(BOTH)
    assert sum(share.values()) == pytest.approx(result.total_gpus, rel=1e-6)
    assert "[OURS]" in type(result).gpus_by_workflow.__doc__
