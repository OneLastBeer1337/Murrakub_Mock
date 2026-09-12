"""
The SLO filters -- eqs. (4)/(5) and their duplicates (8)/(9), and the two findings they carry.

The filters look like the least interesting part of A.5. They are in fact where three separate
defects live:

  * **A66** -- they constrain `x^peak` only, so `x^avg` roams the whole space.
  * **A68/Q24** -- `tau_{w,s}` is ONE number per `(w,s)`, compared against an accuracy in eq. (4)
    and a latency in eq. (5). Only the dimension-matching filter can apply, which leaves latency
    runs with no quality floor at all.
  * **A37** -- under `baseline`, eq. (5) removes every candidate on the `best` latency tier.
    That is the expected result, and reaching it is the point of the run.
"""

from __future__ import annotations

import pytest

from optimization.milp.sets import DATA_LACK, SLO_FILTER, build_admissible
from optimization.profiles.profile_sets import baseline, derived_tiers
from optimization.profiles.schema import SloMix


def _inputs(slo_type: str, tier: str, builder=baseline):
    return builder(SloMix.section_4_2(slo_type, tier)).to_milp_inputs()


def _adm(slo_type: str, tier: str, workflow: str = "video_qa", builder=baseline):
    return build_admissible(
        _inputs(slo_type, tier, builder), workflow, (slo_type, tier)
    )


# ---------------------------------------------------------------------------------------------
# A66 -- the filters bind peak only
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("slo", [("accuracy", "best"), ("latency", "basic")])
def test_average_allocation_is_not_slo_filtered(slo) -> None:
    """A66 reproduced as an index-space asymmetry, not as a comment.

    `x^avg`'s space must be strictly larger than `x^peak`'s wherever the filter bites. Making
    them equal would be a repair -- and a very tempting one, because the asymmetry looks like a
    bug until you read eqs. (2), (6) and (13) and find no filter among them.
    """
    adm = _adm(*slo)
    assert len(adm.pairs_unfiltered) > len(adm.pairs), (
        "x^avg was restricted to the filtered space -- A66 has been repaired"
    )
    filtered_out = set(adm.pairs_unfiltered) - set(adm.pairs)
    assert filtered_out, "no pair was SLO-filtered, so this test asserted nothing"


def test_slo_violating_pairs_remain_available_to_the_accuracy_objective() -> None:
    """The sharp end of A66.

    Objective (13) maximises `sum x^avg * a_c`. Every pair the accuracy filter rejected is still
    in `x^avg`'s domain, so the objective may place load on configurations whose accuracy is
    below the very threshold the run is named after.
    """
    adm = _adm("accuracy", "best")
    rejected = set(adm.pairs_unfiltered) - set(adm.pairs)
    below_threshold = [
        (c, m) for (c, m) in rejected if c in adm.a_c
    ]
    assert below_threshold, "expected accuracy-rejected pairs to survive in x^avg"


# ---------------------------------------------------------------------------------------------
# A68 / Q24 -- only the dimension-matching filter applies
# ---------------------------------------------------------------------------------------------


def test_accuracy_filter_does_not_run_on_a_latency_tier() -> None:
    """A.5 itself scopes each filter: "For accuracy SLO (s = max_accuracy)" / "For latency SLO
    (s = min_latency)". So this is the LITERAL reading, not a deviation.

    Applying eq. (4) on a latency run would compare an accuracy fraction against a threshold in
    seconds -- not a comparison at all.
    """
    adm = _adm("latency", "basic")
    assert all(e.parameter != "eq4" for e in adm.ledger.slo_excluded)


def test_latency_filter_does_not_run_on_an_accuracy_tier() -> None:
    adm = _adm("accuracy", "best")
    assert all(e.parameter != "eq5" for e in adm.ledger.slo_excluded)


def test_a_latency_run_has_no_quality_floor_whatsoever() -> None:
    """A68's consequence, asserted rather than asserted-about.

    `tau_{w,s}` is one number. On a latency tier it is a latency, so nothing in the formulation
    bounds answer quality, and the optimizer is free to pick the worst configuration in `C_w`.
    A reader comparing Figure 7b's latency tiers against Figure 7a's accuracy tiers would
    reasonably assume both promises hold at once. They cannot.
    """
    adm = _adm("latency", "basic")
    admitted_accuracies = [adm.a_c[c] for c in adm.configs if c in adm.a_c]
    assert admitted_accuracies
    # The worst admitted configuration is genuinely bad -- no floor removed it.
    assert min(admitted_accuracies) < max(admitted_accuracies)


