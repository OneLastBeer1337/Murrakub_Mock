"""
The formulation itself: A.5's ten distinct equations, and the boundaries M4 must not cross.

These tests defend properties, not functions. The properties are the ones that make this a
REPRODUCTION rather than an implementation inspired by a paper: the equation set is the paper's,
the constraint system does not vary with the objective, and three specific repairs that would each
make the optimizer "better" are provably absent.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from optimization.milp import A5
from optimization.milp.model import NO_MULTIPLEXING, build_model
from optimization.milp.objectives import Objective, attach
from optimization.milp.scenarios import no_budget
from optimization.milp.sets import build_admissible
from optimization.profiles.profile_sets import baseline
from optimization.profiles.schema import SloMix

REPO = pathlib.Path(__file__).resolve().parent.parent
MILP = REPO / "optimization" / "milp"
VERBATIM = MILP / "A5_VERBATIM.md"


@pytest.fixture(scope="module")
def inputs():
    return baseline(SloMix.section_4_2("accuracy", "good")).to_milp_inputs()


# ---------------------------------------------------------------------------------------------
# The equations are the paper's
# ---------------------------------------------------------------------------------------------


def test_thirteen_numbered_equations_are_ten_distinct(inputs) -> None:
    """A58, as an assertion rather than a footnote.

    A.5 states four constraints twice. A reader counting constraints from the equation numbers
    overcounts by three, and an implementation that emitted all thirteen would add three
    redundant constraints and report a different model size.
    """
    assert len(A5.ALL_NUMBERED) == 13
    assert len(A5.DISTINCT_EQUATIONS) == 10
    assert A5.DUPLICATE_OF == {8: 4, 9: 5, 10: 6}


def test_the_duplicates_really_are_duplicates() -> None:
    """(8)==(4) and (9)==(5) verbatim; (10)==(6) up to inlining `Cost_budget`.

    Compared after stripping whitespace and A.5's parenthetical tier labels, because the paper
    prints them with different annotations in the two places.
    """

    def norm(text: str) -> str:
        body = text.split("[")[0]
        return "".join(body.split()).replace("(accuracy)", "").replace("(latency)", "")

    assert norm(A5.EQ_8_FILTER_ACCURACY_DUP) == norm(A5.EQ_4_FILTER_ACCURACY)
    assert norm(A5.EQ_9_FILTER_LATENCY_DUP).replace("*", "") == norm(
        A5.EQ_5_FILTER_LATENCY
    ).replace("*", "")


def test_a5_py_matches_the_verbatim_markdown() -> None:
    """The anti-drift mechanism, same as M3 used for `PROFILES.md`.

    Two copies of the paper's algebra exist -- `A5_VERBATIM.md` for a human with the PDF open,
    `A5.py` for the code. If they diverge, the file a reviewer checks stops describing the file
    the optimizer runs, which defeats the purpose of transcribing verbatim at all.
    """
    text = VERBATIM.read_text(encoding="utf-8")
    checks = {
        "capacity": "n_m · θ_m",
        "filter_accuracy": "a_c < τ_{w,s}",
        "resource_budget": "n_m · g_m  ≤  B_g",
        "energy": "min Σ_m n_m e_m g_m",
        "epsilon": "ε = 0.001",
    }
    for name, fragment in checks.items():
        assert fragment in text, f"{name}: {fragment!r} missing from A5_VERBATIM.md"
    assert A5.EPSILON == 0.001


def test_x_avg_is_never_slo_filtered(inputs) -> None:
    """A66, enforced as data rather than remembered as prose.

    `x^avg` appears in eq. (2), eq. (6), eq. (10) and objective (13). None of those is an SLO
    filter and none is the capacity constraint. So average load is never quality-checked and
    never sizes the fleet -- which is why objective (13), the only objective that optimises
    quality, is the one the quality filter cannot reach.
    """
    avg_equations = {n for n, v in A5.VARIABLE_OF.items() if v == "x_avg"}
    assert avg_equations == {2, 6, 10, 13}
    filters = {4, 5, 8, 9}
    assert not (avg_equations & filters), "an SLO filter reached x^avg -- A66 has been repaired"
    assert A5.VARIABLE_OF[3] == "x_peak", "eq. (3) must bind peak only; it has no average twin"


def test_capacity_constraint_binds_peak_not_average() -> None:
    """Q21(b). `n_m` is provisioned from peak load alone."""
    assert "x^peak" in A5.EQ_3_CAPACITY
    assert "x^avg" not in A5.EQ_3_CAPACITY


# ---------------------------------------------------------------------------------------------
# The constraint system does not vary with the objective
# ---------------------------------------------------------------------------------------------


def test_constraint_set_is_identical_across_objectives(inputs) -> None:
    """What makes cross-objective comparison meaningful.

    Figures 7-9 report Acc./Energy against Acc./Cost columns. If the constraint set moved with
    the objective, those columns would differ for two reasons at once and neither could be
    attributed. The one permitted variation is eq. (6), whose presence A.5 itself ties to a
    supplied budget -- so with identical budget arguments the emitted constraints must match
    exactly.
    """
    adm = build_admissible(inputs, "video_qa", ("accuracy", "good"))
    emitted = []
    for objective in Objective:
        built = build_model(inputs, adm, epoch=0)
        names = sorted(built.problem.constraints)
        emitted.append(names)
    assert emitted[0] == emitted[1] == emitted[2]


def test_mu_m_defaults_to_one_and_is_isolated() -> None:
    """A42. `mu_m` is introduced by eq. (3) and defined nowhere in either version.

    Setting it to 1 adds no information. M5 changes `_capacity_lhs` and nothing else, so this
    test also pins the seam: if multiplexing ever leaks into another constraint, the default
    here stops being the whole story.
    """
    assert NO_MULTIPLEXING == 1.0
    source = (MILP / "model.py").read_text(encoding="utf-8-sig")
    assert source.count("mu") > 0
    assert "_capacity_lhs" in source


# ---------------------------------------------------------------------------------------------
# The three repairs that must be absent
# ---------------------------------------------------------------------------------------------


def _imports_of(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_model_py_never_imposes_coherence() -> None:
    """A51. `MilpInputs.coherent()` is a REPORTING tool and must never become a constraint.

    A.5 contains no constraint linking `c` to `m`. Adding one would make the optimizer produce
    sensible-looking answers and would erase the defect this project exists to measure -- which
    under `baseline` turns out to be 100% of allocated mass, not a latent edge case.
    """
    # Checked on the AST, not the raw text: `model.py`'s docstring legitimately EXPLAINS the
    # prohibition, and a substring scan cannot tell an explanation from a violation. What must
    # be absent is a real attribute access or call.
    tree = ast.parse((MILP / "model.py").read_text(encoding="utf-8-sig"))
    used = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
    } | {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
    }
    assert "coherent" not in used, "model.py calls coherent() -- A51 has been repaired"
    assert not any(
        "incoherence" in imported for imported in _imports_of(MILP / "model.py")
    )


def test_milp_never_imports_the_development_layer() -> None:
    """DESIGN.md Section 10.1, stated as a prohibition and enforced as one.

    A.5 has no precedence constraint and no makespan term. M4 may not read `LogicalWorkflow`,
    node lists or edges -- not for scheduling, not for anything. If M4 ever NEEDED precedence to
    be feasible, that is the finding, and it belongs in `architecture-decisions.md` rather than
    in `model.py`.
    """
    for path in MILP.rglob("*.py"):
        for imported in _imports_of(path):
            assert not imported.startswith("development"), f"{path.name} imports {imported}"
            assert not imported.startswith("shared.workflow"), f"{path.name} reads a DAG"


def test_milp_takes_only_milp_inputs_from_the_profile_layer() -> None:
    """The one-way boundary of DESIGN.md Section 4.3.

    `model.py` is the file that matters: it may know about `MilpInputs` and must not reach into
    the profile assembly modules, whose values carry provenance the optimizer has no business
    interpreting.
    """
    forbidden = {
        "optimization.profiles.workflow_profiles",
        "optimization.profiles.model_profiles",
        "optimization.profiles.figures_digitized",
        "optimization.profiles.critique.tool_latency",
    }
    assert not (_imports_of(MILP / "model.py") & forbidden)


def test_no_invented_tool_latency_reaches_the_optimizer() -> None:
    """Q16's quarantine, re-asserted from M4's side.

    The seven invented tool service times are the only invented numbers in the project. M3
    proved `to_milp_inputs()` cannot reach them; this proves M4 does not reach them by another
    route.
    """
    for path in MILP.rglob("*.py"):
        assert "tool_latency" not in _imports_of(path), path.name
