"""
Model profiles -- `theta_m`, `l^TTFT_m`, `l^TPOT_m`, `g_m`, `e_m` (Section 3.3, p.573).

The recurring hazard here is that Section 3.3 describes a profile that "spans load levels" while
Appendix A.5 (p.586) consumes scalar PARAMETERS. The load-indexed profile the paper describes
cannot enter the optimizer the paper describes, so a collapse is unavoidable -- and the tests
below exist to keep it NAMED and MEASURED rather than hidden in a constant (A37b).
"""

from __future__ import annotations

import pytest

from optimization.profiles.model_profiles import (
    ENERGY_PER_GPU,
    build_model_profiles,
    collapse_operating_points,
    table_operating_points,
)
from optimization.profiles.provenance import Measured, Provenance, Unavailable
from optimization.profiles.schema import (
    STRONGEST_FIRST,
    ModelProfileKey,
    OperatingPointPolicy,
)
from optimization.profiles.sources.tables import (
    TABLE_5_OSDI,
    TABLE_6_OSDI,
    reported_operating_points,
)


@pytest.fixture(scope="module")
def models():
    return build_model_profiles()


# ---------------------------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------------------------


def test_every_profile_has_at_least_one_load_point(models) -> None:
    for key, mp in models.items():
        assert mp.curve, f"{key}: empty curve"


def test_parallelism_equals_the_key_tp(models) -> None:
    """`g_m` is the GPU count of one instance of `m`.

    Section 3.3.1, Decision 3 (p.574): "A profile encodes a specific model, GPU type, and
    parallelism strategy, so choosing `m` implicitly fixes the hardware and parallelism degree."
    A profile whose `g_m` disagreed with its own TP degree would make eq. (7)'s
    `sum n_m * g_m <= B_g` count the wrong number of GPUs.
    """
    for key, mp in models.items():
        assert isinstance(mp.parallelism, Measured)
        assert mp.parallelism.value == key.tp, f"{key}: g_m={mp.parallelism.value} != tp={key.tp}"


def test_gpu_types_are_only_those_the_paper_runs_on(models) -> None:
    """Section 4.1 (p.575) runs on A100 and H100 VMs only."""
    assert {k.gpu for k in models} == {"A100", "H100"}


def test_energy_is_per_gpu_and_keyed_by_gpu_type_only(models) -> None:
    """A41. Figure 3's "TPS per Wh" is dimensionally undefined, so `e_m` comes from Table 3 per
    GPU TYPE. The consequence is a real limitation: objective (11) CANNOT distinguish two models
    running on the same GPU type, and that is asserted here rather than merely noted.
    """
    assert set(ENERGY_PER_GPU) == {"A100", "H100"}
    by_gpu: dict[str, set[float]] = {}
    for key, mp in models.items():
        if isinstance(mp.energy, Unavailable):
            continue
        by_gpu.setdefault(key.gpu, set()).add(round(float(mp.energy.value), 9))
    for gpu, values in by_gpu.items():
        assert len(values) == 1, f"{gpu}: e_m varies by model ({values}), which A41 says it cannot"


# ---------------------------------------------------------------------------------------------
# Table cells survive into the profiles
# ---------------------------------------------------------------------------------------------


def test_every_table_tuple_has_a_profile(models) -> None:
    """Tables 5 and 6 jointly name 12 `(model, GPU, TP)` tuples. Each must exist as an `m`."""
    for model, gpu, tp in reported_operating_points():
        assert ModelProfileKey(model, gpu, tp) in models, f"{model}/{gpu}/TP={tp} has no profile"


@pytest.mark.parametrize("row", TABLE_5_OSDI + TABLE_6_OSDI, ids=str)
def test_table_reported_policy_returns_a_cell_from_the_table(models, row) -> None:
    """Under TABLE_REPORTED, `theta_m` and `l^TPOT_m` must be cells of Tables 5/6 verbatim.

    This is the only policy with PAPER_TABLE provenance end to end, so if it ever returned an
    interpolated value the strongest evidence in the profile set would silently weaken.
    """
    key = ModelProfileKey(row.model, row.gpu, row.tp)
    mp = models[key]
    theta = mp.theta(OperatingPointPolicy.TABLE_REPORTED)
    tpot = mp.tpot(OperatingPointPolicy.TABLE_REPORTED)
    if isinstance(theta, Unavailable):
        pytest.skip(f"{key}: no throughput value")

    reported = reported_operating_points()[(row.model, row.gpu, row.tp)]
    assert float(theta.value) in {tps for tps, _tpot, _o in reported}
    if isinstance(tpot, Measured):
        assert float(tpot.value) in {t for _tps, t, _o in reported}


