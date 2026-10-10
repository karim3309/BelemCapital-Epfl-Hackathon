# StackTrace · dependencies and risk of a DeFi position

> **Belem DeFi Risk** hackathon (EPFL). A DeFi position goes in, an **actionable risk sheet** comes out:
> 1. **Discovery**: the dependency graph, every edge **proven** (on-chain, API or curated official source);
> 2. **Impact**: an engine that propagates a shock through this graph up to the position, in $;
> 3. **Decision**: STAY / PARTIAL x% / EXIT, with the brief's probability threshold **p\***;
> 4. **Front** (`front/`): a slide deck that shows all of this, pocket by pocket.
>
> No address, no link, no parameter is guessed.

## The risk sheet in 30 seconds (block #26162087)
| | |
|---|---|
| Alert (demo scenario from the framing note) | **Lasting USDe depeg −30%**: the oracle switches after 16 h, the position is liquidated, **−$53,133** (all the capital) and **−$77,723 for the lenders** |
| Certain exit cost | **$854**, measured on-chain (sale simulated on the real Pendle pool) |
| Threshold | **p\* = 1.6%** over 7 days, i.e. the risk of an event that happens **≈ once every 14 months** → "do I believe there is more than a 1.6% chance this happens this week?" |
| No alert (Monte Carlo, 200,000 weeks) | expected loss ≈ $131/7 d, VaR 95% = $0, ES 99% ≈ $13k → **STAY** |
| The trap of this position | **duration**: USDe at $0.93 for 6 h = $0 loss; for 24 h = liquidation (−$37k) |
| The hidden risk | Pendle exploit: the fixed oracle sees nothing → **$152k of unrecoverable debt for the lenders** |
| Real replay | 10/10/2025: USDe at $0.65 on Binance. Our oracle holds; an oracle on the Binance price would have liquidated us |

The details are in [docs/PARTS_2_3.md](docs/PARTS_2_3.md) (brief → what we did → where) and the format in
[docs/RISK_CONTRACT.md](docs/RISK_CONTRACT.md).

## Result: position A

A **PT-sUSDE-26NOV2026** (Pendle) is deposited as collateral on a **Morpho Blue** market, and **USDC** is borrowed against it.
The figures below are read at block **#26162087** (2026-10-10 12:39 UTC). The demo replays **without network**.

| | |
|---|---|
| Graph | **28 nodes, 45 edges**: 29 proven on-chain, 2 via API, 14 curated (URL + date) |
| Position | 413,030 PT as collateral, debt 357,217 USDC (interest included), LTV 87.2% / LLTV 91.5% |
| Health | health factor **1.050**: liquidatable if the oracle price drops by **4.75%** |
| Oracle | Steakhouse **meta-oracle**. The primary is a linear discount alone (**fixed**). The backup adds Chainlink USDe/USD (**market**). Switches if the gap exceeds 0.75% for 16 h |
| Exit liquidity | Pendle pool of $3.82M for $7.76M lent on the market |

```
POSITION (value_usd=409,819.73)
└─ deployed_in ⛓ → morpho_market_5613b170 [lending_market] Morpho Blue PT-sUSDE-26NOV2026 / USDC (LLTV 91.5%)
   ├─ collateralized_by ⛓ → pt_susde_26nov2026 [asset]
   │  ├─ deployed_in ⛓ → pendle_plp_susde_26nov2026 [liquidity_venue]   (AMM pool, TVL $3.8M)
   │  ├─ issued_by 📄 → pendle
   │  └─ redeemable_into ⛓ → sy_susde → redeemable_into ⛓ → susde → redeemable_into ⛓ → usde
   │                                                    └─ issued_by 📄 → ethena_labs ─ deployed_in 📄 → copper, ceffu,
   │                                                                                     fireblocks, binance, bybit, okx…
   ├─ lends ⛓ → usdc ─ issued_by 📄 → circle
   └─ priced_by ⛓ → oracle_meta_f8b29e (hybrid, effective: fixed)
      ├─ priced_by ⛓ → oracle_morpho_v2_8fca98 (fixed)  ─ priced_by ⛓ → PT linear discount feed (6%/yr)
      └─ priced_by ⛓ → oracle_morpho_v2_e2f4cf (market) ─ priced_by ⛓ → PT linear discount feed
                                                         ├─ priced_by ⛓ → feed_usde_usd ─ issued_by ⛓ (ENS) → chainlink
                                                         └─ priced_by ⛓ → constant "Dummy" feed (USDC = 1)
⛓ onchain · 🌐 api · 📄 curated          (+ every contract --settled_on--> ethereum)
```

