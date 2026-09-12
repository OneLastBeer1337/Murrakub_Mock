import collections

import fitz

doc = fitz.open(r"D:\osdi26-chaudhry.pdf")
page = doc[4]
drawings = page.get_drawings()


def rnd(c):
    return tuple(round(v, 3) for v in c) if c else None


GRAY = (0.69, 0.69, 0.69)
grid = [d for d in drawings if rnd(d.get("color")) == GRAY]
print("gray gridline objects:", len(grid))

vert, horiz = [], []
for d in grid:
    r = d["rect"]
    if r.width < 1.0 and r.height > 3:
        vert.append((round(r.x0, 1), round(r.y0, 1), round(r.y1, 1)))
    elif r.height < 1.0 and r.width > 3:
        horiz.append((round(r.y0, 1), round(r.x0, 1), round(r.x1, 1)))
print("vertical gridlines:", len(vert), " horizontal:", len(horiz))

# panels = clusters of gridlines sharing the same y-span (vertical) / x-span (horizontal)
spans = collections.Counter((y0, y1) for _x, y0, y1 in vert)
print("\ndistinct vertical-gridline y-spans (panel rows x cols):")
for (y0, y1), n in sorted(spans.items()):
    xs = sorted(x for x, a, b in vert if (a, b) == (y0, y1))
    print(f"  y {y0}..{y1}  n={n}  x from {xs[0]} to {xs[-1]}")

print("\ntext spans in the figure-3 band (y 240..430):")
d = page.get_text("dict")
for block in d["blocks"]:
    for line in block.get("lines", []):
        for span in line["spans"]:
            x0, y0, x1, y1 = span["bbox"]
            if 240 < y0 < 440 and span["text"].strip():
                print(f"  ({x0:6.1f},{y0:6.1f})-({x1:6.1f},{y1:6.1f})  {span['text']!r}")
