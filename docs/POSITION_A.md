# Position A : ce qu'on a découvert, expliqué simplement

Tous les chiffres sont lus **on-chain au bloc #26161750** (2026-10-10 11:31 UTC), sauf mention contraire.
Chaque affirmation de ce document correspond à une arête ou à un `meta` de [`output/graph.json`](../output/graph.json).
On peut la retrouver avec :

```bash
PYTHONPATH=src python -m discovery.inspect_graph --evidence
```

## En 5 lignes
1. On a déposé **413 030 PT-sUSDE-26NOV2026** sur un marché **Morpho Blue**, et on doit **357 215 USDC**.
2. Notre ratio dette/collatéral est de **87,2 %**, pour une limite (LLTV) de **91,5 %**. Le health factor vaut **1,050** : une baisse de **4,75 %** du prix donné par l'oracle nous rend liquidables.
3. L'oracle est un **méta-oracle**. En temps normal, il donne un prix **fixé par une formule** (décote linéaire de 6 %/an, qui ignore le marché) et suppose USDe = USDC = 1. Si le prix de marché s'écarte de plus de 0,75 % pendant 16 h, il peut **basculer** sur un oracle qui suit le prix de marché de l'USDe (Chainlink).
4. Tout en bas de la pile, le PT vaut 1 USDe à l'échéance (26 nov. 2026, dans 46,5 jours). L'USDe repose sur Ethena, c'est-à-dire des réserves chez des custodians et des shorts sur des exchanges centralisés. **Rien de cela n'est on-chain.**
5. Pour sortir du PT avant l'échéance, il faut passer par un pool Pendle de **3,8 M$**. C'est peu face aux **7,0 M$ empruntés** sur ce marché.

---

## Couche par couche (de la position vers le fond de la pile)

### 0. La position · `morpho:0x5613…:0x03BA…`
- **Ce que c'est :** une ligne dans le registre de Morpho, pour le couple (marché, emprunteur).
- **Lu :** `Morpho.position(id, user)` renvoie `(supplyShares 0, borrowShares 355 505 047 827 188 788, collateral 413 030,32 PT)`.
- **Dette à jour :** les parts de dette sont converties en USDC **avec les intérêts courus**. Morpho ne met ses totaux à jour qu'à chaque interaction (`lastUpdate`) ; ici, la dernière date d'environ 45 h. On ajoute donc les intérêts nous-mêmes, comme Morpho : `IRM.borrowRateView` donne le taux par seconde, auquel on applique `wTaylorCompounded`. Sans ça, la dette serait sous-estimée de 67 USDC sur notre position (1 322 USDC sur tout le marché). Recoupement : notre calcul et l'API Morpho diffèrent de **0,0001 %**.
- **`value_usd = 409 816,56 $`** : valeur du collatéral au prix de l'oracle, × prix de l'USDC selon Chainlink (USDC/USD = 0,99987, feed trouvé par ENS `usdc-usd.data.eth`). Valeur nette (collatéral − dette) : 52 650 $.

### 1. Le marché de prêt · `morpho_market_5613b170`
- **Ce que c'est :** un des marchés isolés du contrat unique Morpho Blue. Il est défini par 5 paramètres figés : USDC prêté, PT en collatéral, oracle, modèle de taux (IRM) et LLTV de 91,5 %.
- **Preuve d'identité :** on recalcule `keccak256(abi.encode(MarketParams))` et on retombe exactement sur l'ID demandé.
- **État :** 7,76 M USDC fournis, 6,99 M empruntés, soit **90,1 % d'utilisation**. Seulement 0,76 M USDC sont disponibles. Le taux d'emprunt est de **3,74 %/an**. L'IRM est bien l'AdaptiveCurveIrm officiel : son adresse correspond à la doc Morpho.
- **Qui prête :** le vault **Pendle Ecosystem USDC** (Morpho Vault V2, 61,6 M$ sous gestion), d'après l'API Morpho. Ses nom, actif et curateur sont relus on-chain.
- **Pourquoi c'est une dépendance :** si les prêteurs retirent leurs fonds, l'utilisation monte et le modèle de taux adaptatif fait grimper notre coût d'emprunt. Si le collatéral perd de la valeur, on est liquidé.

### 2. L'oracle : le cœur du sujet
Morpho appelle `oracle.price()` et lui fait **aveuglément confiance**. Démonter l'oracle, c'est savoir *quand* et *comment* on peut être liquidé.

```
oracle_meta_f8b29e  MetaOracleDeviationTimelock (Steakhouse) — clone EIP-1167, immuable — mode HYBRID
├── PRIMAIRE (actif) : oracle_morpho_v2_8fca98  MorphoChainlinkOracleV2 — mode FIXED
│     prix = SCALE × BASE_FEED_1                         (les 5 autres slots sont vides = 1)
│     └── BASE_FEED_1 = PendleSparkLinearDiscountOracle : prix_PT = 1 − 6 %/an × temps restant
└── SECOURS : oracle_morpho_v2_e2f4cf  MorphoChainlinkOracleV2 — mode MARKET
      prix = SCALE × BASE_FEED_1 × BASE_FEED_2 / QUOTE_FEED_1
      ├── BASE_FEED_1 = la même décote linéaire (fixe)
      ├── BASE_FEED_2 = Chainlink USDe / USD  (prouvé par ENS usde-usd.data.eth)  → 0,99960 $
      └── QUOTE_FEED_1 = DummyFeed : renvoie toujours 1 (sert à caler les décimales) → USDC = 1 en dur
```

