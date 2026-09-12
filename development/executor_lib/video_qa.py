"""
The Video Q/A catalogue: 13 executors covering the four sub-tasks of Listing 2.

Implements Murakkab (OSDI '26), Section 3.2, "Executor Library" and "Attributes" (p.572), for the
Video Q/A workflow of Figure 1a (p.568), Listing 2 (p.572), Section 2.2 (p.568) and Appendix A.2 +
Table 5 (p.585).

Listing 2 (p.572) is reproduced verbatim in `development/specs/video_qa.py`; its four sub-tasks and
their data flow give the signatures below:

    scene_detect  :: (Videos)                                         -> Scenes
    frame_extract :: (Scenes)                                         -> Frames | AnnotatedFrames
    stt           :: (Scenes)                                         -> Transcript
    q_a           :: (Query, [Frames | AnnotatedFrames | Transcript]) -> Answer

Figure 1a (p.568), read off the figure:
    Question/Videos -> Scene Detector (Tool) -> Frame Extractor (Tool) -> Raw Frames
                                             -> Audio -> Speech-to-Text (ML Model) -> Text
                       Raw Frames -> Object Detector (ML Model) -> Annotated Frames
                       Text + Annotated Frames -> Q/A (LLM) -> Answer
Caption: "Video Q/A workflow: multi-modal with tools handling different modalities before feeding
into an LLM for answering the query."

--- THREE DEVIATIONS FORCED BY LISTING 2, ALL DECLARED (gaps A22, A23, A24) -------------------
1. NO OBJECT-DETECTION SUB-TASK. Figure 1a and Section 2.2 (p.568) describe five agents including
   an Object Detector; Listing 2 declares four sub-tasks and no detection step. Listing 2 is the
   only DECLARATIVE description the paper gives, and this is the declarative layer, so Listing 2
   wins: object detection is folded into `frame_extract` executors, which is why annotation
   appears as an alternative OUTPUT TYPE (`AnnotatedFrames`) rather than as a node. (A22)
2. `stt` CONSUMES SCENES, NOT AUDIO. Listing 1 (p.569, the imperative straw-man) routes a separate
   audio stream out of scene detection; Listing 2 writes `transcript = stt(scenes)`. So audio
   de-muxing happens INSIDE the STT executor and `whisper_stt`'s input port is `Scenes`.
   Implementing Listing 1's shape would require multi-output calls -- the paradigm the paper
   argues against. (A23)
3. NO `stt_enabled` KNOB ANYWHERE. Section 3.3.1 (p.574) names STT on/off as a workflow-level
   knob, but Section 3.2's attribute model attaches knobs to executors and no executor can own the
   knob that deletes it. Decision Q6 (2026-09-11) expresses it through `C_w` instead -- see
   `knobs.NO_STT_ENABLED_KNOB`. (A18/A24)

--- GROUNDING ---------------------------------------------------------------------------------
Same scheme as the Code Generation catalogue: "PAPER" (the paper names this executor or backend
for Video Q/A), "PAPER-FORM" (the paper names the form/pattern but applies it elsewhere or leaves
the application ambiguous), "INVENTED" (ours). Markers live in banner comments and in `GROUNDING`,
never in the prompt-facing `description` -- telling the orchestrator LLM which entries the authors
invented would bias selection on a signal the real system does not have.

--- WHAT IS NOT HERE --------------------------------------------------------------------------
No performance numbers: accuracy, latency, TTFT/TPOT, energy, cost and token counts are Milestone
3 (Section 3.3, p.573). No parameter values (Section 3.2, p.572 defers configuration to the
optimizer). No hardware knobs -- Section 3.3.1 Decision 3 (p.574) makes GPU type and parallelism
implicit in the model profile.
"""

from __future__ import annotations

from typing import Final

from development.executor_lib.knobs import (
    cores_knob,
    debaters_knob,
    frames_knob,
    rounds_knob,
    segment_knob,
    video_qa_model_knob,
)
from development.executor_lib.registry import register_catalogue
from shared.executor import ExecutorKind, ExecutorSpec, Port
from shared.types import ANNOTATED_FRAMES, ANSWER, FRAMES, QUERY, SCENES, TRANSCRIPT, VIDEOS

# =============================================================================================
# 1. scene_detect :: (Videos) -> Scenes
#    Listing 2 line 2: "Given a list of videos, identify scenes in each."
#    Figure 1a: "Scene Detector (Tool)".
# =============================================================================================

