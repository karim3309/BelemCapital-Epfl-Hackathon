# Position A: what we discovered, explained simply

All figures are read **on-chain at block #26162087** (2026-10-10 12:39 UTC), unless stated otherwise.
Every claim in this document matches an edge or a `meta` in [`output/graph.json`](../output/graph.json).
You can find it again with:

```bash
PYTHONPATH=src python -m discovery.inspect_graph --evidence
```

## In 5 lines
1. We deposited **413,030 PT-sUSDE-26NOV2026** on a **Morpho Blue** market, and we owe **357,217 USDC**.
2. Our debt/collateral ratio is **87.2%**, against a limit (LLTV) of **91.5%**. The health factor is **1.050**: a **4.75%** drop in the price given by the oracle makes us liquidatable.
3. The oracle is a **meta-oracle**. In normal times, it gives a price **set by a formula** (linear discount of 6%/year, which ignores the market) and assumes USDe = USDC = 1. If the market price deviates by more than 0.75% for 16 h, it can **switch** to an oracle that follows the market price of USDe (Chainlink).
4. At the very bottom of the stack, the PT is worth 1 USDe at maturity (26 Nov 2026, in 46.5 days). USDe relies on Ethena, that is, reserves held by custodians and shorts on centralised exchanges. **None of this is on-chain.**
5. To exit the PT before maturity, you have to go through a Pendle pool of **$3.8M**. That is small compared to the **$7.0M borrowed** on this market.

---

## Layer by layer (from the position down to the bottom of the stack)

### 0. The position · `morpho:0x5613…:0x03BA…`
- **What it is:** a row in Morpho's registry, for the (market, borrower) pair.
- **Read:** `Morpho.position(id, user)` returns `(supplyShares 0, borrowShares 355,505,047,827,188,788, collateral 413,030.32 PT)`.
- **Up-to-date debt:** the debt shares are converted into USDC **including accrued interest**. Morpho only updates its totals at each interaction (`lastUpdate`); here, the last one dates back about 45 h. So we add the interest ourselves, just like Morpho: `IRM.borrowRateView` gives the per-second rate, to which we apply `wTaylorCompounded`. Without this, the debt would be underestimated by 67 USDC on our position (1,322 USDC on the whole market). Cross-check: our calculation and the Morpho API differ by **0.0001%**.
- **`value_usd = $409,819.73`**: value of the collateral at the oracle price, × the USDC price according to Chainlink (USDC/USD = 0.99987, feed found via ENS `usdc-usd.data.eth`). Net value at the oracle price (collateral − debt): ~$52,650; at the AMM market price: $53,133.

### 1. The lending market · `morpho_market_5613b170`
- **What it is:** one of the isolated markets of the single Morpho Blue contract. It is defined by 5 frozen parameters: USDC lent, PT as collateral, oracle, interest rate model (IRM) and LLTV of 91.5%.
- **Proof of identity:** we recompute `keccak256(abi.encode(MarketParams))` and land exactly on the requested ID.
- **State:** 7.76M USDC supplied, 6.99M borrowed, i.e. **90.1% utilization**. Only 0.76M USDC are available. The borrow rate is **3.74%/year**. The IRM is indeed the official AdaptiveCurveIrm: its address matches the Morpho docs.
- **Who lends:** the **Pendle Ecosystem USDC** vault (Morpho Vault V2, $61.6M under management), according to the Morpho API. Its name, asset and curator are re-read on-chain.
- **Why it is a dependency:** if the lenders withdraw their funds, utilization rises and the adaptive rate model pushes up our borrowing cost. If the collateral loses value, we get liquidated.

### 2. The oracle: the heart of the matter
Morpho calls `oracle.price()` and **blindly trusts** it. Taking the oracle apart means knowing *when* and *how* we can be liquidated.

