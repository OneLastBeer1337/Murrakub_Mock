# Topic 2 — paper confirmations, one claim at a time

**Purpose.** Record what the actual OSDI paper says before deciding whether an open method belongs in the presentation. Source: Chaudhry et al., *Murakkab: Resource-Efficient Agentic Workflow Orchestration in Cloud Platforms*, local PDF `C:/Users/darkn/Downloads/osdi26-chaudhry (1).pdf`. “Not specified” means not found in the checked paper text/figures, not proof that the authors had no private implementation. The user will decide presentation relevance item by item.

## 1. How an executor is chosen for a new task

**Paper check:** OSDI §3.2 (printed pp. 571–573), Table 1, and the remaining main text and appendices for mentions of orchestrator, executor assignment, prompt, ranking, feedback and onboarding. The §4.4 dynamic coding example also mentions an orchestrator choosing writer specialization per request, but does not give a general selection protocol.

| Question | Confirmed from the paper |
|---|---|
| What is the search space? | A finite, known library of models, compositions and tools. Each exposes a description, interface and configurable parameters. If no suitable executor exists, the developer is asked to onboard one (§3.2, printed pp. 571–572). |
| What does the orchestrator receive? | An LLM with tool-calling capabilities receives the list of available executors and their interfaces plus task descriptions, then selects an executor for each subtask (§3.2, p. 573). The paper says descriptions and interfaces are used to rank and assign executors (p. 572). |
| What validation follows? | The logical DAG is type checked; a mismatch causes regeneration with error feedback to the LLM. Persistent errors go to the developer (§3.2, p. 573). The logical workflow is request-agnostic, and model/hardware choices are deferred. |
| What is not made reproducible? | The exact orchestrator model/version, prompt or tool-call schema, scoring rule for “best,” criterion for “none found,” number of retries, and an executor-assignment accuracy evaluation were not located in these sections or elsewhere in the OSDI text. |

**What the repository does.** [WorkflowOrchestrator](../development/orchestrator.py) implements the stated flow through an abstract client and bounds attempts at three—an explicit repository choice. [MockLLMClient](../shared/llm_client.py) exercises keyword or fixture selection; [prompting.py](../development/prompting.py) renders descriptions/interfaces and task dependencies. This tests plumbing and type feedback, not fidelity to the authors' LLM choices. The paper says the LLM receives the available-executor list, so a **retrieval stage is not a missing paper step**. Retrieval could be tested later as a scalability improvement to this component.

**Presentation-safe wording:** “Murakkab specifies an LLM-based executor assignment pipeline and type-feedback loop, but does not give enough detail to reproduce its executor choices for a new task.”

**Presentation relevance:** **Pending user judgment.** This is relevant if the presentation needs to explain why our Phase 1 executor assignments may diverge from Murakkab. It is less central if the eventual project focuses entirely on profiling, optimization or runtime. Do not frame it as “Murakkab has no executor selection method.”

**Next item:** workflow profiling protocol—what the paper actually says about benchmark data, token sampling and profile updates.
