"""
Model profiles: `theta_m`, `l^TTFT_m`, `l^TPOT_m`, `g_m`, `e_m` -- the workflow-independent layer.

Section 3.3 (p.573): "Model profiles capture the performance and resource characteristics of
model deployments across hardware configurations... Each profile reports: (1) latency (TTFT and
TPOT for LLMs), (2) energy consumption across hardware, and (3) cost per configuration.
Profiles span load levels to expose trade-offs and guide the optimizer in allocating load and
instances."

Section 3.3.1, Decision 3 (p.574): "A profile encodes a specific model, GPU type, and parallelism
strategy, so choosing `m` implicitly fixes the hardware and parallelism degree."

TWO SOURCES, AND THEY VALIDATE EACH OTHER. Tables 5/6 (pp.585-586) give exact `(TPOT, TPS)` cells
for chosen configurations; Figure 3 (p.570) gives the whole load curve. Interpolating the figure
at each table row's TPS reproduces that row's TPOT to a median 1.1% over 20 points -- so the
tables are samples of the figure, and `theta_m` IS the `TPS` column with `l^TPOT_m` the `TPOT`
column, with no conversion and no assumption.

WHERE THE TWO LAYERS MEET A.5:

  * `theta_m`, `l^TPOT_m` -- PAPER_TABLE where a table row exists, else PAPER_FIGURE_READ from
    the curve.
  * `l^TTFT_m` -- **PAPER_FIGURE_READ ONLY, ALWAYS** (A36). TTFT is tabulated NOWHERE in either
    version; Figure 3's middle column is the only source in the paper. Models with no Figure 3
    panel (Llava-OneVision-7B, Llama-3.2-90B -- A35) therefore have `Unavailable` TTFT, which
    blocks eq. (5) for them entirely. That is not a gap we can close; it is the paper's.
  * `g_m` = the parallelism degree. Structural, not measured.
  * `e_m` -- derived from Table 3 per GPU TYPE (Section 6.5), so objective (11) cannot
    distinguish two models on the same GPU (A41: Figure 3's "TPS per Wh" column is
    dimensionally undefined and unusable as a source).

OPERATING-POINT COLLAPSE (Q20 / A37b). Tables 5 and 6 report the SAME `(model, GPU, TP)` at up to
four different `(TPOT, TPS)` points across SLO tiers, and A.2 (p.585) says so explicitly --
Murakkab "increases the allowed load per model instance to increase batching as the SLO is
relaxed". A.5 has no variable for that choice: `theta_m` and `l^TPOT_m` are constants of `m`.
Resolved Q20: `M` is NOT re-indexed. `TABLE_REPORTED` collapses the rows to one operating point
per `m`, ties breaking toward the HIGHER `theta_m` -- deliberately toward the baseline's
advantage, so that any GPU-count gap M4 reports is a LOWER bound on Murakkab's disadvantage
rather than an artifact of our tie-break. Every collapse is recorded in
`ModelProfile.collapsed_rows` with the discarded rows and the theta ratio between them.
"""

from __future__ import annotations

from typing import Final, Mapping

from optimization.profiles.provenance import (
    Anchor,
    Citation,
    Measured,
    Provenance,
    Unavailable,
    Value,
)
from optimization.profiles.schema import LoadPoint, ModelProfile, ModelProfileKey
from optimization.profiles.sources.figure_labels import FIGURE_3_COVERAGE
from optimization.profiles.sources.figures_digitized import FIG_3_CURVES
from optimization.profiles.sources.tables import TABLE_5_OSDI, TABLE_6_OSDI

# ---------------------------------------------------------------------------------------------
# Citations
# ---------------------------------------------------------------------------------------------