For the full explanation, layer by layer, and the depeg scenarios with figures: [docs/POSITION_A.md](docs/POSITION_A.md).

## Position A risk engine (offline)
```bash
PYTHONPATH=src python -m risk.run
```
`risk.run` reads `output/graph.json` and `output/risk_inputs.json` (offline) and writes `output/risk_report.json` and
`output/risk_grid.json`. **Do not delete `output/`**: these are the inputs of the engine and of the tests.

To **refresh the whole snapshot** (discovery + engine reads, at the same block), online: `PYTHONPATH=src python -m risk.refresh`.

## Backend v2: any real holder, online → STAY / EXIT

v2 starts from **the address of a real holder** (e.g. the Belem RWA EURCV vault from the RockawayX Dune dashboard). It finds
all its pockets, builds the proven graph of each one, prices the impact of incidents, measures the exit cost and
returns a **STAY / EXIT** verdict with the threshold **p\***. An HTTP API is provided for the front.
→ [docs/BACKEND_V2.md](docs/BACKEND_V2.md) (pipeline, model, limits) · [docs/API.md](docs/API.md) (API contract + real examples)

## Slide-deck front: backend v2 on screen (`front/`)

A 7-slide deck that follows Léa's questions at 3 a.m.: the portfolio, **the STAY / EXIT verdict** for
each pocket (very large), which path I am exposed through (proven graph, evidence of each edge on click), how much I
can lose, what exiting costs, and incident mode ("do you believe in more than p\*?"), then the hidden concentration
of the portfolio. ← → switches pocket, ↑ ↓ switches question. The front **computes no risk**: it reads the API.

```bash
cd front && npm install && npm run dev        # http://localhost:5173
```

