"""
Infeasibility as a RESULT -- DESIGN.md Section 7.3, and the four checks of Section 7.4.

Under `baseline`, latency-tier runs are PREDICTED to be infeasible. Q14 fixed `tau` to Figure
7b/8b's printed labels under the reproduce-literally policy, and A37 shows those labels are
unreachable under the paper's own eq. (5) with the paper's own Table 5 configuration. M4 must
reach that conclusion and stop there.

Explicitly forbidden, and each would "fix" the milestone into meaninglessness: loosening `tau`,
swapping in `derived_tiers` and calling it the headline, dropping the `alpha` buffer, substituting
p50 tokens, or falling back to the nearest feasible tier.

Because infeasibility is the EXPECTED outcome, it is also the worst possible place to hide a bug
in our own code. Section 7.4's four independent checks are all asserted here.
"""

from __future__ import annotations

import pytest

from optimization.milp import Objective, no_budget, solve
from optimization.milp.model import build_model
from optimization.milp.objectives import attach
from optimization.milp.sets import build_admissible
from optimization.milp.solve import MilpStatus, relaxation_probe, solve_model
from optimization.profiles.profile_sets import baseline, derived_tiers
from optimization.profiles.schema import SloMix


def _run(slo_type: str, tier: str, objective=Objective.COST):
    pset = baseline(SloMix.section_4_2(slo_type, tier))
    return solve(pset, "video_qa", (slo_type, tier), objective, no_budget())


# ---------------------------------------------------------------------------------------------
# The A37 result
# ---------------------------------------------------------------------------------------------


def test_best_latency_tier_reports_structural_infeasibility() -> None:
    """Detected BEFORE the solver runs, because there is nothing to solve.

    A solver status code would say "infeasible" and stop. The structural path says WHICH filter
    emptied the set and by how much, which is the actual finding.
    """
    result = _run("latency", "best")
    assert result.status is MilpStatus.INFEASIBLE_STRUCTURAL
    assert result.objective_value is None
    assert "eq. (5)" in result.structural_reason
    assert result.nearest_miss


def test_infeasibility_is_reported_not_raised() -> None:
    """An infeasible run is written to the report like any other. Raising would tempt a caller
    to catch and skip, and the whole point is that this outcome gets printed."""
    result = _run("latency", "best")
    rendered = result.render()
    assert "INFEASIBLE_STRUCTURAL" in rendered
    assert "nearest miss" in rendered


def test_the_printed_arithmetic_is_checkable_by_hand() -> None:
    """Section 7.4, check 3. A reviewer holding Table 5 must be able to redo the sum.

    This is how the factor-60 arrival-rate bug was caught during the build: the operands were
    visible, so the wrong one was obvious.
    """
    result = _run("latency", "best")
    miss = result.nearest_miss
    assert "+" in miss and "=" in miss and "tau" in miss
    head, _, tail = miss.partition("=")
    ttft, _, rest = head.partition("+")
    tokens, _, tpot = rest.partition("x")
    computed = float(ttft) + float(tokens) * float(tpot)
    stated = float(tail.split("s")[0])
    assert computed == pytest.approx(stated, rel=1e-3)


def test_alpha_is_not_dropped_to_obtain_feasibility() -> None:
    """A.5's buffer factor stays at 1.15 whatever the outcome."""
    inputs = baseline(SloMix.section_4_2("latency", "best")).to_milp_inputs()
    assert float(inputs.alpha.value) == 1.15


def test_tau_is_not_loosened_to_obtain_feasibility() -> None:
    """The printed Figure 7b label stands, per Q14."""
    inputs = baseline(SloMix.section_4_2("latency", "best")).to_milp_inputs()
    assert float(inputs.tau[("video_qa", "latency", "best")].value) == 0.5


def test_token_policy_stays_at_p90() -> None:
    """Substituting p50 tokens would shrink eq. (5)'s middle term and manufacture feasibility."""
    result = _run("latency", "best")
    assert result.token_policy.percentile == 90


# ---------------------------------------------------------------------------------------------
# Section 7.4 -- distinguishing the paper's inconsistency from our bugs
# ---------------------------------------------------------------------------------------------


def test_the_self_consistent_control_is_feasible() -> None:
    """Check 1. Same code, same data, different `tau`.

    `derived_tiers` computes latency thresholds from our own eq. (5) population. If THAT were
    also infeasible, the fault would be ours and every A37 claim unsafe.

    (This check found a real M3 defect: `derived_tiers` was a byte-for-byte copy of `baseline`
    because `use_printed_latency` was read and then ignored. See A73.)
    """
    inputs = derived_tiers().to_milp_inputs()
    adm = build_admissible(inputs, "video_qa", ("latency", "best"))
    assert not adm.is_empty