def test_collapsed_rows_are_recorded_where_a_tuple_has_several_operating_points(models) -> None:
    """A37b, made measurable.

    Tables 5/6 report the same `(model, GPU, TP)` at up to FOUR `(TPOT, TPS)` operating points
    -- Phi-4/H100/TP=1 at (0.0373, 757), (0.0165, 248), (0.0253, 552), (0.0372, 755). A.5 has
    one `theta_m` per `m`, so three of those four are DISCARDED. Expanding `M` would repair the
    formulation, which the standing policy forbids, so the loss is recorded instead.
    """
    distinct = {
        k: {(tps, tpot) for tps, tpot, _ in v} for k, v in reported_operating_points().items()
    }
    assert len(distinct[("Phi-4", "H100", 1)]) == 4

    lossy = {k: v for k, v in distinct.items() if len(v) > 1}
    lossless = {k: v for k, v in distinct.items() if len(v) == 1}
    assert lossy and lossless, "expected both kinds of tuple in Tables 5/6"

    for (model, gpu, tp), points in lossy.items():
        mp = models[ModelProfileKey(model, gpu, tp)]
        assert mp.collapsed_rows, f"{model}/{gpu}/TP={tp} discarded {len(points)-1} points silently"

    for (model, gpu, tp) in lossless:
        # Several table ROWS can report the SAME operating point -- Phi-4/A100/TP=2 appears twice
        # at (0.0609, 623), and NVLM-D-72B/H100/TP=8 twice at (0.0129, 84). Nothing is lost in
        # those cases, so a `collapsed_rows` entry would overstate the damage A37b does.
        mp = models[ModelProfileKey(model, gpu, tp)]
        assert not mp.collapsed_rows, f"{model}/{gpu}/TP={tp} reported a loss that did not occur"


def test_collapse_reports_the_throughput_spread() -> None:
    """The magnitude of the collapse is the point, not the fact of it.

    Llava-OneVision-7B/H100/TP=4 spans 479 -> 3271 tokens/s across Table 5's own rows, a factor
    of ~6.8. Every GPU count M4 produces moves by that factor depending on which row is chosen,
    which makes the operating-point policy the single largest sensitivity knob in the set.
    """
    points = reported_operating_points()[("Llava-OneVision-7B", "H100", 4)]
    tps = [p[0] for p in points]
    assert max(tps) / min(tps) > 5.0, f"expected a large spread, got {sorted(tps)}"
    chosen, discarded = collapse_operating_points(
        table_operating_points()[("Llava-OneVision-7B", "H100", 4)]
    )
    assert chosen is not None
    assert discarded, "a 6.8x spread must leave a record of what was discarded"
    assert any("A.5 cannot represent it" in d for d in discarded)


def test_table_operating_points_matches_the_source_tables() -> None:
    """The two source views must name the same tuples and the same cells.

    They differ deliberately in FIELD ORDER -- `tables.reported_operating_points()` yields
    `(tps, tpot, note)` and `model_profiles.table_operating_points()` yields `(tpot, tps, note)`.
    Comparing them as sets of unordered cells catches a transcription drift without pinning the
    accident of which order each caller happens to want.
    """
    mine = {k: {(tpot, tps) for tpot, tps, _ in v} for k, v in table_operating_points().items()}
    theirs = {k: {(tpot, tps) for tps, tpot, _ in v} for k, v in reported_operating_points().items()}
    assert mine == theirs


# ---------------------------------------------------------------------------------------------
# Operating-point policies
# ---------------------------------------------------------------------------------------------


