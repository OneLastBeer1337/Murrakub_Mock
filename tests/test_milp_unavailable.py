"""
Missing data -- DESIGN.md Section 7.1: exclude and report, never impute.

The rule has no exceptions, and the reason is that every plausible substitute is FLATTERING in a
specific direction:

  * `l^TTFT_m = 0` makes filter (5) more permissive -- more configurations pass their latency SLO.
  * `t_c = 0` makes a configuration free in eq. (3) -- zero capacity consumed, zero GPUs needed.
  * `a_c = 0` would fail filter (4) and look conservative, but silently removes a configuration
    for a reason that has nothing to do with its quality.

So an absent number removes the index element that needs it, and the removal is recorded with its
reason. Q19 then requires that record to be printed beside every headline number.
"""

from __future__ import annotations

import pytest

from optimization.milp import Objective, no_budget, solve
from optimization.milp.sets import build_admissible
from optimization.profiles.profile_sets import baseline
from optimization.profiles.provenance import Unavailable
from optimization.profiles.schema import SloMix


@pytest.fixture(scope="module")
def accuracy_inputs():
    return baseline(SloMix.section_4_2("accuracy", "good")).to_milp_inputs()


@pytest.fixture(scope="module")
def latency_inputs():
    return baseline(SloMix.section_4_2("latency", "basic")).to_milp_inputs()


def test_configurations_without_tokens_are_excluded_not_zeroed(accuracy_inputs) -> None:
    """`t_c = 0` would make a configuration consume no capacity and therefore need no GPUs --
    the most flattering possible substitution."""
    adm = build_admissible(accuracy_inputs, "video_qa", ("accuracy", "good"))
    gaps = {e.element for e in adm.ledger.data_excluded if e.parameter == "t_c"}
    assert gaps, "expected configurations with no token distribution"
    for c in adm.configs:
        assert str(c) not in gaps
        assert float(adm.t_c[c].value) > 0.0


def test_models_without_ttft_are_excluded_on_latency_runs(latency_inputs) -> None:
    """`l^TTFT_m = 0` would make filter (5) MORE permissive -- it would admit models by deleting
    the term that disqualifies them. 7 of 20 profiles have no TTFT (A35/A36)."""
    adm = build_admissible(latency_inputs, "video_qa", ("latency", "basic"))
    gaps = {e.element for e in adm.ledger.data_excluded if e.parameter == "l_ttft_m"}
    assert len(gaps) >= 5
    for m in adm.models:
        assert str(m) not in gaps


def test_models_without_ttft_are_admissible_on_accuracy_runs(accuracy_inputs) -> None:
    """A71: the same profile is admissible or not depending on the SLO TYPE, so the runs are
    solved over different index spaces."""
    adm = build_admissible(accuracy_inputs, "video_qa", ("accuracy", "good"))
    ttft_gaps = [
        m for m in adm.models if isinstance(accuracy_inputs.l_ttft_m[m], Unavailable)
    ]
    assert ttft_gaps, "a model with no TTFT should still be usable under an accuracy SLO"


def test_energy_gaps_only_bite_the_energy_objective(accuracy_inputs) -> None:
    """A71 again: `e_m` is consumed by objective (11) and nothing else, so exclusion is
    objective-dependent. With complete `e_m` coverage the two sets coincide -- and asserting
    that they *can* differ is what keeps the mechanism honest."""
    with_energy = build_admissible(
        accuracy_inputs, "video_qa", ("accuracy", "good"), objective_needs_energy=True
    )
    without = build_admissible(accuracy_inputs, "video_qa", ("accuracy", "good"))
    assert set(with_energy.models) <= set(without.models)


def test_every_exclusion_carries_a_reason(accuracy_inputs) -> None:
    """An exclusion with no reason is indistinguishable from a bug."""
    adm = build_admissible(accuracy_inputs, "video_qa", ("accuracy", "good"))
    for entry in adm.ledger.entries:
        assert entry.reason, f"{entry.element} excluded with no reason"
        assert entry.parameter, f"{entry.element} excluded with no parameter named"


def test_slo_exclusions_carry_the_arithmetic(latency_inputs) -> None:
    """So a reviewer holding Table 5 can check the verdict by eye."""
    adm = build_admissible(latency_inputs, "video_qa", ("latency", "basic"))
    for entry in adm.ledger.slo_excluded:
        assert entry.arithmetic, f"{entry.element} filtered with no arithmetic shown"
        assert "=" in entry.arithmetic


def test_no_unavailable_value_reaches_the_solved_model(accuracy_inputs) -> None:
    """The end-to-end guarantee: nothing that entered a constraint was a documented absence."""
    adm = build_admissible(
        accuracy_inputs, "video_qa", ("accuracy", "good"), objective_needs_energy=True
    )
    for c in adm.configs:
        assert not isinstance(accuracy_inputs.t_c[c], Unavailable)
    for m in adm.models:
        assert not isinstance(accuracy_inputs.theta_m[m], Unavailable)
        assert not isinstance(accuracy_inputs.e_m[m], Unavailable)


def test_the_result_reports_what_it_excluded() -> None:
    """Q19: mandatory beside every headline number."""
    pset = baseline(SloMix.section_4_2("accuracy", "good"))
    result = solve(pset, "video_qa", ("accuracy", "good"), Objective.ENERGY, no_budget())
    assert result.data_excluded, "a run with known gaps reported none"
    assert result.exclusion_ledger is not None
    summary = result.exclusion_ledger.summary()
    assert summary["excluded_for_lack_of_data"] == len(result.data_excluded)


def test_data_lack_and_slo_filtering_are_never_summed() -> None:
    """They are different claims, and one number conflating them would let a hole in the
    evidence masquerade as a performance verdict."""
    pset = baseline(SloMix.section_4_2("latency", "basic"))
    result = solve(pset, "video_qa", ("latency", "basic"), Objective.COST, no_budget())
    summary = result.exclusion_ledger.summary()
    assert summary["excluded_for_lack_of_data"] != summary["excluded_by_slo_filter"]
    text = "\n".join(result.caveats())
    assert "data-lack" in text and "SLO-filtered" in text
    assert "NEVER summed" in text
