"""
The SLO tier derivation of Section 3.4 (p.575), and its reconstruction against the paper.

This module is the strongest validation in Milestone 3: the paper STATES a rule, PLOTS the data
the rule consumes, and PRINTS the rule's output. All three are checkable against each other, so a
correct reproduction has to close the loop. It does, on both workflows, 8/8 tier values inside the
digitization band.

History worth keeping, because it is the reason these assertions exist: DESIGN.md Section 7.3
originally claimed the tiers reproduced ONLY over a hardware-expanded, TP-feasibility-weighted
population. That claim was wrong twice over -- Phi-4 has four Figure 3 tuples rather than eight
(A53), and the reconstruction had been run with linear-interpolation percentiles. The real
determinant is the PERCENTILE CONVENTION (`lower`), and under it the weighting does not matter at
all. A38 was withdrawn as a result.
"""

from __future__ import annotations

import pytest

from optimization.profiles.slo_tiers import (
    DIGITIZATION_BAND_PP,
    accuracy_population,
    derive_accuracy_tiers,
    derive_latency_tiers,
    reconstruct,
)
from optimization.profiles.sources.figure_labels import FIGURE_3_COVERAGE, TIER_LABELS
from optimization.profiles.sources.figures_digitized import (
    DEEPSEEK_LLAMA_70B_SINGLE_MARKER_PCT,
    FIG_2A_ACCURACY_PCT,
    FIG_2C_ACCURACY_PCT,
    FIG_4B_ACCURACY_PCT,
)

HARDWARE_TUPLES = {m: sum(len(v) for v in g.values()) for m, g in FIGURE_3_COVERAGE.items()}


def _code_gen_accuracy_by_model() -> dict[str, list[float]]:
    """The four Code Gen models that have a readable accuracy source.

    DeepSeek-Llama-70B is absent on purpose: Figure 4b plots exactly one marker for it (A54), so
    its four `a_c` values are Unavailable. `test_admitting_deepseek_llama_70b_breaks_the_tiers`
    shows the tier reconstruction independently agrees with that exclusion.
    """
    by_model: dict[str, list[float]] = {}
    for (model, _d, _r), value in FIG_2C_ACCURACY_PCT.items():
        by_model.setdefault(model, []).append(value)
    for (model, _d, _r), value in FIG_4B_ACCURACY_PCT.items():
        by_model.setdefault(model, []).append(value)
    return by_model


def _video_accuracy_by_model() -> dict[str, list[float]]:
    by_model: dict[str, list[float]] = {}
    for (model, _f, _stt), value in FIG_2A_ACCURACY_PCT.items():
        by_model.setdefault(model, []).append(value)
    return by_model


# ---------------------------------------------------------------------------------------------
# The reconstruction
# ---------------------------------------------------------------------------------------------


def test_code_generation_tiers_reproduce_the_printed_figure_8a_labels():
    pop = accuracy_population(_code_gen_accuracy_by_model())
    result = reconstruct("code_generation", "accuracy", pop)

    assert result["derived"]["best"] == pytest.approx(91.61, abs=0.01)
    assert result["derived"]["good"] == pytest.approx(89.23, abs=0.01)
    assert result["derived"]["fair"] == pytest.approx(87.32, abs=0.01)
    assert result["derived"]["basic"] == pytest.approx(75.77, abs=0.01)
    assert result["within_band"], result["residuals"]


def test_video_qa_tiers_reproduce_the_printed_figure_7a_labels():
    pop = accuracy_population(_video_accuracy_by_model())
    result = reconstruct("video_qa", "accuracy", pop)

    assert result["derived"]["best"] == pytest.approx(66.49, abs=0.01)
    assert result["derived"]["good"] == pytest.approx(64.70, abs=0.01)
    assert result["derived"]["fair"] == pytest.approx(61.37, abs=0.01)
    assert result["derived"]["basic"] == pytest.approx(54.82, abs=0.01)
    assert result["within_band"], result["residuals"]


def test_every_residual_is_inside_the_digitization_band():
    """8/8, and the Code Gen four agree with each other to 0.12 pp -- i.e. the residual is the
    measured bar-edge bias (`BAR_EDGE_BIAS_PP`), not noise."""
    for workflow, by_model in (
        ("code_generation", _code_gen_accuracy_by_model()),
        ("video_qa", _video_accuracy_by_model()),
    ):
        result = reconstruct(workflow, "accuracy", accuracy_population(by_model))
        for tier, residual in result["residuals"].items():
            assert abs(residual) <= DIGITIZATION_BAND_PP, (workflow, tier, residual)

    cg = reconstruct("code_generation", "accuracy", accuracy_population(_code_gen_accuracy_by_model()))
    residuals = list(cg["residuals"].values())
    assert max(residuals) - min(residuals) < 0.15, residuals


