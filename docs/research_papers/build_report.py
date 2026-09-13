#!/usr/bin/env python3
import json, os, datetime, subprocess, sys

GROWTH_LOG_PATH = "growth_log.json"

def word_count(obj):
    if isinstance(obj, str):
        return len(obj.split())
    if isinstance(obj, dict):
        return sum(word_count(v) for v in obj.values())
    if isinstance(obj, list):
        return sum(word_count(v) for v in obj)
    return 0

def main():
    with open("papers.json") as f:
        data = json.load(f)

    papers = data["papers"]
    concepts = data["concepts"]
    scope_items = data["project"]["scope_items"]

    total_words = word_count(data)

    # update growth log
    if os.path.exists(GROWTH_LOG_PATH):
        with open(GROWTH_LOG_PATH) as f:
            growth_log = json.load(f)
    else:
        growth_log = []
    latest_id = papers[-1]["id"] if papers else "P0"
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    growth_log.append({
        "snapshot": latest_id,
        "papers": len(papers),
        "concepts": len(concepts),
        "total_words": total_words,
        "timestamp": now
    })
    with open(GROWTH_LOG_PATH, "w") as f:
        json.dump(growth_log, f, indent=2)

    lines = []
    lines.append("# Paper Relationship Report\n")
    lines.append(f"Generated: {now}\n")
    lines.append(f"**{len(papers)} papers, {len(concepts)} concepts, ~{total_words} words**\n")

    lines.append("## Integrity Check\n")
    try:
        result = subprocess.run(
            [sys.executable, "integrity_check.py", "papers.json"],
            capture_output=True, text=True, timeout=30
        )
        lines.append("```")
        lines.append(result.stdout.strip())
        lines.append("```\n")
    except Exception as e:
        lines.append(f"*(integrity_check.py not run: {e})*\n")

    lines.append("## Growth Log\n")
    lines.append("| Snapshot | Papers | Concepts | Total words |")
    lines.append("|---|---|---|---|")
    for row in growth_log:
        lines.append(f"| {row['snapshot']} | {row['papers']} | {row['concepts']} | {row['total_words']} |")
    lines.append("")

    lines.append("## Scope Coverage\n")
    scope_counts = {sid: 0 for sid in scope_items}
    for c in concepts:
        s = c.get("supports_scope")
        if s is None:
            continue
        s_list = [s] if isinstance(s, str) else s
        for sid in s_list:
            if sid in scope_counts:
                scope_counts[sid] += 1
    lines.append("| Scope Item | Description | # Concepts |")
    lines.append("|---|---|---|")
    for sid, desc in scope_items.items():
        lines.append(f"| {sid} | {desc} | {scope_counts[sid]} |")
    lines.append("")

    lines.append("## Concepts\n")
    lines.append("| ID | Name | Supports |")
    lines.append("|---|---|---|")
    for c in concepts:
        s = c.get("supports_scope", "-")
        s_disp = ", ".join(s) if isinstance(s, list) else s
        lines.append(f"| {c['id']} | {c['name']} | {s_disp} |")
    lines.append("")

    lines.append("## Papers (full detail)\n")
    for p in papers:
        lines.append(f"### {p['id']} — {p['short_name']}")
        lines.append(f"*{p['full_citation']}*\n")
        lines.append(f"- **Role:** {p['role']} ({p.get('role_label','')})")
        lines.append(f"- **Status:** {p['status']}\n")
        lines.append(f"**Summary:** {p['summary']}\n")
        fd = p.get("full_detail", {})
        for field in ["problem", "method", "results", "limitations"]:
            if fd.get(field):
                lines.append(f"**{field.capitalize()}:** {fd[field]}\n")
        if fd.get("numbers"):
            lines.append("**Key numbers:**")
            for n in fd["numbers"]:
                lines.append(f"- {n}")
            lines.append("")
        if p.get("concept_links"):
            lines.append("**Concept links:**\n")
            lines.append("| Concept | Strength | Excerpt | Detail |")
            lines.append("|---|---|---|---|")
            for link in p["concept_links"]:
                lines.append(f"| {link['concept_id']} | {link.get('strength','-')} | {link.get('excerpt','-')} | {link.get('detail','-')} |")
            lines.append("")
        if p.get("caveats"):
            lines.append(f"**Caveats:** {p['caveats']}\n")
        lines.append("---\n")

    with open("relationship_report.md", "w") as f:
        f.write("\n".join(lines))
    print(f"Wrote relationship_report.md ({total_words} total words)")

if __name__ == "__main__":
    main()
