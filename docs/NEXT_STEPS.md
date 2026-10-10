# Next steps and ready-to-run prompts

## Where we are (updated after parts 2 and 3)
- **Part 1, discovery**: position A, 28 nodes, 45 edges, valid contract, replayable without network.
- **Parts 2 and 3, impact and decision** (`src/risk/`):
  - 15 scenarios and a price × duration grid;
  - a Monte Carlo and a replay of 10/10/2025;
  - p\* and the partial exit;
  - every figure with its status.
- **Front**: `front/` (deck on API v2, recorded responses offline).
- **126 tests** in total.

Prompts S1 to S8 further down remain valid (deepening the discovery). The new prompts R1 to R5 are just below.

### To validate as a team / with the Belem mentors (priority 1)
1. **Decision horizon**: 7 days (hypothesis). The framing note raises the question (24 h or 7 days?). Change `horizon_days` in `risk/params.yaml`.
2. **Pocket V = net capital** of the position ($53k), not the gross value ($410k). This is what makes p\* so low (×8 leverage). Agreed?
3. **Exploit frequencies**: order-of-magnitude hypotheses, because the DeFiLlama hacks dataset is paid. Do the mentors have a reference source?
4. **100% liquidation** (worst case, allowed by Morpho): sensitivity displayed from 50% to 100%. Realistic for them?
5. **Does p\* speak to them more than a probability estimated by us?** (question from the framing note)

### New prompts (after parts 2-3)
**R1 · Position B: USDC deposit in a curated Morpho vault** (framing note §4.1).
```text
Read CLAUDE.md, docs/PARTS_2_3.md and docs/CONTRACT.md. Goal: position B from the framing note, a USDC deposit in a curated
Morpho vault. The root becomes a vault: it allocates to N markets, each with its own collateral and oracle.
1. Explain to me in 10 lines what a MetaMorpho / Morpho Vault V2 vault is and how to read its allocations ON-CHAIN
   (exact functions from the Morpho docs, URL cited). WAIT for my approval of the chosen vault (e.g. the "Pendle
   Ecosystem USDC" vault already discovered, $61.6M).
2. Add a "vault" root adapter without breaking position A (new config in configs/, output in output/position_b/).
3. Adapt the risk engine: for a lender, the loss comes from the markets' unrecoverable debt (already computed by
   position.py). Reuse scenarios and Monte Carlo; p* on the depositor's pocket.
4. Tests, refresh, audit, front (position selector).
```
**R2 · "10-pocket book" view** (framing note bonus).
```text
Read CLAUDE.md and docs/PARTS_2_3.md. Goal: a book of 10 pockets of 10% each (position A, position B, then real
variants). Show the SHARED dependencies (e.g. USDe, Ethena, Chainlink) and the hidden concentration: what share of the book
falls if Ethena falls? Reuse the graph.json files and the engine; no invented data (pockets = real positions).
```
**R3 · Calibrating exploit frequencies on a public source.**
```text
Read CLAUDE.md and risk/params.yaml (events section). Goal: replace the "hypothesis" annual frequencies with a
sourced calibration. The DeFiLlama hacks dataset is paid (pro-api.llama.fi/api/hacks): find a public source
(rekt.news, a published annual report, a dated manual export), cite the URL and show me the method BEFORE coding. Status:
source + as_of, or we keep the hypothesis.
```
**R4 · xUSD / deUSD replay (November 2025).** You need an **archive** RPC (free Alchemy or Infura) to read the blocks from before the crisis.
```text
Read CLAUDE.md and src/risk/replay.py. Goal: the framing note's main replay, the cascade Stream xUSD → Elixir deUSD →
lending markets (November 2025). First find, in reliable (cited) sources, the dates, assets and Morpho markets
affected, and a vault that was exposed to them. WAIT for my validation. Then discover the graph of that vault at a block from BEFORE the
crisis (archive RPC in .env) and show that the tool finds the contagion path.
```
**R5 · Claude as judge** (framing note §6.5).
```text
Play the risk manager of Belem Capital (≈ $400M, zero liquidations since 2020). Read README.md, docs/PARTS_2_3.md and
output/risk_report.json. Tear our figures apart: find the 10 toughest criticisms of how defensible the impact and
the decision are, ranked by severity, with what it would take to answer them. Do not modify any file.
```

---

## Before parts 2-3 (still valid)
This document lists, in order:
1. what **you** need to do (check, decide);
2. the split between the 3 of us;
3. the next technical steps, each with a **prompt to copy-paste** into Claude Code.

---

## Step 0: for you to do (≈ 1 h, before any new code)
1. **Read** [`POSITION_A.md`](POSITION_A.md) and answer the 5 questions (the answers are at the bottom, folded).
2. **Tick** [`VERIFY.md`](VERIFY.md), at least section A (`config.yaml` inputs) and section B (`curated.yaml`).
3. **Decide with the organisers**:
   - the `lends` edge (market → lent asset) is an **extension** of the brief's 6 types: do we keep it?
   - `collateralized_by` (market → collateral) is "is collateral of" **read backwards**, to keep a single direction: OK?
   - the `position` root is not a node, but it is the `from` of an edge: OK for the downstream teams?
   - `value_usd` = value of the collateral at the oracle price (not net of the debt): is that what they expect?
   - the real borrower `0x03BA…`, or a hypothetical $1M position as in the brief's example?
