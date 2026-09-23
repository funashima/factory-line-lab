#!/usr/bin/env python3
"""Validate these data with an existing mock_line_editor.py (v1.0.0)."""
import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--program", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=ROOT / "validation_recheck.json")
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Output exists; choose another --out")
    spec = importlib.util.spec_from_file_location("data_validation_line_lab", args.program)
    lab = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = lab
    spec.loader.exec_module(lab)
    audit = json.loads((ROOT / "json/provenance.json").read_text(encoding="utf-8"))
    results = []
    for path in sorted((ROOT / "json").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if "nodes" not in data:
            continue
        model = lab.load_json(path)
        cfg = lab.SimulationConfig(**data["simulation"])
        result = lab.run_experiment(model, cfg)
        if path.stem in audit["benchmarks"]:
            expected = audit["benchmarks"][path.stem]["single_product_critical_path_time"]
        elif path.stem.endswith("_mean"):
            expected = audit["smart_factory"]["mean_automatic_duration_sum_seconds"]
        else:
            expected = None
        actual = None
        if expected is not None:
            actual = lab.run_experiment(model, lab.SimulationConfig(jobs=1, runs=1, interval=0, sensitivity=False)).runs[0]["makespan"]
            if not np.isclose(expected, actual, rtol=0, atol=1e-8):
                raise AssertionError((path.name, expected, actual))
        results.append(dict(file=path.name, valid=True, nodes=len(model.nodes), edges=len(model.edges),
                            default_config=data["simulation"], default_makespan=result.summary["makespan"],
                            single_product_expected=expected, single_product_actual=actual,
                            improvement_top=result.summary["improvement_top"]))
    obs = json.loads((ROOT / "json/smart_factory_observations.json").read_text(encoding="utf-8"))
    sim = lab.Simulator(lab.load_json(ROOT / "json/smart_factory_10_mean.json"))
    replay = []
    for case in obs["cases"]:
        samples = {r["model_node"]: r["duration_seconds"] for r in case["observations"]}
        matrix = np.array([[samples[n] for n in sim.ids]])
        actual = sim.run(matrix, 0).makespan
        if not np.isclose(actual, case["automatic_duration_sum_seconds"], rtol=0, atol=1e-8):
            raise AssertionError(case["process_instance_id"])
        replay.append(dict(case_id=case["process_instance_id"], expected=case["automatic_duration_sum_seconds"], actual=actual))
    report = dict(program_version=lab.VERSION, program_sha256=hashlib.sha256(args.program.read_bytes()).hexdigest(),
                  models=results, empirical_single_product_replay_cases=len(replay), replay_results=replay,
                  scope="Compatibility and numerical consistency only. Not validation of factory capacity, bottlenecks or distribution family.")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(validated_models=len(results), empirical_replays=len(replay), output=str(args.out))))


if __name__ == "__main__":
    main()
