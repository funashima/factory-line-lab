#!/usr/bin/env python3
"""Rebuild traceable simulator JSON from the supplied, unmodified source files.

Python 3.10+, standard library only. No network calls. Existing output JSON is
replaced only with --overwrite. Original source files are never modified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict, deque
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RETRIEVED = "2026-09-23"
ZDOI = "10.5281/zenodo.14441997"
ZURL = "https://zenodo.org/records/14441997"
SURL = "https://assembly-line-balancing.de/salbp/benchmark-data-sets-1993/"
SZIP = "https://assembly-line-balancing.de/wp-content/uploads/2017/01/SALBP-data-sets.zip"
EXPECTED = {
    "scholl1993/JACKSON.IN2": "70eaccc7b34dc4e65649888695e4cef4039e0dd810ad3a9c9b867718093de4ac",
    "scholl1993/MITCHELL.IN2": "96387ea78feb52efc96556f60fc02958adf8bf329c0503719ca1afc101117165",
    "scholl1993/HESKIA.IN2": "2b4558e1e1aa9c013a61bb08d917639398bd39acdf638c6eea30f44c51b80908",
    "scholl1993/README.DOC": "987e400302cd0573779fbe47808ad02521bb2cdc456da76825810336808b99d0",
    "zenodo_14441997/camunda-activity.json": "4b076db16761a0ccc300b150afe2284bf57e8f8afd68fe2e3b130c6b6eaed154",
    "zenodo_14441997/camunda-process.json": "e0c59de80c667baaa001fd44a1494874338dd5375f5b3db69040b53b3fc6cb07",
    "zenodo_14441997/production_process.bpmn": "cb68fc08e5f22d7fcf39f9eae36372b2572d75a590dad33891d31881781491f7",
}
SELECTION = {
    "processDefinitionKey": "production_process_new3",
    "processDefinitionVersion": 2,
    "start_local_date": "2023-04-11",
    "state": "COMPLETED",
    "activityType": "serviceTask",
    "processDefinitionId": "production_process_new3:2:912e1f83-c3fb-11ed-9ece-2a1b4c3d6e5f",
}
JP_NAMES = {
    "Activity_0aprosy": "HBWの原点調整",
    "Activity_0cr4src": "VGRの原点調整（前半）",
    "Activity_1lx6ugd": "HBWから取り出す",
    "Activity_107pam0": "炉まで運ぶ",
    "Activity_0jtoxii": "VGRの原点調整（後半）",
    "Activity_1e6xoye": "炉で処理する",
    "Activity_075b7q0": "WTで運ぶ",
    "Activity_0kh9pn6": "フライス盤を動かす",
    "Activity_147au71": "仕分ける",
    "Activity_0cwptph": "排出口まで運ぶ",
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def seconds(record):
    t0, t1 = (datetime.fromisoformat(record[k]) for k in ("startTime", "endTime"))
    duration = record["durationInMillis"] / 1000
    if not math.isclose((t1 - t0).total_seconds(), duration, abs_tol=1e-8):
        raise ValueError("Timestamp and duration disagree: " + record["id"])
    return duration


def topo(ids, edges):
    indegree = dict.fromkeys(ids, 0)
    children = defaultdict(list)
    for a, b in edges:
        if a not in indegree or b not in indegree or a == b:
            raise ValueError("Invalid edge")
        indegree[b] += 1
        children[a].append(b)
    todo = deque(sorted(k for k, v in indegree.items() if v == 0))
    order = []
    while todo:
        a = todo.popleft()
        order.append(a)
        for b in sorted(children[a]):
            indegree[b] -= 1
            if indegree[b] == 0:
                todo.append(b)
    if len(order) != len(ids):
        raise ValueError("Cycle")
    if len(set(edges)) != len(edges):
        raise ValueError("Duplicate edge")
    return order


def layout(ids, edges):
    levels, counts = {}, Counter()
    pred = defaultdict(list)
    for a, b in edges:
        pred[b].append(a)
    for nid in topo(ids, edges):
        level = max((levels[a] + 1 for a in pred[nid]), default=0)
        levels[nid] = level
    return {nid: {"x": float(235 * levels[nid]), "y": float(110 * sum(1 for a in ids[:i] if levels[a] == levels[nid]))}
            for i, nid in enumerate(ids)}


def base_model(nodes, edges, title, unit, kind, sources, assumptions, config):
    ids = [n["id"] for n in nodes]
    return {
        "meta": {
            "version": 2, "program": "1.0.0",
            "semantics": "AND-fork-join/FCFS/unlimited-buffer",
            "title": title, "time_unit": unit, "data_kind": kind,
            "retrieved_on": RETRIEVED, "sources": sources,
            "assumptions": assumptions,
            "provenance_warning": "GUI re-save drops extra source metadata; retain provenance.json and the original model.",
        },
        "nodes": nodes,
        "edges": [{"id": f"E{i:03}", "src": a, "dst": b} for i, (a, b) in enumerate(edges, 1)],
        "layout": layout(ids, edges),
        "simulation": config,
    }


def config(jobs=60, runs=1, interval=1.0):
    return dict(jobs=jobs, runs=runs, interval=interval, seed=42,
                improvement=0.1, sensitivity=True, all_traces=False)


def make_benchmarks(src):
    outputs, audit = {}, {}
    for name in ("JACKSON", "MITCHELL", "HESKIA"):
        path = src / "scholl1993" / (name + ".IN2")
        lines = path.read_text(encoding="ascii").splitlines()
        n = int(lines[0])
        times = list(map(int, lines[1:n+1]))
        edges, evidence = [], []
        for lineno, line in enumerate(lines[n+1:], n+2):
            if not line.strip() or line.strip() == "-1,-1":
                continue
            a, b = map(int, line.split(","))
            edges.append((f"N{a:02}", f"N{b:02}"))
            evidence.append(dict(source_line=lineno, source_pair=[a, b], model_pair=list(edges[-1])))
        nodes = [dict(id=f"N{i:02}", name=f"{name} task {i}",
                      service=dict(dist="constant", p1=t, p2=0), capacity=1)
                 for i, t in enumerate(times, 1)]
        stem = name.lower() + f"_{n}"
        assumptions = {
            "source_facts": "Task times and every listed precedence pair are unchanged.",
            "time_unit": "Not specified in IN2; abstract benchmark units, not assumed seconds.",
            "resource_capacity": "One dedicated resource per task is an added modeling assumption, not a source observation.",
            "source_problem": "SALBP assigns tasks to shared work stations; this simulator does not solve that assignment problem.",
            "variability": "No repeated measurements or standard deviations supplied; use constant, p2=0.",
            "configuration": "60 products, interval 1 and 10% improvement are chosen experiment conditions, not measurements.",
            "layout": "Generated display coordinates; not a physical factory floor plan.",
            "other": "Unlimited buffers, no transport delay, FCFS, all tasks once per product.",
        }
        source = dict(title="Scholl (1993), Data of Assembly Line Balancing Problems",
                      landing_url=SURL, download_url=SZIP, archive_member="precedence graphs/" + path.name,
                      local_path=str(path.relative_to(src.parent)), sha256=sha(path))
        model = base_model(nodes, edges, f"{name} / original deterministic task data",
                           "unspecified_benchmark_time_unit", "published_benchmark_not_event_log",
                           [source], assumptions, config())
        outputs[stem + ".json"] = model
        pred = defaultdict(list)
        for a, b in edges:
            pred[b].append(a)
        finish = {}
        mapping = {r["id"]: r["service"]["p1"] for r in nodes}
        for nid in topo(list(mapping), edges):
            finish[nid] = mapping[nid] + max((finish[a] for a in pred[nid]), default=0)
        audit[stem] = dict(
            source=source, assumptions=assumptions, task_count=n, edge_count=len(edges),
            task_time_sum=sum(times), task_time_max=max(times),
            single_product_critical_path_time=max(finish.values()),
            source_nodes=[dict(model_node=f"N{i:02}", source_task=i, source_line=i+1, task_time=t)
                          for i, t in enumerate(times, 1)],
            source_edges=evidence,
        )
    return outputs, audit


def make_smart_factory(src):
    raw = src / "zenodo_14441997"
    activities = json.loads((raw / "camunda-activity.json").read_text())
    processes = json.loads((raw / "camunda-process.json").read_text())
    for records in (activities, processes):
        if len({r["id"] for r in records}) != len(records):
            raise ValueError("Duplicate source record ID")
    ns = {"b": "http://www.omg.org/spec/BPMN/20100524/MODEL"}
    process = ET.parse(raw / "production_process.bpmn").getroot().find("b:process", ns)
    if process.attrib["id"] != SELECTION["processDefinitionKey"]:
        raise ValueError("BPMN process mismatch")
    elements = {e.attrib["id"]: e for e in process if "id" in e.attrib}
    flows = [(e.attrib["sourceRef"], e.attrib["targetRef"]) for e in process.findall("b:sequenceFlow", ns)]
    all_ids = {x for pair in flows for x in pair}
    all_order = topo(sorted(all_ids), flows)
    auto_order = [a for a in all_order if elements[a].tag.endswith("}serviceTask")]
    # The supplied production process is serial. Never flatten gateways silently.
    if any(e.tag.rsplit("}", 1)[-1].endswith("Gateway") for e in process):
        raise ValueError("Unexpected gateway: manual interpretation required")
    if any(Counter(a for a, b in flows)[k] > 1 or Counter(b for a, b in flows)[k] > 1 for k in all_ids):
        raise ValueError("Expected a serial production BPMN")
    if len(auto_order) != 10:
        raise ValueError("Expected ten service tasks")
    # All nine service-to-service links must really occur in the BPMN.
    auto_edges = list(zip(auto_order, auto_order[1:]))
    if not set(auto_edges) <= set(flows):
        raise ValueError("Unexpected intervening activity")
    selected = sorted([r for r in processes
                       if r["processDefinitionKey"] == SELECTION["processDefinitionKey"]
                       and r["processDefinitionVersion"] == SELECTION["processDefinitionVersion"]
                       and r["processDefinitionId"] == SELECTION["processDefinitionId"]
                       and r["state"] == "COMPLETED"
                       and r["startTime"][:10] == SELECTION["start_local_date"]], key=lambda r: r["startTime"])
    if len(selected) != 15:
        raise ValueError("Expected 15 selected completed cases")
    process_ids = {r["id"] for r in selected}
    selected_activities = [r for r in activities if r["processInstanceId"] in process_ids]
    observations = [r for r in selected_activities if r["activityType"] == "serviceTask"]
    source_index = {r["id"]: i for i, r in enumerate(activities)}
    pindex = {r["id"]: i for i, r in enumerate(processes)}
    ids = {aid: f"P{i:02}" for i, aid in enumerate(auto_order, 1)}
    stats, cases = [], []
    grouped = defaultdict(list)
    for r in observations:
        if r["activityId"] not in ids or r["canceled"] or r["endTime"] is None:
            raise ValueError("Invalid selected activity")
        if r["processDefinitionId"] != SELECTION["processDefinitionId"]:
            raise ValueError("Process version mismatch")
        if seconds(r) <= 0:
            raise ValueError("Non-positive automatic activity duration")
        grouped[r["activityId"]].append(r)
    for aid in auto_order:
        rows = grouped[aid]
        if len(rows) != len(selected) or len({r["processInstanceId"] for r in rows}) != len(selected):
            raise ValueError("Missing/repeated activity within a case")
        values = [seconds(r) for r in rows]
        stats.append(dict(model_node=ids[aid], activity_id=aid, name_source=elements[aid].get("name"),
                          name_ja=JP_NAMES[aid], n=len(values), mean_seconds=statistics.mean(values),
                          sample_sd_seconds=statistics.stdev(values), min_seconds=min(values),
                          median_seconds=statistics.median(values), max_seconds=max(values),
                          coefficient_of_variation=statistics.stdev(values)/statistics.mean(values)))
    for p in selected:
        seconds(p)
        rows_by_id = {r["activityId"]: r for r in observations if r["processInstanceId"] == p["id"]}
        rows = [rows_by_id[aid] for aid in auto_order]
        for r1, r2 in zip(rows, rows[1:]):
            if datetime.fromisoformat(r1["endTime"]) > datetime.fromisoformat(r2["startTime"]):
                raise ValueError("BPMN precedence violated")
        total = sum(seconds(r) for r in rows)
        span = (datetime.fromisoformat(rows[-1]["endTime"]) - datetime.fromisoformat(rows[0]["startTime"])).total_seconds()
        cases.append(dict(process_instance_id=p["id"], source_process_array_index=pindex[p["id"]],
                          start_time=p["startTime"], end_time=p["endTime"], full_process_seconds=seconds(p),
                          automatic_duration_sum_seconds=total, automatic_span_seconds=span,
                          between_task_gap_seconds=span-total,
                          observations=[dict(model_node=ids[r["activityId"]], activity_id=r["activityId"],
                                             source_record_id=r["id"], source_array_index=source_index[r["id"]],
                                             start_time=r["startTime"], end_time=r["endTime"],
                                             duration_millis=r["durationInMillis"], duration_seconds=seconds(r)) for r in rows]))
    # Confirm the selected production runs did not overlap one another.
    nonoverlap = all(datetime.fromisoformat(a["endTime"]) <= datetime.fromisoformat(b["startTime"])
                     for a, b in zip(selected, selected[1:]))
    assumptions = {
        "observed": "BPM activity elapsed time, durationInMillis / 1000; includes command/network/control overhead, not isolated machining time.",
        "graph": "Ten automatic service tasks and their nine direct links from production_process.bpmn; manual Enter Color and start/end events excluded.",
        "grouping": "Group by activityId, never by name; two Calibrate VGR activities are distinct.",
        "filter": SELECTION,
        "sample_size": "15 observations per activity from one day; no outliers removed.",
        "capacity": "capacity=1 for each separate task is assumed. Shared robot and machine use between different tasks is not modeled.",
        "simulation": "Default jobs=1 avoids inter-product resource competition. interval=0 is a single-product placeholder, not an observed arrival interval.",
        "independence": "Lognormal model draws independently across tasks/products, discarding empirical dependence.",
        "distribution": "Mean/SD moment matching only; lognormal distribution and stationarity have not been validated. Multimodal short calibration times remain in the data.",
        "layout": "Generated coordinates, not source factory geometry.",
    }
    source = dict(creator="Ronny Seiger", title="Dataset from a Smart Factory to evaluate a Semi-automated Approach to Detecting Process-Level Activities from Sensor Data",
                  doi=ZDOI, url=ZURL, publication_date="2024-12-13", license="CC-BY-4.0",
                  files=[dict(path=str((raw/name).relative_to(src.parent)), sha256=sha(raw/name),
                              download_url=ZURL + "/files/" + name + "?download=1")
                         for name in ("camunda-activity.json", "camunda-process.json", "production_process.bpmn")])
    edges = [(ids[a], ids[b]) for a, b in auto_edges]
    outputs = {}
    for dist, suffix in (("constant", "mean"), ("lognormal", "lognormal")):
        nodes = [dict(id=s["model_node"], name=s["name_ja"],
                      service=dict(dist=dist, p1=s["mean_seconds"], p2=s["sample_sd_seconds"] if dist=="lognormal" else 0), capacity=1)
                 for s in stats]
        outputs["smart_factory_10_" + suffix + ".json"] = base_model(
            nodes, edges, "St.Gallen automatic tasks / " + suffix, "seconds",
            "observed_elapsed_times_with_assumed_resources_and_distribution", [source], assumptions,
            config(jobs=1, runs=50 if dist=="lognormal" else 1, interval=0.0))
    outputs["smart_factory_observations.json"] = {
        "schema": "research.observations.v1", "simulator_input": False,
        "time_unit": "seconds", "source": source, "selection": SELECTION,
        "statistics": stats, "cases": cases,
    }
    audit = dict(source=source, selection=SELECTION, assumptions=assumptions,
                 raw_process_count=len(processes), raw_activity_count=len(activities),
                 process_key_count=sum(r["processDefinitionKey"] == SELECTION["processDefinitionKey"] for r in processes),
                 selected_process_count=len(selected), selected_all_activity_count=len(selected_activities),
                 selected_service_task_count=len(observations),
                 excluded_selected_activity_types=dict(Counter(r["activityType"] for r in selected_activities if r["activityType"] != "serviceTask")),
                 selected_cases_nonoverlapping=nonoverlap,
                 duration_matches_timestamp=True, precedence_violations=0,
                 stats=stats, direct_bpmn_edges=[dict(source_activity=a, target_activity=b, model_src=ids[a], model_dst=ids[b]) for a,b in auto_edges],
                 mean_automatic_duration_sum_seconds=statistics.mean(c["automatic_duration_sum_seconds"] for c in cases),
                 mean_automatic_span_seconds=statistics.mean(c["automatic_span_seconds"] for c in cases),
                 automatic_total_sample_sd_seconds=statistics.stdev(c["automatic_duration_sum_seconds"] for c in cases),
                 independent_model_total_sd_seconds=math.sqrt(sum(s["sample_sd_seconds"]**2 for s in stats)),
                 between_task_gap_min_seconds=min(c["between_task_gap_seconds"] for c in cases),
                 between_task_gap_max_seconds=max(c["between_task_gap_seconds"] for c in cases))
    return outputs, audit


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sources", type=Path, default=ROOT / "sources")
    p.add_argument("--out", type=Path, default=ROOT / "rebuilt")
    p.add_argument("--overwrite", action="store_true")
    args = p.parse_args()
    if args.out.exists() and any(args.out.iterdir()) and not args.overwrite:
        p.error("Output must be empty; use another --out or explicit --overwrite")
    source_checks = {}
    for relative, expected in EXPECTED.items():
        actual = sha(args.sources / relative)
        if actual != expected:
            raise ValueError("Source SHA256 mismatch: " + relative)
        source_checks[relative] = actual
    metadata = json.loads((args.sources / "zenodo_14441997_metadata.json").read_text())
    md5_checks = {}
    for f in metadata["files"]:
        path = args.sources / "zenodo_14441997" / f["key"]
        if path.exists():
            actual = hashlib.md5(path.read_bytes()).hexdigest()
            if f["checksum"] != "md5:" + actual:
                raise ValueError("Published MD5 mismatch: " + f["key"])
            md5_checks[f["key"]] = actual
    outputs, benchmark = make_benchmarks(args.sources)
    smart_outputs, smart = make_smart_factory(args.sources)
    outputs.update(smart_outputs)
    audit = dict(retrieved_on=RETRIEVED, converter_version="1.0.0", source_sha256=source_checks,
                 published_zenodo_md5=md5_checks, benchmarks=benchmark, smart_factory=smart)
    for name, data in outputs.items():
        write(args.out / name, data)
    write(args.out / "provenance.json", audit)
    write(args.out / "catalog.json", {
        "schema": "research.data_catalog.v1", "retrieved_on": RETRIEVED,
        "models": [{"file": name, "title": m["meta"]["title"], "nodes": len(m["nodes"]),
                    "edges": len(m["edges"]), "time_unit": m["meta"]["time_unit"],
                    "default_simulation": m["simulation"]} for name, m in outputs.items() if "meta" in m],
        "observations": "smart_factory_observations.json", "audit": "provenance.json",
        "warning": "Only files in models are inputs for mock_line_editor.py. Keep source/provenance when editing models.",
    })
    print(json.dumps({"written_files": len(outputs)+2, "output": str(args.out),
                      "benchmark_tasks": {k:v["task_count"] for k,v in benchmark.items()},
                      "observed_cases": smart["selected_process_count"], "observed_automatic_tasks": smart["selected_service_task_count"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
