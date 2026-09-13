"""
Measurement harness — runs conditions under matched inputs.

Spec: docs/design/System_Architecture_v2.md §4.7, §6.1.
Build step 10. Verified by: reproduces a known result end-to-end.
Owner: 089

Fixes batch, profile snapshot, budget and seed identically across conditions; runs
Tracks A, B, C and the exact MILP; records cost, runtime, bound, feasibility.
Calls invariants.check() on every produced result.
"""
