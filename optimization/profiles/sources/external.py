"""
`c_g` -- the only parameter in A.5 sourced from outside the paper, because the paper omits it.

FLAGGED GAP A40. Appendix A.5 (p.586) lists:

    "cg: Cost per instance per second for resource type g in G"

and uses it in the cost budget constraint eq. (6)/(10) and the Minimize Cost objective eq. (12)
(p.587). NEITHER VERSION STATES ITS VALUE, and it is not recoverable from the reported results:
Table 2 (p.576) implies $3.43/GPU-h for its LangGraph row and $2.05/GPU-h for its Mkb Opt row of
the same cluster, because Murakkab's allocation varies across the 24 h while the reported cost
integrates it. No single constant `c_g` reproduces both.

Resolved Q18 (2026-09-11): `EXTERNAL` provenance from a vendor price list, swept +/-50%, rather
than `Unavailable`. `Unavailable` is the maximally honest option but it disables eq. (6), eq. (10),
eq. (12) and eq. (13) -- two of the three objectives -- which would cost two thirds of the
evaluation. The +/-50% band makes the dependence visible instead of hiding it.

This module contains `EXTERNAL` values ONLY. `B_g` is NOT here: Section 4.5's budget sweep is
paper text and lives in `sources/figure_labels.py` (A43 -- no budget is invented).

-------------------------------------------------------------------------------------------------
UNIT: `c_g` IS PER GPU PER SECOND, NOT PER VM (A53)
-------------------------------------------------------------------------------------------------
A.5 names the parameter "cost per INSTANCE per second", but its own equations use it per GPU.
Verified against [OSDI] p.587:

    eq. (12)   min  SUM_m  n_m * g_m * c_g(m)
    eq. (6)    SUM  x^avg * (t_c / theta_m) * g_m * c_g(m)  <=  Cost_budget

Both multiply `c_g` by `g_m`, the parallelism degree -- i.e. the number of GPUs the instance
occupies (Section 3.3.1, Decision 3, p.574). If `c_g` were already a whole-VM price, `g_m` would
double-count. The same pattern appears in eq. (11), `min SUM n_m * e_m * g_m`, so `e_m` is
likewise per GPU. The parameter's NAME contradicts the parameter's USE; we follow the equations,
since those are what M4 executes, and record the discrepancy.

The same reading resolves `B_g`, described as "Maximum available resource instances of type g"
while eq. (7) writes `SUM_{m:GPU(m)=g} n_m * g_m <= B_g` -- GPUs, not instances. Section 4.5
(p.578) confirms GPUs: "the cluster always provides 2,000 A100 GPUs".

-------------------------------------------------------------------------------------------------
SKU IDENTIFICATION IS DERIVED FROM THE PAPER, NOT CHOSEN BY US (corrects DESIGN.md Section 6.6)
-------------------------------------------------------------------------------------------------
DESIGN.md Section 6.6 says the prices come from "the exact VM shapes Section 4.1 (p.575) names".
Section 4.1 names NO SKU. Verbatim (p.575):

    "We run our experiments on A100 and H100 VMs from Microsoft Azure. Each A100 VM has
     8xNVIDIA A100 (80GB) GPUs and an AMD EPYC 7V12 64-Core processor, while each H100 VM has
     8xNVIDIA H100 (80GB) GPUs with an Intel Xeon (Sapphire Rapids) processor."

What it names instead is the GPU count, the GPU memory AND THE HOST CPU, and those pin the SKU
uniquely within Azure's catalogue:

  * 8x A100 80GB + AMD EPYC 7V12 64-core  ->  Standard_ND96asr_v4    (ND A100 v4 series)
  * 8x H100 80GB + Intel Xeon Sapphire Rapids -> Standard_ND96isr_H100_v5 (ND H100 v5 series)

So the identification is an inference from the paper's own hardware description -- stronger than a
free choice, weaker than a citation. The SKU mapping is recorded as the `assumption` on each value
and the resulting price is `EXTERNAL` (a derived value may not outrank its weakest input, and a
vendor price list is the weakest input here).
"""

from __future__ import annotations

from typing import Final

from optimization.profiles.provenance import Citation, Measured, Provenance
from optimization.profiles.sources.tables import TABLE_3

# ---------------------------------------------------------------------------------------------
# Retrieved prices (live, from the public Azure Retail Prices API)
# ---------------------------------------------------------------------------------------------

RETRIEVED: Final[str] = "2026-09-12"
"""Retrieval date. A vendor price list without a date is not a source (provenance.py requires it
for every EXTERNAL citation)."""

PRICES_API: Final[str] = "https://prices.azure.com/api/retail/prices"

REGION: Final[str] = "eastus"
"""The paper names no region. `eastus` is ours, chosen because it publishes both SKUs; the +/-50%
sweep covers regional variation, which is far smaller than that band."""

VM_HOURLY_USD: Final[dict[str, float]] = {
    "A100": 27.197,
    "H100": 98.320,
}
"""Linux pay-as-you-go hourly list price per WHOLE VM (8 GPUs), retrieved 2026-09-12 from the
Azure Retail Prices API, `priceType eq 'Consumption'`, `armRegionName eq 'eastus'`:

  Standard_ND96asr_v4       productName "Virtual Machines NDasr A100 v4 Series"  $27.197 / hour
  Standard_ND96isr_H100_v5  productName "Virtual Machines NDsr H100 v5 Series"   $98.320 / hour

Windows, Spot and Low Priority meters returned by the same query are deliberately excluded: the
paper self-hosts vLLM on Linux (Section 4.1, p.575) and a pre-emptible price would not support a
provisioning study.
"""

