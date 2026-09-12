"""
The Code Generation catalogue: 13 executors covering the four sub-tasks of Figure 1b.

Implements Murakkab (OSDI '26), Section 3.2, "Executor Library" and "Attributes" (p.572), for the
Code Generation workflow of Figure 1b (p.568), Section 2.2 (p.569) and Appendix A.3 + Table 6
(p.585-586).

Figure 1b (p.568), read off the figure:
    Query -> Coder-A/B/C (LLM), with a "Multi-Round Debate" arc drawn back over the three coders
          -> fully cross-connected to Tester-A/Tester-B (LLM)
          -> Python Interp. (Tool) -> Ranker (LLM) -> Answer
Caption: "Code generation workflow: text-only with an LLM Debate structure to write, test and
execute code."

Section 2.2, "Code Generation" (p.569), verbatim: "It adopts the LLM Debate framework, where coder
agents propose candidate solutions and tester agents generate tests and execute them using a
Python interpreter. Each agent plays a unique role (e.g., algorithm developer, unit tester) and
may employ the same or different LLMs. The agents engage in iterative rounds of debate, aiming to
reach consensus or terminating after a pre-defined number of rounds. The final output is selected
as the highest-voted solution, determined by an LLM based on both the proposed candidates and the
original query."

--- GROUNDING, and why it is marked in the source ---------------------------------------------
The paper names NO Code Generation executors beyond Figure 1b's four node labels (DESIGN.md A11).
Everything else here is constructed, and a reader of this file alone must be able to tell which is
which. Every entry therefore carries an inline banner comment and an entry in `GROUNDING`:

  "PAPER"       the paper names this executor for Code Generation (a Figure 1b node);
  "PAPER-FORM"  the paper names the FORM or PATTERN, but applies it elsewhere or leaves the
                application ambiguous;
  "INVENTED"    no counterpart in the paper at all -- ours, and marked as such.

Grounding markers are kept OUT of the `description` strings, because descriptions are the
prompt-facing text the orchestrator LLM selects on (Section 3.2, p.573: it "uses these
descriptions and interfaces to rank and assign executors"). Telling the model which entries the
authors invented would bias selection on a signal the real system does not have.

--- WHY THERE ARE ALTERNATIVES ----------------------------------------------------------------
Milestone 1's stub had exactly ONE type-compatible executor for three of the four sub-tasks, so
"selection" was a forced move and the orchestrator could not be wrong. This catalogue gives every
sub-task at least three signature-viable candidates spanning at least two executor kinds
(DESIGN.md Sections 1.3, 4.5).

--- WHAT IS NOT HERE --------------------------------------------------------------------------
No performance numbers of any kind. Accuracy `a_c`, token counts `t_c`, latency, energy and cost
are Milestone 3 (Section 3.3, p.573). No parameter VALUES: Section 3.2 (p.572) defers "parameter
configuration to a later optimization phase (Section 3.3)". No hardware knobs (`gpu`, `tp`,
`batch`, `n_m`): Section 3.3.1 Decision 3 (p.574) makes those implicit in the model profile.
"""

from __future__ import annotations

from typing import Final

from development.executor_lib.knobs import (
    cores_knob,
    debaters_knob,
    model_knob,
    rounds_knob,
    timeout_knob,
)
from development.executor_lib.registry import register_catalogue
from shared.executor import ExecutorKind, ExecutorSpec, Port
from shared.types import ANSWER, CODE_CANDIDATES, EXECUTION_RESULTS, QUERY, TEST_SUITE

# =============================================================================================
# 1. propose_solutions :: (Query) -> CodeCandidates
#    Figure 1b: Coder-A/B/C plus the Multi-Round Debate arc.
# =============================================================================================

