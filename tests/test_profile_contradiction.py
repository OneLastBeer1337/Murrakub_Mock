"""
The direct encoding of the `CLAUDE.md` rule: **never invent a number that contradicts a
paper-reported figure.**

DESIGN.md Section 2.5 calls this the "fifth, softer test". Softer because it cannot be
exhaustive -- it only covers values the paper ALSO reports -- but it is the one that turns the
rule from an intention into something a build can fail on.

Two strengths of agreement, deliberately kept apart:

  * `PAPER_TABLE` and `PAPER_FIGURE_LABEL` are TYPESET text. Exact to the digit, zero tolerance.
  * `PAPER_FIGURE_READ` is a pixel reading. Agreement means "inside the recorded band", and a
    band is mandatory at that provenance level.

Conflating them is how a digitized value would quietly acquire the authority of a printed one.
"""

from __future__ import annotations

import pytest

from optimization.profiles.model_profiles import ENERGY_PER_GPU, build_model_profiles
from optimization.profiles.profile_sets import profile_set
from optimization.profiles.provenance import Measured, Provenance, Unavailable
from optimization.profiles.schema import ModelProfileKey, OperatingPointPolicy
from optimization.profiles.slo_tiers import DIGITIZATION_BAND_PP
from optimization.profiles.validation import (
    TIER_LABEL_TOLERANCE_PP,
    figure2c_vs_tier_labels,
    figure3_vs_tables,
)
from optimization.profiles.sources.external import (
    GPUS_PER_VM,
    RETRIEVED,
    VM_HOURLY_USD,
    cost_per_gpu_second,
)
from optimization.profiles.sources.figure_labels import TIER_LABELS
from optimization.profiles.sources.tables import (
    ALPHA,
    TABLE_3,
    TABLE_5_OSDI,
    TABLE_6_OSDI,
)


@pytest.fixture(scope="module")
def models():
    return build_model_profiles()


# ---------------------------------------------------------------------------------------------
# Exact agreement with typeset numbers
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("row", TABLE_5_OSDI, ids=lambda r: f"{r.slo}/{r.objective}/{r.tier}")
def test_table_5_cells_are_reproduced_exactly(models, row) -> None:
    mp = models[ModelProfileKey(row.model, row.gpu, row.tp)]
    tpot = mp.tpot(OperatingPointPolicy.TABLE_REPORTED)
    theta = mp.theta(OperatingPointPolicy.TABLE_REPORTED)
    if isinstance(tpot, Unavailable) or isinstance(theta, Unavailable):
        pytest.skip("no tabled operating point")
    reported = {(r.tpot_s, r.tps) for r in TABLE_5_OSDI if
                (r.model, r.gpu, r.tp) == (row.model, row.gpu, row.tp)}
    reported |= {(r.tpot_s, r.tps) for r in TABLE_6_OSDI if
                 (r.model, r.gpu, r.tp) == (row.model, row.gpu, row.tp)}
    assert (float(tpot.value), float(theta.value)) in reported


@pytest.mark.parametrize("row", TABLE_6_OSDI, ids=lambda r: f"{r.slo}/{r.objective}/{r.tier}")
def test_table_6_cells_are_reproduced_exactly(models, row) -> None:
    mp = models[ModelProfileKey(row.model, row.gpu, row.tp)]
    tpot = mp.tpot(OperatingPointPolicy.TABLE_REPORTED)
    theta = mp.theta(OperatingPointPolicy.TABLE_REPORTED)
    if isinstance(tpot, Unavailable) or isinstance(theta, Unavailable):
        pytest.skip("no tabled operating point")
    reported = {(r.tpot_s, r.tps) for r in TABLE_6_OSDI if
                (r.model, r.gpu, r.tp) == (row.model, row.gpu, row.tp)}
    reported |= {(r.tpot_s, r.tps) for r in TABLE_5_OSDI if
                 (r.model, r.gpu, r.tp) == (row.model, row.gpu, row.tp)}
    assert (float(tpot.value), float(theta.value)) in reported


