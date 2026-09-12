"""
Provenance machinery: no number may exist in this package without a source.

Implements the discipline required by, but never specified in, Murakkab (OSDI '26), Section 3.3,
"Profiles" (p.573). The paper reports profile *values*; it does not say where several of them came
from, and this reproduction has no GPUs with which to measure any of them. CLAUDE.md's rule --
"Never invent numbers that contradict a paper-reported figure -- flag the gap instead of quietly
extrapolating past what's defensible" -- therefore needs a representation, or it decays into a
comment that rots the first time a value is moved.

The rule this module enforces (DESIGN.md Section 2.1):

    No numeric value may exist anywhere in /optimization/profiles/ unless it is wrapped in a
    `Measured` record carrying a `Provenance` tag and a citation.

Enforced twice: by construction here (`Measured.__post_init__`), and reflectively over the whole
assembled `ProfileSet` by tests/test_profile_provenance.py (DESIGN.md Section 2.5).

Nothing in this module knows what a profile is. It is imported by every module that holds a number
and imports none of them, so the enforcement cannot be circumvented by import order.

Two sources of truth, cross-checked (DESIGN.md header):
  [OSDI]  Chaudhry et al., OSDI '26, pp. 567-587      -- primary; unqualified citations are OSDI
  [ARXIV] arXiv:2508.18298v2, same authors/title      -- cross-check
Figure and table numbering differs between them (DESIGN.md Section 11.1); see CITATION_REGISTRY.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Generic, Literal, TypeVar

T = TypeVar("T")

Version = Literal["OSDI", "ARXIV", "BOTH", "EXTERNAL"]


class ProfileProvenanceError(Exception):
    """A value was constructed without the evidence its provenance level demands."""


class ProfileUnavailableError(Exception):
    """A value the paper does not report was read as though it existed (DESIGN.md 2.4).

    Raised instead of returning 0 or a default. With `l_TTFT_m = 0` the latency filter eq. (5)
    becomes strictly MORE permissive, which would silently flatter the baseline -- exactly the
    class of error this milestone exists to prevent.
    """


class Provenance(IntEnum):
    """Epistemic strength of a single number, ordered by DECREASING strength (DESIGN.md 2.2).

    `IntEnum` is deliberate: `min(...)` over the provenances of a derived quantity's inputs gives
    the strength of its weakest input, and `weakest()` below uses that to enforce the rule that a
    derived value is never stronger than its weakest ingredient.
    """

    PAPER_TABLE = 100
    """A cell of a numbered table, copied verbatim. Exact; zero band."""

    PAPER_TEXT = 90
    """A number stated in prose, e.g. Section 3.4 (p.575): "600 and 1200 tokens in the 50th and
    99th percentile"."""

    PAPER_FIGURE_LABEL = 85
    """A printed axis or tier annotation -- TYPESET TEXT, exact to the digit (e.g. Figure 8a's
    "Best >=91.4%"). Kept separate from PAPER_FIGURE_READ so an exact printed number cannot
    inherit a digitization band, nor a pixel reading claim typeset exactness. The distinction
    carries the Section 7.3 tier reconstruction."""

    PAPER_FIGURE_READ = 70
    """Digitized from a plotted mark. REQUIRES an uncertainty band."""

    DERIVED = 60
    """Arithmetic over paper values plus an explicitly stated assumption."""

    INTERPOLATED = 50
    """Between two anchors, both of which must be recorded."""

    EXTRAPOLATED = 40
    """Outside the anchor range; the extrapolation model must be named in `assumption`."""

    EXTERNAL = 30
    """A real non-paper source (vendor price list, spec sheet), with a retrieval date."""

    ASSUMED_ALIAS = 20
    """Borrowed wholesale from a DIFFERENT profile, on the assumption that two paper names denote
    the same thing (A34: `DeepSeek-Llama-70B` vs `Llama-3.1-70B`). Its own member rather than
    DERIVED because copying a curve between names is not arithmetic -- it is an identity claim,
    and it deserves to be greppable on its own."""

    INVENTED = 10
    """No basis whatsoever. Legal only inside `critique/`, which tests/test_milp_boundary.py
    asserts is unreachable from `to_milp_inputs()` (Q16)."""