Ce qu'on a **prouvé** :
- Les deux sous-oracles ont été créés par la factory officielle Morpho (`isMorphoChainlinkOracleV2 = true`).
- Leur prix **recalculé** à partir des briques est **identique** à `price()`.
- La formule de décote linéaire, recalculée, retombe sur la valeur du feed.
- Le feed « Dummy » est constant : `roundId = 1` et `updatedAt` égal à l'horodatage du bloc. Personne ne le met à jour.

**Prix fixé, taux interne, prix de marché : pourquoi ça change tout.**
- **Primaire (fixe).** Le prix du PT ne dépend que du temps : 0,99235 aujourd'hui, 1,0000 le 26 novembre. Il suppose implicitement **1 USDe = 1 USDC**. Un depeg de l'USDe ne le fait **pas** bouger.
- **Secours (marché).** Il multiplie la même décote par le **vrai** prix de l'USDe (Chainlink). Un depeg le fait baisser d'autant.
- **La règle de bascule.** Elle est sourcée dans la [doc Steakhouse](https://steakhouse.financial/docs/products/infrastructure/metaoracle), et ses paramètres sont lus on-chain. L'écart vaut |primaire − secours| / moyenne. Seuil = **0,75 %**. N'importe qui peut appeler `challenge()`. Si l'écart tient encore après **57 600 s (16 h)**, `acceptChallenge()` bascule sur le secours. Le retour au primaire se fait après **86 400 s (24 h)** de reconvergence. Écart actuel : 0,04 %.
- **Taux interne.** Le sUSDe vaut **1,25234 USDe** selon `convertToAssets`. C'est une comptabilité interne qui ne fait que monter, pas un prix de marché. Ici, aucun des deux oracles ne l'utilise : le PT est directement libellé en USDe (`SY.assetInfo()` → USDe).

### Scénarios de depeg (calculés avec les valeurs du bloc)
Le prix de secours vaut à peu près « prix primaire × prix de l'USDe ». On en déduit :

| Prix de marché de l'USDe | Ce qui se passe |
|---|---|
| ≥ 0,9925 $ | Écart < 0,75 % : aucune bascule possible. Prix fixe, rien ne bouge. |
| entre 0,9525 $ et 0,9925 $ | Un `challenge()` est possible. Si le depeg dure plus de 16 h, l'oracle bascule sur le marché. Notre health factor baisse, mais nous **ne sommes pas liquidables**. |
| < 0,9525 $ **pendant plus de 16 h** | Après bascule, le prix passe sous 0,9452 USDC/PT (= prix actuel / HF) : **nous sommes liquidables**. Les liquidateurs prennent nos PT avec un bonus. |
| < 0,9525 $ **pendant moins de 16 h** | Le prix reste fixe, nous ne sommes pas liquidés. Mais pendant cette fenêtre, n'importe qui peut acheter du PT bon marché et emprunter des USDC au prix fixe. **Ce sont les prêteurs** (dont le vault Pendle Ecosystem USDC) qui portent le risque. |

Autrement dit, le méta-oracle **amortit les depegs courts** (bon pour l'emprunteur, risque pour le prêteur) et **suit les depegs longs** (liquidations). Le délai de 16 h est le paramètre de risque central de cette position.

À noter aussi :
- **Sans depeg**, la décote fait monter le prix du PT de +0,77 % d'ici l'échéance, tandis que la dette croît d'environ 0,48 % sur la même période (3,74 %/an). Le health factor s'améliore donc légèrement jusqu'au 26 novembre, à taux constant. Mais le taux est adaptatif et l'utilisation est à 90 % : à surveiller.
- Le prix de l'oracle (0,99235) est **0,14 % sous** le prix implicite du pool Pendle (0,99379 USDe). L'oracle est un peu plus prudent que le marché aujourd'hui.

### 3. Le PT et son pool AMM (Pendle) · `pt_susde_26nov2026`, `pendle_plp_susde_26nov2026`
- **PT** (Principal Token) : il vaut 1 actif comptable du SY (**l'USDe**, `SY.assetInfo()`) à l'échéance du **26/11/2026**. Analogie : une obligation zéro-coupon. Sa factory `0x3E6E…` est `yieldContractFactoryV6` dans les déploiements officiels de Pendle.
- **SY-sUSDE** : l'emballage standard de Pendle. `yieldToken()` donne sUSDe. On peut y entrer en USDe ou en sUSDe, mais on en sort **en sUSDe uniquement** (`getTokensOut`). Le rachat du PT donne donc du sUSDe, qu'il faut ensuite déstaker pendant 1 jour (cooldown) pour obtenir de l'USDe.
- **Pool Pendle :** il a été localisé par l'API Pendle, puis **prouvé on-chain** : `readTokens()` contient bien notre PT, et la `marketFactoryV6` répond `isValidMarket = true`. Réserves : 971 271 PT et 2 282 035 SY, pour une TVL de **3,82 M$** (l'API Pendle donne 3,82 M$ aussi). Taux implicite : 5,01 %.
- **Pourquoi c'est une dépendance :** un liquidateur qui saisit nos PT doit les revendre sur ce pool, ou attendre 46 jours l'échéance. Un pool peu profond freine les liquidations et peut créer de la dette irrécouvrable.

### 4. La source de rendement et son émetteur (Ethena) · `susde`, `usde`, `ethena_labs`
- **sUSDe :** coffre ERC-4626. 1 part = 1,25234 USDe ; 1,21 Md USDe déposés ; cooldown de retrait de **86 400 s (1 jour)**, lu on-chain.
- **USDe :** dollar synthétique d'Ethena (4,78 Md en circulation). Il est adossé à du collatéral crypto couvert par des **ventes à découvert de contrats perpétuels**.
- **Émetteur :** les adresses de l'USDe et du sUSDe correspondent à la page officielle « Key Addresses » d'Ethena (lien curé).
- **Ce qui N'EST PAS on-chain (→ `curated.yaml`) :**
  - les custodians « Off-Exchange Settlement » cités par Ethena : **Copper, Ceffu, Fireblocks** ;
  - les exchanges de hedge cités : **Binance, Bybit, Bitget, Deribit, OKX**.

  Les deux listes sont introduites par « such as » dans la doc d'Ethena : ce sont des exemples, pas forcément la liste complète. La répartition n'est **pas** connue de notre graphe (poids 1.0 = borne haute). Elle se trouve dans les tableaux de bord de transparence d'Ethena : c'est une prochaine étape.

### 5. La chaîne · `ethereum`
14 contrats ont du code au bloc #26161750 (`eth_getCode`), sur `eth_chainId = 1`.

### À côté de la pile : USDC · `usdc`, `circle`
C'est l'actif de la dette. USDC est un **proxy upgradeable** (slot ZeppelinOS lu on-chain) : Circle peut en changer le code. L'adresse correspond à la page officielle de Circle.

---

## Questions ouvertes (vraies inconnues, pas des suppositions)
- Quelle factory a déployé ce méta-oracle ? La doc Steakhouse ne publie pas son adresse, donc le lien avec Steakhouse n'est **pas prouvé on-chain** (`meta.design_note`).
- Quelle est la répartition réelle des réserves et des hedges d'Ethena ? Elle est sur les tableaux de bord de transparence, mais n'est pas encore curée.
- Quelle profondeur réelle pour une liquidation ? Il faudrait simuler une vente de PT sur le pool (glissement de prix). C'est le travail d'une autre équipe, mais `reserve_pt` et `reserve_sy` leur donnent la base.

<details>
<summary><b>Corrigé des 5 questions de compréhension</b> (essayez d'abord !)</summary>

1. **L'USDe à 0,92 $ avec une décote linéaire sans feed USDe ?** Dans un marché à oracle *purement* fixe, on n'est pas liquidé : le prix ne bouge pas. Ce sont les prêteurs qui perdent si l'USDe ne remonte pas (dette irrécouvrable à l'échéance), et ils perdent plus tôt si des opportunistes empruntent contre du PT acheté au rabais. **Sur notre marché réel**, il y a le méta-oracle : après 16 h d'écart, il bascule sur le prix de marché. À 0,92 $ (< 0,9525 $), on devient liquidables.
2. **Prouver les paramètres sans l'app Morpho :** on recalcule `keccak256(abi.encode(loanToken, collateralToken, oracle, irm, lltv))` à partir de `idToMarketParams(id)`, et on vérifie qu'on retombe sur `id` (champ `meta.market_id_check`).
3. **1 PT à l'échéance :** il vaut 1 USDe (l'actif comptable du SY), payé en **SY**, échangeable en **sUSDe** (seul jeton de sortie). Ensuite, il faut un cooldown d'1 jour pour obtenir de l'USDe. « 1 PT = 1 sUSDe » est faux, car 1 sUSDe vaut déjà 1,25 USDe.
4. **Non prouvable on-chain :** où sont les réserves d'Ethena (custodians) et sur quels exchanges sont ses hedges ; ou encore qui est derrière une adresse (ex. « cette adresse est l'USDC de Circle »). Preuve possible : l'URL officielle et sa date de relevé (`evidence_url`, `as_of` dans `curated.yaml`).
5. **Le pool peu profond, même si l'oracle ne le lit pas :** les liquidateurs doivent revendre le PT saisi. S'ils ne peuvent pas le faire sans grosse perte, ils ne liquident pas, ou trop tard, et la dette irrécouvrable s'accumule.
</details>
