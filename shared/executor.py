"""
Executor Library data model: the three executor forms and the three exposed attributes.

Implements Murakkab (OSDI '26), Section 3.2, "Executor Library" and "Attributes" (p.572).

The three forms, verbatim from Section 3.2 (p.572):
  1. LLM: "specialized LLM configurations (fine-tuning, few-shot learning, or even just
     domain-specific prompting)";
  2. Structured compositions: "aggregations of models, e.g., a self-reflection or an LLM-Debate
     pattern built from multiple LLMs";
  3. Tool: "utility modules for AI workflows to take actions with (e.g., OpenCV frame extractor
     for video processing, web-search, file-search, computer-use, or any third-party tools that
     follow the MCP specification)."

The three attributes, verbatim from Section 3.2, "Attributes" (p.572):
  "Each model or tool in the library exposes three attributes: (1) a textual description,
   (2) an interface specification, and (3) a key-value list of configurable parameters. For
   example, the frame extraction tool exposes the knobs: F (number of frames to extract) and
   cores (number of CPU cores to run on). The LLM Debate composition exposes the knobs:
   D (number of debaters), R (number of rounds), and model (which LLM to use). The orchestrator
   uses these descriptions and interfaces to rank and assign executors (models or tools) for
   workflow tasks, deferring parameter configuration to a later optimization phase
   (Section 3.3)."

That last clause is why `ParameterSpec` has NO value field: parameters are declared here and
valued by the optimizer (Section 3.3; Appendix A.5, p.586-587; Table 6, p.586).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal, Protocol

from shared.types import validate_type


class ExecutorKind(Enum):
    """The three forms an executor can take (Section 3.2, p.572). Closed set."""

    LLM = "llm"
    COMPOSITION = "composition"
    TOOL = "tool"


@dataclass(frozen=True)
class Port:
    """One typed slot of an executor's interface specification (attribute (2)).

    Ports are ORDERED on `ExecutorSpec`, because Listing 2's data flow is positional Python
    call composition and binding is therefore positional (DESIGN.md Section 4.3).
    """

    name: str
    type: str
    variadic: bool = False
    """True if this port accepts a list-literal argument.

    Required by Listing 2 line 11 (p.572): `answer = q_a(query, [frames, transcript])` binds
    two upstream results to a single argument position.
    """
    also_accepts: tuple[str, ...] = ()
    """Additional element types allowed on a variadic port.

    Listing 2's `q_a` is described as "Answer the query given some context", and its list
    argument mixes frames with a transcript -- i.e. a variadic port is heterogeneous by nature.
    (The M1 design doc originally required all elements to share one type; that was corrected
    during implementation. See DESIGN.md Section 4.3, "Correction applied during
    implementation".)
    """

    def __post_init__(self) -> None:
        validate_type(self.type)
        for extra in self.also_accepts:
            validate_type(extra)
        if self.also_accepts and not self.variadic:
            raise ValueError(
                f"port {self.name!r} declares `also_accepts` but is not variadic; only a "
                "variadic port may accept more than one element type"
            )

    @property
    def accepted_types(self) -> tuple[str, ...]:
        """The set of types this port accepts. A single type unless the port is variadic."""
        return (self.type, *self.also_accepts)


@dataclass(frozen=True)
class ParameterSpec:
    """One entry of the paper's "key-value list of configurable parameters" (attribute (3)).

    Examples given by the paper (Section 3.2, p.572): the frame extraction tool's `F` and
    `cores`; the LLM Debate composition's `D` (debaters), `R` (rounds) and `model`.

    NOTE: there is deliberately no `value` field. Section 3.2 defers "parameter configuration
    to a later optimization phase (Section 3.3)". Milestone 1 must not fill these in.
    """

    name: str
    kind: Literal["int", "float", "str", "enum"]
    domain: tuple[Any, ...] | None = None
    description: str = ""


@dataclass(frozen=True)
class ExecutorSpec:
    """A single library entry exposing the paper's three attributes (Section 3.2, p.572)."""

    name: str
    kind: ExecutorKind
    description: str  # attribute (1): textual description
    inputs: tuple[Port, ...] = ()  # attribute (2): interface specification (ordered)
    outputs: tuple[Port, ...] = ()  # attribute (2)
    parameters: tuple[ParameterSpec, ...] = ()  # attribute (3): configurable parameters

    def __post_init__(self) -> None:
        if len(self.outputs) != 1:
            # [DESIGN CHOICE] Listing 2 binds exactly one result per call
            # (`scenes = scene_detect(videos)`), so an executor has exactly one output.
            # The paper does not state this; it follows from the DSL's assignment form.
            raise ValueError(
                f"executor {self.name!r} must declare exactly one output port "
                f"(Listing 2 binds one result per call); got {len(self.outputs)}"
            )
        variadic_count = sum(1 for p in self.inputs if p.variadic)
        if variadic_count > 1:
            raise ValueError(
                f"executor {self.name!r} declares {variadic_count} variadic input ports; "
                "at most one is supported"
            )

    @property
    def output(self) -> Port:
        """The single output port."""
        return self.outputs[0]

    @property
    def parameter_names(self) -> tuple[str, ...]:
        return tuple(p.name for p in self.parameters)


class ExecutorLibrary(Protocol):
    """The finite, known catalogue the orchestrator selects from.

    Section 3.2 (p.572): "A key design choice in Murakkab is mapping a broad range of unknown
    tasks to executors that are built from a finite, known set of models and tools in the
    library. If none is found, Murakkab prompts the developer to onboard a suitable one."
    """

    def all(self) -> tuple[ExecutorSpec, ...]: ...

    def get(self, name: str) -> ExecutorSpec: ...


@dataclass(frozen=True)
class ExecutionPreferences:
    """Optional developer-stated execution preferences.

    Section 3.2, "Declarative Specification" (p.573): "However, Murakkab does not restrict
    developers from specifying any execution preferences (e.g., particular LLM choice or
    hardware constraint), which are then incorporated into the optimization process as
    constraints."

    [DESIGN CHOICE] The paper gives neither a syntax for preferences nor a mapping onto the
    Appendix A.5 decision variables (gap A7). Milestone 1 therefore only defines the boundary:
    preferences travel BESIDE the LogicalWorkflow, never inside it, so that Section 3.2's
    "without binding to specific models, resources, or hardware" still holds for the DAG.
    Populating and encoding them is Milestone 4's job.
    """

    allowed_models: tuple[str, ...] = ()
    hardware_constraints: dict[str, Any] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not self.allowed_models and not self.hardware_constraints
