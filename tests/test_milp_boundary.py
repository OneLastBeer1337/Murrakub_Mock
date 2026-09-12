"""
The enforced boundary: `to_milp_inputs()` exposes exactly Appendix A.5's parameter list, and
nothing in `critique/` is reachable from it (Q16, DESIGN.md Sections 4.3 and 12.1).

This is the test that lets Milestone 3 claim 0% invented values in the MILP-facing set. The
claim is not "we were careful"; it is "an import-graph walk from the boundary function never
reaches the module where the invented numbers live, and the parameter list is pinned".

Two failure modes are guarded:

  * LEAKAGE IN -- a `critique/` number reaching a constraint or objective. Seven invented tool
    service times exist (Section 12.1); if any entered eq. (3), (5) or (12), every headline
    number would be contaminated by a value with no source.
  * LEAKAGE OUT -- `MilpInputs` growing a field A.5 does not have. `node_tokens`,
    `prompt_tokens` and `accuracy_measured_on_model` are all NON-MILP by design, and each one
    exists to measure a gap rather than to be optimised against. Exposing one would silently
    repair the formulation we are supposed to be reproducing faithfully.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from optimization.profiles.profile_sets import NAMED_SETS, budget_scenarios, profile_set
from optimization.profiles.provenance import Measured, Provenance, Unavailable
from optimization.profiles.schema import (
    MilpInputs,
    OperatingPointPolicy,
    ProfileSet,
    TokenPolicy,
)

REPO = pathlib.Path(__file__).resolve().parent.parent
PROFILES_DIR = REPO / "optimization" / "profiles"
CRITIQUE_MODULES = {
    "optimization.profiles.critique.tool_latency",
    "optimization.profiles.critique.critical_path",
}


@pytest.fixture(scope="module")
def inputs() -> MilpInputs:
    return profile_set("baseline").to_milp_inputs()


# ---------------------------------------------------------------------------------------------
# The parameter list is exactly A.5's
# ---------------------------------------------------------------------------------------------


def test_a5_parameter_list_is_pinned() -> None:
    """Appendix A.5 (p.586). Thirteen parameters, named as the paper names them."""
    assert MilpInputs.A5_PARAMETERS == (
        "a_c",
        "t_c",
        "theta_m",
        "l_ttft_m",
        "l_tpot_m",
        "g_m",
        "e_m",
        "c_g",
        "B_g",
        "tau",
        "lam_peak",
        "lam_avg",
        "alpha",
    )


def test_every_a5_parameter_is_present(inputs: MilpInputs) -> None:
    for name in MilpInputs.A5_PARAMETERS:
        assert hasattr(inputs, name), f"A.5 names {name} and MilpInputs does not carry it"


def test_mu_m_is_absent(inputs: MilpInputs) -> None:
    """A42. eq. (3) introduces a multiplexing factor the paper never defines, bounds or reports,
    and Section 3.3's list of what a profile contains does not include it. It cannot be smuggled
    into the profile layer; it remains Milestone 5's problem."""
    assert not hasattr(inputs, "mu_m")
    assert "mu_m" not in MilpInputs.A5_PARAMETERS


def test_non_milp_fields_are_not_exposed(inputs: MilpInputs) -> None:
    """`node_tokens`, `prompt_tokens` and `accuracy_measured_on_model` measure gaps. They must
    not be reachable from the object the optimizer consumes."""
    for forbidden in ("node_tokens", "node_service_time", "prompt_tokens",
                      "accuracy_measured_on_model"):
        assert not hasattr(inputs, forbidden), f"{forbidden} escaped into MilpInputs"


def test_workflow_profile_to_milp_exposes_only_a_c_and_t_c() -> None:
    pset = profile_set("baseline")
    wp = next(iter(pset.workflow.values()))
    assert set(wp.to_milp()) == {"a_c", "t_c"}


def test_coherence_predicate_exists_but_is_not_a_parameter(inputs: MilpInputs) -> None:
    """A51. A.5 has NO constraint linking `c` to `m`, so `x_{w,s,c,m}` may claim one model's
    accuracy while paying another's throughput. `coherent()` exists so M4 can MEASURE how much
    selected mass is incoherent -- it is a reporting tool, and must never become a constraint."""
    assert hasattr(inputs, "coherent")
    assert "coherent" not in MilpInputs.A5_PARAMETERS


# ---------------------------------------------------------------------------------------------
# The quarantine
# ---------------------------------------------------------------------------------------------


def _module_name(path: pathlib.Path) -> str:
    return ".".join(path.relative_to(REPO).with_suffix("").parts)


