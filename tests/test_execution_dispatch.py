"""
Dispatch -- A83, and the prohibition M6 inherits from M4.

Section 3.4 says request dispatch is "deterministic given the selected workflow". A.5 declares
`x^peak, x^avg in R+`. Those two statements are not compatible when the optimum spreads load
across several `(c, m)` pairs, which it routinely does (A70). Something must turn a fraction into
a decision, and the paper never says what.

So the policy is a named choice, three are implemented, and the difference between them is
MEASURED rather than asserted -- because the whole reason it matters is the error structure, and
an argument about error structure that never measures the error is worthless.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from execution.dispatch import (
    DEFAULT_POLICY,
    Dispatcher,
    HashByRequest,
    RoundRobin,
    WeightedRandom,
    policy_named,
)

ROUTING = {("cfg_a", "model_a"): 0.7, ("cfg_b", "model_b"): 0.3}
EXECUTION = pathlib.Path(__file__).resolve().parent.parent / "execution"


# ---------------------------------------------------------------------------------------------
# All policies honour the plan in the mean
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["weighted_random", "round_robin", "hash_by_request"])
def test_realized_split_converges_to_the_plan(name: str) -> None:
    """Whatever the policy, dispatching N requests must reproduce the optimizer's fractions.

    If it did not, the runtime would be serving a different plan from the one the MILP solved,
    and every GPU count in the milestone would describe an allocation nobody runs.
    """
    dispatcher = Dispatcher(policy=policy_named(name, seed=11))
    for i in range(4000):
        dispatcher.dispatch(ROUTING, i)
    split = dispatcher.realized_split()
    assert split[("cfg_a", "model_a")] == pytest.approx(0.7, abs=0.05)
    assert split[("cfg_b", "model_b")] == pytest.approx(0.3, abs=0.05)


def test_round_robin_error_is_tighter_than_random(name_seed: int = 7) -> None:
    """A83, measured. The policies differ in error structure, not in mean.

    Round-robin's deviation is bounded by the largest-remainder schedule; weighted-random's is
    O(1/sqrt(N)). Over a SHORT window -- which is what the auto-scaler sees -- that difference is
    the short-term variance Section 3.4 says the auto-scaler exists to absorb. Choosing
    round-robin by default would make the auto-scaler look unnecessary by construction.
    """
    window = 60
    rr = Dispatcher(policy=RoundRobin())
    wr = Dispatcher(policy=WeightedRandom(__import__("random").Random(name_seed)))
    for i in range(window):
        rr.dispatch(ROUTING, i)
        wr.dispatch(ROUTING, i)
    rr_err = abs(rr.realized_split().get(("cfg_a", "model_a"), 0.0) - 0.7)
    wr_err = abs(wr.realized_split().get(("cfg_a", "model_a"), 0.0) - 0.7)
    assert rr_err <= wr_err + 1e-9, (
        f"round-robin error {rr_err:.4f} should not exceed random's {wr_err:.4f} over a short "
        "window; if it does, the control arm is not a control"
    )


def test_hash_dispatch_is_stable_under_replay() -> None:
    """Deterministic per request id and order-independent -- the replay control."""
    a = Dispatcher(policy=HashByRequest())
    b = Dispatcher(policy=HashByRequest())
    ids = list(range(200))
    first = [a.dispatch(ROUTING, i) for i in ids]
    second = [b.dispatch(ROUTING, i) for i in reversed(ids)][::-1]
    assert first == second


def test_the_default_is_named_and_is_the_noisy_one() -> None:
    """Q33. Weighted random is the default deliberately: it is the only policy whose error
    structure creates the short-term variance the component under test exists to absorb."""
    assert DEFAULT_POLICY == "weighted_random"


def test_an_unknown_policy_is_refused() -> None:
    with pytest.raises(KeyError):
        policy_named("magic")


def test_the_policy_travels_with_the_dispatcher() -> None:
    """No policy is applied silently -- A83 is a fork, so the arm has to be visible."""
    for name in ("weighted_random", "round_robin", "hash_by_request"):
        assert policy_named(name).name == name


# ---------------------------------------------------------------------------------------------
# The prohibition -- M6 does not schedule by the DAG
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


#: The ONLY module permitted to read a DAG, and only for data-flow correctness (M7).
DAG_WALKER = "workflow_run.py"


def test_no_allocation_module_reads_a_dag() -> None:
    """A.5 has no precedence constraint and no makespan term, so the runtime that realises it
    adds neither. This is M1's rule, carried through M4, M5 and M6.

    M7 NARROWS the rule rather than breaking it. `workflow_run.py` must read the DAG, because a
    workflow cannot be executed without respecting data flow -- but it is the only module that
    may, and it may do so only for ordering, never for allocation. The distinction:

        walking the DAG for DATA-FLOW CORRECTNESS   -- permitted, workflow_run.py only
        scheduling by the DAG for RESOURCE ALLOCATION -- forbidden everywhere

    `test_end_to_end.py` enforces the second half on the walker itself: the `(c, m)` pair is
    fixed before the walk begins, ties break on declaration order rather than duration, and no
    critical-path or earliest-finish identifier exists in it.

    If a module that ALLOCATES ever needed the DAG, that would be the finding -- and it would
    belong in `architecture-decisions.md`, not in `dispatch.py`.
    """
    offenders = []
    for path in EXECUTION.rglob("*.py"):
        if "critique" in path.parts or path.name == DAG_WALKER:
            continue
        for imported in _imports_of(path):
            if imported.startswith("shared.workflow") or "logical" in imported.lower():
                offenders.append(f"{path.name} -> {imported}")
    assert not offenders, "allocation modules reading a DAG: " + "; ".join(offenders)


def test_the_dag_exemption_is_exactly_one_module() -> None:
    """The narrowing must stay narrow. If a second module starts reading the DAG, that is a
    prohibition breach dressed as an exemption."""
    readers = []
    for path in EXECUTION.rglob("*.py"):
        if "critique" in path.parts:
            continue
        for imported in _imports_of(path):
            if imported.startswith("shared.workflow"):
                readers.append(path.name)
    assert set(readers) == {DAG_WALKER}, f"DAG readers: {sorted(set(readers))}"


def test_no_scheduling_heuristic_hides_in_the_dispatcher() -> None:
    """Names are not proof, but a critical-path or earliest-finish-time helper appearing here
    would be a precedence mechanism arriving by the back door."""
    # Checked on the AST, not raw text: `dispatch.py`'s docstring legitimately EXPLAINS the
    # prohibition, and a substring scan cannot tell an explanation from a violation.
    tree = ast.parse((EXECUTION / "dispatch.py").read_text(encoding="utf-8-sig"))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    names |= {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    for banned in ("critical_path", "earliest_finish", "makespan", "topological_sort"):
        assert banned not in names, f"{banned} is a precedence mechanism arriving by the back door"


def test_execution_does_not_import_its_own_critique_package() -> None:
    """Same one-way boundary M3 and M4 enforce."""
    for path in EXECUTION.rglob("*.py"):
        if "critique" in path.parts:
            continue
        for imported in _imports_of(path):
            assert "execution.critique" not in imported, f"{path.name} imports critique"
