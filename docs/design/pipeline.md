# Pipeline — ASCII Diagrams

End-to-end visual reference of the PoC pipeline, from problem input through track
execution to metric aggregation. Companion to `System_Architecture_v2.md` (formulation
and design) and `poc_findings.md` (current measurements). Documentation-only — no source
changes.

---

## 0. Top-level pipeline

```
+--------------------+      +--------------------+      +----------------------+
|  PROBLEM INPUT     |      |  INSTANCE LAYER    |      |  CORE STATE          |
|  (workflow DAGs,   | ---> |  (synthetic +      | ---> |  (ProvisioningState, |
|   profiles, budget)|      |   hand-verified    |      |   invariants)        |
+--------------------+      |   fixtures)        |      +----------------------+
                            +--------------------+                |
                                                                   v
+--------------------+      +--------------------+      +----------------------+
|  METRICS / OUTPUT  | <--- |  HARNESS           | <--- |  TRACKS (allocators) |
|  (tables, gaps,    |      |  (matched-condition|      |  exact_milp, A, A+M1,|
|   feasibility)     |      |   runner, sweep)   |      |  B/B-cold, C, C2,    |
+--------------------+      +--------------------+      |  STATIC)             |
                                                       +----------------------+
```

---

## 1. Instance layer (input construction)

```
                +---------------------------+
                |  ProfileSpec list         |  (m: thr, gpu, price, rel, lat)
                +---------------------------+
                            |
                            v
+---------------------------------------------+
|  Generator (uniform or structured)          |
|  - sample tasks t (load, relFloor, latCeil)  |
|  - sample profiles m                        |
|  - derive C(t) via eligibility filter       |
+---------------------------------------------+
                            |
                            v
+---------------------------------------------+       +----------------------------+
|  ProblemInstance                            |       |  Reference allocation      |
|  - tasks, profiles, C(t), budget B          | ----> |  (GPU-efficient, F2 anchor)|
+---------------------------------------------+       +----------------------------+

  Optional override:
  +---------------------------------------------+
  |  Hand-verified fixture: adversarial_3t2p   |
  |  - 2 profiles, 3 tasks, B=4, opt=280        |
  +---------------------------------------------+
```

---

## 2. Invariant gating (runs on every result)

```
                  AllocationResult (x, n, cost, feasible)
                                 |
                                 v
                  +------------------------------+
                  |  invariants.check()          |
                  |  I1  every task routed once  |
                  |  I2  load <= n[m]*thr(m)     |
                  |  I3  total gpu <= B          |
                  |  I4  routed m in C(t)        |
                  |  I5  n[m] >= 1 if used       |
                  +------------------------------+
                          |                |
                       PASS             FAIL -> raise / discard
                          |
                          v
                     Harness records
```

---

## 3. Tracks (allocators) — all return `AllocationResult`

```
                       +-------------------+
                       |  allocate(...)    |  uniform signature
                       +---------+---------+
                                 |
   +-------------+----------+----+----+---------+--------------+----------+
   |             |          |         |         |              |          |
   v             v          v         v         v              v          v
+--------+  +---------+  +------+  +------+  +--------+  +-----------+  +-------+
| exact  |  | STATIC  |  |  A   |  | A+M1 |  |   B    |  | B-cold    |  |  C    |
| _milp  |  | (no     |  |(greedy|  |(greedy|  |(Lagr.  |  |(Lagr.    |  |(LP +  |
| (PuLP/ |  |  optim.)|  | constr|  | +look-|  | relax  |  | no warm  |  | round)|
|  CBC)  |  |         |  | uct.) |  | ahead)|  | (C1))  |  | start)   |  |       |
+--------+  +---------+  +------+  +------+  +--------+  +-----------+  +-------+
                                  +------+                                       +-------+
                                  | C2   |  (LP + round + 2 realisation orders)  | MILP  |
                                  +------+                                       +-------+
                                                                                (same as
                                                                                 exact)
```

---

## 4. Track A (greedy) and A+M1 (with M1 lookahead)

```
+----------------------------------+
|  tasks (orderable, seed-driven)  |
+----------------------------------+
                |
                v
+----------------------------------+
|  for each task t in order:       |
|   for each profile m in C(t):    |
|     candidate = state.cost_to_   |
|       admit(t, m)                |
|     [A+M1 only]  feasibility     |
|        lookahead on remaining    |
|        tasks vs remaining budget |
|   pick argmin candidate          |
|   state.admit(t, pick)           |
+----------------------------------+
                |
                v
       build_provisioning() -> n
       AllocationResult(x, n)
```

---

## 5. Track C (LP + rounding + repair)

