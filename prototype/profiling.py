"""
Profile Store with EMA updates, and a Drift Detector (§4.5).

Outside PoC scope — see prototype/README.md. Owner: 077.

This is the half of the project that carries its novelty. "Profile-guided" is the first
phrase in the title, principle P6 is *profiles are measured, not declared*, and R4 is the
requirement none of the PoC touches. It is also the half with no implementation, so this
exists to make the loop concrete enough to argue about.

Nothing here needs an Execution Engine. Observations are fed in directly, which is enough
to exercise the EMA, the drift signal, and the re-optimisation trigger.

THE COMPATIBILITY SCORE IS [PROPOSED] AND IS NOT THE PAPER'S.

§9 attributes it to Hatherley (2025), which is not in this repo. §4.5 describes the
mechanism — "recomputes the would-be decision under the updated profile, computes the
compatibility score, compares to threshold" — but not the score. The definition here is
invented to match that description:

    compatibility = (tasks whose chosen profile is unchanged) / (total tasks)

so 1.0 means the updated profiles would produce exactly the same allocation and 0.0 means
every task would move. Drift signals when compatibility falls below a threshold.

Two consequences worth knowing before trusting a number from this:

  * It is a **decision-space** measure, not a parameter-space one. A large change in `rel(m)`
    that flips no decision scores 1.0 — deliberately, since re-optimising would be pointless
    — but that also means it is blind to drift that is heading somewhere bad and has not
    arrived.
  * It requires running the allocator to evaluate, so it is not cheap. §4.5's claim that
    drift detection is a lightweight signal does not obviously hold under this definition.

**077 must reconcile this against the source before any finding depends on it.**
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from poc.formulation.types import AllocationResult, Observation, ProfileSpec, Task, TaskId

DEFAULT_ALPHA = 0.3             # EMA weight on the newest observation (latency only)
DEFAULT_BETA = 0.2              # EMA weight on throughput (G2, Bayesian Kalman filter equivalence)
# Decay sets the effective sample size at 1/(1 - decay). That ceiling matters more than it
# looks: with a prior of p, an unbroken run of successes converges to (N + p) / (N + 2p), so
# a short memory imposes a CEILING on achievable reliability. At decay 0.98 (N = 50) and a
# Laplace prior of 1.0 that ceiling is 51/52 = 0.981 — and any task with rel_floor 0.99
# would have been permanently unservable by a measured profile. At decay 0.995 (N = 200)
# with a Jeffreys prior of 0.5 the ceiling is 0.9975, which clears realistic floors.
DEFAULT_DECAY = 0.995           # effective sample size ~200
DEFAULT_PRIOR = 0.5             # Jeffreys prior
DEFAULT_MIN_OBSERVATIONS = 5    # below this, suppress drift signals (§4.5)
DEFAULT_WARMUP_OBSERVATIONS = 3 # Tier 1 warmup gate (§7.2, G2)
DEFAULT_SLEW_RATE_MAX = 0.20    # Tier 3 slew rate limiter (+/- 20%) (§7.2, G2)
DEFAULT_ELECTRICITY_PRICE_KWH = 0.12 # $0.12 / kWh electricity price ($3.333e-8 / Joule)
DEFAULT_THRESHOLD = 0.9         # signal when compatibility drops below this
DEFAULT_EPSILON_REL = 0.01      # critical safety margin for reliability floor (§4.5, G6, G7)
DEFAULT_EPSILON_LAT = 5.0       # critical safety margin for latency ceiling (ms) (§4.5, G6, G7)


def get_baseline_power_watts(spec: ProfileSpec) -> float:
    """Return default hardware power draw (Watts) per finding F31 and Arch v5 §7.2.

    Hardware tiers:
      - CPU workers (gpus == 0): 75W
      - Edge / Workstation GPUs (gpus == 1): 200W
      - Datacenter accelerators (gpus >= 2): 350W * gpus
    """
    if spec.gpus == 0:
        return 75.0
    elif spec.gpus == 1:
        return 200.0
    else:
        return 350.0 * float(spec.gpus)


@dataclass(frozen=True)
class ExtendedObservation(Observation):
    """Observation extended with optional throughput, power, and energy telemetry fields (G2)."""
    throughput: float | None = None
    energy_joules: float | None = None
    power_watts: float | None = None


# Backward/forward alias for Architecture v5 telemetry
ObservationV5 = ExtendedObservation


class NotProfiled(Exception):
    """Unprofiled entries return this, never a default value (§4.5, CLAUDE.md)."""


class ProfileStore:
    """Sole writer of profile state (§4.5). Serves immutable snapshots.

    An allocation run reads exactly one snapshot, so a bound computed during that run stays
    meaningful even if observations arrive mid-run.

    In Architecture v5 (Closing Gap G2 per §7.2), ProfileStore implements Online Self-Correcting
    Profiles:
      - Dual-input throughput estimation: direct rate or latency-implied rate (Principle P6).
      - 4-Tier damping architecture to prevent transient outlier spikes from causing false capacity collapses.
      - Steady-state Bayesian Kalman filter equivalence via EMA (beta = 0.2).
      - Thermodynamic efficiency (eta = throughput / P_avg) and effective cost/watt tracking.
    """

    def __init__(self, profiles: dict[str, ProfileSpec],
                 alpha: float = DEFAULT_ALPHA,
                 decay: float = DEFAULT_DECAY,
                 prior: float = DEFAULT_PRIOR,
                 beta: float = DEFAULT_BETA,
                 warmup_observations: int = DEFAULT_WARMUP_OBSERVATIONS,
                 slew_rate_max: float = DEFAULT_SLEW_RATE_MAX,
                 electricity_price_kwh: float = DEFAULT_ELECTRICITY_PRICE_KWH):
        if not 0.0 < alpha <= 1.0:
            raise ValueError(f"alpha must be in (0, 1], got {alpha}")
        if not 0.0 < beta <= 1.0:
            raise ValueError(f"beta must be in (0, 1], got {beta}")
        if not 0.0 < decay <= 1.0:
            raise ValueError(f"decay must be in (0, 1], got {decay}")
        if warmup_observations < 0:
            raise ValueError(f"warmup_observations must be non-negative, got {warmup_observations}")
        if not 0.0 < slew_rate_max <= 1.0:
            raise ValueError(f"slew_rate_max must be in (0, 1], got {slew_rate_max}")

        self._profiles = dict(profiles)
        self._initial_specs = {pid: spec for pid, spec in profiles.items()}
        self._alpha = alpha
        self._beta = beta
        self._decay = decay
        self._prior = prior
        self._warmup_observations = warmup_observations
        self._slew_rate_max = slew_rate_max
        self._electricity_price_kwh = electricity_price_kwh

        # Seeded from the declared reliability so a profile does not start from the prior
        # and immediately look unreliable. Weighted as a few effective observations.
        self._counters = {
            pid: (spec.reliability * 5.0, 5.0) for pid, spec in profiles.items()
        }
        # Hardware power baselines (Watts) for cost/watt estimation
        self._power_draw = {
            pid: get_baseline_power_watts(spec) for pid, spec in profiles.items()
        }
        # Cumulative tracking for energy, energy cost, and observed task costs
        self._cumulative_energy_joules: dict[str, float] = {pid: 0.0 for pid in profiles}
        self._cumulative_energy_cost: dict[str, float] = {pid: 0.0 for pid in profiles}
        self._cumulative_observed_cost: dict[str, float] = {pid: 0.0 for pid in profiles}

    def snapshot(self) -> dict[str, ProfileSpec]:
        """An immutable view. Callers may not mutate the store through it."""
        return dict(self._profiles)

    def get(self, profile_id: str) -> ProfileSpec:
        if profile_id not in self._profiles:
            raise NotProfiled(f"no profile {profile_id!r}")
        return self._profiles[profile_id]

    def reliability_upper_bound(self, profile_id: str, z: float = 1.96) -> float:
        """Optimistic bound on reliability, for eligibility filtering.

        WHY AN UPPER BOUND AND NOT A LOWER ONE. Findings F23 and the first version of the
        component reference both said "filter on a lower confidence bound". That is
        backwards: with few observations a lower bound is *low*, so it would exclude a
        profile faster than the point estimate does, making premature abandonment worse.

        The requirement is to exclude a profile only when we are CONFIDENT it is genuinely
        below the floor. That is the upper bound:

            include m in C(t)  iff  upper_bound(rel(m)) >= R_min(t)

        Few observations -> wide interval -> high upper bound -> keep trying it. Many
        observations on a genuinely bad profile -> the bound converges down -> exclude.
        This is optimism under uncertainty, the standard explore/exploit rule.
        """
        successes, trials = self._counters.get(profile_id, (0.0, 0.0))
        if trials <= 0:
            return 1.0
        point = (successes + self._prior) / (trials + 2 * self._prior)
        margin = z * math.sqrt(max(point * (1.0 - point) / trials, 0.0))
        return min(1.0, point + margin)

    def get_effective_cost(self, profile_id: str) -> float:
        """Return the effective instance price of the profile including energy and observed runtime costs."""
        return self.get(profile_id).price

    def get_efficiency_per_watt(self, profile_id: str) -> float:
        """Return thermodynamic efficiency eta = throughput / P_avg (req/Joule or throughput/Watt)."""
        spec = self.get(profile_id)
        power = self._power_draw.get(profile_id, get_baseline_power_watts(spec))
        if power <= 0:
            return 0.0
        return spec.throughput / power

    def get_cumulative_energy_joules(self, profile_id: str) -> float:
        """Return cumulative active energy in Joules consumed by this profile."""
        if profile_id not in self._profiles:
            raise NotProfiled(f"no profile {profile_id!r}")
        return self._cumulative_energy_joules.get(profile_id, 0.0)

    def get_power_watts(self, profile_id: str) -> float:
        """Return active power draw in Watts for this profile."""
        if profile_id not in self._profiles:
            raise NotProfiled(f"no profile {profile_id!r}")
        return self._power_draw.get(profile_id, get_baseline_power_watts(self.get(profile_id)))

    def record(self, observation: Observation) -> ProfileSpec:
        """Fold one observation into the profile. Returns the updated spec.

        LATENCY uses the EMA that §4.5 specifies. It is a continuous quantity and an EMA
        tracks drift in it correctly.

        RELIABILITY uses a decayed counting estimator with a Laplace prior (Beta-Binomial):
            rel = (decayed successes + prior) / (decayed trials + 2 * prior)

        THROUGHPUT is calibrated online (Gap G2 per Arch v5 §7.2, Principle P6):
          1. Dual-input rate estimation:
             - Direct throughput: r_obs = obs.throughput (if provided and > 0).
             - Latency-implied rate: r_implied = thr_declared * (L_nominal / max(L_obs, 1e-3)).
          2. 4-Tier Outlier Damping Architecture:
             - Tier 1: Cold-start warmup gate (suppresses throughput updates for N < warmup_observations).
             - Tier 2: Huber-style loss attenuation on large deviations (|r - thr| / thr > 0.5).
             - Tier 3: Slew-rate limiter clamping step changes to +/- 20% of current throughput.
             - Tier 4: Global physiological bounds [max(0.10 * thr_0, 1.0), 3.0 * thr_0].

        COST & ENERGY METRICS (Finding F31):
          - Active Energy: E = P_avg * (L_obs / 1000s) (Joules).
          - Energy Cost: C_energy = E * ($0.12 / 3.6e6 J).
          - Effective Price: price_eff = price_initial + cumulative_energy_cost + cumulative_observed_cost.
        """
        current = self.get(observation.profile_id)
        pid = observation.profile_id
        initial = self._initial_specs.get(pid, current)

        # 1. Reliability update (Decayed counting estimator)
        successes, trials = self._counters.get(pid, (0.0, 0.0))
        successes = successes * self._decay + (1.0 if observation.success else 0.0)
        trials = trials * self._decay + 1.0
        self._counters[pid] = (successes, trials)
        new_reliability = (successes + self._prior) / (trials + 2 * self._prior)

        # 2. Latency update (EMA)
        a = self._alpha
        new_latency = (1.0 - a) * current.latency + a * observation.latency

        # 3. Throughput self-correction (G2)
        # Tier 1: Warmup gate (N_warmup observations before adapting throughput)
        if current.observations < self._warmup_observations:
            final_thr = current.throughput
        else:
            # Dual-input rate estimation
            obs_throughput = getattr(observation, "throughput", None)
            if obs_throughput is not None and obs_throughput > 0:
                raw_thr = float(obs_throughput)
            else:
                # Latency-implied service rate: thr_declared * (L_nominal / max(L_obs, 1e-3))
                l_nominal = max(initial.latency, 1e-3)
                l_obs = max(observation.latency, 1e-3)
                raw_thr = initial.throughput * (l_nominal / l_obs)

            # Tier 2: Huber-style loss attenuation on large deviations (|r - thr| / thr > 0.5)
            deviation = abs(raw_thr - current.throughput) / max(current.throughput, 1e-3)
            if deviation > 0.5:
                beta_eff = self._beta / (1.0 + deviation * deviation)
            else:
                beta_eff = self._beta

            # Candidate throughput via EMA
            cand_thr = (1.0 - beta_eff) * current.throughput + beta_eff * raw_thr

            # Tier 3: Slew-rate limiter clamping single-step changes to +/- 20%
            max_shift = current.throughput * self._slew_rate_max
            min_slew = current.throughput - max_shift
            max_slew = current.throughput + max_shift
            slew_clamped_thr = max(min_slew, min(max_slew, cand_thr))

            # Tier 4: Global physiological bounds [max(0.10 * thr_0, 1.0), 3.0 * thr_0]
            min_phys = max(0.10 * initial.throughput, 1.0)
            max_phys = max(3.0 * initial.throughput, min_phys)
            final_thr = max(min_phys, min(max_phys, slew_clamped_thr))

        # 4. Cost and Energy Tracking (Finding F31)
        obs_power = getattr(observation, "power_watts", None)
        if obs_power is not None and obs_power > 0:
            power_w = float(obs_power)
            self._power_draw[pid] = power_w
        else:
            power_w = self._power_draw.get(pid, get_baseline_power_watts(initial))

        exec_sec = max(observation.latency, 0.0) / 1000.0
        obs_energy = getattr(observation, "energy_joules", None)
        if obs_energy is not None and obs_energy >= 0:
            energy_j = float(obs_energy)
        else:
            energy_j = power_w * exec_sec

        energy_cost = energy_j * (self._electricity_price_kwh / 3.6e6)

        obs_cost = float(getattr(observation, "cost", 0.0) or 0.0)
        if obs_cost > 0:
            self._cumulative_observed_cost[pid] += obs_cost

        self._cumulative_energy_joules[pid] += energy_j
        self._cumulative_energy_cost[pid] += energy_cost

        effective_price = initial.price + self._cumulative_energy_cost[pid] + self._cumulative_observed_cost[pid]

        updated = replace(
            current,
            latency=new_latency,
            reliability=new_reliability,
            throughput=final_thr,
            price=effective_price,
            observations=current.observations + 1,
        )
        self._profiles[pid] = updated
        return updated


@dataclass(frozen=True)
class DriftSignal:
    compatibility: float
    threshold: float
    changed_tasks: int
    total_tasks: int
    suppressed: bool            # too few observations to be meaningful
    reason: str
    candidate: AllocationResult | None = None

    @property
    def fired(self) -> bool:
        return not self.suppressed and self.compatibility < self.threshold


class DriftDetector:
    """Signals only; never re-optimises (§4.5).

    Two-tier detection architecture (R2 / G6, G7):
    1. Parameter Cliff Margin Check: Directly flags drift when estimated parameter margins
       (Delta R = R_est - R_min, Delta L = L_max - L_est) breach critical safety margins,
       avoiding an expensive preliminary solve.
    2. Decision-Space Compatibility Check: Evaluates candidate allocation when parameters
       remain within margins, preserving candidate for downstream reuse to prevent duplicate
       optimizer runs.
    """

    def __init__(self, allocate=None, threshold: float = DEFAULT_THRESHOLD,
                 min_observations: int = DEFAULT_MIN_OBSERVATIONS,
                 epsilon_rel: float = DEFAULT_EPSILON_REL,
                 epsilon_lat: float = DEFAULT_EPSILON_LAT):
        self._allocate = allocate
        self._threshold = threshold
        self._min_observations = min_observations
        self._epsilon_rel = epsilon_rel
        self._epsilon_lat = epsilon_lat

    def check(self, current_routing: dict[TaskId, str],
              tasks: list[Task],
              pools: dict[TaskId, list[str]],
              updated_profiles: dict[str, ProfileSpec],
              budget: int) -> DriftSignal:
        """Evaluate parameter cliff margins and would-be decisions under updated profiles."""
        touched = {m for m in current_routing.values()}
        thin = [m for m in touched
                if updated_profiles[m].observations < self._min_observations]
        if thin:
            return DriftSignal(
                compatibility=1.0, threshold=self._threshold, changed_tasks=0,
                total_tasks=len(tasks), suppressed=True,
                reason=f"only {min(updated_profiles[m].observations for m in thin)} "
                       f"observations on {sorted(thin)[0]}; need {self._min_observations}")

        # Tier 1: Parameter Cliff Margin Check (R2 / G6, G7)
        # Delta R = R_est - R_min, Delta L = L_max - L_est
        cliff_violations = []
        for task in tasks:
            profile_id = current_routing.get(task.id)
            if not profile_id or profile_id not in updated_profiles:
                continue
            spec = updated_profiles[profile_id]
            delta_r = spec.reliability - task.rel_floor
            delta_l = task.lat_ceil - spec.latency
            if delta_r < self._epsilon_rel or delta_l < self._epsilon_lat:
                cliff_violations.append((task, profile_id, delta_r, delta_l))

        if cliff_violations:
            first_t, first_m, dr, dl = cliff_violations[0]
            reason = (f"parameter cliff breached on profile '{first_m}' for task {first_t.id}: "
                      f"Delta R={dr:.4f} (< {self._epsilon_rel}), "
                      f"Delta L={dl:.1f}ms (< {self._epsilon_lat}ms)")
            return DriftSignal(
                compatibility=0.0, threshold=self._threshold,
                changed_tasks=len(cliff_violations), total_tasks=len(tasks),
                suppressed=False, reason=reason, candidate=None)

        # Tier 2: Decision-Space Compatibility Check (if no parameter cliff)
        if self._allocate is None:
            return DriftSignal(
                compatibility=1.0, threshold=self._threshold,
                changed_tasks=0, total_tasks=len(tasks),
                suppressed=False, reason="no allocator configured; parameter margins intact",
                candidate=None)

        would_be = self._allocate(tasks, pools, updated_profiles, budget)
        if not would_be.feasible:
            return DriftSignal(
                compatibility=0.0, threshold=self._threshold,
                changed_tasks=len(tasks), total_tasks=len(tasks), suppressed=False,
                reason="no feasible allocation exists under the updated profiles",
                candidate=would_be)

        changed = sum(1 for t in tasks
                      if current_routing.get(t.id) != would_be.routing.get(t.id))
        compatibility = 1.0 - changed / len(tasks) if tasks else 1.0

        return DriftSignal(
            compatibility=compatibility, threshold=self._threshold,
            changed_tasks=changed, total_tasks=len(tasks), suppressed=False,
            reason=f"{changed} of {len(tasks)} tasks would move",
            candidate=would_be)