# --- [PAPER] Figure 1b (p.568); Section 2.2 (p.569); knob set verbatim from Section 3.2 (p.572).
LLM_DEBATE_CODERS = ExecutorSpec(
    name="llm_debate_coders",
    kind=ExecutorKind.COMPOSITION,
    # Form 2, Section 3.2 (p.572): "aggregations of models, e.g., a self-reflection or an
    # LLM-Debate pattern built from multiple LLMs".
    description=(
        "LLM Debate composition: multiple coder agents independently propose candidate code "
        "solutions for a coding problem, then debate and revise them over several rounds, "
        "terminating on consensus or a round limit. Many agents, many rounds."
    ),
    inputs=(Port(name="problem", type=QUERY),),
    outputs=(Port(name="candidates", type=CODE_CANDIDATES),),
    # Section 3.2 (p.572): "The LLM Debate composition exposes the knobs: D (number of debaters),
    # R (number of rounds), and model (which LLM to use)." Exactly these three, in that order.
    parameters=(debaters_knob(), rounds_knob(), model_knob()),
)

# --- [PAPER-FORM] Section 3.2 (p.572) names "a self-reflection ... pattern" as executor form 2;
#     the paper REALIZES it for Math Q/A (Figure 15, p.585: "Multi-Round Self-Reflect", with
#     Reflect and Re-Answer arcs over a single Coder-B agent). Applying the same pattern to the
#     Code Generation coder role is OURS, not the paper's.
LLM_SELF_REFLECT_CODER = ExecutorSpec(
    name="llm_self_reflect_coder",
    kind=ExecutorKind.COMPOSITION,
    description=(
        "Self-reflection composition: a single coder agent drafts a candidate code solution, "
        "then critiques and revises its own draft over several rounds, stopping when it is "
        "confident or at a round limit. One agent, no cross-agent debate."
    ),
    inputs=(Port(name="problem", type=QUERY),),
    outputs=(Port(name="candidates", type=CODE_CANDIDATES),),
    # No `D`: a self-reflection loop has one agent by construction. This is the knob-surface
    # difference that distinguishes it from LLM_DEBATE_CODERS at the same signature.
    parameters=(rounds_knob(), model_knob()),
)

# --- [INVENTED] The paper never describes a single-shot coder. Carried over from the Milestone 1
#     stub. Justified only as form 1, Section 3.2 (p.572): "specialized LLM configurations". It
#     exists as a separate entry because `D`'s domain is the literal {2, 4} (Table 6, p.586), so
#     "one coder, one round" is NOT expressible as a parameterization of the debate composition
#     (DESIGN.md A21).
LLM_SINGLE_SHOT_CODER = ExecutorSpec(
    name="llm_single_shot_coder",
    kind=ExecutorKind.LLM,
    description=(
        "A single LLM call that writes one candidate code solution for a coding problem in one "
        "shot, with no debate, revision or self-reflection."
    ),
    inputs=(Port(name="problem", type=QUERY),),
    outputs=(Port(name="candidates", type=CODE_CANDIDATES),),
    parameters=(model_knob(),),
)

# --- [PAPER-FORM] Section 3.2 (p.572) defines form 1 as "specialized LLM configurations
#     (fine-tuning, few-shot learning, or even just domain-specific prompting)". Few-shot
#     prompting is thus a paper-named form; this particular instantiation for coding is ours.
LLM_FEWSHOT_CODER = ExecutorSpec(
    name="llm_fewshot_coder",
    kind=ExecutorKind.LLM,
    description=(
        "A coder LLM specialized by few-shot prompting: the same single-pass generation as a "
        "plain coder, but primed with worked exemplars of similar problems and their reference "
        "implementations. No debate, no revision rounds."
    ),
    inputs=(Port(name="problem", type=QUERY),),
    outputs=(Port(name="candidates", type=CODE_CANDIDATES),),
    parameters=(model_knob(),),
)

# =============================================================================================
# 2. write_tests :: (Query, CodeCandidates) -> TestSuite
#    Figure 1b: Tester-A, Tester-B.
# =============================================================================================

