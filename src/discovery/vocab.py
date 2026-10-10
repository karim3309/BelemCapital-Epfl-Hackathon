"""Vocabulaire FIGÉ du contrat graph.json (voir CLAUDE.md, section « Vocabulaire du graphe »).

Règle de direction (appliquée partout) :
    `from` = celui qui DÉPEND, `to` = sa DÉPENDANCE.
    On lit l'arête comme une phrase : "<from> <type> <to>"
    ex. "morpho_market collateralized_by pt_susde", "susde redeemable_into usde".
    → Une panne se propage TOUJOURS à contre-courant des flèches (de `to` vers `from`).

Toute modification de ce fichier doit être validée par les 3 membres (PR relue) :
les autres équipes consomment ces chaînes de caractères telles quelles.
"""

# --- Types de nœuds -------------------------------------------------------
NODE_TYPES = {
    "chain",                  # blockchain où le contrat s'exécute (ethereum)
    "asset",                  # tout token ERC-20 : PT, SY, sUSDe, USDe, USDC... (détail dans meta.asset_kind)
    "issuer",                 # entité responsable d'un actif / protocole (Ethena Labs, Circle, Pendle, Morpho, Chainlink)
    "oracle",                 # tout contrat qui fournit un prix : assembleur ou feed (détail dans meta.oracle_kind)
    "liquidity_venue",        # AMM / pool où l'on peut vendre l'actif (pool Pendle PT/SY)
    "lending_market",         # un marché de prêt isolé (1 marketId Morpho = 1 nœud)
    "vault",                  # coffre qui alloue des fonds dans des marchés (MetaMorpho / Morpho Vault V2)
    "offchain_counterparty",  # entité hors chaîne qui détient des actifs ou des hedges (custodian, exchange)
}

# --- Types d'arêtes (from = dépendant → to = dépendance) ---------------------
EDGE_TYPES = {
    "deployed_in",        # "mes fonds sont placés dans"        position→marché, vault→marché, asset→pool, émetteur→custodian
    "collateralized_by",  # "je suis garanti par"                marché→collatéral  (= « est collatéral de » lu à l'envers)
    "lends",              # "je prête cet actif"                 marché→actif prêté (EXTENSION, à confirmer avec les orgas)
    "priced_by",          # "ma valeur est calculée par"         marché→oracle, oracle→feed, oracle→vault (taux interne)
    "redeemable_into",    # "je peux être échangé contre"        PT→SY→sUSDe→USDe
    "issued_by",          # "je suis émis / contrôlé par"        actif→émetteur, oracle→émetteur
    "settled_on",         # "je m'exécute sur"                    contrat→chaîne
}

SOURCES = {"onchain", "api", "curated"}

# Comment un oracle (ou un composant d'oracle) suit le prix — l'info clé en cas de depeg.
PRICING_MODES = {
    "market",         # suit un prix de marché (Chainlink, TWAP d'AMM)
    "fixed",          # prix fixé / formule déterministe (décote linéaire, feed constant, feed absent = 1)
    "internal_rate",  # taux comptable interne d'un contrat (ERC-4626 convertToAssets)
    "hybrid",         # bascule entre plusieurs modes (méta-oracle avec oracle de secours)
    "unknown",        # on n'a pas pu prouver le mode → on ne devine pas
}

# Triplets autorisés (type du from, type d'arête, types possibles du to).
# "position" désigne la racine (objet `position` du JSON, qui n'est pas un nœud).
ALLOWED_EDGE_SHAPES: dict[str, tuple[set[str], set[str]]] = {
    "deployed_in": ({"position", "vault", "issuer", "asset"},
                    {"lending_market", "liquidity_venue", "offchain_counterparty", "vault"}),
    "collateralized_by": ({"lending_market"}, {"asset"}),
    "lends": ({"lending_market"}, {"asset"}),
    "priced_by": ({"lending_market", "oracle"}, {"oracle", "liquidity_venue", "asset"}),
    "redeemable_into": ({"asset"}, {"asset"}),
    "issued_by": ({"asset", "oracle", "vault", "lending_market", "liquidity_venue"}, {"issuer"}),
    "settled_on": ({"asset", "oracle", "vault", "lending_market", "liquidity_venue"}, {"chain"}),
}

assert set(ALLOWED_EDGE_SHAPES) == EDGE_TYPES, "chaque type d'arête doit avoir sa forme autorisée"
