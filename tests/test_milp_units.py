"""
Units -- DESIGN.md Section 3.4, "the one place a silent bug would be fatal".

That description was earned during the build. `sets.demand()` originally divided arrival rates by
60 to convert Figure 19's req/min axis, not realising M3's `arrivals.py` had already done it. The
result was a 60x under-statement of demand that produced 1-2 GPUs instead of ~70 -- a small
positive integer, entirely plausible, flagged by nothing. These tests exist so that class of error
fails loudly instead.
"""

from __future__ import annotations

import pytest

from optimization.milp.units import (
    EPOCH_SECONDS,
    Quantity,
    UnitError,
    dollars_per_gpu_second,
    kwh_per_gpu_second,
    over_epoch,
    requests_per_second,
    seconds,
    tokens_per_request,
    tokens_per_second,
)
from optimization.milp.sets import demand
from optimization.profiles.profile_sets import baseline
from optimization.profiles.schema import SloMix


def test_capacity_constraint_reduces_to_tokens_per_second() -> None:
    """eq. (3): `x^peak * t_c` on the left, `n_m * theta_m` on the right.

    req/s x tokens/req must cancel to tokens/s, matching the right-hand side. If it does not,
    the capacity constraint is comparing unlike things and every GPU count is wrong by whatever
    factor the mismatch implies.
    """
    lhs = requests_per_second(3000) * tokens_per_request(1000)
    rhs = tokens_per_second(653) * 3
    assert lhs.dim == "tokens/s"
    assert rhs.dim == "tokens/s"
    assert (lhs <= rhs) in (True, False)  # comparable at all


def test_energy_objective_reduces_to_kwh_over_one_epoch() -> None:
    """eq. (11) integrated over the 60-minute epoch, matching Figure 18a's MWh axis."""
    rate = kwh_per_gpu_second(0.4) * 8 * 3
    assert rate.dim == "kWh/s"
    assert over_epoch(rate).dim == "kWh"


def test_cost_objective_reduces_to_dollars_over_one_epoch() -> None:
    """eq. (12), matching Figure 18a's "Cost (x1000 $)" axis."""
    rate = dollars_per_gpu_second(0.00094) * 8 * 3
    assert rate.dim == "$/s"
    assert over_epoch(rate).dim == "$"


def test_over_epoch_multiplies_by_a_quantity_not_a_scalar() -> None:
    """The specific bug this function had once.

    Multiplying by a bare `EPOCH_SECONDS` leaves the `/s` uncancelled and silently returns
    `kWh/s` where `kWh` was meant -- numerically 3600x wrong, dimensionally undetectable unless
    the epoch itself carries a dimension.
    """
    assert over_epoch(Quantity(1.0, "kWh/s")).dim == "kWh"
    assert over_epoch(Quantity(1.0, "kWh/s")).value == EPOCH_SECONDS


def test_adding_unlike_dimensions_raises() -> None:
    with pytest.raises(UnitError):
        seconds(1.0) + tokens_per_second(1.0)


def test_comparing_unlike_dimensions_raises() -> None:
    with pytest.raises(UnitError):
        _ = seconds(1.0) < tokens_per_request(1.0)


def test_a_quantity_must_state_a_dimension() -> None:
    with pytest.raises(UnitError):
        Quantity(1.0, "")


def test_arrival_rate_is_read_not_assumed() -> None:
    """THE REGRESSION TEST FOR THE FACTOR-60 BUG.

    M3 delivers `lambda` already converted, tagged `req/s`. `demand()` must read that tag rather
    than re-applying Figure 19's req/min conversion. The magnitude check is the real assertion:
    Figure 19's chat trace runs at thousands of requests per MINUTE, so tens per second. A value
    near 1 req/s means the conversion was applied twice.
    """
    inputs = baseline(SloMix.section_4_2("accuracy", "good")).to_milp_inputs()
    peak, avg = demand(inputs, "video_qa", ("accuracy", "good"), 0)
    assert peak.dim == "req/s" and avg.dim == "req/s"
    assert 10.0 < peak.value < 200.0, (
        f"peak arrival rate {peak.value:.3f} req/s is implausible for Figure 19's trace "
        "(thousands of req/min); suspect a double unit conversion"
    )
    assert avg.value <= peak.value


def test_demand_refuses_an_unrecognised_unit() -> None:
    """Guessing here would scale every GPU count in the milestone."""
    from optimization.milp.sets import _as_req_per_second

    class Bogus:
        unit = "furlongs/fortnight"
        value = 1.0

    with pytest.raises(UnitError, match="Refusing to guess"):
        _as_req_per_second(Bogus())


def test_epoch_is_the_papers_sixty_minutes() -> None:
    """Section 3.4 (p.575): the optimizer runs "every 60 minutes". Imported, not retyped."""
    assert EPOCH_SECONDS == 3600