# --- [PAPER] Figure 1b's "Tester-A (LLM)" / "Tester-B (LLM)" (p.568); Section 2.2 (p.569):
#     "tester agents generate tests".
LLM_UNIT_TEST_WRITER = ExecutorSpec(
    name="llm_unit_test_writer",
    kind=ExecutorKind.LLM,
    description=(
        "A tester agent that writes an executable suite of unit tests checking candidate code "
        "solutions against the requirements of the coding problem."
    ),
    inputs=(
        Port(name="problem", type=QUERY),
        Port(name="candidates", type=CODE_CANDIDATES),
    ),
    outputs=(Port(name="tests", type=TEST_SUITE),),
    parameters=(model_knob(),),
)

# --- [PAPER-FORM] Figure 1b draws TWO tester agents fully cross-connected to the coders, and
#     Section 2.2 (p.569) says "The agents engage in iterative rounds of debate" without excluding
#     the testers. Whether testers are a separate sub-task (M1's reading) or extra debaters inside
#     the coder composition is Milestone 1's open item A2. This entry makes that ambiguity
#     TESTABLE rather than settled by omission (decision Q5, 2026-09-10).
#
#     KNOWN CONSEQUENCE (DESIGN.md A14): if this executor is selected, one Code Gen workflow
#     carries TWO independent (D, R) pairs, while Table 6 (p.586) has exactly one `Agents` and one
#     `Rounds` column per configuration row. Either the paper's testers do not debate, or Table 6
#     under-reports the configuration. Deferred to Milestone 3's C_w enumeration, not pre-empted.
LLM_DEBATE_TESTERS = ExecutorSpec(
    name="llm_debate_testers",
    kind=ExecutorKind.COMPOSITION,
    description=(
        "LLM Debate composition over tester agents: several testers each draft unit tests for "
        "the candidate code solutions, then debate and merge them over several rounds into one "
        "agreed test suite. Many testers, many rounds."
    ),
    inputs=(
        Port(name="problem", type=QUERY),
        Port(name="candidates", type=CODE_CANDIDATES),
    ),
    outputs=(Port(name="tests", type=TEST_SUITE),),
    parameters=(debaters_knob(), rounds_knob(), model_knob()),
)

# --- [INVENTED] No such executor in the paper. Justified only by the breadth of form 3,
#     Section 3.2 (p.572): "utility modules for AI workflows to take actions with (e.g., OpenCV
#     frame extractor ..., web-search, file-search, computer-use, or any third-party tools that
#     follow the MCP specification). Traditional ML models are also included as tools".
#     It is here to put a TOOL alternative on a sub-task that otherwise generates tokens -- see
#     the note on Tool invisibility at the bottom of this module.
PROPERTY_TEST_GENERATOR = ExecutorSpec(
    name="property_test_generator",
    kind=ExecutorKind.TOOL,
    description=(
        "Property-based test generator tool: derives a test suite mechanically from the "
        "signatures and type annotations of the candidate code, fuzzing inputs and asserting "
        "invariants. No language model is involved."
    ),
    inputs=(
        Port(name="problem", type=QUERY),
        Port(name="candidates", type=CODE_CANDIDATES),
    ),
    outputs=(Port(name="tests", type=TEST_SUITE),),
    parameters=(cores_knob(), timeout_knob()),
)

# =============================================================================================
# 3. execute_tests :: (CodeCandidates, TestSuite) -> ExecutionResults
#    Figure 1b: "Python Interp. (Tool)".
# =============================================================================================

# --- [PAPER] Figure 1b's "Python Interp. (Tool)" node (p.568); Section 2.2 (p.569): "execute them
#     using a Python interpreter".
PYTHON_INTERPRETER = ExecutorSpec(
    name="python_interpreter",
    kind=ExecutorKind.TOOL,
    description=(
        "Sandboxed Python interpreter tool: runs a unit test suite against candidate code "
        "solutions in-process and reports which tests passed, which failed, and the failure "
        "output."
    ),
    inputs=(
        Port(name="code", type=CODE_CANDIDATES),
        Port(name="tests", type=TEST_SUITE),
    ),
    outputs=(Port(name="results", type=EXECUTION_RESULTS),),
    # `cores` is paper-named (Section 3.2, p.572, for the frame extractor); `timeout_s` is
    # invented. Neither can reach the MILP -- see the Tool-invisibility note below.
    parameters=(cores_knob(), timeout_knob()),
)

