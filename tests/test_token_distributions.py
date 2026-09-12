"""
`t_c` -- the invariants of DESIGN.md Section 12.2, plus the per-node decomposition of A59.

`t_c` is the single most load-bearing number in the reproduction: eq. (3)'s capacity constraint
multiplies it by every peak request rate, and eq. (5)'s latency filter multiplies it by TPOT. Its
definition is also the easiest thing to get subtly wrong, because a per-request total and a sum
of per-call totals are both "the number of tokens" in English and differ by a large factor.

Section 4.1/4.2 (p.576) binds it to the p90: "We assume the 90th percentile token generation load
from our profiles when making resource allocation decisions for all policies for a fair
comparison." A46 records that this sentence exists only in [OSDI].
"""

from __future__ import annotations

import pytest

from optimization.profiles.enumerate_cw import enumerate_code_generation, enumerate_video_qa
from optimization.profiles.provenance import Unavailable
from optimization.profiles.schema import TokenDistribution
from optimization.profiles.workflow_profiles import (
    LLM_NODES,
    TOOL_NODES,
    build_code_generation_profiles,
    build_video_profiles,
    build_workflow_profiles,
)


@pytest.fixture(scope="module")
def profiles():
    return build_workflow_profiles()


def _p90(dist) -> float:
    return float(dist.p90().value)


# ---------------------------------------------------------------------------------------------
# The p90 is mandatory
# ---------------------------------------------------------------------------------------------


def test_every_available_distribution_has_a_p90(profiles) -> None:
    """`TokenDistribution.__post_init__` refuses to construct without one; this asserts the rule
    survives assembly for all 44 configurations."""
    for key, wp in profiles.items():
        if isinstance(wp.tokens, Unavailable):
            continue
        assert 90 in wp.tokens.percentiles, f"{key}: no p90"


def test_unavailable_tokens_block_the_right_equations(profiles) -> None:
    """An absent `t_c` must name eq. (3), (5) and (6) as blocked, so `coverage_report()` can
    count them without anyone remembering which equations consume tokens."""
    for key, wp in profiles.items():
        if not isinstance(wp.tokens, Unavailable):
            continue
        assert set(wp.tokens.blocks) >= {"eq3", "eq5"}, f"{key}: {wp.tokens.blocks}"


def test_the_documented_number_of_configurations_lack_token_data(profiles) -> None:
    """Q19 accepted 14 of 44 `t_c` values as `Unavailable`. Pinning the count means a silent
    regression that starts inventing data fails here rather than improving a coverage stat."""
    missing = [k for k, wp in profiles.items() if isinstance(wp.tokens, Unavailable)]
    assert len(missing) == 14, sorted(str(k) for k in missing)


# ---------------------------------------------------------------------------------------------
# Monotonicity -- Section 12.2, requirement 1
# ---------------------------------------------------------------------------------------------


def test_tokens_increase_with_debaters_and_rounds() -> None:
    """`t_c(4,4) > t_c(4,2) > t_c(2,2)` for every model with data.

    This is the only thing in A.5 that distinguishes a sixteen-call debate from a single call:
    there is no call count, no per-node term and no concurrency anywhere in the formulation, so
    the entire cost of `D` and `R` has to arrive through the magnitude of `t_c`.
    """
    profiles = build_code_generation_profiles()
    by_model: dict[str, dict[tuple[int, int], float]] = {}
    for key, wp in profiles.items():
        if isinstance(wp.tokens, Unavailable):
            continue
        by_model.setdefault(key.knob["model"], {})[(key.knob["D"], key.knob["R"])] = _p90(wp.tokens)

    checked = 0
    for model, points in by_model.items():
        if {(2, 2), (4, 2), (4, 4)} <= set(points):
            assert points[(4, 4)] > points[(4, 2)] > points[(2, 2)], f"{model}: {points}"
            checked += 1
    assert checked, "no model had all three (D,R) points -- the test asserted nothing"


