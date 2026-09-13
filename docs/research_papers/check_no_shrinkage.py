#!/usr/bin/env python3
"""Compare an old snapshot of papers.json to a new version and fail loudly
if any paper's content shrank, lost a concept_link, or was removed."""
import json, sys

def load(path):
    with open(path) as f:
        return json.load(f)

def word_count(obj):
    if isinstance(obj, str):
        return len(obj.split())
    if isinstance(obj, dict):
        return sum(word_count(v) for v in obj.values())
    if isinstance(obj, list):
        return sum(word_count(v) for v in obj)
    return 0

def main():
    if len(sys.argv) != 3:
        print("Usage: check_no_shrinkage.py <old.json> <new.json>")
        sys.exit(2)
    old = load(sys.argv[1])
    new = load(sys.argv[2])

    old_papers = {p["id"]: p for p in old.get("papers", [])}
    new_papers = {p["id"]: p for p in new.get("papers", [])}

    failures = []

    for pid, op in old_papers.items():
        if pid not in new_papers:
            failures.append(f"Paper {pid} was REMOVED.")
            continue
        np_ = new_papers[pid]
        old_wc = word_count(op)
        new_wc = word_count(np_)
        if new_wc < old_wc:
            failures.append(f"Paper {pid} SHRANK: {old_wc} words -> {new_wc} words.")

        old_links = {(l["concept_id"]) for l in op.get("concept_links", [])}
        new_links = {(l["concept_id"]) for l in np_.get("concept_links", [])}
        missing_links = old_links - new_links
        if missing_links:
            failures.append(f"Paper {pid} LOST concept_links: {missing_links}")

    old_concepts = {c["id"] for c in old.get("concepts", [])}
    new_concepts = {c["id"] for c in new.get("concepts", [])}
    missing_concepts = old_concepts - new_concepts
    if missing_concepts:
        failures.append(f"Concepts REMOVED: {missing_concepts}")

    if failures:
        print("SHRINKAGE DETECTED:")
        for f in failures:
            print(" - " + f)
        sys.exit(1)
    else:
        print("OK")
        sys.exit(0)

if __name__ == "__main__":
    main()
