# Verification checklist (to be ticked by the team)

Project rule: **no address and no endpoint comes from Claude's memory.** Every value below was
**collected by Claude on 2026-10-10** from an official source ("Source" column) or **read on-chain**.
Your role: re-verify it yourselves and tick. An Etherscan page is found at `https://etherscan.io/address/<address>`
(tabs *Contract → Read Contract* and *Code*).

Legend: ✅ already proven automatically on every build · 🔎 to be checked by hand

## A. `config.yaml` entries (priority 1: everything else follows from them)
| ☐ | Item | Value | Source | Already proven? | How to verify |
|---|---|---|---|---|---|
| ☐ | Morpho Blue (singleton) | `0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb` | [Morpho docs: addresses](https://docs.morpho.org/developers/contracts/addresses/) | 🔎 | Etherscan: verified contract named `Morpho`; same address in the docs, **Ethereum** tab |
| ☐ | AdaptiveCurveIrm | `0x870aC11D48B15DB9a138Cf899d20F13F79Ba00BC` | same page | ✅ equal to `idToMarketParams(id).irm` | Morpho docs |
| ☐ | MorphoChainlinkOracleV2Factory | `0x3A7bB36Ee3f3eE32A60e9f2b33c1e5f2E83ad766` | same page | ✅ returns `isMorphoChainlinkOracleV2 = true` for our 2 sub-oracles | Morpho docs + Etherscan |
| ☐ | ENS Registry | `0x00000000000C2E074eC69A0dFb2997BA6C7d2e1e` | [ENS docs: deployments](https://docs.ens.domains/learn/deployments) | ✅ resolves `usde-usd.data.eth` and `usdc-usd.data.eth` | ENS docs |
| ☐ | `market_id` | `0x5613b170…c46cb05` | Morpho API (search "PT-sUSDE") | ✅ hash of the parameters recomputed | Morpho app: the market page must show PT-sUSDE-26NOV2026 / USDC, LLTV 91.5% |
| ☐ | `user` (borrower) | `0x03BAbEB24619902253FDB0D5675A816879115d98` | Morpho API (top borrowers, public address) | ✅ `position()` not empty | **Team decision:** keep this real address, or set `user: null` (hypothetical position, `value_usd_override: 1000000`) |
| ☐ | Morpho GraphQL API | `https://api.morpho.org/graphql` | [Morpho API docs](https://docs.morpho.org/developers/api/get-started/) | — | docs |
| ☐ | Pendle API | `https://api-v2.pendle.finance/core` (`GET /v2/markets/all`) | [Pendle API docs](https://docs.pendle.finance/pendle-v2-dev/Backend/ApiOverview) | ✅ the pool found is re-proven on-chain | docs (limits: 200 CU/min) |
| ☐ | Example public RPC (`.env.example`) | PublicNode | [main.net guide](https://main.net/guides/ethereum-mainnet-rpc-public-vs-private) | — | **Use your own RPC instead** (Alchemy/Infura); for an old block, you need an archive node |

## A bis. `config.yaml` → `curator_books.rockawayx` (curator view, backend v2)
Located by the Morpho API (`userByAddress` of `0x4F87…0545`) and proven on-chain (`name()`, `balanceOf`) at block
#26162868 (`docs/api_examples/pockets.json`). The curator itself is re-read on-chain (`curator()`) at every analysis.
**Check each one against the RockawayX Dune dashboard shared by Belem**, and add the vaults that are missing.
| ☐ | Vault | Address | How to verify |
|---|---|---|---|
| ☐ | Belem RWA EURCV | `0xD6d4b804014EF27836dBe9f8f6Bf6c71251548Ec` | Dune dashboard + Etherscan `name()` + Morpho app vault page (curator) |
| ☐ | RockawayX f(x) Protocol Ecosystem USDC | `0x2cA22cb25558fa2018ecb1CE4eD8AF92Ee7ea423` | same |
| ☐ | RockawayX USDC Yield | `0xE0181090c22579B6A217f1522cbf8c9f1F0C1965` | same |
| ☐ | RockawayX wETH | `0x64C18DCC4Ccb3b8D27877a4aeBB4C3126CB39cB9` | same |
| ☐ | RockawayX Tori Ecosystem | `0x3BD9AdAE6643dDcddD02746b8B60075E56DF9478` | same |
| ☐ | RockawayX Confidential RWA USDC | `0xc207d3f66537D7F66456808379A0E560cF20Da36` | copied from the Dune list ("ethereum · morpho"): Etherscan `name()` + Morpho app |
| ☐ | Huma USDC Main | `0x8aC91877b93330f52b2979a31a4879506021475c` | same |
| ☐ | RockawayX NUVA Ecosystem | `0x93e0F9d502eEfce8D34924ab3478C7EA0CBC5a2E` | same |
| ☐ | Other Dune vaults | — | out of scope today: Solana (Kamino), Base, BSC, Sei, Pharos, Citrea, and Ethereum vaults on Upshift / Ember / Accountable / Midas |

## B. `curated.yaml` (the off-chain part)
| ☐ | Claim | Source | How to verify |
|---|---|---|---|
| ☐ | USDe = `0x4c9edd58…e68b3`, sUSDe = `0x9d39a5de…a3497` (Ethena) | [Ethena Key Addresses](https://docs.ethena.fi/solution-design/key-addresses) | ✅ we also **discovered them on-chain** (SY → sUSDe → USDe); check that they appear on the page |
| ☐ | USDC = `0xA0b86991…6eB48` (Circle) | [Circle: USDC addresses](https://developers.circle.com/stablecoins/usdc-contract-addresses) | "Ethereum" row |
| ☐ | `yieldContractFactoryV6` = `0x3E6EBa46…E4637`, `marketFactoryV6` = `0x6d247b1c…EB29A9f` (Pendle) | [Pendle deployments 1-core.json](https://github.com/pendle-finance/pendle-core-v2-public/blob/main/deployments/1-core.json) | ✅ these are the `factory()` values read on-chain on the PT and the pool |
| ☐ | Ethena OES custodians: Copper, Ceffu, Fireblocks ("such as") | [Ethena OES in detail](https://docs.ethena.fi/backing-custody-and-security/overview/off-exchange-settlement-in-detail) | re-read the sentence; look for a more complete list |
| ☐ | Hedge exchanges: Binance, Bybit, Bitget, Deribit, OKX ("such as") | [Ethena exchange failure risk](https://docs.ethena.fi/solution-overview/risks/exchange-failure-risk) | same + **breakdown** in Ethena's transparency dashboards (next step) |
| ☐ | Chainlink feeds = ENS domain `data.eth` | [Chainlink: ENS](https://docs.chain.link/data-feeds/ens) | — |

## C. Function names used by the adapters
They were all called successfully at the pinned block. Those marked ⚖ were also **cross-checked numerically** against an independent API.
| ☐ | Contract | Functions | Where to verify |
|---|---|---|---|
| ☐ | Morpho Blue | `idToMarketParams(bytes32)`, `market(bytes32)` ⚖, `position(bytes32,address)` ⚖ | Etherscan Read Contract. Field order cross-checked against the Morpho API (exact collateral, debt within 0.0001%) |
| ☐ | AdaptiveCurveIrm | `borrowRateView(MarketParams, Market)` ⚖ | Etherscan / Morpho docs. Formulas `wTaylorCompounded` and virtual shares (1e6): Morpho Blue code (`MathLib`, `SharesMathLib`) |
| ☐ | MetaOracleDeviationTimelock (`0xF8b2…1b08`, clone of `0x9B46…de5B`) | `primaryOracle`, `backupOracle`, `currentOracle`, `deviationThreshold`, `getDeviation`, `challengeTimelockDuration`, `healingTimelockDuration`, `isChallenged`, `isHealing`, `primaryPrice`, `backupPrice` | ABI on Etherscan (implementation) + [Steakhouse docs](https://steakhouse.financial/docs/products/infrastructure/metaoracle) + [source code](https://github.com/Steakhouse-Financial/steakhouse-oracles/blob/36385342274f71999b66c79c4475234a39ba9a01/src/MetaOracleDeviationTimelock.sol) |
| ☐ | MorphoChainlinkOracleV2 | `BASE_FEED_1/2`, `QUOTE_FEED_1/2`, `BASE_VAULT`, `QUOTE_VAULT`, `*_VAULT_CONVERSION_SAMPLE`, `SCALE_FACTOR`, `price` | ✅ recomputed price = `price()` |
| ☐ | PendleSparkLinearDiscountOracle (`0xA572…cD35`) | `PT`, `maturity`, `baseDiscountPerYear`, `latestRoundData` | Etherscan (verified contract name); ✅ formula recomputed |
| ☐ | DummyFeed (`0xc386…973D`) | `latestRoundData`, `decimals`, `description` | Etherscan: deployed by the address labelled "Steakhouse: Deployer" |
| ☐ | Chainlink proxy USDe/USD (`0xa569…F961`) | `aggregator`, `phaseId`, `description`, `latestRoundData`, `version`, `owner` | ✅ ENS; Chainlink page of the USDe/USD feed |
| ☐ | Pendle PT / YT / SY | `SY`, `YT`, `expiry`, `isExpired`, `factory`; `yieldToken`, `assetInfo`, `exchangeRate`, `getTokensIn`, `getTokensOut`, `paused`, `owner` | Etherscan Read Contract |
| ☐ | PendleMarket + factory | `readTokens`, `factory`, `expiry`, `totalSupply`, `_storage` ⚖, `isValidMarket` | **`_storage()`: field order** cross-checked against the Pendle API (exact PT/SY reserves, identical implied rate); to be confirmed in the `PendleMarketV3` code |
| ☐ | sUSDe (ERC-4626) | `asset`, `convertToAssets`, `totalAssets`, `cooldownDuration`, `owner` | Etherscan |
| ☐ | ENS | `resolver(bytes32)`, `addr(bytes32)` | ENS docs |
| ☐ | **Not verified**: Pendle TWAP feed | `market()`, `twapDuration()` (probes) | **absent from position A**: find a Morpho market that uses it and confirm (see `NEXT_STEPS.md`) |

## C bis. Risk engine (parts 2-3)
| ☐ | Item | Value / function | Source | How to verify |
|---|---|---|---|---|
| ☐ | Pendle RouterStatic | `0x263833d47eA3fA4a30f269323aba6a107f9eB14C` | [Pendle deployments 1-core.json](https://github.com/pendle-finance/pendle-core-v2-public/blob/main/deployments/1-core.json) (key `routerStatic`) | ✅ called on-chain successfully; check the key in the file |
| ☐ | simulation function | `swapExactPtForSyStatic(address,uint256) → (netSyOut, netSyFee, priceImpact, exchangeRateAfter)` | [IPActionMarketCoreStatic.sol, @pendle/core-v2@6.6.1](https://cdn.jsdelivr.net/npm/@pendle/core-v2@6.6.1/contracts/interfaces/IPActionMarketCoreStatic.sol) | ✅ 1 PT → 0.7934 SY × 1.2523 ≈ 0.9937 USDe ≈ AMM implied price |
| ☐ | liquidation bonus formula | LIF = min(1.15, 1/(0.3·LLTV + 0.7)) | [Morpho docs: liquidation](https://docs.morpho.org/learn/concepts/liquidation/) | re-read the formula and the constants |
| ☐ | meta-oracle rule | deviation = \|p − b\| / average; challenge / acceptChallenge / heal permissionless | [Steakhouse MetaOracle docs](https://steakhouse.financial/docs/products/infrastructure/metaoracle) | re-read, then read the contract's verified source code |
| ☐ | Chainlink history | `phaseId()`, `phaseAggregators(uint16)`, `latestRound()`, `getRoundData(uint80)` | Chainlink docs (historical data) | ✅ 960 rounds read; check a random round on Etherscan |
| ☐ | ETH/USD (gas) | ENS `eth-usd.data.eth` | [Chainlink ENS docs](https://docs.chain.link/data-feeds/ens) | ✅ resolved on-chain |
| ☐ | 10/10/2025 episode | USDe $0.65 on Binance, ~40 min | [21Shares](https://www.21shares.com/it-eu/insights/why-did-ethenas-stablecoin-remain-stable-onchain-but-depegged-on-binance) | re-read the article; look for a 2nd source (Binance, Ethena) |
| ☐ | all hypotheses | `risk/params.yaml` (`hypothesis: true`) and `risk/scenarios.yaml` | — | re-read them as a team and discuss them with the mentors |

## D. Facts collected by Claude outside the pipeline (for context, not in the graph)
- The contracts `0xA572…` and `0xc386…` carry the verified names `PendleSparkLinearDiscountOracle` and `DummyFeed` on Etherscan.
- The meta-oracle is an EIP-1167 clone of `0x9B46…`, verified contract `MetaOracleDeviationTimelock`. The Steakhouse factory **has no published address** in the docs → link not proven.
- The market was the largest non-expired PT-sUSDe/USDC market in the Morpho API on 2026-10-10 (≈ $7.76M supplied).