def test_the_excluded_set_differs_between_accuracy_and_latency_runs() -> None:
    """A71, asserted on the asymmetry the data actually exercises.

    The obvious instance -- a configuration with `a_c` but no `t_c` -- does NOT occur: in both
    workflows every configuration missing `a_c` is also missing `t_c`, and `t_c` is checked
    first, so the accuracy gap is always subsumed. The observable instance is on the model side:
    7 of 20 profiles have no `l^TTFT_m` (A35/A36), which is fatal on a latency run and
    irrelevant on an accuracy run.

    That is enough to make the point A71 exists for: the eight Section 4.2 runs are solved over
    different index spaces, so their objective values are not strictly comparable.
    """
    acc = _adm("accuracy", "best")
    lat = _adm("latency", "basic")
    assert set(acc.models) != set(lat.models)
    assert len(acc.models) > len(lat.models), "TTFT gaps should bite only on latency runs"
    ttft_gaps = {e.element for e in lat.ledger.data_excluded if e.parameter == "l_ttft_m"}
    assert ttft_gaps, "expected model profiles with no TTFT"
    assert any("Llava-OneVision-7B" in e for e in ttft_gaps), (
        "A62: the model Section 4.6's parallelism study runs must be among them"
    )


# ---------------------------------------------------------------------------------------------
# A37 -- the expected infeasibility
# ---------------------------------------------------------------------------------------------


def test_best_latency_tier_is_structurally_infeasible_under_baseline() -> None:
    """THE A37 RESULT. Not a bug -- the paper's own printed tier is unreachable under its own
    eq. (5) using its own Table 5 configuration.

    Q14 fixed `tau` to Figure 7b/8b's printed labels under the reproduce-literally policy. This
    test asserts the consequence, so that anyone who later "fixes" it by loosening `tau` breaks
    a test that explains why they must not.
    """
    adm = _adm("latency", "best")
    assert adm.is_empty
    assert "eq. (5)" in adm.empty.emptied_by
    assert adm.empty.nearest_miss, "the arithmetic of the nearest miss must be printed"
    assert ">" in adm.empty.nearest_miss and "tau" in adm.empty.nearest_miss


def test_the_nearest_miss_shows_its_operands() -> None:
    """Section 7.4's third check against our own bugs.

    The printed line must contain the actual numbers, so a reviewer holding Table 5 can redo the
    arithmetic by eye. A unit-conversion error surfaces here immediately -- which is exactly how
    a factor-60 bug in the arrival rate was caught during this build.
    """
    adm = _adm("latency", "best")
    miss = adm.empty.nearest_miss
    assert "+" in miss and "x" in miss and "=" in miss


def test_derived_tiers_is_the_self_consistent_control() -> None:
    """Section 7.4's first check: same code, same data, different `tau`.

    `derived_tiers` computes thresholds from our own population instead of the printed labels.
    If the `best` latency tier is infeasible THERE too, the fault is ours rather than the
    paper's, and every A37 claim in this milestone would be unsafe.
    """
    from optimization.profiles.profile_sets import derived_tiers

    inputs = derived_tiers().to_milp_inputs()
    adm = build_admissible(inputs, "video_qa", ("latency", "best"))
    assert not adm.is_empty, (
        "derived_tiers is also infeasible -- suspect our code, not the paper (Section 7.4)"
    )

    # And the ratio corroborates rather than indicts: A37 predicts the printed label is
    # unreachable by roughly 2-5x, not by orders of magnitude. A measured 400x would mean the
    # fault was ours.
    printed = 0.5
    derived_best = float(inputs.tau[("video_qa", "latency", "best")].value)
    assert 1.5 < derived_best / printed < 20.0, (
        f"derived best tier is {derived_best / printed:.1f}x the printed label; A37 predicts "
        "a small multiple, so an extreme value indicts our code"
    )


# ---------------------------------------------------------------------------------------------
# Data-lack and SLO-filter are never conflated
# ---------------------------------------------------------------------------------------------


def test_exclusion_kinds_are_kept_apart() -> None:
    """"Too slow to meet its promise" and "the paper never reported this" are different claims.

    Summing them would be the most misleading single number this milestone could produce -- it
    would let a data gap masquerade as a performance verdict.
    """
    adm = _adm("latency", "basic")
    kinds = {e.kind for e in adm.ledger.entries}
    assert kinds <= {DATA_LACK, SLO_FILTER}
    summary = adm.ledger.summary()
    assert set(summary) == {"excluded_for_lack_of_data", "excluded_by_slo_filter"}
    assert summary["excluded_for_lack_of_data"] + summary["excluded_by_slo_filter"] == len(
        adm.ledger
    )


def test_data_gaps_are_never_tested_against_a_threshold() -> None:
    """A configuration with no `t_c` is unmeasured, not slow.

    Order matters: data availability is checked BEFORE the filter, so nothing dropped for data
    ever reaches a comparison that would manufacture a verdict out of a missing number.
    """
    adm = _adm("latency", "basic")
    data_elements = {e.element for e in adm.ledger.data_excluded}
    for entry in adm.ledger.slo_excluded:
        for element in data_elements:
            assert not entry.element.startswith(element + " on"), (
                f"{element} was excluded for data AND tested against a threshold"
            )
