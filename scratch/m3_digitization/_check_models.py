from optimization.profiles.model_profiles import ENERGY_PER_GPU, build_model_profiles
from optimization.profiles.provenance import Measured, Unavailable

profiles = build_model_profiles()
print("model profiles:", len(profiles))
for gpu, v in ENERGY_PER_GPU.items():
    print(f"  e_m[{gpu}] = {v.value:.4f} {v.unit}  band {v.band[0]:.3f}..{v.band[1]:.3f}")

print()
blocked = 0
for key in sorted(profiles, key=str):
    p = profiles[key]
    theta, ttft, tpot = p.theta(), p.ttft(), p.tpot()
    t = f"{theta.value:8.1f}" if isinstance(theta, Measured) else "  UNAVAIL"
    f = f"{ttft.value:7.3f}" if isinstance(ttft, Measured) else " UNAVAIL"
    o = f"{tpot.value:8.4f}" if isinstance(tpot, Measured) else " UNAVAIL"
    if isinstance(ttft, Unavailable):
        blocked += 1
    print(f"  {str(key):34s} theta={t} ttft={f} tpot={o} pts={len(p.curve):3d} "
          f"collapsed={len(p.collapsed_rows)}")

print(f"\nprofiles whose TTFT is Unavailable (eq.5 blocked): {blocked}/{len(profiles)}")
print("\nexample collapse record:")
for key in sorted(profiles, key=str):
    if profiles[key].collapsed_rows:
        print(" ", key)
        for line in profiles[key].collapsed_rows:
            print("   -", line)
        break
