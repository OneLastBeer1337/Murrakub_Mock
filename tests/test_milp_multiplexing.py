"""
`mu_m` -- the multiplexing factor, and what the paper does and does not say about it.

A.5 introduces `mu_m` in eq. (3) and defines it in one clause: "where mu_m is the model-specific
multiplexing factor". No value, no bound, no units, no estimation method, in either version, and
it is absent from Section 3.3's list of what a profile contains (A42).

These tests defend the consequences of that: `mu` is an injected coordinate and never profile
data; the one value we can obtain is DERIVED from Table 2 and its calibration is therefore spent;
per-model values are invented and quarantined; and the symbol is bounded nowhere, so we do not
bound it either.
"""

from __future__ import annotations

import pytest

from optimization.milp import mu as mu_mod
from optimization.milp.mu import (
    DEFAULT_SWEEP,
    DERIVATION_ASSUMPTIONS,
    MuSource,
    from_table_2,
    no_multiplexing,
    out_of_sample_targets,
    sweep,
    uniform_from_table_2,
)
from optimization.profiles.schema import MilpInputs
from optimization.profiles.sources.tables import MULTIPLEXING_REDUCTION_PCT


# ---------------------------------------------------------------------------------------------
# `mu` is not profile data
# ---------------------------------------------------------------------------------------------


def test_mu_is_absent_from_the_a5_parameter_list() -> None:
    """A42. Putting `mu` in `MilpInputs` would falsify three separate guarantees at once:
    A.5's pinned parameter list, M3's 0%-invented claim, and Section 3.3's profile contents."""
    assert "mu_m" not in MilpInputs.A5_PARAMETERS
    assert "mu" not in MilpInputs.A5_PARAMETERS


def test_mu_is_not_reachable_from_the_profile_layer() -> None:
    """It is an argument to the solver, exactly like `B_g` (A43) and `tau_{w,cost}` (Q23)."""
    import ast
    import pathlib

    profiles = pathlib.Path(__file__).resolve().parent.parent / "optimization" / "profiles"
    for path in profiles.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "milp.mu" not in node.module, f"{path.name} imports the mu coordinate"


# ---------------------------------------------------------------------------------------------
# Direction and dimension
# ---------------------------------------------------------------------------------------------


def test_mu_below_one_relaxes_the_constraint() -> None:
    """`mu` multiplies the DEMAND side of eq. (3), so `mu < 1` reduces `n_m`.

    That is the right direction for a sharing gain. Getting it backwards would make
    multiplexing cost capacity, and every Table 2 comparison would come out with the wrong sign.
    """
    assert uniform_from_table_2("OSDI") < 1.0
    assert no_multiplexing().of(None) == 1.0


def test_mu_is_not_bounded_because_the_paper_does_not_bound_it() -> None:
    """Q31. Rejecting `mu > 1` would be us adding a constraint A.5 lacks, on the strength of our
    own reading of Table 2's direction. Permitted, never used in a headline."""
    assert sweep(1.5).uniform == 1.5
    with pytest.raises(ValueError):
        sweep(0.0)  # zero or negative would invert or vanish eq. (3), which is not a reading


# ---------------------------------------------------------------------------------------------
# The derivation, and the calibration it spends
# ---------------------------------------------------------------------------------------------


def test_mu_is_derived_from_table_2_not_retyped() -> None:
    """The citation travels with the number: `mu.py` imports `MULTIPLEXING_REDUCTION_PCT`
    rather than hard-coding 0.784, the same rule M4 applied to `SOLVER_TIME_LIMIT_S`."""
    for version, (gpu_pct, _e, _c) in MULTIPLEXING_REDUCTION_PCT.items():
        assert uniform_from_table_2(version) == pytest.approx(1.0 - gpu_pct / 100.0)
    assert uniform_from_table_2("OSDI") == pytest.approx(0.784)
    assert uniform_from_table_2("ARXIV") == pytest.approx(0.789)


def test_the_derivation_states_its_assumptions() -> None:
    """Three of them, and each is a place the inference could fail. A DERIVED value that did not
    name its assumptions would be an invented one with better manners."""
    assert len(DERIVATION_ASSUMPTIONS) == 3
    joined = " ".join(DERIVATION_ASSUMPTIONS).lower()
    assert "uniform" in joined
    assert "integrality" in joined


def test_the_calibration_is_marked_spent() -> None:
    """A63's circularity in new clothes.

    `mu` is fitted to Table 2's 21.6% GPU reduction, so reproducing that 21.6% is arithmetic.
    Anything that reports it as validation is reporting its own input back to itself.
    """
    choice = from_table_2()
    assert choice.calibration_is_spent
    assert "SPENT" in choice.describe()
    assert not no_multiplexing().calibration_is_spent


def test_the_out_of_sample_targets_are_mutually_inconsistent() -> None:
    """A77. If one uniform `mu` explained the gain, all three reported reductions would agree.

    They do not -- 21.6 / 20.2 / 17.4 -- so no single `mu` reproduces all three, and the spread
    measures how much of the reported benefit is NOT capacity sharing.
    """
    targets = out_of_sample_targets("OSDI")
    assert targets["gpu_pct"] != targets["energy_pct"] != targets["cost_pct"]
    assert targets["gpu_pct"] > targets["cost_pct"]


def test_both_paper_versions_are_available() -> None:
    """A47: the validation target itself is version-dependent, so both are reported."""
    assert from_table_2("OSDI").uniform != from_table_2("ARXIV").uniform


# ---------------------------------------------------------------------------------------------
# Provenance governs reachability
# ---------------------------------------------------------------------------------------------


def test_per_model_mu_is_invented_and_not_headline_safe() -> None:
    """A77: one aggregate number under-determines 20 unknowns by 17. Any per-model assignment is
    invented, and invented values are quarantined exactly as M3 quarantined tool service times."""
    assert not MuSource.INVENTED_PER_MODEL.headline_safe
    assert MuSource.DERIVED_TABLE_2.headline_safe
    assert MuSource.NONE.headline_safe
    assert MuSource.SWEEP.headline_safe


def test_every_choice_describes_its_provenance() -> None:
    for choice in (no_multiplexing(), from_table_2(), sweep(0.9)):
        assert choice.provenance
        assert choice.describe()


def test_the_sweep_brackets_the_derived_value() -> None:
    """A sensitivity band that sat entirely on one side of the point estimate would not be one."""
    derived = uniform_from_table_2("OSDI")
    assert min(DEFAULT_SWEEP) < derived < max(DEFAULT_SWEEP)


def test_no_multiplexing_is_exactly_one() -> None:
    """M4's value, and the "Mkb Opt" arm. 1 adds no information to eq. (3)."""
    assert mu_mod.NO_MULT == 1.0
    assert no_multiplexing().is_multiplexing is False
    assert from_table_2().is_multiplexing is True