# --- [INVENTED] Not in the paper. A second execution backend with real engineering differences
#     from the first (per-candidate container isolation, different startup cost and resource
#     envelope) and ZERO difference to Appendix A.5 -- which is exactly the point it is here to
#     make. See the Tool-invisibility note below.
SANDBOXED_CONTAINER_RUNNER = ExecutorSpec(
    name="sandboxed_container_runner",
    kind=ExecutorKind.TOOL,
    description=(
        "Container-isolated test runner tool: executes each candidate solution against the unit "
        "test suite inside its own throwaway container, giving stronger isolation than an "
        "in-process interpreter at the cost of per-candidate startup, and reports pass/fail "
        "results."
    ),
    inputs=(
        Port(name="code", type=CODE_CANDIDATES),
        Port(name="tests", type=TEST_SUITE),
    ),
    outputs=(Port(name="results", type=EXECUTION_RESULTS),),
    parameters=(cores_knob(), timeout_knob()),
)

# --- [INVENTED -- AND DELIBERATELY A BAD EXECUTOR. READ THIS BEFORE DELETING IT.] --------------
#     Decision Q3 (Arno, 2026-09-10): include, clearly marked.
#
#     This executor does not run any code; it asks an LLM to *predict* what the tests would do.
#     No engineer would deploy it over a real interpreter. It is in the catalogue as a probe,
#     because it is the ONLY `execute_tests` candidate that Appendix A.5 can see at all:
#
#       * `python_interpreter` and `sandboxed_container_runner` are TOOLs. A Tool has no model
#         profile `m`, generates no tokens, and needs no GPU instance, so it contributes exactly
#         zero to capacity eq. (3), zero to the latency filter eq. (5), and zero to the energy and
#         cost objectives eqs. (11)-(12). Choosing either is free and unobservable.
#       * `llm_execution_simulator` consumes tokens, so it is the only one of the three that shows
#         up anywhere in the formulation.
#
#     The catalogue therefore encodes an inversion: the executor with real cost is visible to the
#     optimizer, and the two that actually work are invisible. That inversion is a finding about
#     Murakkab's formulation, reproduced rather than repaired (standing policy, 2026-09-10), and
#     this entry is what makes it demonstrable inside the library instead of only in prose.
LLM_EXECUTION_SIMULATOR = ExecutorSpec(
    name="llm_execution_simulator",
    kind=ExecutorKind.LLM,
    description=(
        "An LLM that predicts the outcome of a unit test suite by reading the candidate code and "
        "the tests and reasoning about what would happen, without executing anything. Cheaper to "
        "deploy than a real sandbox and strictly less trustworthy: its reported results are "
        "guesses, not observations."
    ),
    inputs=(
        Port(name="code", type=CODE_CANDIDATES),
        Port(name="tests", type=TEST_SUITE),
    ),
    outputs=(Port(name="results", type=EXECUTION_RESULTS),),
    parameters=(model_knob(),),
)

# =============================================================================================
# 4. rank_solutions :: (Query, [CodeCandidates | ExecutionResults | TestSuite]) -> Answer
#    Figure 1b: "Ranker (LLM)" -> "Answer".
# =============================================================================================

# --- [PAPER] Figure 1b's "Ranker (LLM)" (p.568); Section 2.2 (p.569): "The final output is
#     selected as the highest-voted solution, determined by an LLM based on both the proposed
#     candidates and the original query."
LLM_RANKER = ExecutorSpec(
    name="llm_ranker",
    kind=ExecutorKind.LLM,
    description=(
        "A ranker LLM that selects the highest-voted final solution given the original coding "
        "problem and some context about the candidate solutions, such as their test results."
    ),
    inputs=(
        Port(name="problem", type=QUERY),
        # Heterogeneous variadic port, mirroring Listing 2's `q_a(query, [frames, transcript])`
        # (p.572) and the correction recorded in M1's DESIGN.md Section 4.3.
        Port(
            name="context",
            type=CODE_CANDIDATES,
            variadic=True,
            also_accepts=(EXECUTION_RESULTS, TEST_SUITE),
        ),
    ),
    outputs=(Port(name="answer", type=ANSWER),),
    parameters=(model_knob(),),
)