4. Record the decisions in `CLAUDE.md` and `vocab.py` (one PR reviewed by the other 2).

## Procedure to know: regenerating the cache
The cache is tied to the pinned block. **As soon as an adapter makes a new call**, you must regenerate:
```bash
# 1. config.yaml → snapshot_block: latest; .env → ETH_RPC_URL=...
PYTHONPATH=src python -m discovery.build_graph            # online, prints "discovery at block #N"
# 2. config.yaml → snapshot_block: N   (copy the number)
PYTHONPATH=src python -m discovery.build_graph --offline  # must show 0 misses
python -m pytest                                          # the golden test compares against output/graph.json
git add data/cache output/graph.json config.yaml && git commit
```
To keep a clean cache, delete `data/cache/` before step 1. With a non-archive RPC, do steps 1 and 2 back to back (less than ~25 min).

## Split between the 3 of us (each with their own files, so no conflicts)
| Member | Role | Files only they modify |
|---|---|---|
| **1 · Foundation & demo** | orchestration, multi-position, CI, performance, demo | `build_graph.py`, `rpc.py`, `cache.py`, `http.py`, `inspect_graph.py`, `.github/` |
| **2 · Lending & pricing** | other Morpho markets, new oracles, vaults | `adapters/morpho.py`, `adapters/morpho_api.py`, `adapters/oracles.py`, `adapters/ens.py` |
| **3 · Assets & off-chain** | Pendle (liquidity), Ethena (weights), curated layer | `adapters/pendle.py`, `adapters/erc4626.py`, `adapters/erc20.py`, `adapters/curated.py`, `curated.yaml` |

Shared files (PR reviewed by the other 2): `vocab.py`, `graph.py`, `validate.py`, `ctx.py`, `config.yaml`, `CLAUDE.md`. Everyone tests in `tests/test_<their_domain>.py`.
Branch rule: `feature/<member>-<topic>` → PR to `main`.

---

## Technical steps and prompts

Each prompt is self-contained. Paste it as is into a Claude Code session opened on the repo.

### S1 · (Member 2) Generalise to other Morpho markets, and hunt down unknown oracles
**Goal:** prove that the module is not tailor-made for position A. **Check:** 0 `unresolved` nodes, or a handler added for each unknown type.
```text
Read CLAUDE.md in full. Goal: test the Discovery Module on Morpho Blue markets other than position A.
1. With the Morpho API (URL in config.yaml, calls via ctx.http so they are cached), list the 10 largest non-expired Ethereum
   markets whose collateral is a Pendle PT, an ERC-4626 (e.g. wstETH, sUSDe) or a plain token.
   Show me the list (marketId, collateral/loan, size) and WAIT for me to choose 3 markets.
2. For each chosen market, create a test config (configs/<name>.yaml, user: null, and ABOVE ALL
   discovery.output_file: output/<name>.json so as not to overwrite output/graph.json), then run
   `python -m discovery.build_graph --config configs/<name>.yaml`.
3. List all meta.unresolved=true nodes and 'unknown' oracles. For each one: read the verified source code on
   Etherscan (tell me the URL), explain the contract in 5 lines, then add a handler in adapters/oracles.py
   with a FakeCtx test in tests/. Do not invent any function name: probe them on-chain and cite the source.
4. In particular, check the UNVERIFIED probes of the Pendle TWAP feed (market(), twapDuration()) on a real contract.
5. Do an audit: valid JSON contract, evidence present, no address pulled from your memory. Update docs/VERIFY.md.
```

### S2 · (Member 3) Exit liquidity: how much does reselling our PT cost?
**Goal:** measure on-chain the price slippage if the position is liquidated on the Pendle pool. **Check:** a small simulated sale ≈ the AMM spot price; the impact grows with size.
```text
Read CLAUDE.md. Goal: add to the liquidity_venue node (Pendle pool) an ON-CHAIN measure of depth:
how much SY (then USDe) do we get by selling 10%, 50% and 100% of our position's collateral?
1. First explain to me what Pendle's RouterStatic is and which "preview" function lets us simulate
   a PT sale without a transaction. Look up the exact name and the address ONLY in the Pendle docs or the
   official deployments/1-core.json file, cite the URL, and add the address to config.yaml with its source.
2. Implement the call in adapters/pendle.py via ctx.call (so cached, at the pinned block), store in meta
   `exit_simulation`: size sold, SY received, average price, impact vs pt_price_implied_by_amm.
3. FakeCtx tests + update of the golden test; regenerate the cache (procedure in docs/NEXT_STEPS.md).
4. Final audit: no address without a source, valid JSON contract, docs/POSITION_A.md updated with the figures.
```

