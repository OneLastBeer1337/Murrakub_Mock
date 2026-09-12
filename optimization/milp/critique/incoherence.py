"""
A51 measured, never constrained -- Appendix A.5 has no constraint linking `c` to `m`.

**QUARANTINED.** `model.py` must never import this module, and
`tests/test_milp_formulation.py::test_model_py_never_imposes_coherence` asserts it by static
import analysis. The reason is the standing policy: adding `c.model == m.model_id` to the MILP
would REPAIR the formulation, and this project exists to measure Murakkab's defects rather than
fix them.

THE DEFECT. `x_{w,s,c,m}` is indexed by a configuration and a model profile independently.
Nothing requires them to name the same model. So the optimizer may route
`c = (D=4, R=4, model=Gemma-3-27B)` onto `m = (Phi-4, H100, TP=2)` and claim Gemma's accuracy
`a_c` while paying Phi-4's throughput, latency and energy. It is not a loophole an implementation
opens -- it is what the index structure permits, and a cost-minimising optimizer has every
incentive to exploit it.

WHAT IS REPORTED, AND WHY EACH PIECE IS NEEDED:

  * `fraction` -- how much of the allocated mass is incoherent. The headline number.
  * `largest_flow` -- the single worst offender, named, so the claim is concrete.
  * `accuracy_delta_pp` -- claimed `a_c` minus the accuracy of the configuration that actually
    names `m` at the same knobs. This converts the defect from "the indices are loose" into
    **percentage points of over-claimed quality**, which is the form the comparison chapter needs.
  * `counterfactual` -- the same model re-solved WITH coherence imposed, in this module, never
    touching the headline result. The gap between the two is the price A.5's looseness buys.

**EITHER OUTCOME IS A FINDING.** A zero fraction means the defect is latent -- the optimum did
not need to exploit it under this profile set -- and is emphatically NOT a vindication of A.5.
A non-zero fraction means the formulation is exploitable and we have measured it. The design must
not prefer one, and this module reports whichever occurs without editorialising.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from optimization.profiles.schema import ConfigKey, MilpInputs, ModelProfileKey

PairKey = tuple[ConfigKey, ModelProfileKey]


@dataclass(frozen=True)
class IncoherentFlow:
    config: ConfigKey
    model: ModelProfileKey
    mass: float
    claimed_accuracy: float | None
    actual_accuracy: float | None
    """Accuracy of the configuration that names `m` at the same knobs, where one exists."""

    alien_to_workflow: bool = False
    """The routed model does not appear in ANY configuration of this workflow.

    A strictly stronger defect than an accuracy mismatch, and the one that actually occurs.
    `M` in A.5 is global -- all model profiles -- and no constraint restricts it to models the
    workflow's own `C_w` mentions. So a Video Q/A request can be assigned to Phi-4, a text-only
    model that appears only in Code Generation configurations and cannot process video at all.
    There is no `a_c` to compare against because the pairing is not merely over-optimistic, it is
    not a thing that could run.
    """

    @property
    def accuracy_delta_pp(self) -> float | None:
        if self.claimed_accuracy is None or self.actual_accuracy is None:
            return None
        return self.claimed_accuracy - self.actual_accuracy

    def describe(self) -> str:
        if self.alien_to_workflow:
            return (
                f"{self.mass:.4g} req/s of `{self.config}` routed onto `{self.model}` -- "
                f"{self.model.model_id} appears in NO {self.config.workflow_id} configuration; "
                "A.5's M is global and nothing ties it to the workflow's own C_w"
            )
        delta = self.accuracy_delta_pp
        tail = "" if delta is None else f", over-claiming {delta:+.2f} pp of accuracy"
        return (
            f"{self.mass:.4g} req/s of `{self.config}` routed onto `{self.model}` "
            f"-- claims {self.config.knob.get('model')}'s accuracy while paying "
            f"{self.model.model_id}'s throughput{tail}"
        )


@dataclass(frozen=True)
class IncoherenceReport:
    """A51, quantified for one run."""

    total_mass: float
    incoherent_mass: float
    flows: tuple[IncoherentFlow, ...]
    counterfactual_objective: float | None = None
    headline_objective: float | None = None

    @property
    def fraction(self) -> float:
        return 0.0 if self.total_mass <= 0 else self.incoherent_mass / self.total_mass

    @property
    def largest_flow(self) -> IncoherentFlow | None:
        return max(self.flows, key=lambda f: f.mass, default=None)

    @property
    def alien_mass(self) -> float:
        """Mass routed onto a model that appears in NO configuration of its workflow."""
        return sum(f.mass for f in self.flows if f.alien_to_workflow)

    @property
    def alien_fraction(self) -> float:
        return 0.0 if self.total_mass <= 0 else self.alien_mass / self.total_mass

    @property
    def worst_over_claim_pp(self) -> float | None:
        deltas = [f.accuracy_delta_pp for f in self.flows if f.accuracy_delta_pp is not None]
        return max(deltas) if deltas else None

    @property
    def price_of_incoherence(self) -> float | None:
        """Counterfactual objective minus headline objective.

        How much the optimizer saved by exploiting the missing constraint. `None` when the
        counterfactual was not run or was infeasible -- and infeasibility is itself informative:
        it means coherence alone makes the problem unsolvable under this profile set.
        """
        if self.counterfactual_objective is None or self.headline_objective is None:
            return None
        return self.counterfactual_objective - self.headline_objective

    def summary(self) -> str:
        if not self.flows:
            return (
                "incoherent mass: 0.0% -- the defect is LATENT under this profile set. This is "
                "not a vindication of A.5: the constraint is still absent, and another profile "
                "set or objective may exploit it."
            )
        worst = self.largest_flow
        alien = (
            f" Of that, {self.alien_fraction * 100:.1f}% is routed onto a model that appears in "
            "NO configuration of its own workflow."
            if self.alien_mass > 0
            else ""
        )
        return (
            f"incoherent mass: {self.fraction * 100:.1f}% of allocation.{alien} "
            f"Largest: {worst.describe() if worst else 'n/a'}"
        )


def measure(
    inputs: MilpInputs,
    x: Mapping[PairKey, float],
    tolerance: float = 1e-9,
) -> IncoherenceReport:
    """Measure how much allocated mass claims one model's quality while paying another's bill."""
    by_knobs: dict[tuple[str, tuple], ConfigKey] = {}
    models_of_workflow: dict[str, set[str]] = {}
    for c in inputs.a_c:
        model = c.knob.get("model")
        if model is not None:
            other = tuple((k, v) for k, v in c.knobs if k != "model")
            by_knobs[(model, other)] = c
            models_of_workflow.setdefault(c.workflow_id, set()).add(model)

    total = 0.0
    bad = 0.0
    flows: list[IncoherentFlow] = []
    for (c, m), mass in x.items():
        if mass <= tolerance:
            continue
        total += mass
        if inputs.coherent(c, m):
            continue
        bad += mass
        claimed = _accuracy_of(inputs, c)
        twin = by_knobs.get((m.model_id, tuple((k, v) for k, v in c.knobs if k != "model")))
        flows.append(
            IncoherentFlow(
                config=c,
                model=m,
                mass=mass,
                claimed_accuracy=claimed,
                actual_accuracy=_accuracy_of(inputs, twin) if twin is not None else None,
                alien_to_workflow=m.model_id
                not in models_of_workflow.get(c.workflow_id, set()),
            )
        )
    return IncoherenceReport(
        total_mass=total,
        incoherent_mass=bad,
        flows=tuple(sorted(flows, key=lambda f: -f.mass)),
    )


def _accuracy_of(inputs: MilpInputs, c: ConfigKey | None) -> float | None:
    if c is None:
        return None
    value = inputs.a_c.get(c)
    if value is None or not hasattr(value, "value"):
        return None
    try:
        return float(value.value)
    except Exception:
        return None


def coherent_pairs(
    inputs: MilpInputs, pairs: tuple[PairKey, ...]
) -> tuple[PairKey, ...]:
    """The counterfactual index space: only pairs naming the same model.

    Used ONLY to re-solve for `price_of_incoherence`. This is the repaired formulation, and it
    exists here, in `critique/`, precisely so that it can never be mistaken for the reproduction.
    """
    return tuple((c, m) for (c, m) in pairs if inputs.coherent(c, m))


__all__ = [
    "IncoherenceReport",
    "IncoherentFlow",
    "coherent_pairs",
    "measure",
]
