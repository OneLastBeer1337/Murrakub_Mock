import json

traces = json.load(open("_fig19.json"))

lines = []
lines.append("# " + "=" * 91)
lines.append("# Figure 19 (p.587) -- the Azure arrival traces, the sole source of lambda^peak/lambda^avg")
lines.append("# " + "=" * 91)
lines.append("#")
lines.append("# Section 4.1 (p.576), verbatim: \"we approximate workload arrivals using LLM serving")
lines.append("# traces collected over a 24-hour period in May 2024 from Azure's LLM inference service")
lines.append("# for chat and coding applications [78]\", and \"We map the chat requests from the trace")
lines.append("# to the video Q/A workflow and coding requests to the code generation workflow.\"")
lines.append("# A.4 (p.587) fixes the window: \"from 08:00 05/15/2024 to 08:00 05/16/2024\".")
lines.append("#")
lines.append("# Extracted from the VECTOR layer, not from pixels: each series is a single stroked")
lines.append("# matplotlib polyline (tab10 blue = Chat, tab10 orange = Coding) whose vertices ARE the")
lines.append("# plotted samples. Axes calibrated from the tick-label text positions (x: 0..25 h,")
lines.append("# y: 2000/4000 req/min). The legend swatches -- 4-point horizontal segments at the same")
lines.append("# two colours -- are excluded by requiring more than 10 vertices.")
lines.append("#")
lines.append("# NOTE: t=0 is 08:00 local on 2024-05-15, NOT midnight. Any diurnal claim about these")
lines.append("# traces has to shift by 8 h, and `arrivals.py` keeps epochs in trace-relative hours so")
lines.append("# the offset is never silently applied twice.")
lines.append("")
for name, pts in sorted(traces.items()):
    body = ",\n        ".join(
        ", ".join(f"({t:g}, {v:g})" for t, v in pts[i : i + 4]) for i in range(0, len(pts), 4)
    )
    lines.append(f"FIG_19_{name.upper()}: Final[tuple[tuple[float, float], ...]] = (")
    lines.append(f"        {body},")
    lines.append(")")
    lo = min(v for _t, v in pts)
    hi = max(v for _t, v in pts)
    wf = "video_qa" if name == "chat" else "code_generation"
    lines.append(
        f'"""({name}) -> `{wf}`. {len(pts)} samples over 0..24 h; '
        f"{lo:.0f}..{hi:.0f} req/min.\"\"\""
    )
    lines.append("")

lines.append("FIG_19_SERIES_TO_WORKFLOW: Final[dict[str, str]] = {")
lines.append('    "chat": "video_qa",')
lines.append('    "coding": "code_generation",')
lines.append("}")
lines.append('"""Section 4.1 (p.576). The mapping is the paper\'s, not ours."""')

block = "\n".join(lines)
path = "optimization/profiles/sources/figures_digitized.py"
src = open(path, encoding="utf-8").read()
assert "# @@FIG19@@" in src
open(path, "w", encoding="utf-8", newline="\n").write(src.replace("# @@FIG19@@", block))
print("wrote FIG_19 block:", {k: len(v) for k, v in traces.items()})
