from __future__ import annotations

import argparse
import copy
import json
import statistics
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

from algorithms.maxflow.base import MaxFlowBase
from algorithms.maxflow.dinic import Dinic
from algorithms.maxflow.ford_fulkerson import FordFulkerson
from cases.scenario_loader import ScenarioLoader
from config.settings import CASES_DIR, OUTPUT_DIR


ALGORITHMS: Dict[str, Type[MaxFlowBase]] = {
    "ford_fulkerson": FordFulkerson,
    "dinic": Dinic,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scripts.run_maxflow",
        description="Jalankan dan bandingkan Ford-Fulkerson vs Dinic pada skenario YAML.",
    )
    parser.add_argument(
        "scenario",
        nargs="?",
        default=str(CASES_DIR / "case_22_konser_jis.yaml"),
        help="Path YAML skenario (default: case_22_konser_jis.yaml).",
    )
    parser.add_argument(
        "--algorithm",
        choices=["both", "ford_fulkerson", "dinic"],
        default="both",
        help="Algoritma yang dijalankan (default: both).",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Jumlah pengulangan untuk median runtime (default: 1).",
    )
    parser.add_argument(
        "--json",
        dest="json_path",
        default=None,
        help="Simpan hasil lengkap ke file JSON.",
    )
    return parser


def _event_payload(event: Dict[str, Any], start: int, goal: int) -> Dict[str, Any]:
    return {
        "type": event.get("type"),
        "edge": tuple(event["target_edge"]),
        "new_weight": event.get("new_weight"),
        "new_capacity": event.get("new_capacity"),
        "start": start,
        "goal": goal,
    }


def _build_topology(model) -> Dict[str, Any]:
    """Ambil daftar vertex (id, label) dan edge (from, to, capacity) dari graf."""
    graph = model.nx_graph
    vertices = [
        {
            "id": node,
            "label": data.get("label") or data.get("name") or str(node),
        }
        for node, data in graph.nodes(data=True)
    ]
    edges = [
        {
            "from": u,
            "to": v,
            "capacity": data.get("capacity", data.get("weight")),
        }
        for u, v, data in graph.edges(data=True)
    ]
    return {"vertices": vertices, "edges": edges}


