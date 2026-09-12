"""
Appendix A.5's equations, transcribed verbatim -- the thing this milestone claims to reproduce.

Murakkab (OSDI '26), Appendix A.5 "Optimization Formulation", pp.586-587. Identical in [ARXIV].

THIS FILE CONTAINS NO LOGIC, DELIBERATELY. It mirrors M3 putting `provenance.py` first: the
verbatim text of what we claim to reproduce must exist in the repo BEFORE the code that claims to
reproduce it, so every later module can be diffed against it by a reviewer holding the PDF.

`A5_VERBATIM.md` beside this file is the human-readable source of truth, extracted from the PDF
text layer on 2026-09-12. This module is its importable form, and
`tests/test_milp_formulation.py::test_a5_py_matches_the_verbatim_markdown` asserts every equation
string here appears there -- the same anti-drift mechanism M3 used for `PROFILES.md`. Neither file
may be edited without the other.

WHY THIRTEEN NUMBERED EQUATIONS ARE TEN (A58). A.5 states four constraints twice: eq. (4) and (8)
are verbatim duplicates, as are eq. (5) and (9), and eq. (6) and (10) differ only by inlining
`Cost_budget`. `DUPLICATE_OF` records this. It is not a transcription error on our part -- it is
in the paper, and a reader counting constraints from the equation numbers will overcount by three.
"""

from __future__ import annotations

from typing import Final, Mapping

CITE: Final[str] = "[OSDI] Appendix A.5, pp.586-587; [ARXIV] identical"

# ---------------------------------------------------------------------------------------------
# Sets, parameters, decision variables -- A.5's own glosses, quoted
# ---------------------------------------------------------------------------------------------

SETS: Final[Mapping[str, str]] = {
    "W": "workflows",
    "S": "SLO types",
    "M": "model profiles",
    "C_w": "workflow configurations for w",
    "G": "resource types",
}

PARAMETERS: Final[Mapping[str, str]] = {
    "lambda_peak": "Peak request rate for workflow w with SLO s",
    "lambda_avg": "Average request rate for workflow w with SLO s",
    "alpha": "Unified buffer factor (default 1.15)",
    "tau": "SLO threshold for workflow w and SLO type s",
    "a_c": "Accuracy of workflow configuration c in C_w",
    "t_c": "Tokens per request for workflow configuration c",
    "theta_m": "Token throughput (tokens/sec) for model profile m",
    "l_ttft_m": "Time to first token for model profile m",
    "l_tpot_m": "Time per output token for model profile m",
    "g_m": "Parallelism for model m",
    "e_m": "Energy consumption (kWh) for model profile m",
    "c_g": "Cost per instance per second for resource type g in G",
    "B_g": "Maximum available resource instances of type g",
}
"""A.5's parameter table, glosses quoted exactly.

TWO OF THESE GLOSSES ARE WRONG BY A.5'S OWN ALGEBRA (A57), and the wrongness is reproduced rather
than corrected:

  * `c_g` says "per instance per second", but eq. (6), eq. (7) and objective (12) all multiply it
    by `g_m` (GPUs per instance), so it is per GPU per second. M3 supplies it as `$/GPU-s`.
  * `B_g` says "resource instances", but eq. (7) is `sum n_m * g_m <= B_g`, which counts GPUs --
    consistent with Section 4.5's "2,000 A100 GPUs" and Table 3's "Allocated A100s".
"""

DECISION_VARIABLES: Final[Mapping[str, str]] = {
    "n_m": "n_m in Z+: Number of instances of model profile m",
    "x_peak": "x^peak_{w,s,c,m} in R+: Peak load allocation from (w,s,c) to model m",
    "x_avg": "x^avg_{w,s,c,m} in R+: Average load allocation from (w,s,c) to model m",
}
"""`x` is CONTINUOUS by A.5's own declaration (`R+`), not integer.

Reproduced as declared (DESIGN.md Section 4.1). The consequence is a finding: a request stream may
be split fractionally across many (c, m) pairs, so "the chosen configuration" is a DISTRIBUTION,
while Tables 5 and 6 print a single row per (workflow, SLO tier) as though it were a choice (A70).
"""

# ---------------------------------------------------------------------------------------------
# The constraints, verbatim
# ---------------------------------------------------------------------------------------------

EQ_1_DEMAND_PEAK: Final[str] = (
    "lambda^peak_{w,s} <= sum_{c in C_w, m in M} x^peak_{w,s,c,m} <= alpha * lambda^peak_{w,s}, "
    "for all w in W, s in S"
)