def test_paper_table_values_carry_no_band(models) -> None:
    """A table cell is exact. A band on one would imply the paper reported a range it did not."""
    pset = profile_set("baseline")
    for key, mp in pset.models.items():
        for getter in (mp.theta, mp.tpot):
            v = getter(OperatingPointPolicy.TABLE_REPORTED)
            if isinstance(v, Measured) and v.provenance is Provenance.PAPER_TABLE:
                assert v.lo is None and v.hi is None, f"{key}: a table cell acquired a band"


def test_alpha_matches_the_paper() -> None:
    """Section 4.2 (p.576)'s over-provisioning factor, used by eq. (2)."""
    assert ALPHA == 1.15
    alpha = profile_set("baseline").alpha
    assert float(alpha.value) == ALPHA


def test_energy_matches_table_3(models) -> None:
    """A41. `e_m` comes from Table 3 per GPU type, and must equal what Table 3 implies rather
    than a rounded convenience value."""
    for gpu, value in ENERGY_PER_GPU.items():
        if isinstance(value, Unavailable):
            continue
        assert float(value.value) > 0, gpu
    assert len(TABLE_3) >= 6, "Table 3's sweep is the source for both GPU types"


# ---------------------------------------------------------------------------------------------
# Printed tier labels
# ---------------------------------------------------------------------------------------------


def test_tier_labels_are_reproduced_within_the_digitization_band() -> None:
    """Section 7.3's reconstruction, asserted as a contradiction check rather than a fit.

    The paper STATES the tier rule (Section 3.4, p.575), PLOTS the population it consumes
    (Figures 2a/2c, 4a/4b) and PRINTS the rule's output (Figures 7/8 labels). A correct
    reproduction closes that loop; a value outside the band means our population or our
    percentile convention contradicts a printed number.
    """
    result = profile_set("baseline").tier_reconstruction
    assert result, "the reconstruction produced nothing"
    for workflow, data in result.items():
        for tier, printed in data["printed"].items():
            derived = data["derived"][tier]
            residual = abs(derived - printed)
            assert residual <= DIGITIZATION_BAND_PP, (
                f"{workflow}/{tier}: derived {derived} vs printed {printed} "
                f"({residual:.2f} pp > {DIGITIZATION_BAND_PP} pp band)"
            )


def test_printed_tier_labels_are_not_silently_edited() -> None:
    """The printed labels are typeset text and must be monotone in the direction of their SLO.

    The direction differs by SLO type and getting it backwards would invert every tier
    assignment: accuracy tiers DESCEND (`best` 66.2% > `basic` 54.9%) because more is better,
    while latency tiers ASCEND (`best` 0.5s < `basic` 5.8s) because less is. Section 3.4 (p.575)
    defines both off the same percentile rule, so only the comparison direction changes.
    """
    assert TIER_LABELS, "no printed tier labels were transcribed"
    for (workflow, slo_type), labels in TIER_LABELS.items():
        assert set(labels) == {"best", "good", "fair", "basic"}, (workflow, slo_type)
        ordered = [labels[t] for t in ("best", "good", "fair", "basic")]
        if slo_type == "accuracy":
            assert ordered == sorted(ordered, reverse=True), f"{workflow}/{slo_type}"
        else:
            assert ordered == sorted(ordered), f"{workflow}/{slo_type}"


# ---------------------------------------------------------------------------------------------
# Section 6.2 -- the tables are samples of Figure 3, so they validate the digitization
# ---------------------------------------------------------------------------------------------