#: Provenance at or below this level must carry an explicit uncertainty band.
BAND_REQUIRED_AT_OR_BELOW = Provenance.PAPER_FIGURE_READ

_ANCHORS_REQUIRED = frozenset(
    {Provenance.INTERPOLATED, Provenance.EXTRAPOLATED, Provenance.DERIVED}
)
_ASSUMPTION_REQUIRED = frozenset(
    {Provenance.DERIVED, Provenance.EXTRAPOLATED, Provenance.ASSUMED_ALIAS}
)


def weakest(*provenances: Provenance) -> Provenance:
    """The weakest of several provenances -- the ceiling for anything derived from them all.

    A derived value may not claim to be stronger than what it was derived from; assertion 3 of
    tests/test_profile_provenance.py checks this over the assembled set.
    """
    if not provenances:
        raise ProfileProvenanceError("weakest() of nothing is not a provenance")
    return min(provenances)


# --- Citations (DESIGN.md Section 2.6) -------------------------------------------------------


@dataclass(frozen=True)
class Citation:
    """A structured pointer to the place a value came from -- not a free-text string.

    `version="BOTH"` is permitted ONLY when the value has been checked in both PDFs and agrees.
    The field is not decoration: DESIGN.md Section 11 lists six places where the versions differ,
    and one of them (A46 -- the "90th percentile token generation load" sentence exists only in
    [OSDI] p.576) is the sole justification for `t_c` being a p90 at all.

    [DESIGN CHOICE, build] A `BOTH` citation names the *[OSDI] locus*, because table and figure
    numbering differs between versions (DESIGN.md 11.1) and a citation must resolve to exactly one
    place in one document to be checkable. DESIGN.md's worked example #3 writes
    `figure="3 (OSDI) / 4 (arXiv)"`; that prose form does not resolve and is not used here --
    it becomes `Citation("BOTH", figure="3", page=570)`, with Section 11.1 supplying the arXiv
    counterpart. Flagged to Arno rather than silently normalized.
    """

    version: Version
    table: int | None = None
    figure: str | None = None
    section: str | None = None
    page: int | None = None

    quote: str = ""
    """The sentence itself, when the value came from prose. Required for PAPER_TEXT."""

    retrieved: str = ""
    """ISO date. Required for EXTERNAL: a vendor price list without a date is not a source."""

    def __post_init__(self) -> None:
        if self.version not in ("OSDI", "ARXIV", "BOTH", "EXTERNAL"):
            raise ProfileProvenanceError(f"{self!r}: unknown version tag")
        if self.version == "EXTERNAL":
            if not self.section or not self.retrieved:
                raise ProfileProvenanceError(
                    f"{self!r}: an EXTERNAL citation must name a source and a retrieval date"
                )
            return
        if self.table is None and self.figure is None and self.section is None:
            raise ProfileProvenanceError(
                f"{self!r}: a citation must name a table, figure, or section"
            )

    @property
    def namespace(self) -> str:
        """Which document's numbering the locus is expressed in.

        `BOTH` resolves to OSDI numbering -- see the class docstring.
        """
        if self.version == "ARXIV":
            return "ARXIV"
        if self.version == "EXTERNAL":
            return "EXTERNAL"
        return "OSDI"

    @property
    def locus(self) -> tuple[str, int | None, str | None, str | None]:
        """The page-independent identity of the place cited."""
        return (self.namespace, self.table, self.figure, self.section)