# --- [PAPER] Listing 1 line 3 (p.569): `scene_detection = Tool(fn=SceneDetector(), ...,
#     resources={"CPUs": 32})`; Section 2.3 (p.569) names "SceneDetector in OpenCV"; Section 3.2
#     (p.572) gives OpenCV as the canonical Tool example.
OPENCV_SCENE_DETECTOR = ExecutorSpec(
    name="opencv_scene_detector",
    kind=ExecutorKind.TOOL,
    description=(
        "OpenCV scene detection tool: analyses the content of each input video and splits it into "
        "distinct scenes at shot boundaries, so that later stages see coherent segments rather "
        "than one continuous stream."
    ),
    inputs=(Port(name="videos", type=VIDEOS),),
    outputs=(Port(name="scenes", type=SCENES),),
    parameters=(cores_knob(),),
)

# --- [INVENTED] No such executor in the paper. A content-blind baseline: fixed-length chunking.
#     Justified only by the breadth of form 3, Section 3.2 (p.572).
FIXED_INTERVAL_SEGMENTER = ExecutorSpec(
    name="fixed_interval_segmenter",
    kind=ExecutorKind.TOOL,
    description=(
        "Fixed-interval segmentation tool: cuts each video into equal-length chunks by timestamp "
        "alone, with no content analysis, so a chunk boundary may fall in the middle of a shot."
    ),
    inputs=(Port(name="videos", type=VIDEOS),),
    outputs=(Port(name="scenes", type=SCENES),),
    parameters=(cores_knob(), segment_knob()),
)

# --- [INVENTED] A multi-modal LLM doing the job of a Tool. Same probe as the Code Generation
#     catalogue's `llm_execution_simulator`: on a sub-task the paper serves with a Tool, this is
#     the ONLY candidate Appendix A.5 can see, because it is the only one that generates tokens.
VLM_SCENE_DETECTOR = ExecutorSpec(
    name="vlm_scene_detector",
    kind=ExecutorKind.LLM,
    description=(
        "A multi-modal LLM that identifies scene boundaries by reading sampled thumbnails of each "
        "video and reasoning about where the setting changes. Slower and less precise than a "
        "dedicated detector, and it consumes model capacity to do a tool's job."
    ),
    inputs=(Port(name="videos", type=VIDEOS),),
    outputs=(Port(name="scenes", type=SCENES),),
    parameters=(video_qa_model_knob(),),
)

# =============================================================================================
# 2. frame_extract :: (Scenes) -> Frames | AnnotatedFrames
#    Listing 2 line 3: "Given a list of scenes, extract frames."
#    Figure 1a: "Frame Extractor (Tool)" -> "Raw Frames" -> "Object Detector (ML Model)" ->
#    "Annotated Frames". Under Listing 2 the detector has no node of its own (A22).
# =============================================================================================

# --- [PAPER] Section 3.2 (p.572), verbatim: "the frame extraction tool exposes the knobs: F
#     (number of frames to extract) and cores (number of CPU cores to run on)". Listing 1 line 8
#     (p.569): `frame_extractor = Tool(fn=FrameExtractor(), params={"num_frames": 15},
#     resources={"CPUs": 32})`.
OPENCV_FRAME_EXTRACTOR = ExecutorSpec(
    name="opencv_frame_extractor",
    kind=ExecutorKind.TOOL,
    description=(
        "OpenCV frame extraction tool: samples a fixed number of frames from each scene and "
        "returns them as raw images, with no labelling or object detection."
    ),
    inputs=(Port(name="scenes", type=SCENES),),
    outputs=(Port(name="frames", type=FRAMES),),
    # The paper's own worked example of attribute (3), Section 3.2 (p.572), in its own order.
    parameters=(frames_knob(), cores_knob()),
)

# --- [PAPER-FORM] OmDet is paper-named -- Section 4.1 (p.575): "OmDet [89] for object detection
#     model serving"; Section 4.6 Figures 12a-12c (p.578) co-schedule it with Whisper -- and
#     Figure 1a has an Object Detector agent. But Listing 2 has no object-detection sub-task, so
#     FOLDING detection into the frame-extraction executor is OURS (A22).
#
#     Decision Q9 (2026-09-11): OmDet is a TOOL, per Section 3.2 (p.572), "Traditional ML models
#     are also included as tools". Consequence (A25): Section 4.6 provisions GPUs for it, yet as a
#     Tool it has no model profile `m`, no `n_m`, and contributes zero to every A.5 constraint and
#     objective.
OMDET_FRAME_ANNOTATOR = ExecutorSpec(
    name="omdet_frame_annotator",
    kind=ExecutorKind.TOOL,
    description=(
        "OmDet frame extraction and object detection tool: samples frames from each scene and "
        "annotates them with the objects it detects, returning labelled frames rather than raw "
        "ones."
    ),
    inputs=(Port(name="scenes", type=SCENES),),
    outputs=(Port(name="frames", type=ANNOTATED_FRAMES),),
    parameters=(frames_knob(), cores_knob()),
)

