#!/usr/bin/env python3
"""Full-graph integrity check for papers.json.

Verifies:
1. Every paper has a complete full_detail (problem, method, results, limitations, numbers).
2. No concept_links point to a non-existent concept.
3. No concept's supports_scope points to a non-existent scope item.
4. No orphan concepts (every concept has >=1 supporting paper).
5. Scope-coverage counts per scope item (S1/S2/S3), printed for visibility.

Run periodically as more papers are added -- recommended after every paper addition,
in addition to check_no_shrinkage.py (which only checks for regressions, not completeness).
"""
import json
import sys

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "papers.json"
    with open(path) as f:
        data = json.load(f)

    papers = data["papers"]
    concepts = {c["id"]: c for c in data["concepts"]}
    scope_items = set(data["project"]["scope_items"].keys())

    issues = []

    # 1. every paper has complete full_detail
    for p in papers:
        fd = p.get("full_detail", {})
        for field in ["problem", "method", "results", "limitations"]:
            if not fd.get(field):
                issues.append(f"{p['id']}: missing or empty full_detail.{field}")
        if "numbers" not in fd:
            issues.append(f"{p['id']}: missing full_detail.numbers")

    # 2. no concept_links point to non-existent concepts
    for p in papers:
        for link in p.get("concept_links", []):
            if link["concept_id"] not in concepts:
                issues.append(f"{p['id']}: concept_link to nonexistent concept {link['concept_id']}")

    # 3. no concept's supports_scope points to nonexistent scope item
    for cid, c in concepts.items():
        s = c.get("supports_scope")
        if s is None:
            continue
        s_list = [s] if isinstance(s, str) else s
        for sid in s_list:
            if sid not in scope_items:
                issues.append(f"Concept {cid}: supports_scope references nonexistent scope {sid}")

    # 4. no orphan concepts
    linked_concepts = set()
    for p in papers:
        for link in p.get("concept_links", []):
            linked_concepts.add(link["concept_id"])
    orphans = set(concepts.keys()) - linked_concepts
    if orphans:
        issues.append(f"Orphan concepts (no supporting paper): {sorted(orphans)}")

    # 5. scope-coverage counts
    scope_counts = {sid: 0 for sid in scope_items}
    for c in concepts.values():
        s = c.get("supports_scope")
        if s is None:
            continue
        s_list = [s] if isinstance(s, str) else s
        for sid in s_list:
            if sid in scope_counts:
                scope_counts[sid] += 1

    print("=== INTEGRITY CHECK ===")
    if issues:
        for i in issues:
            print("FAIL:", i)
    else:
        print("All checks passed: full_detail complete, concept_links valid, scope references valid, no orphan concepts.")

    print()
    print("=== SCOPE COVERAGE ===")
    for sid, count in sorted(scope_counts.items()):
        print(f"{sid}: {count} concepts")

    print()
    print(f"Total papers: {len(papers)}, total concepts: {len(concepts)}")

    sys.exit(1 if issues else 0)

if __name__ == "__main__":
    main()
