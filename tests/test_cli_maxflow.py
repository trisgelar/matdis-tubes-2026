import json
from pathlib import Path

from config.settings import CASES_DIR
from core.simulation_observers import TraceExportObserver
from scripts.run_maxflow import main as run_maxflow_main
from scripts.run_simulation import main as run_simulation_main


JIS_SCENARIO = CASES_DIR / "case_22_konser_jis.yaml"


def test_run_maxflow_cli_exports_expected_flows(tmp_path: Path, capsys):
    """CLI maxflow harus melaporkan 4600 -> 3100 -> 2800 dan menulis JSON."""
    json_path = tmp_path / "maxflow_case22.json"

    run_maxflow_main(
        [
            str(JIS_SCENARIO),
            "--repeat",
            "2",
            "--json",
            str(json_path),
        ]
    )

    output = capsys.readouterr().out
    assert "ford_fulkerson" in output
    assert "dinic" in output
    assert "[OK] Ford-Fulkerson dan Dinic sepakat" in output

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    algorithms = {result["algorithm"] for result in payload["results"]}
    assert algorithms == {"ford_fulkerson", "dinic"}

    for result in payload["results"]:
        assert result["initial"]["max_flow"] == 4600.0
        assert result["events"][0]["max_flow"] == 3100.0
        assert result["events"][1]["max_flow"] == 2800.0
        assert result["final"]["max_flow"] == 2800.0
        assert result["events"][0]["target_edge"] == [5, 21]
        assert result["events"][1]["target_edge"] == [9, 8]


def test_run_simulation_uses_algorithm_from_yaml(capsys, monkeypatch):
    """Skenario JIS harus otomatis memakai maxflow tanpa flag --algorithm."""
    monkeypatch.setattr(TraceExportObserver, "on_complete", lambda self, result: None)

    run_simulation_main([str(JIS_SCENARIO), "--no-viz"])

    output = capsys.readouterr().out
    assert "Algorithm: Dinic" in output
    assert "Max Flow Awal: 4600.0" in output
    assert "Max Flow Baru: 3100.0" in output
    assert "Max Flow Baru: 2800.0" in output
