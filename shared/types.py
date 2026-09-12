"""
Nominal type registry for executor interface specifications.

Implements the type vocabulary required by the DAG type-check in:
  Murakkab (OSDI '26), Section 3.2, "Logical Workflow" (p.573):
    "The orchestrator performs type-checking on the DAG to ensure output types from source
     nodes match input types of destination nodes."

[DESIGN CHOICE] The paper MANDATES type-checking but never specifies a type vocabulary, and
the declarative specification (Listing 2, p.572) contains no developer-written types at all.
All types therefore come from executor interface specifications (Section 3.2, "Attributes",
attribute (2)). This module supplies the minimal nominal vocabulary that makes the paper's own
check executable. See DESIGN.md Section 3.3 and gap A6.

Design rule: strict NOMINAL equality, no subtyping, no coercion. A `Text`-for-everything
vocabulary would make the paper's type-check vacuous.
"""

from __future__ import annotations

from typing import Final

# --- Code Generation workflow types (Figure 1b, p.568; Section 2.2, p.569) ------------------
# [DESIGN CHOICE] Names are ours; the paper names no types.

QUERY: Final = "Query"
"""The natural-language request entering a workflow.

Code Generation (Figure 1b, p.568): the coding problem, drawn as the 'Query' node.
Video Q/A (Listing 2, p.572): the `query` boundary parameter of `def workflow(query, videos)`,
consumed by `q_a` -- "Answer the query given some context."

[M2b, decision Q7 of DESIGN_VIDEO_QA.md] One type serves both workflows. The paper has no type
vocabulary at all (M1 gap A6), and a second near-identical nominal type for "the user's request"
would buy separation the variadic `accepted_types` sets already provide. This docstring was
generalized in M2b; the NAME and registry membership are unchanged, so nothing downstream moves.
"""

CODE_CANDIDATES: Final = "CodeCandidates"
"""Candidate code solutions proposed by the coder agents (Figure 1b: Coder-A/B/C)."""

TEST_SUITE: Final = "TestSuite"
"""Unit tests produced by the tester agents (Figure 1b: Tester-A/B)."""

EXECUTION_RESULTS: Final = "ExecutionResults"
"""Results of running the tests (Figure 1b: 'Python Interp.', a Tool executor)."""

ANSWER: Final = "Answer"
"""The workflow's final answer.

Code Generation (Figure 1b, p.568): the highest-voted solution selected by the Ranker.
Video Q/A (Figure 1a, p.568; Listing 2 line 11, p.572): the answer to the user's query.

[M2b] Generalized by documentation only -- this is the single type both workflows share."""


# --- Video Q/A workflow types (Figure 1a, p.568; Listing 2, p.572; Section 2.2, p.568) --------
# [DESIGN CHOICE] Names are ours; the paper names no types. Added ADDITIVELY in Milestone 2b --
# no existing constant is renamed, removed, or re-spelled (DESIGN_VIDEO_QA.md Section 3.1).

VIDEOS: Final = "Videos"
"""The list of input videos (Listing 2 line 6: `def workflow(query, videos)`; Listing 1 p.569
illustrates the payload as `videos = ["road_trip.mp4"]`)."""

SCENES: Final = "Scenes"
"""Distinct scenes identified in each video (Figure 1a: 'Scene Detector'; Listing 2 line 8).

Note that BOTH downstream branches consume this: `frame_extract(scenes)` and `stt(scenes)`.
Listing 2's `stt` takes scenes, not a separate audio stream -- see gap A23."""

FRAMES: Final = "Frames"
"""Frames sampled from the scenes (Figure 1a: 'Raw Frames'; Listing 2 line 9)."""

ANNOTATED_FRAMES: Final = "AnnotatedFrames"
"""Frames annotated with detected objects (Figure 1a: 'Annotated Frames', out of the Object
Detector).

This type exists because Listing 2 (p.572) has NO object-detection sub-task, while Figure 1a and
Section 2.2 (p.568) both describe an Object Detector agent. Reproducing Listing 2 literally folds
detection into the `frame_extract` executors, so annotation shows up as an alternative OUTPUT TYPE
of that sub-task rather than as a node. See gap A22."""

TRANSCRIPT: Final = "Transcript"
"""The audio transcript (Figure 1a: 'Text' out of Speech-to-Text; Listing 2 line 10)."""


TYPE_REGISTRY: Final[frozenset[str]] = frozenset(
    {
        # Code Generation (Milestone 1)
        QUERY,
        CODE_CANDIDATES,
        TEST_SUITE,
        EXECUTION_RESULTS,
        ANSWER,
        # Video Q/A (Milestone 2b). `Query` and `Answer` are REUSED, not duplicated: Listing 2
        # names the boundary parameter `query` and returns `answer`.
        VIDEOS,
        SCENES,
        FRAMES,
        ANNOTATED_FRAMES,
        TRANSCRIPT,
    }
)


class UnknownTypeError(ValueError):
    """Raised when an executor interface references a type outside the registry.

    Deliberately a load-time error rather than a runtime surprise: DESIGN.md Section 3.2 makes
    this an obligation on the Executor Library (Milestone 2).
    """


def validate_type(name: str) -> str:
    """Return `name` if it is a registered type, else raise `UnknownTypeError`."""
    if name not in TYPE_REGISTRY:
        raise UnknownTypeError(
            f"unknown type {name!r}; registered types are {sorted(TYPE_REGISTRY)}"
        )
    return name


def types_match(source_type: str, destination_type: str) -> bool:
    """Nominal equality check backing the paper's source-output/destination-input rule.

    No subtyping and no coercion, by design (DESIGN.md Section 3.3).
    """
    return source_type == destination_type
