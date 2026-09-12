"""
The index spaces `W / S / M / C_w / G`, and the admissibility computation that realises A.5's
filters -- Appendix A.5 "Sets and Indices" (p.586), eqs. (4)/(5) and their duplicates (8)/(9).

TWO THINGS HAPPEN HERE, AND BOTH ARE LOAD-BEARING.

**1. The SLO filters are applied by NOT CREATING A VARIABLE.** A.5 writes eqs. (4) and (5) as
assignments (`x = 0 if ...`), not as inequalities, so the faithful implementation is domain
restriction rather than a big-M constraint. The model comes out smaller, there is no big-M
numerical fragility, and -- the actual point -- **the set of excluded things becomes a data
structure** with a reason attached to every element, instead of a silent zero.

**2. Exclusion-for-lack-of-data and exclusion-by-SLO-filter are kept strictly apart.** They are
completely different claims. "This configuration is too slow to meet its promise" is a result;
"the paper never reports this configuration's token count" is a hole in the evidence. Summing them
into one number would be the single most misleading thing this milestone could do, so
`ExclusionLedger` refuses to: they are separate counters with separate reason strings, and Q19
requires the data-lack set to be printed beside every headline number.

A71 -- THE CONSEQUENCE NOBODY EXPECTS. Because a missing `l^TTFT_m` only matters on a latency run,
and a missing `a_c` only matters on an accuracy run (A68), **each (w, s) is solved over a
different index space**. The eight SLO runs of Section 4.2 are therefore not strictly comparable,
and `report.py` refuses to tabulate them together without saying so.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

from optimization.milp.units import (
    UnitError,
    Quantity,
    dollars_per_gpu_second,
    kwh_per_gpu_second,
    requests_per_second,
    seconds,
    tokens_per_request,
    tokens_per_second,
)
from optimization.profiles.provenance import Measured, Unavailable
from optimization.profiles.schema import ConfigKey, MilpInputs, ModelProfileKey

#: Why an element is not in the model. NEVER conflated -- see the module docstring.
DATA_LACK = "data"
SLO_FILTER = "slo"


@dataclass(frozen=True)
class Exclusion:
    """One element that is not in the model, and why."""

    element: str
    kind: str
    """`DATA_LACK` or `SLO_FILTER`."""
    parameter: str
    reason: str
    arithmetic: str = ""
    """For SLO exclusions: the operands and the comparison, so a reviewer holding Table 5 can
    check it by eye (e.g. `0.22 + 1050 x 0.0070 = 7.57 s > tau = 0.50 s`). This is what makes
    A37 legible as a RESULT rather than as a solver status code."""


@dataclass
class ExclusionLedger:
    """Every element removed from the model, partitioned by why.

    Mutable during construction, read-only in the result. Deliberately not a `Counter`: the
    reasons are the product, not the counts.
    """

    entries: list[Exclusion] = field(default_factory=list)

    def add(self, element: str, kind: str, parameter: str, reason: str, arithmetic: str = "") -> None:
        self.entries.append(Exclusion(element, kind, parameter, reason, arithmetic))

    def of_kind(self, kind: str) -> tuple[Exclusion, ...]:
        return tuple(e for e in self.entries if e.kind == kind)

    @property
    def data_excluded(self) -> tuple[Exclusion, ...]:
        return self.of_kind(DATA_LACK)

    @property
    def slo_excluded(self) -> tuple[Exclusion, ...]:
        return self.of_kind(SLO_FILTER)

    def summary(self) -> Mapping[str, int]:
        return {
            "excluded_for_lack_of_data": len(self.data_excluded),
            "excluded_by_slo_filter": len(self.slo_excluded),
        }

    def __len__(self) -> int:
        return len(self.entries)


@dataclass(frozen=True)
class EmptyAdmissibleSet:
    """Structural infeasibility: there is nothing to solve, and we can say exactly why.

    Detected BEFORE the solver runs. Under `baseline`, latency-tier runs are predicted to land
    here (A37): Figure 7b/8b's printed thresholds are unreachable under eq. (5) using the paper's
    own Table 5 configuration. `nearest_miss` carries the arithmetic of the pair that came
    closest, which IS the A37 finding -- far more useful than a solver status code.
    """

    workflow: str
    slo: tuple[str, str]
    emptied_by: str
    nearest_miss: str
    tau: float | None
    candidates_considered: int


@dataclass(frozen=True)
class Admissible:
    """The surviving index space for one `(w, s)`, plus the record of what did not survive."""

    workflow: str
    slo: tuple[str, str]
    configs: tuple[ConfigKey, ...]
    models: tuple[ModelProfileKey, ...]
    pairs: tuple[tuple[ConfigKey, ModelProfileKey], ...]
    """The `x^peak` index space: data available AND the SLO filter passed."""

    ledger: ExclusionLedger
    empty: EmptyAdmissibleSet | None = None

    pairs_unfiltered: tuple[tuple[ConfigKey, ModelProfileKey], ...] = ()
    """The `x^avg` index space: data available, **SLO filter NOT applied**.

    This asymmetry is not an oversight, it is A66 reproduced. Eqs. (4)/(5)/(8)/(9) constrain
    `x^peak` ONLY -- verified verbatim against pp.586-587 (`A5_VERBATIM.md`). Eq. (2) sums over
    all `c in C_w, m in M` with no filter, and objective (13) maximises over `x^avg`. So average
    load is free to sit on configurations that violate the very SLO the run is named after.

    Restricting `x^avg` to `pairs` would REPAIR the formulation and erase the finding, which the
    standing policy forbids. `tests/test_milp_filters.py` asserts the two spaces differ whenever
    the filter bites.
    """


    # -- converted parameters, SI-per-second, computed once at this boundary (Section 3.4) --
    t_c: Mapping[ConfigKey, Quantity] = field(default_factory=dict)
    a_c: Mapping[ConfigKey, float] = field(default_factory=dict)
    theta_m: Mapping[ModelProfileKey, Quantity] = field(default_factory=dict)
    e_m: Mapping[ModelProfileKey, Quantity] = field(default_factory=dict)
    g_m: Mapping[ModelProfileKey, int] = field(default_factory=dict)
    c_g: Mapping[str, Quantity] = field(default_factory=dict)
    eq5_value: Mapping[tuple[ConfigKey, ModelProfileKey], float] = field(default_factory=dict)
    """eq. (5)'s left-hand side per admissible pair: `l^TTFT_m + t_c * l^TPOT_m`. Retained
    because Section 10.2's `StructuralRecord` needs it -- it is the optimizer's ENTIRE latency
    model, as one number, and the critical-path comparison is computed against it."""

    @property
    def is_empty(self) -> bool:
        return self.empty is not None


def _value(v) -> float | None:
    return None if isinstance(v, Unavailable) else float(v.value)


def _slo_type(slo: tuple[str, str]) -> str:
    return slo[0]


def build_admissible(
    inputs: MilpInputs,
    workflow: str,
    slo: tuple[str, str],
    objective_needs_energy: bool = False,
) -> Admissible:
    """Compute the admissible `(c, m)` space for one `(workflow, SLO)` run.

    Order matters and is deliberate: **data availability is checked before the SLO filter.** A
    configuration with no `t_c` is not "too slow", it is unmeasured, and testing it against a
    threshold would manufacture a verdict out of a missing number. Anything dropped for data is
    dropped first and never reaches a filter.

    `objective_needs_energy` exists because A.5 makes exclusion objective-dependent: `e_m` is
    needed by objective (11) and by nothing else, so a model with no `e_m` is admissible under
    (12) and (13) and not under (11) (A71).
    """
    ledger = ExclusionLedger()
    slo_type = _slo_type(slo)
    tau_value = _value(inputs.tau.get((workflow, slo[0], slo[1]), Unavailable(
        reason="no threshold", cite=next(iter(inputs.a_c.values())).cite
    ))) if (workflow, slo[0], slo[1]) in inputs.tau else None

    # -- configurations: data first -------------------------------------------------------
    configs: list[ConfigKey] = []
    t_c: dict[ConfigKey, Quantity] = {}
    a_c: dict[ConfigKey, float] = {}
    for c in inputs.configs_by_workflow.get(workflow, ()):
        tokens = inputs.t_c[c]
        if isinstance(tokens, Unavailable):
            ledger.add(str(c), DATA_LACK, "t_c", tokens.reason)
            continue
        acc = inputs.a_c[c]
        if isinstance(acc, Unavailable):
            if slo_type == "accuracy":
                # Only fatal where filter (4) is active. On a latency run A68 makes (4)
                # inactive, so a configuration with no accuracy is admissible -- and the run
                # then has no quality floor at all, which report.py prints.
                ledger.add(str(c), DATA_LACK, "a_c", acc.reason)
                continue
        else:
            a_c[c] = float(acc.value)
        t_c[c] = tokens_per_request(float(tokens.value))
        configs.append(c)

    # -- model profiles: data first -------------------------------------------------------
    models: list[ModelProfileKey] = []
    theta: dict[ModelProfileKey, Quantity] = {}
    energy: dict[ModelProfileKey, Quantity] = {}
    g_m: dict[ModelProfileKey, int] = {}
    ttft: dict[ModelProfileKey, float] = {}
    tpot: dict[ModelProfileKey, float] = {}
    for m in inputs.theta_m:
        th = inputs.theta_m[m]
        if isinstance(th, Unavailable):
            ledger.add(str(m), DATA_LACK, "theta_m", th.reason)
            continue
        if slo_type == "latency":
            missing = [
                name
                for name, v in (("l_ttft_m", inputs.l_ttft_m[m]), ("l_tpot_m", inputs.l_tpot_m[m]))
                if isinstance(v, Unavailable)
            ]
            if missing:
                # A62 lands here: Llava-OneVision-7B, the model Section 4.6's parallelism study
                # runs, has no TTFT anywhere in either version, so eq. (5) cannot be evaluated
                # for it at all. Excluded for lack of data, never for merit, and printed.
                v = inputs.l_ttft_m[m] if "l_ttft_m" in missing else inputs.l_tpot_m[m]
                ledger.add(str(m), DATA_LACK, missing[0], v.reason)
                continue
        if objective_needs_energy and isinstance(inputs.e_m[m], Unavailable):
            ledger.add(str(m), DATA_LACK, "e_m", inputs.e_m[m].reason)
            continue
        theta[m] = tokens_per_second(float(th.value))
        if isinstance(inputs.e_m[m], Measured):
            energy[m] = kwh_per_gpu_second(float(inputs.e_m[m].value))
        g_m[m] = int(inputs.g_m[m].value)
        if isinstance(inputs.l_ttft_m[m], Measured):
            ttft[m] = float(inputs.l_ttft_m[m].value)
        if isinstance(inputs.l_tpot_m[m], Measured):
            tpot[m] = float(inputs.l_tpot_m[m].value)
        models.append(m)

    # -- the SLO filter, eqs. (4)/(5) -- applied only on the matching dimension (A68/Q24) --
    pairs: list[tuple[ConfigKey, ModelProfileKey]] = []
    pairs_unfiltered: list[tuple[ConfigKey, ModelProfileKey]] = []
    eq5: dict[tuple[ConfigKey, ModelProfileKey], float] = {}
    nearest: tuple[float, str] | None = None
    considered = 0

    for c in configs:
        for m in models:
            considered += 1
            # `x^avg`'s space: data-available only. The SLO filter below never touches it (A66).
            pairs_unfiltered.append((c, m))
            if slo_type == "latency" and tau_value is not None:
                lhs = ttft[m] + float(t_c[c].value) * tpot[m]
                eq5[(c, m)] = lhs
                if lhs > tau_value:
                    arithmetic = (
                        f"{ttft[m]:g} + {t_c[c].value:g} x {tpot[m]:g} = {lhs:.4g} s "
                        f"> tau = {tau_value:g} s"
                    )
                    ledger.add(f"{c} on {m}", SLO_FILTER, "eq5", "latency filter", arithmetic)
                    slack = lhs - tau_value
                    if nearest is None or slack < nearest[0]:
                        nearest = (slack, arithmetic)
                    continue
            elif slo_type == "accuracy" and tau_value is not None:
                acc = a_c.get(c)
                if acc is not None and acc < tau_value:
                    arithmetic = f"a_c = {acc:g} < tau = {tau_value:g}"
                    ledger.add(f"{c} on {m}", SLO_FILTER, "eq4", "accuracy filter", arithmetic)
                    miss = tau_value - acc
                    if nearest is None or miss < nearest[0]:
                        nearest = (miss, arithmetic)
                    continue
            pairs.append((c, m))

    empty = None
    if not pairs:
        emptied_by = (
            "no configuration or model survived the data check"
            if not configs or not models
            else f"eq. ({'5' if slo_type == 'latency' else '4'}) removed every candidate"
        )
        empty = EmptyAdmissibleSet(
            workflow=workflow,
            slo=slo,
            emptied_by=emptied_by,
            nearest_miss=nearest[1] if nearest else "no candidate was evaluable",
            tau=tau_value,
            candidates_considered=considered,
        )

    return Admissible(
        workflow=workflow,
        slo=slo,
        configs=tuple(configs),
        models=tuple(models),
        pairs=tuple(pairs),
        pairs_unfiltered=tuple(pairs_unfiltered),
        ledger=ledger,
        empty=empty,
        t_c=t_c,
        a_c=a_c,
        theta_m=theta,
        e_m=energy,
        g_m=g_m,
        c_g={g: dollars_per_gpu_second(float(v.value))
             for g, v in inputs.c_g.items() if isinstance(v, Measured)},
        eq5_value=eq5,
    )


def demand(inputs: MilpInputs, workflow: str, slo: tuple[str, str], epoch: int) -> tuple[Quantity, Quantity]:
    """`lambda^peak` and `lambda^avg` for one `(w, s, epoch)`, converted to req/s.

    Figure 19's axis is "Load (req/min)", so this is the single conversion eq. (3) depends on. A
    missed factor of 60 here would scale every GPU count in the milestone and still look
    plausible (DESIGN.md Section 3.4).
    """
    key = (workflow, slo[0], slo[1], epoch)
    peak, avg = inputs.lam_peak[key], inputs.lam_avg[key]
    return _as_req_per_second(peak), _as_req_per_second(avg)


def _as_req_per_second(value) -> Quantity:
    """Convert an arrival rate to req/s, reading the unit rather than assuming it.

    THIS FUNCTION EXISTS BECAUSE THE ASSUMPTION WAS WRONG ONCE. Figure 19's axis is req/min, so
    the obvious implementation divides by 60 -- but M3's `arrivals.py` already performs that
    conversion and tags the value `req/s`. Dividing again produced a silent 60x under-statement
    of demand: every GPU count came out ~60x too small and still looked like a plausible small
    integer (1-2 GPUs instead of ~100). Nothing downstream would have flagged it.

    So the unit is READ, not assumed, and an unrecognised one raises rather than guessing. This
    is the single conversion DESIGN.md Section 3.4 calls the one place a silent bug would be
    fatal, and it earned that description.
    """
    unit = getattr(value, "unit", "")
    raw = float(value.value)
    if unit in ("req/s", "requests/s"):
        return Quantity(raw, "req/s")
    if unit in ("req/min", "requests/min", "rpm"):
        return requests_per_second(raw)
    raise UnitError(
        f"arrival rate carries unit {unit!r}; expected req/s or req/min. Refusing to guess -- "
        "a wrong guess here scales every GPU count in the milestone by 60"
    )


def slo_space(inputs: MilpInputs, workflow: str) -> tuple[tuple[str, str], ...]:
    """`S` -- the `(type, tier)` pairs this workflow can actually be solved for.

    The INTERSECTION of two things that do not coincide, which is an integration fact worth
    stating because it silently controls which runs exist:

      * `tau` is defined for all eight `(type, tier)` combinations -- Section 3.4 derives four
        tiers for each of quality and latency.
      * `lambda` exists only where the profile set's `SloMix` put demand. The `baseline` set
        carries Section 4.3's joint mix (70% accuracy / 30% latency, **both `good` tier**), so
        six of the eight combinations have a threshold and no arrivals.

    A threshold with no demand is not a run: eq. (1) would read `0 <= sum x <= 0`. To reproduce
    Section 4.2's eight separate experiments ("all requests have the same SLO for each
    experiment"), build the profile set with `SloMix.section_4_2(type, tier)`, which puts the
    whole arrival stream on one combination.
    """
    with_tau = {(t, tier) for (w, t, tier) in inputs.tau if w == workflow}
    with_demand = {(t, tier) for (w, t, tier, _e) in inputs.lam_peak if w == workflow}
    return tuple(sorted(with_tau & with_demand))


def slo_space_without_demand(inputs: MilpInputs, workflow: str) -> tuple[tuple[str, str], ...]:
    """Thresholds that exist but carry no arrivals under this profile set's mix.

    Reported rather than silently skipped -- a reader comparing against Figures 7/8, which show
    all four tiers, needs to know which tiers this run could not exercise and why.
    """
    with_tau = {(t, tier) for (w, t, tier) in inputs.tau if w == workflow}
    with_demand = {(t, tier) for (w, t, tier, _e) in inputs.lam_peak if w == workflow}
    return tuple(sorted(with_tau - with_demand))


def epochs_of(inputs: MilpInputs, workflow: str) -> tuple[int, ...]:
    """A69: A.5 has no time index, but Section 3.4 runs the optimizer every 60 minutes, so M4
    solves one INDEPENDENT MILP per epoch with no state carried across. Nothing in A.5 couples
    two epochs -- no warm start, no switching cost, no minimum instance lifetime -- so our
    reproduction will tear down and rebuild a fleet between adjacent hours for free, exactly as
    the formulation permits. `report.py` measures the resulting churn."""
    return tuple(sorted({e for (w, _t, _tier, e) in inputs.lam_peak if w == workflow}))


__all__ = [
    "Admissible",
    "DATA_LACK",
    "EmptyAdmissibleSet",
    "Exclusion",
    "ExclusionLedger",
    "SLO_FILTER",
    "build_admissible",
    "demand",
    "epochs_of",
    "slo_space",
]
