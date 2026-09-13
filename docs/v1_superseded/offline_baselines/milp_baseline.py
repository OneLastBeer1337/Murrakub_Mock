"""
Offline MILP baseline — free, open-source, no CPLEX/Gurobi license needed.

Solves the exact same allocation problem as the project's heuristic (Algorithm B1),
using PuLP as the modeling layer and CBC (COIN-OR Branch and Cut) as the solver —
both fully open source, zero cost, no registration.

This reproduces the worked example from Architecture_Design.md Section 3.5:
the OS-log DAG (parse_log_line -> classify_severity + enrich_context -> generate_report),
with the same candidate table, floors, and 4-GPU-slot ledger.

Run: python3 milp_baseline.py
"""

import pulp

# ---------------------------------------------------------------------------
# 1. The same candidate data from Architecture_Design.md's worked example
# ---------------------------------------------------------------------------
# (task, candidate) -> (cost, latency_ms, reliability, gpu_slots)
CANDIDATES = {
    ("parse_log_line", "fast-parser"):      (0.002, 40,  0.97,  1),
    ("parse_log_line", "thorough-parser"):  (0.006, 90,  0.995, 1),
    ("classify_severity", "small-model"):   (0.010, 60,  0.94,  1),
    ("classify_severity", "large-model"):   (0.030, 150, 0.99,  2),
    ("enrich_context", "lookup-tool"):      (0.001, 20,  0.999, 1),
    ("generate_report", "template-fill"):   (0.004, 30,  0.98,  1),
}

# Per-task-type floors, same as the worked example
FLOORS = {
    "parse_log_line":    {"reliability": 0.95, "latency": 999},
    "classify_severity":  {"reliability": 0.90, "latency": 999},
    "enrich_context":     {"reliability": 0.00, "latency": 999},
    "generate_report":    {"reliability": 0.00, "latency": 999},
}

TOTAL_GPU_SLOTS = 4
TASKS = ["parse_log_line", "classify_severity", "enrich_context", "generate_report"]

# ---------------------------------------------------------------------------
# 2. Formulate as a MILP — same objective/constraints as the equation slide,
#    now solved EXACTLY (jointly, not one task at a time) instead of greedily
# ---------------------------------------------------------------------------
prob = pulp.LpProblem("OfflineBaseline_OSLogAllocation", pulp.LpMinimize)

# One binary decision variable per (task, candidate): 1 if chosen, 0 if not
x = {}
for (task, cand), (cost, lat, rel, gpu) in CANDIDATES.items():
    x[(task, cand)] = pulp.LpVariable(f"x_{task}_{cand}", cat="Binary")

# Objective: minimize total cost across the whole DAG, jointly
prob += pulp.lpSum(
    CANDIDATES[(task, cand)][0] * x[(task, cand)]
    for (task, cand) in CANDIDATES
), "TotalCost"

# Constraint: exactly one candidate chosen per task
for task in TASKS:
    prob += pulp.lpSum(
        x[(t, c)] for (t, c) in CANDIDATES if t == task
    ) == 1, f"OneCandidate_{task}"

# Constraint: reliability floor per task-type
for (task, cand), (cost, lat, rel, gpu) in CANDIDATES.items():
    floor = FLOORS[task]["reliability"]
    if rel < floor:
        # This candidate can never be chosen if it fails the floor
        prob += x[(task, cand)] == 0, f"ReliabilityFloor_{task}_{cand}"

# Constraint: total GPU slots used across ALL tasks jointly <= capacity
# (this is the one thing the heuristic can only approximate via ledger order —
#  the MILP sees all tasks' resource needs simultaneously)
prob += pulp.lpSum(
    CANDIDATES[(task, cand)][3] * x[(task, cand)]
    for (task, cand) in CANDIDATES
) <= TOTAL_GPU_SLOTS, "TotalGPUCapacity"

# ---------------------------------------------------------------------------
# 3. Solve with CBC — free, open source, already installed with PuLP
# ---------------------------------------------------------------------------
solver = pulp.PULP_CBC_CMD(msg=0)  # msg=0 to suppress solver's own verbose log
prob.solve(solver)

print("=" * 70)
print("OFFLINE MILP BASELINE — solved with PuLP + CBC (free, open source)")
print("=" * 70)
print(f"Solver status: {pulp.LpStatus[prob.status]}")
print()

total_cost = 0.0
total_gpu = 0
for task in TASKS:
    for (t, cand) in CANDIDATES:
        if t == task and x[(t, cand)].value() == 1:
            cost, lat, rel, gpu = CANDIDATES[(t, cand)]
            total_cost += cost
            total_gpu += gpu
            print(f"  {task:20s} -> {cand:16s}  cost=${cost:.3f}  "
                  f"latency={lat}ms  reliability={rel:.3f}  gpu={gpu}")

print()
print(f"TOTAL COST (MILP-optimal, exact):  ${total_cost:.3f}")
print(f"TOTAL GPU SLOTS USED:               {total_gpu} / {TOTAL_GPU_SLOTS}")
print()
print("-" * 70)
print("COMPARISON — the heuristic (Algorithm B1) picked, per")
print("Architecture_Design.md Section 3.5's worked example:")
print("-" * 70)
print("  parse_log_line       -> fast-parser        cost=$0.002")
print("  classify_severity    -> small-model         cost=$0.010")
print("  enrich_context       -> lookup-tool          cost=$0.001")
print("  generate_report      -> template-fill        cost=$0.004")
print("  TOTAL COST (heuristic, greedy):     $0.017")
print()
gap = total_cost - 0.017
print(f"Gap between heuristic and MILP-optimal on THIS example: ${gap:.3f}  "
      f"({'heuristic already optimal' if abs(gap) < 1e-9 else 'heuristic sub-optimal by this much'})")