EQ_2_DEMAND_AVG: Final[str] = (
    "lambda^avg_{w,s} <= sum_{c in C_w, m in M} x^avg_{w,s,c,m} <= alpha * lambda^avg_{w,s}, "
    "for all w in W, s in S"
)

EQ_3_CAPACITY: Final[str] = (
    "mu_m * sum_{w,s,c} x^peak_{w,s,c,m} * t_c <= n_m * theta_m, for all m in M"
)
""""where mu_m is the model-specific multiplexing factor" -- A.5's entire definition of it.

No value, bound, or estimation method appears in either version, and Section 3.3's list of what a
profile contains does not include it (A42). M4 sets `mu_m = 1`; M5 owns the problem.

NOTE the index: `x^peak`. Eq. (3) has NO average-rate twin (Q21(b), settled against the PDF), so
`n_m` is provisioned from PEAK load alone and `x^avg` never sizes the fleet.
"""

EQ_4_FILTER_ACCURACY: Final[str] = (
    "x^peak_{w,s,c,m} = 0 if a_c < tau_{w,s}    [For accuracy SLO (s = max_accuracy)]"
)

EQ_5_FILTER_LATENCY: Final[str] = (
    "x^peak_{w,s,c,m} = 0 if l^TTFT_m + t_c * l^TPOT_m > tau_{w,s}    "
    "[For latency SLO (s = min_latency)]"
)
"""The paper's ENTIRE model of end-to-end latency.

One model's TTFT plus that model's per-token time times the whole configuration's token count. No
sum over sub-tasks, no max over parallel branches, no critical path, no term a tool could occupy.
Section 4.6 (p.578) nonetheless measures DAG-parallel co-scheduling -- the gap M4 records and does
not repair (DESIGN.md Section 10).
"""

EQ_6_COST_BUDGET: Final[str] = (
    "sum_{w,s,c,m} x^avg_{w,s,c,m} * (t_c / theta_m) * g_m * c_{g(m)} <= Cost_budget, "
    "where Cost_budget = sum_{w in W} tau_{w,cost} * sum_s lambda^avg_{w,s}"
)
"""Prices CONSUMPTION (GPU-seconds of work), where objective (12) prices PROVISIONING (A72).

Nothing ties the two together, so a solution may sit far under this budget while provisioning an
arbitrarily expensive fleet: idle capacity costs nothing here and everything in eq. (12).
Compounded by A66 -- `x^avg` is unfiltered and never drives `n_m` -- this budget constrains a
quantity that is nearly free to satisfy.

`Cost_budget` IS defined, but in terms of `tau_{w,cost}`, a COST-type SLO threshold. Section 3.4
(p.575) defines four tiers for quality and latency only, and no table in either version reports a
cost tier (A67). Supplied explicitly per run; never defaulted.
"""

EQ_7_RESOURCE_BUDGET: Final[str] = (
    "sum_{m : GPU(m) = g} n_m * g_m <= B_g, for all g in G"
)

EQ_8_FILTER_ACCURACY_DUP: Final[str] = (
    "x^peak_{w,s,c,m} = 0 if a_c < tau_{w,s}    (accuracy)"
)

EQ_9_FILTER_LATENCY_DUP: Final[str] = (
    "x^peak_{w,s,c,m} = 0 if l^TTFT_m + t_c l^TPOT_m > tau_{w,s}    (latency)"
)

EQ_10_COST_BUDGET_DUP: Final[str] = (
    "sum_{w,s,c,m} x^avg_{w,s,c,m} (t_c / theta_m) g_m c_{g(m)} "
    "<= sum_w tau_{w,cost} sum_s lambda^avg_{w,s}"
)

# ---------------------------------------------------------------------------------------------
# The objectives, verbatim
# ---------------------------------------------------------------------------------------------

EQ_11_MIN_ENERGY: Final[str] = "min sum_m n_m * e_m * g_m"
"""Multiplies `e_m` by `g_m`, so `e_m` is per GPU.

M3 supplies `e_m` from Table 3 per GPU TYPE (A41: Figure 3's "TPS per Wh" column is dimensionally
undefined), so this objective CANNOT distinguish two models running on the same GPU type. It
degenerates to "minimize total GPU-hours, weighted by GPU type".
"""

EQ_12_MIN_COST: Final[str] = "min sum_m n_m * g_m * c_{g(m)}"