def test_max_throughput_is_never_below_table_reported(models) -> None:
    """The policies are ordered by optimism, and the ordering must be real.

    MAX_THROUGHPUT takes the curve maximum, so it can only raise `theta_m` relative to a table
    cell -- which LOWERS `n_m` and therefore every cost and energy total. A violation here would
    mean the curve and the table disagree about which point is the maximum.
    """
    for key, mp in models.items():
        table = mp.theta(OperatingPointPolicy.TABLE_REPORTED)
        fastest = mp.theta(OperatingPointPolicy.MAX_THROUGHPUT)
        if isinstance(table, Unavailable) or isinstance(fastest, Unavailable):
            continue
        assert float(fastest.value) >= float(table.value) - 1e-9, key


def test_knee_lies_between_the_two_extremes(models) -> None:
    """KNEE is the engineering reading of "expose trade-offs": the last point before TPOT
    exceeds 1.5x its floor. It must not exceed the curve maximum."""
    for key, mp in models.items():
        knee = mp.theta(OperatingPointPolicy.KNEE)
        fastest = mp.theta(OperatingPointPolicy.MAX_THROUGHPUT)
        if isinstance(knee, Unavailable) or isinstance(fastest, Unavailable):
            continue
        assert float(knee.value) <= float(fastest.value) + 1e-9, key


def test_policies_are_declared_strongest_first() -> None:
    assert STRONGEST_FIRST[0] is OperatingPointPolicy.TABLE_REPORTED
    assert set(STRONGEST_FIRST) == set(OperatingPointPolicy)


@pytest.mark.parametrize("policy", list(OperatingPointPolicy), ids=lambda p: p.value)
def test_every_policy_is_evaluable_on_every_profile(models, policy) -> None:
    """A policy that raised on some `m` would make the profile set unusable at M4 without a
    special case. Absence must arrive as `Unavailable`, never as an exception."""
    for key, mp in models.items():
        for getter in (mp.theta, mp.ttft, mp.tpot):
            value = getter(policy)
            assert isinstance(value, (Measured, Unavailable)), f"{key}/{policy}: {value!r}"


def test_fallback_for_untabled_profiles_is_the_saturation_endpoint(models) -> None:
    """8 of the profiles have no Table 5/6 row. The fallback must be the curve's saturation
    endpoint, not its first point: the first point is the LOWEST offered load on the sweep, and
    using it as `theta_m` would understate capacity by up to an order of magnitude and inflate
    `n_m` by the same factor. Recorded as PAPER_FIGURE_READ so it is never mistaken for a cell.
    """
    tabled = set(reported_operating_points())
    checked = 0
    for key, mp in models.items():
        if (key.model_id, key.gpu, key.tp) in tabled:
            continue
        theta = mp.theta(OperatingPointPolicy.TABLE_REPORTED)
        if isinstance(theta, Unavailable):
            continue
        usable = [p for p in mp.curve if isinstance(p.throughput, Measured)]
        assert float(theta.value) == max(float(p.throughput.value) for p in usable), key
        assert theta.provenance is not Provenance.PAPER_TABLE, f"{key}: fallback claims a table"
        checked += 1
    assert checked, "no untabled profile was exercised"


# ---------------------------------------------------------------------------------------------
# Latency
# ---------------------------------------------------------------------------------------------


def test_ttft_and_tpot_are_positive_where_available(models) -> None:
    for key, mp in models.items():
        for name, getter in (("ttft", mp.ttft), ("tpot", mp.tpot)):
            v = getter(OperatingPointPolicy.TABLE_REPORTED)
            if isinstance(v, Unavailable):
                continue
            assert float(v.value) > 0, f"{key}: {name} = {v.value}"


def test_h100_is_not_slower_than_a100_for_the_same_model_and_tp(models) -> None:
    """A sanity check on the digitization rather than on the paper: an H100 profile reading
    slower than the matching A100 one at the same TP would indicate a panel or series mix-up in
    Figure 3, which is exactly the failure mode 8 series per panel invites.
    """
    checked = 0
    for key, mp in models.items():
        if key.gpu != "H100":
            continue
        twin = ModelProfileKey(key.model_id, "A100", key.tp)
        if twin not in models:
            continue
        h, a = mp.theta(OperatingPointPolicy.MAX_THROUGHPUT), models[twin].theta(
            OperatingPointPolicy.MAX_THROUGHPUT
        )
        if isinstance(h, Unavailable) or isinstance(a, Unavailable):
            continue
        assert float(h.value) >= float(a.value), f"{key}: H100 {h.value} < A100 {a.value}"
        checked += 1
    assert checked, "no A100/H100 twin was compared"
