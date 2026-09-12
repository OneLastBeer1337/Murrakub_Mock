"""
Generates `PROFILES.md` -- the provenance ledger of DESIGN.md Section 10.

The file is GENERATED, never hand-written, and `tests/test_profiles_md_generated.py` asserts
byte-equality with the checked-in copy. That is assertion 4 of Section 2.5, and its purpose is
narrow but important: documentation that can drift from the data it describes is worse than no
documentation, because it is quoted with confidence.

Run `python -m optimization.profiles.ledger` to regenerate.
"""

from __future__ import annotations

from typing import Any, Sequence

from optimization.profiles.arrivals import EPOCHS, FIG_19_SERIES_TO_WORKFLOW, trace_summary
from optimization.profiles.enumerate_cw import EXPECTED_CARDINALITY
from optimization.profiles.profile_sets import NAMED_SETS, profile_set
from optimization.profiles.provenance import (
    CITATION_REGISTRY,
    Citation,
    Measured,
    Provenance,
    Unavailable,
)
from optimization.profiles.schema import OperatingPointPolicy, ProfileSet
from optimization.profiles.sources.external import GPUS_PER_VM, RETRIEVED, VM_HOURLY_USD
from optimization.profiles.validation import summary
from optimization.profiles.sources.tables import (
    DEBATERS_COLUMN_HEADER,
    STT_COLUMN_EXISTS,
)

PREAMBLE = """\
> **Read this before quoting any number below.**
>
> This is a REPRODUCTION of a paper that has no source release. Every value here is either
> transcribed from the paper, digitized from one of its figures, derived from those by stated
> arithmetic, or recorded as *unavailable*. Nothing is invented: the only invented numbers in
> Milestone 3 are seven tool service times, which live in `optimization/profiles/critique/` and
> which a test proves the optimizer cannot reach.
>
> Three consequences a casual reader will otherwise miss. **First**, a large minority of values
> are `Unavailable` -- the paper simply does not report them -- so any total computed from this
> set is a LOWER BOUND, and unequally so between the two workflows. **Second**, digitized values
> carry bands, and the bands are wide where the figure is dense; a point estimate quoted without
> its band overstates what the source supports. **Third**, tier values depend on the whole
> population, so they are NOT comparable across profile sets, and every number must be quoted
> together with the set that produced it.
>
> Where this reproduction disagrees with the paper, the paper's reading is kept and the
> disagreement is recorded rather than repaired. See `PROGRESS.md` for the numbered gap list.
"""


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def _cite_str(cite: Citation) -> str:
    if cite.version == "EXTERNAL":
        return f"EXTERNAL {cite.section} (retrieved {cite.retrieved})"
    bits = []
    if cite.table is not None:
        bits.append(f"Table {cite.table}")
    if cite.figure is not None:
        bits.append(f"Figure {cite.figure}")
    if cite.section is not None:
        bits.append(f"Section {cite.section}")
    if cite.page is not None:
        bits.append(f"p.{cite.page}")
    return f"[{cite.version}] " + ", ".join(bits)


def _band(m: Measured) -> str:
    if m.lo is None:
        return "exact"
    return f"[{_fmt(m.lo)}, {_fmt(m.hi)}]"


def _escape(text: str) -> str:
    return text.replace("|", r"\|").replace("\n", " ").strip()


# ---------------------------------------------------------------------------------------------
# Value collection
# ---------------------------------------------------------------------------------------------


def _rows(pset: ProfileSet) -> list[tuple[str, str, Any]]:
    """Every MILP-facing value, as `(owner, field, value)`, in a stable order.

    Deliberately built from the SAME projection the optimizer consumes rather than by walking
    the object graph: a ledger that documented values the MILP never sees would be reassuring
    and wrong.
    """
    out: list[tuple[str, str, Any]] = []
    for key in sorted(pset.workflow, key=str):
        wp = pset.workflow[key]
        out.append((str(key), "a_c", wp.accuracy))
        tokens = wp.tokens if isinstance(wp.tokens, Unavailable) else wp.tokens.p90()
        out.append((str(key), "t_c (p90)", tokens))
    for mk in sorted(pset.models, key=str):
        mp = pset.models[mk]
        policy = OperatingPointPolicy.TABLE_REPORTED
        out.append((str(mk), "theta_m", mp.theta(policy)))
        out.append((str(mk), "l_ttft_m", mp.ttft(policy)))
        out.append((str(mk), "l_tpot_m", mp.tpot(policy)))
        out.append((str(mk), "g_m", mp.parallelism))
        out.append((str(mk), "e_m", mp.energy))
    for name in sorted(pset.resources):
        rt = pset.resources[name]
        out.append((name, "c_g", rt.cost_per_instance_second))
        out.append((name, "B_g", rt.budget))
    for skey in sorted(pset.slo, key=str):
        out.append(("/".join(skey), "tau", pset.slo[skey]))
    for ap in sorted(pset.arrivals, key=lambda a: (a.workflow_id, a.slo, a.epoch)):
        owner = f"{ap.workflow_id}/{ap.slo[1]}/epoch {ap.epoch}"
        out.append((owner, "lambda_peak", ap.lam_peak))
        out.append((owner, "lambda_avg", ap.lam_avg))
    out.append(("global", "alpha", pset.alpha))
    return out


