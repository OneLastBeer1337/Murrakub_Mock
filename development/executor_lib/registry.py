"""
The library container: a flat, finite catalogue built from one or more per-workflow catalogues.

Implements Murakkab (OSDI '26), Section 3.2, "Executor Library" (p.572):
  "A key design choice in Murakkab is mapping a broad range of unknown tasks to executors that are
   built from a finite, known set of models and tools in the library. If none is found, Murakkab
   prompts the developer to onboard a suitable one."

`InMemoryExecutorLibrary` was written in Milestone 1 (`development/executor_library.py`) and is
MOVED here unchanged in behaviour. This module contains NO executor definitions -- those live in
per-workflow catalogue modules (`code_generation.py` today) and are registered below. That split
is DESIGN.md Section 8, point 1: adding a second workflow must be a registration, not a refactor.

Flat and finite, matching "a finite, known set": no retrieval layer, no embedding index, no
per-workflow filtering at selection time. Section 3.2 describes one shared executor ecosystem, so
`default_library()` offers every registered executor for every sub-task and lets the type-check
(Section 3.2, p.573) and the orchestrator's own judgement reject the irrelevant ones.
"""

from __future__ import annotations

from typing import Sequence

from development.errors import UnknownExecutorError
from shared.executor import ExecutorSpec


class InMemoryExecutorLibrary:
    """A flat, finite catalogue. No retrieval layer: the paper describes a known set."""

    def __init__(self, executors: Sequence[ExecutorSpec]) -> None:
        names = [e.name for e in executors]
        duplicates = {n for n in names if names.count(n) > 1}
        if duplicates:
            raise ValueError(f"duplicate executor names in library: {sorted(duplicates)}")
        self._executors: tuple[ExecutorSpec, ...] = tuple(executors)

    def all(self) -> tuple[ExecutorSpec, ...]:
        """Declaration order is stable and is the orchestrator's tie-break order."""
        return self._executors

    def get(self, name: str) -> ExecutorSpec:
        for executor in self._executors:
            if executor.name == name:
                return executor
        raise UnknownExecutorError(
            f"{name!r} is not in the executor library; available: "
            f"{[e.name for e in self._executors]}"
        )

    def __len__(self) -> int:
        return len(self._executors)


# ---------------------------------------------------------------------------------------------
# Catalogue registration
# ---------------------------------------------------------------------------------------------

CATALOGUES: dict[str, tuple[ExecutorSpec, ...]] = {}
"""workflow-domain name -> its executors. Insertion order is preserved and becomes the library's
declaration order, which is the orchestrator's documented tie-break order."""


def register_catalogue(domain: str, executors: Sequence[ExecutorSpec]) -> None:
    """Register a per-workflow catalogue under `domain` (e.g. "code_generation").

    Re-registration replaces, so that re-importing a module in a test session is idempotent.
    """
    CATALOGUES[domain] = tuple(executors)


def library_for(*domains: str) -> InMemoryExecutorLibrary:
    """Build a library from the named catalogues, in the order given."""
    executors: list[ExecutorSpec] = []
    for domain in domains:
        if domain not in CATALOGUES:
            raise KeyError(
                f"no catalogue registered for {domain!r}; registered: {sorted(CATALOGUES)}"
            )
        executors.extend(CATALOGUES[domain])
    return InMemoryExecutorLibrary(executors)


def default_library() -> InMemoryExecutorLibrary:
    """Every registered executor, as one flat menu.

    Today this is identical to `code_generation_library()`, because Code Generation is the only
    catalogue (Video Q/A, Math Q/A and OS-log analysis are deferred by CLAUDE.md; the Video Q/A
    decision is gated on the Milestone 3 boundary). The distinction is kept because the two stop
    being identical the moment a second catalogue is registered, and DESIGN.md Section 8.1 warns
    that the wider menu will change orchestrator behaviour on the existing Code Gen tests.
    """
    return library_for(*CATALOGUES)