FIG3 = Citation(version="BOTH", figure="3", page=570)
TABLE5 = Citation(version="BOTH", table=5, page=585)
TABLE6 = Citation(version="BOTH", table=6, page=586)
TABLE3 = Citation(version="BOTH", table=3, page=578)
SEC_4_1 = Citation(
    version="BOTH",
    section="4.1",
    page=575,
    quote=(
        "We run our experiments on A100 and H100 VMs from Microsoft Azure. Each A100 VM has "
        "8xNVIDIA A100 (80GB) GPUs and an AMD EPYC 7V12 64-Core processor, while each H100 VM "
        "has 8xNVIDIA H100 (80GB) GPUs with an Intel Xeon (Sapphire Rapids) processor."
    ),
)

FIGURE_READ_BAND = 0.03
"""Relative band on a vector-extracted Figure 3 value.

The extraction itself is exact -- marker centroids come from the PDF's own path data, so there is
no rasterization error. The band is not digitization noise; it is the agreement between the two
independent sources, i.e. the 3.6% worst-case residual between the figure curves and the table
cells (`FIG_3_VALIDATION_VS_TABLES`). Using the cross-source disagreement as the band is the
honest choice: it is larger than the measurement error and it is what a reader should assume."""


# ---------------------------------------------------------------------------------------------
# Energy -- Section 6.5, derived from Table 3
# ---------------------------------------------------------------------------------------------


def _energy_per_gpu() -> Mapping[str, Value]:
    """`e_m`, in kW per GPU, derived from Table 3's two single-GPU-type rows.

    Row 1 allocates 1,292 A100 and no H100 for 24.7 MWh over 24 h; row 6 allocates 495 H100 and
    no A100 for 11.0 MWh. Dividing gives an average per-GPU power UNDER THE ASSUMPTION THAT THE
    ALLOCATION WAS CONSTANT across the 24 h -- which Figure 11 (p.578) shows it was not, since
    Murakkab reconfigures with the diurnal load. The assumption is stated on the value rather
    than buried, and it is the same one `sources/external.py` uses for its cost cross-check.

    A.5's eq. (11) is `min SUM_m n_m * e_m * g_m`, so `e_m` is multiplied by the GPU count and is
    therefore PER GPU (A57), despite A.5 naming it "Energy consumption (kWh) for model profile m"
    -- kWh is an energy, not a power, and an instantaneous objective needs a rate.

    CONSEQUENCE, AND IT IS A REAL FIDELITY LOSS: this yields one number per GPU TYPE, not per
    model. Objective (11) therefore cannot distinguish two models running on the same GPU. The
    paper's own per-model energy column (Figure 3's "TPS per Wh") is dimensionally undefined in
    both versions and yields no plausible device power under any reading, so it cannot be used
    (A41).
    """
    from optimization.profiles.sources.tables import TABLE_3

    a100_row, h100_row = TABLE_3[0], TABLE_3[-1]
    out: dict[str, Value] = {}
    for gpu, row, count in (
        ("A100", a100_row, a100_row.allocated_a100),
        ("H100", h100_row, h100_row.allocated_h100),
    ):
        kw_per_gpu = row.energy_mwh * 1_000.0 / 24.0 / count
        mwh = Measured(
            value=row.energy_mwh,
            unit="MWh",
            provenance=Provenance.PAPER_TABLE,
            cite=TABLE3,
            note=f"Table 3 24 h energy for the {count}x{gpu} single-GPU-type allocation",
        )
        out[gpu] = Measured(
            value=kw_per_gpu,
            unit="kW/GPU",
            provenance=Provenance.DERIVED,
            cite=TABLE3,
            lo=kw_per_gpu * 0.8,
            hi=kw_per_gpu * 1.2,
            anchors=(Anchor(profile_key=f"Table3/{gpu}-only-row", field="energy_mwh", value=mwh),),
            assumption=(
                f"Table 3 row with {count} {gpu} GPUs and no other type: "
                f"{row.energy_mwh} MWh / 24 h / {count} GPUs, ASSUMING the allocation was constant "
                "over the 24 h (Figure 11 p.578 shows it was not; the band is +/-20% to cover it). "
                "Per GPU because eq. (11) multiplies e_m by g_m (A57)."
            ),
            note=(
                "One value per GPU TYPE, not per model: objective (11) cannot distinguish two "
                "models on the same GPU. Figure 3's 'TPS per Wh' column is unusable (A41)."
            ),
        )
    return out


