"""
The Logical Workflow must be request-agnostic and unconfigured.

Covers Murakkab (OSDI '26), Section 3.2, "Logical Workflow" (p.573):
  "This abstract execution plan captures the functional intent of each task without binding to
   specific models, resources, or hardware. ... This representation remains request-agnostic,
   containing no per-request details such as query text, input payloads, or SLOs. Execution
   specifics (e.g., model selection or hardware allocation) are deferred to later stages."

These are assertions, not assumptions: the request literals are taken from the spec's own
execution section and searched for in the serialized DAG.
"""

from __future__ import annotations

import dataclasses
import json

import pytest

from development.executor_library import code_generation_library
from development.orchestrator import WorkflowOrchestrator
from development.spec_parser import parse_spec_file
from shared.executor import ExecutionPreferences, ParameterSpec
from shared.llm_client import MockLLMClient
from shared.model_ids import ALL_MODEL_IDS, CODE_GEN_MODELS
from shared.workflow import (
    FORBIDDEN_FIELD_NAMES,
    InputBinding,
    LogicalEdge,
    LogicalNode,
    LogicalWorkflow,
    audit_request_agnostic,
)

SPEC_PATH = "development/specs/code_generation.py"

EXPECTED = {
    "propose_solutions": "llm_debate_coders",
    "write_tests": "llm_unit_test_writer",
    "execute_tests": "python_interpreter",
    "rank_solutions": "llm_ranker",
}


@pytest.fixture()
def result():
    llm = MockLLMClient(mode="fixture", fixture=EXPECTED)
    return WorkflowOrchestrator(code_generation_library(), llm).orchestrate_file(SPEC_PATH)


@pytest.fixture()
def execution_section():
    _, section = parse_spec_file(SPEC_PATH)
    return section


def test_no_request_literal_reaches_the_workflow(result, execution_section):
    """The example query in the spec's execution section must not appear anywhere in the DAG."""
    assert execution_section.literals  # the spec really does contain a request
    violations = audit_request_agnostic(result.workflow, execution_section.literals)
    assert violations == ()


def test_no_slo_reaches_the_workflow(result, execution_section):
    """The SLO enters at `run(workflow(query), slo=...)`, outside the workflow definition."""
    assert execution_section.slo == "HIGH_ACCURACY"
    blob = result.workflow.to_json()
    assert "HIGH_ACCURACY" not in blob
    for token in ("slo", "SLO", "LOW_LATENCY", "deadline"):
        assert token not in blob


def _blob_without_knob_domains(workflow) -> str:
    """The serialized DAG with every knob DOMAIN stripped out.

    Milestone 2 gave the `model` knob a real domain -- the five Code Generation model ids of
    Table 6 (p.586) and Figure 4b (p.571) -- where M1's stub had `domain=None`. So model NAMES now
    legitimately appear in the DAG, inside the declared domain of an UNVALUED parameter.

    That is a declaration of what may be chosen, not a binding: Section 3.2 (p.573) forbids
    "binding to specific models, resources, or hardware", and M1's own DESIGN.md Section 4.2
    requires the orchestrator to be shown "parameter names and domains". Distinguishing the two is
    this helper's job; the assertions below are correspondingly SHARPER than the substring scan
    they replace, which could not tell a domain from a binding.
    """
    document = json.loads(workflow.to_json())
    for node in document["nodes"]:
        for parameter in node.get("open_parameters", []):
            parameter.pop("domain", None)
    return json.dumps(document).lower()


def test_no_model_or_hardware_binding_reaches_the_workflow(result):
    """"without binding to specific models, resources, or hardware" (Section 3.2, p.573)."""
    blob = _blob_without_knob_domains(result.workflow)
    for token in ("llama", "gpt", "phi-4", "gemma", "deepseek", "whisper", "a100", "h100", "gpu"):
        assert token not in blob


