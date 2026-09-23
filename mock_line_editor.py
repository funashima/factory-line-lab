#!/usr/bin/env python3
"""Production Line Lab 1.0.0 — the supplied graphical mock-up extended.

One product executes every node once. Edges are AND precedence relations,
not routing probabilities. Resources are local FCFS servers; buffers are
unlimited. Time is an arbitrary, common unit. See docs/line_lab_guide.tex.
Core/CLI imports do not require Qt. Run without arguments for the editor.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import heapq
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import sys
from dataclasses import asdict, dataclass, field
from typing import Callable

import networkx as nx
import numpy as np
from scipy.stats import t as student_t

VERSION = "1.0.0"
DIST_NAMES = ("constant", "normal", "uniform", "lognormal")


# 1. Domain data and validation ---------------------------------------------
@dataclass
class ServiceSpec:
    dist: str
    p1: float
    p2: float = 0.0

    def issues(self) -> list[str]:
        if self.dist not in DIST_NAMES:
            return [f"未対応の分布: {self.dist}"]
        if not all(math.isfinite(x) for x in (self.p1, self.p2)):
            return ["処理時間に NaN / inf は使えない"]
        if self.dist == "uniform":
            return [] if 0 <= self.p1 < self.p2 else ["uniform: 0 <= 下限 < 上限 が必要"]
        if self.p1 <= 0 or self.p2 < 0:
            return ["平均・定数は正、標準偏差は0以上が必要"]
        if self.dist == "constant" and self.p2 != 0:
            return ["constant の p2 は0とする"]
        return []

    def scaled(self, factor: float) -> ServiceSpec:
        return ServiceSpec(self.dist, self.p1 * factor, self.p2 * factor)


@dataclass
class NodeSpec:
    id: str
    name: str
    service: ServiceSpec
    capacity: int = 1


@dataclass
class EdgeSpec:
    id: str
    src: str
    dst: str


@dataclass
class LineModel:
    nodes: dict[str, NodeSpec]
    edges: list[EdgeSpec]
    layout: dict[str, dict[str, float]] = field(default_factory=dict)

    def graph(self) -> nx.DiGraph:
        g = nx.DiGraph()
        g.add_nodes_from(sorted(self.nodes))
        g.add_edges_from((e.src, e.dst) for e in self.edges)
        return g

    def validate(self) -> list[str]:
        problems = []
        if not self.nodes:
            return ["工程がない"]
        for key, node in self.nodes.items():
            if not key or key != node.id or any(c in key for c in '\r\n\t'):
                problems.append(f"工程IDが不正: {key!r}")
            if not isinstance(node.capacity, int) or isinstance(node.capacity, bool) or not 1 <= node.capacity <= 128:
                problems.append(f"{key}: capacity は1〜128の整数")
            problems.extend(f"{key}: {x}" for x in node.service.issues())
        seen, edge_ids = set(), set()
        for e in self.edges:
            if e.id in edge_ids:
                problems.append(f"重複した接続ID: {e.id}")
            edge_ids.add(e.id)
            if e.src not in self.nodes or e.dst not in self.nodes:
                problems.append(f"接続先の工程がない: {e.src} -> {e.dst}")
            if e.src == e.dst:
                problems.append(f"自己ループ: {e.src}")
            if (e.src, e.dst) in seen:
                problems.append(f"重複した接続: {e.src} -> {e.dst}")
            seen.add((e.src, e.dst))
        for nid, pos in self.layout.items():
            if nid not in self.nodes or not isinstance(pos, dict) or not all(
                isinstance(pos.get(k), (int, float)) and math.isfinite(pos[k]) for k in ("x", "y")
            ):
                problems.append(f"配置座標が不正: {nid}")
        g = self.graph()
        if not nx.is_directed_acyclic_graph(g):
            problems.append("循環がある。戻り工程のないDAGのみ対応")
        if len(self.nodes) > 1:
            isolated = list(nx.isolates(g))
            if isolated:
                problems.append("孤立工程: " + ", ".join(sorted(isolated)))
            if not nx.is_weakly_connected(g):
                problems.append("ラインが分離している。1つの連結したラインにする")
        return problems

    def require_valid(self) -> None:
        problems = self.validate()
        if problems:
            raise ValueError("\n".join(problems))

    def topo_order(self) -> list[str]:
        self.require_valid()
        return list(nx.lexicographical_topological_sort(self.graph()))

    def payload(self) -> dict:
        return {"meta": {"version": 2, "program": VERSION, "semantics": "AND-fork-join/FCFS/unlimited-buffer"},
                "nodes": [asdict(self.nodes[k]) for k in sorted(self.nodes)],
                "edges": [asdict(e) for e in sorted(self.edges, key=lambda e: (e.src, e.dst))],
                "layout": self.layout}


@dataclass(frozen=True)
class SimulationConfig:
    jobs: int = 60
    runs: int = 50
    interval: float = 1.0
    seed: int = 42
    improvement: float = 0.10
    sensitivity: bool = True
    all_traces: bool = False

    def validate(self) -> None:
        for name, value, lo, hi in (("jobs", self.jobs, 1, 10000),
                                    ("runs", self.runs, 1, 10000),
                                    ("seed", self.seed, 0, 2**32 - 1)):
            if not isinstance(value, int) or isinstance(value, bool) or not lo <= value <= hi:
                raise ValueError(f"{name}: 整数 {lo}〜{hi} が必要")
        if not math.isfinite(self.interval) or self.interval < 0:
            raise ValueError("投入間隔は0以上の有限値")
        if not math.isfinite(self.improvement) or not 0 < self.improvement < 1:
            raise ValueError("短縮割合は0より大きく1より小さい値")


# 2. File formats -----------------------------------------------------------
def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def load_json(path: Path, allow_draft: bool = False) -> LineModel:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        meta = data.get("meta", {})
        if meta.get("version", 1) not in (1, 2):
            raise ValueError("未対応のJSONバージョン")
        if meta.get("semantics", "AND-fork-join/FCFS/unlimited-buffer") != "AND-fork-join/FCFS/unlimited-buffer":
            raise ValueError("このプログラムと異なる分岐・合流の仕様")
        nodes = {}
        for item in data["nodes"]:
            nid = item["id"]
            if not isinstance(nid, str) or nid in nodes:
                raise ValueError(f"工程IDの重複または型違い: {nid!r}")
            svc = item["service"]
            nodes[nid] = NodeSpec(nid, str(item.get("name", nid)),
                                  ServiceSpec(str(svc["dist"]), float(svc["p1"]), float(svc.get("p2", 0))),
                                  item.get("capacity", 1))
        edges = [EdgeSpec(str(e.get("id", f"E{i:04}")), e["src"], e["dst"])
                 for i, e in enumerate(data["edges"])]
        model = LineModel(nodes, edges, data.get("layout", {}))
        issues = model.validate()
        if allow_draft:
            issues = [x for x in issues if not x.startswith(("孤立工程:", "ラインが分離", "工程がない"))]
        if issues:
            raise ValueError("\n".join(issues))
        return model
    except (KeyError, TypeError, AttributeError, json.JSONDecodeError) as exc:
        raise ValueError(f"JSON形式が不正: {exc}") from exc


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = list(rows[0]) if rows else []
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path, required: set[str]) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not required <= set(reader.fieldnames or []):
            raise ValueError(f"{path.name}: 必要な列 {sorted(required)} がない")
        rows = list(reader)
        if any(None in row or any(v is None for v in row.values()) for row in rows):
            raise ValueError(f"{path.name}: 列数が一致しない行がある")
        return rows


def load_csv(folder: Path) -> LineModel:
    nodes = {}
    for rownum, row in enumerate(read_csv(folder / "proc_time.csv", {"process", "dist_type", "p1", "p2"}), 2):
        try:
            nid = row["process"].strip()
            if nid in nodes:
                raise ValueError("工程IDが重複")
            nodes[nid] = NodeSpec(nid, row.get("name", nid),
                                  ServiceSpec(row["dist_type"].strip(), float(row["p1"]), float(row["p2"])),
                                  int(row.get("capacity", "1")))
        except (ValueError, TypeError) as exc:
            raise ValueError(f"proc_time.csv {rownum}行目: {exc}") from exc
    edges = [EdgeSpec(f"E{i:04}", row["from"].strip(), row["to"].strip())
             for i, row in enumerate(read_csv(folder / "edges.csv", {"from", "to"}))]
    model = LineModel(nodes, edges)
    model.require_valid()
    auto_layout(model)
    return model


def save_csv(model: LineModel, folder: Path) -> None:
    model.require_valid()
    write_csv(folder / "proc_time.csv", [dict(process=k, name=n.name, dist_type=n.service.dist,
              p1=n.service.p1, p2=n.service.p2, capacity=n.capacity) for k, n in sorted(model.nodes.items())])
    write_csv(folder / "edges.csv", [{"from": e.src, "to": e.dst} for e in model.edges], ["from", "to"])


def auto_layout(model: LineModel) -> None:
    model.require_valid()
    model.layout = {nid: {"x": float(i * 210), "y": float(j * 125 - (len(level) - 1) * 62.5)}
                    for i, level in enumerate(nx.topological_generations(model.graph()))
                    for j, nid in enumerate(sorted(level))}


# 3. Reproducible service times ---------------------------------------------
def sample_service_times(rng: np.random.Generator, svc: ServiceSpec, size: int) -> np.ndarray:
    if svc.dist == "constant":
        return np.full(size, svc.p1)
    if svc.dist == "normal":
        # Clipping is explicit: this distribution is NOT an unmodified normal.
        return np.maximum(0.0, rng.normal(svc.p1, svc.p2, size))
    if svc.dist == "uniform":
        return rng.uniform(svc.p1, svc.p2, size)
    if svc.dist == "lognormal":
        sigma2 = math.log1p((svc.p2 / svc.p1) ** 2)
        mu = math.log(svc.p1) - sigma2 / 2
        return rng.lognormal(mu, math.sqrt(sigma2), size)
    raise ValueError(svc.dist)


def draw_services(model: LineModel, config: SimulationConfig, run: int) -> np.ndarray:
    columns = []
    for nid in sorted(model.nodes):
        # Python hash() is randomized between processes; use SHA-256 instead.
        digest = hashlib.sha256(nid.encode("utf-8")).digest()[:16]
        words = [int.from_bytes(digest[k:k+4], "little") for k in range(0, 16, 4)]
        rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([config.seed, run, *words])))
        try:
            columns.append(sample_service_times(rng, model.nodes[nid].service, config.jobs))
        except (OverflowError, FloatingPointError) as exc:
            raise ValueError(f"{nid}: 処理時間パラメータが大きすぎる") from exc
    a = np.column_stack(columns)
    if not np.isfinite(a).all():
        raise ValueError("処理時間が浮動小数点数の範囲を超えた。パラメータを小さくする")
    return a


# 4. Discrete-event simulation ----------------------------------------------
@dataclass
class RunResult:
    makespan: float
    throughput: float
    mean_flow: float
    metrics: dict[str, dict[str, float]]
    traces: list[dict]
    finishes: np.ndarray


class Simulator:
    """Prepared graph reused for many replications and interventions."""
    def __init__(self, model: LineModel):
        model.require_valid()
        self.ids = sorted(model.nodes)
        idx = {nid: i for i, nid in enumerate(self.ids)}
        g = model.graph()
        self.pred = [sorted(idx[x] for x in g.predecessors(nid)) for nid in self.ids]
        self.succ = [sorted(idx[x] for x in g.successors(nid)) for nid in self.ids]
        self.sources = [i for i, p in enumerate(self.pred) if not p]
        self.sinks = [i for i, s in enumerate(self.succ) if not s]
        self.cap = [model.nodes[nid].capacity for nid in self.ids]

    def run(self, services: np.ndarray, interval: float, trace: bool = False) -> RunResult:
        services = np.asarray(services, dtype=float)
        jobs, count = services.shape
        if count != len(self.ids) or jobs < 1 or not np.isfinite(services).all() or (services < 0).any():
            raise ValueError("処理時間行列が不正")
        if not math.isfinite(interval) or interval < 0:
            raise ValueError("投入間隔が不正")
        release = np.arange(jobs, dtype=float) * interval
        remaining = np.tile([len(p) for p in self.pred], (jobs, 1))
        ready = np.zeros((jobs, count))
        start = np.zeros((jobs, count))
        finish = np.full((jobs, count), np.nan)
        server_used = np.zeros((jobs, count), dtype=int)
        # (time, event type, node index, job id, server id); 0 release, 1 finish.
        events = [(float(release[j]), 0, -1, j, -1) for j in range(jobs)]
        heapq.heapify(events)
        queues = [[] for _ in self.ids]  # (ready time, job id), FCFS with ties
        free = [list(range(c)) for c in self.cap]  # min heaps of server IDs
        completed = 0
        while events:
            now = events[0][0]
            # Gather all already scheduled events at this exact timestamp before
            # dispatch. A zero-duration completion creates a new micro-round.
            while events and events[0][0] == now:
                _, kind, node, job, server = heapq.heappop(events)
                if kind == 0:
                    for source in self.sources:
                        ready[job, source] = now
                        heapq.heappush(queues[source], (now, job))
                else:
                    finish[job, node] = now
                    completed += 1
                    heapq.heappush(free[node], server)
                    for successor in self.succ[node]:
                        remaining[job, successor] -= 1
                        if remaining[job, successor] == 0:
                            ready[job, successor] = now
                            heapq.heappush(queues[successor], (now, job))
            for node in range(count):
                while free[node] and queues[node]:
                    _, job = heapq.heappop(queues[node])
                    server = heapq.heappop(free[node])
                    start[job, node] = now
                    server_used[job, node] = server
                    end = now + float(services[job, node])
                    if not math.isfinite(end):
                        raise ValueError("時刻が数値の範囲を超えた")
                    heapq.heappush(events, (end, 1, node, job, server))
        if completed != jobs * count:
            raise RuntimeError("未完了工程が残った")
        product_finish = np.max(finish[:, self.sinks], axis=1)
        makespan = float(product_finish.max())
        if makespan <= 0:
            raise ValueError("全体完了時間が0。正の処理時間を使う")
        metrics, traces = {}, []
        for node, nid in enumerate(self.ids):
            wait = start[:, node] - ready[:, node]
            earliest = np.min(finish[:, self.pred[node]], axis=1) if self.pred[node] else release
            sync = ready[:, node] - earliest
            metrics[nid] = dict(queue_total=float(wait.sum()), queue_mean=float(wait.mean()),
                                sync_total=float(sync.sum()), sync_mean=float(sync.mean()),
                                service_mean=float(services[:, node].mean()),
                                utilization=float(services[:, node].sum() / (self.cap[node] * makespan)),
                                queue_time_average=float(wait.sum() / makespan))
            if trace:
                for job in range(jobs):
                    traces.append(dict(job=job, process=nid, server=int(server_used[job, node]),
                                       release=float(release[job]), first_component=float(earliest[job]),
                                       ready=float(ready[job, node]), start=float(start[job, node]),
                                       finish=float(finish[job, node]), service=float(services[job, node]),
                                       queue_wait=float(wait[job]), sync_wait=float(sync[job])))
        return RunResult(makespan, jobs / makespan, float(np.mean(product_finish - release)),
                         metrics, traces, product_finish)


# 5. Statistics and interventions -------------------------------------------
def mean_ci(values) -> dict:
    a = np.asarray(values, dtype=float)
    mean = float(a.mean())
    if len(a) < 2:
        return dict(mean=mean, sd=None, ci_low=None, ci_high=None, n=len(a))
    sd = float(a.std(ddof=1))
    half = float(student_t.ppf(0.975, len(a) - 1) * sd / math.sqrt(len(a)))
    return dict(mean=mean, sd=sd, ci_low=mean-half, ci_high=mean+half, n=len(a))


def wilson(success: int, total: int) -> tuple[float, float]:
    z = 1.959963984540054
    p = success / total
    den = 1 + z*z/total
    center = (p + z*z/(2*total))/den
    half = z*math.sqrt(p*(1-p)/total + z*z/(4*total*total))/den
    return center-half, center+half


def top_set(scores: dict[str, float]) -> list[str]:
    maximum = max(scores.values())
    # Near equal numerical maxima are kept as ties, never silently broken.
    return [k for k, v in sorted(scores.items()) if math.isclose(v, maximum, rel_tol=1e-8, abs_tol=1e-9)]


class Cancelled(Exception):
    pass


@dataclass
class ExperimentResult:
    model: LineModel
    config: SimulationConfig
    runs: list[dict]
    nodes: list[dict]
    interventions: list[dict]
    traces: list[dict]
    summary: dict
    first_services: np.ndarray


def run_experiment(model: LineModel, config: SimulationConfig,
                   progress: Callable[[int, int], None] | None = None,
                   cancelled: Callable[[], bool] | None = None) -> ExperimentResult:
    config.validate()
    sim = Simulator(model)
    runs, nodes, interventions, traces = [], [], [], []
    first_services = None
    total = config.runs * (1 + len(sim.ids) if config.sensitivity else 1)
    done = 0

    def checkpoint():
        nonlocal done
        if cancelled and cancelled():
            raise Cancelled("計算を中止した")
        if progress:
            progress(done, total)

    for run in range(config.runs):
        checkpoint()
        services = draw_services(model, config, run)
        if run == 0:
            first_services = services.copy()
        base = sim.run(services, config.interval, trace=(run == 0 or config.all_traces))
        done += 1
        runs.append(dict(run=run, makespan=base.makespan, throughput=base.throughput, mean_flow=base.mean_flow))
        nodes.extend(dict(run=run, process=nid, **base.metrics[nid]) for nid in sim.ids)
        traces.extend(dict(run=run, **row) for row in base.traces)
        if config.sensitivity:
            for i, nid in enumerate(sim.ids):
                checkpoint()
                changed = services.copy()
                changed[:, i] *= 1-config.improvement
                alternative = sim.run(changed, config.interval)
                delta = base.makespan - alternative.makespan
                interventions.append(dict(run=run, process=nid, baseline=base.makespan,
                    improved=alternative.makespan, delta=delta, gain_percent=100*delta/base.makespan))
                done += 1
    checkpoint()
    summary = {"program_version": VERSION, "config": asdict(config),
               "makespan": mean_ci([r["makespan"] for r in runs]),
               "throughput": mean_ci([r["throughput"] for r in runs]),
               "mean_flow": mean_ci([r["mean_flow"] for r in runs]), "nodes": {}}
    for nid in sim.ids:
        rows = [r for r in nodes if r["process"] == nid]
        stat = {key: mean_ci([r[key] for r in rows]) for key in rows[0] if key not in ("run", "process")}
        if config.sensitivity:
            imp = [r for r in interventions if r["process"] == nid]
            stat["delta"] = mean_ci([r["delta"] for r in imp])
            stat["gain_percent"] = mean_ci([r["gain_percent"] for r in imp])
        summary["nodes"][nid] = stat
    summary["queue_top"] = top_set({k: s["queue_mean"]["mean"] for k, s in summary["nodes"].items()})
    summary["improvement_top"] = top_set({k: s["delta"]["mean"] for k, s in summary["nodes"].items()}) if config.sensitivity else []
    return ExperimentResult(copy.deepcopy(model), config, runs, nodes, interventions, traces, summary, first_services)


# 6. Graphs and reproducibility outputs -------------------------------------
def export_figures(result: ExperimentResult, folder: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    folder.mkdir(parents=True, exist_ok=True)
    ids = sorted(result.model.nodes)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "figure.dpi": 120})

    def save(fig, name):
        fig.tight_layout()
        fig.savefig(folder / f"{name}.png", dpi=180, bbox_inches="tight")
        fig.savefig(folder / f"{name}.pdf", bbox_inches="tight")
        plt.close(fig)

    model = copy.deepcopy(result.model)
    if len(model.layout) != len(ids):
        auto_layout(model)
    pos = {k: (v["x"], -v["y"]) for k, v in model.layout.items()}
    fig, ax = plt.subplots(figsize=(11, 3.2))
    colors = ["#ed9a60" if k in result.summary["improvement_top"] else "#a8cadf" for k in ids]
    nx.draw_networkx(model.graph(), pos, ax=ax, nodelist=ids, node_color=colors,
                     node_size=1000, font_size=9, arrowsize=18, edge_color="#657587")
    ax.set_title("AND fork/join network (orange: largest mean improvement)")
    ax.margins(0.1); ax.axis("off"); save(fig, "network")

    for key, name, label in (("queue_mean", "queue_wait", "Queue wait per product [time]"),
                              ("sync_mean", "join_wait", "Join synchronization gap [time]")):
        stats = [result.summary["nodes"][k][key] for k in ids]
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.bar(ids, [s["mean"] for s in stats], color="#447d9f")
        if result.config.runs > 1:
            ax.errorbar(ids, [s["mean"] for s in stats], yerr=[s["ci_high"]-s["mean"] for s in stats],
                        fmt="none", color="#243a4a", capsize=3)
        ax.set_ylabel(label); ax.set_xlabel("Process ID"); ax.set_title("Means across runs; bars: individual 95% t intervals")
        ax.tick_params(axis="x", rotation=45); save(fig, name)
    fig, ax = plt.subplots(figsize=(8, 4))
    values = [r["makespan"] for r in result.runs]
    ax.hist(values, bins=min(20, max(1, int(math.sqrt(len(values))))), color="#447d9f", edgecolor="white")
    ax.set_xlabel("Batch makespan [time]"); ax.set_ylabel("Number of runs"); save(fig, "makespan")
    if result.config.sensitivity:
        stats = [result.summary["nodes"][k]["delta"] for k in ids]
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.bar(ids, [s["mean"] for s in stats], color="#cf8153")
        if result.config.runs > 1:
            ax.errorbar(ids, [s["mean"] for s in stats], yerr=[s["ci_high"]-s["mean"] for s in stats],
                        fmt="none", color="#624032", capsize=3)
        ax.axhline(0, color="gray", lw=0.5)
        ax.set_xlabel("Individually improved process"); ax.set_ylabel("Makespan reduction [time]")
        ax.set_title(f"{100*result.config.improvement:g}% service-time reduction; paired runs; 95% t intervals")
        ax.tick_params(axis="x", rotation=45); save(fig, "improvement")
    rows = math.ceil(len(ids)/4)
    fig, axes = plt.subplots(rows, 4, figsize=(11, rows*2.2), squeeze=False)
    for i, ax in enumerate(axes.flat):
        if i >= len(ids):
            ax.axis("off"); continue
        ax.hist(result.first_services[:, i], bins=15, color="#68a0a2")
        ax.set_title(f"{ids[i]}: {model.nodes[ids[i]].service.dist}", fontsize=9)
        ax.set_xlabel("Service time", fontsize=8)
    save(fig, "service_samples")
    fig, ax = plt.subplots(figsize=(11, max(4, len(ids)*0.35)))
    cmap = plt.get_cmap("tab10")
    for row in result.traces:
        if row["run"] == 0 and row["job"] < 8:
            y = ids.index(row["process"])
            ax.broken_barh([(row["start"], row["service"])], (y-.35, .7), facecolors=cmap(row["job"]%10))
    ax.set_yticks(range(len(ids)), ids); ax.set_xlabel("Time (first 8 products, run 0)")
    ax.set_title("Processing intervals; colors identify products; servers may overlap")
    save(fig, "timeline")


def export_result(result: ExperimentResult, folder: Path, figures: bool = True) -> None:
    if folder.exists() and any(folder.iterdir()):
        raise ValueError("出力先が空ではない。新しいフォルダを指定する")
    folder.mkdir(parents=True, exist_ok=True)
    model_payload = result.model.payload()
    model_payload["simulation"] = asdict(result.config)
    write_json(folder / "model.json", model_payload)
    write_json(folder / "summary.json", result.summary)
    save_csv(result.model, folder / "input_csv")
    write_csv(folder / "runs.csv", result.runs)
    write_csv(folder / "node_metrics.csv", result.nodes)
    write_csv(folder / "trace.csv", result.traces)
    write_csv(folder / "interventions.csv", result.interventions,
              ["run", "process", "baseline", "improved", "delta", "gain_percent"])
    ranks = []
    metric = "delta" if result.config.sensitivity else "queue_mean"
    stats = result.summary["nodes"]
    for nid in sorted(stats, key=lambda k: (-stats[k][metric]["mean"], k)):
        row = dict(process=nid, name=result.model.nodes[nid].name)
        for key in ("queue_mean", "sync_mean", "utilization", "delta", "gain_percent"):
            if key in stats[nid]:
                for label in ("mean", "ci_low", "ci_high"):
                    row[f"{key}_{label}"] = stats[nid][key][label]
        ranks.append(row)
    write_csv(folder / "ranking.csv", ranks)
    versions = {}
    for package in ("numpy", "networkx", "scipy", "matplotlib", "PyQt6", "pyqtgraph"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "not installed"
    source = Path(__file__).read_bytes()
    write_json(folder / "reproducibility.json", dict(program=VERSION, python=platform.python_version(),
        platform=platform.platform(), libraries=versions, code_sha256=hashlib.sha256(source).hexdigest(),
        config=asdict(result.config), rng="PCG64/SeedSequence(seed,run,SHA256(node_id)[0:16])",
        trace_scope="all baseline runs" if result.config.all_traces else "baseline run 0 only",
        semantics="Each product visits all nodes once; AND joins; FCFS; unlimited buffers; independent service times"))
    if figures:
        export_figures(result, folder / "figures")


# 7. Sample models and five prespecified scenarios ---------------------------
def example_model(kind: str = "serial") -> LineModel:
    nodes = {f"N{i:02}": NodeSpec(f"N{i:02}", f"Process {i:02}", ServiceSpec("normal", 3, 0.45)) for i in range(1, 13)}
    if kind == "serial":
        pairs = [(i, i+1) for i in range(1, 12)]
    elif kind == "fork":
        pairs = [(1, 2), (2, 3), (3, 4), (4, 5), (2, 6), (6, 7), (7, 8),
                 (5, 9), (8, 9), (9, 10), (10, 11), (11, 12)]
    else:
        raise ValueError(kind)
    edges = [EdgeSpec(f"E{k:02}", f"N{a:02}", f"N{b:02}") for k, (a, b) in enumerate(pairs)]
    model = LineModel(nodes, edges)
    auto_layout(model)
    return model


def scenarios() -> list[dict]:
    cases = []
    for name, kind, target in (("serial_middle", "serial", "N06"), ("serial_head", "serial", "N01"),
                               ("fork_arm", "fork", "N06"), ("fork_join", "fork", "N09")):
        base = example_model(kind)
        changed = copy.deepcopy(base)
        changed.nodes[target].service = changed.nodes[target].service.scaled(1.5)
        cases.append(dict(name=name, kind=kind, baseline=base, model=changed, perturbed=target,
                          expected=target, reason="One station 3 -> 4.5, std 0.45 -> 0.675; others 3"))
    base = example_model("fork")
    for n in base.nodes.values():
        n.service = ServiceSpec("constant", 2, 0)
    base.nodes["N06"].service = ServiceSpec("constant", 8, 0)
    base.nodes["N03"].service = ServiceSpec("constant", 1, 0)
    changed = copy.deepcopy(base)
    changed.nodes["N03"].service = ServiceSpec("constant", 1.5, 0)
    cases.append(dict(name="nonbottleneck_control", kind="fork", baseline=base, model=changed,
                      perturbed="N03", expected="N06", reason="N03 1 -> 1.5; N06 remains 8 (deterministic control)"))
    return cases


def create_examples(folder: Path) -> None:
    if folder.exists() and any(folder.iterdir()):
        raise ValueError("サンプル出力先が空ではない")
    for kind in ("serial", "fork"):
        model = example_model(kind)
        write_json(folder / kind / "model.json", model.payload())
        save_csv(model, folder / kind)
    rows = []
    for case in scenarios():
        dest = folder / "scenarios" / case["name"]
        write_json(dest / "baseline.json", case["baseline"].payload())
        write_json(dest / "model.json", case["model"].payload())
        save_csv(case["model"], dest)
        rows.append({k: case[k] for k in ("name", "kind", "perturbed", "expected", "reason")})
    write_csv(folder / "scenarios.csv", rows)


def run_benchmark(config: SimulationConfig, folder: Path) -> list[dict]:
    if folder.exists() and any(folder.iterdir()):
        raise ValueError("評価出力先が空ではない")
    if not config.sensitivity:
        raise ValueError("評価実験には感度分析が必要")
    summary_rows, decisions, confusions = [], [], []
    folder.mkdir(parents=True, exist_ok=True)
    for case in scenarios():
        print(f"Benchmark: {case['name']}", flush=True)
        result = run_experiment(case["model"], config)
        export_result(result, folder / case["name"])
        write_json(folder / case["name"] / "unperturbed_model.json", case["baseline"].payload())
        for method, key in (("queue", "queue_mean"), ("utilization", "utilization"), ("improvement", "delta")):
            hits = ambiguous = top_hits = 0
            for run in range(config.runs):
                table = result.interventions if method == "improvement" else result.nodes
                scores = {r["process"]: r[key] for r in table if r["run"] == run}
                winners = top_set(scores)
                unique = len(winners) == 1
                hit = unique and winners[0] == case["expected"]
                hits += int(hit); ambiguous += int(not unique)
                top_hits += int(case["expected"] in winners)
                predicted = winners[0] if unique else "AMBIGUOUS"
                decisions.append(dict(scenario=case["name"], run=run, method=method,
                    expected=case["expected"], perturbed=case["perturbed"], predicted=predicted,
                    top_set="|".join(winners), unique_correct=int(hit)))
            stochastic = any(n.service.dist == "uniform" or
                             (n.service.dist in ("normal", "lognormal") and n.service.p2 > 0)
                             for n in case["model"].nodes.values())
            lo, hi = wilson(hits, config.runs) if stochastic else (None, None)
            summary_rows.append(dict(scenario=case["name"], method=method, expected=case["expected"],
                perturbed=case["perturbed"], runs=config.runs, correct=hits, wrong=config.runs-hits-ambiguous,
                ambiguous=ambiguous, top_set_hits=top_hits, detection_rate=hits/config.runs,
                ci_low=lo, ci_high=hi, uncertainty="Wilson95" if stochastic else "deterministic",
                mean_makespan=result.summary["makespan"]["mean"]))
    from collections import Counter
    for (scenario, method, actual, predicted), n in sorted(Counter(
        (r["scenario"], r["method"], r["expected"], r["predicted"]) for r in decisions).items()):
        confusions.append(dict(scenario=scenario, method=method, expected=actual, predicted=predicted, count=n))
    write_csv(folder / "detection_summary.csv", summary_rows)
    write_csv(folder / "decisions.csv", decisions)
    write_csv(folder / "confusion.csv", confusions)
    write_json(folder / "benchmark_config.json", asdict(config))
    return summary_rows


# 8. Qt editor (lazy imports: the CLI works without Qt) -----------------------
def build_gui_classes():
    from PyQt6.QtCore import Qt, QPointF, QRectF, QThread, pyqtSignal
    from PyQt6.QtGui import QBrush, QPen, QColor, QPainter, QPainterPath, QPolygonF, QAction
    from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QGraphicsScene, QGraphicsView, QGraphicsItem, QGraphicsRectItem, QGraphicsEllipseItem,
        QGraphicsPathItem, QGraphicsSimpleTextItem, QGraphicsPolygonItem, QSplitter,
        QFormLayout, QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox, QPushButton,
        QFileDialog, QMessageBox, QLabel, QFrame, QMenu, QTabWidget, QTableWidget,
        QTableWidgetItem, QHeaderView, QCheckBox, QProgressBar, QGroupBox)
    import pyqtgraph as pg
    pg.setConfigOptions(background="w", foreground="#244050", antialias=True)

    class PortItem(QGraphicsEllipseItem):
        def __init__(self, parent, output):
            super().__init__(-7, -7, 14, 14, parent)
            self.output = output
            self.setBrush(QBrush(QColor("#e78e50" if output else "#4189a3")))
            self.setPen(QPen(QColor("#ffffff"), 1.5))
            self.setZValue(5)
            self.setToolTip("出力端子: クリックしてから接続先の青い端子をクリック" if output else "入力端子")

    class NodeItem(QGraphicsRectItem):
        def __init__(self, nid):
            super().__init__(0, 0, 158, 74)
            self.node_id = nid
            self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                          QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
                          QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
            self.setBrush(QBrush(QColor("#e1edf3")))
            self.setPen(QPen(QColor("#42657a"), 1.6))
            self.in_port = PortItem(self, False); self.in_port.setPos(0, 37)
            self.out_port = PortItem(self, True); self.out_port.setPos(158, 37)
            self.label = QGraphicsSimpleTextItem(self)
            self.label.setPos(12, 10)
            self.label.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self.setZValue(1)

        def refresh(self, spec):
            name = spec.name if len(spec.name) <= 15 else spec.name[:14] + "…"
            self.label.setText(f"{name}\n{spec.id}  ·  {spec.service.dist}\np1={spec.service.p1:g}  c={spec.capacity}")
            self.setToolTip(f"{spec.name}\nID: {spec.id}\np1={spec.service.p1:g}, p2={spec.service.p2:g}")

        def itemChange(self, change, value):
            if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.scene():
                self.scene().update_edges()
            return super().itemChange(change, value)

    class EdgeItem(QGraphicsPathItem):
        def __init__(self, eid, source, target):
            super().__init__()
            self.eid, self.source, self.target = eid, source, target
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
            self.setPen(QPen(QColor("#526d7a"), 2.4))
            self.arrow = QGraphicsPolygonItem(self)
            self.arrow.setBrush(QBrush(QColor("#526d7a")))
            self.arrow.setPen(QPen(Qt.PenStyle.NoPen))
            self.arrow.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self.setZValue(0)
            self.update_path()

        def update_path(self):
            a, b = self.source.out_port.scenePos(), self.target.in_port.scenePos()
            path = QPainterPath(a)
            dx = max(45, abs(b.x()-a.x())*.5)
            path.cubicTo(QPointF(a.x()+dx, a.y()), QPointF(b.x()-dx, b.y()), b)
            self.setPath(path)
            self.arrow.setPolygon(QPolygonF([b, b+QPointF(-12, -5), b+QPointF(-12, 5)]))

    class EditorScene(QGraphicsScene):
        modelChanged = pyqtSignal()
        selectedNode = pyqtSignal(object)
        notice = pyqtSignal(str)

        def __init__(self):
            super().__init__()
            self.nodes, self.edges = {}, {}
            self.model = LineModel({}, [])
            self.pending = None
            self.selectionChanged.connect(self.on_selection)

        def on_selection(self):
            selected = [x for x in self.selectedItems() if isinstance(x, NodeItem)]
            self.selectedNode.emit(selected[0].node_id if len(selected) == 1 else None)

        def update_edges(self):
            for edge in self.edges.values():
                edge.update_path()

        def snapshot(self):
            self.model.layout = {nid: dict(x=item.pos().x(), y=item.pos().y()) for nid, item in self.nodes.items()}
            return copy.deepcopy(self.model)

        def load_model(self, model):
            self.blockSignals(True)
            self.pending = None
            self.nodes.clear(); self.edges.clear(); self.clear()
            self.model = copy.deepcopy(model)
            if len(self.model.layout) != len(model.nodes):
                if not self.model.validate():
                    auto_layout(self.model)
                else:
                    self.model.layout = {nid: dict(x=210*(i%5), y=125*(i//5)) for i,nid in enumerate(sorted(model.nodes))}
            for nid, spec in sorted(self.model.nodes.items()):
                item = NodeItem(nid); self.addItem(item); self.nodes[nid] = item
                pos = self.model.layout[nid]; item.setPos(pos["x"], pos["y"]); item.refresh(spec)
            for e in self.model.edges:
                item = EdgeItem(e.id, self.nodes[e.src], self.nodes[e.dst])
                self.addItem(item); self.edges[e.id] = item
            self.blockSignals(False)
            self.setSceneRect(self.itemsBoundingRect().adjusted(-400, -300, 400, 300))
            self.selectedNode.emit(None); self.modelChanged.emit()

        def add_process(self, pos):
            i = 1
            while f"N{i:02}" in self.model.nodes:
                i += 1
            nid = f"N{i:02}"
            spec = NodeSpec(nid, nid, ServiceSpec("constant", 3))
            self.model.nodes[nid] = spec
            item = NodeItem(nid); self.addItem(item); self.nodes[nid] = item
            item.setPos(pos); item.refresh(spec)
            self.clearSelection(); item.setSelected(True); self.modelChanged.emit()

        def connect_nodes(self, src, dst):
            if src == dst or any(e.src == src and e.dst == dst for e in self.model.edges):
                self.notice.emit("自己接続・重複接続は追加できません"); return
            g = self.model.graph(); g.add_edge(src, dst)
            if not nx.is_directed_acyclic_graph(g):
                self.notice.emit("循環する接続は追加できません"); return
            i = 1
            while f"E{i:04}" in self.edges:
                i += 1
            eid = f"E{i:04}"
            edge = EdgeItem(eid, self.nodes[src], self.nodes[dst])
            self.addItem(edge); self.edges[eid] = edge
            self.model.edges.append(EdgeSpec(eid, src, dst)); self.modelChanged.emit()

        def delete_selected(self):
            selected = list(self.selectedItems())
            nids = {x.node_id for x in selected if isinstance(x, NodeItem)}
            eids = {x.eid for x in selected if isinstance(x, EdgeItem)}
            eids |= {e.id for e in self.model.edges if e.src in nids or e.dst in nids}
            self.pending = None
            for eid in eids:
                item = self.edges.pop(eid, None)
                if item is not None: self.removeItem(item)
            self.model.edges = [e for e in self.model.edges if e.id not in eids]
            for nid in nids:
                self.removeItem(self.nodes.pop(nid)); self.model.nodes.pop(nid)
                self.model.layout.pop(nid, None)
            if eids or nids:
                self.modelChanged.emit(); self.selectedNode.emit(None)

        def contextMenuEvent(self, event):
            menu = QMenu(); add = menu.addAction("工程を追加"); delete = menu.addAction("選択を削除")
            action = menu.exec(event.screenPos())
            if action == add: self.add_process(event.scenePos())
            elif action == delete: self.delete_selected()

        def mousePressEvent(self, event):
            item = self.itemAt(event.scenePos(), self.views()[0].transform()) if self.views() else None
            if event.button() == Qt.MouseButton.LeftButton and isinstance(item, PortItem):
                nid = item.parentItem().node_id
                if item.output:
                    self.pending = nid; self.notice.emit(f"{nid} の接続先: 青い入力端子をクリック (Escで取消)")
                elif self.pending is not None:
                    self.connect_nodes(self.pending, nid); self.pending = None
                event.accept(); return
            super().mousePressEvent(event)

    class EditorView(QGraphicsView):
        def __init__(self, scene):
            super().__init__(scene)
            self.setRenderHint(QPainter.RenderHint.Antialiasing)
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
            self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
            self.setBackgroundBrush(QColor("#f6f9fb")); self.pan_pos = None

        def wheelEvent(self, event):
            factor = 1.15 if event.angleDelta().y() > 0 else 1/1.15
            if .08 < self.transform().m11()*factor < 8:
                self.scale(factor, factor)
            event.accept()

        def mousePressEvent(self, event):
            if event.button() == Qt.MouseButton.MiddleButton:
                self.pan_pos = event.position(); event.accept()
            else: super().mousePressEvent(event)

        def mouseMoveEvent(self, event):
            if self.pan_pos is not None:
                delta = event.position() - self.pan_pos; self.pan_pos = event.position()
                self.horizontalScrollBar().setValue(self.horizontalScrollBar().value()-int(delta.x()))
                self.verticalScrollBar().setValue(self.verticalScrollBar().value()-int(delta.y()))
            else: super().mouseMoveEvent(event)

        def mouseReleaseEvent(self, event):
            if event.button() == Qt.MouseButton.MiddleButton:
                self.pan_pos = None; event.accept()
            else: super().mouseReleaseEvent(event)

        def keyPressEvent(self, event):
            if event.key() == Qt.Key.Key_Delete: self.scene().delete_selected()
            elif event.key() == Qt.Key.Key_Escape:
                self.scene().pending = None; self.scene().notice.emit("接続操作を取消")
            else: super().keyPressEvent(event)

    class PropertyPanel(QFrame):
        changed = pyqtSignal()
        def __init__(self):
            super().__init__()
            self.current = None; self.loading = False
            form = QFormLayout(self)
            self.id_label = QLabel("工程を選択")
            self.name_edit = QLineEdit()
            self.dist = QComboBox(); self.dist.addItems(DIST_NAMES)
            self.p1 = QDoubleSpinBox(); self.p2 = QDoubleSpinBox()
            for spin in (self.p1, self.p2):
                spin.setRange(0, 1e9); spin.setDecimals(5); spin.setSingleStep(.1)
            self.capacity = QSpinBox(); self.capacity.setRange(1, 128)
            self.l1 = QLabel("定数"); self.l2 = QLabel("未使用 (0)")
            form.addRow("ID", self.id_label); form.addRow("工程名", self.name_edit)
            form.addRow("処理時間の分布", self.dist); form.addRow(self.l1, self.p1)
            form.addRow(self.l2, self.p2); form.addRow("設備台数", self.capacity)
            self.note = QLabel("時間の単位は全工程で統一する。\nnormalは負の値を0に切り上げる。")
            self.note.setWordWrap(True); form.addRow(self.note)
            self.name_edit.textEdited.connect(self.notify)
            self.dist.currentTextChanged.connect(self.dist_changed)
            for spin in (self.p1, self.p2, self.capacity): spin.valueChanged.connect(self.notify)
            self.setEnabled(False)

        def notify(self, *_):
            if not self.loading: self.changed.emit()

        def dist_changed(self, *_):
            dist = self.dist.currentText()
            self.l1.setText("下限" if dist == "uniform" else "定数" if dist == "constant" else "平均 (元の正規)" if dist == "normal" else "算術平均")
            self.l2.setText("上限" if dist == "uniform" else "未使用 (0)" if dist == "constant" else "標準偏差")
            self.p2.setEnabled(dist != "constant")
            if not self.loading and dist == "constant": self.p2.setValue(0)
            self.notify()

        def set_spec(self, nid, spec):
            self.loading = True; self.current = nid; self.setEnabled(spec is not None)
            if spec is not None:
                self.id_label.setText(nid); self.name_edit.setText(spec.name)
                self.dist.setCurrentText(spec.service.dist)
                self.p1.setValue(spec.service.p1); self.p2.setValue(spec.service.p2)
                self.capacity.setValue(spec.capacity); self.dist_changed()
            self.loading = False

        def apply(self, model):
            if self.current not in model.nodes: return
            n = model.nodes[self.current]
            n.name = self.name_edit.text().strip() or n.id
            n.service = ServiceSpec(self.dist.currentText(), self.p1.value(), self.p2.value())
            n.capacity = self.capacity.value()

    class Worker(QThread):
        succeeded = pyqtSignal(object)
        failed = pyqtSignal(str)
        progress = pyqtSignal(int, int)
        def __init__(self, model, config, parent):
            super().__init__(parent); self.model = model; self.config = config
        def run(self):
            try:
                result = run_experiment(self.model, self.config, self.progress.emit, self.isInterruptionRequested)
                self.succeeded.emit(result)
            except Exception as exc:
                self.failed.emit(str(exc))

    class MainWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle(f"Production Line Lab {VERSION} — 工程ネットワーク実験")
            self.resize(1480, 940)
            self.result = None; self.worker = None; self.saved_snapshot = None
            self.scene = EditorScene(); self.view = EditorView(self.scene)
            self.prop = PropertyPanel(); self.prop.changed.connect(self.property_changed)
            self.scene.selectedNode.connect(lambda nid: self.prop.set_spec(nid, self.scene.model.nodes.get(nid)))
            self.scene.modelChanged.connect(self.invalidate)
            self.scene.notice.connect(lambda msg: self.statusBar().showMessage(msg, 7000))
            toolbar = self.addToolBar("工程編集"); toolbar.setMovable(False)
            self.edit_actions = []
            for label, fn in (("直列の例", lambda: self.load_example("serial")),
                              ("分岐の例", lambda: self.load_example("fork")),
                              ("工程追加", lambda: self.scene.add_process(self.view.mapToScene(self.view.viewport().rect().center()))),
                              ("選択削除", self.scene.delete_selected), ("全体表示", self.fit),
                              ("JSON保存", self.save_model), ("JSON読込", self.open_model),
                              ("CSV読込", self.open_csv), ("CSV出力", self.export_csv)):
                action = QAction(label, self); action.triggered.connect(fn); toolbar.addAction(action)
                self.edit_actions.append(action)
            self.controls = QGroupBox("実験条件")
            form = QFormLayout(self.controls)
            self.jobs = QSpinBox(); self.jobs.setRange(1, 10000); self.jobs.setValue(60)
            self.runs = QSpinBox(); self.runs.setRange(1, 10000); self.runs.setValue(50)
            self.interval = QDoubleSpinBox(); self.interval.setRange(0, 1e9); self.interval.setDecimals(5); self.interval.setValue(1)
            self.seed = QLineEdit("42")
            self.improvement = QDoubleSpinBox(); self.improvement.setRange(.01, 99.99); self.improvement.setDecimals(2); self.improvement.setValue(10); self.improvement.setSuffix(" %")
            self.sensitivity = QCheckBox("各工程を速くして改善効果を比較"); self.sensitivity.setChecked(True)
            form.addRow("製品数 / 試行", self.jobs); form.addRow("試行回数", self.runs)
            form.addRow("投入間隔", self.interval); form.addRow("乱数seed", self.seed)
            form.addRow("処理時間短縮率", self.improvement); form.addRow(self.sensitivity)
            self.run_button = QPushButton("シミュレーション実行"); self.run_button.clicked.connect(self.start_run)
            self.cancel_button = QPushButton("中止"); self.cancel_button.setEnabled(False)
            self.cancel_button.clicked.connect(lambda: self.worker.requestInterruption() if self.worker else None)
            self.export_button = QPushButton("結果を保存 (CSV・図・JSON)"); self.export_button.setEnabled(False)
            self.export_button.clicked.connect(self.export_results)
            self.progress = QProgressBar(); self.progress.setValue(0)
            self.summary_label = QLabel("工程を設定し、実行してください。"); self.summary_label.setWordWrap(True)
            left = QWidget(); left_layout = QVBoxLayout(left)
            left_layout.addWidget(self.controls); left_layout.addWidget(self.run_button)
            left_layout.addWidget(self.cancel_button); left_layout.addWidget(self.progress)
            left_layout.addWidget(self.export_button); left_layout.addWidget(self.summary_label)
            left_layout.addWidget(QLabel("工程の設定")); left_layout.addWidget(self.prop)
            left_layout.addStretch(1); left.setMinimumWidth(295); left.setMaximumWidth(390)
            self.tabs = QTabWidget()
            self.hist = pg.PlotWidget(title="全体完了時間の分布")
            self.waitplot = pg.PlotWidget(title="工程別の設備待ち")
            self.gainplot = pg.PlotWidget(title="工程を速くした場合の短縮時間")
            self.table = QTableWidget(); self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
            for widget, name in ((self.hist,"完了時間"),(self.waitplot,"設備待ち"),(self.gainplot,"改善効果"),(self.table,"数値表")):
                self.tabs.addTab(widget, name)
            center = QSplitter(Qt.Orientation.Vertical); center.addWidget(self.view); center.addWidget(self.tabs); center.setSizes([530, 340])
            layout = QHBoxLayout(); container = QWidget(); container.setLayout(layout)
            layout.addWidget(left); layout.addWidget(center, 1); self.setCentralWidget(container)
            for field in (self.jobs, self.runs, self.interval, self.improvement): field.valueChanged.connect(self.invalidate)
            self.seed.textEdited.connect(self.invalidate); self.sensitivity.toggled.connect(self.invalidate)
            self.scene.load_model(example_model("fork")); self.fit(); self.saved_snapshot = self.state_payload()
            self.statusBar().showMessage("橙端子→青端子で接続。ホイール: 拡大縮小 / 中ボタン: 移動 / Delete: 削除")

        def fit(self):
            self.view.fitInView(self.scene.itemsBoundingRect().adjusted(-35,-35,35,35), Qt.AspectRatioMode.KeepAspectRatio)

        def config(self):
            try: seed = int(self.seed.text())
            except ValueError: raise ValueError("seedには0以上の整数を入力する")
            cfg = SimulationConfig(self.jobs.value(), self.runs.value(), self.interval.value(), seed,
                                   self.improvement.value()/100, self.sensitivity.isChecked())
            cfg.validate(); return cfg

        def state_payload(self):
            payload = self.scene.snapshot().payload()
            payload["simulation"] = asdict(self.config())
            return payload

        def invalidate(self, *_):
            self.result = None
            self.export_button.setEnabled(False)
            self.hist.clear(); self.waitplot.clear(); self.gainplot.clear(); self.table.setRowCount(0)
            self.summary_label.setText("条件が変更されました。実行すると結果を表示します。")
            for item in self.scene.nodes.values(): item.setBrush(QBrush(QColor("#e1edf3")))

        def property_changed(self):
            self.prop.apply(self.scene.model)
            nid = self.prop.current
            if nid in self.scene.nodes: self.scene.nodes[nid].refresh(self.scene.model.nodes[nid])
            self.invalidate()

        def can_discard(self):
            try: dirty = self.state_payload() != self.saved_snapshot
            except ValueError: dirty = True
            return not dirty or QMessageBox.question(self, "未保存の変更", "未保存の工程・条件を破棄しますか？") == QMessageBox.StandardButton.Yes

        def load_example(self, kind):
            if self.can_discard():
                self.scene.load_model(example_model(kind)); self.fit(); self.saved_snapshot = None

        def save_model(self):
            try:
                payload = self.state_payload()
                issues = [x for x in self.scene.model.validate()
                          if not x.startswith(("孤立工程:", "ラインが分離", "工程がない"))]
                if issues: raise ValueError("\n".join(issues))
                # Disconnected drafts can be saved/reopened, but cannot run.
                path, _ = QFileDialog.getSaveFileName(self, "工程と条件を保存", "line_model.json", "JSON (*.json)")
                if path:
                    write_json(Path(path), payload); self.saved_snapshot = payload
                    self.statusBar().showMessage("工程・配置・実験条件をJSONに保存しました", 6000)
            except Exception as exc: QMessageBox.critical(self, "保存エラー", str(exc))

        def open_model(self):
            path, _ = QFileDialog.getOpenFileName(self, "工程を読み込む", "", "JSON (*.json)")
            if not path: return
            try:
                model = load_json(Path(path), allow_draft=True)
                payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
                cfg = SimulationConfig(**payload.get("simulation", {})); cfg.validate()
                if not self.can_discard(): return
                self.scene.load_model(model)
                self.jobs.setValue(cfg.jobs); self.runs.setValue(cfg.runs); self.interval.setValue(cfg.interval)
                self.seed.setText(str(cfg.seed)); self.improvement.setValue(100*cfg.improvement)
                self.sensitivity.setChecked(cfg.sensitivity); self.fit(); self.saved_snapshot = self.state_payload()
            except Exception as exc: QMessageBox.critical(self, "読込エラー (現在の工程は維持)", str(exc))

        def open_csv(self):
            path = QFileDialog.getExistingDirectory(self, "proc_time.csv と edges.csv のあるフォルダ")
            if not path: return
            try:
                model = load_csv(Path(path))
                if self.can_discard(): self.scene.load_model(model); self.fit(); self.saved_snapshot = None
            except Exception as exc: QMessageBox.critical(self, "CSV読込エラー", str(exc))

        def export_csv(self):
            path = QFileDialog.getExistingDirectory(self, "CSVの保存先 (空のフォルダ)")
            if not path: return
            try:
                dest = Path(path)
                if any(dest.iterdir()): raise ValueError("空のフォルダを選択してください")
                save_csv(self.scene.snapshot(), dest)
            except Exception as exc: QMessageBox.critical(self, "CSV保存エラー", str(exc))

        def set_busy(self, busy):
            self.view.setEnabled(not busy); self.controls.setEnabled(not busy)
            self.prop.setEnabled(not busy and self.prop.current in self.scene.model.nodes)
            self.run_button.setEnabled(not busy); self.cancel_button.setEnabled(busy)
            for action in self.edit_actions: action.setEnabled(not busy)

        def start_run(self):
            try:
                model = self.scene.snapshot(); model.require_valid(); cfg = self.config()
            except Exception as exc:
                QMessageBox.critical(self, "入力を確認してください", str(exc)); return
            self.invalidate(); self.set_busy(True); self.progress.setValue(0)
            self.worker = Worker(model, cfg, self)
            self.worker.progress.connect(lambda done,total: self.progress.setValue(round(100*done/total)))
            self.worker.succeeded.connect(self.show_result)
            self.worker.failed.connect(lambda msg: self.summary_label.setText(msg))
            self.worker.finished.connect(lambda: self.set_busy(False))
            self.worker.start()

        def show_result(self, result):
            self.result = result; self.export_button.setEnabled(True)
            s = result.summary["makespan"]
            ci = f"{s['ci_low']:.3f}〜{s['ci_high']:.3f}" if s["ci_low"] is not None else "試行1回のため算出不可"
            tops = ", ".join(result.summary["improvement_top"]) or "未計算"
            self.summary_label.setText(f"全体完了時間の平均: {s['mean']:.3f}\n平均の95%区間: {ci}\n改善効果が最大: {tops}\n同率や区間の重なりにも注意。")
            values = [r["makespan"] for r in result.runs]
            hist, bins = np.histogram(values, bins=min(20, max(1,int(math.sqrt(len(values))))))
            self.hist.addItem(pg.BarGraphItem(x=(bins[1:]+bins[:-1])/2, height=hist, width=np.diff(bins)*.9, brush="#447d9f"))
            self.hist.setLabel("bottom", "全体完了時間"); self.hist.setLabel("left", "試行数")
            ids = sorted(result.model.nodes)
            for plot, key, label in ((self.waitplot,"queue_mean","設備待ち時間 / 製品"),(self.gainplot,"delta","全体完了時間の短縮")):
                if key == "delta" and not result.config.sensitivity: continue
                vals = [result.summary["nodes"][nid][key]["mean"] for nid in ids]
                plot.addItem(pg.BarGraphItem(x=np.arange(len(ids)),height=vals,width=.7,brush="#cf8153" if key=="delta" else "#447d9f"))
                plot.getAxis("bottom").setTicks([list(enumerate(ids))]); plot.setLabel("left",label)
            headers = ["工程", "名前", "設備待ち", "合流待ち", "稼働率", "短縮時間", "短縮率 (%)"]
            self.table.setColumnCount(len(headers)); self.table.setHorizontalHeaderLabels(headers); self.table.setRowCount(len(ids))
            ids.sort(key=lambda nid: -result.summary["nodes"][nid]["delta" if result.config.sensitivity else "queue_mean"]["mean"])
            for row,nid in enumerate(ids):
                stat = result.summary["nodes"][nid]
                vals = [nid,result.model.nodes[nid].name]+[f"{stat[k]['mean']:.4f}" if k in stat else "—" for k in ("queue_mean","sync_mean","utilization","delta","gain_percent")]
                for col,val in enumerate(vals): self.table.setItem(row,col,QTableWidgetItem(val))
                if nid in result.summary["improvement_top"]: self.scene.nodes[nid].setBrush(QBrush(QColor("#f3ccaa")))
            self.statusBar().showMessage("計算完了。結果保存で詳細CSV、95%区間つき図、再現用JSONを出力できます", 10000)

        def export_results(self):
            if self.result is None: return
            path = QFileDialog.getExistingDirectory(self, "結果の保存先 (空のフォルダ)")
            if not path: return
            try:
                export_result(self.result, Path(path))
                self.statusBar().showMessage("結果を保存しました", 6000)
            except Exception as exc: QMessageBox.critical(self, "結果保存エラー", str(exc))

        def closeEvent(self, event):
            if self.worker and self.worker.isRunning():
                self.worker.requestInterruption(); self.statusBar().showMessage("計算を中止しています。終了後に閉じてください")
                event.ignore(); return
            if self.can_discard(): event.accept()
            else: event.ignore()

    return QApplication, MainWindow


# 9. Command-line interface -------------------------------------------------
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command")
    ex = sub.add_parser("examples", help="12工程の入力例と5シナリオを生成")
    ex.add_argument("--out", type=Path, required=True)
    val = sub.add_parser("validate", help="JSON/CSVの整合性を確認")
    group = val.add_mutually_exclusive_group(required=True)
    group.add_argument("--model",type=Path); group.add_argument("--csv-dir",type=Path)
    for command in ("run", "benchmark"):
        p = sub.add_parser(command)
        if command == "run":
            group = p.add_mutually_exclusive_group(required=True)
            group.add_argument("--model",type=Path); group.add_argument("--csv-dir",type=Path)
            p.add_argument("--no-sensitivity",action="store_true")
            p.add_argument("--no-figures",action="store_true")
            p.add_argument("--all-traces",action="store_true")
        p.add_argument("--out",type=Path,required=True)
        p.add_argument("--jobs",type=int,default=None); p.add_argument("--runs",type=int,default=None)
        p.add_argument("--interval",type=float,default=None); p.add_argument("--seed",type=int,default=None)
        p.add_argument("--improvement",type=float,default=None,help="処理時間の短縮割合 (0.1 = 10%%)")
    args = parser.parse_args(argv)
    try:
        if args.command is None:
            QApplication, MainWindow = build_gui_classes()
            app = QApplication(sys.argv[:1]); window = MainWindow(); window.show()
            return app.exec()
        if args.command == "examples":
            create_examples(args.out); print(f"Created: {args.out}"); return 0
        model = None
        if args.command in ("validate", "run"):
            model = load_json(args.model) if args.model else load_csv(args.csv_dir)
        if args.command == "validate":
            print(f"OK: {len(model.nodes)} processes, {len(model.edges)} edges, AND-fork/join DAG"); return 0
        params = {}
        if args.command == "run" and args.model:
            params.update(json.loads(args.model.read_text(encoding="utf-8-sig")).get("simulation", {}))
        for name in ("jobs", "runs", "interval", "seed", "improvement"):
            value = getattr(args,name)
            if value is not None: params[name] = value
        if args.command == "run":
            if args.no_sensitivity: params["sensitivity"] = False
            if args.all_traces: params["all_traces"] = True
        config = SimulationConfig(**params); config.validate()
        if args.out.exists() and any(args.out.iterdir()): raise ValueError("出力先は空のフォルダを指定する")
        if args.command == "benchmark":
            run_benchmark(config,args.out)
        else:
            result = run_experiment(model,config)
            export_result(result,args.out,figures=not args.no_figures)
            print(json.dumps({k:result.summary[k] for k in ("makespan","queue_top","improvement_top")},ensure_ascii=False,indent=2))
        print(f"Saved: {args.out}"); return 0
    except (ValueError, OSError, TypeError, ImportError) as exc:
        print(f"Error: {exc}",file=sys.stderr); return 2


if __name__ == "__main__":
    raise SystemExit(main())
