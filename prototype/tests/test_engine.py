"""
Tests for the Concrete WorkflowExecutionEngine (J5/J6) and Full Pipeline Mockup.
"""

import pytest
from pathlib import Path

from poc.formulation.types import TaskId
from prototype.engine import ProfileRuntimeState, WorkflowExecutionEngine
from prototype.ingestion import InvalidBatch, TaskTypeSpec, ingest
from prototype.pipeline_mockup import run_pipeline_mockup

MANIFEST_PATH = Path("data/eval_batches/eval_batch_3workflows.json")
SPECS = {
    "parse_log_line":    TaskTypeSpec(6.0, 0.90, 200.0),
    "classify_severity": TaskTypeSpec(4.0, 0.85, 200.0),
    "enrich_context":    TaskTypeSpec(3.0, 0.80, 200.0),
    "generate_report":   TaskTypeSpec(5.0, 0.85, 200.0),
}


def test_acyclic_validation_detects_cycles(tmp_path):
    """G4: Cyclic workflow DAGs must be rejected loudly at ingestion."""
    bad_manifest = {
        "batch_id": "cyclic-batch",
        "workflows": [
            {
                "workflow_id": "wf-cycle",
                "dag": {
                    "nodes": [
                        {"id": "n1", "task_type": "parse_log_line", "depends_on": ["n2"]},
                        {"id": "n2", "task_type": "classify_severity", "depends_on": ["n1"]}
                    ]
                }
            }
        ]
    }
    p = tmp_path / "cyclic.json"
    import json
    p.write_text(json.dumps(bad_manifest), encoding="utf-8")

    with pytest.raises(InvalidBatch, match="contains a dependency cycle"):
        ingest(p, SPECS)


def test_input_based_load_scaling_differentiates_tasks():
    """G1: Tasks across workflows with different input sizes have distinct loads."""
    batch_scaled = ingest(MANIFEST_PATH, SPECS, scale_load_by_input=True)
    loads_by_wf = {}
    for t in batch_scaled.tasks:
        if t.task_type == "parse_log_line":
            loads_by_wf[t.id.workflow_id] = t.load

    # wf-1 has 181 lines, wf-2 has 150 lines, wf-3 has 138 lines
    assert loads_by_wf["wf-1"] > loads_by_wf["wf-2"]
    assert loads_by_wf["wf-2"] > loads_by_wf["wf-3"]


def test_engine_executes_real_log_records_end_to_end():
    """J5/J6: Real Zookeeper log lines flow from parser to report generator."""
    batch = ingest(MANIFEST_PATH, SPECS)
    engine = WorkflowExecutionEngine(raw_manifest=batch.raw_manifest, tasks=batch.as_list(), seed=42)

    routing = {
        TaskId("wf-1", "n1"): "parse_log_line-cheap",
        TaskId("wf-1", "n2"): "classify_severity-cheap",
        TaskId("wf-1", "n3"): "enrich_context-cheap",
        TaskId("wf-1", "n4"): "generate_report-cheap",
    }
    wf_manifest = [w for w in batch.raw_manifest["workflows"] if w["workflow_id"] == "wf-1"][0]
    output, obs = engine.execute_workflow("wf-1", wf_manifest, routing)

    assert output.workflow_id == "wf-1"
    assert output.status == "SUCCESS"
    assert output.log_lines_processed == 181
    assert "Incident Detection Report: wf-1" in output.report_text
    assert len(obs) >= 4


def test_load_scaled_observation_counts():
    """G3: High-load tasks emit more observations than low-load tasks."""
    batch = ingest(MANIFEST_PATH, SPECS)
    engine = WorkflowExecutionEngine(raw_manifest=batch.raw_manifest, tasks=batch.as_list(), seed=0)

    routing = {t.id: f"{t.task_type}-solid" for t in batch.tasks}
    obs = engine.execute(routing)

    # 12 tasks; tasks with load 6 emit 2 obs, load 3 emit 1 obs -> 18 total
    assert len(obs) == 18


def test_pipeline_mockup_runs_cleanly(capsys):
    """J1-J10: Full pipeline mockup executes with zero exceptions."""
    run_pipeline_mockup(budget=8, use_track="C")
    captured = capsys.readouterr()
    assert "ORCHESTRATION PIPELINE MOCKUP — SYSTEM ARCHITECTURE v4" in captured.out
    assert "J9: Automated Global Re-Optimization" in captured.out
    assert "Mockup execution completed successfully" in captured.out
