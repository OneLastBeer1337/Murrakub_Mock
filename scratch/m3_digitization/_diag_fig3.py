import json

from optimization.profiles.sources.tables import TABLE_5_OSDI, TABLE_6_OSDI

series = json.load(open("_fig3.json"))

seen = set()
print(f"{'model':20s}{'gpu':5s}{'tp':>3s}{'tableTPS':>9s}{'tableTPOT':>10s}{'figTPS@same TPOT':>18s}{'ratio':>8s}")
ratios = []
for r in list(TABLE_6_OSDI) + list(TABLE_5_OSDI):
    key = (r.model, r.gpu, r.tp, r.tps, r.tpot_s)
    if key in seen:
        continue
    seen.add(key)
    pts = series.get(f"{r.model}|{r.gpu}|{r.tp}|tpot")
    if not pts:
        continue
    pts = sorted(pts)
    hit = None
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        lo, hi = min(y0, y1), max(y0, y1)
        if lo <= r.tpot_s <= hi and y1 != y0:
            hit = x0 + (x1 - x0) * (r.tpot_s - y0) / (y1 - y0)
            break
    if hit is None:
        print(f"{r.model:20s}{r.gpu:5s}{r.tp:3d}{r.tps:9.0f}{r.tpot_s:10.4f}{'out of range':>18s}{'--':>8s}")
        continue
    ratio = hit / r.tps
    ratios.append(ratio)
    print(f"{r.model:20s}{r.gpu:5s}{r.tp:3d}{r.tps:9.0f}{r.tpot_s:10.4f}{hit:18.0f}{ratio:8.3f}")

if ratios:
    ratios.sort()
    n = len(ratios)
    print(f"\nn={n}  ratio min={ratios[0]:.3f} median={ratios[n // 2]:.3f} max={ratios[-1]:.3f}")
    spread = ratios[-1] / ratios[0]
    print(f"spread max/min = {spread:.2f}  -> {'SYSTEMATIC scale error' if spread < 1.25 else 'NOT a single scale error'}")
