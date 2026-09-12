"""
Profile data model: the two profiling layers of Section 3.3 and the A.5 parameter projection.

Implements Murakkab (OSDI '26), Section 3.3, "Profiles" (p.573), verbatim:

    "Accurate, fine-grained performance characterization is essential for optimizing
     multi-tenant agentic workflows with dynamic execution patterns. Inspired by
     Profile-Guided Optimization (PGO) [60, 84], Murakkab builds offline profiles across
     diverse configurations to inform runtime decisions. Each profile captures three key
     metrics per workflow configuration: response quality, end-to-end latency, and resource
     usage."

and the split that the same paragraph makes load-bearing:

    "Profiling is lightweight; performed once per configuration and reused across workflows.
     New models and accelerators are profiled upon integration. Decoupling workflow and model
     profiles enables workflows to benefit immediately from model updates, with selective
     re-profiling as needed."

WORKFLOW profiles are denominated in TOKENS (hardware-independent). MODEL profiles convert
tokens into SECONDS, WATTS and DOLLARS (workflow-independent). The only place the two meet is
the capacity constraint, Appendix A.5 eq. (3) (p.586):

    mu_m * SUM_{w,s,c} x^peak_{w,s,c,m} * t_c  <=  n_m * theta_m

-- workflow-side `t_c` against model-side `theta_m`. That single multiplication is the entire
interface between the layers, which is why `MilpInputs` (below) is the only export M4 may read.

Every numeric field on every dataclass here is a `Value` (`Measured | Unavailable`) from
provenance.py. There are no bare floats outside the STRUCTURAL_FIELDS allow-list, and
tests/test_profile_provenance.py enforces that reflectively over an assembled `ProfileSet`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal, Mapping, Sequence

from optimization.profiles.provenance import (
    Citation,
    Measured,
    ProfileProvenanceError,
    ProfileUnavailableError,
    Provenance,
    Unavailable,
    Value,
)

# ---------------------------------------------------------------------------------------------
# Structural (non-measured) numeric fields
# ---------------------------------------------------------------------------------------------

STRUCTURAL_FIELDS: frozenset[str] = frozenset(
    {
        # knob SETTINGS and index-set coordinates -- choices, not measurements
        "tp",
        "dag_variant",
        "workflow_id",
        "model_id",
        "gpu",
        "knobs",
        "name",
        "epoch",
        "percentile",
        "share",
        # bookkeeping
        "unit",
        "accuracy_benchmark",
        "accuracy_measured_on_model",
        "note",
        "reason",
        "blocks",
        "collapsed_rows",
        "residuals",
        "tier_reconstruction",
        "operating_point_collapse",
        "counts",
        "excluded",
    }
)
"""Fields a numeric value may inhabit WITHOUT being wrapped in `Measured`/`Unavailable`.

