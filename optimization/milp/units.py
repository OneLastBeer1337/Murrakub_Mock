"""
Unit conversions -- **[OURS]**, and the one place a silent bug would be fatal.

A.5 states no units for anything. Its parameters arrive in five different time bases, and eq. (3)
is a rate inequality while eqs. (11)/(12) integrate over an epoch:

    lambda    requests / MINUTE          (Figure 19's axis, p.587)
    theta_m   tokens / SECOND            (A.5's own gloss)
    t_c       tokens / request
    l_*       SECONDS
    e_m       kWh / GPU-HOUR             (Table 3 is an MWh total over a 24h trace)
    c_g       $ / GPU-SECOND             (M3, from the Azure list price / 8 GPUs / 3600 s)

Mix two of those and eq. (3) is wrong by a factor of 60 -- which would look entirely plausible in
the output, because every GPU count would simply be 60x too small and still be a positive integer.
That is the failure mode this module exists to make impossible.

THE RULE (DESIGN.md Section 3.4): convert everything to SI-per-second ONCE, at the boundary in
`sets.py`, and carry every converted number in a `Quantity` whose arithmetic checks units. Nothing
downstream of the boundary sees a bare float.

`Quantity` is deliberately minimal -- this is not a units library. It tracks a dimension string,
refuses to add unlike dimensions, and composes them on multiply/divide. That is enough to catch
the class of error above, and small enough that it cannot itself be the bug.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from optimization.profiles.sources.tables import OPTIMIZATION_EPOCH_MINUTES

SECONDS_PER_MINUTE: Final[int] = 60
SECONDS_PER_HOUR: Final[int] = 3600

EPOCH_SECONDS: Final[int] = OPTIMIZATION_EPOCH_MINUTES * SECONDS_PER_MINUTE
"""One optimization epoch in seconds.

Section 3.4 (p.575) runs the optimizer "every 60 minutes". Imported from `sources/tables.py`
rather than retyped, so the citation travels with the number.
"""


class UnitError(Exception):
    """Two quantities were combined in a way their dimensions do not permit."""


@dataclass(frozen=True)
class Quantity:
    """A number that knows what it is.

    `dim` is a free-form dimension string in a normalised form -- `"tokens/s"`, `"$"`, `"kWh"`,
    `"req/s"`, `"1"` for dimensionless. Equality of dimension is string equality after
    normalisation, which is crude but total: there is no clever inference to get subtly wrong.
    """

    value: float
    dim: str

    def __post_init__(self) -> None:
        if not self.dim:
            raise UnitError("a quantity must state its dimension ('1' for dimensionless)")

    # -- arithmetic ----------------------------------------------------------------------

    def __add__(self, other: "Quantity") -> "Quantity":
        self._same(other, "add")
        return Quantity(self.value + other.value, self.dim)

    def __sub__(self, other: "Quantity") -> "Quantity":
        self._same(other, "subtract")
        return Quantity(self.value - other.value, self.dim)

    def __mul__(self, other: "Quantity | float | int") -> "Quantity":
        if isinstance(other, (int, float)):
            return Quantity(self.value * other, self.dim)
        return Quantity(self.value * other.value, _compose(self.dim, other.dim, "*"))

    __rmul__ = __mul__

    def __truediv__(self, other: "Quantity | float | int") -> "Quantity":
        if isinstance(other, (int, float)):
            return Quantity(self.value / other, self.dim)
        return Quantity(self.value / other.value, _compose(self.dim, other.dim, "/"))

    def _same(self, other: "Quantity", op: str) -> None:
        if self.dim != other.dim:
            raise UnitError(f"cannot {op} {self.dim!r} and {other.dim!r}")

    def __lt__(self, other: "Quantity") -> bool:
        self._same(other, "compare")
        return self.value < other.value

    def __le__(self, other: "Quantity") -> bool:
        self._same(other, "compare")
        return self.value <= other.value

    def __str__(self) -> str:
        return f"{self.value:g} {self.dim}"


def _compose(a: str, b: str, op: str) -> str:
    """Dimension algebra, reduced to cancelling one matching denominator.

    Deliberately weak. It handles the six products and quotients A.5 actually forms and nothing
    else; anything it cannot reduce it records verbatim (`"a*b"`), which still compares unequal to
    the wrong thing and so still fails loudly. A fuller implementation would be more code with
    more places to hide a mistake, for no gain on ten equations.
    """
    an, ad = _split(a)
    bn, bd = _split(b)
    if op == "*":
        num, den = an + bn, ad + bd
    else:
        num, den = an + bd, ad + bn
    for term in list(num):
        if term in den:
            num.remove(term)
            den.remove(term)
    return _join(num, den)


def _split(dim: str) -> tuple[list[str], list[str]]:
    if dim == "1":
        return [], []
    num, _, den = dim.partition("/")
    return (
        [t for t in num.split("*") if t and t != "1"],
        [t for t in den.split("*") if t and t != "1"],
    )


def _join(num: list[str], den: list[str]) -> str:
    n = "*".join(sorted(num)) or "1"
    d = "*".join(sorted(den))
    return f"{n}/{d}" if d else n


# ---------------------------------------------------------------------------------------------
# The conversions -- one line each, as DESIGN.md Section 3.4 requires
# ---------------------------------------------------------------------------------------------


def requests_per_second(lambda_per_minute: float) -> Quantity:
    """`lambda` arrives per MINUTE (Figure 19's y-axis, "Load (req/min)")."""
    return Quantity(lambda_per_minute / SECONDS_PER_MINUTE, "req/s")


def tokens_per_request(t_c: float) -> Quantity:
    return Quantity(t_c, "tokens/req")


def tokens_per_second(theta_m: float) -> Quantity:
    return Quantity(theta_m, "tokens/s")


def seconds(latency: float) -> Quantity:
    return Quantity(latency, "s")


def kwh_per_gpu_second(e_m_per_gpu_hour: float) -> Quantity:
    """`e_m` is a per-GPU-HOUR energy; eq. (11) is evaluated over one epoch."""
    return Quantity(e_m_per_gpu_hour / SECONDS_PER_HOUR, "kWh/s")


def dollars_per_gpu_second(c_g: float) -> Quantity:
    """Already per GPU-second from M3 (A57: `c_g` is per GPU despite its gloss)."""
    return Quantity(c_g, "$/s")


def over_epoch(rate: Quantity) -> Quantity:
    """Integrate a per-second rate over one optimization epoch.

    This is what turns eq. (11)'s `kWh/s` into `kWh` and eq. (12)'s `$/s` into `$`. A.5 never
    says the objectives are epoch totals rather than rates, but Section 3.4's hourly cadence and
    Figure 18's "Energy (MWh)" / "Cost (x1000 $)" axes over a 24-hour trace leave no other
    consistent reading. **[OURS]**, and flagged in every result.

    The epoch is multiplied in as a `Quantity` with dimension `s`, NOT as a bare scalar -- a
    scalar leaves the `/s` uncancelled and returns `kWh/s` where `kWh` was intended, which is the
    exact silent-factor class of error this module exists to prevent.
    """
    return rate * Quantity(float(EPOCH_SECONDS), "s")


__all__ = [
    "EPOCH_SECONDS",
    "Quantity",
    "SECONDS_PER_HOUR",
    "SECONDS_PER_MINUTE",
    "UnitError",
    "dollars_per_gpu_second",
    "kwh_per_gpu_second",
    "over_epoch",
    "requests_per_second",
    "seconds",
    "tokens_per_request",
    "tokens_per_second",
]
