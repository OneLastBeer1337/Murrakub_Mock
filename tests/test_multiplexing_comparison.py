"""
Table 2 / Figure 18 -- and A80, the strongest result in this milestone.

The paper reports one number and attributes it to multiplexing: GPUs down 21.6%, energy 20.2%,
cost 17.4% ([OSDI] p.576). We compute three arms instead of two, because the paper's single figure
conflates two mechanisms that can be separated:

    A. SEPARATE   -- each workflow alone, summed.   mu = 1
    B. JOINT      -- both in one problem, sharing.  mu = 1    <- "Mkb Opt"
    C. JOINT+MULT -- the same, with mu < 1.                   <- "Mkb Opt+Mult"

`B - A` is what A.5's STRUCTURE achieves. `C - B` is what the `mu` COEFFICIENT contributes.

**A80: `B - A` is zero, or at most integrality rounding.** Eq. (3) is linear, so pooling two
workflows' demand onto one `n_m` needs `ceil((d1+d2)/theta)` instead of `ceil(d1/theta) +
ceil(d2/theta)` -- a difference of at most one instance per shared model. A.5's structure
therefore cannot produce 21.6%; the entire gain enters through a coefficient the paper never
defines, and which we could only obtain by fitting it to that same 21.6%.
"""

from __future__ import annotations

import pytest

from optimization.milp.compare import (
    SECTION_4_3_SLOS,
    SECTION_4_3_WORKFLOWS,
    compare,
)
from optimization.milp.mu import from_table_2, no_multiplexing, sweep
from optimization.milp.objectives import Objective
from optimization.milp.scenarios import no_budget
from optimization.milp.solve import MilpStatus
from optimization.profiles.profile_sets import baseline, derived_tiers


@pytest.fixture(scope="module")
def control():
    """`derived_tiers` -- the only set on which all three arms run (see the baseline test)."""
    return compare(derived_tiers(), Objective.ENERGY, no_budget())


# ---------------------------------------------------------------------------------------------
# A80 -- the structural arm produces nothing
# ---------------------------------------------------------------------------------------------


def test_joint_solving_alone_saves_essentially_nothing(control) -> None:
    """THE FINDING. Sharing `n_m` between two workflows is worth ~0% on its own.

    Not because our model fails to share -- a model IS shared, asserted below -- but because
    eq. (3) is linear in `x` and `n`. Pooling demand can only save integrality rounding.
    """
    assert control.all_feasible
    assert control.structural_sharing_pct is not None
    assert abs(control.structural_sharing_pct) < 1.0, (
        f"structural sharing measured {control.structural_sharing_pct:.2f}%; A80 predicts it is "
        "bounded by integrality rounding"
    )


def test_a_model_really_is_shared_so_the_zero_is_not_vacuous(control) -> None:
    """If no model carried both workflows, `B - A = 0` would be trivial rather than a finding."""
    assert control.shared_models(), "no model was shared -- the A80 measurement means nothing"


def test_the_entire_reported_gain_comes_from_mu(control) -> None:
    """`C - B` accounts for essentially all of `C - A`.

    That is the sharp form of A80: Table 2's headline is not a property of A.5's formulation, it
    is the value of a coefficient the paper never reports.
    """
    assert control.mu_contribution_pct > 20.0
    assert control.combined_pct == pytest.approx(control.mu_contribution_pct, abs=1.0)


def test_the_mu_contribution_matches_one_minus_mu(control) -> None:
    """Because eq. (3) is linear, `n_m` scales with `mu` up to rounding -- so the measured
    reduction must land near `1 - mu`. It does, which confirms the derivation's assumption A3 and
    simultaneously shows the gain was inserted rather than discovered."""
    expected = 100.0 * (1.0 - from_table_2().uniform)
    assert control.mu_contribution_pct == pytest.approx(expected, abs=2.0)


def test_reproducing_table_2_is_arithmetic_not_validation(control) -> None:
    """A63's circularity in new clothes, asserted so no future reader quotes this as a result.

    `mu` was fitted to Table 2's 21.6%. Landing near 21.6% therefore demonstrates only that the
    arithmetic is consistent, which is why the comparison prints CALIBRATION SPENT.
    """
    assert control.joint_mult.mu.calibration_is_spent
    assert "CALIBRATION SPENT" in control.render()
    assert "arithmetic, not validation" in control.render()


# ---------------------------------------------------------------------------------------------
# The headline set, and what it reports instead
# ---------------------------------------------------------------------------------------------


def test_the_paper_s_own_tiers_make_the_experiment_infeasible() -> None:
    """Q30, decided in favour of the paper. `baseline` carries Figure 7b/8b's PRINTED thresholds.

    Section 4.3's experiment includes a 30% low-latency share, and A37 shows the printed latency
    tier is unreachable under A.5's own eq. (5). So the paper's own headline multiplexing
    experiment cannot be run on the paper's own published SLO tiers. That is the finding, and it
    is reported rather than worked around.
    """
    result = compare(baseline(), Objective.ENERGY, no_budget())
    assert not result.all_feasible
    assert result.structural_sharing_pct is None
    assert "NOT ALL ARMS FEASIBLE" in result.render()


def test_the_control_set_is_never_presented_as_the_paper_s(control) -> None:
    """`derived_tiers` uses OUR thresholds. Every number from it must carry that label."""
    assert control.profile_set_name == "derived_tiers"
    assert "derived_tiers" in control.render()


def test_the_comparison_reports_which_version_it_used(control) -> None:
    """A47: the validation target itself differs between versions (21.6 vs 21.1)."""
    assert "OSDI" in control.render()


# ---------------------------------------------------------------------------------------------
# Shape and caveats
# ---------------------------------------------------------------------------------------------


def test_the_two_deltas_are_reported_separately(control) -> None:
    """Q26: report both, refuse to pick which one Table 2's "Murakkab Opt" means.

    Collapsing them into one figure is exactly what the paper does, and it is what hides the
    finding.
    """
    text = control.render()
    assert "structural sharing" in text
    assert "mu contribution" in text
    assert control.structural_sharing_pct != control.mu_contribution_pct


def test_gpu_counts_carry_the_llm_only_qualifier(control) -> None:
    """As at M4: 11 of 26 executors are tools with no profile, so every count is a lower bound."""
    assert "LLM executors only" in control.render()


def test_the_section_4_3_setup_is_the_papers_own() -> None:
    """70% high-accuracy / 30% low-latency, both `good` tier, both workflows together."""
    assert SECTION_4_3_WORKFLOWS == ("video_qa", "code_generation")
    assert SECTION_4_3_SLOS == (("accuracy", "good"), ("latency", "good"))


def test_a_larger_mu_sweep_moves_monotonically() -> None:
    """Sanity on the sensitivity band: smaller `mu` must never need more GPUs."""
    results = [
        compare(derived_tiers(), Objective.ENERGY, no_budget(), mu=sweep(m)).joint_mult.total_gpus
        for m in (0.6, 0.8, 1.0)
    ]
    assert results == sorted(results)


def test_no_multiplexing_arm_equals_the_joint_arm(control) -> None:
    """Arm B is by definition the joint solve at `mu = 1`."""
    assert control.joint.mu.of(None) == 1.0
    assert control.joint.status is MilpStatus.OPTIMAL
