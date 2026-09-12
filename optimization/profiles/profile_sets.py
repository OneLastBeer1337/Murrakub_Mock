"""
Named, swappable `ProfileSet`s -- and the reason the whole package is built around them.

THE THREAT THIS ANSWERS. With no GPUs, every number Milestone 4 produces is a function of profiles
we reconstructed. "Murakkab provisions X% more GPUs than my system" is then a claim about our
reconstruction unless it survives a different plausible profile set. So a profile set is a VALUE,
`/optimization/milp/` may not import a concrete profile module, and no result may be reported
without the name of the set that produced it (`MilpResult.profile_set_name`).

THE SETS:

  `paper_only`   every value weaker than DERIVED becomes Unavailable. The floor: whatever
                 survives here is not an artifact of our reconstruction. Small and full of holes,
                 which is the point.
  `baseline`     the set Sections 5-8 of DESIGN.md describe. The headline set.
  `pessimistic`  every `Measured` replaced by the band end that WORSENS Murakkab's objective.
  `optimistic`   the same in the improving direction. Deterministic corner cases.
  `derived_tiers` `baseline` but `tau` computed from our own population instead of the printed
                 Figure 7/8 labels. Isolates A37 -- see below.

TWO SETS DESIGN.md SECTION 9.2 LISTS DO NOT EXIST, DELIBERATELY (A64):

  `maxthroughput` would be `baseline` with `OperatingPointPolicy.MAX_THROUGHPUT`, and it is the
                 largest single lever in the set (~6.8x on `theta_m` for
                 Llava-OneVision-7B/H100/TP=4, from Table 5's own rows). It is NOT a set, because
                 A37b decided the operating-point collapse is a policy applied AT the boundary
                 rather than baked into a profile. The substance is fully available as
                 `to_milp_inputs(operating_point=OperatingPointPolicy.MAX_THROUGHPUT)`, and
                 `MilpInputs.operating_point_policy` records which was used. Making it a set too
                 would give one knob two homes.
  `wide`         has two incompatible definitions in the repo and is implemented under neither.
                 Section 9.2 says "baseline + the 14 extrapolated `t_c` values of Section 5.4
                 with +/-8x bands" -- but Q19 SUPERSEDED Section 5.4: those 14 are `Unavailable`
                 precisely so nothing is extrapolated. This docstring previously claimed instead
                 that it enabled the aliased DeepSeek-Llama-70B profile (Q13/A34), a different
                 thing; the `ASSUMED_ALIAS` provenance level exists for it and is currently
                 unused. Needs Arno's decision -- see PROGRESS.md A64.

`tau` AND THE Q14 DECISION. `baseline` takes the latency thresholds from the PRINTED Figure 7b/8b
labels even though they are unreachable under the paper's own eq. (5) (A37): Table 5's `Best` row
is Llava-OneVision-7B at TPOT 0.0044 s, and `0.2 + 400*0.0044 ~= 2.0 s` against a printed
`<= 0.5 s`. Reproduce-literally keeps the printed labels; `derived_tiers` carries the
self-consistent alternative. M4 is therefore EXPECTED to find the latency-SLO runs infeasible for
the paper's own chosen configuration, and must not resolve that by loosening `tau`.

Accuracy tiers are DERIVED in every set, because there the derivation reproduces the printed
labels to within the digitization band on both workflows (Section 7.3), so there is nothing to
choose between.
"""

from __future__ import annotations

import random
from typing import Callable, Final, Mapping

from optimization.profiles.arrivals import build_arrivals
from optimization.profiles.model_profiles import build_model_profiles
from optimization.profiles.provenance import (
    Anchor,
    Citation,
    Measured,
    Provenance,
    Unavailable,
    Value,
)
from optimization.profiles.schema import (
    SLO_TIERS,
    ConfigKey,
    LoadPoint,
    ModelProfile,
    ProfileSet,
    ResourceType,
    SloMix,
    WorkflowProfile,
)
from optimization.profiles.slo_tiers import (
    accuracy_population,
    derive_accuracy_tiers,
    derive_latency_tiers,
    reconstruct,
)
from optimization.profiles.sources import external
from optimization.profiles.sources.figure_labels import TIER_LABELS
from optimization.profiles.sources.tables import ALPHA, TABLE_3
from optimization.profiles.workflow_profiles import build_workflow_profiles

