# Full audit: StackTrace against the Belem brief (10/10/2026)

> Goal: know, criterion by criterion of the grading scale, where we gain points, where we lose them, and what to do **before the
> feature freeze**. This document changes no code: every proposed fix waits for the team's agreement.

## 0. Method
**Read:**
- the brief (`docs/BelemCapital_EPFL-Hackathon_DeFi-Risk-Dependency-Challenge_EN_v1.pdf`) and the framing note (`docs/Belem DeFi Risk — Cadrage & Guideline.pdf`);
- all of `src/` (discovery, risk, stacktrace), `risk/*.yaml`, `config.yaml`;
- the outputs (`output/`, `docs/api_examples/`) and all the docs.

**Run (offline):**
- `pytest`: **129 tests green**, 2 skipped (network tests);
- `discovery.build_graph --offline`: 1027 cached reads, **0 network calls**;
- `discovery.validate`: valid contract;
- `risk.run`: report identical to the committed report;
- `npm run build` of the `front/` front end: the build passes.

**Counter-experiments:** a few cases run by hand to test the engine (section 3.2).

**Not verified:**
- the RockawayX Dune dashboard: `dune.com` is blocked by this environment's network (section 4);
- the v2 backend live: it needs an RPC, and no key is present here. It was judged on its recorded responses (`docs/api_examples/`, block #26162868).

---

## 1. Verdict in 30 seconds
The project answers the problem statement and the framing note **to the letter**:
- a **proven** dependency graph (the brief's 5 layers, and even 7 hops down to Ethena's custodians);
- an impact in **$**, propagated by one rule per edge type;
- a **STAY / PARTIAL / EXIT** decision based on **p\***;
- a real replay, a real book of 11 pockets taken from the Dune dashboard;
- a demo that runs without network.

That is already above what is expected from a team of beginners.

The lost points hide in three places:
1. **three engine artefacts** that an expert on the jury can find in 5 minutes (section 3.2);
2. **the "calm market" exit cost**, used even when the alert has already fired (section 3.3);
3. **a two-headed demo story**: two engines, two front ends, two blocks (section 3.4).

| Criterion (weight) | Estimated score today | After the P0 fixes | Why |
|---|---|---|---|
| Discovery (30%) | 4 / 5 | 4 / 5 (4.5 with P1) | Very solid on position A; shorter v2 graphs (no issuers or off-chain layer for Belem's RWAs) |
| Impact (30%) | 3.5 / 5 | 4.2 / 5 | Fine-grained mechanics (meta-oracle, Morpho LIF, measured slippage), but "all or nothing" liquidation is non-monotonic and collateral is misclassified in v2 |
| Decision (25%) | 4 / 5 | 4.5 / 5 | p\* and partial exit: exactly what the brief wants. Missing: the exit cost **under stress** and an indifference zone |
| Demo (15%) | 4 / 5 | 4.5 / 5 | Offline and reproducible, but in recorded mode 9 pockets out of 11 have no detail |
| **Weighted total** | **≈ 3.85 / 5** | **≈ 4.3 / 5** | personal estimate, not an official score |

---

## 2. What the brief asks for → what we have
| Brief requirement | Status | Where |
|---|---|---|
| "Automatically identify the dependencies of a position" | ✅ v1 starts from a `marketId` + `user`; v2 starts from **any holder address** | `src/discovery/`, `src/stacktrace/portfolio.py` |
| The 5 layers of the Pendle PT example (chain, yield source + issuer, oracle, PT AMM, lending market) | ✅ all present for position A, each with its evidence | `output/graph.json` |
| "Estimate the potential economic impact […] when one of them is affected" | ✅ 15 scenarios, a grid of 228 cases, a Monte Carlo, borrower **and** lender losses | `src/risk/` |
| "Explain how that incident propagates through the dependency stack" | ✅ in v1 (rule per edge + trace + paths); ⚠ shorter in v2 (section 3.2, C) | `src/risk/propagate.py` |
| "Stay or exit […] despite slippage and execution costs" | ✅ p\* = C_exit / loss, partial exit, decision sentence | `src/risk/decide.py`, `src/stacktrace/analyze.py` |
| Book of 10 pockets, one pocket affected, exit at 11% | ✅ real book of 11 pockets and shared dependencies (v2); ⚠ the brief's numerical example (10 × 10%, 11%) is not replayed as is | `/book`, `front/` slide 7 |
| "Runs on real data" | ✅ mainnet, pinned block, committed cache, replay of 10/10/2025 | `data/cache/`, `src/risk/replay.py` |
| Scope: **feed-quality** analysis | ⚠ partial: pricing mode (market / fixed / internal rate), Midas bounds, Chainlink history. **No age ↔ heartbeat comparison**, nor deviation threshold | `adapters/oracles.py` |
| Scope: vault deploying to an **external venue (perp)** | ⚠ covered indirectly (Ethena → exchanges, curated layer); position C of the framing note is not done | `curated.yaml` |
| Scope: protocol that **concentrates a large share of TVL** | ❌ not handled (we have `tvl_usd` per node, but no share of the chain's TVL) | — |
| Scope: other ecosystems (Solana, Canton, Tempo) | ❌ Ethereum + Morpho only. The Dune dashboard also contains **Kamino (Solana)** vaults | — |

---

## 3. Criterion by criterion

### 3.1 Discovery (30%): "depth and correctness"
**Strengths (to highlight in front of the jury)**
- **Zero hand-drawn edges.** Every edge carries `source` and evidence (`Contract.function(args) = result @ address #block`). The validator rejects anything else.
- **Independent recomputations:**
  - the market id is recomputed (keccak);
  - the price of every Morpho oracle is recomputed;
  - accrued interest is recomputed (0.0001% deviation from the API).
- **Proven provenance:** oracle factory, `isValidMarket` for the Pendle pool, ENS for the Chainlink feed.
- **Depth:** position → market → PT → SY → sUSDe → USDe → Ethena → custodians / exchanges, i.e. 7 hops. The brief shows 5.
- **The Steakhouse meta-oracle** (threshold 0.75%, delay 16 h, read on-chain): a detail few teams will find.
- **v2:** from a real address, 11 pockets discovered, V2 vault → adapters → markets. Borrowers are read one by one.

**What costs points**
1. **The v2 graphs stop at the collateral.** The "Belem RWA EURCV" vault has 25 nodes, but its only issuers are Chainlink, Morpho and RockawayX. No node for:
   - the issuer of **EURCV**, **mGLOeuro**, **PST**, **cbBTC**, **WBTC**, **wstETH**, **weETH**;
   - their custodians or their underlying funds.

   Yet this is **Belem's book**, and it is layer 2 of the brief ("underlying yield source and its issuer"). `curated.yaml` only covers position A.
2. **USDe's reserves are not modelled.** We have Ethena's custodians and exchanges, but not the **composition** of the reserves (liquid assets, LSTs, stablecoins…).
3. **The exit route is not discovered.** The 2nd leg (sUSDe → USDC) is a 5 bp hypothesis (`risk/params.yaml:80`). The secondary pools are not in the graph. Yet that is where slippage explodes in a crisis. For the record, the sUSDe cooldown (1 day, read on-chain) rules out the "unstake" route.
4. **Feed quality:** `age_seconds` is read, but never compared with the heartbeat published by Chainlink. The brief's scope explicitly mentions "feed-quality analysis".
5. **`lends` and `collateralized_by`** are still "to be confirmed with the organisers" (`vocab.py`). It is a 30-second question to ask a mentor.

### 3.2 Impact (30%): "is the number defensible"
**Strengths**
- **Official Morpho** liquidation (LIF = min(1.15, 1/(0.3·LLTV + 0.7)), source cited).
- The liquidator only acts if it is profitable **after slippage measured on-chain** (Pendle RouterStatic).
- **The meta-oracle simulated faithfully.** The demonstration "$0.93 for 6 h = $0, for 24 h = −$37k" is the best moment of the demo.
- **Lender losses are distinguished** from the borrower's (Pendle exploit: $152k of bad debt without liquidation). That is the insight the framing note expects.
- **Every parameter has a status**, a range and a sensitivity tornado. No "magic score".

**Three verified artefacts that an expert can find quickly**

**A. "All or nothing" liquidation: a worse market reduces the loss (non-monotonicity).**
- *Where:* `src/risk/position.py:107-117`. The liquidator repays 100% of the debt at once, and only does so if it is profitable on that whole block.
- *What we ran:* the USDe at $0.93 for 24 h scenario, with an extra 3% AMM discount (the top of its sensitivity range).

| Extra AMM discount | Liquidation | Borrower loss |
|---|---|---|
| 0% | yes | $37,556 |
| 3% (worse market) | no ("not profitable") | **$0** |

  The same thing shows in the tornado: the expected loss drops from $147 to $42 when the market gets worse.
- *Why it is wrong in reality:* on Morpho, a liquidator chooses **the size** it repays. If repaying everything is not profitable, a part often is, because slippage is lower on a small sale.
- *Fix (≈ 1 h):* search for the largest repaid fraction that stays profitable (grid in 5% steps), instead of a yes / no on 100%.

**B. v2: a composite collateral receives only one type of shock.**
- *Where:* `src/stacktrace/market_data.py:111` and `:161-164`, `src/stacktrace/risk_engine.py:240`.
- *What happens:* if **one** building block of the oracle is an internal rate, the whole collateral is classified `rwa_or_synthetic`. Example: weETH, priced by the weETH/eETH rate × ETH/USD.
- *Consequences in `docs/api_examples/book.json`:*
  - the same weETH receives the `volatile_crash` incident in pocket 1 (weETH/RLUSD), but `rwa_credit_event` (5%/year, −5 to −50%) in pocket 4 (weETH/USDT, $2.56M);
  - in pocket 4, **an ETH crash that would trigger liquidation is not modelled at all**;
  - in the RockawayX wETH vault, we even see a `rwa_credit_event:eth` incident.
- *Fix (≈ 1 h 30):* generate **two** families for a composite collateral:
  - the market component (ETH), which the oracle follows, hence with liquidation;
  - the specific component (depeg of the LST or the RWA), which the oracle does not see, hence bad debt.

**C. Two engines, two propagation depths.**
- **v1** (`src/risk/propagate.py`) propagates any shock, edge by edge, from any node. Ethena, a custodian, an exchange: everything flows up to the position.
- **v2** (`risk_engine.py`) only generates incidents on the direct collateral, its direct issuers, the feeds, the protocol and the curator. A "deep" failure (underlying of a PT, reserves of a stablecoin) is therefore folded into a generic `rwa_credit_event`.
- **Risk in front of the jury:** "Which one is your engine?" A clear answer is needed, see section 5.

**Other weaknesses (already partly acknowledged in `docs/AUDIT.md`)**
- **Headline probability inconsistent with our own model.**
  - The headline says "EXIT — you estimate a 10% chance" of a USDe −30% depeg in 7 days (`risk/scenarios.yaml:21`).
  - Our Monte Carlo gives ≈ **0.19%** per week for the **whole** "severe depeg" family (λ = 0.1/year).
  - Defensible only if we say clearly that it is **a probability conditional on the alert**, entered by the manager. Today, this is written nowhere.
- **Independent v2 Monte Carlo** (`risk_engine.py:281`): no correlation between incidents or between pockets. v1, on the other hand, correlates through common parents.
- **v2 lenders and volatile collateral:** the loss is **always 0** ("gradual drop"). A flash crash (10/10/2025, precisely) can jump the 1 − LLTV = 14% margin. We would need at least one "gap" case.
- **Layer 1 (chain):** the only scenario gives $0. It is consistent (24 h halt, prices back before the horizon), but the layer looks "free". A "halt + lasting depeg" case would show the effect.
- **Exploit frequencies:** these are hypotheses (paid DeFiLlama dataset). Well acknowledged; p\* protects the decision.

### 3.3 Decision (25%): "stay or exit, and why"
**Strengths:** p\* is **exactly** the brief's trade-off ("exiting is expensive and certain, staying is cheap and uncertain"). There is the partial exit, one sentence per verdict, the p → verdict table read by the front end, and limited vault liquidity (`f_max` = 22% exitable for Belem RWA EURCV). Very strong.

**What is missing**
1. **The exit cost is measured "cold".**
   - For S-USDe-30, p\* = $854 / $53,133 = 1.6%, with an intact Pendle pool and a 2nd leg at 5 bp (`src/risk/scenarios.py:92`: no liquidity stress in this scenario).
   - Yet the brief says "**one pocket is affected**. Unwinding it costs 11%". That is the exit cost **during** the incident.
   - *Fix (≈ 1 h):* show p\* as a range, "1.6% if we exit before the market reacts, X% if the pool has already lost half its liquidity". We already have the pool factors (`exit_model.cost(f, pool_factor)`).
2. **No indifference zone.**
   - Pocket 9 (PST/PYUSD, $40k) shows **EXIT** because the expected loss ($46) exceeds the cost ($45) by **$1**.
   - A manager wants "STAY (indifferent)" when the gap is below a materiality threshold. *Fix:* 20 min.
3. **Different vocabulary between v1 and v2.**
   - v1: STAY / PARTIAL x% / EXIT.
   - v2: STAY / EXIT only (`analyze.py:141,182`). On the mGLOeuro incident, v2 says "EXIT" for 22% of the pocket.
   - The framing note asks for "STAY / PARTIAL x% / EXIT". *Fix:* 15 min.
4. **Léa's question 5** ("how long before liquidity disappears?") has no explicit answer.
   - We have the ingredients: the meta-oracle's 16 h window, and the vault's `f_max`, which drops if other depositors exit before us.
   - A line such as "you have ≈ 16 h before the oracle switches", or "withdrawable liquidity is 22% and it is shared with N other depositors", would be very telling.

### 3.4 Demo on real data (15%)
**Strengths:**
- everything can be replayed offline, at the same block, with a test that checks that `web/data/` is identical to the outputs;
- the 10/10/2025 replay is **a real incident**, with the lesson "the oracle's source matters";
- a timed demo script (`docs/DEMO.md`) and a plan B.

**Risks**
1. **Two stories:**
   - v1 "X-Ray": `web/`, position A, block #26162087;
   - v2 "Slides": `front/`, real book, block #26162868.

   `docs/DEMO.md` only talks about v1. Yet v2 (the real book from the Dune dashboard provided by Belem) is what will speak **the most** to their risk team.
2. **The v2 front end in recorded mode** only has the detail of 2 pockets out of 11 (`front/README.md`). If the Wi-Fi or the RPC goes down, 9 pockets show "computed live". The live cache (`data/cache_live/`) is ignored by git, which goes against the "everything is cached" rule of `CLAUDE.md`.
3. **The framing note's main replay** (xUSD / deUSD, Nov. 2025) is not done. Plan B (10/10/2025) is: that is acceptable, but it must be said.
4. **Outdated numbers in the docs:** "97 tests" in `CLAUDE.md:114`, `README.md:119` and `docs/NEXT_STEPS.md:11`, versus **129** today. A jury that runs `pytest` will see it.

---

## 4. The RockawayX Dune dashboard provided by Belem
- **Access:** impossible from this environment (the proxy refuses `dune.com`). I therefore did **not** verify its content. To be done by a human: compare the list of vaults in the dashboard with the 11 pockets of `docs/api_examples/book.json`.
- **Public sources on RockawayX:**
  - RockawayX curates vaults on **Morpho (Ethereum)** and on **Kamino (Solana)**;
  - its first Morpho vaults are USDC Prime, USDC Yield and wETH.

  Sources: [RockawayX, vaults on Morpho](https://rockawayx.com/insights/rockawayx-launches-three-curated-vaults-on-morpho), [overview of RockawayX curation](https://rockawayx.com/insights/rockawayx-vault-curation-an-overview-of-products-capabilities), [Morpho forum](https://forum.morpho.org/t/introducing-rockawayx-vaults-on-morpho/2214).
- **What we already do with it (well):**
  - the holder `0x4F87…0545`, main depositor of the "Belem RWA EURCV" vault;
  - 11 real pockets ($26.4M);
  - the shared dependencies (Morpho: 11 pockets; Chainlink: 7; RockawayX curator: 4).
- **What is missing:**
  - the **Kamino / Solana** vaults of the same curator (the brief mentions Solana in the scope);
  - confirmation, by Belem, that `0x4F87…` really is theirs (still "to be confirmed" in `docs/BACKEND_V2.md`). **Question no. 1 to ask the mentor.**
- **A small visible flaw:** in `shared_dependencies`, two different nodes carry the same name "Chainlink ETH / USD". On the "Concentration" slide, this is confusing. We need to show the short address, or merge them.

---

## 5. The questions the jury will ask (and the answer to prepare)
| Likely question | Ready answer |
|---|---|
| "Where do your exploit probabilities come from?" | "They are displayed hypotheses, with a ×0.5 / ×2 sensitivity. The decision rests on **p\***, which does not depend on them." ✅ |
| "Why EXIT if you estimate 10%? Your Monte Carlo says 0.2%/week." | ⚠ To prepare: "10% is the probability **conditional on the alert**, entered by the manager. Without an alert, we say STAY." Write it in the front end too. |
| "Your loss goes down when the market gets worse?" | ❌ Today, no good answer → fix A. |
| "If USDe is already at 0.93, does exiting still cost $854?" | ⚠ → fix 3.3-1 (p\* as a range, with the stressed pool). |
| "V = $53k or $410k?" | "Net capital: it is what the fund allocated to the pocket. With ×7.7 leverage, LGI = 100%." The answer exists, but it has not been validated by the mentors (`NEXT_STEPS.md`). |
| "v1 or v2, which one is your engine?" | Proposal: "v1 = depth (edge-by-edge propagation, on the brief's exact example); v2 = scaling up to the **real book**. Same discovery, same evidence, same p\* rule." |
| "Does it work on Solana?" | "No, and that is acknowledged: Ethereum + Morpho cover 11 real pockets. The one-adapter-per-protocol architecture is built to add more." |
| "Who says Ethena's custodians are those ones?" | "The curated layer: official URL + date, on every row. The weights are at 1.0 (upper bound) and that is written in the evidence." ✅ |

---

## 6. Prioritised action plan
The roles follow the framing note: **P1** = Discovery, **P2** = Risk engine, **P3** = Demo and story. Each fix touches one area of code and can be tested on its own.

### P0: before the freeze (≈ 5 h in total, to be split)
| # | Who | What | Effort | Gain |
|---|---|---|---|---|
| 1 | P2 | **Profitable partial liquidation** (artefact A) + a monotonicity test: "loss(worse market) ≥ loss(normal market)" | 1 h | Impact |
| 2 | P2 | **Composite collateral in v2**: two families (market + specific) (artefact B) + a test on a weETH oracle | 1 h 30 | Impact |
| 3 | P2 | **p\* as a range**: normal and stressed exit cost (pool ÷2), shown in the headline and on the Verdict slide | 1 h | Decision |
| 4 | P2 | **Indifference zone** + **PARTIAL** label in v2 | 30 min | Decision |
| 5 | P3 | **A single demo thread:** X-Ray (position A, 3 min) → switch to "and on Belem's real book" (v2 front end, 1 min 30). Update `DEMO.md` | 45 min | Demo |
| 6 | P3 | **Record the 11 pockets** (`/risk` and `/graph` for each) in `docs/api_examples/` for the v2 front end's offline mode | 30 min (with an RPC) | Demo |
| 7 | P3 | **Docs up to date:** 129 tests; "p = probability conditional on the alert" in the front end and the README | 15 min | Demo |

### P1: if time allows
| # | Who | What | Effort |
|---|---|---|---|
| 8 | P1 | **Curated layer for the Belem book's assets.** Issuer, and custodian if published, for EURCV, mGLOeuro, PST, cbBTC, WBTC, wstETH, weETH. Each row: official URL + date, ticked in `VERIFY.md` | 1 h 30 |
| 9 | P1 | **Feed quality:** heartbeat and deviation threshold (Chainlink docs, sourced curated row) compared with `age_seconds`, with a "stale feed" flag | 1 h |
| 10 | P1 | **TVL concentration** (brief's scope): share of the chain's TVL for Morpho, Pendle, Ethena, via the public DeFiLlama API (endpoint to be checked in their docs, response cached) | 1 h |
| 11 | P2 | **Replay the brief's example**: 10 pockets × 10%, exit at 11%. Show that p\* = 11% / LGI. One more line on the Verdict slide | 30 min |

### P2: to tell the jury rather than code today
- The xUSD / deUSD replay (it needs an archive RPC).
- Kamino / Solana.
- Correlations between pockets in v2 (reuse v1's "common parents" logic).
- A public calibration of exploit frequencies.
- Merging the two engines.

---

## 7. Questions still open for the Belem mentors
1. Is the address `0x4F87…0545` (main depositor of "Belem RWA EURCV") really yours?
2. Decision horizon: 24 h or 7 days? (today: 7 days, hypothesis)
3. Pocket size **V**: net capital ($53k) or gross value ($410k)?
4. The `lends` extension, and the `collateralized_by` direction ("is collateral of", read backwards): accepted?
5. Does p\* speak to you more than a probability we would estimate ourselves?
6. The RockawayX Dune dashboard: which pockets do you want to see first, Morpho or Kamino?