def _imports_of(path: pathlib.Path) -> set[str]:
    # utf-8-sig: several modules in this repo were written with a BOM, which `utf-8` hands to
    # `ast.parse` as U+FEFF and which fails as a non-printable character.
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
            found.update(f"{node.module}.{a.name}" for a in node.names)
    return found


def _reachable_from(start: str) -> set[str]:
    """Transitive import closure over the profile package, by static analysis.

    Static rather than dynamic on purpose: a runtime check would only catch a leak on the code
    path the test happens to exercise, whereas an invented number is dangerous the moment it is
    IMPORTABLE from a MILP-facing module by any path.
    """
    seen: set[str] = set()
    queue = [start]
    while queue:
        name = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        rel = pathlib.Path(*name.split(".")).with_suffix(".py")
        path = REPO / rel
        if not path.exists():
            continue
        for imported in _imports_of(path):
            if imported.startswith("optimization.") and imported not in seen:
                queue.append(imported)
    return seen


def test_critique_modules_exist_and_contain_invented_values() -> None:
    """The quarantine is only meaningful if there is something to quarantine."""
    from optimization.profiles.critique.tool_latency import TOOL_SERVICE_TIMES

    assert len(TOOL_SERVICE_TIMES) == 7
    for name, value in TOOL_SERVICE_TIMES.items():
        assert value.provenance is Provenance.INVENTED, name
        assert value.note, "an invented value must say why it exists"


@pytest.mark.parametrize(
    "entry",
    ["optimization.profiles.profile_sets", "optimization.profiles.schema"],
)
def test_no_milp_facing_module_reaches_critique(entry: str) -> None:
    """The load-bearing assertion of Q16.

    `to_milp_inputs()` lives in `schema.py`; the named sets that produce a `ProfileSet` live in
    `profile_sets.py`. Neither may reach `critique/` by any import path.
    """
    reachable = _reachable_from(entry)
    leaked = reachable & CRITIQUE_MODULES
    assert not leaked, f"{entry} can reach quarantined modules: {sorted(leaked)}"
    assert not any("critique" in m for m in reachable), sorted(
        m for m in reachable if "critique" in m
    )


def test_the_quarantine_test_would_actually_catch_a_leak() -> None:
    """A guard against the guard silently passing.

    `critical_path.py` DOES import `tool_latency`, so the closure walker must report that edge.
    If this fails, `_reachable_from` has stopped following imports and every other assertion in
    this section is vacuous.
    """
    reachable = _reachable_from("optimization.profiles.critique.critical_path")
    assert "optimization.profiles.critique.tool_latency" in reachable


@pytest.mark.parametrize("name", sorted(NAMED_SETS))
def test_no_named_set_carries_an_invented_value(name: str) -> None:
    pset = profile_set(name)
    inputs = pset.to_milp_inputs()
    for param in MilpInputs.A5_PARAMETERS:
        value = getattr(inputs, param)
        values = value.values() if hasattr(value, "values") else [value]
        for v in values:
            if isinstance(v, Measured):
                assert v.provenance is not Provenance.INVENTED, f"{name}.{param}"


# ---------------------------------------------------------------------------------------------
# Shape of what crosses the boundary
# ---------------------------------------------------------------------------------------------


def test_every_parameter_is_a_value_or_a_mapping_of_values(inputs: MilpInputs) -> None:
    """Nothing crosses the boundary as a bare float -- M4 must be able to see provenance and
    absence on every input it consumes."""
    for param in MilpInputs.A5_PARAMETERS:
        value = getattr(inputs, param)
        values = list(value.values()) if hasattr(value, "values") else [value]
        for v in values:
            assert isinstance(v, (Measured, Unavailable)), f"{param}: {type(v).__name__}"


def test_data_excluded_is_populated_and_matches_the_unavailable_set(inputs: MilpInputs) -> None:
    """Q19: M4 must report configurations excluded for LACK OF DATA rather than lack of merit.
    The list has to be non-empty (14 configurations lack `t_c`) and has to agree with the
    parameters it claims to summarise."""
    assert inputs.data_excluded, "14 configurations lack t_c; none were reported as excluded"
    unavailable = {
        str(k) for k, v in inputs.t_c.items() if isinstance(v, Unavailable)
    } | {str(k) for k, v in inputs.a_c.items() if isinstance(v, Unavailable)}
    assert unavailable <= set(inputs.data_excluded)


def test_configs_by_workflow_covers_the_whole_space(inputs: MilpInputs) -> None:
    total = sum(len(v) for v in inputs.configs_by_workflow.values())
    assert total == 44 == len(inputs.a_c) == len(inputs.t_c)


