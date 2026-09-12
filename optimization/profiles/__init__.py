"""
Workflow and Model Profiles -- Murakkab (OSDI '26) Section 3.3, "Profiles" (p.573).

    "Each profile reports: (1) latency (TTFT and TPOT for LLMs), (2) energy consumption across
    hardware, and (3) cost per configuration."

THE PUBLIC SURFACE IS DELIBERATELY TWO NAMES.

`profile_set(name)` gives a complete, named, swappable `ProfileSet`; `ProfileSet.to_milp_inputs()`
projects it onto exactly Appendix A.5's thirteen parameters. Everything else in this package is
assembly detail, and one thing -- `critique/` -- is actively quarantined: it holds the only
invented numbers in the milestone, and `tests/test_milp_boundary.py` asserts by static import
analysis that nothing reachable from `to_milp_inputs()` can touch it.

Import the submodules directly if you are working ON the profiles. Import from here if you are
working FROM them, which is what `/optimization/milp/` must do.

Two properties worth knowing before consuming any of this:

  * **Absence is a value.** Roughly an eighth of the MILP-facing set is `Unavailable` because
    the paper does not report it. Reading one raises rather than returning a zero, and
    `MilpInputs.data_excluded` lists what M4 must report as excluded for lack of data rather
    than lack of merit.
  * **Tier values are population-dependent.** Section 3.4 (p.575) derives them from "the set of
    all workflow, model, and hardware configurations", so adding a model shifts every tier. A
    number from one profile set is not comparable with a number from another, and every reported
    result has to be tagged with the set that produced it.

`PROFILES.md` at the repository root is the generated ledger for all of it.
"""

from __future__ import annotations

from optimization.profiles.profile_sets import NAMED_SETS, profile_set, resample
from optimization.profiles.schema import (
    ConfigKey,
    MilpInputs,
    ModelProfileKey,
    OperatingPointPolicy,
    ProfileSet,
    SloMix,
    TokenPolicy,
)

__all__ = [
    "ConfigKey",
    "MilpInputs",
    "ModelProfileKey",
    "NAMED_SETS",
    "OperatingPointPolicy",
    "ProfileSet",
    "SloMix",
    "TokenPolicy",
    "profile_set",
    "resample",
]
