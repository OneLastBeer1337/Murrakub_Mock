"""
`mu_m` -- the multiplexing factor, and the record of what it is and is not.

Appendix A.5, eq. (3), p.587:

    mu_m * sum_{w,s,c} x^peak_{w,s,c,m} * t_c  <=  n_m * theta_m,   for all m in M
    "where mu_m is the model-specific multiplexing factor."

**THAT SENTENCE IS THE PAPER'S COMPLETE DEFINITION.** No value, no bound, no units, no estimation
method, in either version. It is absent from Section 3.3's list of what a profile contains (A42),
so it cannot be smuggled into `MilpInputs` -- M3 guarantees 0% invented values in any
`ProfileSet`, and `test_a5_parameter_list_is_pinned` fixes the parameter list. `mu` is an argument
to the solver, exactly like the budgets (A43, Q23).

This module holds no solver logic. It mirrors M4 putting `A5.py` first and M3 putting
`provenance.py` first: the record of what `mu_m` is must exist before any code multiplies by it.

DIMENSIONS AND DIRECTION. `mu_m` is dimensionless -- eq. (3)'s left side is already tokens/s. It
multiplies the DEMAND side, so `mu < 1` RELAXES the constraint and REDUCES `n_m`. That is the
right direction for a "multiplexing gain": sharing an instance between workflows should let fewer
instances carry the same load. `mu > 1` would mean sharing costs capacity. The paper bounds
neither, so neither does this module (Q31) -- adding a bound A.5 lacks would be us constraining an
unbounded symbol on the strength of our own reading.

A78 -- THE CENTRAL FINDING, AND IT IS ABOUT THE SYMBOL ITSELF. Statistical multiplexing gain
depends on how many independent streams share an instance and how bursty they are. Those are
properties of the ASSIGNMENT (`x`), not of the model. A.5 makes `mu` a parameter of `m` alone, so
the gain is EXOGENOUS: the optimizer is told the answer rather than deriving it from the sharing
it chooses. Worse, `mu_m * sum(...) <= n_m * theta_m` is algebraically identical to
`sum(...) <= n_m * (theta_m / mu_m)`, so scaling `mu` is indistinguishable from scaling `theta_m`.
Multiplexing, in A.5, is a throughput bonus wearing a different name. Reproduced exactly; measured
in M5, never repaired.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, Mapping

from optimization.profiles.schema import ModelProfileKey
from optimization.profiles.sources.tables import MULTIPLEXING_REDUCTION_PCT

NO_MULT: Final[float] = 1.0
"""M4's value. Adds no information: eq. (3) reads "peak token demand must fit in provisioned
throughput", which is the constraint's evident intent. This is the **Mkb Opt** arm."""


class MuSource(Enum):
    """How a `mu` value was obtained. Governs whether it may reach a headline number."""

    NONE = "no_multiplexing"
    DERIVED_TABLE_2 = "derived_from_table_2"
    SWEEP = "ours_sweep"
    INVENTED_PER_MODEL = "invented_per_model"

    @property
    def headline_safe(self) -> bool:
        """`PER_MODEL` values are invented and quarantined to `critique/` (test-enforced)."""
        return self is not MuSource.INVENTED_PER_MODEL


# ---------------------------------------------------------------------------------------------
# The derivation -- the one place a number is produced rather than quoted
# ---------------------------------------------------------------------------------------------

DERIVATION_ASSUMPTIONS: Final[tuple[str, ...]] = (
    "A1: mu is UNIFORM across models. A.5 writes mu_m, per model, but Table 2 reports one "
    "aggregate reduction, which under-determines 20 unknowns by 17 (A77). A uniform value is the "
    "only reading the published data supports.",
    "A2: the reported GPU reduction is attributable ENTIRELY to mu. Section 4.5 predicts that "
    "joint solving with mu=1 saves only integrality rounding, so this is close to true by "
    "construction -- but it is an assumption, not a measurement, and M5 tests it.",
    "A3: n_m scales inversely with mu. Exact in the LP relaxation (eq. 3 is the only constraint "
    "coupling mu to n_m); approximate under integrality, which is why the reproduced reduction "
    "will not land exactly on 21.6%.",
)


def uniform_from_table_2(version: str = "OSDI") -> float:
    """`mu` inferred from Table 2's reported GPU reduction. **DERIVED**, not invented.

    Table 2 reports that multiplexing cuts GPUs by 21.6% [OSDI] / 21.1% [ARXIV]. Under the three
    assumptions above, `n_m` scales with `mu`, so a 21.6% reduction implies `mu = 1 - 0.216`.

    THE CALIBRATION IS SPENT (A63's circularity in new clothes). Once `mu` is fitted to Table 2's
    GPU reduction, reproducing that same 21.6% is arithmetic, not validation -- the number was put
    in by hand. It must never be quoted as evidence the reproduction works. The energy and cost
    reductions (20.2% and 17.4%) were NOT used to fit `mu`, so they remain weak out-of-sample
    checks; A77 records that they are mutually inconsistent with any single uniform `mu`, which
    is itself the finding.
    """
    if version not in MULTIPLEXING_REDUCTION_PCT:
        raise KeyError(f"{version!r}: expected one of {sorted(MULTIPLEXING_REDUCTION_PCT)}")
    gpu_reduction_pct, _energy, _cost = MULTIPLEXING_REDUCTION_PCT[version]
    return 1.0 - gpu_reduction_pct / 100.0


