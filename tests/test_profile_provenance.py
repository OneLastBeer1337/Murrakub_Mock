"""
The four assertions of DESIGN.md Section 2.5 -- the tests that make the provenance discipline
real rather than aspirational.

The claim these defend is the one PROGRESS.md makes in public: of ~230 MILP-facing values, 0%
are invented. That claim is worth nothing unless a naked float cannot enter the profile set
without failing a test, so assertion 1 walks the object graph reflectively rather than checking
a list someone has to remember to update.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Mapping, Sequence

import pytest

from optimization.profiles.profile_sets import NAMED_SETS, profile_set
from optimization.profiles.provenance import (
    CITATION_REGISTRY,
    Citation,
    Measured,
    Provenance,
    Unavailable,
    is_registered,
    weakest,
)
from optimization.profiles.schema import STRUCTURAL_FIELDS, ProfileSet

ALL_SETS = sorted(NAMED_SETS)


@pytest.fixture(scope="module")
def baseline_set() -> ProfileSet:
    return profile_set("baseline")


# ---------------------------------------------------------------------------------------------
# Reflective walk
# ---------------------------------------------------------------------------------------------


def _walk(node: Any, path: str = "", seen: set[int] | None = None, inherited: str = ""):
    """Yield `(path, field_name, value)` for every leaf reachable from `node`.

    `field_name` is the name of the dataclass field or mapping key the leaf sits in -- that is
    what the STRUCTURAL_FIELDS allow-list is keyed on.

    `inherited` carries that name DOWN through anonymous nesting. `ConfigKey.knobs` is a
    `tuple[tuple[str, Any], ...]`, so the `2` in `("D", 2)` is three levels below the field that
    names it; without inheritance it would be reported as sitting in a field called `knobs[0]`,
    match nothing in the allow-list, and fail the test for being a knob setting -- exactly the
    case the allow-list exists to permit.
    """
    seen = seen if seen is not None else set()
    if id(node) in seen:
        return
    if isinstance(node, (Measured, Unavailable, Citation)):
        return
    seen.add(id(node))

    if dataclasses.is_dataclass(node) and not isinstance(node, type):
        for f in dataclasses.fields(node):
            value = getattr(node, f.name)
            yield from _leaf(value, f"{path}.{f.name}", f.name, seen)
    elif isinstance(node, Mapping):
        for k, v in node.items():
            yield from _leaf(v, f"{path}[{k!r}]", str(k), seen)
    elif isinstance(node, Sequence) and not isinstance(node, (str, bytes)):
        for i, v in enumerate(node):
            yield from _leaf(v, f"{path}[{i}]", inherited, seen)


def _leaf(value: Any, path: str, field_name: str, seen: set[int]):
    yield (path, field_name, value)
    if isinstance(value, (Measured, Unavailable, Citation)):
        return
    if field_name in STRUCTURAL_FIELDS:
        # PRUNE, do not descend. An allow-listed field is allowed as a SUBTREE: `knobs` is
        # `(("D", 2), ...)` and `tier_reconstruction` is a nested report keyed by workflow and
        # tier name. Descending would re-label those numbers with the innermost mapping key
        # (`"best"`, `"residuals"`), which names nothing in the allow-list, and the test would
        # demand provenance for a diagnostic the reconstruction PRODUCED rather than consumed.
        return
    if dataclasses.is_dataclass(value) or isinstance(value, (Mapping, Sequence)):
        if not isinstance(value, (str, bytes)):
            yield from _walk(value, path, seen, inherited=field_name)


def _collect_measured(pset: ProfileSet) -> list[tuple[str, Measured]]:
    out: list[tuple[str, Measured]] = []
    for path, _name, value in _walk(pset, pset.name):
        if isinstance(value, Measured):
            out.append((path, value))
    return out


def _collect_citations(pset: ProfileSet) -> list[tuple[str, Citation]]:
    out: list[tuple[str, Citation]] = []
    for path, value in _collect_measured(pset):
        out.append((path, value.cite))
    for path, _name, value in _walk(pset, pset.name):
        if isinstance(value, Unavailable):
            out.append((path, value.cite))
    return out


# ---------------------------------------------------------------------------------------------
# Assertion 1 -- no naked numbers
# ---------------------------------------------------------------------------------------------


def test_no_naked_numbers(baseline_set: ProfileSet) -> None:
    """Every numeric leaf is wrapped, or sits in an explicitly allowed structural field.

    A failure here is not a style complaint. An unwrapped float is a number with no source, and
    the whole comparative argument of this repo rests on being able to say where each one came
    from.
    """
    naked: list[str] = []
    for path, field_name, value in _walk(baseline_set, baseline_set.name):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if field_name in STRUCTURAL_FIELDS:
            continue
        naked.append(f"{path} = {value!r} (field {field_name!r})")
    assert not naked, "unwrapped numeric values:\n  " + "\n  ".join(sorted(naked))


def test_structural_allow_list_is_unchanged() -> None:
    """The allow-list is the escape hatch, so it is pinned.

    Widening it is how the discipline would quietly die: one `"latency"` added here and an
    unsourced number becomes legal forever. Changing this set should require changing this test,
    deliberately.
    """
    assert STRUCTURAL_FIELDS == frozenset(
        {
            "tp",
            "dag_variant",
            "workflow_id",
            "model_id",
            "gpu",
            "knobs",
            "name",
            "epoch",
            "percentile",
            "share",
            "unit",
            "accuracy_benchmark",
            "accuracy_measured_on_model",
            "note",
            "reason",
            "blocks",
            "collapsed_rows",
            "residuals",
            "tier_reconstruction",
            "operating_point_collapse",
            "counts",
            "excluded",
        }
    )


# ---------------------------------------------------------------------------------------------
# Assertion 2 -- every citation resolves
# ---------------------------------------------------------------------------------------------


def test_every_citation_is_registered(baseline_set: ProfileSet) -> None:
    bad = [
        f"{path}: {cite!r}"
        for path, cite in _collect_citations(baseline_set)
        if not is_registered(cite)
    ]
    assert not bad, "citations not in CITATION_REGISTRY:\n  " + "\n  ".join(sorted(bad))


def test_every_citation_names_a_version_and_a_locus(baseline_set: ProfileSet) -> None:
    bad: list[str] = []
    for path, cite in _collect_citations(baseline_set):
        if cite.version not in ("OSDI", "ARXIV", "BOTH", "EXTERNAL"):
            bad.append(f"{path}: bad version {cite.version!r}")
        if cite.version == "EXTERNAL":
            if not cite.retrieved:
                bad.append(f"{path}: EXTERNAL citation without a retrieval date")
            continue
        if cite.table is None and cite.figure is None and cite.section is None:
            bad.append(f"{path}: no locus (table/figure/section all None)")
    assert not bad, "\n  ".join(bad)


def test_prose_values_quote_the_sentence(baseline_set: ProfileSet) -> None:
    """`PAPER_TEXT` without a quote is unverifiable by a reader holding the PDF."""
    bad = [
        f"{path}: {m.note[:60]}"
        for path, m in _collect_measured(baseline_set)
        if m.provenance is Provenance.PAPER_TEXT and not m.cite.quote
    ]
    assert not bad, "\n  ".join(bad)


def test_citation_registry_pages_are_plausible() -> None:
    """A typo'd page is the failure mode this registry exists to catch, so the registry itself
    is checked: every OSDI page lies inside the paper's own page range."""
    for locus, pages in CITATION_REGISTRY.items():
        version = locus[0]
        if version != "OSDI":
            continue
        for p in pages:
            assert 565 <= p <= 590, f"{locus}: page {p} is outside the OSDI paper"


