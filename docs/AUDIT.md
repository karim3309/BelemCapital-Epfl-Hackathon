# Audit

This file has two parts:
1. **the current audit** of the whole project against the Belem brief and its grading scheme (what is solid, what is
   missing, what comes next);
2. **the audit log**: the audits run during development, each with its findings and fixes (history, kept as is).

---

## 1. Current audit (11/10/2026, `main` at block #26162087 / #26162868)

### 1.1 What was run
| Check | Result |
|---|---|
| `python -m pytest` | ✅ 142 passed, 2 skipped (network tests), ~9 s, no network |
| `python -m discovery.build_graph --offline` | ✅ 1027 cached reads, **0 network calls** |
| `python -m discovery.validate output/graph.json` | ✅ valid contract, 28 nodes, 45 edges |
| `python -m risk.run` | ✅ rewrites `output/` byte for byte (reproducible) |
| `cd front && npm ci && npm run build` | ✅ type check + production build pass |

Not run here: the v2 backend live (it needs an RPC key) and the RockawayX Dune dashboard (to be compared by hand,
see [`VERIFY.md`](VERIFY.md) §A bis).

### 1.2 Score against the grading scheme (team estimate, not an official score)
| Criterion (weight) | Estimate | Why |
|---|---|---|
| Dependency discovery (30%) | 4 / 5 | Position A: 7 layers (position → market → PT → SY → sUSDe → USDe → Ethena → custodians / exchanges), every edge proven, independent recomputations (market id, oracle prices, accrued interest), provenance proven (oracle factory, `isValidMarket`, ENS). v2 graphs stop at the collateral: no issuer / custodian for EURCV, mGLOeuro, PST, cbBTC, WBTC, wstETH, weETH |
| Impact estimation (30%) | 3.5 / 5 | Faithful meta-oracle (threshold + 16 h timer read on-chain), official Morpho liquidation bonus, slippage measured on-chain, lender losses separated from the borrower's, every parameter with a status. Three engine artefacts remain (§1.3) |
| Decision usefulness (25%) | 4 / 5 | p\* = C_exit / loss is exactly the brief's trade-off; partial exit on position A; sentence per verdict. v2 says STAY / EXIT only and measures the exit cost "cold" |
| Working demo on real data (15%) | 3.5 / 5 | Mainnet, pinned blocks, offline replay of position A, real crises replayed. The deck is live by default and has **no recorded fallback** for the RockawayX book yet |

### 1.3 Open findings, by priority
| # | Severity | Finding | Where | Fix |
|---|---|---|---|---|
| 1 | 🔴 demo | `docs/api_examples/recordings/` does not exist: the deck opens on `book:rockawayx` but recorded mode has nothing to show. If the RPC or the Wi-Fi fails on stage, there is no fallback | `front/src/api/recorded.ts` | with an RPC: `PYTHONPATH=src python -m stacktrace.record book:rockawayx`, then commit the folder |
| 2 | 🔴 demo | The narrative of [`DEMO.md`](DEMO.md) still follows the former single holder `0x4F87…` (11 pockets, $26.4M) | `docs/DEMO.md` | rewrite on the live numbers of the warm-up |
| 3 | 🟠 impact | "All or nothing" liquidation: the liquidator repays 100% of the debt or nothing, so a worse market can **reduce** the loss (e.g. USDe $0.93 for 24 h: −$37.6k; same with +3% AMM discount: $0) | `src/risk/position.py` (liquidation block) | largest profitable repaid fraction (5% grid) + a monotonicity test |
| 4 | 🟠 impact | v2: a composite collateral (one internal-rate building block, e.g. weETH = weETH/eETH rate × ETH/USD) is classified `rwa_or_synthetic` as a whole, so an ETH crash that would liquidate is not modelled | `src/stacktrace/market_data.py` (`collateral_class`) | two incident families: market component (oracle follows → liquidation) + specific component (oracle blind → bad debt) |
| 5 | 🟠 decision | v2 has no PARTIAL verdict and no indifference zone (EXIT when the expected loss beats the cost by $1) | `src/stacktrace/analyze.py` | reuse `risk.decide.best_fraction`; materiality threshold |
| 6 | 🟠 decision | The exit cost is measured before the market reacts; in the brief's example the pocket is already affected (exit at 11%) | `src/risk/decide.py`, `src/stacktrace/analyze.py` | show p\* as a range: calm pool and stressed pool (`exit_model.cost(f, pool_factor)` already exists) |
| 7 | 🟡 impact | The headline uses a 10% probability for a −30% USDe depeg in 7 days, while the Monte Carlo puts the whole severe-depeg family at ≈ 0.19%/week. Defensible only as "probability **given the alert**, entered by the manager" | `risk/scenarios.yaml` | say it in the front and on stage |
| 8 | 🟡 impact | v2 Monte Carlo: incidents and pockets are independent (v1 correlates through common parents) | `src/stacktrace/risk_engine.py` | reuse the v1 common-parent logic |
| 9 | 🟡 discovery | Feed quality: `age_seconds` is read but never compared with a sourced heartbeat / deviation threshold | `src/discovery/adapters/oracles.py` | curated heartbeat row + "stale feed" flag |
| 10 | 🟡 discovery | Exit route: the sUSDe → USDC leg is a 5 bp hypothesis, secondary pools are not in the graph | `risk/params.yaml` | discover the pools on-chain |