def test_derived_latency_tiers_are_per_workflow() -> None:
    """A79. The latency population must be grouped by workflow, exactly as the accuracy one is.

    Pooling both workflows gave them the SAME derived threshold (2.938 s), which is wrong on its
    face: Figures 7b and 8b print visibly different ladders -- 0.5-5.8 s for Video Q/A against
    11.3-78.2 s for Code Generation. A pooled tier is simultaneously too loose for one workflow
    and impossible for the other, and it made the Section 4.3 joint experiment unrunnable on the
    latency arm under EITHER profile set.
    """
    from optimization.profiles.profile_sets import derived_tiers

    inputs = derived_tiers().to_milp_inputs()
    video = float(inputs.tau[("video_qa", "latency", "good")].value)
    code = float(inputs.tau[("code_generation", "latency", "good")].value)
    assert video != code, "derived latency tiers were pooled across workflows"
    assert code > video, (
        "a Code Generation debate runs far longer than a video answer; Figures 7b/8b agree"
    )


def test_both_workflows_are_feasible_on_the_joint_experiment_arm() -> None:
    """Section 4.3's joint setup (70% accuracy / 30% latency, both `good`) is M5's headline.

    Under `baseline` it is infeasible on the latency arm for Video Q/A -- that is A37 and it is
    the expected result. Under `derived_tiers`, the self-consistent control, BOTH workflows must
    be feasible, or M5 has no runnable multiplexing experiment at all.
    """
    from optimization.profiles.profile_sets import derived_tiers

    inputs = derived_tiers().to_milp_inputs()
    for workflow in ("video_qa", "code_generation"):
        adm = build_admissible(inputs, workflow, ("latency", "good"))
        assert not adm.is_empty, f"{workflow} is infeasible under the self-consistent control"


def test_the_two_sets_actually_differ() -> None:
    """The control is worthless if it is a copy of the thing it controls for -- which it was."""
    printed = baseline(SloMix.section_4_2("latency", "best")).to_milp_inputs()
    derived = derived_tiers().to_milp_inputs()
    key = ("video_qa", "latency", "best")
    assert float(printed.tau[key].value) != float(derived.tau[key].value)


def test_the_relaxation_probe_corroborates_rather_than_indicts() -> None:
    """Check 4. The `tau` at which the run would become feasible, COMPUTED and never applied.

    A37 predicts the printed label is unreachable by a small multiple. An extreme ratio would
    mean our arithmetic is wrong, not the paper's.
    """
    inputs = baseline(SloMix.section_4_2("latency", "best")).to_milp_inputs()
    adm = build_admissible(inputs, "video_qa", ("latency", "best"))
    built = build_model(inputs, adm, epoch=0)
    probe = relaxation_probe(built)
    assert probe is not None
    ratio = probe / float(inputs.tau[("video_qa", "latency", "best")].value)
    assert 1.5 < ratio < 20.0, (
        f"would need tau x{ratio:.1f} to become feasible; A37 predicts a small multiple, so an "
        "extreme value indicts our code rather than the paper"
    )


def test_a_known_feasible_tier_still_solves() -> None:
    """Check 2's spirit: if everything were infeasible, the infeasibility would prove nothing."""
    result = _run("latency", "basic")
    assert result.status is MilpStatus.OPTIMAL
    assert result.objective_value is not None and result.objective_value > 0


def test_accuracy_runs_are_feasible_under_baseline() -> None:
    """A37 is specific to the LATENCY tiers. The accuracy ladder reproduces to within the
    digitization band (M3 Section 7.3), so those runs must solve."""
    for tier in ("best", "good", "fair", "basic"):
        result = _run("accuracy", tier, Objective.ENERGY)
        assert result.status is MilpStatus.OPTIMAL, f"accuracy/{tier} unexpectedly infeasible"


def test_structural_infeasibility_skips_the_solver_entirely() -> None:
    """Handing an empty problem to a solver and interpreting its opinion would be worse than
    useless -- the structural reason is already known and more informative."""
    inputs = baseline(SloMix.section_4_2("latency", "best")).to_milp_inputs()
    adm = build_admissible(inputs, "video_qa", ("latency", "best"))
    built = build_model(inputs, adm, epoch=0)
    outcome = solve_model(built)
    assert outcome.status is MilpStatus.INFEASIBLE_STRUCTURAL
    assert outcome.wall_clock_s == 0.0
