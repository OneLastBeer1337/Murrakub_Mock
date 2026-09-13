"""
Simulated time -- DESIGN.md Section 11, and Q42.

**Everything in `/execution/` runs in simulated seconds. Nothing here touches a GPU, a serving
engine, or a network.** That is stated in the module that owns time, because it is the single
easiest thing to forget when reading a report full of latencies and instance counts.

FIXED TICK, NOT DISCRETE-EVENT (Q42). Every quantity the auto-scaler compares is a WINDOWED RATE
-- tokens/s over 60 s, measured against a throughput threshold read off a Figure 3 curve whose
points are sparse pixel readings. Discrete-event simulation would give sub-second event ordering
that the underlying profile data cannot justify, and it would make determinism harder to test for
no gain in fidelity. A 1-second tick is coarse, honest, and reproducible.

The four intervals below are all NAMED COORDINATES, not constants, so any result can be swept
against them:

    tick             1 s     the simulation's resolution
    control          10 s    how often the auto-scaler decides
    window          60 s     Section 3.4's "short windows (seconds to minutes)"
    epoch         3600 s     Section 3.4's "every 60 minutes"
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from optimization.profiles.sources.tables import OPTIMIZATION_EPOCH_MINUTES

TICK_S: float = 1.0
CONTROL_INTERVAL_S: float = 10.0
MONITOR_WINDOW_S: float = 60.0
EPOCH_S: float = OPTIMIZATION_EPOCH_MINUTES * 60.0
"""Imported, not retyped -- Section 3.4's "every 60 minutes" already carries its citation in
`sources/tables.py`."""

PROVISIONING_DELAY_S: float = 1200.0
"""Section 4.7, verbatim: "Provisioning new instances (i.e., VM allocation, software setup, and
model transfer to GPUs) is assumed to take 20 minutes [31, 38, 62]."

**This is A87.** Section 3.4 says the auto-scaler "monitors per-model instance load over short
windows (seconds to minutes) and rapidly scales out when needed". A 20-minute cold start cannot
answer a 60-second window. Kept ON by default (Q40) because switching it off would flatter the
auto-scaler with an assumption the paper does not make -- and because the failure it produces IS
the finding.
"""


@dataclass
class SimClock:
    """Simulated seconds since the start of the run. Monotonic, explicit, testable."""

    now_s: float = 0.0
    tick_s: float = TICK_S

    def advance(self) -> float:
        self.now_s += self.tick_s
        return self.now_s

    def ticks(self, duration_s: float) -> Iterator[float]:
        end = self.now_s + duration_s
        while self.now_s < end:
            yield self.advance()

    @property
    def epoch_index(self) -> int:
        return int(self.now_s // EPOCH_S)

    def is_control_instant(self) -> bool:
        return abs(self.now_s % CONTROL_INTERVAL_S) < self.tick_s / 2.0

    def is_epoch_boundary(self) -> bool:
        return abs(self.now_s % EPOCH_S) < self.tick_s / 2.0


__all__ = [
    "CONTROL_INTERVAL_S",
    "EPOCH_S",
    "MONITOR_WINDOW_S",
    "PROVISIONING_DELAY_S",
    "SimClock",
    "TICK_S",
]
