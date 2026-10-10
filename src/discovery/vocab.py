"""FROZEN vocabulary of the graph.json contract (see CLAUDE.md, "Graph vocabulary" section).

Direction rule (applied everywhere):
    `from` = the one that DEPENDS, `to` = its DEPENDENCY.
    Read the edge as a sentence: "<from> <type> <to>"
    ex. "morpho_market collateralized_by pt_susde", "susde redeemable_into usde".
    → A failure ALWAYS travels against the arrows (from `to` to `from`).

Any change to this file must be approved by the 3 members (reviewed PR):
other teams consume these strings as they are.
"""

# --- Node types ------------------------------------------------------------
NODE_TYPES = {
    "chain",                  # blockchain the contract runs on (ethereum)
    "asset",                  # any ERC-20 token: PT, SY, sUSDe, USDe, USDC... (details in meta.asset_kind)
    "issuer",                 # entity responsible for an asset / protocol (Ethena Labs, Circle, Pendle, Morpho, Chainlink)
    "oracle",                 # any contract that provides a price: assembler or feed (details in meta.oracle_kind)
    "liquidity_venue",        # AMM / pool where the asset can be sold (Pendle PT/SY pool)
    "lending_market",         # an isolated lending market (1 Morpho marketId = 1 node)
    "vault",                  # vault allocating funds into markets (MetaMorpho / Morpho Vault V2)
    "offchain_counterparty",  # off-chain entity holding assets or hedges (custodian, exchange)
}

# --- Edge types (from = dependent → to = dependency) ------------------------
EDGE_TYPES = {
    "deployed_in",        # "my funds are placed in"            position→market, vault→market, asset→pool, issuer→custodian
    "collateralized_by",  # "I am secured by"                    market→collateral  (= "is collateral of" read backwards)
    "lends",              # "I lend this asset"                  market→lent asset (EXTENSION, to be confirmed with the organisers)
    "priced_by",          # "my value is computed by"            market→oracle, oracle→feed, oracle→vault (internal rate)
    "redeemable_into",    # "I can be exchanged for"             PT→SY→sUSDe→USDe
    "issued_by",          # "I am issued / controlled by"        asset→issuer, oracle→issuer
    "settled_on",         # "I run on"                           contract→chain
}

SOURCES = {"onchain", "api", "curated"}

# How an oracle (or an oracle component) follows the price — the key information in a depeg.
PRICING_MODES = {
    "market",         # follows a market price (Chainlink, AMM TWAP)
    "fixed",          # fixed price / deterministic formula (linear discount, constant feed, missing feed = 1)
    "internal_rate",  # internal accounting rate of a contract (ERC-4626 convertToAssets)
    "hybrid",         # switches between several modes (meta-oracle with a fallback oracle)
    "unknown",        # the mode could not be proven → we do not guess
}

# Allowed triplets (from type, edge type, possible to types).
# "position" means the root (the JSON `position` object, which is not a node).
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

assert set(ALLOWED_EDGE_SHAPES) == EDGE_TYPES, "every edge type must have its allowed shape"