EQ_13_MAX_ACCURACY: Final[str] = (
    "max ( sum_{w,s,c,m} x^avg_{w,s,c,m} * a_c ) / ( sum_{w,s} lambda^avg_{w,s} ) "
    "- epsilon * Cost_total,  where epsilon = 0.001"
)
"""THE OBJECTIVE THE QUALITY FILTER CANNOT REACH (A66).

The superscript is `avg` (Q21(c), settled against the PDF). Filters (4)/(5)/(8)/(9) constrain
`x^peak` ONLY, so nothing prevents this objective from placing average load on configurations
whose `a_c` is BELOW `tau_{w,s}`. The one objective that optimises quality is the one the quality
filter does not apply to.

`Cost_total` is never defined in A.5. Eq. (12)'s expression is the only candidate and is what M4
uses, labelled as such.
"""

EPSILON: Final[float] = 0.001
"""A.5 p.587: "where epsilon = 0.001". The cost tie-breaker weight in objective (13)."""

SOLUTION_METHOD: Final[str] = (
    "The formulated Mixed Integer Linear Program (MILP) is solved using Gurobi [37] with a time "
    "limit of 300 seconds. The solution yields an allocation of model instance counts n*_m and "
    "load distributions across model instances for all workflows."
)

# ---------------------------------------------------------------------------------------------
# The 13 -> 10 map (A58)
# ---------------------------------------------------------------------------------------------

DUPLICATE_OF: Final[Mapping[int, int]] = {8: 4, 9: 5, 10: 6}
"""A.5's redundant equation numbers. (8)==(4) and (9)==(5) verbatim; (10)==(6) up to inlining
`Cost_budget`. Thirteen numbered equations, ten distinct."""

DISTINCT_EQUATIONS: Final[Mapping[int, str]] = {
    1: EQ_1_DEMAND_PEAK,
    2: EQ_2_DEMAND_AVG,
    3: EQ_3_CAPACITY,
    4: EQ_4_FILTER_ACCURACY,
    5: EQ_5_FILTER_LATENCY,
    6: EQ_6_COST_BUDGET,
    7: EQ_7_RESOURCE_BUDGET,
    11: EQ_11_MIN_ENERGY,
    12: EQ_12_MIN_COST,
    13: EQ_13_MAX_ACCURACY,
}
"""The ten M4 implements. Constraint numbers 1-7, objective numbers 11-13."""

ALL_NUMBERED: Final[Mapping[int, str]] = {
    **DISTINCT_EQUATIONS,
    8: EQ_8_FILTER_ACCURACY_DUP,
    9: EQ_9_FILTER_LATENCY_DUP,
    10: EQ_10_COST_BUDGET_DUP,
}

CONSTRAINT_NUMBERS: Final[tuple[int, ...]] = (1, 2, 3, 4, 5, 6, 7)
OBJECTIVE_NUMBERS: Final[tuple[int, ...]] = (11, 12, 13)

#: Which decision variable each numbered equation constrains. The basis of A66.
VARIABLE_OF: Final[Mapping[int, str]] = {
    1: "x_peak",
    2: "x_avg",
    3: "x_peak",
    4: "x_peak",
    5: "x_peak",
    6: "x_avg",
    7: "n_m",
    8: "x_peak",
    9: "x_peak",
    10: "x_avg",
    11: "n_m",
    12: "n_m",
    13: "x_avg",
}
"""A66, as data rather than prose.

Read the `x_avg` rows: eqs. (2), (6), (10) and objective (13). None of them is an SLO filter, and
none of them is the capacity constraint. So average load is never quality-checked and never sizes
the fleet. `tests/test_milp_formulation.py` asserts this closure directly, so the finding is
enforced by the code rather than remembered.
"""

__all__ = [
    "ALL_NUMBERED",
    "CITE",
    "CONSTRAINT_NUMBERS",
    "DECISION_VARIABLES",
    "DISTINCT_EQUATIONS",
    "DUPLICATE_OF",
    "EPSILON",
    "EQ_1_DEMAND_PEAK",
    "EQ_2_DEMAND_AVG",
    "EQ_3_CAPACITY",
    "EQ_4_FILTER_ACCURACY",
    "EQ_5_FILTER_LATENCY",
    "EQ_6_COST_BUDGET",
    "EQ_7_RESOURCE_BUDGET",
    "EQ_8_FILTER_ACCURACY_DUP",
    "EQ_9_FILTER_LATENCY_DUP",
    "EQ_10_COST_BUDGET_DUP",
    "EQ_11_MIN_ENERGY",
    "EQ_12_MIN_COST",
    "EQ_13_MAX_ACCURACY",
    "OBJECTIVE_NUMBERS",
    "PARAMETERS",
    "SETS",
    "SOLUTION_METHOD",
    "VARIABLE_OF",
]
