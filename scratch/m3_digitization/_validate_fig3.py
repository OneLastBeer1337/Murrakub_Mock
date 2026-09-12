import json

from optimization.profiles.sources.tables import TABLE_5_OSDI, TABLE_6_OSDI

series = json.load(open("_fig3.json"))


def curve(model, gpu, tp, metric):
    return series.get(f"{model}|{gpu}|{tp}|{metric}")


def interp(pts, x):
    pts = sorted(pts)
    xs = [p[0] for p in pts]
    if x < xs[0] or x > xs[-1]:
        return None, f"outside [{xs[0]:.0f},{xs[-1]:.0f}]"
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            if x1 == x0:
                return y0, "exact"
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0), "interp"
    return None, "gap"


rows = []
for r in TABLE_6_OSDI:
    rows.append(("code_gen", r.model, r.gpu, r.tp, r.tps, r.tpot_s))
for r in TABLE_5_OSDI:
    rows.append(("video", r.model, r.gpu, r.tp, r.tps, r.tpot_s))

print(f"{'model':22s}{'gpu':5s}{'tp':>3s}{'TPS':>7s}{'table':>9s}{'figure':>9s}{'resid%':>8s}  note")
resids = []
for wf, model, gpu, tp, tps, tpot in rows:
    pts = curve(model, gpu, tp, "tpot")
    if not pts:
        print(f"{model:22s}{gpu:5s}{tp:3d}{tps:7.0f}{tpot:9.4f}{'--':>9s}{'--':>8s}  no figure-3 series")
        continue
    got, note = interp(pts, tps)
    if got is None:
        print(f"{model:22s}{gpu:5s}{tp:3d}{tps:7.0f}{tpot:9.4f}{'--':>9s}{'--':>8s}  {note}")
        continue
    rel = (got - tpot) / tpot * 100
    resids.append(abs(rel))
    print(f"{model:22s}{gpu:5s}{tp:3d}{tps:7.0f}{tpot:9.4f}{got:9.4f}{rel:8.1f}  {note}")

if resids:
    resids.sort()
    print(f"\nn={len(resids)}  median |resid| = {resids[len(resids)//2]:.1f}%  max = {resids[-1]:.1f}%")