# ---------------------------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------------------------


def _ledger_table(rows: Sequence[tuple[str, str, Any]]) -> list[str]:
    lines = [
        "| Owner | Field | Value | Unit | Provenance | Citation | Band | Assumption / anchors |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for owner, field, value in rows:
        if isinstance(value, Unavailable):
            lines.append(
                f"| `{owner}` | `{field}` | *unavailable* | - | UNAVAILABLE | "
                f"{_cite_str(value.cite)} | - | {_escape(value.reason)} |"
            )
            continue
        extra = ""
        if value.anchors:
            anchors = "; ".join(f"{a.profile_key}.{a.field}" for a in value.anchors)
            extra = f"anchors: {anchors}. "
        if value.assumption:
            extra += _escape(value.assumption)
        lines.append(
            f"| `{owner}` | `{field}` | {_fmt(value.value)} | {value.unit} | "
            f"{Provenance(value.provenance).name} | {_cite_str(value.cite)} | "
            f"{_band(value)} | {_escape(extra) or '-'} |"
        )
    return lines


def _coverage_section(pset: ProfileSet) -> list[str]:
    report = pset.coverage_report()
    columns = sorted({k for c in report.counts.values() for k in c})
    lines = ["| Field | " + " | ".join(columns) + " | Total |", "|---" * (len(columns) + 2) + "|"]
    for field, counts in report.counts.items():
        total = sum(counts.values())
        cells = " | ".join(str(counts.get(c, 0)) for c in columns)
        lines.append(f"| `{field}` | {cells} | {total} |")
    return lines


def _unavailable_register(rows: Sequence[tuple[str, str, Any]]) -> list[str]:
    lines = ["| Owner | Field | Blocks | Reason |", "|---|---|---|---|"]
    for owner, field, value in rows:
        if not isinstance(value, Unavailable):
            continue
        blocks = ", ".join(value.blocks) if value.blocks else "-"
        lines.append(f"| `{owner}` | `{field}` | {blocks} | {_escape(value.reason)} |")
    return lines


def _concordance_section() -> list[str]:
    return [
        "| Item | [OSDI] | [ARXIV] | Note |",
        "|---|---|---|---|",
        "| Chosen configurations, Video Q/A | Table 5 | Table 4 | A44: the `STT` column exists "
        f"only in [OSDI] ({STT_COLUMN_EXISTS['OSDI']} vs {STT_COLUMN_EXISTS['ARXIV']}) |",
        "| Chosen configurations, Code Gen | Table 6 | Table 5 | A45: column headed "
        f"`{DEBATERS_COLUMN_HEADER['OSDI']}` vs `{DEBATERS_COLUMN_HEADER['ARXIV']}`; the column "
        "is `D`, which resolves M2's A14 |",
        "| p90 allocation rule | p.576 | *absent* | A46: the sentence that binds `t_c` to the "
        "p90 exists in one version only |",
    ]


def _validation_section(pset: ProfileSet) -> list[str]:
    """Section 10, item 5: all THREE cross-checks with their residuals.

    Each compares a digitized reading against a number the digitization never saw, so agreement
    is evidence rather than self-consistency. See `validation.py` on why the Section 5.2 check
    and the Section 7.3 reconstruction are independent only while `a_c` stays sourced from
    Figure 2c (A63).
    """
    checks = summary()
    lines = ["| Check | Result |", "|---|---|"]

    fig3 = checks["figure_3_vs_tables"]
    lines.append(
        f"| Section 6.2, Tables 5/6 vs Figure 3 curves | "
        f"{fig3['agreeing']:.0f}/{fig3['points']:.0f} tabled points lie on their own curve; "
        f"worst residual {fig3['worst_residual_frac'] * 100:.1f}% "
        f"(tolerance {fig3['tolerance_frac'] * 100:.0f}%) |"
    )
    acc = checks["figure_2c_vs_tier_labels"]
    lines.append(
        f"| Section 5.2, Figure 2c bars vs printed tier labels | "
        f"{acc['agreeing']:.0f}/{acc['points']:.0f} tiers agree; worst residual "
        f"{acc['worst_residual_pp']:.2f} pp (tolerance {acc['tolerance_pp']:.1f} pp); every "
        "residual is positive, i.e. the chosen configuration CLEARS its tier rather than "
        "equalling it |"
    )
    for workflow, data in sorted(pset.tier_reconstruction.items()):
        worst = max(abs(v) for v in data["residuals"].values())
        lines.append(
            f"| Section 7.3 tier reconstruction, {workflow} ({data['figure']}, "
            f"n={data['population_size']}) | worst residual {worst:.2f} pp; "
            f"within band: {data['within_band']} |"
        )
    if pset.operating_point_collapse:
        lines.append(
            f"| A37b operating-point collapse | {len(pset.operating_point_collapse)} rows "
            "discarded and recorded |"
        )
    lines.append(
        f"| Configuration space | {EXPECTED_CARDINALITY['code_generation']} code generation + "
        f"{EXPECTED_CARDINALITY['video_qa']} video Q/A = "
        f"{sum(EXPECTED_CARDINALITY.values())} |"
    )
    lines.append(f"| Citation registry | {len(CITATION_REGISTRY)} loci, all resolved |")
    return lines


def _named_sets_section() -> list[str]:
    purpose = {
        "baseline": "the default: every value at its point estimate",
        "paper_only": "values with PAPER_* provenance only; everything derived becomes "
        "`Unavailable`, so M4 can report what the paper alone supports",
        "pessimistic": "every band at its unfavourable end",
        "optimistic": "every band at its favourable end",
        "derived_tiers": "tiers recomputed from our population instead of the printed labels",
    }
    lines = ["| Set | Purpose |", "|---|---|"]
    for name in NAMED_SETS:
        lines.append(f"| `{name}` | {purpose.get(name, '-')} |")
    return lines


def _external_section() -> list[str]:
    lines = [
        "| SKU | Hourly (whole VM, 8 GPUs) | Per GPU-second | Retrieved |",
        "|---|---|---|---|",
    ]
    for gpu, hourly in sorted(VM_HOURLY_USD.items()):
        lines.append(
            f"| {gpu} | ${hourly:.3f} | ${hourly / GPUS_PER_VM / 3600.0:.8f} | {RETRIEVED} |"
        )
    return lines


def _arrivals_section() -> list[str]:
    """Figure 19's traces, summarised by the statistics eq. (2) and eq. (3) actually consume.

    The peak-to-mean ratio is the one that matters: eq. (3) provisions on `lambda^peak` while
    eq. (2) admits on `lambda^avg`, so the ratio is the size of the over-provisioning the
    formulation builds in before `alpha` is applied at all.
    """
    lines = [
        "| Trace | Workflow | Samples | Min rpm | Mean rpm | Max rpm | Peak/mean |",
        "|---|---|---|---|---|---|---|",
    ]
    summary = trace_summary()
    for name, workflow in sorted(FIG_19_SERIES_TO_WORKFLOW.items()):
        s = summary[name]
        lines.append(
            f"| {name} | {workflow} | {s['samples']:.0f} | {s['min_rpm']:.1f} | "
            f"{s['mean_rpm']:.1f} | {s['max_rpm']:.1f} | {s['peak_to_mean_ratio']:.3f} |"
        )
    lines.append("")
    lines.append(f"Optimization epochs per trace: {EPOCHS}.")
    return lines


# ---------------------------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------------------------


def render(set_name: str = "baseline") -> str:
    pset = profile_set(set_name)
    rows = _rows(pset)
    measured = [v for _o, _f, v in rows if isinstance(v, Measured)]
    unavailable = [v for _o, _f, v in rows if isinstance(v, Unavailable)]
    total = len(rows)
    invented = sum(1 for m in measured if m.provenance is Provenance.INVENTED)

    out: list[str] = [
        "# PROFILES.md -- provenance ledger",
        "",
        "**GENERATED FILE. Do not edit by hand.**",
        "Regenerate with `python -m optimization.profiles.ledger`; "
        "`tests/test_profiles_md_generated.py` asserts this file matches the data byte for byte.",
        "",
        PREAMBLE,
        "",
        f"Profile set: `{pset.name}`. "
        f"{total} MILP-facing values: {len(measured)} sourced, {len(unavailable)} unavailable "
        f"({100.0 * len(unavailable) / total:.1f}%), {invented} invented.",
        "",
        "## 1. Coverage summary",
        "",
        *_coverage_section(pset),
        "",
        "## 2. The `Unavailable` register",
        "",
        "What this reproduction does not know, and which expression each gap blocks.",
        "",
        *_unavailable_register(rows),
        "",
        "## 3. Validation",
        "",
        *_validation_section(pset),
        "",
        "## 4. Paper-version concordance",
        "",
        *_concordance_section(),
        "",
        "## 5. Named profile sets",
        "",
        *_named_sets_section(),
        "",
        "## 6. External sources",
        "",
        "`c_g` is the only parameter with a non-paper source (A40).",
        "",
        *_external_section(),
        "",
        "## 7. Arrival traces",
        "",
        *_arrivals_section(),
        "",
        "## 8. The ledger",
        "",
        f"One row per MILP-facing value ({total} rows).",
        "",
        *_ledger_table(rows),
        "",
    ]
    return "\n".join(out)


def write(path: str = "PROFILES.md", set_name: str = "baseline") -> str:
    text = render(set_name)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return text


if __name__ == "__main__":
    write()
    print("wrote PROFILES.md")


__all__ = ["PREAMBLE", "render", "write"]
