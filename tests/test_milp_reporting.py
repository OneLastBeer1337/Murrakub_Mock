"""
Reporting -- DESIGN.md Section 9, and the caveat gate that makes a bare number unobtainable.

Q19 requires the data-excluded set beside every headline number. A convention enforced by
discipline fails the first time someone wants a quick figure for a slide, so it is enforced by
construction instead: `MilpResult.headline()` emits the caveats in the same string as the
objective value, and there is no code path that returns one without the other.

Three further things this milestone must never let a reader miss:

  * **GPU counts are for LLM executors only** -- 11 of 26 executors are tools with no profile, so
    every count is a LOWER bound, unequally between the two workflows (M3 Section 12.3).
  * **A70** -- with continuous `x`, "the chosen configuration" is a distribution. Tables 5/6
    print one row per tier; the formulation need not agree.
  * **A71** -- runs are solved over different index spaces, so cross-run tables need a banner.
"""

from __future__ import annotations

import pytest

from optimization.milp import Objective, compare_runs, no_budget, solve, table_3
from optimization.milp.report import GPU_QUALIFIER, MilpResult, churn, support_size
from optimization.profiles.profile_sets import baseline
from optimization.profiles.schema import SloMix


def _run(slo_type="accuracy", tier="good", objective=Objective.ENERGY, epoch=0):
    pset = baseline(SloMix.section_4_2(slo_type, tier))
    return solve(pset, "video_qa", (slo_type, tier), objective, no_budget(), epoch=epoch)


# ---------------------------------------------------------------------------------------------
# The caveat gate
# ---------------------------------------------------------------------------------------------


def test_no_headline_number_without_its_caveats() -> None:
    """THE Q19 GATE. The objective value and its qualifications arrive together or not at all."""
    result = _run()
    head = result.headline()
    assert f"{result.objective_value:.4f}" in head
    assert result.profile_set_name in head
    assert result.operating_point_policy.value in head
    assert "excluded for lack of data" in head


def test_caveats_name_the_operating_point_as_the_sensitivity_lever() -> None:
    """A37b: the operating-point collapse moves `theta_m` by up to ~6.8x, which moves every GPU
    count by the same factor. A number quoted without it is not interpretable."""
    assert "sensitivity lever" in "\n".join(_run().caveats())


def test_caveats_name_the_token_percentile_and_its_single_source() -> None:
    """A46: the p90 rule rests on one sentence present in one version of the paper."""
    text = "\n".join(_run().caveats())
    assert "p90" in text and "A46" in text


def test_every_gpu_count_is_qualified() -> None:
    """M3 Section 12.3: tools have no profile, so the count is a lower bound on the deployment
    the paper describes, and the qualifier belongs in the sentence."""
    head = _run().headline()
    assert "GPUs" in head
    assert GPU_QUALIFIER in head
    assert "lower" in GPU_QUALIFIER.lower() or "only" in GPU_QUALIFIER


def test_an_infeasible_run_still_renders_with_caveats() -> None:
    """Infeasibility is a result and is written to the report like any other."""
    result = _run("latency", "best")
    head = result.headline()
    assert "INFEASIBLE" in head
    assert result.profile_set_name in head


# ---------------------------------------------------------------------------------------------
# A70 -- the support size
# ---------------------------------------------------------------------------------------------


def test_support_size_is_reported() -> None:
    """A.5 declares `x` continuous, so the optimum may BLEND configurations while Tables 5/6
    print a single row per tier. Whether it blends is an empirical question worth having an
    answer to, and the answer must be visible."""
    result = _run()
    assert result.support_size >= 1
    if result.support_size > 1:
        assert "A70" in result.render()


def test_support_size_counts_only_non_zero_mass() -> None:
    assert support_size({}) == 0
    assert support_size({("a", "b"): 0.0, ("c", "d"): 1.0}) == 1


# ---------------------------------------------------------------------------------------------
# A51 -- incoherence surfaces in the report
# ---------------------------------------------------------------------------------------------


def test_incoherent_mass_is_reported_whatever_its_value() -> None:
    """Both outcomes are findings. A zero must not read as a clean bill of health."""
    result = _run()
    assert result.incoherent_mass is not None
    summary = result.incoherent_mass.summary()
    assert summary
    if result.incoherent_mass.fraction == 0:
        assert "LATENT" in summary and "not a vindication" in summary
    else:
        assert "%" in summary


def test_incoherence_is_measured_under_the_baseline_set() -> None:
    """Under `baseline` the defect is not latent: the optimizer routes Video Q/A load onto
    Phi-4, a model that appears in no Video Q/A configuration at all. A.5's `M` is global and
    nothing ties it to the workflow's own `C_w`."""
    result = _run()
    report = result.incoherent_mass
    assert report.fraction > 0.0, "expected A51 to be exploited under baseline"
    assert report.alien_fraction > 0.0
    assert "NO video_qa configuration" in report.largest_flow.describe()


# ---------------------------------------------------------------------------------------------
# A71 -- cross-run comparison needs a banner
# ---------------------------------------------------------------------------------------------


def test_compare_runs_warns_when_the_excluded_sets_differ() -> None:
    """Two rows solved over different index spaces are not strictly comparable, and the table
    must say so rather than inviting the reader to subtract one from the other."""
    runs = [_run("accuracy", "good"), _run("latency", "basic", Objective.COST)]
    table = compare_runs(runs)
    assert "EXCLUDED SETS DIFFER" in table
    assert "A71" in table


def test_compare_runs_omits_the_banner_when_the_sets_match() -> None:
    runs = [_run("accuracy", "good"), _run("accuracy", "good", Objective.COST)]
    assert "EXCLUDED SETS DIFFER" not in compare_runs(runs)


def test_compare_runs_always_qualifies_its_gpu_column() -> None:
    assert GPU_QUALIFIER in compare_runs([_run()])


def test_compare_runs_handles_no_runs() -> None:
    assert compare_runs([]) == "(no runs)"


# ---------------------------------------------------------------------------------------------
# A69 -- churn across epochs
# ---------------------------------------------------------------------------------------------


def test_churn_measures_the_free_teardown_assumption() -> None:
    """A.5 has no inter-epoch coupling of any kind -- no warm start, no switching cost, no
    minimum instance lifetime -- so the optimizer may rebuild an entire fleet hourly at zero
    modelled cost. This turns that remark into a number."""
    runs = [_run(epoch=e) for e in range(3)]
    total = churn(runs)
    assert total >= 0
    assert isinstance(total, int)


def test_churn_of_a_single_epoch_is_its_own_fleet() -> None:
    """Starting from nothing, the first epoch's churn is the fleet it builds."""
    run = _run(epoch=0)
    assert churn([run]) == sum(run.n.values())


# ---------------------------------------------------------------------------------------------
# Fidelity notes travel with the result
# ---------------------------------------------------------------------------------------------


def test_fidelity_notes_are_attached_to_every_run() -> None:
    """The defects reproduced in this milestone are properties of the ANSWER, not of the
    documentation, so they travel with it."""
    notes = " ".join(_run().fidelity_notes)
    for gap in ("A57", "A58", "A66", "A69", "A72"):
        assert gap in notes


def test_the_equation_map_records_the_duplicates() -> None:
    assert _run().equation_map == {8: 4, 9: 5, 10: 6}