# ---------------------------------------------------------------------------------------------
# Assertion 3 -- anchors are reachable and never weaker than what claims them
# ---------------------------------------------------------------------------------------------


def test_derived_values_name_anchors(baseline_set: ProfileSet) -> None:
    needs_anchors = {
        Provenance.DERIVED,
        Provenance.INTERPOLATED,
        Provenance.EXTRAPOLATED,
    }
    bad = [
        f"{path} ({m.provenance.name})"
        for path, m in _collect_measured(baseline_set)
        if m.provenance in needs_anchors and not m.anchors
    ]
    assert not bad, "derived values with no anchors:\n  " + "\n  ".join(sorted(bad))


def test_no_value_claims_more_than_its_anchors(baseline_set: ProfileSet) -> None:
    """A derived value may not be stronger than the weakest thing it came from.

    `Provenance` is an `IntEnum` ordered by DECREASING strength, so this is a `<=` on the
    numeric value: a `DERIVED` (60) value anchored on a `PAPER_FIGURE_READ` (70) input is fine;
    a `PAPER_TABLE` (100) value anchored on a figure reading is not.
    """
    bad: list[str] = []
    for path, m in _collect_measured(baseline_set):
        if not m.anchors:
            continue
        ceiling = weakest(*(a.value.provenance for a in m.anchors))
        if m.provenance > ceiling:
            bad.append(f"{path}: {m.provenance.name} > anchors' {ceiling.name}")
    assert not bad, "\n  ".join(bad)


