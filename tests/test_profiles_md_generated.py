"""
Assertion 4 of DESIGN.md Section 2.5: `PROFILES.md` is GENERATED, and cannot drift from the data.

The failure this prevents is specific and common. Someone regenerates the profile set, a value
moves, and the checked-in ledger keeps saying the old thing -- confidently, in a file whose whole
purpose is to be quoted. Byte-equality is the only check that catches it, because any looser
comparison would tolerate exactly the drift being guarded against.

If this test fails after a legitimate data change, the fix is to regenerate, not to relax it:

    python -m optimization.profiles.ledger
"""

from __future__ import annotations

import pathlib

import pytest

from optimization.profiles.ledger import PREAMBLE, render

REPO = pathlib.Path(__file__).resolve().parent.parent
PROFILES_MD = REPO / "PROFILES.md"


@pytest.fixture(scope="module")
def generated() -> str:
    return render("baseline")


def test_profiles_md_exists() -> None:
    assert PROFILES_MD.exists(), (
        "PROFILES.md is missing. Generate it with `python -m optimization.profiles.ledger`"
    )


def test_profiles_md_matches_the_regenerated_ledger(generated: str) -> None:
    on_disk = PROFILES_MD.read_text(encoding="utf-8")
    if on_disk != generated:
        pytest.fail(
            "PROFILES.md is stale -- the checked-in ledger no longer matches the profile data. "
            "Regenerate with `python -m optimization.profiles.ledger`.\n"
            f"on disk: {len(on_disk)} chars, regenerated: {len(generated)} chars"
        )


def test_generation_is_deterministic() -> None:
    """Two renders must agree.

    Dict iteration order, set ordering and float formatting are all places where a ledger can
    become non-reproducible without any value changing. A non-deterministic generator would make
    the byte-equality test above fail at random, and the natural response to a flaky test is to
    delete it.
    """
    assert render("baseline") == render("baseline")


def test_the_honesty_preamble_is_present(generated: str) -> None:
    """Section 10, item 7. The preamble is aimed at a reader who quotes a number out of this
    repo without reading further, so its absence is a real defect rather than a cosmetic one."""
    assert PREAMBLE.strip() in generated
    assert "LOWER BOUND" in generated


@pytest.mark.parametrize(
    "heading",
    [
        "## 1. Coverage summary",
        "## 2. The `Unavailable` register",
        "## 3. Validation",
        "## 4. Paper-version concordance",
        "## 5. Named profile sets",
        "## 6. External sources",
        "## 7. Arrival traces",
        "## 8. The ledger",
    ],
)
def test_every_required_section_is_present(generated: str, heading: str) -> None:
    """Section 10 enumerates what the file must contain. Each item is checked by name so a
    section cannot quietly disappear during a refactor."""
    assert heading in generated


def test_the_ledger_reports_zero_invented_values(generated: str) -> None:
    """The headline claim of Milestone 3, asserted against the generated text rather than the
    data -- so the file a reader actually opens is the thing making the claim."""
    assert "0 invented" in generated


def test_unavailable_rows_name_the_blocked_expression(generated: str) -> None:
    """A gap that does not say which equation it blocks is not actionable at M4."""
    assert "eq3" in generated or "eq5" in generated


def test_the_ledger_has_one_row_per_value(generated: str) -> None:
    """The ledger is long by design (Section 10, item 1: "it is long, and it should be").
    A short one means the row collection silently stopped early."""
    body = generated.split("## 8. The ledger", 1)[1]
    rows = [ln for ln in body.splitlines() if ln.startswith("| `")]
    assert len(rows) > 300, f"only {len(rows)} ledger rows"


def test_no_row_breaks_the_markdown_table(generated: str) -> None:
    """A `|` inside a reason or an assumption would split a cell and corrupt every column to its
    right. `_escape` handles it; this asserts the escaping actually ran."""
    body = generated.split("## 8. The ledger", 1)[1]
    for line in body.splitlines():
        if not line.startswith("| `"):
            continue
        cells = line.count("|") - line.count(r"\|")
        assert cells == 9, f"row has {cells - 1} cells, expected 8:\n{line}"
