"""Le front ne fait qu'afficher : ses données doivent être EXACTEMENT celles du moteur, et complètes."""
import json
import re
from pathlib import Path

from discovery.config import REPO_ROOT

WEB = REPO_ROOT / "web"


def _load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def test_web_data_is_a_copy_of_the_engine_output():
    for f in ("graph.json", "risk_report.json", "risk_grid.json"):
        assert _load(WEB / "data" / f) == _load(REPO_ROOT / "output" / f), \
            f"web/data/{f} est en retard : lancez python -m risk.export_web"


def test_every_node_has_a_layer_and_a_label():
    view, graph = _load(WEB / "data" / "view.json"), _load(REPO_ROOT / "output" / "graph.json")
    ids = {n["id"] for n in graph["nodes"]} | {graph["position"]["id"]}
    assert ids <= set(view["layers"])
    assert {n["id"] for n in graph["nodes"]} <= set(view["display"])
    assert all(0 <= layer < len(view["layer_titles"]) for layer in view["layers"].values())


def test_front_makes_no_network_call_and_loads_no_remote_asset():
    """Démo hors ligne : aucune URL http(s) chargée par le HTML/CSS/JS (les liens <a> vers les preuves sont permis)."""
    for path in [WEB / "index.html", *WEB.glob("css/*.css"), *WEB.glob("js/*.js")]:
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"<script[^>]+src=[\"']https?://", text), path
        assert not re.search(r"<link[^>]+href=[\"']https?://", text), path
        assert not re.search(r"@import|url\([\"']?https?://", text), path
        assert not re.search(r"fetch\([\"'`]https?://", text), path