#: Loci actually used by this reproduction, each mapped to the page(s) attested for it.
#:
#: Assertion 2 of tests/test_profile_provenance.py requires every `Citation` to appear here, so a
#: typo'd page number fails the build rather than the reader's trust. An empty page set means the
#: locus is registered but no page has been attested -- such a citation must omit `page`.
#:
#: Seeded ONLY from loci with a page attested in DESIGN.md. Adding an entry is an editorial act:
#: check the PDF first.
CITATION_REGISTRY: dict[tuple[str, int | None, str | None, str | None], frozenset[int]] = {
    # --- [OSDI] sections ---
    ("OSDI", None, None, "2.2"): frozenset({568, 569}),
    ("OSDI", None, None, "2.5"): frozenset({570}),
    ("OSDI", None, None, "3.2"): frozenset({572, 573}),
    ("OSDI", None, None, "3.3"): frozenset({573}),
    ("OSDI", None, None, "3.3.1"): frozenset({574}),
    ("OSDI", None, None, "3.4"): frozenset({575}),
    ("OSDI", None, None, "4.1"): frozenset({575, 576}),
    ("OSDI", None, None, "4.2"): frozenset({576}),
    ("OSDI", None, None, "4.3"): frozenset({576}),
    ("OSDI", None, None, "4.5"): frozenset({578}),
    ("OSDI", None, None, "4.6"): frozenset({578}),
    ("OSDI", None, None, "A.2"): frozenset({585}),
    ("OSDI", None, None, "A.5"): frozenset({586, 587}),
    # --- [OSDI] listings and tables ---
    ("OSDI", None, None, "Listing 1"): frozenset({569}),
    ("OSDI", None, None, "Listing 2"): frozenset({572}),
    ("OSDI", 1, None, None): frozenset({572}),
    ("OSDI", 2, None, None): frozenset({576}),
    ("OSDI", 3, None, None): frozenset({578}),
    ("OSDI", 4, None, None): frozenset({585}),
    ("OSDI", 5, None, None): frozenset({585}),
    ("OSDI", 6, None, None): frozenset({586}),
    # --- [OSDI] figures ---
    ("OSDI", None, "2", None): frozenset({570}),
    ("OSDI", None, "2a", None): frozenset({570}),
    ("OSDI", None, "2b", None): frozenset({570}),
    ("OSDI", None, "2c", None): frozenset({570}),
    ("OSDI", None, "2d", None): frozenset({570}),
    ("OSDI", None, "3", None): frozenset({570}),
    ("OSDI", None, "4", None): frozenset({571}),
    ("OSDI", None, "4a", None): frozenset({571}),
    ("OSDI", None, "4b", None): frozenset({571}),
    ("OSDI", None, "6", None): frozenset({574}),
    ("OSDI", None, "7a", None): frozenset({575}),
    ("OSDI", None, "7b", None): frozenset({575}),
    ("OSDI", None, "8a", None): frozenset({575}),
    ("OSDI", None, "8b", None): frozenset({575}),
    ("OSDI", None, "10", None): frozenset({577}),
    ("OSDI", None, "11", None): frozenset({578}),
    ("OSDI", None, "19", None): frozenset({587}),
    # --- [ARXIV] cross-check loci (DESIGN.md 11.1 concordance) ---
    ("ARXIV", 1, None, None): frozenset({9}),
    ("ARXIV", 2, None, None): frozenset({9}),
    ("ARXIV", 3, None, None): frozenset({16}),
    ("ARXIV", 4, None, None): frozenset({16}),
    ("ARXIV", 5, None, None): frozenset({17}),
    ("ARXIV", None, "3", None): frozenset({4}),
    ("ARXIV", None, "4", None): frozenset({4}),
    ("ARXIV", None, "5", None): frozenset({5}),
    ("ARXIV", None, "18", None): frozenset({18}),
}


def is_registered(cite: Citation) -> bool:
    """Whether `cite` names a locus in CITATION_REGISTRY at an attested page."""
    if cite.version == "EXTERNAL":
        return True
    pages = CITATION_REGISTRY.get(cite.locus)
    if pages is None:
        return False
    return cite.page in pages if cite.page is not None else not pages


# --- Values (DESIGN.md Sections 2.3, 2.4) ----------------------------------------------------


@dataclass(frozen=True)
class Anchor:
    """A literal back-pointer to an input a derived value sits between or came from.

    Carrying the `Measured` itself, not just a key, means an interpolated value can be
    re-derived by a reader without consulting prose.
    """

    profile_key: str
    field: str
    value: "Measured[Any]"


