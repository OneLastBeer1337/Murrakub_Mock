"""
Turning routing FRACTIONS into per-request choices -- A83, the gap Section 3.4 creates and
does not close.

THE CONTRADICTION, STATED PLAINLY. Section 3.4 says request dispatch is "deterministic given the
selected workflow". But A.5 declares `x^peak, x^avg in R+` -- CONTINUOUS -- and the optimizer
routinely spreads one request stream across several `(c, m)` pairs (M4 records this as
`support_size`, A70). A fractional routing map is not a deterministic choice; something must turn
`{pair_A: 0.7, pair_B: 0.3}` into a decision for request #4171, and the paper never says what.

That "something" is a policy with real consequences, so M6 implements three and makes the choice
explicit (Q33). They differ in their ERROR STRUCTURE, not their mean:

    weighted_random   realized split converges as O(1/sqrt(N)); short-window error is what the
                      auto-scaler exists to absorb, so this arm exercises the component
    round_robin       deterministic, bounded error -- closest to Section 3.4's literal word
    hash_by_request   deterministic per request id; stable under replay, useful as a control

**Default is `weighted_random`** because a dispatcher with no short-term error would make the
auto-scaler look unnecessary by construction. Round-robin is the control arm and both get
reported. No policy is applied silently -- the choice travels in the result.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Mapping, Protocol, Sequence

from optimization.profiles.schema import ConfigKey, ModelProfileKey

Pair = tuple[ConfigKey, ModelProfileKey]


class DispatchPolicy(Protocol):
    name: str

    def choose(self, pairs: Sequence[Pair], weights: Sequence[float], request_id: int) -> Pair: ...


@dataclass
class WeightedRandom:
    """Samples in proportion to the plan. Realized split converges; short windows deviate."""

    rng: random.Random = field(default_factory=lambda: random.Random(0))
    name: str = "weighted_random"

    def choose(self, pairs, weights, request_id):
        return self.rng.choices(list(pairs), weights=list(weights), k=1)[0]


@dataclass
class RoundRobin:
    """Deterministic interleave honouring the weights via largest-remainder allocation.

    The closest reading of Section 3.4's "deterministic". Its realized split error is bounded by
    one request per pair rather than growing with sqrt(N), which is why it is the control arm:
    any auto-scaler behaviour that appears under `weighted_random` but not here was caused by
    dispatch noise, not by load.
    """

    name: str = "round_robin"
    _schedule: list[Pair] = field(default_factory=list)
    _i: int = 0
    _built_for: tuple = ()

    def choose(self, pairs, weights, request_id):
        signature = (tuple(map(str, pairs)), tuple(weights))
        if signature != self._built_for:
            self._schedule = _largest_remainder(list(pairs), list(weights), 100)
            self._built_for = signature
            self._i = 0
        pair = self._schedule[self._i % len(self._schedule)]
        self._i += 1
        return pair


@dataclass
class HashByRequest:
    """Deterministic per request id -- stable under replay, order-independent."""

    name: str = "hash_by_request"

    def choose(self, pairs, weights, request_id):
        total = sum(weights)
        if total <= 0:
            return pairs[0]
        target = ((request_id * 2654435761) % 10_000) / 10_000 * total
        acc = 0.0
        for pair, w in zip(pairs, weights):
            acc += w
            if target < acc:
                return pair
        return pairs[-1]


def _largest_remainder(pairs: list[Pair], weights: list[float], slots: int) -> list[Pair]:
    """A SMOOTH weighted schedule -- interleaved, not blocked.

    The obvious implementation emits `[a] * 70 + [b] * 30`, which has the right totals and is
    useless as a control arm: over any window shorter than 70 requests it is further from the
    plan than weighted-random, because it serves only `a`. Round-robin is supposed to be the
    LOW-error policy, so the interleave is the whole point.

    This is smooth weighted round-robin: at each slot, emit the pair whose cumulative deficit
    against its target share is largest. For 0.7/0.3 that gives `a b a a b a a b a a ...`, whose
    deviation from the plan is bounded at every prefix rather than only at the end.
    """
    total = sum(weights) or 1.0
    targets = [w / total for w in weights]
    emitted = [0.0] * len(pairs)
    out: list[Pair] = []
    for slot in range(slots):
        deficits = [targets[i] * (slot + 1) - emitted[i] for i in range(len(pairs))]
        pick = max(range(len(pairs)), key=lambda i: deficits[i])
        out.append(pairs[pick])
        emitted[pick] += 1.0
    return out or [pairs[0]]


@dataclass
class Dispatcher:
    """Applies a named policy to a plan's normalised routing.

    **Contains no critical-path, earliest-finish-time or makespan logic**, and reads no DAG
    edges. A.5 has no precedence constraint, so neither does the runtime that realises it
    (DESIGN.md Section 12.2). `tests/test_execution_*.py` asserts this by inspection.
    """

    policy: DispatchPolicy
    realized: dict[Pair, int] = field(default_factory=dict)

    def dispatch(self, routing: Mapping[Pair, float], request_id: int) -> Pair:
        pairs = list(routing)
        weights = [routing[p] for p in pairs]
        chosen = self.policy.choose(pairs, weights, request_id)
        self.realized[chosen] = self.realized.get(chosen, 0) + 1
        return chosen

    def realized_split(self) -> Mapping[Pair, float]:
        total = sum(self.realized.values())
        return {} if total == 0 else {p: c / total for p, c in self.realized.items()}


def policy_named(name: str, seed: int = 0) -> DispatchPolicy:
    if name == "weighted_random":
        return WeightedRandom(rng=random.Random(seed))
    if name == "round_robin":
        return RoundRobin()
    if name == "hash_by_request":
        return HashByRequest()
    raise KeyError(f"{name!r}: expected weighted_random | round_robin | hash_by_request")


DEFAULT_POLICY = "weighted_random"

__all__ = [
    "DEFAULT_POLICY",
    "DispatchPolicy",
    "Dispatcher",
    "HashByRequest",
    "Pair",
    "RoundRobin",
    "WeightedRandom",
    "policy_named",
]