```
+---------------------------+        +----------------------------+
|  LP relaxation of full IP | -----> |  argmax x[t][m] per task   |
|  (x in [0,1], n >= 0)     |        |  (routing is integral 96%  |
+---------------------------+        |   of the time, F6)         |
                                      +----------------------------+
                                                   |
                                                   v
                                      +----------------------------+
                                      |  ceil(n[m]) -> instance    |
                                      |  counts from LP            |
                                      +----------------------------+
                                                   |
                                                   v
                                      +----------------------------+
                                      |  Realise in C(t) via       |
                                      |  shared decision rule      |
                                      |  select_profile(...)       |
                                      |  (C  = one order,          |
                                      |   C2 = two orders)         |
                                      +----------------------------+
                                                   |
                                                   v
                                           AllocationResult
```

---

## 6. Track B (Lagrangian relaxation, relaxing C1)

```
+----------------------------------------------------+
|  Initialise multipliers lambda[t] = 0              |
|  best_upper = INF, best_lower = -INF               |
+----------------------------------------------------+
                          |
                          v
+----------------------------------------------------+
|  Subgradient loop, up to 120 iters:                |
|                                                    |
|   For each profile m, solve subproblem:            |
|     n[m] = argmax  lambda' * load_x                |
|              - price(m) * n                        |
|              s.t.  load routed <= n * thr(m)       |
|     (exact 0/1 knapsack DP per profile)            |
|                                                    |
|   Lower bound  L =  sum_m n[m] * price(m)          |
|                 + sum_t lambda[t]                   |
|   Upper bound  U =  primal repair via              |
|                   select_profile (greedy-equivalent)|
|                                                    |
|   Update lambda[t] via subgradient step            |
|     (step size, tolerance = untuned defaults, O5)  |
|                                                    |
|   Stop when |U - L| / max(1, |U|) < tol            |
+----------------------------------------------------+
                          |
                          v
                  AllocationResult (from U),
                  bound_gap reported (L vs MILP opt)
```

---

## 7. Harness (matched-condition runner)

```
+-------------------+      +---------------------+      +--------------------+
|  sweep(n_tasks,   | ---> |  for each (tightness| ---> |  for each seed:    |
|   n_profiles,     |      |  seed):             |      |   ProblemInstance  |
|   tightness[],    |      |    run all enabled  |      |     from generator |
|   seeds[])        |      |    conditions on    |      +--------------------+
+-------------------+      |    same instance    |                |
                          +---------------------+                v
                                                  +----------------------------+
                                                  |  collect records           |
                                                  |  (cond, inst, feas, gap%,  |
                                                  |   bound_gap%, time)        |
                                                  +----------------------------+
                                                                |
                                                                v
                                                +------------------------------+
                                                |  metrics.summarise /         |
                                                |  metrics.solvability /       |
                                                |  metrics.format_table        |
                                                +------------------------------+
                                                                |
                                                                v
                                                       docs/evidence/poc_findings.md
```

---

## 8. Decision-rule internals (used by A, A+M1, B, C, C2)

```
+----------------------------------+
|  ProvisioningState               |
|  - profiles, budget,             |
|    n[m], load[m]                 |
+----------------------------------+
                ^
                |  cost_to_admit(t, m) -> AdmitCost(extra_instances,
                |                                        extra_gpus,
                |                                        extra_cost)
                |
+----------------------------------+
|  select_profile(task,            |
|    pool=C(t), state, cost_adjust)|
|  pick argmin candidate,          |
|  None if all ineligible          |
+----------------------------------+
                |
                v
        state.admit(task, pick)
```

---

## 9. End-to-end ASCII recap

```
   workflows(DAG) + profiles
            |
            v
   +------------------+        +-------------------+
   | ProblemInstance  | -----> |  invariants       | <-- on every result
   |  tasks, C(t), B  |        |  I1..I5           |
   +------------------+        +-------------------+
            |
            +--> exact_milp (PuLP/CBC) ----+
            +--> STATIC ------------------+
            +--> Track A  ----------------+--> AllocationResult --> metrics
            +--> Track A+M1 --------------+        |
            +--> Track B   --------------+        v
            +--> Track B-cold -----------+   docs/evidence/poc_findings.md
            +--> Track C   --------------+
            +--> Track C2  --------------+

   Track B additionally reports a lower bound
   compared against exact optimum (T1).
```

---

## Out of pipeline (deliberately not built)

- Executor registry, profiling, execution, drift/re-optimisation
- Zookeeper / LogHub domain data
- Monitoring, fallback, framework integration
- Track A relocate / consolidate / elaborate multi-start
- Track B relaxing (C3) — only (C1) is implemented
- Murakkab as a separate condition (its model == the exact MILP here)