A5 = Citation(
    version="BOTH",
    section="A.5",
    page=586,
    quote="alpha: Unified buffer factor (default 1.15)",
)
SEC_4_5 = Citation(version="BOTH", section="4.5", page=578)
FIG_7_8 = Citation(version="BOTH", figure="7b", page=575)

WORKFLOWS: Final[tuple[str, ...]] = ("code_generation", "video_qa")


def _alpha() -> Value:
    return Measured(
        value=ALPHA,
        unit="dimensionless",
        provenance=Provenance.PAPER_TEXT,
        cite=A5,
        note="eq. (1)/(2) demand-satisfaction buffer. Identical in both versions.",
    )


def _resources() -> dict[str, ResourceType]:
    """`c_g` from the vendor price list (Q18); `B_g` deliberately Unavailable.

    A43: Sections 4.2 and 4.3 state NO budget, so constraint (7) is inactive there and no budget
    is invented. Section 4.5's sweep (2,000 A100 plus 0-500 H100) exists only for that section's
    experiment and is supplied explicitly by the caller when reproducing it.
    """
    out: dict[str, ResourceType] = {}
    for gpu in ("A100", "H100"):
        out[gpu] = ResourceType(
            name=gpu,
            cost_per_instance_second=external.cost_per_gpu_second(gpu),
            budget=Unavailable(
                reason=(
                    "Sections 4.2 and 4.3 state no resource budget, so eq. (7) is inactive for "
                    "the headline experiments. Section 4.5 (p.578) sweeps 2,000 A100 with 0-500 "
                    "H100, but that budget belongs to that experiment and is not a profile (A43)"
                ),
                cite=SEC_4_5,
                blocks=("eq7",),
            ),
        )
    return out



def _latency_population(
    workflow_profiles: Mapping[ConfigKey, WorkflowProfile],
    models: Mapping,
    workflow: str,
) -> list[tuple[float, str, Measured]]:
    """eq. (5) evaluated over COHERENT `(c, m)` pairs -- the latency this formulation can deliver.

    Section 3.4 derives a tier from "the ... values of accuracy and latency available among the
    set of all workflow, model, and hardware configurations". For latency that quantity is
    eq. (5), `l^TTFT_m + t_c * l^TPOT_m`.

    Restricted to pairs whose configuration names the model (`coherent`), mirroring how the
    accuracy population is grouped by the model a configuration was measured on. Including
    incoherent pairs would define a tier off latencies no sensible deployment would produce --
    A51 is a defect to MEASURE in M4, not a basis for setting thresholds in M3.
    """
    out: list[tuple[float, str, Measured]] = []
    for key, profile in workflow_profiles.items():
        if key.workflow_id != workflow:
            # PER-WORKFLOW, like the accuracy population. Pooling both workflows gives them the
            # SAME latency tiers, which is wrong on its face -- Video Q/A answers a question
            # about a video in seconds while a Code Generation debate runs for tens of seconds,
            # and Figures 7b and 8b print visibly different ladders (0.5-5.8 s vs 11.3-78.2 s).
            # Pooling made `derived_tiers` assign 2.938 s to both, which is simultaneously too
            # loose for one workflow and impossible for the other.
            continue
        if isinstance(profile.tokens, Unavailable):
            continue
        tokens = float(profile.tokens.p90().value)
        for mk, mp in models.items():
            if mk.model_id != key.knob.get("model"):
                continue
            ttft, tpot = mp.ttft(), mp.tpot()
            if isinstance(ttft, Unavailable) or isinstance(tpot, Unavailable):
                continue
            # The anchor is the model's own TPOT -- a real profiled value that entered the
            # arithmetic -- so the derived tier can never claim provenance stronger than the
            # weakest measurement behind it.
            out.append((float(ttft.value) + tokens * float(tpot.value), f"{key} on {mk}", tpot))
    if not out:
        raise ValueError("no coherent (c, m) pair has a complete eq. (5) input")
    return out


def _accuracy_tiers(workflow_profiles: Mapping[ConfigKey, WorkflowProfile]) -> dict[str, dict[str, float]]:
    by_workflow: dict[str, dict[str, list[float]]] = {}
    for key, profile in workflow_profiles.items():
        if isinstance(profile.accuracy, Unavailable):
            continue
        by_workflow.setdefault(key.workflow_id, {}).setdefault(
            profile.accuracy_measured_on_model, []
        ).append(profile.accuracy.value)
    return {w: derive_accuracy_tiers(accuracy_population(m)) for w, m in by_workflow.items()}


