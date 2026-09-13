"""
select_profile — the one inner rule all three tracks call (principle P4).

Spec: docs/design/System_Architecture_v2.md §5.2.1.
Build step 6. Verified by: known pools with hand-computed picks; all-infeasible returns None.
Owner: 075

cost_adjust is the seam that lets the tracks share this rule:

    Track A       admit.extra_cost                    marginal provisioning cost only
    Track B       admit.extra_cost + lambda[task]     plus the relaxed assignment multiplier
    Track C       admit.extra_cost                    (repair pass)

Complexity: O(|C(t)|) per task. The pool passed in is C(t), already floor-filtered —
floors are applied by construction, never weighted against cost (principle P3).

TIE-BREAKING IS PART OF THE CONTRACT. The §5.2.1 pseudocode uses a strict `<`, which makes
the winner depend on iteration order when two profiles price identically — and on this
problem ties are common, because extra_cost is 0 for every profile that already has enough
headroom. Ties are broken on profile id so results are reproducible (P10). Changing this
changes Track A's output on every tied instance, so change it deliberately or not at all.
"""

from __future__ import annotations

from poc.core.provisioning import ProvisioningState
from poc.formulation.types import Task


def select_profile(task: Task,
                   pool: list[str],
                   state: ProvisioningState,
                   cost_adjust) -> str | None:
    """Return the winning profile id, or None if no profile is admissible within budget.

    None corresponds to Infeasible(reason="no profile admissible within budget",
                                   blocking_task=task.id, constraint="C3").
    """
    best: str | None = None
    best_value: float | None = None

    for profile_id in pool:
        admit = state.cost_to_admit(task, profile_id)
        if admit is None:               # would exceed the GPU budget
            continue

        value = cost_adjust(profile_id, admit)
        if best_value is None or value < best_value or (
                value == best_value and profile_id < best):
            best, best_value = profile_id, value

    return best