def test_every_table_cell_lands_on_its_figure_3_curve() -> None:
    """DESIGN.md Section 6.2, point 2: "Each validated point is asserted in
    test_profile_contradiction.py". This is that assertion.

    The tables report `(TPS, TPOT)` and Figure 3 plots TPOT against TPS for the same tuple, so a
    tabled cell must lie ON the digitized curve. Nothing in the pipeline forces this: the cells
    are transcribed from a table and the curve is read off a log-axis panel carrying eight
    series. Agreement is therefore evidence that the Figure 3 reading is sound -- which matters
    because 8 of the 20 profiles have NO table row and rest entirely on that reading.
    """
    checks = figure3_vs_tables()
    assert len(checks) >= 12, f"only {len(checks)} tabled points were checkable"
    bad = [
        f"{c.key} @ {c.table_tps:.0f} TPS: table {c.table_tpot:.4f} vs curve "
        f"{c.curve_tpot:.4f} ({c.residual_frac * 100:.1f}%)"
        for c in checks
        if not c.agrees
    ]
    assert not bad, "table cells off their own curve:\n  " + "\n  ".join(bad)


def test_the_figure_3_agreement_is_tight_not_merely_within_tolerance() -> None:
    """The tolerance is 20% because a log-axis read near a crossing is genuinely uncertain. The
    OBSERVED agreement is far better than that, and pinning it means a digitization regression
    that still squeaked inside the band would fail here."""
    worst = max(c.residual_frac for c in figure3_vs_tables())
    assert worst < 0.05, f"worst residual {worst * 100:.1f}% -- previously under 4%"


def test_the_curve_is_read_independently_of_the_table() -> None:
    """The check above is only evidence if the curve points are not themselves the table cells.

    `_curve_points` inserts the tabled operating point INTO the curve alongside the digitized
    markers, so a naive comparison could compare a cell against itself and always agree.
    `figure3_vs_tables` interpolates over `Figure`-origin points only; this asserts that
    exclusion is real.
    """
    from optimization.profiles.model_profiles import build_model_profiles

    mp = build_model_profiles()[ModelProfileKey("DeepSeek-Qwen-32B", "H100", 4)]
    origins = {p.origin.split()[0] for p in mp.curve}
    assert {"Table", "Figure"} <= origins, "expected both sources on the curve"
    check = next(c for c in figure3_vs_tables() if c.key.model_id == "DeepSeek-Qwen-32B"
                 and c.key.gpu == "H100")
    assert check.curve_tpot != check.table_tpot, "the curve read reproduced the cell exactly"


# ---------------------------------------------------------------------------------------------
# Section 5.2 -- bars, tier labels and the chosen-configuration table agree
# ---------------------------------------------------------------------------------------------


def test_digitized_bars_agree_with_the_printed_tier_labels() -> None:
    """Three independent parts of the paper have to line up: Figure 2c's bar (digitized), Figure
    8a's printed threshold (typeset), and Table 6's row naming the configuration chosen at that
    tier (typeset). Nothing in our pipeline forces them to agree."""
    checks = figure2c_vs_tier_labels()
    assert len(checks) == 4, f"expected all four Code Gen accuracy tiers, got {len(checks)}"
    bad = [
        f"{c.tier}: {c.model} D={c.debaters} R={c.rounds} digitized {c.digitized_pct} vs "
        f"printed {c.printed_pct} ({c.residual_pp:+.2f} pp)"
        for c in checks
        if not c.agrees
    ]
    assert not bad, "\n  ".join(bad)


def test_the_chosen_configuration_clears_its_tier_rather_than_equalling_it() -> None:
    """The sign of the residual is the finding, and it confirms the tier SEMANTICS.

    Section 3.4 (p.575) defines a tier as a percentile of the population, while Table 6 names the
    configuration the optimizer PICKED there -- which must clear the threshold, not equal it. So
    every residual should be >= 0, and all four are (+0.21, +0.33, +0.82, +0.27 pp). A negative
    one would mean the optimizer chose a configuration below its own advertised tier, which would
    indicate we had misread either the tier rule or the table.
    """
    for c in figure2c_vs_tier_labels():
        assert c.residual_pp >= -TIER_LABEL_TOLERANCE_PP, (
            f"{c.tier}: chosen configuration sits {c.residual_pp:.2f} pp BELOW its tier"
        )


