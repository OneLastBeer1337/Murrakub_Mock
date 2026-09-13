"""
The ground-truth instance — 3 tasks, 2 profiles, B = 4.

Source: CLAUDE.md "Ground-truth instance (verified by hand)".
DO NOT CHANGE THESE NUMBERS. The optimum below was computed by exhaustion, and two
separate build steps are checked against it (step 4: MILP returns 280; step 9: greedy
returns 300).

Full enumeration — t3 is forced to m1 (m2 fails its reliability floor), so this is just
the subsets of {t1, t2} routed to m2:

    routing         n[m1]           n[m2]   GPUs    cost
    all on m1       ceil(23/10)=3   0       3       300
    t1→m2           ceil(15/10)=2   1       4       380
    t2→m2           ceil(17/10)=2   1       4       380
    t1,t2→m2        ceil( 9/10)=1   1       3       280   ← OPTIMUM

Why this instance matters beyond validating the MILP — traced by hand, greedy returns 300:

    t1: m1 costs 100 (open 1 instance), m2 costs 180        → m1.  n[m1]=1, load=8
    t2: m1 headroom 2 < 6 → +1 instance = 100; m2 = 180     → m1.  n[m1]=2, load=14
    t3: m1 headroom 6 < 9 → +1 instance = 100; m2 ineligible → m1. n[m1]=3, load=23

That is the aggregate-coupling problem exactly: t1 and t2 are individually cheaper on m1,
but *together* they fit one m2 instance with room left over. Verified by exhaustive
enumeration, neither escape works — all six orderings return 300 (greedy always takes m1
first because it is individually cheaper, and the cascade follows), and single-move
relocate does not recover either, since moving t1 alone to m2 costs +180 and saves only
100. The improving move is both tasks together.
"""

PROFILES = {
    "m1": {"throughput": 10, "gpus": 1, "price": 100, "reliability": 0.99, "latency": 50},
    "m2": {"throughput": 25, "gpus": 2, "price": 180, "reliability": 0.95, "latency": 80},
}

TASKS = {
    "t1": {"load": 8, "rel_floor": 0.90, "lat_ceil": 100},
    "t2": {"load": 6, "rel_floor": 0.90, "lat_ceil": 100},
    "t3": {"load": 9, "rel_floor": 0.98, "lat_ceil": 100},
}

# C(t), by construction from the floors — m2's reliability 0.95 < t3's floor 0.98
POOLS = {
    "t1": ["m1", "m2"],
    "t2": ["m1", "m2"],
    "t3": ["m1"],
}

BUDGET = 4

OPTIMUM = {
    "total_cost": 280,
    "routing": {"t1": "m2", "t2": "m2", "t3": "m1"},
    "provisioning": {"m1": 1, "m2": 1},
    "gpus_used": 3,
}

# What plain greedy returns on this instance, by hand-trace and by enumeration of all
# six orderings. Asserted at build step 9 — a different number means the myopia is not
# being reproduced, which is itself a bug.
GREEDY_EXPECTED_COST = 300


def build():
    """Return (tasks, pools, profiles, budget) as formulation types.

    An adapter only — the numbers above are the fixture and are not touched here.
    C(t) is taken from POOLS rather than recomputed, so a test that wants to check the
    floors derive the same pools can do that independently (test_invariants does).
    """
    from poc.formulation.types import ProfileSpec, Task, TaskId

    ids = {name: TaskId("wf", name) for name in TASKS}
    tasks = [
        Task(id=ids[name], task_type="generic", load=float(spec["load"]),
             rel_floor=spec["rel_floor"], lat_ceil=float(spec["lat_ceil"]))
        for name, spec in TASKS.items()
    ]
    pools = {ids[name]: list(POOLS[name]) for name in TASKS}
    profiles = {
        pid: ProfileSpec(id=pid, declared_type="generic",
                         throughput=float(spec["throughput"]), gpus=spec["gpus"],
                         price=float(spec["price"]), reliability=spec["reliability"],
                         latency=float(spec["latency"]))
        for pid, spec in PROFILES.items()
    }
    return tasks, pools, profiles, BUDGET


def task_id(name):
    """'t1' -> TaskId('wf', 't1'). For writing expectations readably in tests."""
    from poc.formulation.types import TaskId
    return TaskId("wf", name)