def _run_once(
    scenario_path: Path,
    algorithm_name: str,
    algorithm_class: Type[MaxFlowBase],
) -> Dict[str, Any]:
    loader = ScenarioLoader(scenario_path)
    plan = loader.get_execution_plan()
    model = loader.build_graph_model()
    solver = algorithm_class(model)

    start = plan["start_node"]
    goal = plan["goal_node"]

    t0 = time.perf_counter()
    path, max_flow = solver.run(start, goal)
    initial_runtime_ms = (time.perf_counter() - t0) * 1000
    initial_path = list(path)
    initial_max_flow = max_flow
    initial_summary = {
        "max_flow": initial_max_flow,
        "path": initial_path,
        "min_cut_value": solver.min_cut_value,
        "min_cut_edges": solver.min_cut_edges,
        "augmentations": solver.augmentations,
        "bfs_phases": solver.bfs_phases,
        "flow_paths": copy.deepcopy(solver.flow_paths),
    }

    event_results: List[Dict[str, Any]] = []
    for index, event in enumerate(plan.get("events", []), 1):
        if event.get("type") not in solver.SUPPORTED_EVENT_TYPES:
            event_results.append(
                {
                    "step": event.get("step", index),
                    "description": event.get("description", ""),
                    "skipped": True,
                }
            )
            continue

        t0 = time.perf_counter()
        path, max_flow = solver.handle_dynamic_event(
            _event_payload(event, start, goal)
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000

        event_results.append(
            {
                "step": event.get("step", index),
                "description": event.get("description", ""),
                "target_edge": list(event["target_edge"]),
                "new_capacity": event.get("new_capacity"),
                "path": list(path),
                "max_flow": max_flow,
                "min_cut_edges": solver.min_cut_edges,
                "min_cut_value": solver.min_cut_value,
                "flow_paths": copy.deepcopy(solver.flow_paths),
                "runtime_ms": elapsed_ms,
            }
        )

    return {
        "algorithm": algorithm_name,
        "initial": {
            **initial_summary,
            "runtime_ms": initial_runtime_ms,
            "nodes": model.nx_graph.number_of_nodes(),
            "edges": model.nx_graph.number_of_edges(),
        },
        "events": event_results,
        "final": {
            "max_flow": solver.max_flow_value,
            "min_cut_value": solver.min_cut_value,
            "min_cut_edges": solver.min_cut_edges,
            "augmentations": solver.augmentations,
            "bfs_phases": solver.bfs_phases,
        },
    }


def _run_algorithm(
    scenario_path: Path,
    algorithm_name: str,
    algorithm_class: Type[MaxFlowBase],
    repeat: int,
) -> Dict[str, Any]:
    runs = [_run_once(scenario_path, algorithm_name, algorithm_class) for _ in range(repeat)]
    first = runs[0]

    first["initial"]["runtime_ms"] = statistics.median(
        run["initial"]["runtime_ms"] for run in runs
    )

    for index, event in enumerate(first["events"]):
        event_runtimes = [
            run["events"][index].get("runtime_ms")
            for run in runs
            if index < len(run["events"]) and "runtime_ms" in run["events"][index]
        ]
        if event_runtimes:
            event["runtime_ms"] = statistics.median(event_runtimes)

    return first


def _format_number(value: Optional[float]) -> str:
    if value is None:
        return "-"
    value = float(value)
    if value.is_integer():
        return f"{int(value):,}".replace(",", ".")
    return f"{value:,.1f}".replace(",", ".")


def _print_result(result: Dict[str, Any]) -> None:
    summary = result["initial"]
    print(f"\n[{result['algorithm']}]")
    print(
        f"  Max flow awal : {_format_number(summary['max_flow'])}"
        f" | augmentasi: {summary['augmentations']}"
        f" | fase BFS: {summary['bfs_phases']}"
        f" | runtime: {summary['runtime_ms']:.3f} ms"
    )
    print(f"  Min-cut       : {_format_number(summary['min_cut_value'])}")
    for edge in summary["min_cut_edges"]:
        print(
            f"    ({edge['from']} -> {edge['to']}) "
            f"kapasitas {_format_number(edge['capacity'])}"
        )

    for event in result["events"]:
        if event.get("skipped"):
            print(f"  [SKIPPED] step {event['step']}: {event['description']}")
            continue
        print(
            f"  Event {event['step']}: {event['description']}\n"
            f"    -> max flow {_format_number(event['max_flow'])}"
            f" | min-cut {_format_number(event['min_cut_value'])}"
            f" | runtime {event['runtime_ms']:.3f} ms"
        )


def main(argv: Optional[List[str]] = None) -> None:
    args = build_parser().parse_args(argv)
    scenario_path = Path(args.scenario)
    repeat = max(1, args.repeat)

    loader = ScenarioLoader(scenario_path)
    metadata = loader.get_metadata()
    plan = loader.get_execution_plan()
    model = loader.build_graph_model()

    print(f"=== MAX FLOW: {metadata.get('title', scenario_path.stem)} ===")
    print(
        f"Graph: {model.nx_graph.number_of_nodes()} nodes, "
        f"{model.nx_graph.number_of_edges()} edges | "
        f"source={plan['start_node']}, sink={plan['goal_node']} | "
        f"repeat={repeat}"
    )

    selected = (
        list(ALGORITHMS.items())
        if args.algorithm == "both"
        else [(args.algorithm, ALGORITHMS[args.algorithm])]
    )

    results = []
    for name, algorithm_class in selected:
        result = _run_algorithm(scenario_path, name, algorithm_class, repeat)
        results.append(result)
        _print_result(result)

    if len(results) == 2:
        ff, dinic = results
        ff_flow = ff["initial"]["max_flow"]
        dinic_flow = dinic["initial"]["max_flow"]
        if ff_flow == dinic_flow:
            print(
                f"\n[OK] Ford-Fulkerson dan Dinic sepakat: "
                f"max flow awal {_format_number(ff_flow)}."
            )
        else:
            print(
                f"\n[WARNING] Hasil berbeda: FF={_format_number(ff_flow)}, "
                f"Dinic={_format_number(dinic_flow)}."
            )

    if args.json_path:
        target = Path(args.json_path)
        if not target.is_absolute():
            target = OUTPUT_DIR / target
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {
                    "metadata": metadata,
                    "execution_plan": {
                        "start_node": plan["start_node"],
                        "goal_node": plan["goal_node"],
                    },
                    "topology": _build_topology(model),
                    "results": results,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        print(f"\n[JSON] Hasil disimpan ke: {target}")


if __name__ == "__main__":
    main()
