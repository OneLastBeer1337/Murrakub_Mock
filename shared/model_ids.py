"""
Model-name vocabulary: the domain of every `model` knob in the Executor Library.

Implements the `model` attribute of Murakkab (OSDI '26), Section 3.2, "Attributes" (p.572):
  "The LLM Debate composition exposes the knobs: D (number of debaters), R (number of rounds),
   and model (which LLM to use)."

NAMES ONLY. This module deliberately contains ZERO performance data -- no accuracy, latency,
TTFT/TPOT, throughput, energy, cost, or token counts. Those belong to Milestone 3 (Section 3.3,
"Workflow Profiles" and "Model Profiles", p.573), which will key its profiles on these exact
strings. A model id here is an opaque identifier; it acquires a GPU type, a tensor-parallelism
degree, and a performance envelope only when M3 pairs it into a model profile.

Why this file is in /shared and not in /development: M2 declares the domain and M3 joins profiles
onto it. If the two kept separate lists they would drift, and a profile keyed on a name no knob
can produce is silently dead.

--- Where the Code Generation model set comes from -------------------------------------------
Section 3.3.1, Decision 3 (p.574): "A profile encodes a specific model, GPU type, and parallelism
strategy, so choosing m implicitly fixes the hardware and parallelism degree." Hence: model NAMES
here; GPU/TP live with the profile in M3.

  DeepSeek-Qwen-32B    Table 6 (p.586) `Model` column; Figures 2c/2d (p.570); Figure 4b (p.571)
  Gemma-3-27B          Table 6; Figures 2c/2d; Section 4.1 LangGraph baseline (p.575)
  Phi-4                Table 6; Figures 2c/2d; Figure 4b
  NVLM-D-72B           Table 6; Figure 4b
  DeepSeek-Llama-70B   Figure 4b (p.571) configuration space ONLY -- it never appears in a
                       *chosen* Table 6 row.

[DESIGN CHOICE -- DESIGN.md A16, resolved as Q4 on 2026-09-10] The domain is the five-model union
from Figure 4b, not Table 6's four. Table 6 reports what the optimizer *chose*; Figure 4b (caption:
"Large space of workflow configurations") shows what it chose *from*. A knob domain is an input
space, so baking the paper's own outcome into it would beg the question at M4.
"""

from __future__ import annotations

from typing import Final

# --- Code Generation (Figure 1b, p.568; Table 6 + Figure 4b) ---------------------------------

DEEPSEEK_QWEN_32B: Final = "DeepSeek-Qwen-32B"
GEMMA_3_27B: Final = "Gemma-3-27B"
PHI_4: Final = "Phi-4"
NVLM_D_72B: Final = "NVLM-D-72B"
DEEPSEEK_LLAMA_70B: Final = "DeepSeek-Llama-70B"

CODE_GEN_MODELS: Final[tuple[str, ...]] = (
    DEEPSEEK_QWEN_32B,
    GEMMA_3_27B,
    PHI_4,
    NVLM_D_72B,
    DEEPSEEK_LLAMA_70B,
)
"""Domain of the `model` knob for every Code Generation executor. Order is stable and is the
order shown to the orchestrator LLM."""


# --- Video Q/A (Figure 1a, p.568; Table 5 + Figure 2a + Figure 4a) ---------------------------
#
#   Llava-OneVision-7B  Table 5 (p.585) `Model` column; Figure 2a (p.570); Figure 4a (p.571)
#   Gemma-3-27B         Table 5; Figure 2a; Figure 4a            -- SHARED with Code Generation
#   NVLM-D-72B          Table 5; Figure 2a; Figure 4a            -- SHARED with Code Generation
#   Llama-3.2-90B       Figure 4a (p.571) model legend. (Listing 1, p.569, hardcodes the smaller
#                       "Llama-3.2" in its imperative example; the profiled model is the 90B.)
#
# Whisper, OmDet and CLIP are deliberately ABSENT. Decision Q9 (2026-09-11): they are TOOL
# executors per Section 3.2 (p.572), "Traditional ML models are also included as tools", and a
# Tool *is* its backend -- it exposes no `model` knob, exactly like `python_interpreter`. The
# consequence is recorded as gaps A25/A31: the tool half of Section 3.3.1 Decision 2's promise
# ("the chosen model or tool for each executor") has no knob to ride on.

LLAVA_ONEVISION_7B: Final = "Llava-OneVision-7B"
LLAMA_3_2_90B: Final = "Llama-3.2-90B"

VIDEO_QA_MODELS: Final[tuple[str, ...]] = (
    LLAVA_ONEVISION_7B,
    GEMMA_3_27B,  # reused, not redeclared
    NVLM_D_72B,  # reused, not redeclared
    LLAMA_3_2_90B,
)
"""Domain of the `model` knob for Video Q/A executors (Table 5 p.585; Figures 2a/4a p.570-571)."""


ALL_MODEL_IDS: Final[frozenset[str]] = frozenset(CODE_GEN_MODELS) | frozenset(VIDEO_QA_MODELS)
"""Every model id known to the platform: the union across registered workflows.

`Gemma-3-27B` and `NVLM-D-72B` appear in both domains and are ONE id, never duplicated per
workflow -- M3 keys a single model profile on each string, and Section 4.3's multiplexing (p.576)
depends on two workflows being able to land on the *same* model instance.
"""


class UnknownModelError(ValueError):
    """Raised when a knob domain or (later) a profile references an unregistered model id."""


def validate_model_id(name: str) -> str:
    """Return `name` if it is a registered model id, else raise `UnknownModelError`."""
    if name not in ALL_MODEL_IDS:
        raise UnknownModelError(
            f"unknown model id {name!r}; registered ids are {sorted(ALL_MODEL_IDS)}"
        )
    return name
