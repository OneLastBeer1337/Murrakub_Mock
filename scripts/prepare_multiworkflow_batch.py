"""
Domain preparation: turn real, multi-machine Zookeeper log data (LogHub) into a concrete
batch of concurrent workflow instances, matching the project's DAG format and offline
batch scope (Architecture_Design.md §2.4).

This directly answers the professor's requirement: evaluation must show 2-3 concurrent
workflows under real, observable load -- not a simulated approximation.
"""

import re
import json
from collections import defaultdict

SEVERITY_MAP = {"ERROR": "critical", "WARN": "warning", "INFO": "normal"}
LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - "
    r"(?P<level>INFO|WARN|ERROR|FATAL|DEBUG)\s+"
    r"\[(?P<thread>[^\]]*)\] - (?P<msg>.*)$"
)
HOST_RE = re.compile(r"/(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})")
CLIENT_RE = re.compile(r"client /(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})")
NON_HOST_ADDRS = {"0.0.0.0"}

def extract_host(line):
    """Prefer the explicit 'client /X.X.X.X' address when present (the actual remote
    party), since a naive first-IP-match tends to pick up Zookeeper's own listener
    bind address (0.0.0.0) instead of anything meaningful."""
    client_match = CLIENT_RE.search(line)
    if client_match:
        return client_match.group(1)
    for candidate in HOST_RE.findall(line):
        if candidate not in NON_HOST_ADDRS:
            return candidate
    return None

def parse_zookeeper_log(path):
    """Parse raw Zookeeper log lines into structured records, grouped by source host."""
    by_host = defaultdict(list)
    unattributed = []
    with open(path, encoding="utf-8", errors="ignore") as f:
        for raw in f:
            line = raw.rstrip("\r\n")
            m = LINE_RE.match(line)
            if not m:
                continue
            host_match = HOST_RE.search(line)
            host = extract_host(line)
            record = {
                "timestamp": m.group("ts"),
                "severity_raw": m.group("level"),
                "severity_ground_truth": SEVERITY_MAP.get(m.group("level"), "normal"),
                "thread": m.group("thread"),
                "message": m.group("msg"),
            }
            if host:
                by_host[host].append(record)
            else:
                unattributed.append(record)
    return by_host, unattributed

def build_workflow_instance(workflow_id, host, records):
    """Package one host's log segment as one DAG workflow instance, matching the
    project's task_type structure (parse_log_line -> classify_severity + enrich_context
    -> generate_report)."""
    return {
        "workflow_id": workflow_id,
        "source": f"zookeeper-host-{host}",
        "dag": {
            "nodes": [
                {"id": "n1", "task_type": "parse_log_line"},
                {"id": "n2", "task_type": "classify_severity", "depends_on": ["n1"]},
                {"id": "n3", "task_type": "enrich_context", "depends_on": ["n1"]},
                {"id": "n4", "task_type": "generate_report", "depends_on": ["n2", "n3"]},
            ]
        },
        "input_data": {
            "log_lines": len(records),
            "records": records,
        },
        "ground_truth": {
            "severity_counts": {
                sev: sum(1 for r in records if r["severity_ground_truth"] == sev)
                for sev in set(SEVERITY_MAP.values())
            },
            "total_incidents_expected": sum(
                1 for r in records if r["severity_ground_truth"] in ("critical", "warning")
            ),
        },
    }

if __name__ == "__main__":
    by_host, unattributed = parse_zookeeper_log("zookeeper_sample.log")

    print("=" * 70)
    print("DOMAIN PREP — Zookeeper log data, parsed and grouped by real host")
    print("=" * 70)
    print(f"Total lines parsed: {sum(len(v) for v in by_host.values()) + len(unattributed)}")
    print(f"Distinct hosts found: {len(by_host)}")
    print(f"Lines with no attributable host (dropped from workflow assignment): {len(unattributed)}")
    print()

    # Pick the 3 hosts with the most log lines -- the most substantial, realistic
    # concurrent workloads to actually exercise the shared-pool contention
    top_hosts = sorted(by_host.items(), key=lambda kv: -len(kv[1]))[:3]

    print("Selected 3 hosts for the concurrent-workflow batch:")
    for host, records in top_hosts:
        sev_counts = defaultdict(int)
        for r in records:
            sev_counts[r["severity_ground_truth"]] += 1
        print(f"  {host}: {len(records)} lines  "
              f"(normal={sev_counts['normal']}, warning={sev_counts['warning']}, critical={sev_counts['critical']})")

    batch = {
        "batch_id": "eval-batch-001",
        "description": "3 concurrent OS/infrastructure incident-detection workflow instances, "
                        "real multi-host Zookeeper log data, offline batch (fixed before optimization)",
        "workflows": [
            build_workflow_instance(f"wf-{i+1}", host, records)
            for i, (host, records) in enumerate(top_hosts)
        ],
    }

    out_path = "eval_batch_3workflows.json"
    with open(out_path, "w") as f:
        json.dump(batch, f, indent=2)

    print()
    print(f"Wrote {out_path}")
    print(f"Total workflow instances in this batch: {len(batch['workflows'])}")
    total_lines = sum(w["input_data"]["log_lines"] for w in batch["workflows"])
    total_incidents = sum(w["ground_truth"]["total_incidents_expected"] for w in batch["workflows"])
    print(f"Total log lines across all 3 concurrent workflows: {total_lines}")
    print(f"Total real incidents (warning+critical) to detect across the batch: {total_incidents}")
