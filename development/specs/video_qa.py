# Declarative workflow specification: Video Q/A.
#
# This file is Murakkab (OSDI '26), Listing 2 (p.572), reproduced CHARACTER-FOR-CHARACTER below
# the header comments. Caption: "Murakkab's declarative workflow specification of the video Q/A
# abstracts away configuration details, letting developers focus on application logic."
#
# Unlike the Code Generation spec -- which the paper never writes down, so M1 had to construct it
# (gap A1) -- this one is given verbatim. It is therefore NOT paraphrased, reordered, renamed or
# "improved" in any way. The same text is embedded in
# tests/test_spec_parser.py::test_parses_the_papers_own_listing_2, which has asserted since
# Milestone 1 that M1's AST parser handles it unchanged.
#
# Contrast with Listing 1 (p.569), the imperative straw-man for the SAME workflow: it hardcodes
# `Whisper`, `CLIP`, `Llama-3.2`, `{"num_frames": 15}`, `{"CPUs": 32}`, `{"GPUs": 8, "Type":
# "H100"}` and API keys inline. None of that appears here: "Configuration details (e.g., which LLM
# to use, number of frames to extract, resource allocation) are omitted from the specification"
# (Section 3.2, p.573).
#
# Two structural notes, both consequences of reproducing Listing 2 literally:
#   * PARALLEL BRANCH. `frame_extract(scenes)` and `stt(scenes)` are independent and both feed
#     `q_a` -- the first genuine fan-out/fan-in in this repo, and the DAG Section 4.6 (p.578)
#     co-schedules (Figure 12a: "near-perfect parallel, with full overlap in execution").
#     Appendix A.5 has no precedence constraint and no makespan term, so this is where that gap
#     becomes demonstrable. See development/executor_lib/video_qa.py.
#   * FOUR SUB-TASKS, NOT FIVE. Figure 1a (p.568) and Section 2.2 (p.568) describe an Object
#     Detector agent; Listing 2 has no object-detection sub-task and feeds `stt` the scenes rather
#     than a separate audio stream. Listing 2 wins here because it is the only declarative
#     description the paper gives. Gaps A22/A23 in DESIGN_VIDEO_QA.md.
#
# This file is PARSED, never executed (see development/spec_parser.py).

# == Sub-tasks in the workflow ==
scene_detect  = "Given a list of videos, identify scenes in each."
frame_extract = "Given a list of scenes, extract frames."
stt           = "Given a list of scenes, convert audio to text."
q_a           = "Answer the query given some context."
# == Workflow description (sub-tasks and data flow) ==
def workflow(query, videos):
    scenes     = scene_detect(videos)
    frames     = frame_extract(scenes)
    transcript = stt(scenes)
    answer     = q_a(query, [frames, transcript])
    return answer
# == Execution with example request ==
query  = "What is the name of the person wearing the red dress?"
videos = ["road_trip.mp4"]
result = run(workflow(query, videos), slo=LOW_LATENCY)
