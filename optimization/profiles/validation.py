"""
The three cross-checks of DESIGN.md Section 10, item 5 -- the evidence that the digitization is
sound rather than merely careful.

Each one has the same shape, and it is the shape that makes them worth anything: the paper
reports a quantity in TWO independent places, we digitize one and compare against the other. A
digitization that agrees with a number it never saw is evidence; one tuned until it agreed is
not.

  * Section 5.2 -- Figure 2c's accuracy bars vs Figure 8a's printed tier labels, joined through
    Table 6's chosen configurations.
  * Section 6.2 -- Tables 5/6's `(TPS, TPOT)` cells vs Figure 3's plotted curves. The tables are
    SAMPLES OF THE FIGURE, so each of the 12 tuples validates the curve at one point.
  * Section 7.3 -- the tier rule of Section 3.4 recomputed over our population vs the printed
    labels. Computed in `slo_tiers.py` and surfaced here for the ledger.

A NOTE ON INDEPENDENCE, which is the whole value of these checks (A63). The Section 5.2 check and
the Section 7.3 reconstruction consume the SAME `a_c` population. They stay independent only
because `a_c` is digitized from Figure 2c and never from the printed labels. DESIGN.md Section
5.2 proposes promoting four `a_c` values to the printed label VALUES; doing that would feed the
labels into the population the reconstruction derives labels from, and both checks would become
partly self-fulfilling. Left unimplemented pending review -- see PROGRESS.md A63.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from optimization.profiles.model_profiles import build_model_profiles
from optimization.profiles.provenance import Measured, Unavailable
from optimization.profiles.schema import ModelProfileKey
from optimization.profiles.sources.figure_labels import TIER_LABELS
from optimization.profiles.sources.tables import TABLE_5_OSDI, TABLE_6_OSDI
from optimization.profiles.workflow_profiles import build_code_generation_profiles

FIGURE_3_TOLERANCE_FRAC = 0.20
"""Agreement band for the Section 6.2 check, as a FRACTION of the tabled TPOT.

20% is wide, deliberately. Figure 3's y-axis is logarithmic and the panels carry eight series
each, so a pixel-level read near a crossing point carries real error. The check is asked to
answer "is the table a point on this curve?", not "what is TPOT to three digits" -- the table
already answers the latter exactly, which is why `theta_m` and `l^TPOT_m` take the CELL and not
the curve.
"""

TIER_LABEL_TOLERANCE_PP = 1.0
"""Agreement band for the Section 5.2 check, in percentage points.

