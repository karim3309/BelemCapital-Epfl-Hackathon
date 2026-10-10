# Checklist de vérification (à cocher par l'équipe)

Règle du projet : **aucune adresse ni aucun endpoint ne vient de la mémoire de Claude.** Chaque valeur ci-dessous a été
**relevée par Claude le 2026-10-10** dans une source officielle (colonne « Source ») ou **lue on-chain**.
Votre rôle : la re-vérifier vous-mêmes et cocher. Une page Etherscan se consulte sous `https://etherscan.io/address/<adresse>`
(onglets *Contract → Read Contract* et *Code*).

Légende : ✅ déjà prouvé automatiquement à chaque build · 🔎 à vérifier à la main

## A. Entrées de `config.yaml` (priorité 1 : tout le reste en découle)
| ☐ | Élément | Valeur | Source | Déjà prouvé ? | Comment vérifier |
|---|---|---|---|---|---|
| ☐ | Morpho Blue (singleton) | `0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb` | [doc Morpho : adresses](https://docs.morpho.org/developers/contracts/addresses/) | 🔎 | Etherscan : contrat vérifié nommé `Morpho` ; même adresse dans la doc, onglet **Ethereum** |
| ☐ | AdaptiveCurveIrm | `0x870aC11D48B15DB9a138Cf899d20F13F79Ba00BC` | même page | ✅ égal à `idToMarketParams(id).irm` | doc Morpho |
| ☐ | MorphoChainlinkOracleV2Factory | `0x3A7bB36Ee3f3eE32A60e9f2b33c1e5f2E83ad766` | même page | ✅ répond `isMorphoChainlinkOracleV2 = true` pour nos 2 sous-oracles | doc Morpho + Etherscan |
| ☐ | ENS Registry | `0x00000000000C2E074eC69A0dFb2997BA6C7d2e1e` | [doc ENS : déploiements](https://docs.ens.domains/learn/deployments) | ✅ résout `usde-usd.data.eth` et `usdc-usd.data.eth` | doc ENS |
| ☐ | `market_id` | `0x5613b170…c46cb05` | API Morpho (recherche « PT-sUSDE ») | ✅ hash des paramètres recalculé | app Morpho : la page du marché doit afficher PT-sUSDE-26NOV2026 / USDC, LLTV 91,5 % |
| ☐ | `user` (emprunteur) | `0x03BAbEB24619902253FDB0D5675A816879115d98` | API Morpho (top emprunteurs, adresse publique) | ✅ `position()` non vide | **Décision d'équipe :** garder cette adresse réelle, ou mettre `user: null` (position hypothétique, `value_usd_override: 1000000`) |
| ☐ | API Morpho GraphQL | `https://api.morpho.org/graphql` | [doc API Morpho](https://docs.morpho.org/developers/api/get-started/) | — | doc |
| ☐ | API Pendle | `https://api-v2.pendle.finance/core` (`GET /v2/markets/all`) | [doc API Pendle](https://docs.pendle.finance/pendle-v2-dev/Backend/ApiOverview) | ✅ le pool trouvé est re-prouvé on-chain | doc (limites : 200 CU/min) |
| ☐ | RPC public d'exemple (`.env.example`) | PublicNode | [guide main.net](https://main.net/guides/ethereum-mainnet-rpc-public-vs-private) | — | **Prenez plutôt votre propre RPC** (Alchemy/Infura) ; pour un bloc ancien, il faut un nœud archive |

## B. `curated.yaml` (le hors-chaîne)
| ☐ | Affirmation | Source | Comment vérifier |
|---|---|---|---|
| ☐ | USDe = `0x4c9edd58…e68b3`, sUSDe = `0x9d39a5de…a3497` (Ethena) | [Ethena Key Addresses](https://docs.ethena.fi/solution-design/key-addresses) | ✅ on les a aussi **découverts on-chain** (SY → sUSDe → USDe) ; vérifiez qu'ils figurent dans la page |
| ☐ | USDC = `0xA0b86991…6eB48` (Circle) | [Circle : adresses USDC](https://developers.circle.com/stablecoins/usdc-contract-addresses) | ligne « Ethereum » |
| ☐ | `yieldContractFactoryV6` = `0x3E6EBa46…E4637`, `marketFactoryV6` = `0x6d247b1c…EB29A9f` (Pendle) | [déploiements Pendle 1-core.json](https://github.com/pendle-finance/pendle-core-v2-public/blob/main/deployments/1-core.json) | ✅ ce sont les `factory()` lues on-chain sur le PT et le pool |
| ☐ | Custodians OES d'Ethena : Copper, Ceffu, Fireblocks (« such as ») | [Ethena OES in detail](https://docs.ethena.fi/backing-custody-and-security/overview/off-exchange-settlement-in-detail) | relire la phrase ; chercher une liste plus complète |
| ☐ | Exchanges de hedge : Binance, Bybit, Bitget, Deribit, OKX (« such as ») | [Ethena exchange failure risk](https://docs.ethena.fi/solution-overview/risks/exchange-failure-risk) | idem + **répartition** dans les dashboards de transparence Ethena (étape suivante) |
| ☐ | Feeds Chainlink = domaine ENS `data.eth` | [Chainlink : ENS](https://docs.chain.link/data-feeds/ens) | — |

## C. Noms de fonctions utilisés par les adaptateurs
Ils ont tous été appelés avec succès au bloc figé. Ceux marqués ⚖ ont en plus été **recoupés numériquement** avec une API indépendante.
| ☐ | Contrat | Fonctions | Où vérifier |
|---|---|---|---|
| ☐ | Morpho Blue | `idToMarketParams(bytes32)`, `market(bytes32)` ⚖, `position(bytes32,address)` ⚖ | Etherscan Read Contract. Ordre des champs recoupé avec l'API Morpho (collatéral exact, dette à 0,0001 %) |
| ☐ | AdaptiveCurveIrm | `borrowRateView(MarketParams, Market)` ⚖ | Etherscan / doc Morpho. Formules `wTaylorCompounded` et parts virtuelles (1e6) : code Morpho Blue (`MathLib`, `SharesMathLib`) |
| ☐ | MetaOracleDeviationTimelock (`0xF8b2…1b08`, clone de `0x9B46…de5B`) | `primaryOracle`, `backupOracle`, `currentOracle`, `deviationThreshold`, `getDeviation`, `challengeTimelockDuration`, `healingTimelockDuration`, `isChallenged`, `isHealing`, `primaryPrice`, `backupPrice` | ABI sur Etherscan (implémentation) + [doc Steakhouse](https://steakhouse.financial/docs/products/infrastructure/metaoracle) + [code source](https://github.com/Steakhouse-Financial/steakhouse-oracles/blob/36385342274f71999b66c79c4475234a39ba9a01/src/MetaOracleDeviationTimelock.sol) |
| ☐ | MorphoChainlinkOracleV2 | `BASE_FEED_1/2`, `QUOTE_FEED_1/2`, `BASE_VAULT`, `QUOTE_VAULT`, `*_VAULT_CONVERSION_SAMPLE`, `SCALE_FACTOR`, `price` | ✅ prix recalculé = `price()` |
| ☐ | PendleSparkLinearDiscountOracle (`0xA572…cD35`) | `PT`, `maturity`, `baseDiscountPerYear`, `latestRoundData` | Etherscan (nom de contrat vérifié) ; ✅ formule recalculée |
| ☐ | DummyFeed (`0xc386…973D`) | `latestRoundData`, `decimals`, `description` | Etherscan : déployé par l'adresse étiquetée « Steakhouse: Deployer » |
| ☐ | Chainlink proxy USDe/USD (`0xa569…F961`) | `aggregator`, `phaseId`, `description`, `latestRoundData`, `version`, `owner` | ✅ ENS ; page Chainlink du feed USDe/USD |
| ☐ | PT / YT / SY Pendle | `SY`, `YT`, `expiry`, `isExpired`, `factory` ; `yieldToken`, `assetInfo`, `exchangeRate`, `getTokensIn`, `getTokensOut`, `paused`, `owner` | Etherscan Read Contract |
| ☐ | PendleMarket + factory | `readTokens`, `factory`, `expiry`, `totalSupply`, `_storage` ⚖, `isValidMarket` | **`_storage()` : ordre des champs** recoupé avec l'API Pendle (réserves PT/SY exactes, taux implicite identique) ; à confirmer dans le code `PendleMarketV3` |
| ☐ | sUSDe (ERC-4626) | `asset`, `convertToAssets`, `totalAssets`, `cooldownDuration`, `owner` | Etherscan |
| ☐ | ENS | `resolver(bytes32)`, `addr(bytes32)` | doc ENS |
| ☐ | **Non vérifié** : feed TWAP Pendle | `market()`, `twapDuration()` (sondes) | **absent de la position A** : trouver un marché Morpho qui l'utilise et confirmer (voir `NEXT_STEPS.md`) |

## D. Faits relevés par Claude hors pipeline (pour le contexte, pas dans le graphe)
- Les contrats `0xA572…` et `0xc386…` portent les noms vérifiés `PendleSparkLinearDiscountOracle` et `DummyFeed` sur Etherscan.
- Le méta-oracle est un clone EIP-1167 de `0x9B46…`, contrat vérifié `MetaOracleDeviationTimelock`. La factory Steakhouse **n'a pas d'adresse publiée** dans la doc → lien non prouvé.
- Le marché était le plus gros marché PT-sUSDe/USDC non expiré dans l'API Morpho le 2026-10-10 (≈ 7,76 M$ fournis).
