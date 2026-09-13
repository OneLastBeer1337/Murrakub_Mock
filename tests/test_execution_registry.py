"""
The Workflow Registry and the request boundary -- Section 3.3.1 (p.574) and Section 3.4 (p.574).

Two paper sentences do most of the work here:

    "Once an executable workflow is generated for all valid SLO tiers of an onboarded workflow,
    it is added to the Murakkab workflow registry and is ready to serve requests."

    "The deployment plan does not prescribe per-request dispatch, which remains a runtime
    responsibility."

The first fixes the registry's key at `(workflow, SLO tier)` and makes "valid" load-bearing: a
tier the optimizer could not solve has no entry. Under `baseline` that is A37 becoming
user-visible, and serving the nearest feasible tier instead would hide the finding at exactly the
moment it starts mattering to someone.
"""

from __future__ import annotations

import pytest

from execution.registry import (
    ExecutableWorkflow,
    TierNotServable,
    WorkflowRegistry,
    build_executable,
)
from execution.requests import (
    Outcome,
    Request,
    SloKeyError,
    SloSpec,
    parse_slo,
)
from optimization.milp import Objective, no_budget, solve
from optimization.profiles.profile_sets import baseline
from optimization.profiles.schema import SloMix


@pytest.fixture(scope="module")
def registry():
    results = []
    for slo_type in ("accuracy", "latency"):
        for tier in ("best", "good", "fair", "basic"):
            pset = baseline(SloMix.section_4_2(slo_type, tier))
            results.append(
                solve(pset, "video_qa", (slo_type, tier), Objective.ENERGY, no_budget())
            )
    return WorkflowRegistry().install_all(results)


# ---------------------------------------------------------------------------------------------
# "for all VALID SLO tiers"
# ---------------------------------------------------------------------------------------------


def test_infeasible_tiers_are_absent_not_loosened(registry) -> None:
    """A37 becoming user-visible.

    Under `baseline` the latency thresholds are Figure 7b's printed labels, which eq. (5) cannot
    reach. Those tiers get NO registry entry. Silently serving the next tier down would be the
    runtime equivalent of loosening `tau`, which M4 forbids in the same words.
    """
    served = {(k[1], k[2]) for k in registry.tiers_for("video_qa")}
    assert ("latency", "best") not in served
    assert ("accuracy", "best") in served
    assert registry.coverage("video_qa")["unservable_tiers"] >= 1


def test_an_unservable_tier_says_why(registry) -> None:
    """A registry that reports absence without a reason turns a finding into a 404."""
    with pytest.raises(TierNotServable) as exc:
        registry.lookup("video_qa", SloSpec("latency", "best"))
    assert "video_qa" in str(exc.value)


def test_an_unknown_workflow_is_distinguishable_from_an_unservable_tier(registry) -> None:
    with pytest.raises(TierNotServable, match="not onboarded"):
        registry.lookup("math_qa", SloSpec("accuracy", "good"))


def test_the_registry_is_keyed_per_tier_not_per_workflow(registry) -> None:
    """Onboarding a workflow creates one entry per valid tier, not one entry."""
    assert len(registry.tiers_for("video_qa")) > 1


# ---------------------------------------------------------------------------------------------
# A plan cannot be registered without its provenance
# ---------------------------------------------------------------------------------------------


def test_an_executable_workflow_carries_its_caveats(registry) -> None:
    """Q19 requires the data-excluded set beside every number. A registry entry is where a
    number stops being a research artifact and starts serving users, so it travels with it."""
    plan = registry.lookup("video_qa", SloSpec("accuracy", "good"))
    assert plan.caveats
    joined = " ".join(plan.caveats)
    assert plan.profile_set_name in joined
    assert "excluded" in joined


def test_a_plan_without_caveats_cannot_be_constructed() -> None:
    with pytest.raises(ValueError, match="provenance"):
        ExecutableWorkflow(
            workflow_id="video_qa",
            slo=SloSpec("accuracy", "good"),
            routing={("c", "m"): 1.0},
            instances={},
            tau_s=None,
            profile_set_name="baseline",
            epoch=0,
            objective="eq.(11)",
            caveats=(),
        )