Figure 2c's bars digitize to +/-0.5 pp. The tier label is exact typeset text. But the two
quantities are not the same thing for three of the four tiers -- see `AccuracyCrossCheck` -- so
1.0 pp allows for the threshold sitting below the chosen configuration's accuracy.
"""


@dataclass(frozen=True)
class CurveCheck:
    """One Table 5/6 cell compared against the Figure 3 curve it should lie on."""

    key: ModelProfileKey
    table_tps: float
    table_tpot: float
    curve_tps: float
    curve_tpot: float
    origin: str

    @property
    def residual_frac(self) -> float:
        return abs(self.curve_tpot - self.table_tpot) / self.table_tpot

    @property
    def agrees(self) -> bool:
        return self.residual_frac <= FIGURE_3_TOLERANCE_FRAC


def _interpolate_tpot(curve, tps: float) -> tuple[float, float] | None:
    """TPOT read off the digitized curve at throughput `tps`, plus the nearest plotted x.

    Linear between bracketing markers. Returns `None` when the table point lies outside the
    digitized sweep -- that is a real limitation of the reading, not a failure, and the caller
    reports it as uncheckable rather than as disagreement.
    """
    points = sorted(
        (float(p.throughput.value), float(p.tpot_p90.value))
        for p in curve
        if isinstance(p.throughput, Measured)
        and isinstance(p.tpot_p90, Measured)
        and p.origin.startswith("Figure")
    )
    if len(points) < 2:
        return None
    if tps < points[0][0] or tps > points[-1][0]:
        return None
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= tps <= x1:
            if x1 == x0:
                return y0, x0
            frac = (tps - x0) / (x1 - x0)
            return y0 + frac * (y1 - y0), x0 if frac < 0.5 else x1
    return None


def figure3_vs_tables() -> tuple[CurveCheck, ...]:
    """Section 6.2, point 2: the tables validate the Figure 3 digitization at 12 points.

    DESIGN.md's worked example claims DeepSeek-Qwen-32B/A100/TP=4's tabled `(653, 0.0767)` lands
    on the orange-circle curve and its H100 row's `(1390, 0.0387)` lands on the blue one. This
    computes that claim for every tabled tuple instead of the two spot-checks.
    """
    models = build_model_profiles()
    out: list[CurveCheck] = []
    seen: set[tuple[str, str, int, float]] = set()
    for row in TABLE_6_OSDI + TABLE_5_OSDI:
        ident = (row.model, row.gpu, row.tp, row.tps)
        if ident in seen:
            continue
        seen.add(ident)
        key = ModelProfileKey(row.model, row.gpu, row.tp)
        mp = models.get(key)
        if mp is None:
            continue
        got = _interpolate_tpot(mp.curve, float(row.tps))
        if got is None:
            continue
        tpot, near = got
        out.append(
            CurveCheck(
                key=key,
                table_tps=float(row.tps),
                table_tpot=float(row.tpot_s),
                curve_tps=near,
                curve_tpot=tpot,
                origin=f"Table {'6' if row in TABLE_6_OSDI else '5'}",
            )
        )
    return tuple(out)


@dataclass(frozen=True)
class AccuracyCrossCheck:
    """One printed Code Gen tier label vs the digitized accuracy of the configuration Table 6
    reports as chosen at that tier.

    THE TWO ARE NOT THE SAME QUANTITY, except at `best`. Section 3.4 (p.575) defines a tier as a
    PERCENTILE of the population ("the best, 95th, 80th, and 50th percentile values"), while
    Table 6 names the configuration the optimizer PICKED at that tier -- which must clear the
    threshold, not equal it. At `best` the threshold IS the population maximum, so equality is
    exact there and an inequality (`digitized >= printed`) is what the other three assert.
    """

    tier: str
    model: str
    debaters: int
    rounds: int
    printed_pct: float
    digitized_pct: float

    @property
    def residual_pp(self) -> float:
        return self.digitized_pct - self.printed_pct

    @property
    def agrees(self) -> bool:
        if self.tier == "best":
            return abs(self.residual_pp) <= TIER_LABEL_TOLERANCE_PP
        return self.residual_pp >= -TIER_LABEL_TOLERANCE_PP


def figure2c_vs_tier_labels() -> tuple[AccuracyCrossCheck, ...]:
    """Section 5.2: bars, tier labels and the chosen-configuration table are mutually consistent.

    Three independent parts of the paper have to line up -- Figure 2c's bar (digitized), Figure
    8a's printed threshold (typeset), and Table 6's row saying which configuration was chosen at
    that tier (typeset). Nothing in our pipeline forces them to.
    """
    profiles = build_code_generation_profiles()
    by_config = {
        (k.knob["model"], k.knob["D"], k.knob["R"]): wp
        for k, wp in profiles.items()
    }
    labels = TIER_LABELS[("code_generation", "accuracy")]

    out: list[AccuracyCrossCheck] = []
    for row in TABLE_6_OSDI:
        if row.slo != "accuracy" or row.objective != "cost":
            continue
        wp = by_config.get((row.model, row.debaters, row.rounds))
        if wp is None or isinstance(wp.accuracy, Unavailable):
            continue
        out.append(
            AccuracyCrossCheck(
                tier=row.tier,
                model=row.model,
                debaters=row.debaters,
                rounds=row.rounds,
                printed_pct=labels[row.tier],
                digitized_pct=float(wp.accuracy.value),
            )
        )
    return tuple(out)


def summary() -> Mapping[str, Mapping[str, float]]:
    """Both checks reduced to the numbers the ledger prints."""
    curves = figure3_vs_tables()
    accuracy = figure2c_vs_tier_labels()
    return {
        "figure_3_vs_tables": {
            "points": float(len(curves)),
            "agreeing": float(sum(1 for c in curves if c.agrees)),
            "worst_residual_frac": max((c.residual_frac for c in curves), default=0.0),
            "tolerance_frac": FIGURE_3_TOLERANCE_FRAC,
        },
        "figure_2c_vs_tier_labels": {
            "points": float(len(accuracy)),
            "agreeing": float(sum(1 for a in accuracy if a.agrees)),
            "worst_residual_pp": max((abs(a.residual_pp) for a in accuracy), default=0.0),
            "tolerance_pp": TIER_LABEL_TOLERANCE_PP,
        },
    }


__all__ = [
    "AccuracyCrossCheck",
    "CurveCheck",
    "FIGURE_3_TOLERANCE_FRAC",
    "TIER_LABEL_TOLERANCE_PP",
    "figure2c_vs_tier_labels",
    "figure3_vs_tables",
    "summary",
]
