# Milestone 3 — Design: Workflow Profiles and Model Profiles `/optimization/profiles/`

**Phase:** Optimization (paper §3.3, "Profiles", p.573; Figure 6 p.574; Appendix A.5 p.586-587)
**Status:** design review pending — no implementation code, no profile data files exist or should
exist yet. Q13-Q20 were delegated back by Arno on 2026-09-11 and are **resolved as recommended**
(§15); that resolves the open questions, not the design itself, which still needs approval.
**Scope:** the two profiling layers for **both** implemented workflows (Code Generation, Video Q/A),
plus the three other MILP input classes §3.3.1 names (arrival patterns, SLO thresholds, resource
budgets). Math Q/A and OS-log analysis remain deferred.

**Sources of truth — two versions, cross-checked.**

| Tag | Document | Used for |
|---|---|---|
| **[OSDI]** | Chaudhry et al., "Murakkab: Resource-Efficient Agentic Workflow Orchestration in Cloud Platforms", *OSDI '26*, pp. 567-587. Cited as `§x.y p.NNN`. | primary |
| **[ARXIV]** | arXiv:2508.18298v2, same authors/title, 18 pp. Cited as `arXiv p.N`. | cross-check |

The two versions **mostly agree but are not identical**, and several differences land directly on
M3's inputs. Every one found is recorded in §11 (A44-A48) rather than silently resolved. Figure and
table numbering differs between versions; §11.1 gives the concordance. Unless tagged, a citation is
[OSDI].

**Standing policy in force (Arno, 2026-09-10):** reproduce Murakkab literally. Where the paper is
ambiguous, unsound, or incomplete, take the paper's reading and report the problem; do not repair
it. M3 is where this bites hardest, because a profile is a *number*, and a wrong number looks
exactly like a right one.

Conventions carried from M1/M2/M2b: **[DESIGN CHOICE]** fills a paper silence; **[INVENTED]** has no
paper counterpart; **[OURS]** marks a step the paper does not describe at all. Ambiguity numbering
continues M1 (A1-A10), M2 (A11-A21), M2b (A22-A33) — this document starts at **A34**. Open questions
continued at **Q13** and ran to **Q20**; all eight are now resolved (§15), so M4 opens at **Q21**.

---

## 1. Plain-language overview (read this first)

### 1.1 What a profile is

A *profile* is a lookup table of measured numbers that lets the optimizer predict what a choice will
cost **before** making it. §3.3 (p.573) states the intent:

> "Accurate, fine-grained performance characterization is essential for optimizing multi-tenant
> agentic workflows with dynamic execution patterns. Inspired by Profile-Guided Optimization (PGO)
> [60, 84], Murakkab builds offline profiles across diverse configurations to inform runtime
> decisions. Each profile captures three key metrics per workflow configuration: response quality,
> end-to-end latency, and resource usage."

M1 built the DAG. M2/M2b built the menu of executors and declared which knobs exist. Neither said
what any setting *costs*. M3 is the answer to "what happens if I turn this knob", and it is the only
input M4's MILP has. Nothing else about M1/M2 reaches the optimizer (M2 DESIGN.md §5, last row).

### 1.2 Why there are two layers, not one

§3.3 (p.573) splits profiling in two, and the split is load-bearing:

- **Workflow profiles** answer *"if I run the Code Generation workflow with 4 debaters and 4 rounds
  on Gemma-3-27B, how good is the answer and how many tokens does it burn?"* Quality is measured on
  a benchmark ("VideoMME [30], HumanEval [15], and Math [39] with ground-truth results"), and load
  is measured as "executor-level load, including prompt and completion tokens for LLM-based
  executors, serving as a proxy for resource usage".
- **Model profiles** answer *"if I put Gemma-3-27B on 4 A100s, how many tokens per second do I get,
  at what TTFT/TPOT, at what energy and what dollar cost?"* — "Each profile reports: (1) latency
  (TTFT and TPOT for LLMs), (2) energy consumption across hardware, and (3) cost per configuration."

The paper gives the reason for the split explicitly, and it is an architectural argument, not an
implementation detail:

> "Profiling is lightweight; performed once per configuration and reused across workflows. New
> models and accelerators are profiled upon integration. Decoupling workflow and model profiles
> enables workflows to benefit immediately from model updates, with selective re-profiling as
> needed." (§3.3, p.573)

Workflow profiles are measured in **tokens** (hardware-independent). Model profiles convert tokens
into **seconds, watts and dollars** (workflow-independent). The MILP multiplies them: capacity eq.
(3) is `μ_m · Σ x^peak · t_c ≤ n_m · θ_m` — workflow-side `t_c` against model-side `θ_m`. That one
multiplication is the entire interface between the layers.

### 1.3 What it means that we have no GPUs

Everything M3 produces is a *reconstruction* of numbers the authors measured on hardware we do not
have. There are four honest positions a number can be in, and the whole milestone is organised
around keeping them apart:

1. **The paper prints it.** Tables 5 and 6 give `Model | GPU | TP | TPOT | TPS` per chosen
   configuration; Figures 7/8 print the four SLO tier values per workflow. These are real, and we
   copy them.
2. **The paper plots it.** Figures 2a-2d, 3, 4a-4b, 19 contain the numbers as pixels. We digitize
   them, and every digitized value carries an uncertainty band, because a bar read as 87% might be
   86.6% or 87.4%.
3. **The paper implies it.** e.g. per-GPU average power is not stated, but Table 3's
   (GPUs, MWh, hours) triple pins it *if* you assume the allocation was constant over the 24 h.
   These are derivations with a stated assumption attached.
4. **The paper says nothing, and no defensible interpolation exists.** The dollar cost per GPU-hour
   `c_g` is in this class (§11, A40). So is TTFT for Llava-OneVision-7B (A35/A36). Here M3 **flags
   and stops**, per `CLAUDE.md`. It does not produce a confident-looking number.

The danger this milestone exists to manage is stated in Arno's project memory and is worth repeating
in the design doc itself: **with no GPUs, every number M4 produces is a function of profiles we
reconstructed.** "Murakkab provisions X% more GPUs than my system" is a claim about the two systems
only if it survives a different plausible profile set. §9 designs for that from the start.

### 1.4 What M3 must supply, exactly

A.5 (p.586) consumes exactly this, and nothing else matters:

| Symbol | Meaning (A.5 verbatim) | Layer | §  |
|---|---|---|---|
| `a_c` | Accuracy of workflow configuration `c ∈ C_w` | workflow | 5 |
| `t_c` | Tokens per request for workflow configuration `c` | workflow | 5 |
| `θ_m` | Token throughput (tokens/sec) for model profile `m` | model | 6 |
| `ℓ^TTFT_m` | Time to first token for model profile `m` | model | 6 |
| `ℓ^TPOT_m` | Time per output token for model profile `m` | model | 6 |
| `g_m` | Parallelism for model `m` | model | 6 |
| `e_m` | Energy consumption (kWh) for model profile `m` | model | 6 |
| `c_g` | Cost per instance per second for resource type `g ∈ G` | resource | 6.6 |
| `B_g` | Maximum available resource instances of type `g` | resource | 8.3 |
| `τ_{w,s}` | SLO threshold for workflow `w`, SLO type `s` | SLO tiers | 7 |
| `λ^peak_{w,s}`, `λ^avg_{w,s}` | Peak / average request rate | arrivals | 8 |
| `α` | Unified buffer factor (default 1.15) | constant | 8.4 |
| `μ_m` | Model-specific multiplexing factor | **not a profile** | 11, A42 |

M3 produces rows 1-11 and `α`. It does **not** produce `μ_m`: A.5 introduces it in eq. (3) and never
defines, reports or bounds it. That remains M5's open problem (`PROGRESS.md`, "Open (pre-M3)"), and
M3 must not quietly invent a profile field for it.

---

## 2. The provenance discipline (design this before any number)

This is the single most important section of the milestone. Everything else is bookkeeping on top
of it.

### 2.1 The rule

> **No numeric value may exist anywhere in `/optimization/profiles/` unless it is wrapped in a
> `Measured` record carrying a `Provenance` tag and a citation.**

Not "should". Cannot — enforced by construction (`__post_init__`) and by a test that walks every
dataclass field of the assembled `ProfileSet` and fails on any bare `float`/`int` in a numeric field
(§2.5).

### 2.2 The enum

Nine members. The ordering is by decreasing epistemic strength, and the enum is `IntEnum` so that
`min(provenances)` over a derived quantity gives the strength of its weakest input — a derived value
is never stronger than its weakest ingredient.

```python
class Provenance(IntEnum):
    PAPER_TABLE        = 100  # a cell of a numbered table, copied verbatim
    PAPER_TEXT         = 90   # a number stated in prose (e.g. "600 and 1200 tokens in the
                              #   50th and 99th percentile", §3.4 p.575)
    PAPER_FIGURE_LABEL = 85   # a printed axis/tier annotation, not a plotted mark
                              #   (e.g. Figure 8a's "Best >=91.4%")
    PAPER_FIGURE_READ  = 70   # digitized from a plotted mark; carries an uncertainty band
    DERIVED            = 60   # arithmetic over paper values + an explicitly stated assumption
    INTERPOLATED       = 50   # between two anchors, both of which must be recorded
    EXTRAPOLATED       = 40   # outside the anchor range; a model must be named
    EXTERNAL           = 30   # a real non-paper source (vendor price list, spec sheet)
    ASSUMED_ALIAS      = 20   # borrowed wholesale from a *different* profile on the assumption
                              #   that two paper names denote the same thing (A34)
    INVENTED           = 10   # no basis whatsoever
UNAVAILABLE = None            # not a Provenance: the deliberate absence of a value (§2.4)
```

Two deliberate choices in this list:

- **`PAPER_FIGURE_LABEL` is separated from `PAPER_FIGURE_READ`.** Figure 8a's "Best ≥91.4%" is
  *typeset text*, exact to the digit; the bar next to it is pixels. Collapsing them would let an
  exact number inherit a digitization band and vice versa. This distinction turns out to matter a
  lot (§7.3).
- **`ASSUMED_ALIAS` is its own member, not `DERIVED`.** Copying Llama-3.1-70B's Figure 3 curves onto
  `DeepSeek-Llama-70B` is not arithmetic; it is an identity claim about two strings. It deserves to
  be greppable on its own (A34).

### 2.3 Where it is stored

Provenance lives **on the value**, not on the file, the table or the model. A per-file header comment
is not machine-readable and rots the first time a value is moved.

```python
@dataclass(frozen=True)
class Measured(Generic[T]):
    value: T
    unit: str                                   # "tokens", "s", "tokens/s", "kWh/h", "$/GPU-s", ...
    provenance: Provenance
    cite: Citation                              # structured, not a string (§2.6)
    lo: T | None = None                         # inclusive uncertainty band; REQUIRED for
    hi: T | None = None                         #   PAPER_FIGURE_READ and weaker
    anchors: tuple[Anchor, ...] = ()            # REQUIRED for INTERPOLATED / EXTRAPOLATED /
                                                #   DERIVED: the inputs this came from
    assumption: str = ""                        # REQUIRED for DERIVED / EXTRAPOLATED / ALIAS
    note: str = ""

    def __post_init__(self):
        if self.provenance <= Provenance.PAPER_FIGURE_READ and (self.lo is None or self.hi is None):
            raise ProfileProvenanceError(f"{self!r}: values at or below PAPER_FIGURE_READ must "
                                          "carry an uncertainty band")
        if self.provenance in (INTERPOLATED, EXTRAPOLATED, DERIVED) and len(self.anchors) < 1:
            raise ProfileProvenanceError(f"{self!r}: must name its anchors")
        if self.provenance in (DERIVED, EXTRAPOLATED, ASSUMED_ALIAS) and not self.assumption:
            raise ProfileProvenanceError(f"{self!r}: must state its assumption")
        if self.provenance is Provenance.INVENTED and not self.note:
            raise ProfileProvenanceError(f"{self!r}: an invented value must say why it exists")
        if not (self.lo is None or self.lo <= self.value <= self.hi):
            raise ProfileProvenanceError(f"{self!r}: value outside its own band")
```

`Anchor` is `(profile_key, field, Measured)` — a literal back-pointer, so an interpolated value knows
the two numbers it sits between and a reader can re-derive it without reading prose.

### 2.4 `UNAVAILABLE` is a first-class state