def _slo_thresholds(
    workflow_profiles: Mapping[ConfigKey, WorkflowProfile],
    use_printed_latency: bool,
    models: Mapping | None = None,
) -> tuple[dict[tuple[str, str, str], Value], dict[str, object]]:
    derived = _accuracy_tiers(workflow_profiles)
    out: dict[tuple[str, str, str], Value] = {}
    report: dict[str, object] = {}

    for workflow in WORKFLOWS:
        tiers = derived.get(workflow, {})
        for tier in SLO_TIERS:
            if tier in tiers:
                # The `lower` convention guarantees the tier IS a member of the population, so
                # the anchor is not an approximation -- it is the exact configuration whose
                # measured accuracy became this threshold. That is only possible because we did
                # not interpolate (Section 7.1).
                source = next(
                    (
                        (key, profile.accuracy)
                        for key, profile in workflow_profiles.items()
                        if key.workflow_id == workflow
                        and isinstance(profile.accuracy, Measured)
                        and profile.accuracy.value == tiers[tier]
                    ),
                    None,
                )
                if source is None:  # pragma: no cover - guarded by test_slo_tiers
                    raise AssertionError(
                        f"{workflow}/{tier}: derived tier {tiers[tier]} is not a member of its "
                        "own population; the `lower` percentile convention was violated"
                    )
                anchor_key, anchor_value = source
                out[(workflow, "accuracy", tier)] = Measured(
                    value=tiers[tier],
                    unit="percent",
                    provenance=Provenance.DERIVED,
                    cite=Citation(version="BOTH", section="3.4", page=575),
                    lo=tiers[tier] - 0.5,
                    hi=tiers[tier] + 0.5,
                    anchors=(
                        Anchor(profile_key=str(anchor_key), field="a_c", value=anchor_value),
                    ),
                    assumption=(
                        "Section 3.4's rule applied to this set's own accuracy population with "
                        "the `lower` percentile convention; reproduces the printed Figure 7a/8a "
                        "labels to within the digitization band (Section 7.3)"
                    ),
                )
            printed = TIER_LABELS[(workflow, "latency")][tier]
            if use_printed_latency:
                out[(workflow, "latency", tier)] = Measured(
                    value=printed,
                    unit="s",
                    provenance=Provenance.PAPER_FIGURE_LABEL,
                    cite=FIG_7_8,
                    note=(
                        "printed tier label; UNREACHABLE under the paper's own eq. (5) for its "
                        "own chosen configuration (A37). Kept per Q14; `derived_tiers` carries "
                        "the self-consistent alternative"
                    ),
                )
            else:
                # A73: this branch did not exist until M4 tried to use it. `use_printed_latency`
                # was read and then ignored -- the printed label was written unconditionally --
                # so `derived_tiers` was a byte-for-byte copy of `baseline`, and Section 7.4's
                # control against OUR OWN bugs did not exist. Found because M4's A37 test
                # expected `derived_tiers` to be feasible at the `best` latency tier and it was
                # not.
                population = _latency_population(workflow_profiles, models, workflow)
                derived_latency = derive_latency_tiers(v for v, _n, _a in population)
                value = derived_latency[tier]
                anchor_name, anchor_value = min(population, key=lambda p: p[0])[1:]
                out[(workflow, "latency", tier)] = Measured(
                    value=value,
                    unit="s",
                    provenance=Provenance.DERIVED,
                    cite=Citation(version="BOTH", section="3.4", page=575),
                    lo=value * 0.97,
                    hi=value * 1.03,
                    anchors=(
                        Anchor(
                            profile_key=anchor_name,
                            field="l_tpot_m",
                            value=anchor_value,
                        ),
                    ),
                    assumption=(
                        "Section 3.4's tier rule applied to this set's own eq. (5) population "
                        "-- the latency the formulation can actually deliver -- instead of the "
                        "printed Figure 7b/8b label, which A37 shows is unreachable. Self-"
                        "consistent by construction; NOT the paper's number"
                    ),
                    note=f"printed label for comparison: {printed} s",
                )

        if workflow in derived:
            populations = {}
            for key, profile in workflow_profiles.items():
                if key.workflow_id == workflow and isinstance(profile.accuracy, Measured):
                    populations.setdefault(profile.accuracy_measured_on_model, []).append(
                        profile.accuracy.value
                    )
            report[workflow] = reconstruct(
                workflow, "accuracy", accuracy_population(populations)
            )

    if not use_printed_latency:
        report["latency_note"] = (
            "this set derives latency tiers from its own population; see `derived_tiers`"
        )
    return out, report