### 1.4 Not covered (stated as limits)
- xUSD / deUSD replay of November 2025 (needs an archive RPC); the framing note's plan B (10/10/2025) is done.
- Solana / Kamino, Base and the non-Morpho vaults of the RockawayX Dune list: Ethereum + Morpho Vault V2 only.
- Share of a protocol in the chain's TVL (brief scope): `tvl_usd` per node only.
- Exploit frequencies are hypotheses (the DeFiLlama hacks dataset is paid); the decision relies on p\*, which does not
  depend on them.

### 1.5 Questions still open for the Belem mentors
1. Decision horizon: 24 h or 7 days? (today 7 days, hypothesis in `risk/params.yaml`)
2. Pocket size V for a leveraged position: net capital ($53k) or gross value ($410k)?
3. The `lends` extension and the `collateralized_by` direction ("is collateral for", read backwards): accepted?
4. Does p\* speak to you more than a probability we would estimate ourselves?
5. Is there a reference source for exploit frequencies?

### 1.6 Procedure: refreshing the data at a new block
The cache is tied to the pinned block. As soon as an adapter makes a new call, regenerate it (needs `ETH_RPC_URL` in `.env`):
```bash
PYTHONPATH=src python -m risk.refresh                     # discovery + engine reads at the SAME (latest) block, pins it in config.yaml
PYTHONPATH=src python -m risk.run                         # offline: report + grid
PYTHONPATH=src python -m discovery.build_graph --offline  # must show 0 misses
python -m pytest                                          # golden tests compare against output/
git add data/cache output config.yaml && git commit
```
A public non-archive RPC only serves the last ~128 blocks: that is why `risk.refresh` does all the reads back to back.

---

## 2. Audit log (history)

Method: after each task, we reread **the whole project** against the instructions (`CLAUDE.md`) and the plan,
we fix things, then start again until the audit finds nothing important.

### Audit 1: after the first complete discovery
| Finding | Fix |
|---|---|
| Crash on `latestRoundData`: the return types were passed as arguments | `latest_round()` helper + feed tests |
| Evidence "`Contract.readTokens()`": the Pendle pool's name was not labelled | `PendleMarket` / `PendleMarketFactory` labels, and `isValidMarket` evidence generated by `ctx.ev` |
| Empty position detected **after** pointless calculations | check moved before the calculation |
| An API outage brought down the whole discovery | API tasks degrade gracefully (⚠ note); on-chain errors remain fatal |

### Audit 2: complete code vs instructions
| Finding | Fix |
|---|---|
| **Underestimated debt**: Morpho only updates interest at each interaction (`lastUpdate` 45 h old) | accrual via `IRM.borrowRateView` + `wTaylorCompounded`, like Morpho. Cross-check with the Morpho API: 0.0001% difference |
| `meta.tvl_usd` (shown in the contract example) missing | `valuation.py`: prices **only** derived from proven data. Cross-check: pool TVL $3.820M versus $3.820M for the Pendle API |
| `ctx` filtered errors by class **name**; signatures with tuples were not handled | typed exceptions; parsing of top-level types (tuples) |
| networkx under-used (stack instruction) | `inspect_graph.py`: tree, impact analysis (`ancestors`), acyclicity test |
| **Unsourced claim** about the meta-oracle's switch rule | rule rewritten from the official Steakhouse docs (URL in `meta.switch_rule_source`). No `issued_by` edge to Steakhouse: the factory is not published, so the link is not proven |
| Proxies checked for tokens and oracles only | check of **all** contracts; "not detected" ≠ "immutable" (`upgradeable: null`) |
| CRLF line endings (Windows) in the cache | writing in LF + `.gitattributes` |