def test_debate_growth_is_sublinear_in_call_count() -> None:
    """Section 12.2 records ~3.3x growth from (2,2) to (4,4) against a 4x growth in calls.

    That sublinearity is a profile FACT the MILP consumes silently -- it never sees the call
    count, so it cannot know the relationship is sublinear rather than linear. Asserted as a
    band rather than a point because it is read off a digitized CDF.
    """
    profiles = build_code_generation_profiles()
    ratios = []
    by_model: dict[str, dict[tuple[int, int], float]] = {}
    for key, wp in profiles.items():
        if isinstance(wp.tokens, Unavailable):
            continue
        by_model.setdefault(key.knob["model"], {})[(key.knob["D"], key.knob["R"])] = _p90(wp.tokens)
    for points in by_model.values():
        if {(2, 2), (4, 4)} <= set(points):
            ratios.append(points[(4, 4)] / points[(2, 2)])
    assert ratios, "no model had both endpoints"
    mean = sum(ratios) / len(ratios)
    assert 1.0 < mean < 4.0, f"growth {mean:.2f}x should be positive but sublinear in calls"


def test_video_tokens_increase_with_frames_where_the_figure_resolves_it() -> None:
    """More frames should not REDUCE generated tokens -- but only where Figure 2b resolves it.

    Unlike percentile monotonicity, this is an empirical claim rather than a definitional one,
    and the figure does not support it everywhere. NVLM-D-72B's F=1 band is [188, 199] and its
    F=5 band is [163, 195]: they OVERLAP, so the figure asserts no ordering between them, and
    the model is recorded as `inseparable` in `FIG_2B_STT_Y_SIDE` for exactly this reason. Its
    answer length is driven by the question, not the frame count.

    So the assertion is conditional on disjoint bands. Where the figure separates two frame
    counts, the ordering must hold; where it does not, the test asserts the bands genuinely
    overlap rather than quietly skipping. Demanding monotonicity everywhere would be asserting
    something the source does not say.
    """
    profiles = build_video_profiles()
    by_model: dict[tuple[str, str], dict[int, object]] = {}
    for key, wp in profiles.items():
        if isinstance(wp.tokens, Unavailable):
            continue
        by_model.setdefault((key.knob["model"], key.dag_variant), {})[key.knob["F"]] = wp.tokens.p90()

    resolved = unresolved = 0
    for (model, variant), points in by_model.items():
        frames = sorted(points)
        for lo_f, hi_f in zip(frames, frames[1:]):
            a, b = points[lo_f], points[hi_f]
            if a.hi <= b.lo:  # disjoint and correctly ordered
                assert a.value <= b.value, f"{model}/{variant}: F={lo_f} > F={hi_f}"
                resolved += 1
            elif b.hi <= a.lo:
                pytest.fail(
                    f"{model}/{variant}: Figure 2b separates F={lo_f} and F={hi_f} and puts "
                    f"MORE frames strictly lower ({b.hi} <= {a.lo})"
                )
            else:
                assert a.lo <= b.hi and b.lo <= a.hi, "bands must overlap to be unresolved"
                unresolved += 1

    assert resolved, "no frame-count pair was separable -- the test asserted nothing"
    assert unresolved, (
        "every frame-count pair was separable, but NVLM-D-72B is recorded as inseparable; "
        "the digitization or this expectation has changed"
    )


def test_percentiles_are_monotone_within_a_distribution(profiles) -> None:
    """A CDF read that produces p50 > p90 is a digitization error, not a finding."""
    for key, wp in profiles.items():
        if isinstance(wp.tokens, Unavailable):
            continue
        ordered = [wp.tokens.at(p).value for p in sorted(wp.tokens.percentiles)]
        assert ordered == sorted(ordered), f"{key}: non-monotone percentiles {ordered}"


# ---------------------------------------------------------------------------------------------
# Per-node decomposition -- Section 12.2 requirements 2 and 3, and A59
# ---------------------------------------------------------------------------------------------


