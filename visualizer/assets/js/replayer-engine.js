/**
 * ReplayerEngine — JIS Max Flow Visualizer
 * Mendukung format output dari run_maxflow.py (maxflow_case22.json)
 * maupun format trace standar (output_case_jis_konser_traffic.json).
 */

class ReplayerEngine {
  constructor(containerId) {
    this.containerId = containerId;
    this.network = null;
    this.data = null;
    this.currentStep = -1; // -1 = kondisi awal

    // Node/edge datasets untuk vis-network
    this.visNodes = new vis.DataSet();
    this.visEdges = new vis.DataSet();

    this._initNetwork();
  }

  /* ─────────────────────────────────────────
   * INIT
   * ───────────────────────────────────────── */
  _initNetwork() {
    const options = {
      physics: { enabled: false },
      edges: {
        arrows: { to: { enabled: true, scaleFactor: 0.6 } },
        color: { color: '#2e3250', highlight: '#4f8ef7' },
        width: 2,
        font: {
          color: '#94a3b8',
          size: 10,
          align: 'middle',
          strokeWidth: 2,
          strokeColor: '#0f1117',
        },
        smooth: { type: 'curvedCW', roundness: 0.1 },
      },
      nodes: {
        shape: 'dot',
        size: 14,
        color: { background: '#1e293b', border: '#4f8ef7', highlight: { background: '#4f8ef7', border: '#fff' } },
        font: { color: '#e2e8f0', size: 10, strokeWidth: 2, strokeColor: '#0f1117' },
        borderWidth: 2,
      },
      interaction: {
        hover: true,
        tooltipDelay: 100,
        zoomView: true,
      },
    };

    const container = document.getElementById(this.containerId);
    this.network = new vis.Network(
      container,
      { nodes: this.visNodes, edges: this.visEdges },
      options
    );
  }

  /* ─────────────────────────────────────────
   * LOAD DATA
   * ───────────────────────────────────────── */
  load(rawData) {
    this.data = this._normalize(rawData);
    this._buildGraph();
    this._buildEventButtons();
    this.goToStep(-1);
  }

  /**
   * Normalisasi dua format JSON berbeda menjadi format internal tunggal:
   * {
   *   nodes: [{id, label, pos}],
   *   edges: [{from, to, capacity}],
   *   results: { ff: {initial, events}, dinic: {initial, events} }
   * }
   */
  _normalize(raw) {
    // ── Format A: output dari run_maxflow.py ──
    // { metadata, execution_plan, results: [{algorithm, initial, events}] }
    if (raw.results && Array.isArray(raw.results)) {
      const ff    = raw.results.find(r => r.algorithm === 'ford_fulkerson') || raw.results[0];
      const dinic = raw.results.find(r => r.algorithm === 'dinic')          || raw.results[1] || ff;

      // Rekonstruksi edge-list dari flow_paths + min_cut_edges (approx.)
      // Fallback: pakai topology embed jika ada
      const nodes = GRAPH_TOPOLOGY.nodes;
      const edges = GRAPH_TOPOLOGY.edges;

      return { nodes, edges, ff, dinic, source: raw.execution_plan?.start_node ?? 0, sink: raw.execution_plan?.goal_node ?? 21 };
    }

    // ── Format B: export_trace_json standar ──
    // { metadata, total_steps, initial_topology: {nodes, edges}, raw_quantitative_trace }
    if (raw.initial_topology) {
      const nodes = raw.initial_topology.nodes || [];
      const edges = raw.initial_topology.edges || [];
      // Bungkus menjadi format FF dummy
      const dummy = { initial: { max_flow: null, min_cut_edges: [], flow_paths: [], augmentations: null, bfs_phases: null, runtime_ms: null }, events: [] };
      return { nodes, edges, ff: dummy, dinic: dummy, source: 0, sink: nodes.length - 1 };
    }

    console.warn('Format JSON tidak dikenali.');
    return { nodes: [], edges: [], ff: null, dinic: null };
  }