### Audit 3: final compliance with `CLAUDE.md`
| Requirement | Status | Where |
|---|---|---|
| Python 3.11, web3.py, requests, networkx | ✅ | `requirements.txt`, `pyproject.toml` |
| Adapters in `src/discovery/adapters/` (`pendle`, `morpho`, `oracles`, `erc4626`…) + `build_graph.py` + `curated.yaml` | ✅ | directory tree |
| **All** RPC and API calls cached in `data/cache/`, offline demo | ✅ cache **at the provider level** (no way around it); offline replay byte-for-byte identical; tested | `rpc.py`, `http.py`, `test_position_a_offline.py` |
| Output = `graph.json` following the frozen contract | ✅ strict validator on every build and in tests | `validate.py` |
| Allowed nodes only | ✅ 8 types | `vocab.py` |
| Allowed edges only | ⚠ 6 types + the `lends` extension; `collateralized_by` = "is collateral for" reversed | decision to be made with the organisers (§1.5) |
| Every edge: `source` + concrete evidence | ✅ format checked by the validator (address + block for onchain, URL for api/curated) | `validate.py` |
| No address or endpoint from memory | ✅ every address is either **discovered on-chain** or taken from official docs with a URL (`config.yaml`, `curated.yaml`). Checklist for the team | `docs/VERIFY.md` |
| Teaching: concepts explained, small testable tasks | ✅ teaching docstrings in every module; 67 unit and integration tests | `docs/POSITION_A.md` |

### Audit 4: simulating a teammate (fresh clone, no `.env`, no network)
| Finding | Fix |
|---|---|
| In a deep folder, a cache file's path exceeded **260 characters** (Windows MAX_PATH): the cache became invisible | `\?\` prefix on Windows in `cache.py`; fresh clone re-tested: 67 tests green, 0 misses, `graph.json` byte-for-byte identical |
| `validate` crashed in a Windows console (cp1252 encoding); expected errors were shown as raw tracebacks | `console.utf8_console()` for the 3 CLIs; `✗ OfflineError: …` messages and exit code 2 |

### Audit 5: risk engine (parts 2 and 3) — steps (a) and (b)
| Finding | Fix |
|---|---|
| The public RPC only serves the last ~128 blocks: the new reads (Pendle simulations, Chainlink history) were impossible at pinned block #26161750 | single command `python -m risk.refresh` (discovery + engine reads at the SAME block, in 30 s); data refreshed at block #26162087, discovery code unchanged |
| DeFiLlama hacks dataset: **paid** endpoint (`pro-api.llama.fi/api/hacks`, official docs), web page blocked | no "invented" probability presented as calibrated: exploit frequencies are **displayed hypotheses**, the decision relies on **p\*** (independent of these frequencies), ×0.5/×2 sensitivity in the report |
| USDe depeg frequency calibrated on the on-chain history (1 episode below $0.99 in ~2.5 years, 7 min, −2.3%) but applied to much stronger severities | split into `usde_market_depeg` (frequency, severity AND duration fitted to the history) and `usde_severe_depeg` (distribution tail = explicit hypothesis) |
| S-TIME ignored that the PT converges to 1 at maturity (displayed loss = interest) | "matured" PT valuation at the AMM's implied rate → gain of ~$855 until maturity |
| Threshold test: I had written threshold = u_now / HF (wrong) | the engine was right: after the switch HF = HF₀ × USDe price, so threshold = 1/HF₀ = $0.9525 (same as POSITION_A.md) |
| Console summary: "ok" shown for a liquidatable but not liquidated position (Morpho exploit, zero collateral) | "liquidatable" label |

### Audit 6: "X-Ray" front and documentation
> Historical: this first static front (`web/`) was later replaced by the slide-deck front `front/` (commit `f61caa8`).

