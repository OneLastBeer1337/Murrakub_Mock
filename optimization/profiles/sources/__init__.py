"""Raw transcriptions and digitizations of the two paper versions.

Nothing in this package interprets a number. It transcribes table cells, printed figure
labels, prose statements and digitized figure readings, each tagged with the version and locus
it came from, so that the interpretation done by `workflow_profiles.py`, `model_profiles.py`,
`slo_tiers.py` and `arrivals.py` is auditable against a source that has not already been
reshaped to fit it.

Two sources of truth, cross-checked (DESIGN.md header):
  [OSDI]  Chaudhry et al., OSDI '26, pp. 567-587   -- primary; unqualified citations are OSDI
  [ARXIV] arXiv:2508.18298v2, same authors/title   -- cross-check
Figure and table numbering differs between them; see `CONCORDANCE` in `tables.py`.
"""