def test_anchor_values_are_themselves_well_formed(baseline_set: ProfileSet) -> None:
    """An anchor carries the `Measured` itself, so a reader can re-derive without the prose.
    That is only true if the anchor's own citation resolves."""
    bad: list[str] = []
    for path, m in _collect_measured(baseline_set):
        for a in m.anchors:
            if not isinstance(a.value, Measured):
                bad.append(f"{path}: anchor {a.field!r} is not a Measured")
            elif not is_registered(a.value.cite):
                bad.append(f"{path}: anchor {a.field!r} has an unregistered citation")
    assert not bad, "\n  ".join(bad)


# ---------------------------------------------------------------------------------------------
# Bands, and the INVENTED count
# ---------------------------------------------------------------------------------------------


def test_weak_values_carry_a_band(baseline_set: ProfileSet) -> None:
    bad = [
        f"{path} ({m.provenance.name})"
        for path, m in _collect_measured(baseline_set)
        if m.provenance <= Provenance.PAPER_FIGURE_READ and (m.lo is None or m.hi is None)
    ]
    assert not bad, "digitized/derived values without a band:\n  " + "\n  ".join(sorted(bad))


def test_values_lie_inside_their_own_bands(baseline_set: ProfileSet) -> None:
    bad = [
        f"{path}: {m.lo} <= {m.value} <= {m.hi} is false"
        for path, m in _collect_measured(baseline_set)
        if m.lo is not None and not (m.lo <= m.value <= m.hi)
    ]
    assert not bad, "\n  ".join(bad)


@pytest.mark.parametrize("name", ALL_SETS)
def test_no_invented_value_in_any_named_set(name: str) -> None:
    """The headline claim of Milestone 3, asserted on every named set rather than just the
    baseline: the only INVENTED numbers in the milestone live in `critique/`, and nothing in a
    `ProfileSet` reaches them (Q16)."""
    pset = profile_set(name)
    invented = [
        path for path, m in _collect_measured(pset) if m.provenance is Provenance.INVENTED
    ]
    assert not invented, f"{name}: INVENTED values inside a ProfileSet:\n  " + "\n  ".join(invented)


def test_unavailable_values_state_why_and_what_they_block(baseline_set: ProfileSet) -> None:
    """An absence is a first-class state and must be actionable: M4 has to be able to say which
    equation it cannot evaluate, without a human remembering."""
    bad: list[str] = []
    for path, _name, value in _walk(baseline_set, baseline_set.name):
        if not isinstance(value, Unavailable):
            continue
        if not value.reason:
            bad.append(f"{path}: no reason")
    assert not bad, "\n  ".join(bad)


def test_reading_an_unavailable_raises(baseline_set: ProfileSet) -> None:
    """The point of `Unavailable` is that it cannot be silently treated as a zero."""
    from optimization.profiles.provenance import ProfileUnavailableError

    found = None
    for _path, _name, value in _walk(baseline_set, baseline_set.name):
        if isinstance(value, Unavailable):
            found = value
            break
    assert found is not None, "expected at least one Unavailable in the baseline set"
    with pytest.raises(ProfileUnavailableError):
        _ = found.value
