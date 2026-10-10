# Backend v2 : d'une adresse réelle à STAY / EXIT

Ce backend répond à la question du brief Belem, sur des **données réelles, en direct** :

> « Est-ce que la perte attendue en restant dans cette position justifie d'en sortir, malgré le coût de sortie ? »

Il remplace la position unique écrite en dur dans `config.yaml` (position A) par **n'importe quel détenteur réel**. Le code de la v1 (`src/discovery`, `src/risk`, position A, démo hors ligne) est intact et ses tests passent toujours.

## Qu'est-ce qu'une « position » ?
C'est **une ligne du portefeuille** d'un détenteur, une « poche » au sens du brief (« a book split across ten pockets »). On part de **l'adresse du détenteur**, et l'outil trouve toutes ses poches. L'adresse de test vient du tableau de bord Dune fourni par Belem ([RockawayX vaults](https://dune.com/rockawayxvault/rockawayx-dashboard)) : `0x4F87…0545`, déposant principal du vault « Belem RWA EURCV ». ⚠ **Que cette adresse appartienne à Belem reste à confirmer avec eux.**

Types de poches pris en charge :
- `morpho_vault_v2` : dépôt dans un vault Morpho V2 (on est **prêteur**) ;
- `morpho_market_borrow` : emprunt sur un marché Morpho (on est **emprunteur**, avec levier) ;
- `morpho_market_supply` : prêt direct sur un marché.

## Le pipeline

```
adresse ─▶ 1. session en ligne (RPC, bloc figé)                          session.py
        ─▶ 2. poches : l'API localise, la chaîne prouve les montants     portfolio.py
        ─▶ 3. graphe prouvé de la poche (vault → adapters → marchés…)    graph_build.py, vault_v2.py
        ─▶ 4. données de risque : emprunteurs, profil d'oracle           market_data.py
        ─▶ 5. incidents générés depuis le graphe → perte de la poche     risk_engine.py
        ─▶ 6. coût de sortie (liquidité, devis DEX, pénalité, gas)       exit_cost.py
        ─▶ 7. décision STAY / EXIT, p*, chemins de contagion            analyze.py
        ─▶ API HTTP pour le front                                         api.py  (contrat : API.md)
```

## Commandes (PowerShell)

```powershell
$env:PYTHONPATH="src"
.venv313\Scripts\python -m stacktrace.doctor                                   # tout répond ?
.venv313\Scripts\python -m stacktrace.portfolio 0x4F87De7d21aeF48090958f7342E1F69Dff790545
.venv313\Scripts\python -m stacktrace.graph_build 0x4F87De7d21aeF48090958f7342E1F69Dff790545 "Belem RWA"
.venv313\Scripts\python -m stacktrace.analyze 0x4F87De7d21aeF48090958f7342E1F69Dff790545          # tout le portefeuille
.venv313\Scripts\python -m stacktrace.analyze 0x4F87De7d21aeF48090958f7342E1F69Dff790545 --pocket "Belem RWA" --incident rwa_credit_event:mgloeuro --severity 0.3 --p 0.2
.venv313\Scripts\python -m stacktrace.api                                      # API sur http://127.0.0.1:8000
```

Les sorties vont dans `output/live/` (ignoré par git). Le cache en ligne va dans `data/cache_live/` (ignoré aussi).

## Le modèle, en clair

**On ne devine jamais.** Chaque adresse et chaque fonction est prouvée on-chain, ou vérifiée dans un code source vérifié (Etherscan, dépôt officiel). Chaque chiffre de `risk/params_v2.yaml` est **sourcé** ou **marqué hypothèse**, avec sa raison et sa plage de sensibilité. Le chargeur refuse tout le reste.

### Ce que perd un prêteur (poche vault)
Seulement la **dette irrécouvrable** des emprunteurs, calculée **emprunteur par emprunteur** (un agrégat cacherait les emprunteurs à risque) :
- si le collatéral est pricé **au marché** et chute **progressivement**, les emprunteurs sont liquidés à temps et le prêteur ne perd rien ;
- en cas de choc **brutal**, ou si l'oracle **ne suit pas le marché** (taux interne, prix posé par un admin), personne n'est liquidé à temps : perte = max(0, D − V·(1−d)·(1−glissement)) ;
- si un feed est **faussé vers le haut**, un attaquant emprunte la liquidité disponible. Il gagne seulement si (1+u)·LLTV > 1. Exemple : le feed Midas est borné à +10 % et la LLTV vaut 77 % ; 1,10 × 0,77 < 1, donc l'attaque ne rapporte rien ;
- un **depeg** de l'actif de la poche, une faille de Morpho ou une défaillance du curateur fait perdre directement la valeur × la sévérité.

### Ce que perd un emprunteur (poche emprunt)
- La **liquidation** : pénalité ρ·D·(LIF − 1), avec la formule officielle Morpho.
- Une **liquidation à tort** si un feed se trompe vers le bas.
- La perte de valeur **propre** au collatéral : défaut d'un RWA, depeg d'un LST pricé au taux de change.
- ⚠ Choix assumé (paramètre `borrow_market_beta_excluded`) : une baisse d'ETH ou de BTC **ne compte que par la liquidation** qu'elle déclenche. Belem est market-neutral : la baisse du marché est une exposition choisie, pas un risque de dépendance.

### La décision
- **Sortir coûte un montant certain**, mesuré :
  - pour un vault : la liquidité retirable maintenant, la pénalité de retrait forcé (au-delà du marché « source de liquidité »), le rendement abandonné et le gas ;
  - pour un emprunt : le glissement mesuré par des **devis KyberSwap réels** à plusieurs tailles, le rendement abandonné et le gas. La part dont le glissement dépasse 25 % est jugée **non sortable par le marché**.
- **On sort la fraction f** qui minimise coût(f) + perte attendue × (1 − f). Si f > 0, c'est **EXIT**, sinon **STAY**.
- **p\* = coût de sortie / perte si l'incident arrive.** C'est le seuil à donner au manager : « sortez si vous croyez à plus de p\* ». Il ne dépend **pas** de nos probabilités, qui sont des hypothèses, seulement de quantités mesurées.

## Limites connues (à dire au jury)
- **Les probabilités d'incident sont des ordres de grandeur** (hypothèses affichées). D'où l'importance de p\*.
- **Les incidents sont tirés indépendamment** : la contagion croisée entre poches n'est pas simulée. Les dépendances partagées sont **listées** (`/book` → `shared_dependencies`).
- **Le prix en dollars de l'actif d'une poche vient de l'API Morpho** (marqué `source: api`).
- **La sortie d'un RWA par rachat chez son émetteur** (ex. Huma pour PST) n'est pas modélisée : seule la sortie par le marché l'est.
- **Seul l'écosystème Morpho Ethereum est couvert.** Midas, Kamino/Solana et les autres protocoles du tableau Dune sont les étapes suivantes.
- **Le panier Reserve (ETH+) n'est pas démonté** : son oracle est marqué `unknown`.

## À vérifier par l'équipe (règle « jamais d'adresse de mémoire »)
- Les sources des nouveaux oracles (codes vérifiés Etherscan cités dans `src/discovery/adapters/oracles.py`).
- L'interface Morpho Vault V2 ([IVaultV2.sol](https://github.com/morpho-org/vault-v2/blob/main/src/interfaces/IVaultV2.sol)) et les deux versions d'adapter (citées dans `src/stacktrace/vault_v2.py`).
- La doc de l'API KyberSwap ([spécification](https://docs.kyberswap.com/kyberswap-solutions/kyberswap-aggregator/aggregator-api-specification/evm-swaps)).
