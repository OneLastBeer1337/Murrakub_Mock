# Declarative workflow specification: Code Generation.
#
# Form: Murakkab (OSDI '26), Section 3.2, "Declarative Specification" + Listing 2 (p.572).
# Content: the Code Generation workflow of Figure 1b (p.568), Section 2.2 (p.569) and
# Appendix A.3 / Table 6 (p.585-586).
#
# NOTE: the paper contains NO declarative listing for Code Generation -- Listing 2 covers Video
# Q/A only (DESIGN.md gap A1). This spec applies Listing 2's format to the Code Generation
# workflow the paper does describe. Intended mapping onto Figure 1b:
#     propose_solutions -> Coder-A/B/C + the Multi-Round Debate arc  (structured composition)
#     write_tests       -> Tester-A/B                                (LLM)
#     execute_tests     -> Python Interp.                            (Tool)
#     rank_solutions    -> Ranker                                    (LLM)
#
# No configuration appears below: "Configuration details (e.g., which LLM to use, number of
# frames to extract, resource allocation) are omitted from the specification" (Section 3.2,
# p.573). The debate loop is the knob R, not an edge, because the logical workflow "is
# represented as a directed acyclic graph (DAG)" (Section 3.2, p.573).
#
# This file is PARSED, never executed (see development/spec_parser.py).

# == Sub-tasks in the workflow ==
propose_solutions = "Given a coding problem, propose candidate code solutions by having multiple agents debate and revise them over several rounds."
write_tests       = "Given a coding problem and candidate code solutions, write unit tests that check them."
execute_tests     = "Execute the candidate code solutions against the unit tests and report the results."
rank_solutions    = "Select the highest-voted solution given the candidate solutions, their test results, and the original query."
# == Workflow description (sub-tasks and data flow) ==
def workflow(query):
    candidates = propose_solutions(query)
    tests      = write_tests(query, candidates)
    results    = execute_tests(candidates, tests)
    answer     = rank_solutions(query, [candidates, results])
    return answer
# == Execution with example request ==
query  = "Write a function that returns the longest common subsequence of two strings."
result = run(workflow(query), slo=HIGH_ACCURACY)
