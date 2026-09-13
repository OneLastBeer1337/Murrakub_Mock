"""
The three tracks plus the exact reference.

Spec: docs/design/System_Architecture_v2.md §5.2.

Every track exposes the same entry point (principle P5 — tracks are swappable):

    def allocate(tasks, pools, profiles, budget, seed=0) -> AllocationResult

Tracks return AllocationResult with feasible=False rather than raising, so the harness
records failures as data instead of crashing. Every result passes invariants.check()
before leaving a track.

Build order is exact-first: exact_milp (4), then track_c_lp (7), track_b_lagr (8),
track_a_greedy (9). Nothing can be checked for correctness without ground truth.
"""
