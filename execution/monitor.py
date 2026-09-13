"""
Per-model-instance load monitoring -- Section 3.4: "monitors per-model instance load over short
windows (seconds to minutes)".

A85 -- THE PAPER NEVER SAYS WHAT "LOAD" IS. Requests/second, tokens/second, queue depth and GPU
utilisation are all defensible readings, and they disagree badly for agentic workflows: the same
request rate can carry a 4x swing in tokens (Figures 2b/2d), which is the very variance
Section 3.4 cites as the auto-scaler's reason to exist.

We measure **tokens/second** (Q34). It is the only unit commensurable with `theta_m`, which is
what the threshold is derived from -- comparing a request rate against a token throughput would
be a unit error of exactly the kind M4's `units.py` exists to prevent. Requests/second and queue
depth are recorded as diagnostics so the choice can be audited, never as the control signal.

The window is a sliding 60 s, the short end of "seconds to minutes". Short windows react faster
and jitter more; with a 20-minute provisioning delay (A87) the reaction speed is mostly academic,
and this module's measurements are what make that visible.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Mapping

from execution.sim.clock import MONITOR_WINDOW_S
from optimization.profiles.schema import ModelProfileKey


@dataclass
class LoadWindow:
    """A sliding window of admitted token load for ONE model profile."""

    window_s: float = MONITOR_WINDOW_S
    samples: Deque[tuple[float, float, int]] = field(default_factory=deque)
    """`(timestamp, tokens, requests)` -- tokens is the control signal, requests a diagnostic."""

    def record(self, now_s: float, tokens: float, requests: int = 1) -> None:
        self.samples.append((now_s, tokens, requests))
        self._evict(now_s)

    def _evict(self, now_s: float) -> None:
        cutoff = now_s - self.window_s
        while self.samples and self.samples[0][0] < cutoff:
            self.samples.popleft()

    def tokens_per_second(self, now_s: float) -> float:
        """The control signal. Commensurable with `theta_m` (tokens/s)."""
        self._evict(now_s)
        if not self.samples:
            return 0.0
        return sum(t for _ts, t, _r in self.samples) / self.window_s

    def requests_per_second(self, now_s: float) -> float:
        """Diagnostic only (A85). Never compared against a throughput threshold."""
        self._evict(now_s)
        if not self.samples:
            return 0.0
        return sum(r for _ts, _t, r in self.samples) / self.window_s

    def mean_tokens_per_request(self, now_s: float) -> float:
        self._evict(now_s)
        reqs = sum(r for _ts, _t, r in self.samples)
        if reqs == 0:
            return 0.0
        return sum(t for _ts, t, _r in self.samples) / reqs


@dataclass
class FleetMonitor:
    """One `LoadWindow` per model profile, plus the diagnostics A85 requires us to keep."""

    window_s: float = MONITOR_WINDOW_S
    windows: dict[ModelProfileKey, LoadWindow] = field(default_factory=dict)

    def record(self, model: ModelProfileKey, now_s: float, tokens: float) -> None:
        self.windows.setdefault(model, LoadWindow(self.window_s)).record(now_s, tokens)

    def tokens_per_second(self, model: ModelProfileKey, now_s: float) -> float:
        w = self.windows.get(model)
        return 0.0 if w is None else w.tokens_per_second(now_s)

    def snapshot(self, now_s: float) -> Mapping[ModelProfileKey, Mapping[str, float]]:
        return {
            m: {
                "tokens_s": w.tokens_per_second(now_s),
                "requests_s": w.requests_per_second(now_s),
                "mean_tokens_per_request": w.mean_tokens_per_request(now_s),
            }
            for m, w in self.windows.items()
        }


__all__ = ["FleetMonitor", "LoadWindow"]
