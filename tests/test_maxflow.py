from __future__ import annotations

from typing import Iterable, Tuple

import networkx as nx
import pytest

from algorithms.maxflow.dinic import Dinic
from algorithms.maxflow.ford_fulkerson import FordFulkerson
from algorithms.registry import AlgorithmRegistry
from cases.scenario_loader import ScenarioLoader
from config.settings import CASES_DIR
from core.graph_model import SpatialGraphModel


JIS_SCENARIO = CASES_DIR / "case_22_konser_jis.yaml"
ALGORITHMS = [FordFulkerson, Dinic]


def _build_model(
    edges: Iterable[Tuple[int, int, float]],
    nodes: Iterable[int],
) -> SpatialGraphModel:
    model = SpatialGraphModel()
    for node in nodes:
        model.add_spatial_node(node)

    for u, v, capacity in edges:
        model.add_weighted_edge(u, v, weight=1.0, capacity=capacity)

    return model


def _jis_model() -> SpatialGraphModel:
    return ScenarioLoader(JIS_SCENARIO).build_graph_model()


def _cut_set(edges):
    return {(edge["from"], edge["to"], edge["capacity"]) for edge in edges}


@pytest.mark.parametrize("algorithm_class", ALGORITHMS)
def test_known_graph_matches_networkx(algorithm_class):
    edges = [
        (0, 1, 3.0),
        (0, 2, 2.0),
        (1, 2, 1.0),
        (1, 3, 2.0),
        (2, 3, 3.0),
    ]
    model = _build_model(edges, range(4))

    solver = algorithm_class(model)
    path, max_flow = solver.run(0, 3)

    assert max_flow == 5.0
    assert path[0] == 0 and path[-1] == 3
    assert solver.min_cut_value == max_flow
    assert nx.maximum_flow_value(model.nx_graph, 0, 3) == max_flow


@pytest.mark.parametrize("algorithm_class", ALGORITHMS)
def test_antiparallel_edges_are_supported(algorithm_class):
    edges = [
        (0, 1, 3.0),
        (1, 0, 2.0),
        (0, 2, 2.0),
        (1, 2, 3.0),
        (2, 3, 4.0),
    ]
    model = _build_model(edges, range(4))

    solver = algorithm_class(model)
    _, max_flow = solver.run(0, 3)

    assert max_flow == nx.maximum_flow_value(model.nx_graph, 0, 3)
    assert solver.min_cut_value == max_flow


@pytest.mark.parametrize("algorithm_class", ALGORITHMS)
def test_disconnected_graph_returns_zero(algorithm_class):
    model = _build_model([(0, 1, 3.0), (2, 3, 4.0)], range(4))

    solver = algorithm_class(model)
    path, max_flow = solver.run(0, 3)

    assert max_flow == 0.0
    assert path == []
    assert solver.min_cut_value == 0.0


@pytest.mark.parametrize("algorithm_class", ALGORITHMS)
def test_jis_initial_flow_and_min_cut(algorithm_class):
    solver = algorithm_class(_jis_model())
    path, max_flow = solver.run(0, 21)

    assert max_flow == 4600.0
    assert path[0] == 0 and path[-1] == 21
    assert solver.min_cut_value == max_flow
    assert _cut_set(solver.min_cut_edges) == {
        (4, 18, 1000.0),
        (5, 21, 1500.0),
        (14, 19, 1200.0),
        (20, 21, 900.0),
    }


def test_ff_and_dinic_agree_on_jis():
    ff = FordFulkerson(_jis_model())
    dinic = Dinic(_jis_model())

    _, ff_flow = ff.run(0, 21)
    _, dinic_flow = dinic.run(0, 21)

    assert ff_flow == dinic_flow == 4600.0
    assert ff.min_cut_value == dinic.min_cut_value == 4600.0
    assert _cut_set(ff.min_cut_edges) == _cut_set(dinic.min_cut_edges)


@pytest.mark.parametrize("algorithm_class", ALGORITHMS)
def test_jis_dynamic_capacity_events(algorithm_class):
    solver = algorithm_class(_jis_model())

    _, initial = solver.run(0, 21)
    _, after_closure = solver.handle_dynamic_event(
        {
            "type": "DYNAMIC_EDGE_CAPACITY",
            "edge": (5, 21),
            "new_capacity": 0.0,
            "start": 0,
            "goal": 21,
        }
    )
    _, after_narrowing = solver.handle_dynamic_event(
        {
            "type": "DYNAMIC_EDGE_CAPACITY",
            "edge": (9, 8),
            "new_capacity": 600.0,
            "start": 0,
            "goal": 21,
        }
    )

    assert initial == 4600.0
    assert after_closure == 3100.0
    assert after_narrowing == 2800.0
    assert solver.min_cut_value == after_narrowing


@pytest.mark.parametrize("algorithm_class", ALGORITHMS)
def test_jis_reopening_one_bottleneck_is_not_enough(algorithm_class):
    solver = algorithm_class(_jis_model())
    solver.run(0, 21)

    solver.handle_dynamic_event(
        {
            "type": "DYNAMIC_EDGE_CAPACITY",
            "edge": (5, 21),
            "new_capacity": 0.0,
            "start": 0,
            "goal": 21,
        }
    )
    solver.handle_dynamic_event(
        {
            "type": "DYNAMIC_EDGE_CAPACITY",
            "edge": (9, 8),
            "new_capacity": 600.0,
            "start": 0,
            "goal": 21,
        }
    )
    _, after_reopen = solver.handle_dynamic_event(
        {
            "type": "DYNAMIC_EDGE_CAPACITY",
            "edge": (5, 21),
            "new_capacity": 1500.0,
            "start": 0,
            "goal": 21,
        }
    )

    assert after_reopen == 4300.0

    _, after_full_restore = solver.handle_dynamic_event(
        {
            "type": "DYNAMIC_EDGE_CAPACITY",
            "edge": (9, 8),
            "new_capacity": 1600.0,
            "start": 0,
            "goal": 21,
        }
    )
    assert after_full_restore == 4600.0


@pytest.mark.parametrize("algorithm_class", ALGORITHMS)
def test_missing_capacity_is_rejected(algorithm_class):
    model = _build_model([], [0, 1])
    model.add_weighted_edge(0, 1, weight=1.0)

    with pytest.raises(ValueError, match="capacity"):
        algorithm_class(model).run(0, 1)


@pytest.mark.parametrize("algorithm_class", ALGORITHMS)
def test_trace_is_recorded(algorithm_class):
    solver = algorithm_class(_jis_model())
    solver.run(0, 21)

    assert solver.step_count > 0
    assert len(solver.delta_logs) == solver.step_count
    assert solver.flow_paths
    assert sum(item["flow"] for item in solver.flow_paths) == pytest.approx(4600.0)


def test_registry_registers_both_algorithms():
    model = _jis_model()

    assert isinstance(AlgorithmRegistry.create("ford_fulkerson", model), FordFulkerson)
    assert isinstance(AlgorithmRegistry.create("dinic", model), Dinic)
    assert isinstance(AlgorithmRegistry.create("maxflow", model), Dinic)
