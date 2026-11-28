from __future__ import annotations

import sys
from typing import Dict, List, Optional, Tuple

from algorithms.maxflow.base import MaxFlowBase
from algorithms.registry import AlgorithmRegistry
from core.graph_model import SpatialGraphModel


class FordFulkerson(MaxFlowBase):
    """Maximum flow dengan Ford-Fulkerson murni: DFS mencari augmenting path.

    Implementasi ini sengaja tidak memakai BFS. Versi BFS adalah Edmonds-Karp;
    memisahkannya membuat perbandingan konseptual FF vs Dinic di laporan menjadi
    jujur: FF memilih path apa pun yang ditemukan DFS, sedangkan Dinic memakai
    level graph dan blocking flow.
    """

    def __init__(self, model: SpatialGraphModel):
        super().__init__(model)

    def _find_augmenting_path(
        self, source: int, sink: int
    ) -> Optional[Dict[int, Tuple[int, int]]]:
        """Cari satu path source -> sink di residual graph dengan DFS.

        Return ``parent`` dengan format ``child -> (parent, edge_index)``.
        """
        parent: Dict[int, Tuple[int, int]] = {}
        visited = {source}

        def dfs(u: int) -> bool:
            if u == sink:
                return True

            for edge_index, edge in enumerate(self.adj.get(u, [])):
                if edge.capacity <= 0 or edge.to in visited:
                    continue
                visited.add(edge.to)
                parent[edge.to] = (u, edge_index)
                if dfs(edge.to):
                    return True

            return False

        return parent if dfs(source) else None

    def run(self, source_node: int, sink_node: int):
        self._reset_state()
        self._validate_endpoints(source_node, sink_node)
        self._build_residual()

        old_limit = sys.getrecursionlimit()
        sys.setrecursionlimit(max(old_limit, len(self.graph.nodes) * 4 + 100))

        self.log_step(
            event_type="INITIALIZATION",
            state_mutations={
                "algorithm": "ford_fulkerson",
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
            while True:
                parent = self._find_augmenting_path(source_node, sink_node)
                if parent is None:
                    break

                path = [sink_node]
                bottleneck = float("inf")
                v = sink_node
                while v != source_node:
                    u, edge_index = parent[v]
                    bottleneck = min(bottleneck, self.adj[u][edge_index].capacity)
                    path.append(u)
                    v = u
                path.reverse()

                v = sink_node
                while v != source_node:
                    u, edge_index = parent[v]
                    edge = self.adj[u][edge_index]
                    edge.capacity -= bottleneck
                    self.adj[v][edge.rev].capacity += bottleneck
                    v = u

                max_flow += bottleneck
                self.augmentations += 1
                self.flow_paths.append({"path": path, "flow": bottleneck})
                if not representative_path:
                    representative_path = path

                self.log_step(
                    event_type="AUGMENTING_PATH_FOUND",
                    state_mutations={
                        "path": path,
                        "bottleneck": bottleneck,
                        "current_max_flow": max_flow,
                        "augmentation": self.augmentations,
                    },
                )
        finally:
            sys.setrecursionlimit(old_limit)

        return self._finalize(source_node, max_flow, representative_path)


AlgorithmRegistry.register("ford_fulkerson", FordFulkerson)
