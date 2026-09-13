"""
The auto-scaler -- Section 3.4, p.575, and the contradiction at its centre.

Section 3.4 describes a component that "monitors per-model instance load over short windows
(seconds to minutes) and **rapidly scales out** when needed". Section 4.7 assumes "provisioning
new instances ... is assumed to take **20 minutes**". These cannot both be true of a system that
absorbs short-term variance, and the paper never reconciles them -- the only candidate is spare
capacity, which Section 3.4 names and never sizes.

These tests do not repair that. They make it produce a number.
"""

from __future__ import annotations

import pytest

from execution.autoscaler import SPARE_FRACTION, AutoScaler
from execution.monitor import FleetMonitor, LoadWindow
from execution.projection import EWMA_ALPHA, EwmaProjector, LookaheadError, under_prediction
from execution.report import ExecutionReport
from execution.registry import build_executable
from execution.runner import FIDELITY_NOTES, run_epoch
from execution.sim.clock import MONITOR_WINDOW_S, PROVISIONING_DELAY_S
from execution.sim.fleet import SimulatedFleet
from execution.thresholds import (
    SCALE_IN_RATIO,
    SCALE_OUT_RATIO,
    ScaleThresholds,
    thresholds_for,
)
from optimization.milp import Objective, no_budget, solve
from optimization.milp.sets import build_admissible, demand
from optimization.profiles.profile_sets import derived_tiers
from optimization.profiles.schema import ModelProfileKey

SLO = ("latency", "good")


@pytest.fixture(scope="module")
def plan_and_inputs():
    pset = derived_tiers()
    inputs = pset.to_milp_inputs()
    result = solve(pset, "video_qa", SLO, Objective.ENERGY, no_budget(), inputs=inputs)
    return pset, inputs, build_executable(result)


def _spike_profile(base: float, n: int = 600, lo: int = 200, hi: int = 400, mult: float = 2.5):
    """A spike SHORTER than the provisioning delay -- which is the case that matters.

    Figure 19's traces vary on far shorter timescales than 20 minutes, so a sub-20-minute spike
    is not a contrived worst case; it is the normal case for the component under test.
    """
    rate = [base] * n
    for t in range(lo, hi):
        rate[t] = base * mult
    return rate


# ---------------------------------------------------------------------------------------------
# A87 -- the 20-minute wall
# ---------------------------------------------------------------------------------------------


def test_provisioning_delay_makes_the_autoscaler_unable_to_absorb_a_spike(plan_and_inputs) -> None:
    """THE A87 MEASUREMENT.

    Same load, same plan, same thresholds -- only the provisioning delay changes. With the
    paper's own 20 minutes, capacity ordered during a 200-second spike arrives long after the
    spike has passed, so the auto-scaler cannot do the job Section 3.4 assigns it.
    """
    pset, inputs, plan = plan_and_inputs
    tau = float(inputs.tau[("video_qa", *SLO[1:])].value) if False else float(
        inputs.tau[("video_qa", SLO[0], SLO[1])].value
    )
    lam, _ = demand(inputs, "video_qa", SLO, 0)
    rate = _spike_profile(lam.value)

    slow, slow_out = run_epoch(
        pset, plan, rate, tau_s=tau, duration_s=600.0, seed=7,
        provisioning_delay_s=PROVISIONING_DELAY_S,
    )
    fast, fast_out = run_epoch(
        pset, plan, rate, tau_s=tau, duration_s=600.0, seed=7, provisioning_delay_s=0.0,
    )

    slow_rate = slow.violated / max(1, slow.completed + slow.violated)
    fast_rate = fast.violated / max(1, fast.completed + fast.violated)
    assert slow_rate > fast_rate, (
        "the 20-minute provisioning delay should make outcomes strictly worse; if it does not, "
        "the simulation is not exercising the auto-scaler at all"
    )
    assert slow_rate > 0.5, (
        f"violation rate under the paper's own provisioning assumption was {slow_rate:.1%}"
    )