def test_tool_nodes_contribute_exactly_zero(profiles) -> None:
    """Section 12.2, requirement 3. The zero is the FORMULATION's, not a measurement.

    A tool stage does real work and takes real wall-clock; it contributes nothing to `t_c`
    because A.5 counts completion tokens and a tool emits none. That is the mechanism behind
    Section 12.3's "three of Video Q/A's four stages are free".
    """
    for key, wp in profiles.items():
        for node in TOOL_NODES[key.workflow_id]:
            if node not in wp.node_tokens:
                continue  # `stt` is absent from the stt_off DAG variant
            dist = wp.node_tokens[node]
            assert isinstance(dist, TokenDistribution), f"{key}/{node} should be an exact zero"
            assert all(v.value == 0.0 for v in dist.percentiles.values())
            assert dist.p90().lo == 0.0 and dist.p90().hi == 0.0, "an exact zero has a zero band"


def test_video_decomposition_is_exact(profiles) -> None:
    """Section 12.2, requirement 2, in the one place it is derivable.

    Three of Video Q/A's four nodes are tools, so the remainder must sit entirely on `q_a`, and
    `sum(node p90) == total p90` EXACTLY -- no invented ratio anywhere. This is what makes the
    Section 12.1 critical-path comparison honest: the LLM term is the whole token total, and the
    tool terms are the part eq. (5) cannot see.
    """
    checked = 0
    for key, wp in profiles.items():
        if key.workflow_id != "video_qa" or isinstance(wp.tokens, Unavailable):
            continue
        nodes = wp.node_tokens
        assert isinstance(nodes["q_a"], TokenDistribution)
        total = sum(
            _p90(d) for d in nodes.values() if isinstance(d, TokenDistribution)
        )
        assert total == pytest.approx(_p90(wp.tokens)), f"{key}: {total} != {_p90(wp.tokens)}"
        checked += 1
    assert checked, "no video configuration had token data"


def test_sum_of_node_p90s_is_never_below_the_total(profiles) -> None:
    """Section 12.2, requirement 2, stated as the inequality it actually is.

    A naive per-node profile would report each node's own p90 and sum them, which is strictly
    larger than the p90 of the total whenever the nodes are not perfectly correlated. We store
    the total as primary and derive the decomposition, never the reverse. On Video Q/A the two
    coincide (one LLM node), so the inequality is tight -- and that tightness is the evidence
    that nothing has been double-counted.
    """
    for key, wp in profiles.items():
        if isinstance(wp.tokens, Unavailable):
            continue
        known = [d for d in wp.node_tokens.values() if isinstance(d, TokenDistribution)]
        if len(known) != len(wp.node_tokens):
            continue  # an Unavailable node makes the sum uncomputable, by design (A59)
        assert sum(_p90(d) for d in known) >= _p90(wp.tokens) - 1e-9, key


def test_code_generation_nodes_are_unavailable_not_guessed() -> None:
    """A59. Three LLM nodes share one published per-request total with no reported split.

    Apportioning it would be an INVENTED ratio, which Q19 forbids outside `critique/`. The
    consequence is recorded rather than papered over: the makespan comparison is not computable
    for Code Generation.
    """
    profiles = build_code_generation_profiles()
    for key, wp in profiles.items():
        for node in LLM_NODES["code_generation"]:
            assert isinstance(wp.node_tokens[node], Unavailable), f"{key}/{node} was guessed"
        assert isinstance(wp.node_tokens["execute_tests"], TokenDistribution)


def test_rank_solutions_records_the_executor_ambiguity() -> None:
    """Section 12.3, point 5, at the data level: `C_w`'s knobs do not determine whether
    `rank_solutions` is served by a TOOL or an LLM, so not even its order of magnitude is
    configuration-dependent in A.5."""
    profiles = build_code_generation_profiles()
    wp = next(iter(profiles.values()))
    reason = wp.node_tokens["rank_solutions"].reason
    assert "test_pass_rate_ranker" in reason and "do not determine which" in reason


def test_stt_off_variant_has_no_stt_node() -> None:
    profiles = build_video_profiles()
    for key, wp in profiles.items():
        if key.dag_variant == "stt_off":
            assert "stt" not in wp.node_tokens
        else:
            assert "stt" in wp.node_tokens


def test_every_configuration_is_profiled() -> None:
    """44 configurations in, 44 profiles out -- no silent drop."""
    profiles = build_workflow_profiles()
    expected = set(enumerate_code_generation()) | set(enumerate_video_qa())
    assert set(profiles) == expected
    assert len(profiles) == 44