# --- [INVENTED] The paper says the winner is "the highest-voted solution, determined by an LLM"
#     (Section 2.2, p.569) -- singular LLM. A panel of independent voters is a natural reading of
#     "highest-voted" but is not what the paper describes, so this entry is ours.
#     Note the knob name: `D`, not a new `V`. Section 3.2 (p.572) defines `D` as the number of
#     agents in a composition; introducing a second name for the same structural knob would
#     fragment Milestone 3's configuration enumeration for no benefit (DESIGN.md Section 4.4).
LLM_VOTE_ENSEMBLE_RANKER = ExecutorSpec(
    name="llm_vote_ensemble_ranker",
    kind=ExecutorKind.COMPOSITION,
    description=(
        "Voting ensemble composition: several judge agents independently score the candidate "
        "solutions against the coding problem and the supporting context, and the majority vote "
        "decides the final answer. Several judges, one round, no debate between them."
    ),
    inputs=(
        Port(name="problem", type=QUERY),
        Port(
            name="context",
            type=CODE_CANDIDATES,
            variadic=True,
            also_accepts=(EXECUTION_RESULTS, TEST_SUITE),
        ),
    ),
    outputs=(Port(name="answer", type=ANSWER),),
    parameters=(debaters_knob(), model_knob()),
)

# --- [INVENTED] Not in the paper; grounded only in form 3's "Traditional ML models are also
#     included as tools" (Section 3.2, p.572). A deterministic, model-free ranker.
#
#     INTERFACE WART, recorded deliberately (DESIGN.md A19): this executor has no use whatsoever
#     for the `problem` input, but must declare it. The declarative spec calls
#     `rank_solutions(query, [candidates, results])` with arity 2, and M1 binds arguments
#     POSITIONALLY (Listing 2's data flow is Python call composition), so any candidate for this
#     sub-task must declare exactly two input ports. Positional arity forces interface padding.
#     Not repaired.
TEST_PASS_RATE_RANKER = ExecutorSpec(
    name="test_pass_rate_ranker",
    kind=ExecutorKind.TOOL,
    description=(
        "Deterministic ranker tool: picks the candidate solution with the highest unit-test pass "
        "rate, breaking ties by shortest implementation. Ignores the problem statement entirely "
        "and uses no language model, so it can only rank what the tests already measured."
    ),
    inputs=(
        # Declared solely to satisfy positional arity; never read. See the wart note above.
        Port(name="problem", type=QUERY),
        Port(
            name="context",
            type=CODE_CANDIDATES,
            variadic=True,
            also_accepts=(EXECUTION_RESULTS, TEST_SUITE),
        ),
    ),
    outputs=(Port(name="answer", type=ANSWER),),
    parameters=(),
)


# =============================================================================================
# The catalogue
# =============================================================================================

CODE_GENERATION_EXECUTORS: Final[tuple[ExecutorSpec, ...]] = (
    # propose_solutions
    LLM_DEBATE_CODERS,
    LLM_SELF_REFLECT_CODER,
    LLM_SINGLE_SHOT_CODER,
    LLM_FEWSHOT_CODER,
    # write_tests
    LLM_UNIT_TEST_WRITER,
    LLM_DEBATE_TESTERS,
    PROPERTY_TEST_GENERATOR,
    # execute_tests
    PYTHON_INTERPRETER,
    SANDBOXED_CONTAINER_RUNNER,
    LLM_EXECUTION_SIMULATOR,
    # rank_solutions
    LLM_RANKER,
    LLM_VOTE_ENSEMBLE_RANKER,
    TEST_PASS_RATE_RANKER,
)
"""Declaration order is grouped by sub-task and is the orchestrator's documented tie-break order.

The four names the paper itself provides (`llm_debate_coders`, `llm_unit_test_writer`,
`python_interpreter`, `llm_ranker`) and `llm_single_shot_coder` are carried over from Milestone 1
UNCHANGED. Executor names are join keys for Milestone 3's profiles and appear verbatim in the
orchestrator prompt: renaming one silently invalidates every profile keyed on it.
"""


