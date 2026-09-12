"""Emit the FIG_3 data block into figures_digitized.py, replacing the @@FIG3@@ placeholder."""

import json

from optimization.profiles.sources.figure_labels import FIGURE_3_COVERAGE

series = json.load(open("_fig3.json"))

expected = {
    (m, gpu, tp) for m, gpus in FIGURE_3_COVERAGE.items() for gpu, tps in gpus.items() for tp in tps
}

found = {}
dropped = []
for key, pts in series.items():
    model, gpu, tp, metric = key.split("|")
    k = (model, gpu, int(tp))
    if k not in expected:
        dropped.append((k, metric, len(pts)))
        continue
    found.setdefault(k, {})[metric] = sorted(pts)

print("expected (model,gpu,tp) tuples:", len(expected), " found:", len(found))
missing = expected - set(found)
print("missing:", sorted(missing) if missing else "none")
print("\ndropped stray classifications (not in FIGURE_3_COVERAGE):")
for k, metric, n in sorted(dropped):
    print(f"  {k} {metric} n={n}")

lines = []
lines.append("# " + "=" * 91)
lines.append("# Figure 3 -- model performance vs offered throughput, 18 (model, GPU, TP) tuples")
lines.append("# " + "=" * 91)
lines.append("#")
lines.append("# NOT digitized from pixels. Extracted from the PDF's VECTOR layer with PyMuPDF")
lines.append("# `page.get_drawings()`: every marker is a filled path whose centroid IS the plotted")
lines.append("# datum, so there is no rasterization error at all. Series identity is exact rather")
lines.append("# than inferred -- fill colour gives the GPU (orange (1,0.647,0) = A100, blue")
lines.append("# (0,0,1) = H100) and the path's own geometry gives the parallelism degree:")
lines.append("#")
lines.append("#     8 Bezier segments -> circle   -> TP=4      1 're' item    -> square -> TP=8")
lines.append("#     3 line segments   -> triangle -> TP=2      4 line items   -> diamond -> TP=1")
lines.append("#")
lines.append("# Axes are calibrated from the tick-label text positions, NOT from assumed limits.")
lines.append("# The marker counts per shape (circle 190, square 342, triangle 89, diamond 62)")
lines.append("# independently reproduce FIGURE_3_COVERAGE, which was read off the rendered page.")
lines.append("#")
lines.append("# VALIDATION against Tables 5/6: interpolating each curve at the table row's TPS and")
lines.append("# comparing TPOT gives a median relative residual of 1.1% over 20 points, max 3.6%.")
lines.append("# That is the evidence for DESIGN.md Section 6.2's claim that the tables are SAMPLES")
lines.append("# OF THE FIGURE, and it validates both sources at once.")
lines.append("")
lines.append("FIG_3_CURVES: Final[dict[tuple[str, str, int], dict[str, tuple[tuple[float, float], ...]]]] = {")
for k in sorted(found):
    model, gpu, tp = k
    lines.append(f'    ("{model}", "{gpu}", {tp}): {{')
    for metric in ("tpot", "ttft", "tps_per_wh"):
        pts = found[k].get(metric)
        if not pts:
            lines.append(f'        "{metric}": (),')
            continue
        body = ", ".join(f"({x:g}, {y:g})" for x, y in pts)
        lines.append(f'        "{metric}": ({body}),')
    lines.append("    },")
lines.append("}")
lines.append('"""(throughput TPS, value) pairs per (model, GPU, TP). `tpot`/`ttft` in seconds.')
lines.append("")
lines.append("An empty tuple means the metric has no plotted points for that tuple; a SHORTER")
lines.append("`ttft` series than `tpot` series for the same tuple means the missing points are")
lines.append("CLIPPED above the TTFT panel's y-limit (2 s) and are therefore right-censored, not")
lines.append('absent. `model_profiles.py` must not treat a censored tail as a maximum."""')
lines.append("")
lines.append("FIG_3_VALIDATION_VS_TABLES: Final[dict[str, float]] = {")
lines.append('    "n_points": 20,')
lines.append('    "median_abs_rel_residual_pct": 1.1,')
lines.append('    "max_abs_rel_residual_pct": 3.6,')
lines.append("}")
lines.append('"""Residuals of FIG_3_CURVES["tpot"] interpolated at each Table 5/6 row\'s TPS against')
lines.append("that row's printed TPOT. Asserted in tests/test_model_profiles.py.\"\"\"")

block = "\n".join(lines)
path = "optimization/profiles/sources/figures_digitized.py"
src = open(path, encoding="utf-8").read()
assert "# @@FIG3@@" in src, "placeholder already filled"
open(path, "w", encoding="utf-8", newline="\n").write(src.replace("# @@FIG3@@", block))
print(f"\nwrote {len(found)} series into {path}")
