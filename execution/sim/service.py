"""
The service model -- how a simulated instance turns tokens into elapsed time.

**This is the least defensible part of M6 and it is labelled as such.** The paper reports
throughput (`theta_m`, tokens/s) and per-request latency (`l^TTFT_m + t_c * l^TPOT_m`) but never
describes a queueing discipline, a batching policy, or what happens when offered load exceeds
capacity. So the model below is `[OURS]`, chosen to be the simplest thing consistent with the
numbers the paper does report:

    capacity(m)      = n_active(m) * theta_m           tokens/s, from the profile curve
    service_time(r)  = l^TTFT_m + tokens(r) * l^TPOT_m  seconds, EQ. (5)'S OWN EXPRESSION
    queueing         = backlog_tokens / capacity        seconds, FIFO

Using eq. (5) for service time is deliberate: it is the same expression the optimizer's latency
filter uses, so the runtime and the planner agree about what a request costs. Where they disagree
is the QUEUEING term, which eq. (5) has no counterpart for at all -- the optimizer assumes a
request meets its SLO if eq. (5) is under `tau`, with no allowance for waiting behind other
requests. That gap is a finding, and this module is where it becomes visible.

TOKENS ARE DRAWN PER REQUEST, NOT SET TO p90. Section 3.4's entire motivation for the auto-scaler
is variance: "a video Q/A workflow with 10 frames and STT on Llava-OneVision-7B produces 600 and
1200 tokens in the 50th and 99th percentile, respectively, highlighting high variance." Serving
every request at `t_c`'s p90 would delete the phenomenon under study. We sample from the
profile's own percentile ladder.
"""

from __future__ import annotations

import bisect
import random
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from optimization.profiles.provenance import Unavailable
from optimization.profiles.schema import (
    ModelProfile,
    ModelProfileKey,
    OperatingPointPolicy,
    TokenDistribution,
)


@dataclass(frozen=True)
class ServiceParams:
    """What one model profile contributes to the runtime, read once from the profile."""

    theta_tokens_s: float
    ttft_s: float | None
    tpot_s: float | None
    gpus: int

    @property
    def eq5_evaluable(self) -> bool:
        """False for the 7 profiles with no TTFT (A35/A36) -- including Llava-OneVision-7B,
        the model Section 3.4's own auto-scaler example uses (A86)."""
        return self.ttft_s is not None and self.tpot_s is not None

    def service_time_s(self, tokens: float) -> float:
        """eq. (5)'s expression, used as the runtime's service time.

        Falls back to `tokens / theta` when TTFT is unreported -- marked by `eq5_evaluable`
        being False so no caller can mistake the fallback for a profiled number.
        """
        if self.eq5_evaluable:
            return self.ttft_s + tokens * self.tpot_s
        return tokens / self.theta_tokens_s if self.theta_tokens_s > 0 else float("inf")


def service_params(
    profile: ModelProfile,
    policy: OperatingPointPolicy = OperatingPointPolicy.TABLE_REPORTED,
) -> ServiceParams:
    theta = profile.theta(policy)
    ttft = profile.ttft(policy)
    tpot = profile.tpot(policy)
    return ServiceParams(
        theta_tokens_s=0.0 if isinstance(theta, Unavailable) else float(theta.value),
        ttft_s=None if isinstance(ttft, Unavailable) else float(ttft.value),
        tpot_s=None if isinstance(tpot, Unavailable) else float(tpot.value),
        gpus=int(profile.parallelism.value),
    )


class TokenSampler:
    """Draws a per-request token count from a profiled `TokenDistribution`.

    Linear interpolation between the profiled percentiles, which are the only shape information
    the figures give. Below p25 and above p99 the endpoints are held flat rather than
    extrapolated -- inventing a tail beyond the data would manufacture exactly the spikes the
    auto-scaler is being tested on.
    """

    def __init__(self, distribution: TokenDistribution, rng: random.Random) -> None:
        pairs = sorted(
            (p, float(v.value))
            for p, v in distribution.percentiles.items()
            if not isinstance(v, Unavailable)
        )
        if not pairs:
            raise ValueError("token distribution has no usable percentile")
        self._pct = [p for p, _ in pairs]
        self._val = [v for _, v in pairs]
        self._rng = rng

    def draw(self) -> float:
        u = self._rng.uniform(0.0, 100.0)
        if u <= self._pct[0]:
            return self._val[0]
        if u >= self._pct[-1]:
            return self._val[-1]
        i = bisect.bisect_left(self._pct, u)
        p0, p1 = self._pct[i - 1], self._pct[i]
        v0, v1 = self._val[i - 1], self._val[i]
        return v0 + (v1 - v0) * (u - p0) / (p1 - p0)

    def percentile(self, p: float) -> float:
        i = bisect.bisect_left(self._pct, p)
        if i == 0:
            return self._val[0]
        if i >= len(self._pct):
            return self._val[-1]
        p0, p1 = self._pct[i - 1], self._pct[i]
        v0, v1 = self._val[i - 1], self._val[i]
        return v0 + (v1 - v0) * (p - p0) / (p1 - p0)


@dataclass
class ModelServer:
    """One model profile's share of the fleet, as a token-rate server with a FIFO backlog."""

    key: ModelProfileKey
    params: ServiceParams
    backlog_tokens: float = 0.0
    served_tokens: float = 0.0
    admitted: int = 0

    def capacity_tokens_s(self, active_instances: int) -> float:
        return active_instances * self.params.theta_tokens_s

    def admit(self, tokens: float) -> None:
        self.backlog_tokens += tokens
        self.admitted += 1

    def queue_delay_s(self, active_instances: int) -> float:
        """How long a request arriving NOW waits behind the backlog.

        eq. (5) has no term for this. The optimizer admits a configuration on
        `l^TTFT + t_c * l^TPOT <= tau` alone, so every second counted here is latency the
        planner cannot see.
        """
        cap = self.capacity_tokens_s(active_instances)
        if cap <= 0:
            return float("inf")
        return self.backlog_tokens / cap

    def drain(self, active_instances: int, dt_s: float) -> float:
        drained = min(self.backlog_tokens, self.capacity_tokens_s(active_instances) * dt_s)
        self.backlog_tokens -= drained
        self.served_tokens += drained
        return drained

    def utilisation(self, active_instances: int, offered_tokens_s: float) -> float:
        cap = self.capacity_tokens_s(active_instances)
        return float("inf") if cap <= 0 else offered_tokens_s / cap


__all__ = ["ModelServer", "ServiceParams", "TokenSampler", "service_params"]
