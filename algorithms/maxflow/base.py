from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from core.base_algorithm import BaseGraphAlgorithm
from core.graph_model import SpatialGraphModel


@dataclass
class _ResidualEdge:
    """Satu sisi pada residual graph.

    ``original_capacity`` hanya diisi pada sisi forward yang berasal dari YAML.
    Sisi reverse selalu mulai dari kapasitas 0.
    """

    to: int
    rev: int
    capacity: float
    original_capacity: float = 0.0
    original_edge: Optional[Tuple[int, int]] = None


class MaxFlowBase(BaseGraphAlgorithm):
    """Fondasi bersama untuk Ford-Fulkerson dan Dinic.

    Kelas ini tidak menyelesaikan alur augmentasi; itu tanggung jawab subclass.
    Yang dibagi di sini adalah validasi input, residual graph, min-cut, dan
    pelaporan metrik.
    """

    SUPPORTED_EVENT_TYPES = frozenset({"DYNAMIC_EDGE_CAPACITY"})

    def __init__(self, model: SpatialGraphModel):
        super().__init__(model)
        self.adj: Dict[int, List[_ResidualEdge]] = {}
        self.max_flow_value = 0.0
        self.min_cut_edges: List[Dict[str, Any]] = []
        self.min_cut_value = 0.0
        self.flow_paths: List[Dict[str, Any]] = []
        self.augmentations = 0
        self.bfs_phases = 0
        self.reachable_nodes: Set[int] = set()
        self.unreachable_nodes: Set[int] = set()

    def _reset_state(self) -> None:
        self.max_flow_value = 0.0
        self.min_cut_edges = []
        self.min_cut_value = 0.0
        self.flow_paths = []
        self.augmentations = 0
        self.bfs_phases = 0
        self.reachable_nodes = set()
        self.unreachable_nodes = set()
        self.adj = {}

    def _validate_endpoints(self, source: int, sink: int) -> None:
        if source == sink:
            raise ValueError("Source dan sink tidak boleh node yang sama.")
        if source not in self.graph:
            raise KeyError(f"Source node {source} tidak ada di graf.")
        if sink not in self.graph:
            raise KeyError(f"Sink node {sink} tidak ada di graf.")

        missing = [
            (u, v)
            for u, v, data in self.graph.edges(data=True)
            if data.get("capacity") is None
        ]
        if missing:
            raise ValueError(
                "Edge maxflow berikut belum punya atribut capacity: "
                + ", ".join(f"({u}, {v})" for u, v in missing)
            )

        negative = [
            (u, v, float(data["capacity"]))
            for u, v, data in self.graph.edges(data=True)
            if float(data["capacity"]) < 0
        ]
        if negative:
            raise ValueError(
                "Kapasitas edge tidak boleh negatif: "
                + ", ".join(f"({u}, {v})={cap}" for u, v, cap in negative)
            )

    def _build_residual(self) -> None:
        """Bangun residual graph dari kapasitas asli di NetworkX.

        Residual graph memakai objek sisi terpisah, sehingga dua edge berlawanan
        arah (u -> v dan v -> u) tetap direpresentasikan dengan benar.
        """
        self.adj = {node: [] for node in self.graph.nodes}

        for u, v, data in self.graph.edges(data=True):
            capacity = float(data["capacity"])
            self._add_residual_edge(u, v, capacity, original_edge=(u, v))

    def _add_residual_edge(
        self,
        u: int,
        v: int,
        capacity: float,
        original_edge: Optional[Tuple[int, int]] = None,
    ) -> None:
        forward = _ResidualEdge(
            to=v,
            rev=len(self.adj[v]),
            capacity=capacity,
            original_capacity=capacity,
            original_edge=original_edge,
        )
        backward = _ResidualEdge(
            to=u,
            rev=len(self.adj[u]),
            capacity=0.0,
        )
        self.adj[u].append(forward)
        self.adj[v].append(backward)

    def _reachable_from_source(self, source: int) -> Set[int]:
        reachable = {source}
        queue = deque([source])

        while queue:
            u = queue.popleft()
            for edge in self.adj.get(u, []):
                if edge.capacity > 0 and edge.to not in reachable:
                    reachable.add(edge.to)
                    queue.append(edge.to)

        return reachable

    def _finalize(self, source: int, max_flow: float, representative_path: List[int]):
        self.max_flow_value = float(max_flow)
        self.reachable_nodes = self._reachable_from_source(source)
        self.unreachable_nodes = set(self.graph.nodes) - self.reachable_nodes

        cut_edges: List[Dict[str, Any]] = []
        for u, v, data in self.graph.edges(data=True):
            if u in self.reachable_nodes and v in self.unreachable_nodes:
                cut_edges.append(
                    {
                        "from": u,
                        "to": v,
                        "capacity": float(data["capacity"]),
                    }
                )

        self.min_cut_edges = cut_edges
        self.min_cut_value = float(sum(edge["capacity"] for edge in cut_edges))

        self.log_step(
            event_type="MAX_FLOW_REACHED",
            state_mutations={
                "source": source,
                "max_flow": self.max_flow_value,
                "min_cut_value": self.min_cut_value,
                "min_cut_edges": cut_edges,
                "augmentations": self.augmentations,
                "bfs_phases": self.bfs_phases,
                "reachable_nodes": sorted(self.reachable_nodes),
            },
        )

        return representative_path, self.max_flow_value

    def handle_dynamic_event(self, event_data: Dict[str, Any]):
        """Terapkan perubahan kapasitas lalu hitung ulang dari nol.

        Recompute from scratch dipilih karena flow lama bisa melanggar kapasitas
        baru ketika kapasitas diturunkan atau edge ditutup. Untuk graf sebesar
        JIS, biaya recompute masih sangat murah dan hasilnya pasti optimal.
        """
        event_type = event_data.get("type")
        if event_type is not None and event_type not in self.SUPPORTED_EVENT_TYPES:
            raise ValueError(f"Tipe event tidak didukung oleh maxflow: {event_type}")

        edge = tuple(event_data["edge"])
        if len(edge) != 2:
            raise ValueError(f"target_edge harus berisi dua node: {edge}")
        u, v = edge

        if not self.graph.has_edge(u, v):
            raise KeyError(f"Edge ({u}, {v}) tidak ditemukan di graf.")

        new_capacity = event_data.get("new_capacity")
        if new_capacity is None:
            new_capacity = event_data.get("new_weight")
        if new_capacity is None:
            raise KeyError(
                f"Event untuk edge ({u}, {v}) tidak punya new_capacity/new_weight."
            )

        new_capacity = float(new_capacity)
        if new_capacity < 0:
            raise ValueError(f"Kapasitas baru edge ({u}, {v}) negatif: {new_capacity}")

        old_capacity = float(self.graph[u][v].get("capacity"))
        self.graph[u][v]["capacity"] = new_capacity

        self.log_step(
            event_type="UPDATE_CAPACITY_EVENT",
            state_mutations={
                "target_edge": [u, v],
                "old_capacity": old_capacity,
                "new_capacity": new_capacity,
            },
        )

        return self.run(event_data["start"], event_data["goal"])
