# How to add a paper to the knowledge graph

Mandatory workflow — content only ever grows, never gets rephrased/shortened/removed.

1. **Snapshot first:**
   `cp papers.json snapshots/papers_before_P<N>.json`
2. Copy `NEW_PAPER_TEMPLATE.json`, assign the next `P#` id.
3. Check the existing `concepts` array for a fit; only add a new `C_` concept if the paper
   introduces a genuinely new mechanism not already covered.
4. Fill only the template fields directly in the JSON (no extra prose generated outside the
   file — keeps token cost low).
5. Append to the `papers` array — **never edit/shorten an existing paper's entry**, only
   append alongside it.
6. **Run the guard before finalizing:**
   `python3 check_no_shrinkage.py snapshots/papers_before_P<N>.json papers.json`
   — must print "OK" before proceeding.
7. Regenerate: `python3 generate_diagram.py && python3 build_report.py`
8. Snapshot again: `cp papers.json snapshots/papers_after_P<N>.json`
9. **Run the integrity check:** `python3 integrity_check.py papers.json` — confirms every
   paper has complete `full_detail`, every `concept_links` entry points to a real concept,
   every concept's `supports_scope` points to a real scope item, and there are no orphan
   concepts. Also prints current S1/S2/S3 coverage counts so scope gaps stay visible.

## Field rules
- `excerpt` = a few words verbatim, never a full sentence/quote block (copyright limit).
- `strength`: strong = paper is a direct source/origin of the mechanism; medium =
  supports/reinforces; weak = tangential or explicitly scopes away from it.
- `full_detail` fields should be as complete as the paper supports — this is a reference
  archive, not a slide summary; longer is fine and expected.