# --- [PAPER] backend named by Listing 1 line 13 (p.569): `object_detection = MLModel(name="CLIP",
#     key=AZURE_KEY, resources={"CPUs": 128})`. Same folding deviation as OmDet above (A22).
CLIP_FRAME_ANNOTATOR = ExecutorSpec(
    name="clip_frame_annotator",
    kind=ExecutorKind.TOOL,
    description=(
        "CLIP frame extraction and annotation tool: samples frames from each scene and tags each "
        "one with the image-text labels that best match it, returning labelled frames."
    ),
    inputs=(Port(name="scenes", type=SCENES),),
    outputs=(Port(name="frames", type=ANNOTATED_FRAMES),),
    parameters=(frames_knob(), cores_knob()),
)

# --- [INVENTED] Not in the paper. A multi-modal LLM captions the sampled frames instead of a
#     detector annotating them -- the token-generating alternative on this sub-task.
VLM_FRAME_CAPTIONER = ExecutorSpec(
    name="vlm_frame_captioner",
    kind=ExecutorKind.LLM,
    description=(
        "A multi-modal LLM that samples frames from each scene and writes a short caption for "
        "each one describing what it shows, producing described frames instead of detector "
        "labels."
    ),
    inputs=(Port(name="scenes", type=SCENES),),
    outputs=(Port(name="frames", type=ANNOTATED_FRAMES),),
    parameters=(frames_knob(), video_qa_model_knob()),
)

# =============================================================================================
# 3. stt :: (Scenes) -> Transcript
#    Listing 2 line 4: "Given a list of scenes, convert audio to text."
#    Figure 1a: "Speech-to-Text (ML Model)" -> "Text".
# =============================================================================================

# --- [PAPER] Listing 1 line 10 (p.569): `speech_to_text = MLModel(name="Whisper",
#     key=OPENAI_API_KEY, resources={"PTUs": 50})`; Section 4.1 (p.575): "speaches-ai (v0.7) as
#     the speech-to-text model serving engine"; Section 4.6 Figures 12a-12c (p.578).
#
#     The `cores` knob is not decoration here: Figure 12b runs Whisper ON CPUs and reports it
#     "runs efficiently without saturating CPUs, making it a good candidate for offloading".
#     It is also unreachable -- Appendix A.5 has no CPU resource type, no placement variable, and
#     its budget constraint (7) is GPU-only. The paper's own GPU-saving result cannot be CHOSEN by
#     the optimizer the paper formulates. (A30)
WHISPER_STT = ExecutorSpec(
    name="whisper_stt",
    kind=ExecutorKind.TOOL,
    description=(
        "Whisper speech-to-text tool: pulls the audio track out of each scene and transcribes the "
        "spoken content into text."
    ),
    inputs=(Port(name="scenes", type=SCENES),),
    outputs=(Port(name="transcript", type=TRANSCRIPT),),
    parameters=(cores_knob(),),
)

# --- [INVENTED] Not in the paper. Reads a subtitle track that already exists in the container;
#     no speech recognition at all, and nothing to transcribe when the video has no captions.
CAPTION_TRACK_EXTRACTOR = ExecutorSpec(
    name="caption_track_extractor",
    kind=ExecutorKind.TOOL,
    description=(
        "Caption track extraction tool: reads a subtitle or closed-caption track already embedded "
        "in the video file and returns it as text. Performs no speech recognition, so it yields "
        "nothing for videos that ship without captions."
    ),
    inputs=(Port(name="scenes", type=SCENES),),
    outputs=(Port(name="transcript", type=TRANSCRIPT),),
    parameters=(cores_knob(),),
)

# --- [INVENTED] An audio-capable multi-modal LLM transcribing directly. Like `vlm_scene_detector`,
#     the only candidate on this sub-task that Appendix A.5 can price at all.
VLM_TRANSCRIBER = ExecutorSpec(
    name="vlm_transcriber",
    kind=ExecutorKind.LLM,
    description=(
        "An audio-capable multi-modal LLM that listens to each scene and writes out what is said, "
        "transcribing directly instead of calling a dedicated recognition model."
    ),
    inputs=(Port(name="scenes", type=SCENES),),
    outputs=(Port(name="transcript", type=TRANSCRIPT),),
    parameters=(video_qa_model_knob(),),
)

