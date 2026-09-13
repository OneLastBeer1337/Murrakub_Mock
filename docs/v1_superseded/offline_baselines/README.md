> **SUPERSEDED — v1.** Not current. See `docs/v1_superseded/README.md` for what
> replaced this and why. Do not build from it.

---

# Offline MILP Baseline — Free, No CPLEX License Needed

Answers the "MILP → solver, CPLEX?" question from the advisor consult concretely:
this is a working offline baseline, solved with **PuLP + CBC** — both fully open
source, zero cost, no registration or license of any kind.

## Two ways to get CPLEX/Gurobi-grade solving for free, in order of effort

1. **Check for a free academic license first.** IBM (CPLEX) and Gurobi both offer
   full-featured, no-size-limit academic editions for free to students/faculty at
   an accredited university — just needs a university email. If that applies to
   you, this may resolve the cost concern without switching tools at all. Worth
   checking before building anything.
2. **CBC (this folder)** — if you want something with zero license dependency at
   all, no registration, works anywhere. Won't match CPLEX's raw speed on huge
   industrial problems, but for workflow-sized allocation problems like this
   project's, it's more than sufficient as an offline comparison baseline.

## Files

- **`milp_baseline.py`** — solves the exact worked example from
  `Architecture_Design.md` Section 3.5 (the OS-log DAG, 4 candidate tasks, 4 GPU
  slots) as a proper MILP, and prints a direct comparison against what the
  heuristic (Algorithm B1) picked. On this example, the heuristic already matches
  the true optimum — a useful, honest result to report as-is.
- **`scenario2_fixed.py`** — a second, deliberately tighter scenario, hand-verified
  before running, that demonstrates the actual order-sensitivity limitation
  flagged in the architecture doc: the same inputs, walked in a different task
  order, produce a different outcome — one order matches the MILP's true optimum,
  the other is infeasible outright. This is the concrete evidence for exactly the
  limitation described in Section 3.5's worked example.

## Run it

```bash
pip install pulp --break-system-packages   # only dependency; CBC ships with it
python3 milp_baseline.py
python3 scenario2_fixed.py
```

## How this plugs into the actual project

Both scripts follow the same shape as Algorithm B1/B2 in `Architecture_Design.md` —
same candidate data structure `(task, candidate) -> (cost, latency, reliability, gpu)`,
same floors, same ledger concept. For a real evaluation run (Stage 8 in
`Project_Schedule.md`), this is the pattern to extend: load the actual profiled
candidate data instead of the worked-example numbers, and run it once per
evaluation scenario to get the true-optimal comparison point.

## Formulation, for reference (matches the "equations" slide)

```
minimize      sum of cost(t, c) * x[t, c]

subject to    sum over c of x[t, c] == 1              for every task t
              x[t, c] == 0                              if reliability(t,c) < floor(t)
              sum of gpu_slots(t, c) * x[t, c] <= TOTAL_CAPACITY

over          x[t, c] in {0, 1}
```

The one thing this formulation does that the heuristic structurally cannot: the
GPU-capacity constraint sums across **every task at once**, so the solver sees the
whole picture before committing to anything — no walk order, no early commitment
that later turns out to be a mistake.