@dataclass(frozen=True)
class Measured(Generic[T]):
    """A number with its evidence attached. Provenance lives on the VALUE, not on the file.

    A per-file header comment is not machine-readable and stops being true the first time a
    value is moved between modules.
    """

    value: T

    unit: str
    """"tokens", "s", "tokens/s", "kWh/h", "$/GPU-s", ... Dimensional slips are how `t_c` ends up
    read as prompt+completion tokens against a completion-token throughput (A39)."""

    provenance: Provenance
    cite: Citation
    lo: T | None = None
    hi: T | None = None
    anchors: tuple[Anchor, ...] = ()
    assumption: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        p = self.provenance
        if p <= BAND_REQUIRED_AT_OR_BELOW and (self.lo is None or self.hi is None):
            raise ProfileProvenanceError(
                f"{self!r}: values at or below PAPER_FIGURE_READ must carry an uncertainty band"
            )
        if (self.lo is None) != (self.hi is None):
            # Not among DESIGN.md 2.3's listed checks: a half-open band would slip past the
            # containment check below and silently disable the Monte-Carlo resample (Section 9.3).
            raise ProfileProvenanceError(f"{self!r}: a band needs both lo and hi, or neither")
        if p in _ANCHORS_REQUIRED and not self.anchors:
            raise ProfileProvenanceError(f"{self!r}: must name its anchors")
        if p in _ASSUMPTION_REQUIRED and not self.assumption:
            raise ProfileProvenanceError(f"{self!r}: must state its assumption")
        if p is Provenance.PAPER_TEXT and not self.cite.quote:
            raise ProfileProvenanceError(f"{self!r}: a prose value must quote the sentence")
        if p is Provenance.INVENTED and not self.note:
            raise ProfileProvenanceError(f"{self!r}: an invented value must say why it exists")
        if self.lo is not None and not (self.lo <= self.value <= self.hi):  # type: ignore[operator]
            raise ProfileProvenanceError(f"{self!r}: value outside its own band")
        if self.anchors and p > weakest(*(a.value.provenance for a in self.anchors)):
            raise ProfileProvenanceError(
                f"{self!r}: claims stronger provenance than the anchors it came from"
            )
        if not is_registered(self.cite):
            raise ProfileProvenanceError(f"{self!r}: {self.cite!r} is not in CITATION_REGISTRY")

    @property
    def band(self) -> tuple[T, T]:
        """(lo, hi), collapsing to (value, value) for exact provenance levels."""
        if self.lo is None:
            return (self.value, self.value)
        return (self.lo, self.hi)  # type: ignore[return-value]


@dataclass(frozen=True)
class Unavailable:
    """The deliberate absence of a value -- a first-class state, not a missing field.

    This is the mechanism that keeps the INVENTED column at zero (Q19, resolved 2026-09-11):
    roughly 14% of MILP-facing values are Unavailable, and M4 must exclude those configurations
    and report them as data-excluded rather than guessing. Reading one raises.
    """

    reason: str

    cite: Citation
    """Where we looked and did not find it."""

    blocks: tuple[str, ...] = ()
    """Which MILP expressions become uncomputable, e.g. ("eq5",). Makes
    `ProfileSet.coverage_report()` able to say "17 of 30 model profiles cannot be evaluated by
    eq. (5)" without anyone having to remember (DESIGN.md 2.4)."""

    def __post_init__(self) -> None:
        if not self.reason:
            raise ProfileProvenanceError(f"{self!r}: an absence must state why")
        if not is_registered(self.cite):
            raise ProfileProvenanceError(f"{self!r}: {self.cite!r} is not in CITATION_REGISTRY")

    @property
    def value(self) -> Any:
        raise ProfileUnavailableError(self.reason)

    @property
    def band(self) -> Any:
        raise ProfileUnavailableError(self.reason)


#: Either a number with evidence, or a documented absence. Every numeric profile field is one.
Value = Measured[Any] | Unavailable


def require(value: Value, context: str = "") -> Any:
    """Read a value, raising ProfileUnavailableError if it is a documented absence."""
    if isinstance(value, Unavailable):
        raise ProfileUnavailableError(f"{context + ': ' if context else ''}{value.reason}")
    return value.value