  /* ─────────────────────────────────────────
   * BUILD GRAPH
   * ───────────────────────────────────────── */
  _buildGraph() {
    const { nodes, edges, source, sink } = this.data;
    const SCALE = 70;

    this.visNodes.clear();
    this.visEdges.clear();

    // Nodes
    this.visNodes.add(nodes.map(n => {
      const [x, y] = n.pos || [0, 0];
      const isSource = n.id === source;
      const isSink   = n.id === sink;
      return {
        id: n.id,
        label: this._shortLabel(n.label || `Node ${n.id}`),
        title: n.label || `Node ${n.id}`,    // tooltip
        x: x * SCALE,
        y: -y * SCALE,                        // flip Y
        color: isSource ? { background: '#065f46', border: '#34d399' }
             : isSink   ? { background: '#7f1d1d', border: '#f87171' }
             : undefined,
        size: (isSource || isSink) ? 20 : 14,
        font: { size: isSource || isSink ? 11 : 9 },
      };
    }));

    // Edges
    this.visEdges.add(edges.map((e, i) => ({
      id: i,
      from: e.from,
      to: e.to,
      _cap: e.capacity,            // simpan kapasitas asli
      label: `${e.capacity}`,
      title: `${e.from} → ${e.to} · cap: ${e.capacity} kend/jam`,
    })));

    this.network.fit({ animation: { duration: 600, easingFunction: 'easeInOutQuad' } });
  }

  _shortLabel(label) {
    // Potong label panjang agar muat di node
    if (label.length <= 20) return label;
    // Ambil kata-kata bermakna
    const words = label.split(' ');
    if (words.length <= 3) return label;
    return words.slice(0, 3).join(' ') + '…';
  }

  /* ─────────────────────────────────────────
   * EVENT BUTTONS
   * ───────────────────────────────────────── */
  _buildEventButtons() {
    const container = document.getElementById('event-controls');
    container.innerHTML = `
      <button class="step-btn active" data-step="-1" onclick="setStep(-1)">
        🏁 Kondisi Awal
      </button>`;

    const events = this.data?.ff?.events || [];
    events.forEach((ev, i) => {
      const btn = document.createElement('button');
      btn.className = 'step-btn';
      btn.dataset.step = i;
      btn.onclick = () => setStep(i);
      btn.innerHTML = `<strong>Step ${ev.step}</strong><br><span style="color:#94a3b8;font-size:10px">${this._truncate(ev.description, 70)}</span>`;
      container.appendChild(btn);
    });
  }

  /* ─────────────────────────────────────────
   * STEP NAVIGATION
   * ───────────────────────────────────────── */
  goToStep(stepIndex) {
    this.currentStep = stepIndex;

    const isInitial = stepIndex === -1;
    const { ff, dinic } = this.data || {};
    if (!ff) return;

    const ffState    = isInitial ? ff.initial    : (ff.events?.[stepIndex]    || ff.initial);
    const dinicState = isInitial ? dinic?.initial : (dinic?.events?.[stepIndex] || dinic?.initial);
    const ev         = isInitial ? null : ff.events?.[stepIndex];

    // Event description panel
    const descPanel = document.getElementById('event-desc-panel');
    const descText  = document.getElementById('event-desc-text');
    if (ev) {
      descPanel.style.display = 'block';
      descText.textContent = ev.description;
    } else {
      descPanel.style.display = 'none';
    }

    // Update comparison table
    this._updateTable(ffState, dinicState, isInitial);

    // Update min-cut list
    this._updateMinCut(ffState?.min_cut_edges || []);

    // Update flow paths
    this._updatePaths(ffState?.flow_paths || []);

    // Update graph highlights
    this._highlightGraph(ffState, ev);
  }

  /* ─────────────────────────────────────────
   * UI UPDATERS
   * ───────────────────────────────────────── */
  _updateTable(ff, dinic, isInitial) {
    const tbody = document.getElementById('cmp-body');
    if (!ff) { tbody.innerHTML = '<tr><td colspan="3" class="empty">—</td></tr>'; return; }

    const fasterRuntime = (ff.runtime_ms != null && dinic?.runtime_ms != null)
      ? (ff.runtime_ms <= dinic.runtime_ms ? 'ff' : 'dinic') : null;

    const fmtFlow = v => v != null ? `<span class="val-flow">${v.toLocaleString('id-ID')}</span>` : '—';
    const fmtMs   = (v, who) => v != null
      ? `<span class="${fasterRuntime === who ? 'val-faster' : ''}">${v.toFixed(3)} ms ${fasterRuntime === who ? '⚡' : ''}</span>`
      : '—';

    tbody.innerHTML = `
      <tr>
        <td>Max Flow</td>
        <td>${fmtFlow(ff.max_flow)}</td>
        <td>${fmtFlow(dinic?.max_flow)}</td>
      </tr>
      <tr>
        <td>Min-Cut Value</td>
        <td>${ff.min_cut_value != null ? ff.min_cut_value.toLocaleString('id-ID') : '—'}</td>
        <td>${dinic?.min_cut_value != null ? dinic.min_cut_value.toLocaleString('id-ID') : '—'}</td>
      </tr>
      <tr>
        <td>Runtime</td>
        <td>${fmtMs(ff.runtime_ms, 'ff')}</td>
        <td>${fmtMs(dinic?.runtime_ms, 'dinic')}</td>
      </tr>
      <tr>
        <td>Augmentations</td>
        <td>${ff.augmentations ?? '—'}</td>
        <td>${dinic?.augmentations ?? '—'}</td>
      </tr>
      <tr>
        <td>BFS Phases</td>
        <td>${ff.bfs_phases ?? '—'}</td>
        <td>${dinic?.bfs_phases ?? '—'}</td>
      </tr>
    `;
  }

