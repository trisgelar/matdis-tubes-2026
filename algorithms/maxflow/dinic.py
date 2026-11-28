from __future__ import annotations

import sys
from collections import deque
from typing import Dict, List

from algorithms.maxflow.base import MaxFlowBase
from algorithms.registry import AlgorithmRegistry
from core.graph_model import SpatialGraphModel


class Dinic(MaxFlowBase):
    """Maximum flow dengan level graph BFS + blocking flow DFS.

    Perbedaan utama dengan Ford-Fulkerson:
    - FF mencari satu augmenting path dengan DFS, lalu mengulang dari awal.
    - Dinic membangun level graph dengan BFS, lalu mengirim blocking flow
      memakai DFS yang hanya boleh bergerak ke level berikutnya.
    """

    def __init__(self, model: SpatialGraphModel):
        super().__init__(model)
        self.level: Dict[int, int] = {}
        self.it: Dict[int, int] = {}

    def _bfs_level_graph(self, source: int, sink: int) -> bool:
        self.level = {node: -1 for node in self.graph.nodes}
        self.level[source] = 0
        queue = deque([source])

        while queue:
            u = queue.popleft()
            for edge in self.adj.get(u, []):
                if edge.capacity > 0 and self.level[edge.to] < 0:
                    self.level[edge.to] = self.level[u] + 1
                    queue.append(edge.to)

        return self.level.get(sink, -1) >= 0

    def _dfs(
        self,
        u: int,
        sink: int,
        pushed: float,
        path: List[int],
    ) -> float:
        if pushed <= 0:
            return 0.0
        if u == sink:
            return pushed

        while self.it[u] < len(self.adj.get(u, [])):
            edge = self.adj[u][self.it[u]]
            if edge.capacity > 0 and self.level.get(edge.to, -1) == self.level[u] + 1:
                sent = self._dfs(
                    edge.to,
                    sink,
                    min(pushed, edge.capacity),
                    path + [edge.to],
                )
                if sent > 0:
                    edge.capacity -= sent
                    self.adj[edge.to][edge.rev].capacity += sent

                    if edge.to == sink:
                        self.augmentations += 1
                        self.flow_paths.append(
                            {"path": path + [edge.to], "flow": sent}
                        )

                    return sent
            self.it[u] += 1

        return 0.0

    def run(self, source_node: int, sink_node: int):
        self._reset_state()
        self._validate_endpoints(source_node, sink_node)
        self._build_residual()

        old_limit = sys.getrecursionlimit()
        sys.setrecursionlimit(max(old_limit, len(self.graph.nodes) * 4 + 100))

        self.log_step(
            event_type="INITIALIZATION",
            state_mutations={
                "algorithm": "dinic",
                "source": source_node,
                "sink": sink_node,
                "nodes": self.graph.number_of_nodes(),
                "edges": self.graph.number_of_edges(),
                "max_flow": 0.0,
            },
        )

        max_flow = 0.0
        representative_path: List[int] = []

        try:
            while self._bfs_level_graph(source_node, sink_node):
                self.bfs_phases += 1
                self.it = {node: 0 for node in self.graph.nodes}

                self.log_step(
                    event_type="BFS_LEVEL_GRAPH",
                    state_mutations={
                        "phase": self.bfs_phases,
                        "levels": self.level.copy(),
                    },
                )

                phase_flow = 0.0
                while True:
                    sent = self._dfs(
                        source_node,
                        sink_node,
                        float("inf"),
                        [source_node],
                    )
                    if sent <= 0:
                        break
                    max_flow += sent
                    phase_flow += sent
                    if not representative_path:
                        representative_path = self.flow_paths[-1]["path"]

                self.log_step(
                    event_type="BLOCKING_FLOW_COMPLETE",
                    state_mutations={
                        "phase": self.bfs_phases,
                        "phase_flow": phase_flow,
                        "current_max_flow": max_flow,
                    },
                )
        finally:
            sys.setrecursionlimit(old_limit)

        return self._finalize(source_node, max_flow, representative_path)


AlgorithmRegistry.register("dinic", Dinic)
AlgorithmRegistry.register_alias("maxflow", "dinic")