ENERGY_PER_GPU: Final[Mapping[str, Value]] = _energy_per_gpu()


# ---------------------------------------------------------------------------------------------
# Table operating points, and the Q20 collapse
# ---------------------------------------------------------------------------------------------


def table_operating_points() -> Mapping[tuple[str, str, int], list[tuple[float, float, str]]]:
    """All `(tpot, tps, provenance-note)` rows Tables 5/6 report, keyed by `(model, gpu, tp)`."""
    out: dict[tuple[str, str, int], list[tuple[float, float, str]]] = {}
    for row in TABLE_6_OSDI:
        key = (row.model, row.gpu, row.tp)
        out.setdefault(key, []).append(
            (row.tpot_s, row.tps, f"Table 6 {row.slo}/{row.objective}/{row.tier}")
        )
    for row in TABLE_5_OSDI:
        key = (row.model, row.gpu, row.tp)
        out.setdefault(key, []).append(
            (row.tpot_s, row.tps, f"Table 5 {row.slo}/{row.objective}/{row.tier}")
        )
    return out


def collapse_operating_points(
    rows: list[tuple[float, float, str]]
) -> tuple[tuple[float, float, str], tuple[str, ...]]:
    """Q20: pick ONE operating point per `m`; return it plus a record of what was discarded.

    Rule: the point appearing in the most table rows; ties break toward the HIGHER `theta`.

    The tie-break direction is deliberate and is the opposite of flattering our own comparison.
    A LOW `theta_m` inflates `n_m`, which inflates Murakkab's GPU count, which would make our
    system look better for free. Breaking toward the higher `theta` means every GPU-count gap M4
    reports is a LOWER bound on Murakkab's disadvantage.
    """
    counts: dict[tuple[float, float], int] = {}
    for tpot, tps, _ in rows:
        counts[(tpot, tps)] = counts.get((tpot, tps), 0) + 1
    best = max(counts, key=lambda k: (counts[k], k[1]))
    chosen = next(r for r in rows if (r[0], r[1]) == best)

    discarded = []
    thetas = [tps for _tpot, tps, _n in rows]
    for tpot, tps, note in rows:
        if (tpot, tps) != best:
            discarded.append(f"{note}: TPOT={tpot} TPS={tps} (theta ratio {tps / best[1]:.2f}x)")
    if discarded:
        discarded.append(
            f"theta spread across reported points: {min(thetas):.0f}..{max(thetas):.0f} "
            f"tokens/s ({max(thetas) / max(min(thetas), 1e-9):.2f}x) -- A.5 cannot represent it"
        )
    return chosen, tuple(discarded)


# ---------------------------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------------------------