def out_of_sample_targets(version: str = "OSDI") -> Mapping[str, float]:
    """Energy and cost reductions, which were NOT used to fit `mu`.

    A77: if a single uniform `mu` explained everything, all three percentages would coincide.
    They do not -- 21.6 / 20.2 / 17.4 -- so no uniform `mu` reproduces all three, and the spread
    is a measurement of how much of the reported gain is NOT capacity sharing.
    """
    gpu, energy, cost = MULTIPLEXING_REDUCTION_PCT[version]
    return {"gpu_pct": gpu, "energy_pct": energy, "cost_pct": cost}


# ---------------------------------------------------------------------------------------------
# The coordinate
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class MuChoice:
    """`mu_m`, stated explicitly. Required by `solve_joint()`; there is no default.

    Follows A43's precedent for `B_g` and Q23's for `tau_{w,cost}`: a quantity the paper requires
    and never reports must be injected by a caller who names it, never defaulted into.
    """

    name: str
    source: MuSource
    uniform: float | None = None
    per_model: Mapping[ModelProfileKey, float] | None = None
    version: str = ""
    provenance: str = ""

    def of(self, m: ModelProfileKey) -> float:
        if self.per_model is not None:
            return self.per_model.get(m, NO_MULT)
        return NO_MULT if self.uniform is None else self.uniform

    @property
    def is_multiplexing(self) -> bool:
        """Whether this choice actually multiplexes. `mu == 1` is the Mkb Opt arm."""
        return self.source is not MuSource.NONE

    @property
    def calibration_is_spent(self) -> bool:
        """True when `mu` was fitted to a number that must therefore not be used as validation."""
        return self.source is MuSource.DERIVED_TABLE_2

    def describe(self) -> str:
        if self.source is MuSource.NONE:
            return "mu = 1 (no multiplexing) -- the 'Mkb Opt' arm"
        if self.source is MuSource.DERIVED_TABLE_2:
            return (
                f"mu = {self.uniform:.4f} uniform, DERIVED from Table 2 [{self.version}]'s "
                f"{100 * (1 - self.uniform):.1f}% GPU reduction. CALIBRATION SPENT: reproducing "
                "that reduction is arithmetic, not validation"
            )
        if self.source is MuSource.SWEEP:
            return f"mu = {self.uniform:.4f} uniform [OURS] -- sensitivity sweep point"
        return f"mu per model [INVENTED] -- quarantined, never a headline number"


def no_multiplexing() -> MuChoice:
    """The **Mkb Opt** arm."""
    return MuChoice(
        name="mu=1",
        source=MuSource.NONE,
        uniform=NO_MULT,
        provenance="A.5 with mu_m = 1; adds no information (M4's default)",
    )


def from_table_2(version: str = "OSDI") -> MuChoice:
    """The **Mkb Opt+Mult** arm. DERIVED, with its calibration stamped."""
    value = uniform_from_table_2(version)
    return MuChoice(
        name=f"mu_table2[{version}]",
        source=MuSource.DERIVED_TABLE_2,
        uniform=value,
        version=version,
        provenance=(
            f"DERIVED from Table 2 [{version}] GPU reduction "
            f"{MULTIPLEXING_REDUCTION_PCT[version][0]}% under 3 stated assumptions; "
            "calibration is SPENT and may not be quoted as validation"
        ),
    )


def sweep(value: float) -> MuChoice:
    """**[OURS]** sensitivity point. No claim of paper fidelity.

    `mu > 1` is permitted (Q31): A.5 places no bound on `mu_m`, and refusing one would be adding
    a constraint the paper does not have on the strength of our own reading of Table 2.
    """
    if value <= 0:
        raise ValueError("mu must be positive; eq. (3) would otherwise invert or vanish")
    return MuChoice(
        name=f"mu={value:g}",
        source=MuSource.SWEEP,
        uniform=float(value),
        provenance="[OURS] sensitivity sweep; A.5 bounds mu_m nowhere, so mu>1 is permitted",
    )


DEFAULT_SWEEP: Final[tuple[float, ...]] = (0.6, 0.7, 0.8, 0.9, 1.0)
"""The sensitivity band. Brackets the Table 2-derived 0.784 on both sides."""


__all__ = [
    "DEFAULT_SWEEP",
    "DERIVATION_ASSUMPTIONS",
    "MuChoice",
    "MuSource",
    "NO_MULT",
    "from_table_2",
    "no_multiplexing",
    "out_of_sample_targets",
    "sweep",
    "uniform_from_table_2",
]
