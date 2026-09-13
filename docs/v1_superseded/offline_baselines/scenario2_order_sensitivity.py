"""
Offline MILP baseline, Scenario 2 (corrected) — a genuine order-sensitivity example,
hand-verified before running. 3 GPU slots would be over-tight (infeasible for
everyone); this uses 4 slots, matching the project's own worked example, but with
a reliability floor raised on classify_severity so ONLY large-model (2 slots)
survives — creating real contention with enrich_context's cheaper-but-bigger option.
"""

import pulp

CANDIDATES = {
    ("parse_log_line", "fast-parser"):     (0.002, 1),   # (cost, gpu_slots)
    ("classify_severity", "large-model"):  (0.030, 2),   # only survivor once floor is raised
    ("enrich_context", "lookup-tool"):     (0.006, 1),
    ("enrich_context", "rich-lookup"):     (0.004, 2),   # cheaper, but costs more capacity
}
TASKS = ["parse_log_line", "classify_severity", "enrich_context"]
TOTAL_GPU_SLOTS = 4

def run_heuristic(task_order):
    ledger = TOTAL_GPU_SLOTS
    assignment, total_cost = {}, 0.0
    for task in task_order:
        options = [(c, cost, gpu) for (t, c), (cost, gpu) in CANDIDATES.items() if t == task]
        survivors = [o for o in options if o[2] <= ledger]
        if not survivors:
            return None, None
        best = min(survivors, key=lambda o: o[1])
        assignment[task] = best[0]
        ledger -= best[2]
        total_cost += best[1]
    return assignment, total_cost

order_A = ["parse_log_line", "classify_severity", "enrich_context"]
order_B = ["parse_log_line", "enrich_context", "classify_severity"]

assign_A, cost_A = run_heuristic(order_A)
assign_B, cost_B = run_heuristic(order_B)

prob = pulp.LpProblem("Scenario2_OrderSensitivity", pulp.LpMinimize)
x = {(t, c): pulp.LpVariable(f"x_{t}_{c}", cat="Binary") for (t, c) in CANDIDATES}
prob += pulp.lpSum(CANDIDATES[(t, c)][0] * x[(t, c)] for (t, c) in CANDIDATES)
for task in TASKS:
    prob += pulp.lpSum(x[(t, c)] for (t, c) in CANDIDATES if t == task) == 1
prob += pulp.lpSum(CANDIDATES[(t, c)][1] * x[(t, c)] for (t, c) in CANDIDATES) <= TOTAL_GPU_SLOTS
prob.solve(pulp.PULP_CBC_CMD(msg=0))

status = pulp.LpStatus[prob.status]
milp_assignment, milp_cost, milp_gpu = {}, 0.0, 0
if status == "Optimal":
    for task in TASKS:
        for (t, c) in CANDIDATES:
            if t == task and x[(t, c)].value() == 1:
                cost, gpu = CANDIDATES[(t, c)]
                milp_assignment[task] = c
                milp_cost += cost
                milp_gpu += gpu

print("=" * 74)
print("SCENARIO 2 (corrected) — order sensitivity, 4 GPU slots, floor raised")
print("=" * 74)
print(f"\nHeuristic, order A {order_A}:")
print(f"    {assign_A} -> ${cost_A:.3f}" if assign_A else "    INFEASIBLE with this walk order")
print(f"\nHeuristic, order B {order_B}:")
print(f"    {assign_B} -> ${cost_B:.3f}" if assign_B else "    INFEASIBLE with this walk order")
print(f"\nMILP baseline (free, CBC), solver status: {status}")
print(f"    {milp_assignment} -> ${milp_cost:.3f}  (GPU used: {milp_gpu}/{TOTAL_GPU_SLOTS})")
print()
print("=" * 74)
if assign_A != assign_B:
    print("RESULT: the two walk orders give DIFFERENT outcomes for the same inputs —")
    print("        this is the order-sensitivity limitation, demonstrated concretely.")
    cheaper = "A" if (cost_A or 9e9) < (cost_B or 9e9) else "B"
    print(f"        Order {cheaper}'s result matches the MILP optimum" +
          (" exactly." if (assign_A if cheaper=='A' else assign_B) == milp_assignment else "; still not optimal."))
