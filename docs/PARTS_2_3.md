# Parts 2 and 3: what the brief asks for, what we did, where it is

Sources: the Belem brief ([`brief/challenge-brief.pdf`](brief/challenge-brief.pdf)) and the
team's framing note ([`brief/framing-note.pdf`](brief/framing-note.pdf)).
The brief's grading scheme: **Discovery 30%** (part 1, already done) · **Impact estimation 30%** (part 2) ·
**Decision usefulness 25%** (part 3) · **Demo on real data 15%**.

---

## Part 2: impact estimation ("is the number defensible?")

| What the brief and the framing note ask for | What we did | Where |
|---|---|---|
| Per-node scenarios: exploit, depeg, oracle failure/manipulation, liquidity freeze, chain halt | **15 stress scenarios**: USDe depeg (3 variants), exchange failure (1 or 3), custodian, wrong feed, frozen feed, pool ÷2 and ÷10, USDC depeg, Pendle exploit, Morpho exploit, Ethereum halt, passage of time. Plus a **grid of 228 cases** (USDe price × duration) | `risk/scenarios.yaml`, `src/risk/scenarios.py` |
| One transmission rule per edge type, **written in plain language** | `redeemable_into` (value follows the underlying), `issued_by` (loss of reserves, without double counting), `deployed_in` (share exposed to the counterparty), `priced_by` (transmitted only if the oracle follows the market), `collateralized_by` / `lends` (effect on health) | `src/risk/propagate.py` (`RULES`) |
| "Collateral drops + oracle follows the market → liquidation, loss = bonus + slippage" | oracle simulator + liquidation with **Morpho's official liquidation bonus** (sourced formula). The liquidator only acts if it is profitable **after slippage measured on-chain** | `src/risk/oracle_sim.py`, `src/risk/position.py` |
| "Collateral drops + fixed oracle → no liquidation → residual debt for the lenders" | computed and displayed: the Pendle exploit (SY −50%) leaves a **$152k** hole for the lenders, without any liquidation | scenario `S-PENDLE-EXPLOIT` |
| The meta-oracle (specific to our position) | **sourced** switch rule (Steakhouse docs) and **parameters read on-chain** (threshold 0.75%, delay 16 h, return 24 h). The duration of the shock decides everything | `oracle_sim._meta` |
| Calibration on the incident history | **full on-chain history** of the Chainlink USDe/USD feed (960 rounds since 04/2024): worst gap 2.3% (21/02/2025), 1 episode below $0.99 in ~2.5 years. The DeFiLlama hacks dataset is **paid**: exploit frequencies are **displayed hypotheses** | `src/risk/calibrate.py`, `risk/params.yaml` |
| Monte Carlo with correlation through common parents → expected loss, VaR 95%, costliest path | 200,000 simulated weeks (fixed seed). Events that hit the same node add up on it and then on its dependants. Outputs: expected loss, **VaR 95/99**, ES 99, P(liquidation), **top 3 paths** (with evidence) | `src/risk/montecarlo.py` |
| "Visible and sourced hypotheses, sensitivity displayed" | **every** parameter has a status (sourced / on-chain / hypothesis), otherwise the loader refuses it. **Sensitivity tornado** on each hypothesis | `src/risk/params.py`, `report.sensitivity` |
| No "magic 0-100 score" | no score: only $, %, a threshold p* | — |

## Part 3: decision usefulness ("stay or exit, and why")

| What the brief and the framing note ask for | What we did | Where |
|---|---|---|
| Exit if p·LGI·V > C_exit ⇔ p > **p\*** = C_exit / (LGI·V) | p\* computed for each scenario and each cell of the grid | `src/risk/decide.py` |
| C_exit = slippage on the **real liquidity** + gas + forgone yield | slippage **simulated on-chain** (Pendle RouterStatic `swapExactPtForSyStatic`, 16 sizes), gas (block base fee × Chainlink ETH/USD), forgone yield (PT APY − borrow cost). The conversion to USDC is a displayed hypothesis | `src/risk/exit_cost.py`, `src/risk/collect.py` |
| **Partial exit**: marginal slippage = marginal expected loss | optimisation of the fraction f that minimises C_exit(f) + p·Loss·(1−f), for each p from 0 to 100% | `decide.best_fraction`, `decision_table` |
| STAY / PARTIAL x% / EXIT verdict, in one sentence | for each scenario + a "no alert" verdict (Monte Carlo) + a main verdict (framing note alert: −30% depeg) | `report.headline`, `report.baseline` |
| The 3 costliest contagion paths, drawn on the graph | `monte_carlo.top_paths` (graph.json edges with their evidence), drawn as fractures in the front | front, skeleton mode |
| List of hypotheses with source + confidence level | `report.params`, `report.confidence` (p*: medium to high; expected loss: low, said plainly) | risk sheet |

## Demo on real data (15%)

| Asked | Done |
|---|---|
| Real mainnet addresses, live calls with cache | the whole graph + the engine reads are made at the **same block** (#26162087), cached, then replayed offline (`python -m risk.refresh`, then `risk.run`) |
| Replay of a real incident | **10 October 2025** (framing note plan B): USDe at $0.65 on Binance for ~40 min (curated source), on-chain ≥ $0.9929 (read on Chainlink). Our oracle holds, an oracle plugged into Binance would have liquidated us. Bonus: 21 February 2025 |
| An app that runs | slide-deck front (`front/`), on API v2 or its recorded responses |

## What is NOT done (and why)
- **xUSD / deUSD replay (November 2025)**: we would need to find an exposed vault and its allocations from before the crisis (historical blocks, hence an archive RPC). The framing note's plan B was done instead.
- **Position B (curated Morpho vault) and the "10-pocket book" view**: done in backend v2 (`vault:0x…`, `book:rockawayx`), see [`BACKEND_V2.md`](BACKEND_V2.md). The v1 engine above stays on position A.
- **Exploit probabilities calibrated on DeFiLlama**: paid dataset. Possible alternatives: rekt.news or a sourced manual export.