  _updateMinCut(edges) {
    const el = document.getElementById('mincut-list');
    if (!edges.length) { el.innerHTML = '<span class="empty">—</span>'; return; }
    el.innerHTML = edges.map(e => {
      const fromLabel = this._getNodeLabel(e.from);
      const toLabel   = this._getNodeLabel(e.to);
      return `<div class="mincut-item">
        <span class="mincut-label">${fromLabel} → ${toLabel}</span>
        <span class="mincut-cap">${e.capacity} kend/jam</span>
      </div>`;
    }).join('');
  }

  _updatePaths(paths) {
    const el = document.getElementById('paths-list');
    if (!paths.length) { el.innerHTML = '<span class="empty">—</span>'; return; }
    el.innerHTML = paths.map(p => `
      <div class="path-item">
        <span>${p.path.join(' → ')}</span>
        <span class="path-flow">+${p.flow}</span>
      </div>`).join('');
  }

  _highlightGraph(ffState, event) {
    const minCutEdgePairs = new Set(
      (ffState?.min_cut_edges || []).map(e => `${e.from}-${e.to}`)
    );
    const flowPathEdges = new Set();
    (ffState?.flow_paths || []).forEach(fp => {
      for (let i = 0; i < fp.path.length - 1; i++) {
        flowPathEdges.add(`${fp.path[i]}-${fp.path[i+1]}`);
      }
    });
    const eventEdge = event?.target_edge ? `${event.target_edge[0]}-${event.target_edge[1]}` : null;

    this.visEdges.forEach(e => {
      const key = `${e.from}-${e.to}`;
      let color, width, label;

      if (key === eventEdge) {
        color = { color: '#fb923c', highlight: '#fb923c' };
        width = 4;
        const newCap = event.new_capacity ?? e._cap;
        label = `${newCap} ⚡`;
      } else if (minCutEdgePairs.has(key)) {
        color = { color: '#f87171', highlight: '#f87171' };
        width = 4;
        label = `${e._cap} ✂️`;
      } else if (flowPathEdges.has(key)) {
        color = { color: '#34d399', highlight: '#34d399' };
        width = 3;
        label = `${e._cap}`;
      } else {
        color = { color: '#2e3250', highlight: '#4f8ef7' };
        width = 2;
        label = `${e._cap}`;
      }

      this.visEdges.update({ id: e.id, color, width, label });
    });
  }

  /* ─────────────────────────────────────────
   * HELPERS
   * ───────────────────────────────────────── */
  _getNodeLabel(id) {
    const nodes = this.data?.nodes || [];
    const n = nodes.find(n => n.id === id);
    return n ? this._shortLabel(n.label || `Node ${id}`) : `Node ${id}`;
  }

  _truncate(str, max) {
    return str && str.length > max ? str.slice(0, max) + '…' : (str || '');
  }
}

/* ─────────────────────────────────────────
 * TOPOLOGY EMBED
 * Data topologi hard-coded dari case_22_konser_jis.yaml
 * Dipakai sebagai fallback ketika JSON format A tidak menyertakan edges.
 * ───────────────────────────────────────── */
