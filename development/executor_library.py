"""
Compatibility shim -- the Executor Library now lives in `development/executor_lib/`.

Implements Murakkab (OSDI '26), Section 3.2, "Executor Library" (p.572), by re-export only.

Milestone 1 shipped a deliberately minimal five-entry catalogue in this module, with the note
"Building the real catalogue is Milestone 2". Milestone 2 has done that: the catalogue is now 13
executors covering all four Code Generation sub-tasks with genuine alternatives per sub-task
(see `development/executor_lib/DESIGN.md`, Sections 1.3 and 4).

The definitions moved rather than being duplicated -- two competing catalogues in one tree is
exactly how M3 ends up profiling one of them and M4 optimizing the other. This module survives
only so that Milestone 1's orchestrator and tests keep their import path:

    from development.executor_library import code_generation_library, InMemoryExecutorLibrary

New code should import from `development.executor_lib` directly.
"""

from __future__ import annotations

from development.executor_lib import (
    CODE_GENERATION_EXECUTORS,
    InMemoryExecutorLibrary,
    code_generation_library,
    default_library,
)

__all__ = [
    "CODE_GENERATION_EXECUTORS",
    "InMemoryExecutorLibrary",
    "code_generation_library",
    "default_library",
]