The `CLAUDE.md` rule — *"flag the gap instead of quietly extrapolating past what's defensible"* —
needs a representation, or it degenerates into a comment. So a profile field may hold
`Unavailable(reason, cite)` instead of a `Measured`.

```python
@dataclass(frozen=True)
class Unavailable:
    reason: str        # "no Figure 3 panel exists for Llava-OneVision-7B; TTFT is reported
                       #  nowhere in either version for this model"
    cite: Citation     # the place we looked and did not find it
    blocks: tuple[str, ...] = ()   # which MILP expressions become uncomputable, e.g. ("eq5",)
```

Consequences, all intentional:

- **An `Unavailable` is not zero and not a default.** Reading it raises `ProfileUnavailableError`.
- **M4 must therefore handle it, visibly.** A configuration whose `ℓ^TTFT_m` is `Unavailable` cannot
  be evaluated by filter (5). M4 either excludes it (and reports how many configurations were
  excluded for lack of data, not for lack of merit) or the run fails. Either is honest; silently
  substituting 0 is not — and with `ℓ^TTFT_m = 0` the latency filter becomes *more* permissive,
  which would flatter the baseline.
- **`blocks` makes the damage report automatic.** `ProfileSet.coverage_report()` can state "17 of 30
  model profiles cannot be evaluated by eq. (5)" without anyone having to remember.

### 2.5 The test that makes it real

`tests/test_profile_provenance.py`, four assertions:

1. **No naked numbers.** Reflectively walk every field of every dataclass reachable from
   `ProfileSet`. Any `int`/`float`/`tuple[float,...]` not wrapped in `Measured` or `Unavailable`,
   and not in an explicit `STRUCTURAL_FIELDS` allow-list (`D`, `R`, `F`, `tp_degree`, counts and
   indices — knob *settings*, not measurements), fails the test. The allow-list is short, explicit,
   and itself asserted to be unchanged.
2. **Every citation resolves.** Each `Citation` must name a version (`OSDI` | `ARXIV` | `BOTH` |
   `EXTERNAL`), a locus (`table=6`, `figure="2c"`, `section="3.4"`, `page=575`) and must appear in
   `CITATION_REGISTRY`, a hand-checked list of the loci actually used. A typo'd page number fails
   the build, not the reader's trust.
3. **Anchors are reachable and stronger.** For every `INTERPOLATED`/`EXTRAPOLATED`/`DERIVED` value,
   each anchor resolves to a real value in the same `ProfileSet`, and
   `value.provenance <= min(anchor.provenance)`. A derived value may not claim to be stronger than
   what it was derived from.
4. **The ledger matches the data.** `PROFILES.md`'s provenance table (§10) is *generated* from the
   `ProfileSet`, and the test re-generates it and asserts byte-equality with the checked-in file. The
   documentation cannot drift from the numbers.

A fifth, softer test (`test_profile_contradiction.py`) is the direct encoding of the `CLAUDE.md`
rule: for every value that a paper table or figure *label* also reports, assert our value equals it
(exactly for `PAPER_TABLE`/`PAPER_FIGURE_LABEL`; within band for digitized). This is what makes
"never invent a number that contradicts the paper" checkable rather than aspirational.

### 2.6 Citations are structured

```python
@dataclass(frozen=True)
class Citation:
    version: Literal["OSDI", "ARXIV", "BOTH", "EXTERNAL"]
    table: int | None = None
    figure: str | None = None
    section: str | None = None
    page: int | None = None
    quote: str = ""      # the sentence, when the value came from prose
```

`version="BOTH"` is only permitted when the value has been checked in both PDFs and agrees. The
version field is not decoration: §11 lists six places where it differs, and one of them (A46) is the
justification for `t_c` being a p90 at all.

---

## 3. `C_w` — enumerating the configuration set

### 3.1 What a configuration is

A.5 defines `C_w` as, in full, "workflow configurations for `w`". That is the entire definition. It
is an opaque index set; `a_c` and `t_c` are attached per element. §3.3.1 Decision 1 (p.574) says what
varies inside one: "the workflow-level knob settings (*e.g.*, number of frames, STT on/off, debaters
and rounds) for each (workflow, SLO)-pair".

Our enumeration is the cross-product of the knob domains **as implemented in M2/M2b**, with one
collapse and one expansion:

- **Collapse (paper-forced).** The nine Code Gen executors and seven Video Q/A executors that declare
  a `model` knob collapse to **one** workflow-level model, because every A.5 decision variable is
  `x_{w,s,c,m}` with a single `m` and no executor index (M2 DESIGN.md §6.2; M1 gap). This is
  reproduction of a defect, not a simplification: it is why `a_c` can be indexed by configuration
  alone (§5.5).
- **Expansion (ours).** `C_w` for Video Q/A contains DAG variants, not just knob tuples — §3.3.

Tool knobs (`cores`, `timeout_s`, `segment_s`) are **excluded from the cross-product**. They cannot
reach the MILP (M2 A13/A17, M2b A30), so including them would multiply `|C_w|` by 6×3×3 = 54 with
every copy carrying identical `a_c` and `t_c`. Excluding them is [DESIGN CHOICE], recorded because it
is a place where we chose tractability over literalism — the literal reading is that a knob setting
is part of the configuration. The two readings are observationally equivalent to A.5, which is the
justification, and `enumerate_cw(include_dead_knobs=True)` exists so the claim is testable.

### 3.2 Code Generation

Executor assignment is fixed at Phase 1 by the orchestrator (Table 1, p.572: "Executor assignment per
DAG node — Once at onboarding"). The reference DAG is M1's:
`propose_solutions → write_tests → execute_tests → rank_solutions`, with `llm_debate_coders`,
`llm_unit_test_writer`, `python_interpreter`, `llm_ranker`.

Live knobs: `D ∈ {2,4}`, `R ∈ {2,4}` (from `llm_debate_coders`), `model ∈ CODE_GEN_MODELS` (5 ids).

> **|C_codegen| = 2 × 2 × 5 = 20.**

Paper coverage: Figure 2c (p.570) plots accuracy for 4 `(D,R)` × 3 models = **12**; Figure 4b (p.571)
plots all 5 models × 4 `(D,R)` = **20** at coarser precision. So every one of the 20 has an accuracy
source; 12 have a good one.

**A14 is now resolved, by the arXiv version.** M2 left open whether `llm_debate_testers` gives a
second independent `(D,R)` pair, noting that OSDI Table 6's column is headed `Agents`. [ARXIV] Table
5 (arXiv p.17) is the same table with the column headed **`Debaters`**. The column is `D`. We
therefore enumerate exactly one `(D,R)` pair per Code Gen configuration, and record that a DAG in
which the orchestrator selects `llm_debate_testers` is **not representable** in `C_w` — a second
`(D,R)` pair has nowhere to go. Logged as A45.

### 3.3 Video Q/A — and the M3 OBLIGATION

`PROGRESS.md` carries this as an explicit obligation, so it is discharged here in full rather than in
passing.

Q6 (M2b, resolved 2026-09-11) took **Option 5: a configuration IS a DAG variant.** `stt_enabled` is
not a knob anywhere in the Executor Library, because §3.2 (p.572) attaches knobs to "each model or
tool" and an executor cannot own the knob that deletes it (A18/A24). Instead, `C_video` contains both
the with-`stt` and the without-`stt` variants, and the MILP chooses between them through `c`.

**Therefore M3 must prune the `stt` node, and the following two disclosures are mandatory.**

1. **[OURS] The paper describes no pruning step.** §3.3.1 (p.574) names "STT on/off" as a decision
   and Figure 2a (p.570) plots both halves of it, but nowhere does the paper describe deriving a
   second DAG from the first, nor any mechanism that could. `prune_node()` is our invention. It is
   labelled as such in code, in `PROFILES.md`, and here. It is not reproduction.
2. **[OURS] §3.2 (p.573) says the orchestrator produces *a* logical workflow, singular** — "The
   workflow orchestrator transforms a declarative workflow specification into a logical workflow…
   It is represented as a directed acyclic graph (DAG)". Under Option 5, M3 derives a **second** DAG
   from the orchestrator's one, after the orchestrator has finished and without consulting it. The
   phase boundary in Table 1 (p.572) — DAG structure decided "Once at onboarding", workflow knobs
   decided "Per epoch" — is crossed by this step. Disclosed, not repaired.

The pruning rule, stated so it is auditable:

```
prune_stt(dag):
    assert "stt" in dag.nodes
    remove node "stt"
    remove edge scene_detect -> stt
    drop the TaskRef("stt") element from q_a's variadic argument list
    assert dag still type-checks     # valid: q_a's port accepts {Frames, AnnotatedFrames,
                                     # Transcript} and a variadic port accepts a SUBSET
                                     # (M2b DESIGN_VIDEO_QA.md §4.1, §5.2 Option 5)
    assert "stt" is not reachable and no other node consumed it
```

The type-check assertion is not decoration: it is the property that makes Option 5 legal rather than
a hack, and it is pinned by a test (`test_pruned_video_dag_typechecks`).

Live knobs: `STT ∈ {on, off}` (as a DAG variant), `F ∈ {1,5,10}`, `model ∈ VIDEO_QA_MODELS` (4 ids).

> **|C_video| = 2 × 3 × 4 = 24.**

Paper coverage: Figure 2a plots 6 `(F,STT)` × 3 models = **18**. Llama-3.2-90B is absent from Figure
2a but present in Figure 4a's model legend (as "Llama-3.2-90B-Vision", A48), giving its 6 points at
lower precision. So 24/24 covered, 18 well.

> **Total: |C| = 44 workflow configurations.**

### 3.4 A cardinality sanity check that is worth doing

Insight 3 (p.571) claims configuration complexity is
`O(#WorkflowKnobs × #AgentKnobs × #HardwareKnobs)`. Our 44 workflow configurations × the ~30 model
profiles of §6 gives ~1,320 `(c, m)` pairs, against Figure 4a/4b's plotted clouds of roughly 100-200
points each. The reproduction's space is an order of magnitude larger than the paper's plots, because
A.5 places no constraint tying `c` to `m` (M1 gap: "c and m are unlinked"). §5.5 explains what we do
about that, which is: record it, and let M4 measure it.

---

## 4. Schemas

### 4.1 Workflow layer

```python
@dataclass(frozen=True)
class ConfigKey:                       # identifies c in C_w; hashable, stable, is the join key
    workflow_id: str                   # "code_generation" | "video_qa"
    knobs: tuple[tuple[str, Any], ...] # sorted; e.g. (("D",4),("R",4),("model","Gemma-3-27B"))
    dag_variant: str = "default"       # "default" | "no_stt"   <- Option 5 lives here [OURS]

@dataclass(frozen=True)
class TokenDistribution:
    """t_c is NOT a scalar. §4.1 p.576 allocates on the p90; §3.4 p.575 reports p50 and p99;
    Figures 2b/2d ARE distributions (CDFs). A scalar cannot represent any of that."""
    percentiles: Mapping[int, Measured[float]]   # {50: .., 90: .., 99: ..}; 90 is MANDATORY
    mean: Measured[float] | Unavailable
    unit: Literal["completion_tokens"]           # see A39 on why not prompt+completion
    def at(self, p: int) -> Measured[float]: ...
    def p90(self) -> Measured[float]: ...        # what A.5's t_c binds to (§5.3)

@dataclass(frozen=True)
class WorkflowProfile:
    key: ConfigKey
    accuracy: Measured[float]                    # a_c, fraction in [0,1]
    accuracy_benchmark: str                      # "HumanEval" | "VideoMME"  (§3.3 p.573)
    accuracy_measured_on_model: str              # NON-MILP. See §5.5. Never read by M4.
    tokens: TokenDistribution                    # t_c, workflow TOTAL per request
    node_tokens: Mapping[str, TokenDistribution] # per-DAG-node breakdown. NON-MILP; exists
                                                 #   only so the critique of §12.1 is computable.
    node_service_time: Mapping[str, Measured[float] | Unavailable]
                                                 # tool wall-clock. NON-MILP, quarantined (§12.1)
    prompt_tokens: TokenDistribution | Unavailable  # §3.3 requires it; A.5 has nowhere to put
                                                    #   it; the paper plots it only for Math Q/A
```

Three fields are marked NON-MILP. They exist because the paper's *prose* requires them (§3.3 p.573
names prompt tokens; §3.3.1 Decision 2 names per-executor assignment) or because the project's
critiques require them (§12). A test asserts they are absent from the MILP-facing projection:

```python
def test_milp_projection_is_exactly_A5():
    assert set(profile.to_milp().keys()) == {"a_c", "t_c"}
```

### 4.2 Model layer

```python
@dataclass(frozen=True)
class ModelProfileKey:
    model_id: str                       # from shared/model_ids.py — the join key M2 promised
    gpu: Literal["A100", "H100"]        # §4.1 p.575
    tp: int                             # tensor-parallel degree; Figure 3 legend {1,2,4,8}

@dataclass(frozen=True)
class LoadPoint:
    """One point on a Figure 3 curve. §3.3 p.573: 'Profiles span load levels to expose
    trade-offs and guide the optimizer in allocating load and instances.'"""
    throughput: Measured[float]         # tokens/s per instance  -> the x-axis of Figure 3
    ttft_p90: Measured[float] | Unavailable   # s; Figure 3 y-axis is literally "TTFT P90 (s)"
    tpot_p90: Measured[float] | Unavailable   # s; Figure 3 y-axis is literally "TPOT P90 (s)"

@dataclass(frozen=True)
class ModelProfile:
    key: ModelProfileKey
    curve: tuple[LoadPoint, ...]        # ascending in throughput; >=1 point
    parallelism: Measured[int]          # g_m == key.tp  (§3.3.1 Decision 3, p.574)
    energy: Measured[float] | Unavailable   # e_m, kWh per GPU per hour (§6.5 on the unit)
    tps_per_wh: tuple[Measured[float], ...] | Unavailable  # Figure 3 col 3, undefined metric (A41)
    def theta(self, policy: OperatingPointPolicy) -> Measured[float]: ...
    def ttft(self, policy) -> Measured[float] | Unavailable: ...
    def tpot(self, policy) -> Measured[float] | Unavailable: ...

@dataclass(frozen=True)
class ResourceType:                     # g in G
    name: Literal["A100", "H100"]
    cost_per_instance_second: Measured[float] | Unavailable   # c_g  -- see A40
    budget: Measured[int] | Unavailable                       # B_g
```

### 4.3 The assembled set

```python
@dataclass(frozen=True)
class ProfileSet:
    name: str                                       # "baseline" | "paper_only" | "pess" | ...
    workflow: Mapping[ConfigKey, WorkflowProfile]
    models: Mapping[ModelProfileKey, ModelProfile]
    resources: Mapping[str, ResourceType]
    slo: Mapping[tuple[str, str], Measured[float]]  # tau_{w,s}
    arrivals: Mapping[tuple[str, str], ArrivalPattern]
    alpha: Measured[float]                          # 1.15, PAPER_TABLE-equivalent (A.5 p.586)
    def coverage_report(self) -> CoverageReport: ...     # counts by Provenance, per field
    def to_milp_inputs(self) -> MilpInputs: ...          # the ONLY thing M4 may import
```

`to_milp_inputs()` is the enforced boundary. M4 imports `MilpInputs`, never `ProfileSet`. A test
asserts `optimization/milp/` contains no import of `profiles.schema` beyond `MilpInputs`.

---

## 5. Workflow profiles — how `a_c` and `t_c` are derived

### 5.1 Anchors

| Quantity | Primary | Secondary | Validation |
|---|---|---|---|
| Code Gen `a_c` | Figure 2c p.570 (12 pts, `PAPER_FIGURE_READ`) | Figure 4b p.571 (20 pts, coarser) | Figure 8a tier labels p.575 (`PAPER_FIGURE_LABEL`, exact) + Table 6 chosen rows |
| Video `a_c` | Figure 2a p.570 (18 pts) | Figure 4a p.571 (24 pts, incl. Llama-3.2-90B) | Figure 7a tier labels + §2.5 text "66.2%" + Table 5 chosen rows |
| Code Gen `t_c` | Figure 2d p.570 CDFs (12) | §2.5 text p.570: "≈20,000 tokens versus ≈2,500" | — |
| Video `t_c` | Figure 2b p.570 CDFs (18) | §3.4 text p.575: p50=600, p99=1200 for (Llava, F=10, STT=Y) | §2.5 text p.570: "from 250 to nearly 1000" |

### 5.2 `a_c` — worked example, and a validation that the whole method is sound

Digitizing Figure 2c gives (values ±0.5 pp; the band is carried on every one):

| `(D,R)` | DeepSeek-Qwen-32B | Phi-4 | Gemma-3-27B |
|---|---|---|---|
| (2,2) | 81.8 | 66.3 | 86.6 |
| (2,4) | 85.3 | 75.8 | 87.6 |
| (4,2) | 86.5 | 67.0 | 87.0 |
| (4,4) | **91.2** | 67.0 | 88.8 |

Now cross-check against two *independent* parts of the paper:

- Figure 8a (p.575) prints the four Code Gen accuracy tiers: **Best ≥91.4%, Good ≥88.9%, Fair
  ≥87.1%, Basic ≥75.5%**.
- Table 6 (p.586) reports which configuration was chosen at each accuracy tier: Best =
  DeepSeek-Qwen-32B `D=4,R=4`; Good = Gemma-3-27B `4,4`; Fair = Gemma-3-27B `2,4`; Basic = Phi-4
  `2,4`.

Line them up: 91.2 ↔ 91.4 (DSQ 4,4) · 88.8 ↔ 88.9 (Gemma 4,4) · 87.6 ↔ 87.1 (Gemma 2,4) · 75.8 ↔
75.5 (Phi-4 2,4). Four independent agreements, all inside the digitization band. **The bars, the tier
labels and the chosen-configuration table are mutually consistent**, which means (a) the digitization
method is sound, and (b) the four tier values can be promoted from `PAPER_FIGURE_READ` to
`PAPER_FIGURE_LABEL` strength for exactly those four configurations, because the label prints the
number the bar approximates.

**Worked example #1, fully specified:**

```
ConfigKey(code_generation, D=4, R=4, model="Gemma-3-27B")
  accuracy = Measured(
      value=0.889, unit="fraction",
      provenance=PAPER_FIGURE_LABEL,
      cite=Citation(version="BOTH", figure="8a(OSDI)/9a(arXiv)", section="4.2", page=575,
                    quote="Good >=88.9%"),
      lo=0.883, hi=0.893,
      note="Figure 2c bar digitizes to 88.8 +/- 0.5; Table 6 (p.586) reports Gemma-3-27B "
           "D=4,R=4 as the configuration chosen at the Good accuracy tier, so the printed "
           "tier value and this bar denote the same configuration.")
```

The remaining 16 Code Gen and 24 Video configurations get `PAPER_FIGURE_READ` with a ±0.5 pp (Fig 2)
or ±1.5 pp (Fig 4) band. **Zero Code Gen or Video `a_c` values are invented.** This is the strongest
part of the profile set.

### 5.3 `t_c` is a p90, so the profile must carry a distribution

[OSDI] §4.1/4.2 boundary, p.576, verbatim:

> "We assume the 90th percentile token generation load from our profiles when making resource
> allocation decisions for all policies for a fair comparison."

So the scalar `t_c` that eq. (3) and eq. (5) consume is **`t_c = tokens.at(90)`**, not a mean and not
a median. Three consequences, all designed for:

1. **The profile stores the distribution.** `TokenDistribution` with p50/p90/p99 mandatory-where-
   derivable. Collapsing to a scalar at profile-build time would make the p90 assumption
   unrecoverable and would silently destroy the auto-scaler's input — §3.4 (p.575) motivates the
   auto-scaler *entirely* by this variance ("600 and 1200 tokens in the 50th and 99th percentile,
   respectively, highlighting high variance"). M6 needs the tail.
2. **The percentile is a policy, not a constant.** `MilpInputs` is built with
   `TokenPolicy(percentile=90)`, and §3.4 (p.575) explicitly contemplates other settings: "The
   optimizer can be configured to be conservative (*i.e.*, consider the tail percentile and provision
   more resources) or optimistic". Sweeping p50/p90/p99 is therefore a *paper-sanctioned* sensitivity
   axis, not an invention (§9.3).
3. **It is an [OSDI]-only sentence.** No equivalent appears in [ARXIV] (searched; the arXiv §4.1 has
   no percentile statement). The entire p90 convention rests on one sentence present in one version.
   Logged as **A46**.

**Worked example #2:**

```
ConfigKey(video_qa, F=10, model="Llava-OneVision-7B", dag_variant="default")   # STT on
  tokens = TokenDistribution(
    percentiles = {
      50: Measured(600,  "completion_tokens", PAPER_TEXT,
             Citation("BOTH", section="3.4", page=575,
                      quote="a video Q/A workflow with 10 frames and STT on Llava-OneVision-7B "
                            "produces 600 and 1200 tokens in the 50th and 99th percentile"),
             lo=600, hi=600),
      99: Measured(1200, "completion_tokens", PAPER_TEXT, <same cite>, lo=1200, hi=1200),
      90: Measured(1050, "completion_tokens", INTERPOLATED,
             Citation("BOTH", figure="2b", page=570),
             lo=900, hi=1150,
             anchors=(p50@600 [PAPER_TEXT], p99@1200 [PAPER_TEXT],
                      "Figure 2b Llava panel, F=10 STT:Y curve, digitized"),
             assumption="p90 read from the Figure 2b CDF after affine rescaling of the "
                        "digitized curve so that its p50 and p99 match the two PAPER_TEXT "
                        "anchors; the rescale corrects a ~15% systematic digitization offset "
                        "(raw digitized p50 = 700 vs stated 600)."),
    }, ...)
```

Note what this record does: it uses the *exact* prose numbers as calibration anchors and demotes the
shape-only information from the plot to `INTERPOLATED`. The one Video Q/A configuration for which the
paper states percentiles in text is used to calibrate the digitization of all 18 Figure 2b curves — a
single global rescale factor, recorded once as a `DERIVED` calibration constant with its own
provenance, so the correction is visible rather than baked in.

### 5.4 Where `t_c` must be extrapolated, and the model used

Two blocks have no token CDF anywhere in either version:

- **Code Gen on NVLM-D-72B and DeepSeek-Llama-70B** (8 configurations). Figure 2d plots only
  DeepSeek-Qwen-32B, Phi-4, Gemma-3-27B. Figure 16b is Math Q/A, a different workflow.
- **Video Q/A on Llama-3.2-90B** (6 configurations). Figure 2b plots only NVLM-D-72B,
  Llava-OneVision-7B, Gemma-3-27B.

The extrapolation model, stated once and applied uniformly:

```
t_c(model, D, R) = S_model * f(D, R)
  f(D,R) = the per-configuration shape factor fitted on the three models Figure 2d DOES plot,
           normalised to f(2,2)=1.  Digitized medians give f ~ (1.0, 1.55, 2.3, 3.3) for
           (2,2),(2,4),(4,2),(4,4) -- i.e. sublinear in D*R (which would be 1,2,2,4).
  S_model = the model's own token scale at (2,2).  UNAVAILABLE for NVLM-D-72B and
            DeepSeek-Llama-70B in Code Generation.
```

`f` is `DERIVED` (anchored on 12 digitized CDFs, assumption: the shape factor is model-independent —
false in general, and defensible only because the three plotted models agree with each other to
within ~20%). `S_model` **is not derivable**, and this is a genuine `Unavailable`:

> **FLAGGED GAP.** There is no statement anywhere in either version about how many tokens NVLM-D-72B
> or DeepSeek-Llama-70B generates on a Code Generation request. A reasoning model and a
> non-reasoning model of similar size differ by ~8× in this quantity by the paper's own report
> ("≈20,000 tokens versus ≈2,500", §2.5 p.570), so interpolating from parameter count would be
> fiction with an 8× error bar.

**Resolved (Q19, 2026-09-11):** mark these 14 of 44 configurations' `t_c` `Unavailable` in the
`baseline` profile set, so M4 cannot select them and reports them as data-excluded; and provide a
`wide` profile set that populates them as `EXTRAPOLATED` with an explicit ±8× band, for sensitivity
only. The alternative — inventing `S_model` — is precisely what `CLAUDE.md` forbids.

### 5.5 `a_c` depends on the model, and A.5 does not care

Figure 2c is unambiguous: at `D=4,R=4` accuracy is 91.2% on DeepSeek-Qwen-32B and 67.0% on Phi-4.
Accuracy is a property of the *(configuration, model)* pair. But A.5 indexes accuracy as `a_c` —
configuration only — and constrains it in eq. (4)/(8) with no reference to `m`.

**How we handle it, given the standing policy:**

1. `model` is *inside* `ConfigKey.knobs` (§3.1), forced there by the collapse in M2 §6.2. So `a_c` is
   well-defined as a function of `c` alone, and A.5 is satisfiable as written. This is the literal
   reading and we take it.
2. The model is *also* recorded redundantly in `WorkflowProfile.accuracy_measured_on_model`, which
   M4 may not read.
3. **The defect is then measurable rather than argued.** A.5 contains no constraint linking `c` to
   `m` — `x_{w,s,c,m}` is free to route configuration `c=(D=4,R=4,model=Gemma)` onto model profile
   `m=(Phi-4, H100, TP=2)`, claiming Gemma's 88.8% accuracy while paying Phi-4's throughput, latency
   and energy. M3's job is to make that countable: `MilpInputs` carries a
   `coherent(c, m) -> bool` predicate (`c.knobs["model"] == m.model_id`) that the MILP **does not
   use**, and M4 reports "N% of the selected `(c,m)` mass is incoherent". If that number is non-zero
   the paper's formulation is not merely under-specified, it is exploitable — and we will have
   measured it rather than asserted it.

This is the design answer to the brief's "say how you handle that": reproduce the index as written,
carry the truth alongside it, and instrument the difference.

---

## 6. Model profiles

### 6.1 The space

`(model_id, gpu, tp)` over 7 model ids × {A100, H100} × {1,2,4,8} = 56 tuples, of which far fewer are
real. The paper's own coverage defines feasibility:

| Model | TP values with a Figure 3 curve / Figure 4 legend entry | Tuples |
|---|---|---|
| DeepSeek-Qwen-32B | Fig 3: A100 {4,8}, H100 {4,8} | 4 |
| Gemma-3-27B | Fig 3: A100 {4,8}, H100 {4,8} | 4 |
| Phi-4 | Fig 3: A100 {1,2,4,8}, H100 {1,2,4,8} | 8 |
| NVLM-D-72B | Fig 3: A100 {4,8}, H100 {4,8} | 4 |
| Llama-3.1-70B | Fig 3: A100 {8}, H100 {8} | 2 |
| Llava-OneVision-7B | **no Figure 3 panel**; Fig 4a legend {4,8}; Table 5 uses {4} | 4 |
| Llama-3.2-90B(-Vision) | **no Figure 3 panel**; Fig 4a legend {4,8} | 4 |
| DeepSeek-Llama-70B | **no Figure 3 panel**; Fig 4b legend only | 0 or 2 (A34) |

> **≈30 model profiles**, of which **12 distinct tuples are directly reported** in Tables 5/6.

**[DESIGN CHOICE] TP feasibility is taken from the paper's own plotted coverage, not from a memory
calculation.** A 72B model at TP=1 does not fit in 80 GB, which is presumably why Figure 3 omits it —
but we do not re-derive that rule, we read it off the figure. Reason: a memory model is a fifth kind
of invented number, and the paper's coverage already encodes the constraint.

Note the workflow asymmetry (A49): Figure 4b (Code Gen) spans TP ∈ {1,2,4,8}; Figure 4a (Video Q/A)
spans only {4,8}, and Table 5 reports only TP=4 in every row. The paper's own TP domain is
workflow-dependent, which A.5 has no way to express (`g_m` is a property of `m` alone).

### 6.2 Tables 5 and 6 are points on Figure 3's curves — which is the key structural insight

Table 6's DeepSeek-Qwen-32B / A100 / TP=4 row reports `TPOT = 0.0767 s` at `TPS = 653`. Figure 3's
DeepSeek-Qwen-32B / A100 / TP=4 curve (orange circles) passes through ≈(650, 0.08-0.10). Its H100 /
TP=4 row reports `0.0387 @ 1390`; the blue-circle curve passes through ≈(1390, 0.038). The tables are
*samples of the figure*. Two consequences:

1. `θ_m` **is** the `TPS` column and `ℓ^TPOT_m` **is** the `TPOT` column — no conversion, no
   assumption. Twelve `(model, gpu, tp)` tuples get `PAPER_TABLE` throughput and TPOT.
2. The tables also **validate the Figure 3 digitization** at 12 independent points, exactly as the
   tier labels validate the Figure 2 digitization (§5.2). Each validated point is asserted in
   `test_profile_contradiction.py`.

**Worked example #3:**

```
ModelProfileKey("DeepSeek-Qwen-32B", gpu="H100", tp=4)
  curve = (...,
    LoadPoint(
      throughput = Measured(1390, "tokens/s", PAPER_TABLE,
          Citation("BOTH", table=6, page=586,
                   quote="Acc./Energy/Best: DeepSeek-Qwen-32B 4 4 H100 4 0.0387 1390"),
          lo=1390, hi=1390),
      tpot_p90  = Measured(0.0387, "s", PAPER_TABLE, <same>, lo=0.0387, hi=0.0387),
      ttft_p90  = Measured(0.22, "s", PAPER_FIGURE_READ,
          Citation("BOTH", figure="3 (OSDI) / 4 (arXiv)", page=570),
          lo=0.15, hi=0.30,
          note="TTFT is reported in NO table in either version (A36); the only source is the "
               "middle column of Figure 3, read at x=1390 on the H100 TP=4 curve.")),
    ...)
  parallelism = Measured(4, "gpus", PAPER_TABLE, Citation("BOTH", table=6, page=586))
```

Note `tpot_p90`: Figure 3's y-axes are labelled literally **"TPOT P90 (s)"** and **"TTFT P90 (s)"**.
The paper's own latency profiles are p90s. This is a second, independent reason `t_c` should be a p90
(§5.3) — the latency side already is — and it means eq. (5)'s
`ℓ^TTFT_m + t_c · ℓ^TPOT_m` is a p90-of-sum approximated by a sum-of-p90s. Reproduced as-is; flagged.

### 6.3 "Profiles span load levels" versus a MILP whose `θ_m` is a constant

§3.3 (p.573): *"Profiles span load levels to expose trade-offs and guide the optimizer in allocating
load and instances."* Figure 3 realises this: each curve is TPOT/TTFT **as a function of** offered
throughput, and it is sharply non-linear — TPOT is flat then hooks vertically at saturation.

But A.5's `θ_m`, `ℓ^TTFT_m`, `ℓ^TPOT_m` are **scalar parameters**, not functions. Capacity eq. (3)
uses a single `θ_m`; latency filter eq. (5) uses a single `ℓ^TPOT_m`. The load-indexed profile the
paper describes cannot enter the optimizer it describes.

**Representation (ours, explicit):** the profile stores the whole curve (`ModelProfile.curve`), and
collapsing to scalars is a *named, swappable policy* applied at `to_milp_inputs()` time:

| `OperatingPointPolicy` | `θ_m` | `ℓ^TPOT_m` | Rationale |
|---|---|---|---|
| `TABLE_REPORTED` (**default**) | the `TPS` cell | the `TPOT` cell | Tables 5/6 report exactly one operating point per chosen configuration; this reproduces the paper's own selections and is the only policy with `PAPER_TABLE` provenance end-to-end. |
| `KNEE` | throughput at the last point before TPOT exceeds 1.5× its floor | TPOT there | The engineering reading of "expose trade-offs". |
| `MAX_THROUGHPUT` | curve maximum | TPOT there | Most optimistic; minimises `n_m`. |
| `SLO_MATCHED` | largest throughput whose TPOT still satisfies `τ_{w,s}` | that TPOT | Closest to what §3.3's prose describes the optimizer doing; **circular**, because `τ` derivation (§7) depends on profiles. Provided, off by default, circularity documented. |

The default matters enormously: `MAX_THROUGHPUT` vs `TABLE_REPORTED` differs by ~4× on Llava
(479 → 3271 tokens/s, Table 5's own rows), which would change `n_m` — and hence every headline GPU
count — by the same factor. This is the single largest sensitivity knob in the whole profile set and
is therefore swept first (§9.3).

**The observation that makes the policy defensible.** Table 5 reports Llava-OneVision-7B / H100 /
TP=4 at *three* different operating points across SLO tiers — `0.0044 s @ 479`, `0.0070 s @ 2836`,
`0.0079 s @ 3271` — and Table 6 reports Phi-4 / H100 / TP=2 at two (`0.0169 @ 1036`,
`0.0218 @ 1185`). So Murakkab evidently *does* pick a per-(workflow, SLO) operating point on the
curve, exactly as A.2 says ("increases the allowed load per model instance to increase batching as
the SLO is relaxed"). **A.5 has no variable for that choice.** It is a fifth decision the system makes
and the formulation cannot express — a new instance of `PROGRESS.md`'s PATTERN, logged as **A37b**
and, in my judgement, the cleanest one yet, because the evidence is two of the paper's own tables
disagreeing with its own appendix. **Resolved (Q20, 2026-09-11): `M` stays `(model, gpu, tp)`; the distinction is lost, deliberately.**
Re-indexing `M` by operating point would be repairing A.5, and the standing policy is to reproduce it
as written. Concretely:

- `TABLE_REPORTED` collapses the 2-3 table rows for a tuple to **one** `(θ_m, ℓ^TPOT_m)` pair: the
  operating point appearing in the most Table 5/6 rows for that tuple.
- **Ties break toward the higher `θ_m`** — i.e. toward the baseline's advantage. A low `θ_m` inflates
  `n_m`, inflates Murakkab's GPU count, and would flatter our comparison system for free; biasing the
  other way makes every GPU-count gap we later report a *lower* bound on Murakkab's disadvantage.
  This tie-break is recorded on the profile, not buried in the policy.
- The discarded per-tier points stay in `ModelProfile.curve` with full provenance, and a
  `PER_TIER_OPERATING_POINT` policy that preserves them ships **off by default**, marked as a repair.
  It is unusable by M4 without a wider `M`; it exists so the magnitude of the loss is measurable.
- Every collapse is logged in `CoverageReport.operating_point_collapse` with the rows dropped and the
  `θ_m` ratio between them, since that ratio reaches ~4× on Llava.

### 6.4 `g_m` — parallelism

`g_m = tp`. §3.3.1 Decision 3 (p.574): "A profile encodes a specific model, GPU type, and parallelism
strategy, so choosing `m` implicitly fixes the hardware and parallelism degree." `PAPER_TABLE` where
a Table 5/6 row gives it; `PAPER_FIGURE_LABEL` from the Figure 3/4 legends otherwise. Zero
uncertainty — it is an integer the paper prints.

Unit check against eq. (7), `Σ_{m:GPU(m)=g} n_m · g_m ≤ B_g`: `n_m` counts *instances*, `g_m` counts
GPUs per instance, so `B_g` counts GPUs. Consistent with §4.5's "2,000 A100 GPUs" and Table 3's
"Allocated A100s". Recorded so M4 does not have to re-derive it.

### 6.5 `e_m` — energy, and the derivation with its assumption exposed

A.5 says `e_m`: "Energy consumption (kWh) for model profile `m`". Objective (11) is
`min Σ_m n_m e_m g_m` — instances × per-GPU energy × GPUs-per-instance. For that to be an energy
rather than a rate, `e_m` must be kWh **per GPU per unit time**, and the natural unit is the
optimization epoch (60 min, §3.4 p.575). We store kWh/GPU-hour and say so in `unit`.

The paper never prints `e_m`. Two candidate derivations:

**(a) From Table 3 (rejected as primary, used as a check).** Row 1: 1292 A100s, 24.7 MWh over 24 h →
`24700 / (1292 × 24) = 0.797 kW/A100`. Row 6: 495 H100s, 11.0 MWh → `0.926 kW/H100`. Assumption: the
allocation was constant across the 24 h. It was not — Figure 11 (p.578) shows instance counts moving
every epoch — so these are averages over a varying denominator. But the magnitudes are sane (A100
SXM TDP 400 W, H100 700 W; at VM level, 8 GPUs + host ≈ 800 W and ≈ 1 kW per GPU respectively), and
the ratio 1.16 is the right shape to explain "Murakkab prefers using H100 GPUs when minimizing
energy" (§4.2 p.576) given Figure 3's ~2× better TPS/Wh on H100.

**(b) From Figure 3's third column (rejected outright).** The axis is labelled "TPS per Wh" with no
definition anywhere in either version. No dimensional reading of it reproduces a plausible device
power: at the DeepSeek-Qwen-32B H100 TP=4 peak (~65 "TPS per Wh" at ~1390 TPS) the implied quantity
is 21.4 Wh, which is neither a power nor an energy-per-token. Logged as **A41**; the raw digitized
series is stored in `tps_per_wh` as an uninterpreted `PAPER_FIGURE_READ` array, with a comment that
it must not be converted until the metric is defined.

**Decision:** `e_m` is `DERIVED` per GPU **type**, not per model profile, from (a), with the
constant-allocation assumption in `assumption` and a ±25% band. Its provenance is capped at
`DERIVED`, and the per-model variation A.5's subscript implies is `Unavailable`. Stated plainly:
**our `e_m` cannot distinguish two models on the same GPU.** Objective (11) therefore degenerates to
"minimize GPU-hours weighted by GPU type" in our reproduction. That is a real fidelity loss and it is
declared here, not discovered at M4.

### 6.6 `c_g` — the cost the paper never reports

**FLAGGED GAP (A40).** `c_g`, "Cost per instance per second for resource type `g`", appears in
objective (12), constraint (6)/(10), and drives every dollar figure in the evaluation. **Neither
version states it.** It is not derivable from Table 2/Table 3 either: dividing cost by
(GPUs × hours) gives $3.43/GPU-h for the LangGraph row of Table 2 but $2.05/GPU-h for the Mkb Opt row
of the same table, because Murakkab's allocation varies across the 24 h while the cost integrates it.
The numbers are mutually inconsistent under any constant `c_g`, which is itself evidence that no
single `c_g` can be recovered.

**Resolved (Q18, 2026-09-11):**

- `c_g` is `EXTERNAL` provenance, sourced from Azure published list prices for the exact VM shapes
  §4.1 (p.575) names (ND A100 v4, ND H100 v5), divided by 8 GPUs, with the retrieval date recorded.
- A consistency check, reported not enforced: the external price **ratio** H100:A100 ≈ 3.6 is close
  to the 3.53 implied by Table 3 rows 1 and 6 under the constant-allocation assumption. That
  agreement is worth reporting and is not strong enough to promote the provenance.
- `c_g` is swept ±50% in every sensitivity run, because it is `EXTERNAL` and because cost is one of
  the three objectives.

If Arno prefers, `c_g` can instead be `Unavailable`, which makes objectives (12) and (13) and
constraint (6) inoperable and reduces M4 to the energy objective only. That is the maximally honest
option and it costs two thirds of the evaluation. Recommendation: `EXTERNAL`, swept.

---

## 7. SLO tiers — `τ_{w,s}` is derived, not given

### 7.1 The rule

§3.4 (p.575), verbatim and identical in both versions:

> "We assign four SLO tiers for quality and end-to-end latency: *best*, *good*, *fair*, and *basic*.
> The SLO tiers correspond to the best, 95th, 80th, and 50th percentile values of accuracy and
> latency available among the set of all workflow, model, and hardware configurations."

Read carefully, because three separate words in it are load-bearing:

- `best` is the **maximum**, not the 99th percentile; `good`/`fair`/`basic` are p95 / p80 / p50.
- The population is "all workflow, model, **and hardware** configurations" — so the hardware
  expansion is in the sentence. (§7.3 shows it makes **no difference** to the result, which is a
  better outcome than it being load-bearing; see there.)
- **"available among the set of"** fixes the percentile convention. With a discrete configuration
  set, an interpolated percentile is a value *no configuration achieves* — the platform would be
  offering an SLO tier nothing can meet. The tier must be a MEMBER of the population, i.e. the
  `lower` (floor-index) convention: the largest profiled value at or below the percentile position.
  This is not a stylistic choice between numpy interpolation modes; it is what makes a tier
  satisfiable. §7.3 shows it is also the only convention that reproduces the paper's own numbers.

### 7.2 The sequencing this forces

```
1. enumerate C_w                       (needs M2/M2b knob domains)          <- §3
2. enumerate model profiles            (needs Figure 3 / Tables 5,6)        <- §6
3. cross to (c, m) pairs, expand by hardware
4. a_{c}       for every pair          -> accuracy population
   lat(c,m) = TTFT_m + t_c * TPOT_m    -> latency population   (eq. 5's own expression)
5. tau_{w, accuracy_tier} = {max, p95, p80, p50} of the accuracy population
   tau_{w, latency_tier}  = {min, p5,  p20, p50} of the latency population   [orientation flipped]
6. ONLY NOW is the MILP formulable.
```

Three consequences, all of which must be stated because they are counter-intuitive:

- **`τ` is an output of profiling, not an input to it.** A `ProfileSet` is not complete until its own
  tiers have been computed from itself. `slo_tiers.py` runs last and the dataclass is built in two
  passes (`ProfileSet.without_tiers()` → `derive_tiers()` → `ProfileSet`). A test asserts no tier
  value is reachable during profile construction.
- **Adding a model, a workflow, or a GPU type shifts every tier.** Onboarding Math Q/A, or admitting
  `DeepSeek-Llama-70B`, moves p50 and therefore changes what "basic" means for *Video Q/A*, a
  workflow that was not touched. Under §3.4's rule this is not a bug — it is what the rule says. It
  does mean tier values are **not comparable across profile sets**, so every reported result must be
  tagged with the set that produced it. `CoverageReport` carries the tier vector for exactly this
  reason.
- **The orientation flip for latency is ours.** The sentence says "the best, 95th, 80th, and 50th
  percentile values of accuracy *and latency*" using one phrasing for two quantities with opposite
  polarity. For latency, lower is better, so `best` = min and `good` = p5 (not p95). We take the
  charitable reading; the literal one would make `basic` latency *stricter* than `good`. Logged as
  **A38b** — a paper wording defect, repaired only in the sense that the literal reading is
  self-contradictory.

### 7.3 Does the rule reproduce the paper's own tier values? — yes, on both workflows

The paper prints its tiers, so the derivation is checkable. This is the best available validation of
the entire profile set. **It was re-run against the digitized data during the build, and an error in
this section's original claim was found and corrected (2026-09-12).**

**The result.** Taking the percentile as `lower` (§7.1) over the per-configuration accuracy
population:

| Workflow | | best | good | fair | basic |
|---|---|---|---|---|---|
| Code Generation | printed (Fig 8a p.575) | 91.4 | 88.9 | 87.1 | 75.5 |
| | reconstructed | 91.61 | 89.23 | 87.32 | 75.77 |
| | residual (pp) | +0.21 | +0.33 | +0.22 | +0.27 |
| Video Q/A | printed (Fig 7a p.575) | 66.2 | 64.4 | 61.4 | 54.9 |
| | reconstructed | 66.49 | 64.70 | 61.37 | 54.82 |
| | residual (pp) | +0.29 | +0.30 | -0.03 | -0.08 |

All eight land inside the ±0.5 pp digitization band. The four Code Gen residuals are near-identical
(+0.26 ± 0.06 pp), which is the bar-edge bias `figures_digitized.BAR_EDGE_BIAS_PP` independently
measured — i.e. the residual is explained, not merely small.

**What the original version of this section got wrong.** It claimed the tiers reproduce "only under
the hardware-expanded, feasibility-weighted population", with Phi-4 weighted 2x for having eight
(GPU, TP) tuples, and reported `basic` = 75.8. Two things were wrong:

1. Phi-4 has **four** Figure 3 tuples, not eight — the panel plots only diamonds (TP=1) and
   triangles (TP=2), corroborated by every Phi-4 row in Table 6 being TP=1 or TP=2 (**A53**).
2. The reconstruction was being run with **linear-interpolation** percentiles. That, not the
   weighting, was the whole discrepancy.

**The correction strengthens the result in three ways**, which is why it is worth stating at length:

- **The hardware expansion is a no-op — but only because the coverage is uniform.** Under `lower`,
  the flat 16-configuration population and the 64-element hardware-expanded population give
  *identical* Code Gen tiers, because Figure 3 covers exactly four (GPU, TP) tuples for each of the
  four models that have accuracy data, so every member is multiplied by the same factor. **A38
  dissolves** in the sense that the feasibility table need not be known — only uniform.
  **But A53 is load-bearing, in the opposite direction from robustness:** had Phi-4 carried the
  eight tuples DESIGN.md §6.1 asserted, its four low accuracies (66–76%) would be weighted 2× every
  other model and the reconstruction would FAIL (`basic` −2.87 pp, `fair` −0.37 pp). Verifying the
  marker shapes in the PDF was therefore necessary to the result, not a detail. Pinned by
  `test_a53_is_load_bearing_the_wrong_phi4_coverage_would_break_the_reconstruction`.
- **NVLM-D-72B's Figure 4b readings are REQUIRED.** Over the three Figure 2c models alone, `basic`
  computes to 85.54 against a printed 75.5 — off by +10.04. Adding NVLM's four values fixes it
  exactly. The decision to read a fourth model off Figure 4b is therefore validated by the paper's
  own printed tier, not merely by convenience.
- **DeepSeek-Llama-70B must be EXCLUDED.** Admitting it (aliased to `Llama-3.1-70B`, four copies of
  the single 81.86 marker) breaks `fair` to -0.37 and `basic` to +6.36. This independently
  corroborates **Q13** (treat as distinct; disabled in `baseline`) and **A54** (its per-(D,R)
  accuracies are unreadable) — two decisions taken for unrelated reasons that the tier
  reconstruction now confirms.

Pinned by `tests/test_slo_tiers.py`, which asserts all eight residuals and the flat/expanded
equivalence. If a future profile-set change breaks the reconstruction, that test fails loudly —
which is the point of deriving tiers rather than hardcoding them.

### 7.4 And a contradiction in the latency tiers that the profiles expose

Running step 4 of §7.2 on the paper's own chosen configuration produces a result the paper's own
figures contradict.

Table 5's latency-tier `Best` row is Llava-OneVision-7B, `F=1`, STT `Y`, H100, TP=4, `TPOT = 0.0044
s`. Figure 7b prints the `Best` latency tier as **≤0.5 s**. Apply eq. (5):

```
TTFT + t_c * TPOT  <=  0.5
  TTFT (Fig 3 floor, any model/hw)   >~ 0.2 s
  t_c  (Fig 2b, Llava F=1 STT:Y, p90) ~ 400 tokens   [p50 ~ 200]
  =>   0.2 + 400 * 0.0044  =  1.96 s   >>  0.5 s
  even at p50:  0.2 + 200 * 0.0044 = 1.08 s > 0.5 s
  the tier is satisfiable only if t_c <~ 68 tokens.
```

Independently, Figure 4a's own latency axis (p.571) — "a subset of knobs and metrics" for Video Q/A —
has its **leftmost plotted point at ≈1.0 s**. If `best` is "the best value available among the set of
all configurations" (§3.4), it should equal that minimum, i.e. ≈1.0 s, not 0.5 s. The same pattern
appears in Code Generation: Figure 9a/8b prints `Best ≤11.3 s` while Figure 4b's leftmost point is
≈20 s. Both are off by a factor of ≈2 in the same direction, which suggests a systematic definitional
difference (e.g. Figure 4's latency includes something eq. (5)'s does not) rather than a typo.

**We do not repair this.** `τ_{w,s}` is taken from the printed Figure 7/8 labels (`PAPER_FIGURE_LABEL`,
the strongest available provenance), and the derived-from-our-space values are computed alongside and
stored in `CoverageReport.tier_reconstruction`. M4 will therefore find that, under the paper's own
τ and the paper's own Table 5 configuration, filter (5) rejects the configuration Table 5 says
Murakkab chose. That is a reportable result about the paper, obtained by doing the reproduction
honestly, and it is exactly what this repo exists to surface. Logged as **A37**.

**Resolved (Q14, 2026-09-11): the printed labels stand as `baseline`.** The derived tiers are built
and shipped as the `derived_tiers` profile set for contrast, but they are not the default. The
consequence is deliberate and must be carried into M4's expectations: the latency-SLO run is
predicted to reject Table 5's own chosen configuration, and M4 is forbidden from resolving that by
loosening `τ`. If M4 comes back latency-feasible everywhere, that is evidence of an error in our
profiles or in eq. (5)'s implementation, not of the contradiction having gone away.

---

## 8. Arrival patterns, budgets, and constants

### 8.1 Source

§4.1 (p.576) and A.4 (p.586): "a subset of LLM serving traces released by Azure [78] from 08:00
05/15/2024 to 08:00 05/16/2024 shown in Figure 19", mapping "the *chat* requests from the trace to
the *video Q/A* workflow and *coding* requests to the *code generation* workflow".

Figure 19 (p.587) plots two series, `Chat` and `Coding`, in **req/min** over 24 h. Digitized at
hourly resolution: chat runs ≈2,900-4,400 with a morning peak near h6 and a trough near h14; coding
runs ≈700 overnight, peaks ≈5,000 at h11-12, and decays to ≈800 by h23. Both series are stored as a
24-point hourly array with a ±150 req/min band (`PAPER_FIGURE_READ`).

**[DESIGN CHOICE]** The underlying Azure trace is a public dataset. We do **not** attempt to
reproduce it from the source, because (a) we cannot verify that we selected the same 24-hour subset
or the same request filtering, and (b) a wrong-but-real trace is more dangerous than a digitized one,
since it would carry unearned authority. The loader is written against a `TraceSource` interface with
`DigitizedFigure19` as the default and `AzurePublicDataset(path)` as a drop-in, so the substitution
is one line if Arno obtains and validates the file. That is itself a sensitivity axis.

### 8.2 From a trace to `λ^peak` and `λ^avg`

A.5 needs one `(λ^peak, λ^avg)` pair per `(workflow, SLO)` per optimization **epoch** (60 min, §3.4
p.575), not per day.

```
for each hour h in 0..23:                      # one epoch, per §3.4
    for w, series in {video_qa: chat, code_generation: coding}:
        lam_avg_w  = mean(series within h)          # req/min -> req/s
        lam_peak_w = max(series within h)           # the tail *within* the epoch
        for s in SLO_TIERS:
            lam_avg[w,s]  = lam_avg_w  * share[s]
            lam_peak[w,s] = lam_peak_w * share[s]
```

Two honest caveats, both recorded on the values:

- At hourly digitization we have **one sample per epoch**, so `max` within an epoch is not recoverable
  and `λ^peak = λ^avg` degenerately. Fix: the digitized series is stored at the finer resolution the
  figure actually supports (the plotted line is visibly noisy at ~1-2 min granularity, but legibly so
  only in envelope), so `λ^peak` is taken as the digitized **upper envelope** of the hour and `λ^avg`
  as the digitized **centre line**, with the envelope width carried as the band. The resulting
  peak/avg ratio is ≈1.15-1.3, which is worth noting against A.5's own buffer factor `α = 1.15`.
- Nothing in either version states the peak/average ratio, so this is `PAPER_FIGURE_READ` with a wide
  band, and it directly scales `n_m` through eq. (3). Sensitivity axis.

### 8.3 SLO tier shares, and `B_g`

§4.3 (p.576): "we run video Q/A and code generation requests together and assign **70% requests to be
high-accuracy and 30% requests to low-latency, both with *good* tier**".

So the main multi-workflow experiment uses **two** of the eight `(SLO type, tier)` combinations:
`(accuracy, good)` at 0.70 and `(latency, good)` at 0.30. All other tiers carry zero arrival rate.
§4.2's single-workflow experiments instead "assume that all requests have the same SLO for each
experiment" — i.e. eight separate runs with share 1.0 on one combination. Both shapes are needed:

```python
SloMix.SECTION_4_3  = {("accuracy","good"): 0.70, ("latency","good"): 0.30}   # PAPER_TEXT
SloMix.SECTION_4_2(slo_type, tier) = {(slo_type, tier): 1.0}                  # PAPER_TEXT
SloMix.UNIFORM      = {each of 8: 0.125}                                       # [INVENTED], sweep only
```

`B_g`: stated only for §4.5's sweep — "the cluster always provides 2,000 A100 GPUs, while the number
of H100 GPUs varies from 0 to 500, increasing by 100" (p.578, Table 3). §4.2/§4.3 state no budget;
the natural reading is unconstrained. So `B_g` is `PAPER_TEXT` for the six §4.5 settings and
`Unavailable` (meaning: constraint (7) inactive) otherwise. Do not invent a budget for §4.2/4.3.

### 8.4 `α`

`α = 1.15`, "Unified buffer factor (default 1.15)", A.5 p.586, identical in both versions.
`PAPER_TABLE`-strength (it is a printed parameter value), zero band.

---

## 9. Sensitivity analysis — designed in, not bolted on

The threat: *"Murakkab provisions X% more GPUs than my system"* is a statement about our
interpolation unless it survives a different plausible profile set. Three mechanisms.

### 9.1 Profile sets are values, and M4 takes one as an argument

`MilpInputs` is constructed from a named `ProfileSet`; nothing in `/optimization/milp/` may import a
concrete profile module. A test asserts it. Swapping the profile set is therefore a parameter, not a
refactor, and no result can be produced without recording which set produced it
(`MilpResult.profile_set_name` is mandatory and non-defaulted).

### 9.2 Named sets, shipped from day one

| Set | Construction | Purpose |
|---|---|---|
| `paper_only` | every value with provenance weaker than `DERIVED` becomes `Unavailable`; `C_w` restricted to configurations the paper actually reports | the floor. Whatever survives here is *not* an artifact of our reconstruction. Small and full of holes — that is the point. |
| `baseline` | the set §5-§8 describe; `TABLE_REPORTED` operating points, p90 tokens, external `c_g` | the headline set |
| `wide` | `baseline` + the 14 extrapolated `t_c` values of §5.4 populated with ±8× bands | coverage over correctness |
| `pessimistic` / `optimistic` | every `Measured` replaced by its `hi` / `lo` in the direction that *worsens* / *improves* Murakkab's objective | the deterministic corner cases; cheap and surprisingly informative |
| `derived_tiers` | `baseline` but `τ` computed from our own space (§7.3) instead of the printed labels | isolates A37 |
| `maxthroughput` | `baseline` with `OperatingPointPolicy.MAX_THROUGHPUT` | isolates the §6.3 fork, the largest single lever |

### 9.3 Monte-Carlo over the bands

```
for trial in 1..N:                       # N = 200, seeded, reproducible
    S' = baseline.resample(rng)          # every Measured with provenance <= PAPER_FIGURE_READ
                                         #   is redrawn uniformly from [lo, hi]; PAPER_TABLE and
                                         #   PAPER_FIGURE_LABEL values are NEVER perturbed
    run M4 on S'
report: fraction of trials in which the qualitative conclusion holds,
        and the interquartile range of every headline number
```

The invariant that makes this meaningful: **paper-reported values are frozen across all trials.** The
Monte-Carlo measures our uncertainty, not the paper's. `resample()` asserts this by provenance level,
and the assertion is tested.

The axes expected to dominate, ranked by prior: (1) the operating-point policy (~4× on `θ_m`, §6.3);
(2) `t_c` percentile p50/p90/p99 (~2× on video, ~2.5× on code gen); (3) `c_g` (±50%, linear in the
cost objective); (4) `e_m`'s constant-allocation assumption (±25%); (5) accuracy digitization (±0.5
pp — small, but it can flip tier membership near a threshold, which is discontinuous).

Deliverable wording for the final comparison: *"Murakkab provisions X% more GPUs (IQR X_lo-X_hi over
200 profile resamples; conclusion holds in K of 200 trials and in the `paper_only`, `pessimistic` and
`maxthroughput` sets)"*. If a conclusion holds only in `baseline`, it is not a conclusion.

---

## 10. `PROFILES.md`

`CLAUDE.md` names this file as where profile provenance is documented. **Recommended location:
repository root**, beside `PROGRESS.md` — it is a cross-cutting ledger that M4-M7 and the final
write-up all consult, not an internal note of one package (resolved Q15; the alternative is
`/optimization/profiles/PROFILES.md`).

It is **generated**, never hand-written (§2.5, test 4), and contains:

1. **The provenance ledger** — one row per value: profile key, field, value, unit, provenance,
   citation, band, and, for derived values, the anchors and the assumption. This is the whole point
   of the file; it is long, and it should be.
2. **The coverage summary** — counts and percentages by provenance, per field, per workflow
   (§13's table, regenerated).
3. **The `Unavailable` register** — every gap, its reason, its citation, and which MILP expression it
   blocks. A reader must be able to answer "what does this reproduction not know?" in one place.
4. **The paper-version concordance** (§11.1) and the discrepancy list (A44-A48).
5. **The validation results** — the §5.2 accuracy cross-check, the §6.2 Table-vs-Figure-3 check, and
   the §7.3 tier reconstruction, each with its residual. These are the evidence that the digitization
   is sound.
6. **The named profile sets** and what each is for (§9.2).
7. **A one-paragraph honesty preamble**, aimed at a reader who quotes a number out of this repo
   without reading further.

---

## 11. Ambiguities, deviations, inventions, and version discrepancies (continuing at A34)

### 11.1 Version concordance (needed to read any citation)

| [OSDI] | [ARXIV] | Content |
|---|---|---|
| Figure 2 (p.570) | Figure 3 (p.4) | workflow accuracy + token CDFs |
| Figure 3 (p.570) | Figure 4 (p.4) | model performance vs hardware/parallelism |
| Figure 4 (p.571) | Figure 5 (p.5) | configuration space vs latency/cost/energy |
| Figure 7 / 8 (p.575) | Figure 8 / 9 (p.8) | per-SLO configuration results + tier labels |
| Table 2 (p.576) | Table 1 (p.9) | policy comparison, 24 h |
| Table 3 (p.578) | Table 2 (p.9) | resource-constrained sweep |
| Table 4 (p.585) | Table 3 (p.16) | Math Q/A policy comparison |
| **Table 5** (p.585) | **Table 4** (p.16) | Video Q/A chosen configurations |
| **Table 6** (p.586) | **Table 5** (p.17) | Code Gen chosen configurations |
| Figure 19 (p.587) | Figure 18 (p.18) | Azure traces |

### 11.2 The list

| # | Item | Nature |
|---|---|---|
| A34 | **`DeepSeek-Llama-70B` and `Llama-3.1-70B` are different strings for a 70B model, and only one of them is profiled.** Figure 4b's Code Gen legend names `DeepSeek-Llama-70B`; Figure 3's model-profile panels name `Llama-3.1-70B`; Figure 10 (p.577) also uses `Llama-3.1-70B`. So the id M2 put in `CODE_GEN_MODELS` has accuracy data and **no** throughput/TTFT/TPOT data, while the id with model profiles is in no workflow's model domain. | Naming gap with real consequences — resolved Q13 (kept distinct) |
| A35 | **`Llava-OneVision-7B` and `Llama-3.2-90B` have no Figure 3 panel.** Their only performance data is Table 5's `TPOT`/`TPS` cells at TP=4. Llava is the model Table 5 chooses for **every** latency-SLO row, so the workflow whose SLO is latency is the one with the thinnest model profile. | Coverage gap |
| A36 | **TTFT is tabulated nowhere in either version.** Tables 5/6 report `TPOT` and `TPS` only. Every `ℓ^TTFT_m` in this reproduction is digitized from Figure 3's middle column, or `Unavailable` (A35). `ℓ^TTFT_m` appears in the only latency expression the optimizer has, eq. (5)/(9). | Provenance gap on a load-bearing parameter |
| A37 | **The printed latency tiers are unreachable under the paper's own eq. (5) and its own chosen configuration.** `Best ≤0.5 s` (Fig 7b) vs `0.2 + 400×0.0044 ≈ 1.96 s` for Table 5's own `Best` row; Figure 4a's minimum plotted latency is ≈1.0 s. Same shape in Code Gen (11.3 s vs ≈20 s), same ≈2× direction. | Internal inconsistency — §7.4; resolved Q14 (printed labels kept) |
| A37b | **Tables 5 and 6 report the same `(model, GPU, TP)` at two or three different `(TPOT, TPS)` operating points across SLO tiers**, and A.2 (p.585) says so explicitly ("increases the allowed load per model instance to increase batching as the SLO is relaxed") — but A.5 has no variable for the operating point; `θ_m` and `ℓ^TPOT_m` are constants of `m`. A sixth decision the system makes and the formulation cannot express. | New PATTERN instance — §6.3; resolved Q20 (`M` not re-indexed) |
| A38 | ~~The SLO tier rule reproduces the paper's Code Gen tiers only over a hardware-expanded, TP-feasibility-weighted population.~~ **WITHDRAWN 2026-09-12.** Re-run against the digitized data, the tiers reproduce on BOTH workflows (8/8 residuals within ±0.5 pp) under the `lower` percentile convention, and the flat and hardware-expanded populations give identical results. The original discrepancy was linear-interpolation percentiles in our reconstruction, not an unstated assumption in the paper. No feasibility table is needed. | Withdrawn — §7.3 |
| A53 | **Phi-4 has FOUR Figure 3 (GPU, TP) tuples, not eight.** DESIGN.md §6.1 asserted A100 {1,2,4,8} x H100 {1,2,4,8}; the panel plots only diamonds (TP=1) and triangles (TP=2), verified at 22x. Corroborated by Table 6 (p.586), where every Phi-4 row is TP=1 or TP=2. Figure 3 therefore covers 18 tuples, not 22. | Design-doc error, PDF wins — `figure_labels.FIGURE_3_COVERAGE` |
| A54 | **Figure 4b plots exactly ONE `DeepSeek-Llama-70B` marker**, not the 4 (D,R) x 8 (GPU,TP) its legend implies. Three of its four (D,R) configurations have no accuracy reading in either version, and the fourth cannot be attributed to a specific (D,R). All four `a_c` values are `Unavailable`. Independently corroborated by §7.3: admitting the model breaks two of the four printed tiers. | Coverage gap — contradicts §3.2's "20/20 covered" claim |
| A55 | **`Llama-3.2-90B` is separable at only three accuracy levels in Figure 4a**, and even those give F (marker size) without STT (hatching, below resolution at 1.3 pp marker height). All six `a_c` values are `Unavailable`. | Coverage gap |
| A56 | **The Figure 2b tail disagrees with §3.4's prose.** §3.4 (p.575) states 600 and 1200 tokens at p50/p99 for Llava-OneVision-7B, F=10, STT on; the digitized curve reads p50 ≈ 585 (-2.5%) but p99 ≈ 1400 (+17%). No single affine rescale fixes both, so the discrepancy is in the TAIL — which is exactly where `t_c`'s p90 lives. | Digitization vs prose conflict |
| A57 | **`c_g` is per GPU, not per instance, despite A.5 naming it "Cost per instance per second".** eqs. (6) and (12) (p.587) both multiply it by `g_m`; eq. (11) does the same to `e_m`. The parameter's name contradicts its own use. Same defect in `B_g`, described as "Maximum available resource *instances*" while eq. (7) writes `Σ n_m·g_m ≤ B_g` — GPUs, as §4.5's "2,000 A100 GPUs" confirms. | Unit defect, resolved by following the equations |
| A58 | **A.5 states four of its constraints twice.** eq. (4) ≡ eq. (8) (accuracy filter) and eq. (5) ≡ eq. (9) (latency filter), verbatim; eq. (6) ≡ eq. (10) (cost budget), differing only in inlining `Cost_budget`. The appendix's 13 numbered equations are 10 distinct ones. | Editorial defect in the formulation |
| A38b | **"the best, 95th, 80th, and 50th percentile values of accuracy and latency"** applies one polarity to two quantities with opposite polarity. Read literally, `basic` latency is stricter than `good`. We flip the orientation for latency. | Wording defect; charitable reading taken |
| A39 | **`t_c`'s unit is ambiguous, and prompt tokens have nowhere to go.** §3.3 (p.573) says workflow profiles capture "prompt **and** completion tokens". A.5 has one parameter, `t_c`, used both against `θ_m` (an output-token throughput, Figure 3's x-axis) and against `ℓ^TPOT_m` (time per *output* token). Only the completion reading is dimensionally consistent — so prefill load is absent from the capacity constraint entirely. Worse: the only prompt-token figure in the paper is Figure 16c, which is **Math Q/A**; no prompt-token data exists for either of our workflows. | Formulation gap + data gap |
| A40 | **`c_g` is reported nowhere and is not derivable.** Table 2's rows imply $3.43 and $2.05 per GPU-hour for the same cluster; the inconsistency is structural (varying allocation vs integrated cost). Every dollar figure in the reproduction rests on an external price list. | Hard gap — §6.6; resolved Q18 (`EXTERNAL`, swept ±50%) |
| A41 | **Figure 3's "TPS per Wh" is undefined** in both versions, and no dimensional reading yields a plausible device power. It is therefore not usable as a source for `e_m`; `e_m` is derived from Table 3 instead, per GPU *type*, so our objective (11) cannot distinguish two models on the same GPU. | Undefined metric; declared fidelity loss |
| A42 | **`μ_m` is not a profile and M3 does not supply it.** A.5 introduces the multiplexing factor in eq. (3) and never defines, bounds or reports it. It is not in §3.3's list of what profiles contain, so it cannot be smuggled into the profile layer. Remains M5's problem. | Reproduction boundary, stated |
| A43 | **`B_g` exists only for §4.5's sweep** (2,000 A100 + 0-500 H100). §4.2/4.3 state no budget, so constraint (7) is inactive there. No budget is invented. | Scope note |
| A44 | **[ARXIV] Table 4 has no `STT` column; [OSDI] Table 5 adds one, `Y` in every row.** The OSDI version added the column that shows the paper never reports the optimizer choosing STT-off — corroborating M2b's A28 and making it version-dependent. | Version discrepancy |
| A45 | **[OSDI] Table 6's column is `Agents`; [ARXIV] Table 5's is `Debaters`.** This **resolves M2's A14**: the column is `D`. One `(D,R)` pair per Code Gen configuration; a DAG selecting `llm_debate_testers` is not representable in `C_w`. | Version discrepancy, resolves an open item |
| A46 | **The 90th-percentile allocation assumption is [OSDI]-only** (p.576). [ARXIV] has no equivalent sentence. `t_c = p90` — the rule that shapes every capacity number in the reproduction — rests on one sentence in one version. | Version discrepancy on a load-bearing rule |
| A47 | **Policy counts and headline numbers differ between versions.** [ARXIV] Table 1 has three policies (Static 2560 GPUs / 80.4 MWh / $201.5k; Opt 1151 / 27.1 / 56.2; Opt+Mult 908 / 21.6 / 46.5); [OSDI] Table 2 has four, adding `LangGraph+Auto`, and restates the others as 2568 / 82.1 / 211.7, 1164 / 27.7 / 57.2, 912 / 22.1 / 47.2. The multiplexing reductions are quoted as 21.1%/20.2%/17.3% [ARXIV] vs 21.6%/20.2%/17.4% [OSDI]. Not profile inputs, but they are the validation targets, so the target itself is version-dependent. | Version discrepancy |
| A48 | **`Llama-3.2-90B` (our id, from M2b) vs `Llama-3.2-90B-Vision` (Figure 4a legend) vs `Llama-3.2` (Listing 1 p.569).** Three spellings, presumably one model. We keep M2b's id and record the aliases, since renaming would break M2b's approved `shared/model_ids.py`. | Naming, low risk |
| A49 | **The TP domain is workflow-dependent in the paper's data** — Figure 4b spans TP {1,2,4,8}, Figure 4a spans {4,8}, Table 5 uses only {4}. A.5's `g_m` is a property of `m` alone and cannot express a per-workflow restriction. | Formulation gap |
| A50 | **[OURS] `C_w` enumeration prunes the `stt` node.** The paper describes no such step, and §3.2 (p.573) says the orchestrator produces *a* logical workflow, singular. Discharges the M3 OBLIGATION from `PROGRESS.md` / M2b Q6. | Declared invention — §3.3 |
| A51 | **`a_c` is model-dependent (Figure 2c) but A.5 indexes it by `c` alone, and nothing links `c` to `m`.** Reproduced as written; a non-MILP `coherent(c,m)` predicate is carried so M4 can measure how much of the selected mass is incoherent. | M1 gap, now instrumented — §5.5 |
| A52 | **"Accuracy" is not one quantity.** §3.3 names VideoMME, HumanEval and Math; §4.4 evaluates the dynamic coding pipeline on **LiveCodeBench-v5 with pass@1 ≈ 0.15-0.40** (Figure 10, p.577) — the same workflow family on a different scale from Figure 2c's 66-91%. `a_c` values from different benchmarks are not comparable, yet A.5 pools them into one `τ_{w,s}` percentile population per workflow. We record `accuracy_benchmark` on every profile and never mix benchmarks within a workflow. | Definitional gap |

Candidates for `architecture-decisions.md`: **A37, A37b, A39, A40, A41, A38** — and A45 as the
resolution of M2's A14.

---

## 12. Required contact with the known critiques

`PROGRESS.md` logs a PATTERN: the evaluation systematically exercises capabilities A.5 cannot
express. M3 is where two of them stop being arguments and become numbers. **M3 adds no precedence
constraint and no makespan term.** It records the data that makes the gap computable at M4.

### 12.1 Precedence and makespan on the Video Q/A DAG

The DAG is `scene_detect → {frame_extract ∥ stt} → q_a` (M2b §6.1), and §4.6 (p.578) co-schedules
exactly that branch: "The two sub-tasks run in **near-perfect parallel, with full overlap in
execution**."

**What a profile-driven critical path would give:**

```
makespan(c) = L_scene(c) + max( L_frames(c), L_stt(c) ) + L_qa(c)
```

For, say, `c = (F=10, STT=on, model=Llava-OneVision-7B)` on H100/TP=4:
`L_scene`, `L_frames`, `L_stt` are **tool** stages — OpenCV, OmDet/CLIP, Whisper, on three different
serving engines (§4.1 p.575) — and generate **zero tokens**. `L_qa` is the only token-generating
stage. So the critical path is `L_scene + max(L_frames, L_stt) + (TTFT + t_c·TPOT)`.

**What filter (5) gives:** `ℓ^TTFT_m + t_c · ℓ^TPOT_m ≈ 0.22 + 1050×0.0070 ≈ 7.6 s`.

**The gap is exactly `L_scene + max(L_frames, L_stt)`, and it is invisible.** Not approximated —
structurally absent, because A.5 has no per-task term to sum or max over. Two specific mispredictions
follow, in opposite directions, and both need M3 data to quantify:

- **Under-count:** the three tool stages contribute real wall-clock that eq. (5) cannot see. §4.6's
  Figure 12b runs Whisper on CPUs and reports "Whisper's added CPU latency has minimal impact on
  end-to-end time" — a statement about a quantity the optimizer does not have.
- **Over-count on a parallel branch:** where two branches *do* both generate tokens, `t_c` folds them
  into one serialized stream on one model, charging a fully overlapped execution as if back-to-back.
  (Video Q/A does not exhibit this, because only `q_a` generates tokens; Code Generation's debate
  does, within one node.)

**What M3 must record for this to be computable at M4, and its provenance:**

| Datum | Field | Provenance | Note |
|---|---|---|---|
| per-node token breakdown, summing to `t_c` | `node_tokens` | `DERIVED` from `t_c` + the DAG (video: 100% on `q_a`; code gen: split across debate/tests/rank) | NON-MILP |
| per-node tool wall-clock | `node_service_time` | **`INVENTED`** or `Unavailable` | NON-MILP, quarantined |
| the DAG itself with edges | already in M1's `LogicalWorkflow` | — | M1's rule stands: M4/M5 must not read edges for scheduling |

The middle row is the honest part. **The paper profiles no tool latency at all.** §3.3's model
profiles report "TTFT and TPOT *for LLMs*"; Whisper, OmDet, CLIP and OpenCV are `TOOL` (M2b Q9/A25)
and have no profile. So a critical-path computation over this DAG is *not derivable from the paper*.
**Resolved (Q16, 2026-09-11):** populate `node_service_time` with clearly `INVENTED` order-of-magnitude values
in a separate module (`critique/tool_latency.py`) that **`to_milp_inputs()` cannot reach**, used only
to produce the side-by-side "critical path vs eq. (5)" figure, with every number in it stamped
`INVENTED` in the caption. The comparison is then a statement about the *structure* of the two
computations — which terms exist at all — not about our invented magnitudes, and it must be written
up that way.

### 12.2 Capacity eq. (3) and what it demands of `t_c`

```
μ_m · Σ_{w,s,c} x^peak_{w,s,c,m} · t_c  ≤  n_m · θ_m
```

`t_c` is per *whole configuration*. A `D=4, R=4` debate — sixteen LLM invocations plus test-writing
plus ranking — is distinguished from a single call **only** through the magnitude of `t_c`. Nothing
else in the formulation knows the difference: no call count, no per-node term, no concurrency.

Direct requirements on the workflow profiles, stated as testable invariants:

1. **`t_c` is the per-request total across every LLM call in the configuration**, not per call.
   Figure 2d's CDFs are exactly that (they are labelled "# of Generated Tokens" per request and they
   scale with `(D,R)`), so the anchors are already the right quantity. A test asserts monotonicity:
   `t_c(D=4,R=4) > t_c(D=4,R=2) > t_c(D=2,R=2)` for every model, and the observed growth is ≈3.3×
   from (2,2) to (4,4), against a call-count growth of 4× — sublinear, and that sublinearity is a
   profile fact the MILP consumes silently.
2. **The p90 must be the p90 of the *total*, not the sum of per-node p90s.** The latter is strictly
   larger and is what a naive per-node profile would produce. `TokenDistribution` therefore stores
   the total's percentiles as primary and `node_tokens` as a derived decomposition, never the
   reverse. Test: `sum(node p90) >= total p90`, asserted with a recorded ratio, so the size of the
   error a naive implementation would make is itself reported.
3. **`t_c` must not double-count tool stages.** Tools generate no tokens (M2 §6.1), so
   `node_tokens[tool] == 0` exactly, with provenance `DERIVED` and the note that this zero is the
   formulation's, not a measurement.

### 12.3 What the profiles structurally cannot supply, and what M4 will therefore compute wrongly

Stated plainly, as the brief requires.

`python_interpreter`, `sandboxed_container_runner`, `property_test_generator`,
`test_pass_rate_ranker`, `opencv_scene_detector`, `fixed_interval_segmenter`,
`opencv_frame_extractor`, `omdet_frame_annotator`, `clip_frame_annotator`, `whisper_stt`,
`caption_track_extractor` — **eleven of the twenty-six executors in the library** — are `TOOL`. A tool
has no model profile, so it has no `θ_m`, no `ℓ^TTFT_m`, no `ℓ^TPOT_m`, no `e_m`, no `g_m`, and it
generates no tokens, so it contributes zero to `t_c`.

Therefore, in M4:

1. **Three of Video Q/A's four stages are free.** `scene_detect`, `frame_extract` and `stt` cost zero
   energy, zero dollars, zero capacity and zero latency. The sub-workflow §4.6 spends an entire
   subsection co-scheduling contributes **nothing** to any constraint or objective.
2. **Code Generation's `execute_tests` stage is free**, and its wall-clock — running arbitrary
   generated code — is unbounded and unobserved by the latency filter.
3. **`n_m` is under-counted relative to the paper's own deployment.** §4.1 (p.575) provisions three
   serving engines (vLLM, speaches-ai, OmDet); §4.6 Figure 12a allocates 6×A100 of which some serve
   Whisper and OmDet. Our reproduction will allocate GPUs for LLM profiles only. **Every GPU count M4
   produces is a lower bound** on the deployment the paper describes, and by an amount our profiles
   cannot even estimate, since no tool throughput is reported anywhere.
4. **Energy and cost are under-counted by the same mechanism**, and non-uniformly across workflows —
   Video Q/A has three tool stages and Code Generation one, so the *comparison between workflows* is
   biased, not just the absolute level.
5. **Executor choice within a tool-served stage is unobservable.** `python_interpreter` vs
   `sandboxed_container_runner` yields a bit-identical objective (M2 §6.1). M3 confirms it at the
   data level: both map to the empty profile.

None of this is repaired. Point 3 in particular must be carried into any comparative claim: a
statement of the form "Murakkab needs N GPUs" is, in this reproduction, "Murakkab needs N GPUs *for
its LLM executors*", and that qualifier belongs in the sentence.

---

## 13. Expected provenance split (estimate, to be replaced by the generated ledger)

| Layer / field | Count | PAPER_TABLE / _LABEL | PAPER_TEXT | FIGURE_READ | DERIVED / INTERP | EXTRAP | EXTERNAL | INVENTED | UNAVAILABLE |
|---|---|---|---|---|---|---|---|---|---|
| `a_c` | 44 | 8 | 1 | 35 | 0 | 0 | 0 | **0** | 0 |
| `t_c` (p90) | 44 | 0 | 2 | 22 | 6 | 0 | 0 | **0** | 14 |
| `θ_m` | ~30 | 12 | 0 | 10 | 0 | 2 | 0 | **0** | 6 |
| `ℓ^TPOT_m` | ~30 | 12 | 0 | 10 | 0 | 2 | 0 | **0** | 6 |
| `ℓ^TTFT_m` | ~30 | **0** | 0 | 22 | 0 | 0 | 0 | **0** | 8 |
| `g_m` | ~30 | 30 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `e_m` | 2 (per GPU type) | 0 | 0 | 0 | 2 | 0 | 0 | **0** | 0 |
| `c_g` | 2 | 0 | 0 | 0 | 0 | 0 | **2** | 0 | 0 |
| `τ_{w,s}` | 16 | 16 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `λ^peak/avg` | 2×24×tiers | 0 | shares only | all | 0 | 0 | 0 | 0 | 0 |
| `α` | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `node_service_time` (NON-MILP) | ~7 | 0 | 0 | 0 | 0 | 0 | 0 | **7** | — |

**Headline split, MILP-facing values only (≈230 values):** roughly **35% directly paper-reported**
(table cells and printed labels), **45% digitized from figures** with bands, **5% derived**, **<2%
extrapolated**, **<1% external**, **0% invented**, and **~14% `Unavailable`** — i.e. deliberately
missing rather than guessed. The only `INVENTED` numbers in the milestone are the seven quarantined
tool service times of §12.1, which cannot reach the optimizer.

That zero in the `INVENTED` column for every MILP-facing field is the design target, and it is
achievable only because `Unavailable` is a legal state, which Q19 accepted. The consequence M4
inherits: every headline GPU, energy and cost number is computed over a *reduced* `C_w`, and the
excluded set must be printed next to it — a comparison run against a different profile set that
happens to exclude a different subset is not comparable.

---

## 14. File layout

```
PROFILES.md .................. (repo root, per Q15) GENERATED provenance ledger (§10)
/optimization/
  profiles/
    DESIGN.md ................ this document
    __init__.py .............. public API: profile_set(name), MilpInputs
    provenance.py ............ Provenance, Measured, Unavailable, Anchor, Citation,
                               CITATION_REGISTRY, ProfileProvenanceError
    schema.py ................ ConfigKey, TokenDistribution, WorkflowProfile, ModelProfileKey,
                               LoadPoint, ModelProfile, ResourceType, ProfileSet, MilpInputs,
                               OperatingPointPolicy, TokenPolicy, SloMix
    enumerate_cw.py .......... C_w for both workflows; prune_stt() [OURS, §3.3]
    sources/
      tables.py .............. Tables 5 and 6 transcribed verbatim, both versions, with a
                               cross-version equality assertion at import time
      figure_labels.py ....... Figures 7/8 tier labels; §2.5/§3.4 prose numbers
      figures_digitized.py ... digitized series for Figures 2a-2d, 3, 4a-4b, 19, each with
                               band, method note, and the calibration constants of §5.3
      external.py ............ c_g from a vendor price list; retrieval date; EXTERNAL only
    workflow_profiles.py ..... assembles a_c, t_c, node_tokens
    model_profiles.py ........ assembles theta/ttft/tpot/e/g; operating-point policies
    slo_tiers.py ............. derives tau; reconstructs and reports the §7.3 residuals
    arrivals.py .............. lambda peak/avg per (w, s) per epoch; SloMix
    profile_sets.py .......... the named sets of §9.2 + resample()
    critique/
      tool_latency.py ........ [INVENTED] tool service times. QUARANTINED: importing this from
                               anything reachable by to_milp_inputs() fails a test.
      critical_path.py ....... makespan vs eq.(5) comparison (§12.1)
/tests/
  test_profile_provenance.py ....... the four assertions of §2.5
  test_profile_contradiction.py .... no value contradicts a paper table or printed label
  test_cw_enumeration.py ........... |C_codegen|==20, |C_video|==24; pruned DAG type-checks;
                                     dead knobs excluded; include_dead_knobs=True equivalence
  test_token_distributions.py ...... p90 present everywhere derivable; monotone in (D,R) and F;
                                     sum(node p90) >= total p90; tools contribute exactly 0
  test_model_profiles.py ........... Table 5/6 cells reproduce Figure 3 curves within band;
                                     g_m == tp; operating-point policies are ordered
  test_slo_tiers.py ................ tier derivation runs after profiles; §7.3 residuals within
                                     the documented tolerance; adding a model shifts the tiers
  test_milp_boundary.py ............ to_milp_inputs() exposes exactly A.5's parameter list;
                                     NON-MILP fields unreachable; critique/ unreachable
  test_profiles_md_generated.py .... PROFILES.md matches the regenerated ledger byte-for-byte
```

Build order, file by file with confirmation per `CLAUDE.md`: `provenance.py` → `schema.py` →
`sources/tables.py` → `sources/figure_labels.py` → `sources/figures_digitized.py` →
`sources/external.py` → `enumerate_cw.py` → `workflow_profiles.py` → `model_profiles.py` →
`slo_tiers.py` → `arrivals.py` → `profile_sets.py` → `critique/` → tests → generate `PROFILES.md`.

`provenance.py` first is deliberate: the machinery that makes a number inadmissible without a source
must exist before the first number does.

---

## 15. Resolved decisions (Q13-Q20)

All eight were put to Arno on 2026-09-11, who delegated them back with "just do as you suggest."
Each is therefore **resolved as recommended**, recorded here as a decision rather than a question.
Design approval for M3 as a whole is separate and still outstanding.

| # | Decision | Resolution (2026-09-11) |
|---|---|---|
| **Q13** | `DeepSeek-Llama-70B` vs `Llama-3.1-70B` (A34) | **Distinct.** `DeepSeek-Llama-70B` gets an `ASSUMED_ALIAS` profile borrowed from `Llama-3.1-70B`, **disabled in `baseline`**, enabled in `wide`. Aliasing silently would put a fabricated identity claim under 4 of 20 Code Gen configurations. |
| **Q14** | `τ` for latency: printed Fig 7b/8b labels, or tiers derived from our own space (A37) | **Printed labels are `baseline`**, per reproduce-literally. Derived tiers ship as the `derived_tiers` profile set and are always computed into `CoverageReport.tier_reconstruction`. M4's first run is therefore *expected to be latency-infeasible for the paper's own Table 5 `Best` configuration*, and that infeasibility is a reported result (A37), not a bug to chase. M4 must not "fix" it by relaxing `τ`. |
| **Q15** | `PROFILES.md` location | **Repo root**, beside `PROGRESS.md`. `CLAUDE.md` cites it as a project-level artifact; M4-M7 all read it. |
| **Q16** | Record `INVENTED` tool service times (§12.1) | **Yes, quarantined** under `critique/`, unreachable from `to_milp_inputs()` (enforced by test), every derived figure captioned `[INVENTED]`. The critical-path comparison is structural; the magnitudes are illustrative only. |
| **Q17** | Carry `prompt_tokens` (A39) | **Yes, as `Unavailable`.** §3.3 requires it of a profile; omitting the field would hide the gap. A test forbids it from appearing in the MILP projection. |
| **Q18** | `c_g` source (A40) | **`EXTERNAL` vendor list price, swept ±50%.** `Unavailable` would disable objectives (12)/(13) and constraint (6) — two of three objectives — which would gut the comparison. The sweep makes the dependence visible. |
| **Q19** | `Unavailable` for 14 `t_c` and 8 `ℓ^TTFT_m` values (≈14% of MILP-facing values) | **Accepted.** M4 excludes those configurations and reports them as *data-excluded*, with the excluded set printed alongside every headline number. This is the mechanism that keeps the `INVENTED` column at zero. |
| **Q20** | Does `M` get indexed by operating point (A37b)? | **No — one operating point per `m`.** `M` stays `(model, gpu, tp)`; `TABLE_REPORTED` collapses the per-tier rows as described in §6.3. Expanding the index set would be repairing A.5, which the standing policy forbids. The lost per-tier batching behaviour is reported, not reinstated. |

## 16. What this milestone does *not* do

- No MILP. No solver, no decision variables, no objective. M4.
- No `μ_m` (A42). M5.
- No auto-scaler thresholds, though §3.4 (p.575) says they come "based on the performance-throughput
  characteristic in executor profiles" — i.e. from `ModelProfile.curve`, which M3 does build. M6
  consumes it.
- No Math Q/A and no OS-log analysis, so Figures 15-17 and Table 4 are read only as cross-checks on
  the *method* (e.g. Figure 16b/16c confirm that the paper profiles prompt and completion tokens
  separately when it has them), never as data.
- No re-profiling loop. §3.3 (p.573) describes periodic profile updates from "request-response pairs
  and user feedback"; with no GPUs and no users there is nothing to update from. Declared as scope,
  not oversight.
