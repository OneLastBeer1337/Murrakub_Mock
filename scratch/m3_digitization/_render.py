import sys

import fitz

doc = fitz.open(r"D:\osdi26-chaudhry.pdf")
page = doc[int(sys.argv[1])]
scale = float(sys.argv[2])
out = sys.argv[3]
clip = fitz.Rect(*[float(v) for v in sys.argv[4:8]]) if len(sys.argv) > 7 else None
pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=clip)
pix.save(out)
print(out, pix.width, "x", pix.height)
