"""Extract Figure 3 (p.570) from the OSDI PDF's VECTOR layer -- exact, not digitized pixels."""

import collections
import json

import fitz

ORANGE, BLUE = (1.0, 0.647, 0.0), (0.0, 0.0, 1.0)
GRAY = (0.69, 0.69, 0.69)
GPU_OF = {ORANGE: "A100", BLUE: "H100"}
# figure_labels.FIGURE_3_COVERAGE: TP=1 diamond, TP=2 triangle, TP=4 circle, TP=8 square
SHAPE_TP = {"circle": 4, "square": 8, "triangle": 2, "diamond": 1}

ROWS = [  # (y0, y1) gridline spans, top to bottom -> model, from the panel titles
    (234.2, 252.6, "DeepSeek-Qwen-32B"),
    (264.5, 283.0, "Gemma-3-27B"),
    (294.9, 313.3, "Llama-3.1-70B"),
    (325.2, 343.6, "Phi-4"),
    (355.5, 373.9, "NVLM-D-72B"),
]
COLS = [(60, 140, "tpot"), (140, 220, "ttft"), (220, 300, "tps_per_wh")]

doc = fitz.open(r"D:\osdi26-chaudhry.pdf")
page = doc[4]
drawings = page.get_drawings()


def rnd(c):
    return tuple(round(v, 3) for v in c) if c else None


def classify(d):
    kinds = [i[0] for i in d["items"]]
    if "c" in kinds:
        return "circle"
    if kinds == ["re"]:
        return "square"
    n = len(kinds)
    if n == 3:
        return "triangle"
    if n == 4:
        r = d["rect"]
        pts = []
        for it in d["items"]:
            for p in it[1:]:
                if hasattr(p, "x"):
                    pts.append((p.x, p.y))
        cx, cy = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
        # diamond: vertices lie on the bbox edge MIDPOINTS
        on_mid = sum(
            1 for x, y in pts if abs(x - cx) < r.width * 0.15 or abs(y - cy) < r.height * 0.15
        )
        return "diamond" if on_mid >= 3 else "square"
    return f"unknown{n}"


# ---- text: tick labels ----------------------------------------------------------------------
labels = []
for block in page.get_text("dict")["blocks"]:
    for line in block.get("lines", []):
        for span in line["spans"]:
            t = span["text"].strip()
            x0, y0, x1, y1 = span["bbox"]
            try:
                labels.append((float(t), (x0 + x1) / 2, (y0 + y1) / 2, x0, x1, y0, y1))
            except ValueError:
                pass


def fit(pairs):
    """pairs: [(device, data)] -> (scale, offset) so data = scale*device + offset"""
    if len(pairs) < 2:
        return None
    pairs = sorted(pairs)
    (d0, v0), (d1, v1) = pairs[0], pairs[-1]
    if d1 == d0:
        return None
    scale = (v1 - v0) / (d1 - d0)
    return scale, v0 - scale * d0


out = collections.defaultdict(list)
panels = {}

for (ry0, ry1, model) in ROWS:
    grid_row = [
        d for d in drawings
        if rnd(d.get("color")) == GRAY
        and d["rect"].width < 1.0
        and abs(d["rect"].y0 - ry0) < 1.5
        and abs(d["rect"].y1 - ry1) < 1.5
    ]
    for (cx0, cx1, metric) in COLS:
        xs = sorted(d["rect"].x0 for d in grid_row if cx0 <= d["rect"].x0 <= cx1)
        if not xs:
            continue
        px0, px1 = min(xs), max(xs)
        # x ticks: numeric labels just BELOW the panel AND horizontally inside it.
        # The `mx >= px0 - 2` guard is essential: without it the y-axis label "0.00", whose
        # centre sits just below the panel's bottom-left corner, is picked up as an x-tick at
        # value 0.0 and drags the whole x-scale (it shifted every series by ~+250 TPS).
        xt = [
            (mx, v)
            for v, mx, my, *_ in labels
            if ry1 < my < ry1 + 6 and px0 - 2 <= mx <= px1 + 2
        ]
        # y ticks: numeric labels wholly LEFT of the panel's left spine
        yt = [
            (my, v)
            for v, mx, my, lx0, lx1, ly0, ly1 in labels
            if ry0 - 3 < my < ry1 + 3 and cx0 - 12 < lx1 <= px0 - 0.3
        ]
        fx, fy = fit(xt), fit(yt)
        panels[(model, metric)] = dict(
            rect=(px0, ry0, px1, ry1), n_xticks=len(xt), n_yticks=len(yt), fx=fx, fy=fy
        )
        if not fx or not fy:
            continue

        for d in drawings:
            f = rnd(d.get("fill"))
            if f not in GPU_OF:
                continue
            r = d["rect"]
            mx, my = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
            if not (px0 - 1 <= mx <= px1 + 1 and ry0 - 1 <= my <= ry1 + 1):
                continue
            shape = classify(d)
            tp = SHAPE_TP.get(shape)
            if tp is None:
                continue
            out[(model, GPU_OF[f], tp, metric)].append(
                (round(fx[0] * mx + fx[1], 2), round(fy[0] * my + fy[1], 5))
            )

print("=== panel calibration ===")
for k, v in sorted(panels.items()):
    ok = "ok " if v["fx"] and v["fy"] else "FAIL"
    print(f"  {ok} {k[0]:20s} {k[1]:11s} xticks={v['n_xticks']:2d} yticks={v['n_yticks']:2d}")

print("\n=== series ===")
series = {}
for key in sorted(out):
    pts = sorted(set(out[key]))
    series["|".join(str(k) for k in key)] = pts
    model, gpu, tp, metric = key
    print(f"  {model:20s} {gpu} TP={tp} {metric:11s} n={len(pts):3d}  "
          f"x {pts[0][0]:8.1f}..{pts[-1][0]:8.1f}  y {min(p[1] for p in pts):.4f}..{max(p[1] for p in pts):.4f}")

json.dump(series, open("_fig3.json", "w"), indent=1)
print("\nwrote _fig3.json")
