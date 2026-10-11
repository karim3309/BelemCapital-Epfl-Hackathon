# StackTrace

[![CI](https://github.com/karim3309/BelemCapital-Epfl-Hackathon/actions/workflows/ci.yml/badge.svg)](https://github.com/karim3309/BelemCapital-Epfl-Hackathon/actions/workflows/ci.yml)

**Belem Capital · DeFi Risk Dependency Challenge (EPFL hackathon).**
StackTrace takes a real on-chain position, rebuilds the stack of things it depends on, prices what each failure
would cost, and answers the portfolio manager's question: **stay, partially exit, or exit, and why.**

- **Discovery**: a dependency graph where every edge is *proven*: an on-chain call at a pinned block, an API
  response re-proven on-chain, or a curated official source with URL and date. Nothing is drawn by hand.
- **Impact**: a shock is propagated edge by edge up to the position, in dollars, for the borrower **and** the lenders.
- **Decision**: exit if the probability of the incident exceeds **p\* = exit cost / loss**. The exit cost is measured
  on the real liquidity (on-chain quotes), not assumed.
- **Demo**: Ethereum mainnet, real positions, the RockawayX curator book shared by Belem, real crises replayed.

---

## How it maps to the judging criteria
| Criterion | What we built | Where |
|---|---|---|
| **Dependency discovery (30%)** | Graph of a Pendle PT position on Morpho Blue: 28 nodes, 45 edges, 7 layers deep (position → market → PT → SY → sUSDe → USDe → Ethena → custodians / exchanges, plus oracles, AMM pool, lenders, chain). Market id, oracle prices and accrued interest are **recomputed**; provenance is proven (Morpho oracle factory, Pendle `isValidMarket`, Chainlink ENS). Unknown contracts are flagged `unresolved`, never guessed. A strict validator checks the contract at every build | `src/discovery/`, `output/graph.json` |
| **Impact estimation (30%)** | One transmission rule per edge type, written in plain English. Faithful simulation of the position's meta-oracle (threshold and 16 h timer read on-chain), official Morpho liquidation bonus, liquidator profitability after on-chain slippage, bad debt for lenders. 15 stress scenarios, a price × duration grid, a 200,000-week Monte Carlo correlated through shared dependencies, sensitivity on every hypothesis | `src/risk/`, `risk/*.yaml` |
| **Decision usefulness (25%)** | p\* per scenario, optimal partial exit (marginal cost = marginal expected loss), one sentence per verdict, a "3 a.m. question" for the manager. Backend v2 does the same for **any holder, vault or curator book** | `src/risk/decide.py`, `src/stacktrace/` |
| **Working demo on real data (15%)** | Mainnet at a pinned block, every RPC/API response cached in `data/cache/` so position A replays with **zero network calls**. Live API + slide-deck front on the RockawayX book. Replays of the real USDe crises of 21/02/2025 and 10/10/2025 | `front/`, `src/stacktrace/api.py` |

Every number in `risk/*.yaml` carries a status (official source + date, on-chain field, or stated hypothesis with a
range); the loader rejects anything else. There is no "magic score": only dollars, percentages and p\*.

## Results

### Position A: PT-sUSDe collateral on Morpho Blue, USDC borrowed (block #26162087)
| | |
|---|---|
| Position | 413,030 PT-sUSDE-26NOV2026 as collateral, 357,217 USDC debt, LTV 87.2% / LLTV 91.5%, health factor **1.050** (liquidatable after a 4.75% oracle drop) |
| Oracle | Steakhouse meta-oracle: primary = fixed linear discount; backup = Chainlink USDe/USD. Switches if they diverge by more than 0.75% for 16 h |
| No alert | Monte Carlo over 7 days: expected loss ≈ $131, VaR 95% = $0, ES 99% ≈ $13k → **STAY** |
| Alert: lasting USDe depeg −30% | the oracle switches after 16 h, the position is liquidated: **−$53,133** (all the capital), **−$77,723 for the lenders** |
| Exit cost (measured) | **$854** (PT sale simulated on the real Pendle pool + gas + forgone yield) → **p\* = 1.6%** over 7 days, i.e. an event that happens about once every 14 months |
| The trap | **duration**, not depth: USDe at $0.93 for 6 h costs $0; for 24 h it liquidates (−$37k) |
| The hidden risk | a Pendle exploit is invisible to the fixed oracle: no liquidation, **$152k of bad debt for the lenders** |
| Real crisis replayed | 10/10/2025, USDe at $0.65 on Binance: our oracle holds; an oracle reading the Binance price would have liquidated the position |

```
POSITION ── deployed_in ──▶ Morpho Blue market PT-sUSDE-26NOV2026 / USDC (LLTV 91.5%)
            ├─ collateralized_by ▶ PT-sUSDe ─ redeemable_into ▶ SY ▶ sUSDe ▶ USDe ─ issued_by ▶ Ethena Labs
            │                       │                                                └ deployed_in ▶ Copper, Ceffu, Fireblocks,
            │                       └ deployed_in ▶ Pendle PT/SY pool ($3.8M)                     Binance, Bybit, OKX…
            ├─ lends ▶ USDC ─ issued_by ▶ Circle
            └─ priced_by ▶ meta-oracle ─▶ primary (fixed discount)  /  backup (discount × Chainlink USDe/USD)
                                                                     (+ every contract ─ settled_on ▶ ethereum)
```
Full walkthrough: [docs/POSITION_A.md](docs/POSITION_A.md).

### Backend v2: any real holder, vault or curator book
Starting from an address (`0x…`), a whole Morpho vault (`vault:0x…`) or a curator book (`book:rockawayx` = the 12
Ethereum Morpho vaults of the RockawayX Dune dashboard shared by Belem), v2 finds every pocket, builds its proven
graph, generates incidents from that graph, measures the exit cost (withdrawable liquidity, DEX quotes, gas) and
returns **STAY / EXIT** with p\*, plus the dependencies shared across pockets (hidden concentration).
→ [docs/BACKEND_V2.md](docs/BACKEND_V2.md) · [docs/API.md](docs/API.md)

---

## Quick start
Requirements: Python **3.11**, Node 18+ (for the front only).

```bash
pip install -r requirements.txt
python -m pytest                                    # ~10 s, no network: discovery, engine, backend v2, API
```

**Position A, fully offline** (everything is read from `data/cache/`):
```bash
export PYTHONPATH=src                               # PowerShell: $env:PYTHONPATH="src"
python -m discovery.build_graph --offline           # rebuild output/graph.json: 0 network calls
python -m discovery.inspect_graph --impact usde     # who is hit if USDe breaks, and through which path
python -m risk.run                                  # output/risk_report.json + risk_grid.json
```

**Live: API + slide deck** (needs `ETH_RPC_URL` in `.env`, see `.env.example`):
```bash
python -m stacktrace.api --hold-block               # http://127.0.0.1:8000, one block until restart
python -m stacktrace.warmup book:rockawayx          # precompute the curator book (minutes the first time)
cd front && npm install && npm run dev              # http://localhost:5173
```
The front computes no risk: it only reads the API (or responses recorded with `python -m stacktrace.record <holder>`).
Demo script: [docs/DEMO.md](docs/DEMO.md).

Other tools: `python -m discovery.inspect_graph --evidence` (evidence of every edge),
`python -m discovery.validate output/graph.json` (contract check), `python -m risk.refresh` (re-read everything at a
new block, online). With `pip install -e .`, `PYTHONPATH=src` is no longer needed.
On Windows, if you clone into a deep folder, run `git config --global core.longpaths true` first.

## Architecture
```
config.yaml           entry points (Morpho market, user, curator books), each address with its source
curated.yaml          off-chain layer (issuers, custodians, exchanges): every row has an https URL + date
src/discovery/        PART 1 · proven dependency graph → output/graph.json
  ctx.py rpc.py cache.py http.py   the only door to the chain/APIs; cache at the web3 provider level, pinned block
  adapters/           morpho, morpho_api, oracles, pendle, erc20, erc4626, ens, contracts (proxies), chain, curated
  graph.py ids.py vocab.py validate.py   graph model, deterministic ids, frozen vocabulary, strict validator
  build_graph.py inspect_graph.py        orchestrator (breadth-first) and networkx inspector
src/risk/             PARTS 2-3 · engine on position A, reads only output/ + risk/*.yaml
  propagate.py        one rule per edge type
  oracle_sim.py position.py   what the oracle shows during a shock; health, liquidation, borrower/lender losses
  exit_cost.py decide.py      measured exit cost, p*, partial exit, verdict
  montecarlo.py calibrate.py replay.py validation.py   Monte Carlo, Chainlink history, real crises
  collect.py refresh.py run.py   on-chain reads at the graph's block; report + grid + validator
src/stacktrace/       BACKEND v2 · any holder / vault / curator book, HTTP API (FastAPI)
risk/                 params.yaml, params_v2.yaml, scenarios.yaml, replays.yaml (every number has a status)
front/                slide-deck front (React + Vite), reads API v2 or its recordings
data/cache/           pinned RPC/API responses, committed on purpose: the demo survives a network outage
output/               graph.json, risk_inputs.json, risk_report.json, risk_grid.json (inputs of tests: never delete)
docs/                 documentation, see docs/README.md
```

## Anti-hallucination guarantees
- **Pinned block**: every read is made at the same block, written in each piece of evidence.
- **Recomputed, not trusted**: market id (`keccak256(MarketParams)`), every Morpho oracle price, the linear discount
  formula, accrued interest (0.0001% from the Morpho API).
- **Proven provenance**: oracle factory (`isMorphoChainlinkOracleV2`), Pendle factory (`isValidMarket`), Chainlink ENS.
- **APIs locate, the chain proves**: an API result is re-read on-chain before it becomes an edge.
- **Unknown = flagged**: `meta.unresolved = true`, never guessed. **Curated = sourced**: URL + date or rejected.
- Every hand-written address is listed in [docs/VERIFY.md](docs/VERIFY.md) with its source, to be ticked by a human.

## Known limits
Stated openly in [docs/AUDIT.md](docs/AUDIT.md) (score per criterion, open findings, questions for the mentors).
In short: Ethereum + Morpho only (no Solana/Kamino yet); exploit frequencies are stated hypotheses (the decision
rests on p\*, which does not depend on them); the exit cost is measured in a calm market; the v2 engine is shallower
than the v1 engine of position A.

## Documentation
Start with [docs/README.md](docs/README.md), the index of every doc by reader (jury, demo, developers).
The brief and the framing note are in [docs/brief/](docs/brief/).