def _curve_points(model: str, gpu: str, tp: int) -> tuple[LoadPoint, ...]:
    """Figure 3's load curve for one tuple, as `LoadPoint`s.

    `ttft` is joined to `tpot` by throughput: both panels plot the same sweep against the same
    x-axis, so the i-th TPOT point and the i-th TTFT point are the same run. Where the TTFT
    series is SHORTER, the missing points are clipped above the panel's 2 s limit -- recorded as
    `Unavailable` with `blocks=("eq5",)` rather than dropped, because a censored tail is not an
    absent measurement.
    """
    series = FIG_3_CURVES.get((model, gpu, tp))
    if not series:
        return ()
    tpot_pts = list(series.get("tpot", ()))
    ttft_by_x = {round(x, 1): y for x, y in series.get("ttft", ())}

    points: list[LoadPoint] = []
    for x, tpot in tpot_pts:
        ttft_val = ttft_by_x.get(round(x, 1))
        if ttft_val is None:
            nearby = [k for k in ttft_by_x if abs(k - x) <= max(2.0, abs(x) * 0.02)]
            ttft_val = ttft_by_x[nearby[0]] if nearby else None
        if ttft_val is None:
            ttft: Value = Unavailable(
                reason=(
                    f"Figure 3 plots no TTFT point for {model}/{gpu}/TP={tp} at {x:.0f} tokens/s; "
                    "the TTFT panel's y-limit is 2 s and the saturation tail is clipped above it, "
                    "so this is right-censored, not missing"
                ),
                cite=FIG3,
                blocks=("eq5",),
            )
        else:
            ttft = Measured(
                value=ttft_val,
                unit="s",
                provenance=Provenance.PAPER_FIGURE_READ,
                cite=FIG3,
                lo=ttft_val * (1 - FIGURE_READ_BAND),
                hi=ttft_val * (1 + FIGURE_READ_BAND),
                note="TTFT is tabulated nowhere in either version (A36); Figure 3 is the only source",
            )
        points.append(
            LoadPoint(
                throughput=Measured(
                    value=x,
                    unit="tokens/s",
                    provenance=Provenance.PAPER_FIGURE_READ,
                    cite=FIG3,
                    lo=x * (1 - FIGURE_READ_BAND),
                    hi=x * (1 + FIGURE_READ_BAND),
                ),
                ttft_p90=ttft,
                tpot_p90=Measured(
                    value=tpot,
                    unit="s",
                    provenance=Provenance.PAPER_FIGURE_READ,
                    cite=FIG3,
                    lo=tpot * (1 - FIGURE_READ_BAND),
                    hi=tpot * (1 + FIGURE_READ_BAND),
                ),
                origin=f"Figure 3 {model}/{gpu}/TP={tp} vector marker @ {x:.0f} TPS",
            )
        )
    return tuple(points)


def build_model_profiles() -> dict[ModelProfileKey, ModelProfile]:
    """Every `m` in `M`, assembled from Tables 5/6 and Figure 3."""
    table_points = table_operating_points()
    profiles: dict[ModelProfileKey, ModelProfile] = {}

    keys = {
        (model, gpu, tp)
        for model, gpus in FIGURE_3_COVERAGE.items()
        for gpu, tps in gpus.items()
        for tp in tps
    } | set(table_points)

    for model, gpu, tp in sorted(keys):
        key = ModelProfileKey(model_id=model, gpu=gpu, tp=tp)
        curve = list(_curve_points(model, gpu, tp))
        collapsed: tuple[str, ...] = ()

        rows = table_points.get((model, gpu, tp))
        if rows:
            (tpot, tps, note), collapsed = collapse_operating_points(rows)
            ttft: Value = Unavailable(
                reason=(
                    f"no Figure 3 panel exists for {model} (A35); TTFT is reported in no table in "
                    "either version (A36), so eq. (5) cannot be evaluated for this profile"
                ),
                cite=FIG3,
                blocks=("eq5",),
            )
            for point in curve:
                if isinstance(point.ttft_p90, Measured):
                    ttft = point.ttft_p90
                    break
            curve.insert(
                0,
                LoadPoint(
                    throughput=Measured(tps, "tokens/s", Provenance.PAPER_TABLE, TABLE6 if any(
                        r.model == model for r in TABLE_6_OSDI
                    ) else TABLE5),
                    ttft_p90=ttft,
                    tpot_p90=Measured(tpot, "s", Provenance.PAPER_TABLE, TABLE6 if any(
                        r.model == model for r in TABLE_6_OSDI
                    ) else TABLE5),
                    origin=note,
                ),
            )

        if not curve:
            continue

        profiles[key] = ModelProfile(
            key=key,
            curve=tuple(curve),
            parallelism=Measured(
                value=tp,
                unit="gpus",
                provenance=Provenance.PAPER_TABLE if rows else Provenance.PAPER_FIGURE_LABEL,
                cite=TABLE6 if rows else FIG3,
                note="g_m = TP. Section 3.3.1 Decision 3 (p.574): choosing m fixes the hardware.",
            ),
            energy=ENERGY_PER_GPU[gpu],
            collapsed_rows=collapsed,
        )
    return profiles


__all__ = [
    "ENERGY_PER_GPU",
    "FIGURE_READ_BAND",
    "build_model_profiles",
    "collapse_operating_points",
    "table_operating_points",
]