# =============================================================================================
# 4. q_a :: (Query, [Frames | AnnotatedFrames | Transcript]) -> Answer
#    Listing 2 line 5: "Answer the query given some context."
#    Figure 1a: "Q/A (LLM)" -> "Answer".
# =============================================================================================
#
# The second port is VARIADIC and heterogeneous, because Listing 2 line 11 is
# `answer = q_a(query, [frames, transcript])` -- the paper's own counter-example to homogeneous
# variadic ports, and the reason M1 corrected its Section 4.3 rule during implementation.
#
# It also accepts a SUBSET of its element types, which is what makes decision Q6's Option 5 work:
# a configuration that prunes the `stt` node still type-checks with only frames arriving here.

_CONTEXT_PORT = dict(
    name="context",
    type=FRAMES,
    variadic=True,
    also_accepts=(ANNOTATED_FRAMES, TRANSCRIPT),
)

# --- [PAPER] Figure 1a's "Q/A (LLM)" node (p.568); Section 2.2 item 5 (p.568): "Multi-modal LLM
#     (or LMM) to answer the user query given the processed frames and audio transcript";
#     Listing 1 line 16 (p.569) `question_answer = LLM(...)`.
MULTIMODAL_LLM_QA = ExecutorSpec(
    name="multimodal_llm_qa",
    kind=ExecutorKind.LLM,
    description=(
        "A multi-modal LLM that answers the user's query in one pass, given the query itself and "
        "the processed context gathered from the video, such as extracted frames and an audio "
        "transcript."
    ),
    inputs=(Port(name="query", type=QUERY), Port(**_CONTEXT_PORT)),
    outputs=(Port(name="answer", type=ANSWER),),
    parameters=(video_qa_model_knob(),),
)

# --- [PAPER-FORM] Self-reflection is form 2, Section 3.2 (p.572): "a self-reflection or an
#     LLM-Debate pattern built from multiple LLMs". The paper REALIZES it for Math Q/A (Figure 15,
#     p.585: "Multi-Round Self-Reflect", Reflect/Re-Answer arcs). Applying it to video Q/A is ours.
#     `R`'s domain {2,4} is inherited from Table 6 (Code Generation) and was never measured for
#     this workflow -- decision Q8, gap A26.
MULTIMODAL_LLM_QA_SELFREFLECT = ExecutorSpec(
    name="multimodal_llm_qa_selfreflect",
    kind=ExecutorKind.COMPOSITION,
    description=(
        "Self-reflection composition over a multi-modal LLM: it drafts an answer from the video "
        "context, then re-reads the context to critique and revise its own answer over several "
        "rounds. One agent, no second opinion."
    ),
    inputs=(Port(name="query", type=QUERY), Port(**_CONTEXT_PORT)),
    outputs=(Port(name="answer", type=ANSWER),),
    parameters=(rounds_knob(), video_qa_model_knob()),
)

# --- [PAPER-FORM] LLM-Debate is form 2 (Section 3.2, p.572) and is the Code Generation structure
#     (Figure 1b, p.568). Applying it to video Q/A is ours; `D`/`R` domains inherited from Table 6
#     (A26).
MULTIMODAL_DEBATE_QA = ExecutorSpec(
    name="multimodal_debate_qa",
    kind=ExecutorKind.COMPOSITION,
    description=(
        "LLM Debate composition over multi-modal agents: several agents each answer the query "
        "from the video context, then debate their disagreements over several rounds until they "
        "converge on one answer. Many agents, many rounds."
    ),
    inputs=(Port(name="query", type=QUERY), Port(**_CONTEXT_PORT)),
    outputs=(Port(name="answer", type=ANSWER),),
    parameters=(debaters_knob(), rounds_knob(), video_qa_model_knob()),
)

# NOTE (decision Q11, 2026-09-11): there is deliberately NO Tool option for `q_a`. A tool-servable
# answer node would allow a Video Q/A DAG in which every stage is a Tool -- a whole workflow
# Appendix A.5 prices at exactly zero across all four objectives. Three of the four sub-tasks
# already expose that gap; a fourth would be gratuitous invention.


# =============================================================================================
# The catalogue
# =============================================================================================