def test_the_boundary_is_reproducible(inputs: MilpInputs) -> None:
    """Two calls with the same policies must agree. A profile set that changed between calls
    would make every M4 result unreproducible in a way no single run could reveal."""
    again = profile_set("baseline").to_milp_inputs()
    assert {str(k): str(v) for k, v in again.t_c.items()} == {
        str(k): str(v) for k, v in inputs.t_c.items()
    }


@pytest.mark.parametrize("policy", list(OperatingPointPolicy), ids=lambda p: p.value)
def test_every_operating_point_policy_crosses_the_boundary(policy) -> None:
    """The collapse is a named, swappable policy applied AT the boundary rather than a hidden
    constant (A37b). Each one must produce a usable `MilpInputs`."""
    inputs = profile_set("baseline").to_milp_inputs(operating_point=policy)
    assert inputs.operating_point_policy is policy
    assert inputs.theta_m


# ---------------------------------------------------------------------------------------------
# M4 readiness -- every parameter M4 consumes is either usable or visibly absent
# ---------------------------------------------------------------------------------------------


def test_budget_is_absent_by_default_and_says_so(inputs: MilpInputs) -> None:
    """A43. `B_g` is `Unavailable` in every profile set, and that is faithful: Sections 4.2/4.3
    state no budget, so eq. (7) is inactive for the headline experiments.

    The danger is that eq. (7) is the ONLY thing bounding allocation. An M4 that met this
    `Unavailable` and quietly skipped the constraint would produce an unbounded provisioning with
    no warning, so the absence has to be loud and has to name eq. (7).
    """
    for gpu, value in inputs.B_g.items():
        assert isinstance(value, Unavailable), f"{gpu}: a budget was invented"
        assert "eq7" in value.blocks, f"{gpu}: absence does not name the constraint it blocks"


def test_table_3_budget_scenarios_are_injectable() -> None:
    """M4 must be able to reproduce Section 4.5's sweep without inventing anything.

    Table 3's six rows are the paper's own budget settings; `no_budget` is the headline case,
    named so it has to be chosen deliberately rather than defaulted into.
    """
    scenarios = budget_scenarios()
    assert "no_budget" in scenarios
    assert len(scenarios) == 7, "no_budget plus Table 3's six sweep rows"

    inputs = profile_set("baseline").to_milp_inputs(budget=scenarios["a2000_h500"])
    assert float(inputs.B_g["A100"].value) == 2000.0
    assert float(inputs.B_g["H100"].value) == 500.0
    for value in inputs.B_g.values():
        assert value.provenance is Provenance.PAPER_TABLE

    assert all(isinstance(v, Unavailable) for v in scenarios["no_budget"].values())


def test_data_excluded_covers_model_side_gaps_too(inputs: MilpInputs) -> None:
    """Q19 requires M4 to REPORT what it excluded for lack of data.

    The register originally listed only configuration-side gaps (`t_c`, `a_c`, `theta_m`), which
    left the 7 model profiles with no TTFT invisible -- including Llava-OneVision-7B, the model
    Section 4.6's parallelism study runs (A62). M4 would have applied eq. (5) to them and met an
    `Unavailable` mid-constraint.
    """
    ttft_gaps = {str(k) for k, v in inputs.l_ttft_m.items() if isinstance(v, Unavailable)}
    assert ttft_gaps, "expected model profiles with no TTFT (A35/A36)"
    assert ttft_gaps <= set(inputs.data_excluded), (
        "model profiles with no TTFT are missing from data_excluded: "
        f"{sorted(ttft_gaps - set(inputs.data_excluded))}"
    )
    assert any("Llava-OneVision-7B" in e for e in inputs.data_excluded), (
        "A62: the model Section 4.6 runs must be reported as eq. (5)-excluded"
    )


def test_the_named_sets_are_exactly_those_that_exist() -> None:
    """A64. DESIGN.md Section 9.2 lists seven named sets; five exist, and the two absences are
    deliberate rather than forgotten. Pinned so the gap stays visible until Arno rules on it."""
    assert set(NAMED_SETS) == {
        "baseline",
        "paper_only",
        "pessimistic",
        "optimistic",
        "derived_tiers",
    }


def test_token_policy_percentile_defaults_to_the_p90() -> None:
    """Section 4.1/4.2 (p.576): "We assume the 90th percentile token generation load". A46
    records that this sentence exists only in [OSDI], and it shapes every capacity number."""
    assert TokenPolicy().percentile == 90
    assert profile_set("baseline").to_milp_inputs().token_policy.percentile == 90
