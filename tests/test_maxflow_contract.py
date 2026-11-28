from pathlib import Path

import pytest

from cases.scenario_loader import ScenarioLoader
from config.settings import CASES_DIR


JIS_SCENARIO = CASES_DIR / "case_22_konser_jis.yaml"


@pytest.fixture
def jis_model():
    """Model JIS yang selalu dibangun ulang agar test tidak saling mencemari."""
    return ScenarioLoader(JIS_SCENARIO).build_graph_model()


def test_jis_graph_has_required_vertices_and_edges(jis_model):
    """Case JIS harus memenuhi syarat minimal 20 vertex dan topologi final."""
    graph = jis_model.nx_graph

    assert graph.number_of_nodes() == 22
    assert graph.number_of_edges() == 29
    assert graph.number_of_nodes() >= 20


def test_jis_all_edges_have_capacity(jis_model):
    """Semua edge maxflow wajib membawa atribut capacity yang valid."""
    graph = jis_model.nx_graph
    missing = [
        (u, v)
        for u, v, data in graph.edges(data=True)
        if data.get("capacity") is None
    ]

    assert missing == []
    assert all(float(data["capacity"]) >= 0 for _, _, data in graph.edges(data=True))


def test_loader_preserves_specific_jis_capacity(jis_model):
    """Nilai kapasitas tidak boleh hilang saat YAML dikonversi ke graf."""
    graph = jis_model.nx_graph

    assert graph[5][21]["capacity"] == 1500.0
    assert graph[9][8]["capacity"] == 1600.0


def test_topology_export_includes_capacity(jis_model):
    """Trace JSON harus bisa dipakai Jocelyn untuk audit kapasitas edge."""
    topology = jis_model.get_topology_dict()
    exported = {(edge["from"], edge["to"]): edge for edge in topology["edges"]}

    assert exported[(5, 21)]["capacity"] == 1500.0
    assert "capacity" in exported[(9, 8)]


def test_loader_rejects_negative_capacity(tmp_path: Path):
    """Kapasitas negatif adalah data rusak, bukan kondisi jalan."""
    scenario = tmp_path / "negative_capacity.yaml"
    scenario.write_text(
        """
case_id: "negative_capacity"
title: "Invalid capacity"
description: "Fixture untuk validasi loader."
nodes:
  - id: 0
    label: "Source"
    pos: [0.0, 0.0]
  - id: 1
    label: "Sink"
    pos: [1.0, 0.0]
edges:
  - from: 0
    to: 1
    weight: 1.0
    capacity: -10.0
execution_plan:
  start_node: 0
  goal_node: 1
  events: []
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="tidak boleh negatif"):
        ScenarioLoader(scenario).build_graph_model()
