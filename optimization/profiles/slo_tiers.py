"""
`tau_{w,s}` -- SLO thresholds, which Section 3.4 DERIVES from the profiles rather than states.

Section 3.4 (p.575), verbatim and identical in both versions:

    "We assign four SLO tiers for quality and end-to-end latency: best, good, fair, and basic.
     The SLO tiers correspond to the best, 95th, 80th, and 50th percentile values of accuracy
     and latency available among the set of all workflow, model, and hardware configurations."

Three words in that sentence decide the whole implementation:

  "best"          -> the MAXIMUM, not the 99th percentile.
  "and hardware"  -> the population spans (configuration x model x hardware) pairs. Empirically
                     this makes NO difference to the accuracy tiers (see `reconstruct`), which is
                     a robustness result, not a licence to drop it.
  "available      -> THE PERCENTILE CONVENTION IS `lower`. With a discrete configuration set, an
   among the set"    interpolated percentile is a value no configuration achieves; the platform
                     would be advertising an SLO tier that nothing in its own catalogue can meet.
                     The tier must be a MEMBER of the population. See `_lower` / `_higher`.

`tau` IS AN OUTPUT OF PROFILING, NOT AN INPUT TO IT. A `ProfileSet` is not complete until its own
tiers have been computed from itself, so construction is two-pass and nothing may read a tier
value while profiles are still being assembled. A consequence worth stating because it is
counter-intuitive: adding a model, a workflow or a GPU type SHIFTS EVERY TIER, including the tiers
of a workflow that was not touched. Under Section 3.4's rule that is not a bug -- it is what the
rule says -- but it means tier values are not comparable across profile sets, and every reported
result must be tagged with the set that produced it.
"""

from __future__ import annotations

import math
from typing import Final, Iterable, Literal, Mapping, Sequence

from optimization.profiles.schema import SLO_TIERS
from optimization.profiles.sources.figure_labels import TIER_LABEL_FIGURE, TIER_LABELS

TIER_PERCENTILES: Final[Mapping[str, int | None]] = {
    "best": None,  # the extremum, not a percentile
    "good": 95,
    "fair": 80,
    "basic": 50,
}

DIGITIZATION_BAND_PP: Final[float] = 0.5
"""The band every Figure 2 accuracy reading carries (`figures_digitized.ACCURACY_BAND_PP`).
A reconstruction residual inside this band is a match; outside it is a finding."""


# ---------------------------------------------------------------------------------------------
# Percentile conventions
# ---------------------------------------------------------------------------------------------


def _lower(sorted_asc: Sequence[float], p: int) -> float:
    """Largest population member at or below the p-th percentile position.

    numpy's `interpolation="lower"`. For accuracy (higher is better) this guarantees the tier is
    achievable: at least the configurations at or above this rank satisfy `a_c >= tau`.
    """
    idx = int(math.floor(p / 100 * (len(sorted_asc) - 1)))
    return sorted_asc[max(0, min(idx, len(sorted_asc) - 1))]


def _higher(sorted_asc: Sequence[float], p: int) -> float:
    """Mirror of `_lower` for a quantity where LOWER is better (latency)."""
    idx = int(math.ceil(p / 100 * (len(sorted_asc) - 1)))
    return sorted_asc[max(0, min(idx, len(sorted_asc) - 1))]


# ---------------------------------------------------------------------------------------------
# Derivation
# ---------------------------------------------------------------------------------------------


def derive_accuracy_tiers(values: Iterable[float]) -> dict[str, float]:
    """`tau_{w, accuracy}` for the four tiers. Higher is better, so `best` = max."""
    pop = sorted(float(v) for v in values)
    if not pop:
        raise ValueError("cannot derive tiers from an empty accuracy population")
    return {
        "best": pop[-1],
        "good": _lower(pop, 95),
        "fair": _lower(pop, 80),
        "basic": _lower(pop, 50),
    }


def derive_latency_tiers(values: Iterable[float]) -> dict[str, float]:
    """`tau_{w, latency}` for the four tiers. LOWER is better, so `best` = min.

    [OURS] THE ORIENTATION FLIP (A38b). Section 3.4 applies one phrasing -- "the best, 95th,
    80th, and 50th percentile values" -- to two quantities of OPPOSITE polarity. Read literally,
    the 95th percentile of a latency population is a SLOWER latency than the 80th, which would
    make `basic` stricter than `good` and invert the whole tier ladder. We take the charitable
    reading: percentiles are counted from the good end, so `good` = p5, `fair` = p20,
    `basic` = p50. The literal reading is self-contradictory, not merely awkward.
    """
    pop = sorted(float(v) for v in values)
    if not pop:
        raise ValueError("cannot derive tiers from an empty latency population")
    return {
        "best": pop[0],
        "good": _higher(pop, 5),
        "fair": _higher(pop, 20),
        "basic": _higher(pop, 50),
    }


def derive_tiers(values: Iterable[float], slo_type: Literal["accuracy", "latency"]) -> dict[str, float]:
    if slo_type == "accuracy":
        return derive_accuracy_tiers(values)
    if slo_type == "latency":
        return derive_latency_tiers(values)
    raise ValueError(f"unknown SLO type {slo_type!r}")


# ---------------------------------------------------------------------------------------------
# Reconstruction against the paper's own printed tiers
# ---------------------------------------------------------------------------------------------


def reconstruct(
    workflow_id: str,
    slo_type: Literal["accuracy", "latency"],
    population: Iterable[float],
) -> dict[str, object]:
    """Compare derived tiers against the printed Figure 7/8 labels.

    This is the best available validation of the whole profile set: the paper prints the output
    of a rule it also states, over data it also plots, so the rule is checkable end to end.
    """
    derived = derive_tiers(population, slo_type)
    printed = TIER_LABELS[(workflow_id, slo_type)]
    residuals = {t: derived[t] - printed[t] for t in SLO_TIERS}
    return {
        "workflow": workflow_id,
        "slo_type": slo_type,
        "figure": TIER_LABEL_FIGURE[(workflow_id, slo_type)],
        "derived": derived,
        "printed": dict(printed),
        "residuals": residuals,
        "within_band": all(abs(r) <= DIGITIZATION_BAND_PP for r in residuals.values()),
        "population_size": len(list(population)) if hasattr(population, "__len__") else None,
    }


def accuracy_population(
    per_model: Mapping[str, Sequence[float]],
    hardware_tuples: Mapping[str, int] | None = None,
) -> list[float]:
    """Build the accuracy population of Section 3.4's rule.

    `hardware_tuples` applies the "and hardware configurations" expansion: each configuration's
    accuracy is repeated once per feasible (GPU, TP) tuple for its model, because `a_c` does not
    depend on hardware but the POPULATION the percentile is taken over does.

    Passing `None` gives the flat per-configuration population. Both are provided because the
    reconstruction shows they are EQUIVALENT under the `lower` convention -- which is what
    dissolves the worry (withdrawn A38) that the derivation depended on a TP-feasibility table
    the paper never states.
    """
    out: list[float] = []
    for model, values in per_model.items():
        repeat = 1 if hardware_tuples is None else hardware_tuples.get(model, 1)
        out.extend(list(values) * repeat)
    return out


__all__ = [
    "DIGITIZATION_BAND_PP",
    "TIER_PERCENTILES",
    "accuracy_population",
    "derive_accuracy_tiers",
    "derive_latency_tiers",
    "derive_tiers",
    "reconstruct",
]
