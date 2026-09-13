"""
Cost, runtime, bound, gap, feasibility.

Spec: docs/design/System_Architecture_v2.md §6.1.
Build step 10. Owner: 089

The gap that matters for T4 is cost-to-optimum, which needs the exact MILP result — so
these are only meaningful on instances small enough to solve exactly. That is deliberate;
the PoC establishes no performance claims at scale (PoC plan §5.7).

TWO RULES THIS MODULE ENFORCES, because getting either wrong flatters a heuristic:

  1. Instances the exact solver could not solve are excluded from every aggregate. A gap
     against an unknown optimum is not a number.
  2. Infeasible runs are counted, never averaged over. A track that solves only the easy
     instances would otherwise post the best mean gap in the table — the failure IS the
     result, and `infeasible` sits next to `mean_gap_pct` so the two are read together.
"""

from __future__ import annotations

from dataclasses import dataclass


def gap_to_optimum(result, optimum_cost: float) -> float | None:
    """Percentage above the exact optimum. None if either side is unavailable."""
    if optimum_cost is None or not result.feasible or optimum_cost <= 0:
        return None
    return (result.total_cost - optimum_cost) / optimum_cost * 100.0


def bound_gap(result, optimum_cost: float) -> float | None:
    """How far the track's lower bound sits below the true optimum, as a percentage.

    This is the T1 quantity: Track B earns its place only if its bound gap is smaller than
    Track C's LP bound gap.
    """
    if optimum_cost is None or result.lower_bound is None or optimum_cost <= 0:
        return None
    return (optimum_cost - result.lower_bound) / optimum_cost * 100.0


@dataclass(frozen=True)
class ConditionSummary:
    condition: str
    instances: int          # solvable instances this condition was run on
    feasible: int
    infeasible: int
    optimal: int            # matched the exact optimum
    mean_gap_pct: float | None
    max_gap_pct: float | None
    mean_bound_gap_pct: float | None
    mean_runtime_s: float

    @property
    def infeasible_pct(self) -> float:
        return self.infeasible / self.instances * 100.0 if self.instances else 0.0


def _mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def summarise(records) -> dict[str, ConditionSummary]:
    """Aggregate a list of RunRecords per condition, over solvable instances only."""
    solvable = [r for r in records if r.solvable]
    summaries = {}

    names = []
    for record in solvable:
        for name in record.conditions:
            if name not in names:
                names.append(name)

    for name in names:
        runs = [(r, r.conditions[name]) for r in solvable if name in r.conditions]
        gaps = [gap_to_optimum(c.result, r.optimum) for r, c in runs]
        bounds = [bound_gap(c.result, r.optimum) for r, c in runs]
        feasible = [c for _, c in runs if c.feasible]

        summaries[name] = ConditionSummary(
            condition=name,
            instances=len(runs),
            feasible=len(feasible),
            infeasible=len(runs) - len(feasible),
            optimal=sum(1 for r, c in runs
                        if c.feasible and abs(c.result.total_cost - r.optimum) < 1e-6),
            mean_gap_pct=_mean(gaps),
            max_gap_pct=max([g for g in gaps if g is not None], default=None),
            mean_bound_gap_pct=_mean(bounds),
            mean_runtime_s=_mean([c.result.compute_time for _, c in runs]) or 0.0,
        )

    return summaries


def format_table(summaries: dict[str, ConditionSummary]) -> str:
    """A fixed-width table. The columns are chosen so a track cannot look good by failing:
    infeasible sits directly beside the gap it would otherwise improve."""
    header = (f"{'cond':<6} {'inst':>5} {'feas':>5} {'infeas':>7} {'=opt':>5} "
              f"{'mean gap%':>10} {'max gap%':>9} {'bound gap%':>11} {'time s':>8}")
    lines = [header, "-" * len(header)]
    for s in summaries.values():
        fmt = lambda v, w, d=2: f"{v:>{w}.{d}f}" if v is not None else f"{'-':>{w}}"  # noqa: E731
        lines.append(
            f"{s.condition:<6} {s.instances:>5} {s.feasible:>5} {s.infeasible:>7} "
            f"{s.optimal:>5} {fmt(s.mean_gap_pct, 10)} {fmt(s.max_gap_pct, 9)} "
            f"{fmt(s.mean_bound_gap_pct, 11)} {fmt(s.mean_runtime_s, 8, 3)}")
    return "\n".join(lines)


def solvability(records) -> dict[float, tuple[int, int]]:
    """tightness -> (solvable, total). The T3 view: where does the budget bind at all?"""
    counts: dict[float, list[int]] = {}
    for record in records:
        entry = counts.setdefault(record.instance.budget_tightness, [0, 0])
        entry[1] += 1
        if record.solvable:
            entry[0] += 1
    return {k: tuple(v) for k, v in sorted(counts.items())}