def test_late_capacity_is_paid_for_and_arrives_too_late(plan_and_inputs) -> None:
    """The auto-scaler's response to a short spike is worse than useless: it buys GPU-seconds
    that arrive after the spike is over. A69's churn cost, arriving through A87's door."""
    pset, inputs, plan = plan_and_inputs
    tau = float(inputs.tau[("video_qa", SLO[0], SLO[1])].value)
    lam, _ = demand(inputs, "video_qa", SLO, 0)
    out, _ = run_epoch(
        pset, plan, _spike_profile(lam.value), tau_s=tau, duration_s=600.0, seed=7,
        provisioning_delay_s=PROVISIONING_DELAY_S,
    )
    assert out.scale_events["scale_out_events"] > 0, "the scaler never reacted"
    assert out.wasted_gpu_seconds > 0, (
        "capacity provisioned during a spike shorter than the delay must show as wasted "
        "GPU-seconds; zero means pending instances are not being billed"
    )


def test_instant_provisioning_is_not_the_papers_assumption() -> None:
    """Section 4.7 states 20 minutes. Any run with the delay off is self-labelling."""
    assert PROVISIONING_DELAY_S == 1200.0


# ---------------------------------------------------------------------------------------------
# Queueing is the dominant failure mode, and eq. (5) cannot see it
# ---------------------------------------------------------------------------------------------


def test_most_violations_come_from_latency_the_planner_cannot_model(plan_and_inputs) -> None:
    """eq. (5) admits a pair on `l^TTFT + t_c * l^TPOT <= tau` with NO queueing term.

    So a plan can be feasible on paper and violate its SLO in the run purely through waiting.
    This asserts that the queueing-attributable violations dominate the ones attributable to
    token variance -- i.e. the blind spot matters more than the p90 collapse.
    """
    pset, inputs, plan = plan_and_inputs
    tau = float(inputs.tau[("video_qa", SLO[0], SLO[1])].value)
    lam, _ = demand(inputs, "video_qa", SLO, 0)
    out, outcomes = run_epoch(
        pset, plan, _spike_profile(lam.value), tau_s=tau, duration_s=600.0, seed=7,
    )
    report = ExecutionReport(
        pset.name, "video_qa", "latency-good", "weighted_random",
        PROVISIONING_DELAY_S, 0.0, tau, [out], outcomes, FIDELITY_NOTES,
    )
    assert report.violations_from_queueing > report.violations_from_token_variance
    assert report.planner_blind_latency_s > 0.0


# ---------------------------------------------------------------------------------------------
# Thresholds come from the profile curve (the one specified mechanism)
# ---------------------------------------------------------------------------------------------


def test_thresholds_are_derived_from_the_profile_curve(plan_and_inputs) -> None:
    """Section 3.4: "We set thresholds for auto-scaling based on the performance-throughput
    characteristic in executor profiles." That characteristic is `ModelProfile.curve`."""
    pset, inputs, _plan = plan_and_inputs
    tau = float(inputs.tau[("video_qa", SLO[0], SLO[1])].value)
    adm = build_admissible(inputs, "video_qa", SLO)
    c, m = adm.pairs[0]
    t = thresholds_for(pset.models[m], tau, float(adm.t_c[c].value))
    assert t.theta_slo_tokens_s > 0
    assert not t.is_fallback
    assert "eq.(5)" in t.derived_from


def test_an_accuracy_tier_has_no_latency_ceiling(plan_and_inputs) -> None:
    """A68: `tau_{w,s}` is one number, so on an accuracy tier the latency filter is inactive and
    the throughput envelope is simply the curve maximum. Said explicitly rather than implied."""
    pset, _inputs, _plan = plan_and_inputs
    m = ModelProfileKey("Gemma-3-27B", "H100", 4)
    t = thresholds_for(pset.models[m], None, 500.0)
    assert not t.is_fallback
    assert "A68" in t.derived_from


def test_models_without_ttft_fall_back_and_are_marked(plan_and_inputs) -> None:
    """A86. The threshold rule needs TTFT at each load point; 7 profiles have none -- including
    Llava-OneVision-7B, the model Section 3.4's own auto-scaler example uses. Marked, never
    imputed."""
    pset, _i, _p = plan_and_inputs
    m = ModelProfileKey("Llava-OneVision-7B", "H100", 4)
    t = thresholds_for(pset.models[m], tau_s=0.5, tokens_per_request=1050.0)
    assert t.is_fallback
    assert "A86" in t.derived_from


