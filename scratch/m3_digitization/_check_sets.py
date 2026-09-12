import random

from optimization.profiles.profile_sets import NAMED_SETS, profile_set, resample

for name in NAMED_SETS:
    ps = profile_set(name)
    rep = ps.coverage_report()
    totals = rep.total_by_provenance()
    n = sum(totals.values())
    unavail = totals.get("UNAVAILABLE", 0)
    print(f"{name:14s} values={n:4d}  unavailable={unavail:3d} ({unavail / n * 100:4.1f}%)  "
          f"eq5-blocked={rep.blocked('eq5'):3d}")
    if name == "baseline":
        print("     provenance split:")
        for k, v in totals.items():
            print(f"       {k:20s} {v:4d}  {v / n * 100:5.1f}%")

base = profile_set("baseline")
print("\ntier reconstruction:")
for wf, r in base.tier_reconstruction.items():
    if isinstance(r, dict) and "residuals" in r:
        print(f"  {wf:16s} within_band={r['within_band']}  "
              f"residuals={ {k: round(v, 2) for k, v in r['residuals'].items()} }")

mi = base.to_milp_inputs()
print("\nMilpInputs:")
print("  a_c", len(mi.a_c), " t_c", len(mi.t_c), " theta_m", len(mi.theta_m), " tau", len(mi.tau))
print("  lam_peak", len(mi.lam_peak), " alpha", mi.alpha.value)
print("  data_excluded:", len(mi.data_excluded))
print("  A5_PARAMETERS:", len(mi.A5_PARAMETERS))

print("\noperating-point collapse records:", len(base.operating_point_collapse))
r = resample(base, random.Random(7))
print("resample ok ->", r.name)
