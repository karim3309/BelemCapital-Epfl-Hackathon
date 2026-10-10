"""Prépare les données du front « Rayon X » dans web/data/ (le front ne calcule AUCUN risque).

    PYTHONPATH=src python -m risk.export_web

Copie graph.json, risk_report.json, risk_grid.json, et fabrique view.json :
  - les COUCHES (« vertèbres ») : la profondeur de la pile, lue de haut en bas
      Position → Marché → Oracle → Experts → Feeds → PT / pool / USDC → SY → sUSDe → USDe → Émetteurs
      → Hors chaîne → Ethereum ;
  - les textes vulgarisés de chaque type de nœud (repris du glossaire de docs/GUIDE_DEBUTANT.md) ;
  - les chemins utiles au front (ex. chemin de contagion de l'USDe pour le curseur de scénario).
"""
from __future__ import annotations

import json
import shutil
import sys

from discovery.config import REPO_ROOT
from discovery.console import utf8_console

from .graphview import GraphView
from .propagate import RULES, contagion_paths

WEB_DATA = REPO_ROOT / "web" / "data"

LAYER_TITLES = [
    "Position", "Marché de prêt", "Oracle du marché", "Experts (sous-oracles)", "Feeds de prix",
    "Gage, dette et bureau de change", "Emballage Pendle (SY)", "Tirelire (sUSDe)", "Dollar synthétique (USDe)",
    "Émetteurs", "Hors chaîne : coffres et exchanges", "Chaîne de règlement",
]

TYPE_TEXT = {
    "lending_market": ("Marché de prêt", "Un guichet de prêt sur gage (Morpho) avec 5 règles figées : ce qu'on prête, "
                       "ce qu'on met en gage, qui donne le prix, le taux, et la limite (LLTV). Au-delà de la limite, "
                       "n'importe qui peut liquider le gage."),
    "vault": ("Vault (coffre de placement)", "Un coffre qui prête l'argent de ses déposants à des marchés. Ici, il "
              "fournit les USDC qu'on emprunte : si le gage ne couvre plus la dette, c'est lui qui encaisse le trou."),
    "oracle": ("Oracle", "L'expert qui dit à la blockchain combien vaut le gage. Morpho le croit aveuglément : si "
               "l'oracle baisse, on peut être liquidé même si rien d'autre n'a changé."),
    "asset": ("Actif (jeton)", "Une ligne dans le grand cahier public : « telle adresse possède tant de ce jeton ». "
              "Sa valeur peut dépendre d'autres jetons (on peut l'échanger contre eux)."),
    "liquidity_venue": ("Bureau de change (pool AMM)", "Une réserve d'échange automatique : on y vend des PT contre "
                        "des SY. Plus on vend gros, plus le taux se dégrade (glissement)."),
    "issuer": ("Émetteur", "L'entreprise ou le protocole qui crée le jeton et en garantit la valeur. S'il fait "
               "défaut, ses jetons perdent de la valeur."),
    "offchain_counterparty": ("Contrepartie hors chaîne", "Une entreprise du monde réel (coffre-fort, exchange) : "
                              "rien de ce qu'elle fait n'est écrit dans le cahier public. On le sait par ce qui est "
                              "publié (lien + date)."),
    "chain": ("Chaîne de règlement", "Le grand cahier public lui-même (Ethereum). S'il s'arrête, plus personne ne "
              "peut liquider ni sortir."),
}

KIND_TEXT = {
    "morpho_meta_oracle_deviation_timelock": "Méta-oracle : un arbitre qui écoute l'expert « catalogue » (prix fixé) et "
        "passe à l'expert « marché » si les deux sont en désaccord de plus de 0,75 % pendant 16 h.",
    "morpho_chainlink_oracle_v2": "Expert assembleur : multiplie et divise des feeds de prix. Un slot vide vaut 1 "
        "(prix supposé fixe).",
    "pendle_linear_discount_feed": "Feed « catalogue » : une formule (1 − décote × temps restant) qui ne regarde "
        "JAMAIS le marché.",
    "chainlink_aggregator_proxy": "Feed Chainlink : le prix de marché, agrégé par Chainlink, mis à jour quand le "
        "prix bouge.",
    "constant_feed": "Feed constant : renvoie toujours la même valeur (ici, « 1 USDC = 1 $ »).",
    "pendle_pt": "PT (Principal Token) : un bon qui vaudra 1 USDe à l'échéance — comme un bon d'achat acheté un peu "
        "moins cher aujourd'hui.",
    "pendle_sy": "SY : l'adaptateur de prise de Pendle, qui emballe le sUSDe.",
    "erc4626_vault": "Tirelire à parts (ERC-4626) : chaque part vaut de plus en plus de l'actif déposé.",
    "erc20": "Jeton standard (ERC-20).",
}

SOURCE_TEXT = {
    "onchain": "Prouvé on-chain : lu directement dans le cahier public, au bloc indiqué (relevé officiel).",
    "api": "Renseignement d'API officielle (site du protocole), avec la date de lecture.",
    "curated": "Source curée : page officielle relevée à la main, avec lien et date (coupure de presse datée).",
}