```
oracle_meta_f8b29e  MetaOracleDeviationTimelock (Steakhouse) — EIP-1167 clone, immutable — HYBRID mode
├── PRIMARY (active): oracle_morpho_v2_8fca98  MorphoChainlinkOracleV2 — FIXED mode
│     price = SCALE × BASE_FEED_1                        (the 5 other slots are empty = 1)
│     └── BASE_FEED_1 = PendleSparkLinearDiscountOracle: PT_price = 1 − 6%/year × time remaining
└── FALLBACK: oracle_morpho_v2_e2f4cf  MorphoChainlinkOracleV2 — MARKET mode
      price = SCALE × BASE_FEED_1 × BASE_FEED_2 / QUOTE_FEED_1
      ├── BASE_FEED_1 = the same linear discount (fixed)
      ├── BASE_FEED_2 = Chainlink USDe / USD  (proven via ENS usde-usd.data.eth)  → $0.99960
      └── QUOTE_FEED_1 = DummyFeed: always returns 1 (used to align decimals) → USDC = 1 hard-coded
```

What we **proved**:
- Both sub-oracles were created by the official Morpho factory (`isMorphoChainlinkOracleV2 = true`).
- Their price, **recomputed** from the building blocks, is **identical** to `price()`.
- The linear discount formula, recomputed, lands on the feed's value.
- The "Dummy" feed is constant: `roundId = 1` and `updatedAt` equals the block timestamp. Nobody updates it.