- **Without backend**: it starts on the real responses recorded in `docs/api_examples/` (mainnet, block #26162868).
  No network required.
- **Live**: start the API (`PYTHONPATH=src python -m stacktrace.api`, with `ETH_RPC_URL` in `.env`); the front
  detects it and offers to switch to live. Or `http://localhost:5173/?source=live`.

Details, architecture and replay server: [front/README.md](front/README.md).

## Quick start

You need Python **3.11**. With Anaconda, for example: `conda create -p .venv311 python=3.11 pip`, then use `.venv311/python`.

```bash
pip install -r requirements.txt
```

```bash
python -m pytest
```

The tests (discovery + risk engine + backend v2 + API) run in ~10 s, without network, and include position A replayed from the cache.

**Offline demo** (no network call, everything comes from `data/cache/`). In PowerShell:

```powershell
$env:PYTHONPATH="src"; python -m discovery.build_graph --offline
```

In bash:

```bash
PYTHONPATH=src python -m discovery.build_graph --offline
```

Explore the graph:

```bash
PYTHONPATH=src python -m discovery.inspect_graph
```

```bash
PYTHONPATH=src python -m discovery.inspect_graph --impact usde
```

```bash
PYTHONPATH=src python -m discovery.validate output/graph.json
```

`--impact` answers "who is hit if USDe breaks, and through which path?". `--evidence` shows the evidence of each edge.
With `pip install -e .`, `PYTHONPATH=src` is no longer needed.
On Windows, if you clone into a very deep folder, first run `git config --global core.longpaths true`.

### Refreshing the data (online)
1. `cp .env.example .env`, then set your `ETH_RPC_URL` (Ethereum mainnet).
2. In `config.yaml`, set `snapshot_block: latest`, then run `python -m discovery.build_graph`.
3. Copy the displayed block number into `config.yaml` to pin it. Rerun `--offline`, then commit `data/cache/` and `output/graph.json`.

> A public non-archive RPC only answers for the last ~128 blocks. To pin an old block, you need an **archive** RPC.

## Architecture

```
config.yaml            discovery inputs (marketId, user, entry contracts), each with its source
curated.yaml           the verifiable off-chain layer (issuers, custodians, exchanges), each line with URL + date
src/discovery/
  vocab.py             FROZEN vocabulary (node/edge types, sources, pricing modes, allowed shapes)
  config.py            loading + safeguards (rejects placeholder addresses)
  cache.py  rpc.py     disk cache plugged in AT THE web3 PROVIDER LEVEL → no call can bypass it
  http.py              APIs (Morpho GraphQL, Pendle) through the same cache
  ctx.py               the only door to the chain: call / try_call (probes) / textual evidence
  graph.py  ids.py     graph model, deterministic ids, export to the JSON contract
  validate.py          strict contract validator (structure + rigour of evidence + connectivity)
  valuation.py         price_usd / tvl_usd from on-chain-proven prices only
  build_graph.py       orchestrator: Morpho root → breadth-first exploration → final passes
  inspect_graph.py     tree + impact analysis (networkx)
  adapters/
    morpho.py          market (params hash recomputed), position, accrued interest, health
    morpho_api.py      vaults that lend to the market (Morpho API, re-read on-chain)
    oracles.py         meta-oracle, MorphoChainlinkOracleV2 (price recomputed), linear discount, Chainlink, constant feed
    pendle.py          PT → SY → yieldToken; pool located via API then PROVEN on-chain
    erc20.py erc4626.py  classification by probing, share vaults
    ens.py             ENS resolution (proves that a feed is an official Chainlink feed)
    contracts.py       proxy detection (EIP-1167, EIP-1967, ZeppelinOS)
    chain.py           settled_on (eth_chainId + eth_getCode)
    curated.py         strict loader for curated.yaml
src/risk/              RISK ENGINE (parts 2 and 3) — reads only graph.json + risk_inputs.json
  collect.py refresh.py   on-chain reads of the engine (Pendle sale quotes, Chainlink history, gas) at the same block
  params.py               STRICT loader for risk/params.yaml (sourced / on-chain / hypothesis status mandatory)
  calibrate.py            Chainlink USDe/USD history → frequency and size of depegs
  propagate.py            one transmission rule per edge type (dominoes)
  oracle_sim.py           what the oracle shows during the shock (meta-oracle: threshold + 16 h timer)
  position.py             health, liquidation (sourced Morpho bonus), borrower / lender losses
  exit_cost.py decide.py  measured exit cost, threshold p*, partial exit, verdict
  montecarlo.py           200,000 simulated weeks → expected loss, VaR, costliest paths
  replay.py               real incidents replayed (10/10/2025, 21/02/2025)
  run.py                  report + grid + validator
risk/                  params.yaml, scenarios.yaml, replays.yaml (every figure has a status)
front/                 slide-deck front (React), reads API v2 or its recorded responses
data/cache/            pinned RPC/API responses (committed: the demo survives a network outage)
output/                graph.json (discovery), risk_inputs.json, risk_report.json, risk_grid.json
```

## Anti-hallucination guarantees
- **Pinned block**: all reads are made at the same block, recorded in each piece of evidence (`#26162087`).
- **Recomputations**: the market ID is recomputed (`keccak256(MarketParams)`). The price of each `MorphoChainlinkOracleV2` is recomputed from its building blocks, as are the linear discount formula and the accrued interest (0.0001% gap with the Morpho API).
- **On-chain provenance**:
  - the sub-oracles are confirmed by the official factory (`isMorphoChainlinkOracleV2`);
  - the Pendle pool by its factory (`isValidMarket`);
  - the USDe/USD feed by ENS (`usde-usd.data.eth`).
- **Unknown = flagged**: an unrecognised contract becomes `meta.unresolved = true`, never guessed.
- **Curated = sourced**: `curated.yaml` rejects any line without an https URL and a date.
- **Validator**: the JSON contract is checked at every build (structure, vocabulary, edge shapes, evidence, connectivity).

## Documentation
| File | For whom / what |
|---|---|
| [docs/PARTS_2_3.md](docs/PARTS_2_3.md) | parts 2 and 3: brief → what we did → where it is |
| [docs/RISK_CONTRACT.md](docs/RISK_CONTRACT.md) | format of `risk_report.json` / `risk_grid.json` |
| [docs/DEMO.md](docs/DEMO.md) | **5-minute demo script** (PowerShell and bash) |
| [front/README.md](front/README.md) | the slide-deck front (launch, data sources, architecture) |
| [docs/BEGINNER_GUIDE.md](docs/BEGINNER_GUIDE.md) | **start here**: everything explained from scratch |
| [CLAUDE.md](CLAUDE.md) | project rules + **frozen vocabulary** + conventions |
| [docs/CONTRACT.md](docs/CONTRACT.md) | **for the other teams**: how to read `graph.json` |
| [docs/POSITION_A.md](docs/POSITION_A.md) | what we discovered about position A, explained simply |
| [docs/VERIFY.md](docs/VERIFY.md) | **checklist for the team to tick** (addresses, functions, endpoints) |
| [docs/NEXT_STEPS.md](docs/NEXT_STEPS.md) | what comes next, the split between the 3 of us, and **ready-to-run prompts** |
| [docs/AUDIT.md](docs/AUDIT.md) | audit log and known limits |
| [docs/AUDIT_BRIEF.md](docs/AUDIT_BRIEF.md) | **audit against the Belem brief and the grading scheme**: estimated scores, gaps, prioritised action plan |