Deliberately short and deliberately boring: a knob setting (`D=4`), a parallelism degree
(`tp=8`), an epoch index or a percentile number is a *coordinate*, not a measurement, and
wrapping it would dilute the provenance discipline rather than strengthen it.
tests/test_profile_provenance.py asserts this set is unchanged.
"""


# ---------------------------------------------------------------------------------------------
# Workflow layer (Section 3.3, "Workflow Profiles", p.573)
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ConfigKey:
    """Identifies `c` in `C_w`. Appendix A.5 (p.586) defines `C_w` in full as "workflow
    configurations for `w`" -- an opaque index set with `a_c` and `t_c` attached per element.

    Section 3.3.1, Decision 1 (p.574) says what varies inside one: "the workflow-level knob
    settings (e.g., number of frames, STT on/off, debaters and rounds) for each (workflow,
    SLO)-pair".

    `dag_variant` is [OURS] (A50): `stt_enabled` cannot be a knob because Section 3.2 (p.572)
    attaches knobs to "each model or tool" and an executor cannot own the knob that deletes it
    (A18/A24). Option 5 of DESIGN_VIDEO_QA.md makes a configuration a DAG variant instead.
    """

    workflow_id: str
    knobs: tuple[tuple[str, Any], ...]
    dag_variant: str = "default"

    def __post_init__(self) -> None:
        if list(self.knobs) != sorted(self.knobs):
            raise ValueError(f"{self.knobs!r}: knobs must be sorted for a stable join key")

    @property
    def knob(self) -> Mapping[str, Any]:
        return dict(self.knobs)

    def __str__(self) -> str:
        body = ", ".join(f"{k}={v}" for k, v in self.knobs)
        tail = "" if self.dag_variant == "default" else f", dag={self.dag_variant}"
        return f"{self.workflow_id}({body}{tail})"


@dataclass(frozen=True)
class TokenDistribution:
    """`t_c` is not a scalar.

    Section 4.1/4.2 boundary (p.576) allocates on the p90 -- "We assume the 90th percentile
    token generation load from our profiles when making resource allocation decisions for all
    policies for a fair comparison." Section 3.4 (p.575) reports a p50 and a p99 for one
    configuration. Figures 2b and 2d (p.570) ARE distributions (CDFs). A scalar cannot
    represent any of that, and collapsing at profile-build time would destroy the auto-scaler's
    input (Section 3.4 motivates the auto-scaler entirely by this variance).

    NOTE (A46): the p90 sentence exists ONLY in [OSDI] p.576. It has no [ARXIV] counterpart
    (searched: [ARXIV] contains no "90th percentile" string). The rule that shapes every
    capacity number in this reproduction rests on one sentence in one version.
    """

    percentiles: Mapping[int, Value]
    mean: Value
    unit: Literal["completion_tokens"] = "completion_tokens"

    def __post_init__(self) -> None:
        if 90 not in self.percentiles:
            raise ProfileProvenanceError(
                f"{self!r}: p90 is mandatory -- it is what A.5's `t_c` binds to (p.576)"
            )

    def at(self, p: int) -> Value:
        if p not in self.percentiles:
            raise KeyError(f"percentile {p} not profiled; have {sorted(self.percentiles)}")
        return self.percentiles[p]

    def p90(self) -> Value:
        return self.percentiles[90]


@dataclass(frozen=True)
class WorkflowProfile:
    """One row of the workflow-profile table: quality and executor-level load for one `c`.

    Section 3.3 (p.573): quality is measured on a benchmark ("VideoMME [30], HumanEval [15],
    and Math [39] with ground-truth results"); load is "executor-level load, including prompt
    and completion tokens for LLM-based executors, serving as a proxy for resource usage".

    Three fields are NON-MILP and `to_milp()` must not expose them:
      * `accuracy_measured_on_model` -- A.5 indexes accuracy as `a_c`, configuration only, and
        has no constraint linking `c` to `m` (A51). We reproduce the index as written and carry
        the truth alongside it so M4 can *measure* how much selected (c,m) mass is incoherent.
      * `node_tokens` / `node_service_time` -- the per-DAG-node decomposition A.5 cannot
        express (Section 12.1 of DESIGN.md; the makespan/precedence critique).
      * `prompt_tokens` -- Section 3.3 (p.573) requires a profile to capture it; A.5 has one
        token parameter, used both against `theta_m` (an output-token throughput, Figure 3's
        x-axis) and against `l^TPOT_m` (time per *output* token), so only the completion
        reading is dimensionally consistent (A39). Carried as `Unavailable`, per Q17, because
        omitting the field would hide the gap.
    """

    key: ConfigKey
    accuracy: Value
    accuracy_benchmark: str
    accuracy_measured_on_model: str
    tokens: TokenDistribution | Unavailable
    """`Unavailable` for the 14 of 44 configurations whose model has no generated-token CDF in
    either figure (Q19). Not a default and not a zero -- reading it raises."""

    node_tokens: Mapping[str, TokenDistribution | Unavailable] = field(default_factory=dict)
    """Per-DAG-node decomposition of `tokens`. `Unavailable` per node is the common case: only
    the TOOL nodes' exact zeros and Video Q/A's single LLM node are derivable (A59)."""
    node_service_time: Mapping[str, Value] = field(default_factory=dict)
    prompt_tokens: TokenDistribution | Unavailable | None = None

    def to_milp(self, percentile: int = 90) -> Mapping[str, Value]:
        """Exactly A.5's workflow-side parameter pair, and nothing else.

        A configuration whose token distribution is `Unavailable` projects that absence straight
        through rather than raising: M4 must see it, exclude the configuration, and REPORT it as
        data-excluded (Q19). Raising here would tempt a caller to skip the configuration
        silently.
        """
        tokens = self.tokens if isinstance(self.tokens, Unavailable) else self.tokens.at(percentile)
        return {"a_c": self.accuracy, "t_c": tokens}


# ---------------------------------------------------------------------------------------------
# Model layer (Section 3.3, "Model Profiles", p.573)
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelProfileKey:
    """`m` in `M`. Section 3.3.1, Decision 3 (p.574): "A profile encodes a specific model, GPU
    type, and parallelism strategy, so choosing `m` implicitly fixes the hardware and
    parallelism degree."

    NOT re-indexed by operating point (Q20 / A37b). Tables 5 and 6 report the same
    `(model, GPU, TP)` at up to FOUR different `(TPOT, TPS)` operating points across SLO tiers
    -- e.g. Phi-4 / H100 / TP=1 at (0.0373, 757), (0.0165, 248), (0.0253, 552), (0.0372, 755)
    -- and A.2 (p.585) says so explicitly ("increases the allowed load per model instance to
    increase batching as the SLO is relaxed"). But `theta_m` and `l^TPOT_m` are constants of
    `m` in A.5. Expanding `M` would be repairing the formulation; the standing policy forbids
    it. The loss is measured instead (`ModelProfile.collapsed_rows`).
    """

    model_id: str
    gpu: Literal["A100", "H100"]
    tp: int

    def __str__(self) -> str:
        return f"{self.model_id}/{self.gpu}/TP={self.tp}"


@dataclass(frozen=True)
class LoadPoint:
    """One point on a Figure 3 (p.570) curve.

    Section 3.3 (p.573): "Profiles span load levels to expose trade-offs and guide the
    optimizer in allocating load and instances."

    Figure 3's y-axes are labelled literally "TPOT P90 (s)" and "TTFT P90 (s)", so the paper's
    own latency profiles are p90s. eq. (5)'s `l^TTFT_m + t_c * l^TPOT_m` is therefore a
    p90-of-a-sum approximated by a sum-of-p90s. Reproduced as-is; flagged.
    """

    throughput: Value
    ttft_p90: Value
    tpot_p90: Value
    origin: str = ""
    """Free text: which table row or figure reading this point came from. Not a measurement."""


class OperatingPointPolicy(Enum):
    """How the load-indexed profile of Section 3.3 collapses to A.5's scalar parameters.

    Section 3.3 (p.573) describes profiles that "span load levels"; Appendix A.5 (p.586) gives
    `theta_m`, `l^TTFT_m` and `l^TPOT_m` as scalar PARAMETERS, not functions. The load-indexed
    profile the paper describes cannot enter the optimizer it describes. Collapsing is
    therefore a named, swappable policy applied at `to_milp_inputs()` time rather than a hidden
    constant.
    """

    TABLE_REPORTED = "table_reported"
    """The `TPS` and `TPOT` cells of Tables 5/6 (pp.585-586). The only policy with PAPER_TABLE
    provenance end-to-end. Falls back to the Figure 3 saturation endpoint for `m` with no table
    row (8 of 26 profiles); that fallback is PAPER_FIGURE_READ and is recorded per value."""

    MAX_THROUGHPUT = "max_throughput"
    """Curve maximum. Most optimistic; minimises `n_m`. Differs from TABLE_REPORTED by ~6.8x on
    Llava-OneVision-7B/H100/TP=4 (479 -> 3271 tokens/s, Table 5's own rows), which moves every
    headline GPU count by the same factor. The single largest sensitivity knob in the set."""

    KNEE = "knee"
    """Last point before TPOT exceeds 1.5x its floor -- the engineering reading of "expose
    trade-offs"."""


STRONGEST_FIRST = (
    OperatingPointPolicy.TABLE_REPORTED,
    OperatingPointPolicy.KNEE,
    OperatingPointPolicy.MAX_THROUGHPUT,
)


@dataclass(frozen=True)
class ModelProfile:
    """`m`: Section 3.3 (p.573) -- "Each profile reports: (1) latency (TTFT and TPOT for LLMs),
    (2) energy consumption across hardware, and (3) cost per configuration."
    """

    key: ModelProfileKey
    curve: tuple[LoadPoint, ...]
    parallelism: Value
    energy: Value
    tps_per_wh: Value | None = None
    collapsed_rows: tuple[str, ...] = ()
    """Table 5/6 rows for this tuple that TABLE_REPORTED discarded, with the theta ratio.
    A.5 cannot represent them (A37b); recording them makes the magnitude of the loss
    measurable rather than merely arguable."""

    def __post_init__(self) -> None:
        if not self.curve:
            raise ProfileProvenanceError(f"{self.key}: a model profile needs >=1 load point")

    # -- operating-point selection -------------------------------------------------------

    def _point(self, policy: OperatingPointPolicy) -> LoadPoint:
        usable = [p for p in self.curve if isinstance(p.throughput, Measured)]
        if not usable:
            raise ProfileUnavailableError(
                f"{self.key}: no load point has a throughput value (see coverage report)"
            )
        if policy is OperatingPointPolicy.TABLE_REPORTED:
            tabled = [p for p in usable if p.origin.startswith("Table")]
            if tabled:
                return tabled[0]
            # No Table 5/6 row for this `m`. Fall back to the Figure 3 SATURATION ENDPOINT, not
            # to the first plotted point: the first point is the lowest offered load on the
            # sweep, and using it as `theta_m` would understate capacity by up to an order of
            # magnitude and inflate `n_m` by the same factor. The fallback is recorded per value
            # as PAPER_FIGURE_READ, so it is never mistaken for a table cell.
            return max(usable, key=lambda p: p.throughput.value)
        if policy is OperatingPointPolicy.MAX_THROUGHPUT:
            return max(usable, key=lambda p: p.throughput.value)
        if policy is OperatingPointPolicy.KNEE:
            tpots = [p for p in usable if isinstance(p.tpot_p90, Measured)]
            if not tpots:
                return usable[0]
            floor = min(p.tpot_p90.value for p in tpots)
            ok = [p for p in tpots if p.tpot_p90.value <= 1.5 * floor]
            return max(ok or tpots, key=lambda p: p.throughput.value)
        raise ValueError(policy)

    def theta(self, policy: OperatingPointPolicy = OperatingPointPolicy.TABLE_REPORTED) -> Value:
        return self._point(policy).throughput

    def ttft(self, policy: OperatingPointPolicy = OperatingPointPolicy.TABLE_REPORTED) -> Value:
        return self._point(policy).ttft_p90

    def tpot(self, policy: OperatingPointPolicy = OperatingPointPolicy.TABLE_REPORTED) -> Value:
        return self._point(policy).tpot_p90


@dataclass(frozen=True)
class ResourceType:
    """`g` in `G`. Section 4.1 (p.575): "We run our experiments on A100 and H100 VMs from
    Microsoft Azure. Each A100 VM has 8xNVIDIA A100 (80GB) GPUs ... each H100 VM has
    8xNVIDIA H100 (80GB) GPUs".

    Unit check against eq. (7), `SUM_{m:GPU(m)=g} n_m * g_m <= B_g`: `n_m` counts instances and
    `g_m` counts GPUs per instance, so `B_g` counts GPUs -- consistent with Section 4.5's
    "2,000 A100 GPUs" and Table 3's "Allocated A100s" (p.578).
    """

    name: Literal["A100", "H100"]
    cost_per_instance_second: Value
    budget: Value


# ---------------------------------------------------------------------------------------------
# SLOs, arrivals, policies
# ---------------------------------------------------------------------------------------------

SloType = Literal["accuracy", "latency"]
SLO_TIERS: tuple[str, ...] = ("best", "good", "fair", "basic")
"""Section 3.4 (p.575): "We assign four SLO tiers for quality and end-to-end latency: best,
good, fair, and basic." Identical in both versions."""


@dataclass(frozen=True)
class TokenPolicy:
    """Which percentile of `TokenDistribution` becomes A.5's scalar `t_c`.

    Default 90 per [OSDI] p.576. Sweeping is paper-sanctioned, not an invention: Section 3.4
    (p.575) says "The optimizer can be configured to be conservative (i.e., consider the tail
    percentile and provision more resources) or optimistic (i.e., consider a more common case
    ...)".
    """

    percentile: int = 90


@dataclass(frozen=True)
class SloMix:
    """The share of arrivals assigned to each `(SLO type, tier)` pair."""

    name: str
    shares: Mapping[tuple[str, str], float]

    @staticmethod
    def section_4_3() -> "SloMix":
        """Section 4.3 (p.576), identical in both versions: "we run video Q/A and code
        generation requests together and assign 70% requests to be high-accuracy and 30%
        requests to low-latency, both with *good* tier"."""
        return SloMix("section_4_3", {("accuracy", "good"): 0.70, ("latency", "good"): 0.30})

    @staticmethod
    def section_4_2(slo_type: str, tier: str) -> "SloMix":
        """Section 4.2 (p.576): "assume that all requests have the same SLO for each
        experiment" -- i.e. eight separate runs, share 1.0 on one combination."""
        return SloMix(f"section_4_2[{slo_type},{tier}]", {(slo_type, tier): 1.0})


@dataclass(frozen=True)
class ArrivalPattern:
    """`lambda^peak_{w,s}` and `lambda^avg_{w,s}` for one workflow, SLO pair and epoch.

    Section 3.4 (p.575): "The optimizer runs in the background after every optimization epoch,
    in our case every 60 minutes". Section 4.1 (p.576) / A.4 (p.586): the arrivals are "a
    subset of LLM serving traces released by Azure [78] from 08:00 05/15/2024 to 08:00
    05/16/2024 shown in Figure 19", with "the *chat* requests from the trace" mapped "to the
    *video Q/A* workflow and *coding* requests to the *code generation* workflow".
    """

    workflow_id: str
    slo: tuple[str, str]
    epoch: int
    lam_peak: Value
    lam_avg: Value


# ---------------------------------------------------------------------------------------------
# Assembled set and the MILP boundary
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class CoverageReport:
    """What the reproduction knows, what it does not, and what it lost on the way in.

    `DESIGN.md` Section 2.4: `Unavailable.blocks` makes the damage report automatic -- this
    object can state "N of M model profiles cannot be evaluated by eq. (5)" without anyone
    having to remember.
    """

    profile_set: str
    counts: Mapping[str, Mapping[str, int]]
    unavailable: tuple[tuple[str, str, str, tuple[str, ...]], ...]
    tier_reconstruction: Mapping[str, Any] = field(default_factory=dict)
    operating_point_collapse: tuple[str, ...] = ()

    def total_by_provenance(self) -> Mapping[str, int]:
        out: dict[str, int] = {}
        for per_field in self.counts.values():
            for k, v in per_field.items():
                out[k] = out.get(k, 0) + v
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    def blocked(self, expr: str) -> int:
        return sum(1 for *_rest, blocks in self.unavailable if expr in blocks)


@dataclass(frozen=True)
class MilpInputs:
    """The ONLY object `/optimization/milp/` may import (DESIGN.md Section 4.3).

    Its keys are exactly Appendix A.5's parameter list (p.586) and nothing else:
    `a_c`, `t_c`, `theta_m`, `l^TTFT_m`, `l^TPOT_m`, `g_m`, `e_m`, `c_g`, `B_g`, `tau_{w,s}`,
    `lambda^peak_{w,s}`, `lambda^avg_{w,s}`, `alpha`.

    `mu_m` is deliberately ABSENT (A42): eq. (3) introduces the multiplexing factor and the
    paper never defines, bounds or reports it, and it is not in Section 3.3's list of what a
    profile contains -- so it cannot be smuggled into the profile layer. It remains M5's
    problem.
    """

    profile_set_name: str
    token_policy: TokenPolicy
    operating_point_policy: OperatingPointPolicy

    a_c: Mapping[ConfigKey, Value]
    t_c: Mapping[ConfigKey, Value]
    theta_m: Mapping[ModelProfileKey, Value]
    l_ttft_m: Mapping[ModelProfileKey, Value]
    l_tpot_m: Mapping[ModelProfileKey, Value]
    g_m: Mapping[ModelProfileKey, Value]
    e_m: Mapping[ModelProfileKey, Value]
    c_g: Mapping[str, Value]
    B_g: Mapping[str, Value]
    tau: Mapping[tuple[str, str, str], Value]
    lam_peak: Mapping[tuple[str, str, str, int], Value]
    lam_avg: Mapping[tuple[str, str, str, int], Value]
    alpha: Value

    configs_by_workflow: Mapping[str, tuple[ConfigKey, ...]] = field(default_factory=dict)
    gpu_of: Mapping[ModelProfileKey, str] = field(default_factory=dict)
    data_excluded: tuple[str, ...] = ()
    """Configurations and model profiles M4 must report as excluded for LACK OF DATA rather
    than lack of merit (Q19). Printing this beside every headline number is mandatory."""

    A5_PARAMETERS: tuple[str, ...] = (
        "a_c",
        "t_c",
        "theta_m",
        "l_ttft_m",
        "l_tpot_m",
        "g_m",
        "e_m",
        "c_g",
        "B_g",
        "tau",
        "lam_peak",
        "lam_avg",
        "alpha",
    )

    def coherent(self, c: ConfigKey, m: ModelProfileKey) -> bool:
        """Whether configuration `c` and model profile `m` name the SAME model.

        THE MILP MUST NOT CALL THIS (A51). Appendix A.5 contains no constraint linking `c` to
        `m`: `x_{w,s,c,m}` is free to route `c = (D=4, R=4, model=Gemma-3-27B)` onto
        `m = (Phi-4, H100, TP=2)`, claiming Gemma's accuracy while paying Phi-4's throughput,
        latency and energy. This predicate exists so M4 can REPORT "N% of the selected (c,m)
        mass is incoherent" -- turning an argued defect into a measured one.
        """
        return c.knob.get("model") == m.model_id


@dataclass(frozen=True)
class ProfileSet:
    """A complete, named, swappable set of profiles.

    Named because Section 3.4's tier rule (p.575) makes tier values depend on the whole
    population -- "the best, 95th, 80th, and 50th percentile values of accuracy and latency
    available among the set of all workflow, model, and hardware configurations" -- so adding a
    model, a workflow or a GPU type shifts every tier. Tier values are therefore NOT comparable
    across profile sets, and every reported result has to be tagged with the set that produced
    it.
    """

    name: str
    workflow: Mapping[ConfigKey, WorkflowProfile]
    models: Mapping[ModelProfileKey, ModelProfile]
    resources: Mapping[str, ResourceType]
    slo: Mapping[tuple[str, str, str], Value]
    arrivals: tuple[ArrivalPattern, ...]
    alpha: Value
    tier_reconstruction: Mapping[str, Any] = field(default_factory=dict)
    operating_point_collapse: tuple[str, ...] = ()

    # -- coverage ------------------------------------------------------------------------

    def coverage_report(self) -> CoverageReport:
        counts: dict[str, dict[str, int]] = {}
        gaps: list[tuple[str, str, str, tuple[str, ...]]] = []

        def tally(field_name: str, owner: str, v: Value | None) -> None:
            if v is None:
                return
            bucket = counts.setdefault(field_name, {})
            if isinstance(v, Unavailable):
                bucket["UNAVAILABLE"] = bucket.get("UNAVAILABLE", 0) + 1
                gaps.append((field_name, owner, v.reason, v.blocks))
            else:
                key = Provenance(v.provenance).name
                bucket[key] = bucket.get(key, 0) + 1

        for key, wp in self.workflow.items():
            tally("a_c", str(key), wp.accuracy)
            tally(
                "t_c",
                str(key),
                wp.tokens if isinstance(wp.tokens, Unavailable) else wp.tokens.p90(),
            )
            tally("prompt_tokens", str(key), wp.prompt_tokens if wp.prompt_tokens else None)
        for mk, mp in self.models.items():
            tally("theta_m", str(mk), mp.curve[0].throughput)
            tally("l_ttft_m", str(mk), mp.curve[0].ttft_p90)
            tally("l_tpot_m", str(mk), mp.curve[0].tpot_p90)
            tally("g_m", str(mk), mp.parallelism)
            tally("e_m", str(mk), mp.energy)
        for name, rt in self.resources.items():
            tally("c_g", name, rt.cost_per_instance_second)
            tally("B_g", name, rt.budget)
        for skey, sv in self.slo.items():
            tally("tau", "/".join(skey), sv)
        for ap in self.arrivals:
            tally("lambda_peak", f"{ap.workflow_id}/{ap.slo[1]}/h{ap.epoch}", ap.lam_peak)
            tally("lambda_avg", f"{ap.workflow_id}/{ap.slo[1]}/h{ap.epoch}", ap.lam_avg)
        tally("alpha", "alpha", self.alpha)

        return CoverageReport(
            profile_set=self.name,
            counts={k: dict(sorted(v.items())) for k, v in sorted(counts.items())},
            unavailable=tuple(gaps),
            tier_reconstruction=self.tier_reconstruction,
            operating_point_collapse=self.operating_point_collapse,
        )

    # -- the enforced boundary -----------------------------------------------------------

    def to_milp_inputs(
        self,
        token_policy: TokenPolicy | None = None,
        operating_point: OperatingPointPolicy = OperatingPointPolicy.TABLE_REPORTED,
        epochs: Sequence[int] | None = None,
        budget: Mapping[str, Value] | None = None,
    ) -> MilpInputs:
        """Project onto exactly Appendix A.5's parameter list (p.586).

        Nothing from `critique/` is reachable from here, and tests/test_milp_boundary.py
        asserts it: the seven tool service times of Section 12.1 are INVENTED (Q16) and must
        never touch an objective or a constraint.

        `budget` supplies `B_g`, which is `Unavailable` in every profile set by default and
        deliberately so (A43): Sections 4.2 and 4.3 state NO resource budget, so eq. (7) is
        inactive for the headline experiments, and Section 4.5's sweep (Table 3: 2,000 A100 with
        0-500 H100) belongs to that one experiment rather than to a profile. M4 therefore has
        three honest options and must pick one EXPLICITLY -- leave eq. (7) out, pass a Table 3
        scenario from `budget_scenarios()`, or pass its own -- because the alternative is an
        unbounded allocation, which eq. (7) exists to prevent. Passing nothing keeps the absence
        visible rather than defaulting to infinity.
        """
        tp = token_policy or TokenPolicy()
        a_c = {k: wp.accuracy for k, wp in self.workflow.items()}
        t_c = {
            k: (wp.tokens if isinstance(wp.tokens, Unavailable) else wp.tokens.at(tp.percentile))
            for k, wp in self.workflow.items()
        }
        theta = {k: m.theta(operating_point) for k, m in self.models.items()}
        ttft = {k: m.ttft(operating_point) for k, m in self.models.items()}
        tpot = {k: m.tpot(operating_point) for k, m in self.models.items()}
        g_m = {k: m.parallelism for k, m in self.models.items()}
        e_m = {k: m.energy for k, m in self.models.items()}

        by_wf: dict[str, list[ConfigKey]] = {}
        for k in self.workflow:
            by_wf.setdefault(k.workflow_id, []).append(k)

        # Every parameter whose absence makes SOME expression uncomputable, not just the
        # configuration-side ones. `l^TTFT_m` is the case that motivated widening this: 7 of 20
        # model profiles have no TTFT (A35/A36 -- no Figure 3 panel, no table column), so eq. (5)
        # cannot be evaluated for them. Reporting only `t_c`/`a_c`/`theta_m` left those 7 invisible,
        # and M4 would have met an `Unavailable` mid-constraint with no warning that Q19's
        # data-excluded register already knew about it.
        excluded = [str(k) for k, v in t_c.items() if isinstance(v, Unavailable)]
        excluded += [str(k) for k, v in a_c.items() if isinstance(v, Unavailable)]
        excluded += [str(k) for k, v in theta.items() if isinstance(v, Unavailable)]
        excluded += [str(k) for k, v in ttft.items() if isinstance(v, Unavailable)]
        excluded += [str(k) for k, v in tpot.items() if isinstance(v, Unavailable)]
        excluded += [str(k) for k, v in e_m.items() if isinstance(v, Unavailable)]

        keep = set(epochs) if epochs is not None else None
        lam_peak = {
            (ap.workflow_id, ap.slo[0], ap.slo[1], ap.epoch): ap.lam_peak
            for ap in self.arrivals
            if keep is None or ap.epoch in keep
        }
        lam_avg = {
            (ap.workflow_id, ap.slo[0], ap.slo[1], ap.epoch): ap.lam_avg
            for ap in self.arrivals
            if keep is None or ap.epoch in keep
        }

        return MilpInputs(
            profile_set_name=self.name,
            token_policy=tp,
            operating_point_policy=operating_point,
            a_c=a_c,
            t_c=t_c,
            theta_m=theta,
            l_ttft_m=ttft,
            l_tpot_m=tpot,
            g_m=g_m,
            e_m=e_m,
            c_g={n: r.cost_per_instance_second for n, r in self.resources.items()},
            B_g={
                n: (budget or {}).get(n, r.budget) for n, r in self.resources.items()
            },
            tau=dict(self.slo),
            lam_peak=lam_peak,
            lam_avg=lam_avg,
            alpha=self.alpha,
            configs_by_workflow={w: tuple(sorted(v, key=str)) for w, v in by_wf.items()},
            gpu_of={k: k.gpu for k in self.models},
            data_excluded=tuple(sorted(set(excluded))),
        )


__all__ = [
    "STRUCTURAL_FIELDS",
    "SLO_TIERS",
    "ArrivalPattern",
    "Citation",
    "ConfigKey",
    "CoverageReport",
    "LoadPoint",
    "Measured",
    "MilpInputs",
    "ModelProfile",
    "ModelProfileKey",
    "OperatingPointPolicy",
    "ProfileSet",
    "ResourceType",
    "SloMix",
    "SloType",
    "TokenDistribution",
    "TokenPolicy",
    "Unavailable",
    "WorkflowProfile",
]