# ---------------------------------------------------------------------------------------------
# Set construction
# ---------------------------------------------------------------------------------------------


def _filter_paper_only(value: Value) -> Value:
    if isinstance(value, Measured) and value.provenance < Provenance.DERIVED:
        return Unavailable(
            reason=(
                f"provenance {value.provenance.name} is weaker than DERIVED, and `paper_only` "
                "admits only what the paper itself supports"
            ),
            cite=value.cite,
        )
    return value


def _map_values(profile_set: ProfileSet, fn: Callable[[Value], Value], name: str) -> ProfileSet:
    """Apply `fn` to every `Measured` in the set, preserving structure."""
    workflow = {}
    for key, wp in profile_set.workflow.items():
        tokens = wp.tokens
        if not isinstance(tokens, Unavailable):
            tokens = type(tokens)(
                percentiles={p: fn(v) for p, v in tokens.percentiles.items()},
                mean=tokens.mean,
            )
        workflow[key] = WorkflowProfile(
            key=wp.key,
            accuracy=fn(wp.accuracy),
            accuracy_benchmark=wp.accuracy_benchmark,
            accuracy_measured_on_model=wp.accuracy_measured_on_model,
            tokens=tokens,
            node_tokens=wp.node_tokens,
            node_service_time=wp.node_service_time,
            prompt_tokens=wp.prompt_tokens,
        )

    models = {}
    for key, mp in profile_set.models.items():
        curve = tuple(
            LoadPoint(
                throughput=fn(p.throughput),
                ttft_p90=fn(p.ttft_p90),
                tpot_p90=fn(p.tpot_p90),
                origin=p.origin,
            )
            for p in mp.curve
        )
        models[key] = ModelProfile(
            key=mp.key,
            curve=curve,
            parallelism=mp.parallelism,
            energy=fn(mp.energy),
            tps_per_wh=mp.tps_per_wh,
            collapsed_rows=mp.collapsed_rows,
        )

    resources = {
        n: ResourceType(name=r.name, cost_per_instance_second=fn(r.cost_per_instance_second), budget=r.budget)
        for n, r in profile_set.resources.items()
    }
    return ProfileSet(
        name=name,
        workflow=workflow,
        models=models,
        resources=resources,
        slo=profile_set.slo,
        arrivals=profile_set.arrivals,
        alpha=profile_set.alpha,
        tier_reconstruction=profile_set.tier_reconstruction,
        operating_point_collapse=profile_set.operating_point_collapse,
    )


def _band_end(pick_low: bool) -> Callable[[Value], Value]:
    def fn(value: Value) -> Value:
        if isinstance(value, Unavailable) or value.lo is None:
            return value
        chosen = value.lo if pick_low else value.hi
        return Measured(
            value=chosen,
            unit=value.unit,
            provenance=value.provenance,
            cite=value.cite,
            lo=value.lo,
            hi=value.hi,
            anchors=value.anchors,
            assumption=value.assumption,
            note=f"{value.note} [band {'low' if pick_low else 'high'} end]".strip(),
        )

    return fn


def _build(name: str, mix: SloMix | None = None) -> ProfileSet:
    workflow = build_workflow_profiles()
    models = build_model_profiles()
    slo, report = _slo_thresholds(workflow, use_printed_latency=True)
    collapse = tuple(
        f"{key}: {line}" for key, mp in models.items() for line in mp.collapsed_rows
    )
    return ProfileSet(
        name=name,
        workflow=workflow,
        models=models,
        resources=_resources(),
        slo=slo,
        arrivals=build_arrivals(mix),
        alpha=_alpha(),
        tier_reconstruction=report,
        operating_point_collapse=collapse,
    )


def baseline(mix: SloMix | None = None) -> ProfileSet:
    return _build("baseline", mix)


def paper_only() -> ProfileSet:
    return _map_values(_build("paper_only"), _filter_paper_only, "paper_only")


def pessimistic() -> ProfileSet:
    return _map_values(_build("pessimistic"), _band_end(pick_low=False), "pessimistic")


def optimistic() -> ProfileSet:
    return _map_values(_build("optimistic"), _band_end(pick_low=True), "optimistic")