const GRAPH_TOPOLOGY = {
  nodes: [
    { id: 0,  label: "Gerbang Utama Arus Masuk (Source / Start)",              pos: [0.0,  0.0]  },
    { id: 1,  label: "Simpang Jl. Lodan - Ancol Barat",                        pos: [2.0,  4.0]  },
    { id: 2,  label: "Kantong Parkir Ancol Karnaval",                           pos: [4.0,  6.0]  },
    { id: 3,  label: "Jl. R.E. Martadinata Barat (Pasir Putih)",               pos: [5.0,  3.0]  },
    { id: 4,  label: "Simpang Taman BMW / Stasiun JIS",                         pos: [7.5,  3.5]  },
    { id: 5,  label: "Jl. R.E. Martadinata Tengah (Depan JIS)",                pos: [10.0, 4.5]  },
    { id: 6,  label: "Simpang Jl. R.E. Martadinata - Tol Pelabuhan",           pos: [15.5, 4.0]  },
    { id: 7,  label: "Akses Arah Tanjung Priok / Bahari",                       pos: [18.0, 6.0]  },
    { id: 8,  label: "Ujung Utara Jl. Danau Sunter Barat",                     pos: [7.0,  1.0]  },
    { id: 9,  label: "Halte Transjakarta / Jl. Danau Sunter Barat Tengah",     pos: [6.0, -2.0]  },
    { id: 10, label: "Simpang Jl. Danau Sunter Barat - Griya Utama",           pos: [5.0, -5.0]  },
    { id: 11, label: "Jl. Griya Utama Barat (Arah Kemayoran)",                 pos: [3.0, -6.0]  },
    { id: 12, label: "Simpang Jl. Griya Utama - Danau Sunter Utara",           pos: [9.0, -6.0]  },
    { id: 13, label: "Jl. Sunter Permai Raya Selatan",                         pos: [11.5,-5.5]  },
    { id: 14, label: "Simpang Jl. Sunter Permai Raya - Danau Cincin",          pos: [12.5,-2.0]  },
    { id: 15, label: "Simpang Jl. Sunter Permai Raya - R.E. Martadinata",      pos: [13.0, 2.5]  },
    { id: 16, label: "Exit Tol Pelabuhan / Papanggo",                          pos: [16.5, 1.0]  },
    { id: 17, label: "Simpang Jl. Warakas - Bahari",                           pos: [17.5, 3.5]  },
    { id: 18, label: "Akses Masuk West Ramp JIS",                              pos: [8.5,  2.2]  },
    { id: 19, label: "Akses Masuk East Ramp JIS",                              pos: [11.5, 0.5]  },
    { id: 20, label: "Akses Jl. Utama 1 (Sisi Selatan Stadion)",               pos: [9.0, -0.5]  },
    { id: 21, label: "Jakarta International Stadium - JIS (Sink / Goal)",       pos: [10.0, 1.5]  },
  ],
  edges: [
    // Super-Source → koridor masuk
    { from: 0,  to: 1,  capacity: 5000 },
    { from: 0,  to: 11, capacity: 5000 },
    { from: 0,  to: 16, capacity: 6000 },
    { from: 0,  to: 7,  capacity: 4500 },
    // Koridor Barat & Utara
    { from: 1,  to: 2,  capacity: 1800 },
    { from: 1,  to: 3,  capacity: 2400 },
    { from: 2,  to: 4,  capacity: 1200 },
    { from: 3,  to: 4,  capacity: 2200 },
    { from: 4,  to: 5,  capacity: 2000 },
    { from: 4,  to: 18, capacity: 1000 },
    // Koridor Timur (Tanjung Priok - Tol)
    { from: 7,  to: 17, capacity: 2000 },
    { from: 17, to: 6,  capacity: 1800 },
    { from: 16, to: 6,  capacity: 3000 },
    { from: 6,  to: 15, capacity: 2500 },
    { from: 15, to: 5,  capacity: 2000 },
    // Koridor Selatan (Griya Utama - Danau Sunter)
    { from: 11, to: 10, capacity: 2600 },
    { from: 11, to: 12, capacity: 2400 },
    { from: 10, to: 9,  capacity: 1800 },
    { from: 9,  to: 8,  capacity: 1600 },
    { from: 8,  to: 4,  capacity: 1500 },
    { from: 8,  to: 20, capacity: 1100 },
    { from: 12, to: 13, capacity: 2200 },
    { from: 13, to: 14, capacity: 2000 },
    { from: 14, to: 15, capacity: 1800 },
    { from: 14, to: 19, capacity: 1200 },
    // Pintu masuk JIS (sink)
    { from: 18, to: 21, capacity: 1000 },
    { from: 19, to: 21, capacity: 1200 },
    { from: 20, to: 21, capacity:  900 },
    { from: 5,  to: 21, capacity: 1500 },
  ],
};