VIDEO_QA_EXECUTORS: Final[tuple[ExecutorSpec, ...]] = (
    # scene_detect
    OPENCV_SCENE_DETECTOR,
    FIXED_INTERVAL_SEGMENTER,
    VLM_SCENE_DETECTOR,
    # frame_extract
    OPENCV_FRAME_EXTRACTOR,
    OMDET_FRAME_ANNOTATOR,
    CLIP_FRAME_ANNOTATOR,
    VLM_FRAME_CAPTIONER,
    # stt
    WHISPER_STT,
    CAPTION_TRACK_EXTRACTOR,
    VLM_TRANSCRIBER,
    # q_a
    MULTIMODAL_LLM_QA,
    MULTIMODAL_LLM_QA_SELFREFLECT,
    MULTIMODAL_DEBATE_QA,
)
"""Declaration order is grouped by sub-task and is the orchestrator's documented tie-break order.

Names are join keys for Milestone 3's profiles and appear verbatim in the orchestrator prompt, so
they are frozen once published -- the same rule the Code Generation catalogue carries.
"""


GROUNDING: Final[dict[str, str]] = {
    "opencv_scene_detector": "PAPER",  # Listing 1 p.569; Section 2.3 p.569
    "fixed_interval_segmenter": "INVENTED",
    "vlm_scene_detector": "INVENTED",
    "opencv_frame_extractor": "PAPER",  # Section 3.2 p.572 (knobs F + cores); Listing 1 p.569
    "omdet_frame_annotator": "PAPER-FORM",  # OmDet named p.575; folding into frame_extract is ours
    "clip_frame_annotator": "PAPER",  # CLIP named in Listing 1 p.569
    "vlm_frame_captioner": "INVENTED",
    "whisper_stt": "PAPER",  # Listing 1 p.569; Section 4.1 p.575; Section 4.6 p.578
    "caption_track_extractor": "INVENTED",
    "vlm_transcriber": "INVENTED",
    "multimodal_llm_qa": "PAPER",  # Figure 1a p.568; Section 2.2 item 5 p.568
    "multimodal_llm_qa_selfreflect": "PAPER-FORM",  # form 2 named p.572; realized for Math Q/A
    "multimodal_debate_qa": "PAPER-FORM",  # form 2 named p.572; realized for Code Generation
}
"""How each entry relates to the paper. Machine-readable so the source and the design document
cannot drift apart; asserted in tests."""

NOT_NAMED_BY_THE_PAPER: Final[frozenset[str]] = frozenset(
    name for name, grounding in GROUNDING.items() if grounding != "PAPER"
)
"""The eight entries the paper does not name as Video Q/A executors: five pure inventions and
three realizations of a form or backend the paper names but applies elsewhere."""


# ---------------------------------------------------------------------------------------------
# The parallel branch -- what this workflow exists to make demonstrable
# ---------------------------------------------------------------------------------------------
#
# Listing 2's data flow is:
#
#                        +--> frame_extract --+
#     videos -> scene_detect                  +--> q_a --> answer
#                        +--> stt ------------+
#     query ---------------------------------->
#
# `frame_extract` and `stt` are independent: neither consumes the other's output, both consume
# `scenes`, both feed `q_a`. Section 4.6 (p.578) schedules exactly this branch -- Figure 12a:
# "The two sub-tasks run in near-perfect parallel, with full overlap in execution"; Figure 12c:
# "Both sub-tasks complete nearly simultaneously".
#
# Appendix A.5 cannot express any of it. Latency appears ONLY as filter eq. (5)/(9),
# `l^TTFT_m + t_c * l^TPOT_m > tau_{w,s}` -- one model's TTFT plus that model's per-output-token
# time, times the whole configuration's token count. No per-task term, so neither `+` nor `max`
# over branches; no makespan term in objectives (11)-(13), so overlap earns nothing; and three of
# these four stages (OpenCV, OmDet/CLIP, Whisper -- Section 4.1 p.575 names three DIFFERENT
# serving engines) generate no LLM tokens at all, so the branch the paper co-schedules contributes
# approximately zero to the only latency expression the optimizer has.
#
# Consequence, and the reason Video Q/A was un-deferred: on this DAG the SLO filter can certify a
# configuration that misses `LOW_LATENCY` (a long non-token branch adds wall-clock eq. (5) cannot
# see) and reject one that meets it (overlapping branches are charged as one serialized stream).
# Code Generation is a total order and could not show either.
#
# M2b adds the DAG, not a scheduler. M1's standing rule holds: the Logical Workflow keeps its
# typed edges because Section 3.2 (p.573) says "edges denote data flow", and M4/M5 must not read
# them for scheduling because Appendix A.5 does not.

register_catalogue("video_qa", VIDEO_QA_EXECUTORS)