### S3 · (Member 3) Ethena's real weights: where are the reserves and the hedges?
**Goal:** replace the 1.0 weights (upper bound) with the published breakdown. **Check:** the weights within a category sum to about 1, each line has a URL and a date.
```text
Read CLAUDE.md. Goal: complete curated.yaml with the BREAKDOWN of USDe's reserve assets by custodian
and of the hedges by exchange, as published by Ethena (transparency pages / attestations).
1. Find the official source (Ethena's website or public API), give me the URL and the date of the figures, and
   WAIT for my validation of the source before writing anything.
2. Update curated.yaml: weight = share (0-1), weight_known: true, as_of = date of the figures. If a piece of data
   comes from an API, make the call via ctx.http (cached) in an adapters/ethena.py adapter rather than by hand.
3. Add a test that checks that the weights within a category sum to ~1.
4. Audit: no figure without a source, nothing extrapolated, docs/VERIFY.md section B up to date.
```

### S4 · (Member 2) The lenders: weight of the vaults in the market
**Goal:** give a real `weight` to the vault → market edge (the share of the market funded by that vault). **Check:** the sum of the vaults' shares ≤ 1.
```text
Read CLAUDE.md. Goal: for each vault that lends to our Morpho market, compute ON-CHAIN the share of the market's supply
that it represents: position(marketId, vault).supplyShares converted to assets / total supplied.
1. Explain the difference between a MetaMorpho v1 vault and a Morpho Vault V2 (adapters): for a V2, are the funds
   held by the vault itself or by an "adapter"? Check in the Morpho docs (cite the URL).
2. Read the right address (vault or adapter) via ctx.call, compute the share, put it in the weight of the
   vault --deployed_in--> market edge (and in meta), keeping the on-chain evidence in evidence.
3. FakeCtx tests, cache regeneration, audit (valid contract, no invented address).
```

### S5 · (Member 1) Multiple positions and continuous integration
**Goal:** `build_graph` processes a list of positions; GitHub Actions runs the tests offline on every push. **Check:** green CI on a PR, and one `output/<position>.json` file per position.
```text
Read CLAUDE.md. Goal 1: allow a list of positions in config.yaml (`positions:` key), produce
output/<slug>.json per position, while keeping output/graph.json for position A (compatibility).
Goal 2: add .github/workflows/tests.yml that installs Python 3.11, requirements.txt, and runs
`python -m pytest` in offline mode (STACKTRACE_OFFLINE=1, no RPC secret).
Constraints: do not break the JSON contract; tests added; explain each YAML block of the CI to me.
Final audit, then suggest the commit message to me.
```

### S6 · (Member 1) Performance: batching calls (Multicall3)
**Goal:** divide the number of RPC requests (≈ 190 today) without changing the graph. **Check:** `output/graph.json` identical before/after.
```text
Read CLAUDE.md. Goal: reduce the number of RPC requests during a refresh by batching the probes
through the Multicall3 contract. Find its address ONLY in an official source (cite the URL) and add it
to config.yaml with its source. The cache must stay at the provider level (rpc.py) and the graph produced must be
STRICTLY identical (compare output/graph.json before/after). Measure the number of network calls before/after.
Keep the code simple and commented: we are beginners.
```

### S7 · (Everyone) Preparing the demo (5 min sharp)
```text
Read CLAUDE.md, README.md and docs/POSITION_A.md. Prepare a 5-minute demo script for the jury:
1. Wi-Fi off → `build_graph --offline` (0 network calls);
2. `inspect_graph`: the tree;
3. `inspect_graph --evidence`: zoom on 3 pieces of evidence (one onchain, one api, one curated);
4. the meta-oracle case: why a short depeg does not liquidate, and a long one does (figures from POSITION_A.md);
5. `inspect_graph --impact binance`: off-chain propagation → position.
Write it in docs/DEMO.md with the exact commands (PowerShell AND bash) and what we say at each step.
Check that each command really works offline.
```

### S8 · (Member 2 or 3) Redeeming the PT at maturity
**Goal:** make explicit the redemption chain after 26/11/2026 (YT.redeemPY, exit into sUSDe, cooldown). **Check:** the added nodes and edges respect the vocabulary, otherwise we ask for an extension.
```text
Read CLAUDE.md. Goal: decide (with me) whether the YT and the redemption mechanism should appear in the graph.
1. Explain how a PT is redeemed after maturity at Pendle (which contract, which function), based on the
   Pendle docs (cite the URL) and the verified code of our position's YT (address in the PT's meta.yt).
2. Propose 2 modelling options compatible with vocab.py (no new type if possible) and WAIT for my choice.
3. Implement, test, regenerate the cache, audit.
```

---

## Ideas for later (not a priority)
- Add a position B on another protocol (e.g. Aave), i.e. a new root adapter.
- Export a JSON Schema of the contract for the teams that do not code in Python.
- Monitor the age of the feeds (`age_seconds` vs Chainlink heartbeat, which also needs a source).