def test_a_non_optimal_solve_is_not_a_plan() -> None:
    """An infeasible solve is a RESULT worth reporting (M4 Section 7.3) but not a deployment
    plan; registering one would serve requests against an answer the solver never vouched for."""
    pset = baseline(SloMix.section_4_2("latency", "best"))
    result = solve(pset, "video_qa", ("latency", "best"), Objective.ENERGY, no_budget())
    with pytest.raises(TierNotServable):
        build_executable(result)


# ---------------------------------------------------------------------------------------------
# Routing fractions (A70) survive into the registry
# ---------------------------------------------------------------------------------------------


def test_the_plan_carries_fractions_not_a_single_choice(registry) -> None:
    """A.5 declares `x` continuous, so a plan may spread one stream across several pairs. The
    registry stores the distribution; turning it into per-request choices is dispatch's job,
    which is exactly what Section 3.3.1 assigns to the runtime."""
    plan = registry.lookup("video_qa", SloSpec("accuracy", "good"))
    assert plan.routing
    normalised = plan.normalised_routing()
    assert sum(normalised.values()) == pytest.approx(1.0)


def test_normalisation_is_needed_because_alpha_lets_the_raw_sum_exceed_demand(registry) -> None:
    """eq. (1) permits `sum x` up to `alpha * lambda^peak`, so raw routing values are rates, not
    fractions. Reading them as fractions without normalising would over-dispatch by up to 15%."""
    plan = registry.lookup("video_qa", SloSpec("accuracy", "good"))
    raw_total = sum(plan.routing.values())
    assert raw_total > 1.0


# ---------------------------------------------------------------------------------------------
# A82 -- the SLO key is not a product
# ---------------------------------------------------------------------------------------------


def test_a_conjoined_slo_is_rejected_with_its_reason() -> None:
    """Section 3.4 says a request may specify "a quality, latency and cost" SLO, which reads as a
    conjunction. But the optimizer solves per `(workflow, SLO)` with ONE `tau` (A68) and every
    run in Sections 4.2/4.3 assigns exactly one type. No plan exists for a conjoined key, so
    serving one would mean inventing a deployment nobody solved."""
    with pytest.raises(SloKeyError, match="A82"):
        parse_slo({"accuracy": "good", "latency": "good"})


def test_a_single_slo_is_accepted_in_several_spellings() -> None:
    assert parse_slo({"quality": "good"}).slo_type == "accuracy"
    assert parse_slo(("latency", "basic")).tier == "basic"
    assert parse_slo(SloSpec("accuracy", "best")).key == ("accuracy", "best")


def test_a_cost_slo_is_rejected_citing_the_undefined_threshold() -> None:
    """A67: `Cost_budget` depends on `tau_{w,cost}`, a cost tier Section 3.4 never defines and no
    table reports."""
    with pytest.raises(SloKeyError, match="A67"):
        SloSpec("cost", "good")


def test_an_unknown_tier_is_rejected() -> None:
    with pytest.raises(SloKeyError):
        SloSpec("accuracy", "platinum")


# ---------------------------------------------------------------------------------------------
# Request shapes
# ---------------------------------------------------------------------------------------------


def test_both_request_shapes_are_representable() -> None:
    """Section 3.4 defines two: a named workflow, and a natural-language query with none."""
    named = Request(1, 0.0, SloSpec("accuracy", "good"), workflow_id="video_qa")
    dynamic = Request(2, 0.0, SloSpec("accuracy", "good"), query="what happens in this clip?")
    assert not named.is_dynamic
    assert dynamic.is_dynamic


def test_outcomes_distinguish_violation_from_drop() -> None:
    """Section 9's rule: a violated request still COMPLETED. Collapsing the two would let an
    unbounded queue masquerade as zero violations."""
    assert Outcome.SLO_VIOLATED.served
    assert Outcome.COMPLETED.served
    assert not Outcome.DROPPED.served
    assert not Outcome.REJECTED.served
