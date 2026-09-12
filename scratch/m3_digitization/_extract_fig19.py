import json

import fitz

TAB10_BLUE = (0.122, 0.467, 0.706)   # "Chat"   -> video Q/A   (Section 4.1, p.576)
TAB10_ORANGE = (1.0, 0.498, 0.055)   # "Coding" -> code generation

doc = fitz.open(r"D:\osdi26-chaudhry.pdf")
page = doc[21]
drawings = page.get_drawings()


def rnd(c):
    return tuple(round(v, 3) for v in c) if c else None


paths = {}
for d in drawings:
    c = rnd(d.get("color"))
    if c not in (TAB10_BLUE, TAB10_ORANGE):
        continue
    pts = []
    for it in d["items"]:
        for p in it[1:]:
            if hasattr(p, "x"):
                pts.append((p.x, p.y))
    r = d["rect"]
    print(f"{'chat' if c == TAB10_BLUE else 'coding':7s} pts={len(pts):4d} "
          f"rect=({r.x0:.1f},{r.y0:.1f})-({r.x1:.1f},{r.y1:.1f})")
    if len(pts) > 10:
        paths["chat" if c == TAB10_BLUE else "coding"] = pts

# axis calibration from tick labels around the figure (caption at y~349)
labels = []
for block in page.get_text("dict")["blocks"]:
    for line in block.get("lines", []):
        for span in line["spans"]:
            t = span["text"].strip()
            x0, y0, x1, y1 = span["bbox"]
            if 250 < y0 < 350 and x0 < 310:
                try:
                    labels.append((float(t), (x0 + x1) / 2, (y0 + y1) / 2, x1))
                except ValueError:
                    pass

allx = [p[0] for pts in paths.values() for p in pts]
ally = [p[1] for pts in paths.values() for p in pts]
print("\npath device extent: x", round(min(allx), 1), round(max(allx), 1),
      " y", round(min(ally), 1), round(max(ally), 1))
print("candidate labels:", [(v, round(mx, 1), round(my, 1)) for v, mx, my, _ in labels])

xt = [(mx, v) for v, mx, my, _ in labels if my > max(ally) - 2]
yt = [(my, v) for v, mx, my, lx1 in labels if lx1 < min(allx) + 1]
print("x ticks:", xt)
print("y ticks:", yt)


def fit(pairs):
    pairs = sorted(pairs)
    (d0, v0), (d1, v1) = pairs[0], pairs[-1]
    s = (v1 - v0) / (d1 - d0)
    return s, v0 - s * d0


fx, fy = fit(xt), fit(yt)
out = {}
for name, pts in paths.items():
    conv = sorted({(round(fx[0] * x + fx[1], 4), round(fy[0] * y + fy[1], 1)) for x, y in pts})
    out[name] = conv
    print(f"\n{name}: n={len(conv)}  t {conv[0][0]:.2f}..{conv[-1][0]:.2f} h   "
          f"load {min(p[1] for p in conv):.0f}..{max(p[1] for p in conv):.0f} req/min")

json.dump(out, open("_fig19.json", "w"), indent=1)
print("\nwrote _fig19.json")