def test_model_names_appear_only_as_an_unbound_knob_domain(result):
    """Every model id in the DAG must sit in the `domain` of an unvalued `model` parameter.

    Section 3.2 (p.572): the orchestrator defers "parameter configuration to a later optimization
    phase (Section 3.3)". A domain is the hole's shape; a value would be configuration.
    """
    document = json.loads(result.workflow.to_json())
    seen_model_knob = False
    for node in document["nodes"]:
        for parameter in node["open_parameters"]:
            assert "value" not in parameter
            if parameter["name"] == "model":
                seen_model_knob = True
                assert parameter["domain"] == list(CODE_GEN_MODELS)
            else:
                # no other knob may smuggle a model name in
                assert not any(
                    isinstance(v, str) and v in ALL_MODEL_IDS for v in parameter.get("domain") or ()
                )
    assert seen_model_knob  # the Code Gen DAG really does carry a model knob to defer


def test_dag_dataclasses_declare_no_forbidden_fields():
    """Structural guarantee: the DAG types have nowhere to PUT a query, payload, SLO, model or
    hardware binding."""
    for dag_type in (LogicalWorkflow, LogicalNode, LogicalEdge, InputBinding):
        for field in dataclasses.fields(dag_type):
            assert field.name not in FORBIDDEN_FIELD_NAMES


def test_parameters_have_no_value_field():
    """Section 3.2 (p.572) defers "parameter configuration to a later optimization phase"; a
    ParameterSpec is a hole, so it cannot carry a configured value at all."""
    names = {f.name for f in dataclasses.fields(ParameterSpec)}
    assert "value" not in names
    assert names == {"name", "kind", "domain", "description"}


def test_every_node_still_has_open_parameters(result):
    """The workflow leaves work for the optimizer rather than pre-empting it."""
    for node in result.workflow.nodes:
        assert node.open_parameters
        for parameter in node.open_parameters:
            assert isinstance(parameter, ParameterSpec)


def test_boundary_inputs_carry_names_and_types_but_no_values(result):
    for port in result.workflow.inputs:
        assert port.name and port.type
        assert not hasattr(port, "value")
    assert [p.name for p in result.workflow.inputs] == ["query"]  # a NAME, not a query string


def test_workflow_is_reusable_across_requests(result):
    """Request-agnostic means one DAG serves every request of this workflow type, which is what
    lets profiling and optimization amortize (Section 3.3, p.573)."""
    second = WorkflowOrchestrator(
        code_generation_library(), MockLLMClient(mode="fixture", fixture=EXPECTED)
    ).orchestrate_file(SPEC_PATH)
    assert second.workflow == result.workflow


def test_execution_preferences_travel_beside_the_dag_not_inside_it():
    """Section 3.2 (p.573): "Murakkab does not restrict developers from specifying any execution
    preferences ... which are then incorporated into the optimization process as constraints."

    They are allowed, but they must not bind the DAG to a model or hardware.
    """
    preferences = ExecutionPreferences(
        allowed_models=("Phi-4",), hardware_constraints={"gpu": "A100"}
    )
    result = WorkflowOrchestrator(
        code_generation_library(), MockLLMClient(mode="fixture", fixture=EXPECTED)
    ).orchestrate_file(SPEC_PATH, preferences=preferences)

    assert result.preferences is preferences
    assert not preferences.is_empty()
    blob = result.workflow.to_json()
    assert "A100" not in blob

    # UPDATED IN MILESTONE 2. This used to assert `"Phi-4" not in blob`, which no longer
    # distinguishes a leak from the ordinary `model` knob domain (every model knob now lists all
    # five Code Gen model ids). The stronger property, and the one the paper actually requires, is
    # that a stated preference does NOT narrow or otherwise touch the DAG: preferences are
    # "incorporated into the optimization process as constraints" (Section 3.2, p.573) at M4, so
    # the logical workflow must be byte-identical with and without them.
    unconstrained = WorkflowOrchestrator(
        code_generation_library(), MockLLMClient(mode="fixture", fixture=EXPECTED)
    ).orchestrate_file(SPEC_PATH)
    assert result.workflow == unconstrained.workflow
    for node in result.workflow.nodes:
        for parameter in node.open_parameters:
            if parameter.name == "model":
                assert parameter.domain == CODE_GEN_MODELS  # not narrowed to ("Phi-4",)


def test_workflow_is_json_serializable(result):
    """Section 3.2 (p.573): "A feedback loop allows developers to inspect and refine the
    generated specification"."""
    blob = result.workflow.to_json(indent=2)
    assert '"workflow_id": "code_generation"' in blob
    assert '"executor": "llm_debate_coders"' in blob