GPUS_PER_VM: Final[int] = 8
"""Section 4.1 (p.575), stated for both VM types. A structural count, not a measurement."""

SWEEP_FRACTION: Final[float] = 0.50
"""+/-50%, per Q18. This is also what satisfies provenance.py's rule that any value at or below
PAPER_FIGURE_READ carries an explicit uncertainty band -- the sweep and the band are the same
object, so the sensitivity analysis cannot be skipped by accident."""


def _citation(sku: str) -> Citation:
    return Citation(
        version="EXTERNAL",
        section=f"azure-retail-prices-api:{sku}",
        retrieved=RETRIEVED,
        quote=(
            f"{PRICES_API}?$filter=armSkuName eq '{sku}' and priceType eq 'Consumption' "
            f"and armRegionName eq '{REGION}'"
        ),
    )


_SKU: Final[dict[str, str]] = {
    "A100": "Standard_ND96asr_v4",
    "H100": "Standard_ND96isr_H100_v5",
}


def cost_per_gpu_second(gpu: str) -> Measured[float]:
    """`c_g` in the units A.5's equations actually use: US dollars per GPU per second.

    VM hourly list price / 8 GPUs / 3600 s, banded +/-50% per Q18.
    """
    hourly = VM_HOURLY_USD[gpu]
    per_gpu_second = hourly / GPUS_PER_VM / 3600.0
    return Measured(
        value=per_gpu_second,
        unit="$/GPU-s",
        provenance=Provenance.EXTERNAL,
        cite=_citation(_SKU[gpu]),
        lo=per_gpu_second * (1.0 - SWEEP_FRACTION),
        hi=per_gpu_second * (1.0 + SWEEP_FRACTION),
        assumption=(
            f"Section 4.1 (p.575) describes the {gpu} host as 8x{gpu} 80GB with "
            f"{'an AMD EPYC 7V12 64-core' if gpu == 'A100' else 'an Intel Xeon (Sapphire Rapids)'} "
            f"processor, which identifies {_SKU[gpu]} uniquely in Azure's catalogue; list price is "
            f"assumed (the paper's implied prices are roughly half list -- see "
            f"`table_3_implied_cost_per_gpu_hour()` -- consistent with reserved or internal rates "
            f"that are not published); c_g is per GPU because eqs. (6) and (12) multiply it by g_m."
        ),
        note=(
            f"{_SKU[gpu]} Linux PAYG ${hourly}/VM-hour / {GPUS_PER_VM} GPUs = "
            f"${hourly / GPUS_PER_VM:.6f}/GPU-hour, retrieved {RETRIEVED} for region {REGION}."
        ),
    )


# ---------------------------------------------------------------------------------------------
# Consistency check -- REPORTED, NOT ENFORCED (Q18)
# ---------------------------------------------------------------------------------------------


def table_3_implied_cost_per_gpu_hour() -> dict[str, float]:
    """What Table 3's single-GPU-type rows imply about `c_g`, under constant allocation.

    Rows 1 and 6 of Table 3 (p.578) are the only rows allocating exactly one GPU type, so cost /
    (GPUs * 24 h) pins an implied price. Every other row mixes both types and cannot be inverted.

    The constant-allocation assumption is FALSE in detail -- Figure 11 (p.578) shows the
    allocation tracking the diurnal load -- which is exactly why this is a reported cross-check
    and not a source. It is the same assumption under which Section 6.5 derives `e_m`.
    """
    a100_row, h100_row = TABLE_3[0], TABLE_3[-1]
    return {
        "A100": a100_row.cost_k_usd * 1_000.0 / (a100_row.allocated_a100 * 24.0),
        "H100": h100_row.cost_k_usd * 1_000.0 / (h100_row.allocated_h100 * 24.0),
    }


def price_consistency() -> dict[str, float]:
    """Compare the external price list against Table 3's implied prices.

    The RATIO agrees closely; the LEVEL does not. Both facts matter to M4:

      * ratio H100:A100 -- list 3.615 vs Table 3's implied 3.533, 2.3% apart. Two independent
        sources agreeing on relative GPU cost is genuine corroboration that the SKU
        identification above is right. It is NOT strong enough to promote the provenance above
        EXTERNAL, because a ratio cannot fix a level.
      * level -- list is ~1.9x Table 3's implied price per GPU-hour. So every absolute dollar
        figure M4 reports will be roughly double the paper's for the same allocation, and a
        cost comparison against Table 2/3 must be made in RELATIVE terms or not at all. This is
        the single most important consequence of A40 and it must appear in PROFILES.md.
    """
    implied = table_3_implied_cost_per_gpu_hour()
    listed = {g: VM_HOURLY_USD[g] / GPUS_PER_VM for g in ("A100", "H100")}
    return {
        "listed_a100_per_gpu_hour": listed["A100"],
        "listed_h100_per_gpu_hour": listed["H100"],
        "implied_a100_per_gpu_hour": implied["A100"],
        "implied_h100_per_gpu_hour": implied["H100"],
        "listed_ratio_h100_over_a100": listed["H100"] / listed["A100"],
        "implied_ratio_h100_over_a100": implied["H100"] / implied["A100"],
        "level_factor_a100": listed["A100"] / implied["A100"],
        "level_factor_h100": listed["H100"] / implied["H100"],
    }


__all__ = [
    "GPUS_PER_VM",
    "REGION",
    "RETRIEVED",
    "SWEEP_FRACTION",
    "VM_HOURLY_USD",
    "cost_per_gpu_second",
    "price_consistency",
    "table_3_implied_cost_per_gpu_hour",
]