def test_threshold_ratios_are_invented_and_named() -> None:
    """Q35: Section 3.4 gives no numbers, so these are ours and must be swept, never quoted
    bare. The scale-in band is far below scale-out on purpose -- with a 20-minute delay,
    releasing an instance you need again is expensive."""
    assert SCALE_OUT_RATIO == 0.80
    assert SCALE_IN_RATIO == 0.40
    assert SCALE_IN_RATIO < SCALE_OUT_RATIO / 1.5


# ---------------------------------------------------------------------------------------------
# Spare capacity, hysteresis, budget
# ---------------------------------------------------------------------------------------------


def test_spare_capacity_defaults_to_zero(plan_and_inputs) -> None:
    """A88/Q36. Section 3.4 says spare resources are maintained and never says how many. Zero is
    the formulation's own answer; a non-zero default would quietly repair A87."""
    assert SPARE_FRACTION == 0.0


def test_hysteresis_prevents_a_churn_storm() -> None:
    """Load oscillating around the threshold must not produce a scale event every control tick.

    With a 20-minute delay each spurious scale-out burns 20 minutes of GPU-seconds for nothing.
    """
    m = ModelProfileKey("Phi-4", "H100", 1)
    thresholds = {m: ScaleThresholds(str(m), 100.0, 80.0, 40.0, "test")}
    scaler = AutoScaler(thresholds=thresholds)
    fleet = SimulatedFleet(gpus_of={m: 1})
    fleet.active[m] = 1
    monitor = FleetMonitor()
    for tick in range(20):
        tokens = 90.0 * MONITOR_WINDOW_S if tick % 2 == 0 else 10.0 * MONITOR_WINDOW_S
        monitor.windows.setdefault(m, LoadWindow()).samples.clear()
        monitor.record(m, tick * 10.0, tokens)
        scaler.control(tick * 10.0, monitor, fleet)
    assert len(scaler.events) <= 4, f"{len(scaler.events)} scale events from an oscillation"


def test_budget_refusal_is_recorded_not_hidden() -> None:
    """A89. Section 3.4 says the auto-scaler "prioritizes avoiding SLO violations", but eq. (7)
    is a hard budget. The budget wins and the refusal is counted."""
    m = ModelProfileKey("Phi-4", "H100", 1)
    fleet = SimulatedFleet(gpus_of={m: 1}, budget={"H100": 2.0})
    granted = fleet.scale_out(m, 10, now_s=0.0)
    assert granted == 2
    assert fleet.budget_blocked_events == 1


# ---------------------------------------------------------------------------------------------
# Projection -- the one runtime number the paper supplies
# ---------------------------------------------------------------------------------------------


def test_projector_uses_the_papers_own_alpha() -> None:
    """Section 4.7: "an exponentially weighted moving average (EWMA) [18], with alpha = 0.5".
    Paper-sourced, unlike mu_m (A42) or the scaling ratios (Q35)."""
    assert EWMA_ALPHA == 0.5


def test_projection_cannot_see_the_epoch_it_predicts() -> None:
    """Replay is not prediction. Feeding the true next-epoch value would reproduce the paper's
    setup while inventing an oracle it never claims."""
    p = EwmaProjector()
    with pytest.raises(LookaheadError):
        p.project("video_qa", [(0, 10.0), (1, 20.0), (2, 30.0)], target_epoch=2)
    assert p.project("video_qa", [(0, 10.0), (1, 20.0)], target_epoch=2) == pytest.approx(15.0)


def test_under_prediction_is_reported_not_fed_back() -> None:
    """Figure 13b's quantity. Positive means the forecast missed low, which is the direction
    that drops requests."""
    assert under_prediction(80.0, 100.0) == pytest.approx(0.2)
    assert under_prediction(120.0, 100.0) < 0


def test_no_bare_alpha_identifier_exists_in_execution() -> None:
    """A90. A.5's `alpha` is 1.15 (demand buffer); Section 4.7's is 0.5 (EWMA). The auto-scaler
    needs both, so a single shadowed name would silently corrupt one of them."""
    import ast
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent / "execution"
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == "alpha":
                pytest.fail(f"{path.name}: bare `alpha` is ambiguous (A90)")
            if isinstance(node, ast.arg) and node.arg == "alpha":
                pytest.fail(f"{path.name}: bare `alpha` argument is ambiguous (A90)")
