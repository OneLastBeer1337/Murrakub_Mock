"""
ProvisioningState — instances per profile, load per profile, GPUs consumed.

Spec: docs/design/System_Architecture_v2.md §4.4, §6.3.
Build step 5. Verified by: admit/release/snapshot/restore sequences; budget rejection.
Owner: 083

This component is the correction at the heart of v2. v1 modelled a slot pool decremented
per task. Under (C2)-(C3) a task consumes no resource directly — it adds *load*, which may
or may not force a new instance.

`cost_to_admit` is the most important operation in the system. It answers "what does routing
this task here cost right now" — and its answer changes as other tasks are admitted. That
state-dependence IS the aggregate-coupling problem, made explicit rather than hidden.

DESIGN NOTE — n[m] is derived, never stored.

    n[m] = ceil(load[m] / thr(m))

Keeping instance counts as a function of routed load rather than as a separate accumulator
makes I2 and I5 true by construction, and makes admit/release exactly symmetric: releasing
a task always returns the state to what it was before admitting it, including giving back
an instance that the task alone had forced open. Storing n incrementally does not give
that — a released task can leave a stranded instance behind, which would quietly inflate
every Track A relocate and every Track C repair.

The identity that makes the incremental view and the derived view agree, for
n = ceil(load/thr):

    ceil((load + l)/thr) - ceil(load/thr)  ==  ceil((load + l - n*thr)/thr)

so cost_to_admit's shortfall arithmetic and the derived count never disagree.

The consequence worth knowing: this state cannot hold spare instances that no load
justifies. No PoC track needs that. A rounding policy that wants to provision ahead of
demand would need a different container.
"""

from __future__ import annotations

import math

from poc.formulation.types import AdmitCost, ProfileSpec, Task, TaskId

# Loads are floats; guard the ceiling against representation error so that a load of
# exactly one instance's throughput does not round up to two.
_ROUND_DP = 9


def _instances_for(load: float, throughput: float) -> int:
    if load <= 0:
        return 0
    return math.ceil(round(load / throughput, _ROUND_DP))


class ProvisioningState:
    def __init__(self, profiles: dict[str, ProfileSpec], budget: int):
        self._profiles = profiles
        self._budget = budget
        self._load: dict[str, float] = {m: 0.0 for m in profiles}
        self._assigned: dict[TaskId, str] = {}

    # --- queries -----------------------------------------------------------------

    def instances(self, profile_id: str) -> int:
        """n[m]."""
        profile = self._profiles[profile_id]
        return _instances_for(self._load[profile_id], profile.throughput)

    def load(self, profile_id: str) -> float:
        return self._load[profile_id]

    def gpus_used(self) -> int:
        return sum(self.instances(m) * p.gpus for m, p in self._profiles.items())

    def headroom(self, profile_id: str) -> float:
        profile = self._profiles[profile_id]
        return self.instances(profile_id) * profile.throughput - self._load[profile_id]

    def total_cost(self) -> float:
        return sum(self.instances(m) * p.price for m, p in self._profiles.items())

    def build_provisioning(self) -> dict[str, int]:
        """n[m], omitting profiles with no instances."""
        return {m: self.instances(m) for m in self._profiles if self.instances(m) > 0}

    def routing(self) -> dict[TaskId, str]:
        return dict(self._assigned)

    # --- the central operation ---------------------------------------------------

    def cost_to_admit(self, task: Task, profile_id: str) -> AdmitCost | None:
        """What routing `task` to `profile_id` costs against the current state.

        Returns None when the extra GPUs would exceed the remaining budget — that is the
        (C3) rejection, and it is why select_profile can run out of options.
        """
        profile = self._profiles[profile_id]
        current = self.instances(profile_id)
        needed = _instances_for(self._load[profile_id] + task.load, profile.throughput)

        extra_instances = max(0, needed - current)
        extra_gpus = extra_instances * profile.gpus

        if self.gpus_used() + extra_gpus > self._budget:
            return None

        return AdmitCost(extra_instances=extra_instances,
                         extra_gpus=extra_gpus,
                         extra_cost=extra_instances * profile.price)

    # --- mutation ----------------------------------------------------------------

    def admit(self, task: Task, profile_id: str) -> None:
        if task.id in self._assigned:
            raise ValueError(f"task {task.id} is already admitted to "
                             f"{self._assigned[task.id]}")
        if self.cost_to_admit(task, profile_id) is None:
            raise ValueError(f"admitting {task.id} to {profile_id} would exceed the GPU "
                             f"budget; callers must check cost_to_admit first")
        self._load[profile_id] += task.load
        self._assigned[task.id] = profile_id

    def release(self, task: Task, profile_id: str) -> None:
        if self._assigned.get(task.id) != profile_id:
            raise ValueError(f"task {task.id} is not admitted to {profile_id}")
        self._load[profile_id] -= task.load
        # Guard against drift from repeated float add/subtract.
        if abs(self._load[profile_id]) < 10 ** -_ROUND_DP:
            self._load[profile_id] = 0.0
        del self._assigned[task.id]

    # --- backtracking ------------------------------------------------------------

    def snapshot(self) -> dict:
        """For Track A's multi-start and Track C's rounding repair (§4.4)."""
        return {"load": dict(self._load), "assigned": dict(self._assigned)}

    def restore(self, snap: dict) -> None:
        self._load = dict(snap["load"])
        self._assigned = dict(snap["assigned"])
