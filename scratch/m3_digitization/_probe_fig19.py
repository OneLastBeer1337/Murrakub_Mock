import collections

import fitz

doc = fitz.open(r"D:\osdi26-chaudhry.pdf")
page = doc[21]  # printed p.587, Figure 19
drawings = page.get_drawings()
print("drawings:", len(drawings))

cnt = collections.Counter()
for d in drawings:
    c = tuple(round(v, 3) for v in d["color"]) if d.get("color") else None
    f = tuple(round(v, 3) for v in d["fill"]) if d.get("fill") else None
    npts = sum(len(i) - 1 for i in d["items"])
    cnt[(c, f)] += 1
    if c and c not in ((0.0, 0.0, 0.0), (0.69, 0.69, 0.69)) and npts > 20:
        r = d["rect"]
        print(f"  LONG PATH stroke={c} items={len(d['items'])} pts~{npts} "
              f"rect=({r.x0:.1f},{r.y0:.1f})-({r.x1:.1f},{r.y1:.1f})")

print("\ncolour census:")
for k, n in cnt.most_common(10):
    print("  ", k, n)

print("\ntext near figure 19 (bottom-left of page):")
for block in page.get_text("dict")["blocks"]:
    for line in block.get("lines", []):
        for span in line["spans"]:
            x0, y0, x1, y1 = span["bbox"]
            if x0 < 300 and y0 > 300 and span["text"].strip():
                print(f"  ({x0:6.1f},{y0:6.1f})-({x1:6.1f},{y1:6.1f}) {span['text']!r}")