def derived_tiers() -> ProfileSet:
    base = _build("derived_tiers")
    slo, report = _slo_thresholds(base.workflow, use_printed_latency=False, models=base.models)
    return ProfileSet(
        name="derived_tiers",
        workflow=base.workflow,
        models=base.models,
        resources=base.resources,
        slo=slo,
        arrivals=base.arrivals,
        alpha=base.alpha,
        tier_reconstruction=report,
        operating_point_collapse=base.operating_point_collapse,
    )


def resample(profile_set: ProfileSet, rng: random.Random, name: str | None = None) -> ProfileSet:
    """Draw every banded value uniformly from its own band -- one Monte-Carlo trial.

    PAPER_TABLE and PAPER_TEXT values have zero band and therefore never move: an exact printed
    number is not a source of uncertainty, and letting it wobble would manufacture doubt where
    the paper is unambiguous.
    """

    def fn(value: Value) -> Value:
        if isinstance(value, Unavailable) or value.lo is None or value.lo == value.hi:
            return value
        drawn = rng.uniform(value.lo, value.hi)
        return Measured(
            value=drawn,
            unit=value.unit,
            provenance=value.provenance,
            cite=value.cite,
            lo=value.lo,
            hi=value.hi,
            anchors=value.anchors,
            assumption=value.assumption,
            note=f"{value.note} [resampled]".strip(),
        )

    return _map_values(profile_set, fn, name or f"{profile_set.name}+resample")


NAMED_SETS: Final[Mapping[str, Callable[[], ProfileSet]]] = {
    "baseline": baseline,
    "paper_only": paper_only,
    "pessimistic": pessimistic,
    "optimistic": optimistic,
    "derived_tiers": derived_tiers,
}


def budget_scenarios() -> Mapping[str, dict[str, Value]]:
    """`B_g` scenarios for eq. (7), taken from Table 3's sweep (Section 4.5, p.578).

    NOT part of any profile set, and that separation is the point (A43). A.5 treats `B_g` as a
    fixed parameter of the problem; the paper's own evaluation SWEEPS it across six settings and
    reports how the allocation, energy and cost move. So a budget is an experiment coordinate,
    not a profile fact, and folding one into `ProfileSet` would bake a single arbitrary point of
    that sweep into every result.

    Sections 4.2 and 4.3 -- which produce the headline numbers -- state no budget at all, so the
    faithful reproduction of those runs has eq. (7) INACTIVE. `no_budget` is that case, and it is
    named rather than implied so M4 has to choose it deliberately.

    Keys are `"a2000_h0"` .. `"a2000_h500"`, matching Table 3's rows in order.
    """
    cite = Citation(version="BOTH", table=3, page=578)
    out: dict[str, dict[str, Value]] = {
        "no_budget": {
            g: Unavailable(
                reason=(
                    "Sections 4.2 and 4.3 state no resource budget, so eq. (7) is inactive for "
                    "the headline experiments (A43). Selecting this scenario asserts that "
                    "absence deliberately rather than defaulting to it"
                ),
                cite=Citation(version="OSDI", section="4.2", page=576),
                blocks=("eq7",),
            )
            for g in ("A100", "H100")
        }
    }
    for row in TABLE_3:
        name = f"a{row.available_a100}_h{row.available_h100}"
        out[name] = {
            "A100": Measured(
                value=float(row.available_a100),
                unit="gpus",
                provenance=Provenance.PAPER_TABLE,
                cite=cite,
                note=(
                    f"Table 3 sweep row: {row.available_a100} A100 available, "
                    f"{row.allocated_a100} allocated; {row.energy_mwh} MWh, "
                    f"${row.cost_k_usd}k"
                ),
            ),
            "H100": Measured(
                value=float(row.available_h100),
                unit="gpus",
                provenance=Provenance.PAPER_TABLE,
                cite=cite,
                note=(
                    f"Table 3 sweep row: {row.available_h100} H100 available, "
                    f"{row.allocated_h100} allocated"
                ),
            ),
        }
    return out


def profile_set(name: str = "baseline") -> ProfileSet:
    if name not in NAMED_SETS:
        raise KeyError(f"unknown profile set {name!r}; have {sorted(NAMED_SETS)}")
    return NAMED_SETS[name]()


__all__ = [
    "NAMED_SETS",
    "baseline",
    "derived_tiers",
    "optimistic",
    "paper_only",
    "pessimistic",
    "profile_set",
    "resample",
]