GROUNDING: Final[dict[str, str]] = {
    "llm_debate_coders": "PAPER",  # Figure 1b (p.568); Section 2.2 (p.569); Section 3.2 (p.572)
    "llm_self_reflect_coder": "PAPER-FORM",  # form 2 named p.572; realized for Math Q/A, Fig 15
    "llm_single_shot_coder": "INVENTED",  # form 1 only; no such executor in the paper
    "llm_fewshot_coder": "PAPER-FORM",  # "few-shot learning" named as form 1, p.572
    "llm_unit_test_writer": "PAPER",  # Figure 1b Tester-A/B (p.568)
    "llm_debate_testers": "PAPER-FORM",  # M1's A2: do the testers debate? Figure 1b is ambiguous
    "property_test_generator": "INVENTED",
    "python_interpreter": "PAPER",  # Figure 1b "Python Interp. (Tool)" (p.568)
    "sandboxed_container_runner": "INVENTED",
    "llm_execution_simulator": "INVENTED",  # deliberately bad; see its banner comment
    "llm_ranker": "PAPER",  # Figure 1b "Ranker (LLM)" (p.568)
    "llm_vote_ensemble_ranker": "INVENTED",
    "test_pass_rate_ranker": "INVENTED",
}
"""How each entry relates to the paper (DESIGN.md Section 4, A11). Machine-readable so that the
source and the design document cannot drift apart; asserted in tests."""

NOT_NAMED_BY_THE_PAPER: Final[frozenset[str]] = frozenset(
    name for name, grounding in GROUNDING.items() if grounding != "PAPER"
)
"""The nine entries the paper does not name as Code Generation executors: six pure inventions and
three realizations of a form the paper names but applies elsewhere or leaves ambiguous."""


# ---------------------------------------------------------------------------------------------
# Tool invisibility -- the finding this catalogue is built to expose
# ---------------------------------------------------------------------------------------------
#
# Four of the thirteen entries are TOOLs (`property_test_generator`, `python_interpreter`,
# `sandboxed_container_runner`, `test_pass_rate_ranker`). Appendix A.5 (p.586-587) is denominated
# entirely in tokens and model profiles:
#
#   eq. (3)  capacity:  mu_m * SUM_{w,s,c} x^peak_{w,s,c,m} * t_c  <=  n_m * theta_m
#   eq. (5)  latency:   x = 0 if  l^TTFT_m + t_c * l^TPOT_m > tau_{w,s}
#   eq. (11) energy:    min SUM_m n_m * e_m * g_m
#   eq. (12) cost:      min SUM_m n_m * g_m * c_{g(m)}
#
# A Tool has no model profile `m`, no `theta_m`, no `l^TTFT_m` / `l^TPOT_m`, no `e_m`, needs no
# GPU instance, and contributes nothing to `t_c`. Therefore EVERY TOOL IN THIS CATALOGUE
# CONTRIBUTES EXACTLY ZERO cost, energy, latency and capacity to the entire formulation, and the
# `cores` and `timeout_s` knobs they expose can never reach the MILP (A.5 has no CPU resource type
# and no wall-clock term). `python_interpreter` vs `sandboxed_container_runner` is a choice whose
# objective value is bit-identical either way.
#
# This is PROGRESS.md's M1 gap "Tool executors are unrepresentable in A.5", made concrete. It is
# reproduced, not repaired: no shadow CPU resource, no tool-latency field, no synthetic token cost.
# See DESIGN.md Section 6.1.

register_catalogue("code_generation", CODE_GENERATION_EXECUTORS)
