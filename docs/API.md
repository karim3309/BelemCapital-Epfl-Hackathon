# StackTrace v2 API: contract for the front

The API is **read-only**. It works on **real, live data** (Ethereum mainnet) and returns JSON.
**Real responses** are recorded in [`docs/api_examples/`](api_examples/): the front can be built on them right away, without running the backend.

## Running the API

```powershell
$env:PYTHONPATH="src"; .venv313\Scripts\python -m stacktrace.api
```

The API answers on `http://127.0.0.1:8000`. The interactive documentation is at `http://127.0.0.1:8000/docs`.
It needs `ETH_RPC_URL` in `.env`. CORS is open: the front can call it from the browser.

## What to know before calling

- **Every response carries the `block`** at which it was computed. All responses for the same block are consistent with each other.
- **The block is renewed every 2 minutes.** In the meantime, results are cached, and a new call is instant.
- **The first analysis is slow**, because it makes hundreds of RPC calls. Plan for a "loading" state:

  | Route | 1st call | Following calls (same block) |
  |---|---|---|
  | `/pockets` | ~5 s | instant |
  | `/risk` of a pocket | ~10 to 30 s | instant |
  | `/incident` | instant if `/risk` has already been called | instant |
  | `/book` (11 pockets) | ~1 min 30 s | instant |

- **Requests are processed one at a time** on the server side. There is no point in launching ten in parallel.
- **`{holder}`**: a holder address (`0x…`), **or** `vault:0x…` (one whole vault, curator view), **or**
  `book:<key>` (every vault of a curator book of `config.yaml`, e.g. `book:rockawayx`). See `GET /books`.
- **`{pocket}`**: the pocket's `id` (`morpho_vault_v2:0xD6d4…`) **or** its `index` number (1, 2, …) in the `/pockets` list.

## Routes

### `GET /health`
Diagnostics: current block, block age, status of the Morpho and Pendle APIs. `status` is `ok` or `degraded`. → [example](api_examples/health.json)

### `GET /books`
The curator books listed in `config.yaml` (`curator_books`): `holder` to use (`book:<key>`), label, number of vaults,
source. Needs no RPC.

### `GET /holders/{holder}/pockets?min_usd=1`
The holder's pockets. They are located via the Morpho API, then **every amount is proven on-chain**. → [example](api_examples/pockets.json)

Useful fields of `holdings[]`:
- `index`, `id`, `kind`, `label`;
- `kind` is `morpho_vault_v2`, `morpho_market_borrow` or `morpho_market_supply`;
- `amount`, `asset_symbol`, `value_usd`, `share_of_book` (share of the portfolio);
- `evidence[]`: the on-chain evidence, to show in a tooltip;
- `api_gap`: difference between the chain and the API (`< 1%` expected).

### `GET /holders/{holder}/pockets/{pocket}/graph`
The pocket's proven dependency graph, in the **usual `graph.json` format** (see [CONTRACT.md](CONTRACT.md)): `graph.position`, `graph.nodes[]`, `graph.edges[]`.
Every edge has its `source` (`onchain`, `api` or `curated`) and its evidence (`evidence`). → [example](api_examples/graph_vault.json)

Fields to highlight:
- `vault` node: `meta.allocations[]` (share of each market) and `meta.exit_liquidity` (what can be withdrawn now);
- `oracle` node: `meta.pricing_mode`, which is `market`, `fixed`, `internal_rate`, `hybrid` or `unknown`. **This is the #1 risk information**: an oracle that is not `market` does not follow the market;
- `issuer` node with `meta.role = vault_curator`: the curator (RockawayX, Bitwise…).

### `GET /holders/{holder}/pockets/{pocket}/risk?horizon=7`
The full analysis of a pocket. → examples: [vault](api_examples/risk_vault.json), [borrow](api_examples/risk_borrow.json)

| Field | Content |
|---|---|
| `decision.verdict` | **`STAY` or `EXIT`** |
| `decision.exit_fraction` | share of the pocket to exit (0 → 1) |
| `decision.sentence` | the sentence to show the manager |
| `monte_carlo` | `expected_loss_usd` (expected loss over the horizon), `var95_usd`, `var99_usd`, `var999_usd`, `p_any_loss` |
| `exit` | `f_max_now` (share that can be exited **now**), `cost_full_usd`, `cost_full_pct`, and the breakdown (DEX quotes, penalty, gas…) |
| `markets[]` | for each market: `collateral_pricing`, `utilization`, `liquidity`, number of borrowers |
| `incidents[]` | **sorted by expected loss**: `id`, `title`, `loss_if_incident_usd`, `p_horizon`, `p_star` (exit threshold), `rule` (the calculation rule in plain words), `contagion_path` (text) |

### `POST /holders/{holder}/pockets/{pocket}/incident`
The **incident mode**: "what should I do if this incident happens?". → [example](api_examples/incident.json)

```json
{ "incident": "rwa_credit_event:mgloeuro", "severity": 0.3, "p": 0.2, "horizon": 7 }
```

- `incident`: an `incidents[].id` from `/risk`. The beginning of an id is enough.
- `severity` (0 → 1): size of the shock. Optional; by default, the middle of the range.
- `p` (0 → 1): the probability estimated **by the manager**. Optional.

The response contains `incident_mode`:
- `verdict`, `exit_fraction`, `loss_if_incident_usd` / `_pct` and **`p_star`** ("exit if you believe in more than p\*");
- `sentence`: the sentence to show;
- `contagion_edges[]`: the graph's edges between the position and the hit node, **to highlight on the graph**.

It also contains `baseline_decision`, the decision without the incident.

### `GET /holders/{holder}/book?horizon=7`
The whole portfolio. → [example](api_examples/book.json)

- `pockets[]`: one row per pocket, with verdict, expected loss, exit cost, exitable share, sentence and main risk;
- `shared_dependencies[]`: **the dependencies shared by several pockets**, i.e. the hidden concentration (for example Chainlink ETH/USD in 4 pockets);
- `skipped[]`: the pockets not supported, with the reason.

## Recording for the offline demo
`PYTHONPATH=src python -m stacktrace.record <holder>` calls every route above for one holder (pockets, book, risk and
graph of every pocket, one incident example at p = 20%) and writes the answers into
`docs/api_examples/recordings/<holder>/`. Commit the folder: the front (recorded mode) and the replay server
(`npm run replay-api`) pick it up by themselves.

## Errors

| Code | When | Content of `detail` |
|---|---|---|
| 404 | unknown pocket | `{error, pockets: [{index, id, label}]}`. [example](api_examples/error_404_pocket.json) |
| 404 | unknown incident | `{error, incidents: [ids…]}` |
| 422 | invalid parameter (e.g. `severity` > 1), or pocket type not supported yet | FastAPI message or text |
| 400 | invalid address | text |
| 503 | RPC unavailable (empty `.env`, node down) | text |