# ---------------------------------------------------------------------------------------------
# Why the derivation is robust -- the withdrawal of A38
# ---------------------------------------------------------------------------------------------


def test_hardware_expansion_is_a_no_op_under_the_actual_figure_3_coverage():
    """WITHDRAWS A38, but only in the precise sense the evidence supports.

    Figure 3 covers exactly four (GPU, TP) tuples for each of the four Code Gen models that have
    accuracy data, so the expansion multiplies every member of the population by the SAME factor
    and percentiles are invariant. The tiers therefore do not depend on the feasibility table
    being known -- only on its being UNIFORM, which the figure shows it is."""
    by_model = _code_gen_accuracy_by_model()
    assert {HARDWARE_TUPLES[m] for m in by_model} == {4}, "coverage is uniform across these models"

    flat = derive_accuracy_tiers(accuracy_population(by_model))
    expanded = derive_accuracy_tiers(accuracy_population(by_model, HARDWARE_TUPLES))
    assert flat == expanded


def test_a53_is_load_bearing_the_wrong_phi4_coverage_would_break_the_reconstruction():
    """A53 is not a cosmetic correction to DESIGN.md Section 6.1 -- the reconstruction depends on
    it. Had Phi-4 carried the eight tuples the design doc asserted, its four accuracies (66-76%)
    would be weighted 2x every other model and the printed tiers would NOT reproduce. Verifying
    the marker shapes in the PDF was therefore necessary, not diligence theatre."""
    by_model = _code_gen_accuracy_by_model()
    wrong = {**HARDWARE_TUPLES, "Phi-4": 8}
    result = reconstruct("code_generation", "accuracy", accuracy_population(by_model, wrong))
    assert not result["within_band"], result["residuals"]
    assert result["residuals"]["basic"] < -2.0


def test_nvlm_figure_4b_readings_are_required_by_the_paper_s_own_tiers():
    """Dropping the fourth model misses the printed `basic` tier by more than 10 pp, so reading
    NVLM-D-72B off Figure 4b is validated by the paper's printed output, not merely convenient."""
    by_model = _code_gen_accuracy_by_model()
    three_models = {m: v for m, v in by_model.items() if m != "NVLM-D-72B"}
    without = derive_accuracy_tiers(accuracy_population(three_models))
    printed = TIER_LABELS[("code_generation", "accuracy")]
    assert without["basic"] - printed["basic"] > 10.0


def test_admitting_deepseek_llama_70b_breaks_the_tiers():
    """Corroborates Q13 (treat as distinct, disabled in `baseline`) and A54 (its per-(D,R)
    accuracies are unreadable) from a completely independent direction."""
    by_model = dict(_code_gen_accuracy_by_model())
    by_model["DeepSeek-Llama-70B"] = [DEEPSEEK_LLAMA_70B_SINGLE_MARKER_PCT] * 4
    result = reconstruct("code_generation", "accuracy", accuracy_population(by_model))
    assert not result["within_band"]
    assert abs(result["residuals"]["basic"]) > 5.0


# ---------------------------------------------------------------------------------------------
# Conventions
# ---------------------------------------------------------------------------------------------


def test_every_derived_tier_is_a_member_of_the_population():
    """The `lower` convention exists to guarantee this: Section 3.4 says tiers are values
    "available among the set of all ... configurations", so an interpolated tier -- one no
    configuration achieves -- would be an SLO the platform cannot honour."""
    for by_model in (_code_gen_accuracy_by_model(), _video_accuracy_by_model()):
        pop = accuracy_population(by_model)
        for value in derive_accuracy_tiers(pop).values():
            assert value in pop


def test_latency_tiers_are_oriented_so_that_better_is_stricter():
    """A38b: read literally, Section 3.4's one phrasing over two opposite-polarity quantities
    makes `basic` latency STRICTER than `good`. We flip the orientation; this pins the flip."""
    latencies = [0.5, 0.9, 1.4, 2.0, 3.0, 4.1, 5.8, 9.0, 14.0, 22.0]
    tiers = derive_latency_tiers(latencies)
    assert tiers["best"] <= tiers["good"] <= tiers["fair"] <= tiers["basic"]
    assert tiers["best"] == min(latencies)
    for value in tiers.values():
        assert value in latencies


def test_tiers_shift_when_the_population_changes():
    """Not a defect -- it is what Section 3.4's rule says, and it is why tier values are not
    comparable across profile sets and every result must be tagged with the set that produced
    it."""
    by_model = _code_gen_accuracy_by_model()
    before = derive_accuracy_tiers(accuracy_population(by_model))
    with_new_model = {**by_model, "SomeFutureModel": [12.0, 15.0, 18.0, 20.0]}
    after = derive_accuracy_tiers(accuracy_population(with_new_model))
    assert after["basic"] < before["basic"]
    assert after["best"] == before["best"]