def compute_layers(gv: GraphView) -> dict[str, int]:
    layer: dict[str, int] = {gv.position_id: 0}
    market = gv.market_id()
    layer[market] = 1
    for v in gv.sources(market, "deployed_in"):
        if v in gv.nodes and gv.node(v)["type"] == "vault":
            layer[v] = 1
    # oracles : profondeur depuis l'oracle du marché
    frontier, depth = [gv.market_oracle_id()], 2
    while frontier:
        nxt = []
        for o in frontier:
            if o in layer:
                continue
            layer[o] = min(depth, 4)
            nxt += [t for t in gv.targets(o, "priced_by") if gv.node(t)["type"] == "oracle"]
        frontier, depth = nxt, depth + 1
    # actifs : profondeur de rachat depuis le collatéral
    coll = gv.collateral_id()
    frontier, depth = [coll], 5
    while frontier:
        nxt = []
        for a in frontier:
            if a in layer:
                continue
            layer[a] = min(depth, 8)
            nxt += gv.targets(a, "redeemable_into")
        frontier, depth = nxt, depth + 1
    layer.setdefault(gv.loan_id(), 5)
    for v in gv.targets(coll, "deployed_in"):
        layer.setdefault(v, 5)
    for n in gv.raw["nodes"]:
        t = n["type"]
        if n["id"] in layer:
            continue
        if t == "issuer":
            layer[n["id"]] = 9
        elif t == "offchain_counterparty":
            layer[n["id"]] = 10
        elif t == "chain":
            layer[n["id"]] = 11
        elif t == "oracle":
            layer[n["id"]] = 4
        else:
            layer[n["id"]] = 8
    return layer


def display_labels(gv: GraphView) -> dict[str, str]:
    """Libellés courts et parlants pour un débutant (le nom technique reste dans la fiche du nœud)."""
    out: dict[str, str] = {}
    roles = {}
    for n in gv.of_type("oracle"):
        if n["meta"].get("oracle_kind") == "morpho_meta_oracle_deviation_timelock":
            for role, key in (("primaire", "primary_oracle"), ("secours", "backup_oracle")):
                tgt = gv.by_address(n["meta"].get(key))
                if tgt:
                    roles[tgt["id"]] = role
    for n in gv.raw["nodes"]:
        m, t, nid = n["meta"], n["type"], n["id"]
        kind = m.get("oracle_kind")
        if t == "lending_market":
            out[nid] = "Marché Morpho"
        elif t == "liquidity_venue":
            out[nid] = "Pool Pendle PT/SY"
        elif t == "chain":
            out[nid] = n["label"]
        elif kind == "morpho_meta_oracle_deviation_timelock":
            out[nid] = "Méta-oracle"
        elif kind in ("morpho_chainlink_oracle_v2", "morpho_chainlink_oracle_v1"):
            mode = {"fixed": "fixe", "market": "marché"}.get(m.get("pricing_mode"), m.get("pricing_mode"))
            out[nid] = f"{roles.get(nid, 'expert').capitalize()} ({mode})"
        elif kind == "pendle_linear_discount_feed":
            out[nid] = "Décote PT (formule)"
        elif kind == "chainlink_aggregator_proxy":
            out[nid] = f"Chainlink {m.get('description', '')}"
        elif kind == "constant_feed":
            out[nid] = "Feed constant (= 1)"
        elif t == "asset":
            out[nid] = m.get("symbol") or n["label"]
        else:
            out[nid] = n["label"]
    return out


def build_view(gv: GraphView, report: dict) -> dict:
    layers = compute_layers(gv)
    usde = report["position"].get("collateral")
    usde_paths = []
    grid_node = None
    grid_file = REPO_ROOT / "output" / "risk_grid.json"
    if grid_file.exists():
        grid_node = json.loads(grid_file.read_text(encoding="utf-8")).get("usde_node")
    if grid_node:
        usde_paths = contagion_paths(gv, grid_node, max_paths=3)
        # le curseur USDe agit aussi via l'oracle : chemin position → oracle → feed qui mesure l'USDe
        for f in [n["id"] for n in gv.of_type("oracle") if n["meta"].get("oracle_kind") == "chainlink_aggregator_proxy"]:
            usde_paths += contagion_paths(gv, f, max_paths=1)
    return {
        "layers": layers, "layer_titles": LAYER_TITLES, "display": display_labels(gv), "type_text": TYPE_TEXT, "kind_text": KIND_TEXT,
        "source_text": SOURCE_TEXT, "rules": RULES, "usde_node": grid_node, "usde_paths": usde_paths,
        "collateral": usde, "etherscan": "https://etherscan.io/address/",
    }


def main() -> int:
    utf8_console()
    WEB_DATA.mkdir(parents=True, exist_ok=True)
    out = REPO_ROOT / "output"
    missing = [f for f in ("graph.json", "risk_report.json", "risk_grid.json") if not (out / f).exists()]
    if missing:
        print(f"✗ fichiers manquants dans output/ : {missing} — lancez d'abord `python -m risk.run`")
        return 1
    for f in ("graph.json", "risk_report.json", "risk_grid.json"):
        shutil.copyfile(out / f, WEB_DATA / f)
    gv = GraphView.load(out / "graph.json")
    report = json.loads((out / "risk_report.json").read_text(encoding="utf-8"))
    view = build_view(gv, report)
    (WEB_DATA / "view.json").write_text(json.dumps(view, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"✓ données du front écrites dans {WEB_DATA.relative_to(REPO_ROOT)} (graph, risk_report, risk_grid, view)")
    print("  Lancer : python -m http.server 8000 -d web   →   http://localhost:8000")
    return 0


if __name__ == "__main__":
    sys.exit(main())
