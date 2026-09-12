"""
Executor Library package -- Milestone 2 (Code Generation) + Milestone 2b (Video Q/A).

Implements Murakkab (OSDI '26), Section 3.2, "Executor Library" and "Attributes" (p.572): the
finite, known set of models and tools the Workflow Orchestrator selects from, each exposing a
textual description, an interface specification, and a key-value list of configurable parameters.

Layout (DESIGN.md Section 7; DESIGN_VIDEO_QA.md Section 9):
    knobs.py            the knob vocabulary -- one ParameterSpec factory per knob per catalogue
    registry.py         InMemoryExecutorLibrary + the per-workflow catalogue registry
    code_generation.py  the Code Generation catalogue (Figure 1b, p.568)  -- 13 executors
    video_qa.py         the Video Q/A catalogue (Figure 1a, p.568; Listing 2, p.572) -- 13

Importing this package registers every catalogue. `default_library()` is the flat union of all of
them -- 26 executors -- which is what Section 3.2 describes: one shared library of executors,
reusable across workflows, with the orchestrator selecting per sub-task. `library_for(...)` and
the per-workflow helpers below exist for tests and for milestones that want isolation.

Math Q/A and the OS-log-analysis workflow remain deferred by CLAUDE.md.
"""

from __future__ import annotations

from development.executor_lib import code_generation as _code_generation  # registers on import
from development.executor_lib import video_qa as _video_qa  # registers on import
from development.executor_lib.code_generation import CODE_GENERATION_EXECUTORS
from development.executor_lib.code_generation import GROUNDING as CODE_GENERATION_GROUNDING
from development.executor_lib.code_generation import (
    NOT_NAMED_BY_THE_PAPER as CODE_GENERATION_NOT_NAMED_BY_THE_PAPER,
)
from development.executor_lib.knobs import HARDWARE_LEVEL_KNOBS, INVENTED_KNOBS, KNOB_LEVELS
from development.executor_lib.registry import (
    CATALOGUES,
    InMemoryExecutorLibrary,
    default_library,
    library_for,
    register_catalogue,
)
from development.executor_lib.video_qa import GROUNDING as VIDEO_QA_GROUNDING
from development.executor_lib.video_qa import (
    NOT_NAMED_BY_THE_PAPER as VIDEO_QA_NOT_NAMED_BY_THE_PAPER,
)
from development.executor_lib.video_qa import VIDEO_QA_EXECUTORS

# NOTE (M2b): `GROUNDING` and `NOT_NAMED_BY_THE_PAPER` are exported PER CATALOGUE. With one
# catalogue the bare names were unambiguous; with two they are not, and merging them would hide
# which paper figure grounds which entry. Same forcing function as gap A27 for knob domains: the
# second workflow turns "one global thing" into "one thing per catalogue".

__all__ = [
    "CATALOGUES",
    "CODE_GENERATION_EXECUTORS",
    "CODE_GENERATION_GROUNDING",
    "CODE_GENERATION_NOT_NAMED_BY_THE_PAPER",
    "HARDWARE_LEVEL_KNOBS",
    "INVENTED_KNOBS",
    "InMemoryExecutorLibrary",
    "KNOB_LEVELS",
    "VIDEO_QA_EXECUTORS",
    "VIDEO_QA_GROUNDING",
    "VIDEO_QA_NOT_NAMED_BY_THE_PAPER",
    "code_generation_library",
    "default_library",
    "library_for",
    "register_catalogue",
    "video_qa_library",
]

_ = (_code_generation, _video_qa)  # imported for registration side effects; kept referenced


def code_generation_library() -> InMemoryExecutorLibrary:
    """Just the Code Generation catalogue (Figure 1b, p.568)."""
    return library_for("code_generation")


def video_qa_library() -> InMemoryExecutorLibrary:
    """Just the Video Q/A catalogue (Figure 1a, p.568; Listing 2, p.572)."""
    return library_for("video_qa")
