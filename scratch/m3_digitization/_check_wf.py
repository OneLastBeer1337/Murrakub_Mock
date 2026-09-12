from optimization.profiles.provenance import Measured, Unavailable
from optimization.profiles.schema import TokenDistribution
from optimization.profiles.workflow_profiles import build_workflow_profiles

profiles = build_workflow_profiles()
print("workflow profiles:", len(profiles))

acc_gap = [k for k, p in profiles.items() if isinstance(p.accuracy, Unavailable)]
tok_gap = [k for k, p in profiles.items() if isinstance(p.tokens, Unavailable)]
print(f"a_c Unavailable: {len(acc_gap)}   t_c Unavailable: {len(tok_gap)}")
print("  a_c gap models:", sorted({k.knob['model'] for k in acc_gap}))
print("  t_c gap models:", sorted({k.knob['model'] for k in tok_gap}))

print("\nsample p90 token values (t_c):")
for k in sorted(profiles, key=str):
    p = profiles[k]
    if isinstance(p.tokens, TokenDistribution):
        v = p.tokens.p90()
        a = p.accuracy
        astr = f"{a.value:5.2f}%" if isinstance(a, Measured) else " UNAVAIL"
        print(f"  {str(k):58s} a_c={astr}  t_c(p90)={v.value:9.1f}  [{v.band[0]:.0f},{v.band[1]:.0f}]")

print("\nboth available (usable by M4):",
      sum(1 for p in profiles.values()
          if isinstance(p.accuracy, Measured) and isinstance(p.tokens, TokenDistribution)))