| Finding | Fix |
|---|---|
| SVG blur filter applied to ~75 shapes, then to the whole group of animated edges: heavy rendering, screenshots timing out | filter-free halo (wide transparent stroke) and CSS `drop-shadow` on nodes only |
| Stretched film grain (big visible pixels) | 128 px noise tile repeated at its actual size |
| Engine sentences in an inconsistent number format ("5,313 $", "1.6%") | `src/risk/fmt.py`: "$5,313", "1.6%" everywhere (report, traces, replay) |
| Rule template with two `{to}`, only one replaced in JS | `replaceAll` |
| Truncated technical names ("MorphoChainlin…") | short labels computed in Python (`view.json.display`: "Primary (fixed)", "Pendle PT/SY pool"…) |
| Challenge threshold 0.9925 hard-coded in the JS | computed by the engine (`replay.meta_oracle.challenge_price`) from the threshold read on-chain |
| Parameter table overflowing on mobile, "R" corner overlapping the 1st layer | `table-layout: fixed` + word breaking; layers shifted below the markers |
| Risk that `web/data/` lags behind the engine, or that a remote resource slips in | test: `web/data/*` must be identical to `output/*`, no URL loaded by HTML/CSS/JS |

### Final audit: compliance with the parts 2-3 prompt
| Requirement | Status |
|---|---|
| Brief read and summarised; parts 2 and 3 identified (Impact 30%, Decision 25%) | ✅ `docs/PARTS_2_3.md` |
| Discovery not modified (code) | ✅ code untouched. Data refreshed at block #26162087 using the documented procedure (non-archive RPC). `config.yaml`: 2 sourced entries added for the engine (RouterStatic, ENS ETH/USD) |
| No parameter without a status; 3 badges in the front | ✅ strict loader + test + `report.params` + sourced / on-chain / hypothesis badges |
| Morpho liquidation formula sourced | ✅ Morpho docs, URL and date |
| One rule per edge type, tested | ✅ `RULES` + `tests/risk/test_rules.py` |
| Faithful meta-oracle (threshold, challenge, healing, deviation formula) | ✅ on-chain parameters, Steakhouse-sourced formula, tests short / long / healing / chain halt / frozen feed |
| Exit cost on the real liquidity, on-chain version | ✅ RouterStatic at the same block, 16 sizes, revert = exit impossible |
| Prompt scenarios (USDe, EXCH, CUST, ORACLE, POOL, USDC, TIME) | ✅ 15 scenarios + a grid containing all the requested combinations |
| `risk_report.json` + `risk_grid.json` + validator + CLI | ✅ (name `risk_report.json` taken from the framing note instead of `risk.json`) |
| No synthetic score (not requested by the brief) | ✅ |
| POSITION_A.md thresholds recovered by the engine | ✅ test: $0.99253 and 1/HF = $0.9525 |
| Front: 6 features, offline, no build, `prefers-reduced-motion`, 375 px mobile | ✅ 6 screenshots in `docs/screens/` |
| Docs: PARTS_2_3, RISK_CONTRACT, DEMO, 2 chapters of the guide, README, AUDIT | ✅ |
| `pytest` green from start to finish | ✅ 97 tests at the time |

### Known limitations at the end of parts 2-3 (open ones are tracked in §1)
- **Vocabulary:** `lends` and the direction convention are awaiting official validation.
- **`value_usd`** = collateral at the oracle price (the net value is given in `meta.position.net_value_usd`). Definition to be confirmed with the downstream teams.
- **Unknown off-chain weights:** the Ethena → custodians / exchanges edges have `weight = 1.0` (upper bound, stated in the evidence). Ethena's lists are examples ("such as").
- **Meta-oracle:** link with the Steakhouse factory not proven on-chain.
- **Pendle TWAP feed:** the probes (`market()`, `twapDuration()`) have not been checked on a real contract (absent from position A).
- **Proxies:** only EIP-1167, EIP-1967 (+ beacon) and ZeppelinOS are detected. "Not detected" does not mean immutable.
- **Non-archive RPC:** refreshing the data requires `snapshot_block: latest`, then pinning the block (procedure in §1.6).
- **Root:** only Morpho Blue positions are supported as a starting point.
- **Freshness:** the feeds' `age_seconds` is provided, but not compared against a sourced heartbeat.
- **Risk engine:**
  - exploit frequencies are hypotheses (paid DeFiLlama dataset);
  - the decision relies on p\*, which does not depend on them.
- **Exit cost:**
  - computed "now", at the block's prices; in the middle of a crisis, the pool may already have deteriorated (see the S-POOL scenarios);
  - the sUSDe → USDC conversion is a hypothesis (5 basis points).
- **Monte Carlo correlations:** only through the graph's shared nodes (no statistical market correlation).
- **xUSD/deUSD replay of November 2025:** not done (archive RPC needed); plan B of the framing note (10/10/2025) is the one carried out.