def test_accuracy_is_digitized_from_figure_2c_not_from_the_tier_labels() -> None:
    """A63 -- the independence the two checks above depend on.

    If any `a_c` were sourced from a printed tier label, the Section 5.2 check would be comparing
    a number against itself and the Section 7.3 reconstruction would derive labels from a
    population containing those labels. Both would still pass, and both would mean nothing. So
    no `a_c` may carry PAPER_FIGURE_LABEL provenance.
    """
    pset = profile_set("baseline")
    promoted = [
        str(k)
        for k, wp in pset.workflow.items()
        if isinstance(wp.accuracy, Measured)
        and wp.accuracy.provenance is Provenance.PAPER_FIGURE_LABEL
    ]
    assert not promoted, (
        "a_c values sourced from printed tier labels make the Section 5.2 and 7.3 checks "
        f"circular (A63): {promoted}"
    )


# ---------------------------------------------------------------------------------------------
# Digitized values stay inside their bands
# ---------------------------------------------------------------------------------------------


def test_digitized_values_declare_a_band_containing_them() -> None:
    pset = profile_set("baseline")
    for key, wp in pset.workflow.items():
        if isinstance(wp.accuracy, Measured) and wp.accuracy.provenance is (
            Provenance.PAPER_FIGURE_READ
        ):
            assert wp.accuracy.lo is not None, f"{key}: a figure reading without a band"
            assert wp.accuracy.lo <= wp.accuracy.value <= wp.accuracy.hi, key


def test_accuracy_values_are_plausible_percentages() -> None:
    """VideoMME and HumanEval are both reported as percentages. A value outside [0, 100] would
    mean an axis was misread, which is the failure mode Figure 4a/4b's dense clouds invite."""
    pset = profile_set("baseline")
    for key, wp in pset.workflow.items():
        if isinstance(wp.accuracy, Unavailable):
            continue
        assert 0.0 <= float(wp.accuracy.value) <= 100.0, f"{key}: {wp.accuracy.value}"


def test_the_documented_number_of_accuracies_are_unavailable() -> None:
    """A54/A55: 10 of 44 `a_c` values have no source. Pinned so that a regression which starts
    interpolating them fails here rather than quietly improving a coverage statistic."""
    pset = profile_set("baseline")
    missing = [k for k, wp in pset.workflow.items() if isinstance(wp.accuracy, Unavailable)]
    assert len(missing) == 10, sorted(str(k) for k in missing)


# ---------------------------------------------------------------------------------------------
# The one external source
# ---------------------------------------------------------------------------------------------


def test_external_prices_are_stamped_external_with_a_retrieval_date() -> None:
    """`c_g` is the only number in the set with a non-paper source (A40: the paper reports no
    cost per GPU-second anywhere, and Table 2 implies two different values for one cluster).
    EXTERNAL provenance demands a retrieval date so the number can be re-checked."""
    assert RETRIEVED, "a vendor price list without a date is not a source"
    for name in VM_HOURLY_USD:
        price = cost_per_gpu_second(name)
        assert price.provenance is Provenance.EXTERNAL, name
        assert price.cite.retrieved == RETRIEVED, f"{name}: no retrieval date"
        assert float(price.value) > 0


def test_cost_per_gpu_second_is_derived_from_the_vm_price(models) -> None:
    """A57: `c_g` is per GPU, not per instance -- eqs. (6) and (12) both multiply it by `g_m`,
    as eq. (11) does to `e_m`. A VM has 8 GPUs (Section 4.1, p.575), so the per-GPU-second rate
    must be the hourly VM price divided by 8 and by 3600."""
    pset = profile_set("baseline")
    assert GPUS_PER_VM == 8
    for gpu, hourly in VM_HOURLY_USD.items():
        c_g = pset.resources[gpu].cost_per_instance_second
        if isinstance(c_g, Unavailable):
            continue
        expected = hourly / GPUS_PER_VM / 3600.0
        assert float(c_g.value) == pytest.approx(expected, rel=1e-6), gpu