**Fixed price, internal rate, market price: why it changes everything.**
- **Primary (fixed).** The PT price depends only on time: 0.99235 today, 1.0000 on 26 November. It implicitly assumes **1 USDe = 1 USDC**. A USDe depeg does **not** move it.
- **Fallback (market).** It multiplies the same discount by the **real** USDe price (Chainlink). A depeg lowers it by the same amount.
- **The switch rule.** It is sourced from the [Steakhouse docs](https://steakhouse.financial/docs/products/infrastructure/metaoracle), and its parameters are read on-chain. The deviation is |primary − fallback| / average. Threshold = **0.75%**. Anyone can call `challenge()`. If the deviation still holds after **57,600 s (16 h)**, `acceptChallenge()` switches to the fallback. Going back to the primary happens after **86,400 s (24 h)** of reconvergence. Current deviation: 0.04%.
- **Internal rate.** sUSDe is worth **1.25234 USDe** according to `convertToAssets`. This is internal accounting that only goes up, not a market price. Here, neither oracle uses it: the PT is directly denominated in USDe (`SY.assetInfo()` → USDe).

### Depeg scenarios (computed with the block's values)
The fallback price is roughly "primary price × USDe price". From this we derive:

| USDe market price | What happens |
|---|---|
| ≥ $0.9925 | Deviation < 0.75%: no switch possible. Fixed price, nothing moves. |
| between $0.9525 and $0.9925 | A `challenge()` is possible. If the depeg lasts more than 16 h, the oracle switches to the market. Our health factor drops, but we are **not liquidatable**. |
| < $0.9525 **for more than 16 h** | After the switch, the price falls below 0.9452 USDC/PT (= current price / HF): **we are liquidatable**. Liquidators take our PT with a bonus. |
| < $0.9525 **for less than 16 h** | The price stays fixed, we are not liquidated. But during this window, anyone can buy cheap PT and borrow USDC at the fixed price. **The lenders** (including the Pendle Ecosystem USDC vault) carry the risk. |

In other words, the meta-oracle **absorbs short depegs** (good for the borrower, a risk for the lender) and **follows long depegs** (liquidations). The 16 h delay is the central risk parameter of this position.

Also worth noting:
- **Without a depeg**, the discount makes the PT price rise by +0.77% until maturity, while the debt grows by about 0.48% over the same period (3.74%/year). So the health factor improves slightly until 26 November, at a constant rate. But the rate is adaptive and utilization is at 90%: keep an eye on it.
- The oracle price (0.99235) is **0.14% below** the implied price of the Pendle pool (0.99379 USDe). The oracle is a bit more cautious than the market today.

### 3. The PT and its AMM pool (Pendle) · `pt_susde_26nov2026`, `pendle_plp_susde_26nov2026`
- **PT** (Principal Token): it is worth 1 unit of the SY's accounting asset (**USDe**, `SY.assetInfo()`) at the **26/11/2026** maturity. Analogy: a zero-coupon bond. Its factory `0x3E6E…` is `yieldContractFactoryV6` in Pendle's official deployments.
- **SY-sUSDE**: Pendle's standard wrapper. `yieldToken()` gives sUSDe. You can enter it with USDe or sUSDe, but you exit it **in sUSDe only** (`getTokensOut`). Redeeming the PT therefore gives sUSDe, which must then be unstaked for 1 day (cooldown) to get USDe.
- **Pendle pool:** it was located via the Pendle API, then **proven on-chain**: `readTokens()` does contain our PT, and the `marketFactoryV6` answers `isValidMarket = true`. Reserves: 971,271 PT and 2,282,035 SY, for a TVL of **$3.82M** (the Pendle API also gives $3.82M). Implied rate: 5.01%.
- **Why it is a dependency:** a liquidator who seizes our PT must resell them on this pool, or wait 46 days for maturity. A shallow pool slows down liquidations and can create bad debt.

### 4. The yield source and its issuer (Ethena) · `susde`, `usde`, `ethena_labs`
- **sUSDe:** ERC-4626 vault. 1 share = 1.25234 USDe; 1.21B USDe deposited; withdrawal cooldown of **86,400 s (1 day)**, read on-chain.
- **USDe:** Ethena's synthetic dollar (4.78B in circulation). It is backed by crypto collateral hedged with **short positions on perpetual contracts**.
- **Issuer:** the USDe and sUSDe addresses match Ethena's official "Key Addresses" page (curated link).
- **What is NOT on-chain (→ `curated.yaml`):**
  - the "Off-Exchange Settlement" custodians cited by Ethena: **Copper, Ceffu, Fireblocks**;
  - the hedging exchanges cited: **Binance, Bybit, Bitget, Deribit, OKX**.

  Both lists are introduced by "such as" in Ethena's docs: they are examples, not necessarily the complete list. The split is **not** known to our graph (weight 1.0 = upper bound). It can be found in Ethena's transparency dashboards: that is a next step.

### 5. The chain · `ethereum`
14 contracts have code at block #26162087 (`eth_getCode`), on `eth_chainId = 1`.

### Beside the stack: USDC · `usdc`, `circle`
It is the debt asset. USDC is an **upgradeable proxy** (ZeppelinOS slot read on-chain): Circle can change its code. The address matches Circle's official page.

---

## Open questions (genuine unknowns, not assumptions)
- Which factory deployed this meta-oracle? The Steakhouse docs do not publish its address, so the link with Steakhouse is **not proven on-chain** (`meta.design_note`).
- What is the actual split of Ethena's reserves and hedges? It is on the transparency dashboards, but not curated yet.
- What is the actual depth for a liquidation? We would need to simulate a PT sale on the pool (price slippage). That is another team's job, but `reserve_pt` and `reserve_sy` give them the basis.

<details>
<summary><b>Answers to the 5 comprehension questions</b> (try first!)</summary>

1. **USDe at $0.92 with a linear discount and no USDe feed?** In a market with a *purely* fixed oracle, we are not liquidated: the price does not move. The lenders are the ones who lose if USDe does not recover (bad debt at maturity), and they lose earlier if opportunists borrow against PT bought at a discount. **On our real market**, there is the meta-oracle: after 16 h of deviation, it switches to the market price. At $0.92 (< $0.9525), we become liquidatable.
2. **Proving the parameters without the Morpho app:** we recompute `keccak256(abi.encode(loanToken, collateralToken, oracle, irm, lltv))` from `idToMarketParams(id)`, and check that we land on `id` (field `meta.market_id_check`).
3. **1 PT at maturity:** it is worth 1 USDe (the SY's accounting asset), paid in **SY**, exchangeable for **sUSDe** (the only exit token). Then a 1-day cooldown is needed to get USDe. "1 PT = 1 sUSDe" is wrong, because 1 sUSDe is already worth 1.25 USDe.
4. **Not provable on-chain:** where Ethena's reserves are (custodians) and on which exchanges its hedges are; or who is behind an address (e.g. "this address is Circle's USDC"). Possible evidence: the official URL and the date it was recorded (`evidence_url`, `as_of` in `curated.yaml`).
5. **The shallow pool, even though the oracle does not read it:** liquidators must resell the seized PT. If they cannot do so without a big loss, they do not liquidate, or too late, and bad debt piles up.
</details>
