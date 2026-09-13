#!/usr/bin/env python3
import json

def esc(s):
    return s.replace('"', "'")

def main():
    with open("papers.json") as f:
        data = json.load(f)

    papers = data["papers"]
    concepts = data["concepts"]
    scope_items = data["project"]["scope_items"]

    lines = ["graph LR"]

    # ===== Papers subgraph =====
    lines.append('  %% ===== Papers (left) =====')
    lines.append('  subgraph Papers[" Papers "]')
    for p in papers:
        pid = p["id"]
        label = esc(f'{p["short_name"]}')
        shape = "(" if p["role"] == "foundation" else "(["
        shape_close = ")" if p["role"] == "foundation" else "])"
        lines.append(f'    {pid}{shape}"{label}"{shape_close}')
    lines.append("  end")

    # ===== Concepts subgraph =====
    lines.append('  %% ===== Concepts (middle) =====')
    lines.append('  subgraph Concepts[" Concepts / Mechanisms "]')
    for c in concepts:
        label = esc(c["name"])
        lines.append(f'    {c["id"]}{{{{"{label}"}}}}')
    lines.append("  end")

    # ===== Scope subgraph =====
    lines.append('  %% ===== Scope Items (right) =====')
    lines.append('  subgraph Scope[" Project Scope "]')
    for sid, desc in scope_items.items():
        label = esc(desc.split("(")[0].strip())
        lines.append(f'    {sid}["{label}"]')
    lines.append("  end")

    # ===== Paper -> Concept links =====
    lines.append("  %% ===== Paper -> Concept links =====")
    for p in papers:
        pid = p["id"]
        for link in p.get("concept_links", []):
            cid = link["concept_id"]
            strength = link.get("strength", "weak")
            arrow = "===>" if strength == "strong" else ("-->" if strength == "medium" else "-.->")
            lines.append(f"  {pid} {arrow} {cid}")

    # ===== Concept -> Scope links =====
    lines.append("  %% ===== Concept -> Scope links =====")
    for c in concepts:
        cid = c["id"]
        scopes = c.get("supports_scope")
        if scopes is None:
            continue
        if isinstance(scopes, str):
            scopes = [scopes]
        for s in scopes:
            lines.append(f"  {cid} --> {s}")

    # ===== Styles =====
    lines.append("  %% ===== Styles =====")
    lines.append("  classDef foundation fill:#FFE4B5,stroke:#B8860B,stroke-width:2px,color:#3a2a00;")
    lines.append("  classDef supporting fill:#D6EAF8,stroke:#2E86C1,stroke-width:1.5px,stroke-dasharray: 4 2,color:#0b3350;")
    lines.append("  classDef concept fill:#F4ECF7,stroke:#8E44AD,stroke-width:1.5px,color:#3d1f4d;")
    lines.append("  classDef scope fill:#E8F8F5,stroke:#0F6E56,stroke-width:2px,color:#0b3a2e;")
    for p in papers:
        cls = "foundation" if p["role"] == "foundation" else "supporting"
        lines.append(f"  class {p['id']} {cls};")
    for c in concepts:
        lines.append(f"  class {c['id']} concept;")
    for sid in scope_items:
        lines.append(f"  class {sid} scope;")

    with open("relationship_map.mmd", "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Wrote relationship_map.mmd ({len(papers)} papers, {len(concepts)} concepts)")

if __name__ == "__main__":
    main()
