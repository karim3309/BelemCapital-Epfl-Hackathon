# Prochaines étapes et prompts prêts à lancer

## Où on en est (mise à jour après les parties 2 et 3)
- **Partie 1, découverte** : position A, 28 nœuds, 45 arêtes, contrat valide, rejouable sans réseau.
- **Parties 2 et 3, impact et décision** (`src/risk/`) :
  - 15 scénarios et une grille prix × durée ;
  - un Monte Carlo et un replay du 10/10/2025 ;
  - p\* et la sortie partielle ;
  - chaque chiffre avec son statut.
- **Front** : `front/` (deck sur l'API v2, réponses enregistrées hors ligne).
- **126 tests** au total.

Les prompts S1 à S8 plus bas restent valables (approfondir la découverte). Les nouveaux prompts R1 à R5 sont juste en dessous.

### À valider en équipe / avec les mentors Belem (priorité 1)
1. **Horizon de décision** : 7 jours (hypothèse). Le cadrage pose la question (24 h ou 7 jours ?). Changer `horizon_days` dans `risk/params.yaml`.
2. **Poche V = capital net** de la position (53 k$), et non la valeur brute (410 k$). C'est ce qui rend p\* si bas (levier ×8). D'accord ?
3. **Fréquences d'exploit** : hypothèses d'ordre de grandeur, car le dataset de hacks DeFiLlama est payant. Les mentors ont-ils une source de référence ?
4. **Liquidation à 100 %** (pire cas, autorisé par Morpho) : sensibilité affichée de 50 % à 100 %. Réaliste pour eux ?
5. **p\* leur parle-t-il plus qu'une probabilité estimée par nous ?** (question du cadrage)

### Nouveaux prompts (après parties 2-3)
**R1 · Position B : dépôt USDC dans un vault Morpho curé** (cadrage §4.1).
```text
Lis CLAUDE.md, docs/PARTS_2_3.md et docs/CONTRACT.md. Objectif : la position B du cadrage, un dépôt USDC dans un vault
Morpho curé. La racine devient un vault : il alloue sur N marchés, chacun avec son collatéral et son oracle.
1. Explique-moi en 10 lignes ce qu'est un vault MetaMorpho / Morpho Vault V2 et comment lire ses allocations ON-CHAIN
   (fonctions exactes depuis la doc Morpho, URL citée). ATTENDS mon accord sur le vault choisi (ex. le vault « Pendle
   Ecosystem USDC » déjà découvert, 61,6 M$).
2. Ajoute un adaptateur racine « vault » sans casser la position A (nouveau config dans configs/, sortie output/position_b/).
3. Adapte le moteur de risque : pour un prêteur, la perte vient de la dette irrécouvrable des marchés (déjà calculée par
   position.py). Réutilise scénarios et Monte Carlo ; p* sur la poche du déposant.
4. Tests, refresh, audit, front (sélecteur de position).
```
**R2 · Vue « book 10 poches »** (bonus du cadrage).
```text
Lis CLAUDE.md et docs/PARTS_2_3.md. Objectif : un book de 10 poches de 10 % (position A, position B, puis des variantes
réelles). Montre les dépendances PARTAGÉES (ex. USDe, Ethena, Chainlink) et la concentration cachée : quelle part du book
tombe si Ethena tombe ? Réutilise les graph.json et le moteur ; aucune donnée inventée (poches = positions réelles).
```
**R3 · Calibration des fréquences d'exploit sur une source publique.**
```text
Lis CLAUDE.md et risk/params.yaml (section events). Objectif : remplacer les fréquences annuelles « hypothesis » par une
calibration sourcée. Le dataset de hacks DeFiLlama est payant (pro-api.llama.fi/api/hacks) : trouve une source publique
(rekt.news, rapport annuel publié, export manuel daté), cite l'URL et montre-moi la méthode AVANT de coder. Statut :
source + as_of, ou on garde l'hypothèse.
```
**R4 · Replay xUSD / deUSD (novembre 2025).** Il faut un RPC **archive** (Alchemy ou Infura gratuit) pour lire les blocs d'avant la crise.
```text
Lis CLAUDE.md et src/risk/replay.py. Objectif : le replay principal du cadrage, la cascade Stream xUSD → Elixir deUSD →
marchés de prêt (novembre 2025). Trouve d'abord, dans des sources fiables (citées), les dates, actifs et marchés Morpho
touchés, et un vault qui y était exposé. ATTENDS ma validation. Puis découvre le graphe de ce vault à un bloc d'AVANT la
crise (RPC archive dans .env) et montre que l'outil retrouve le chemin de contagion.
```
**R5 · Claude comme jury** (cadrage §6.5).
```text
Joue le risk manager de Belem Capital (≈ 400 M$, zéro liquidation depuis 2020). Lis README.md, docs/PARTS_2_3.md et
output/risk_report.json. Démonte nos chiffres : trouve les 10 critiques les plus dures sur la défendabilité de l'impact et
de la décision, classées par gravité, avec ce qu'il faudrait pour y répondre. Ne modifie aucun fichier.
```

---

## Avant les parties 2-3 (toujours valable)
Ce document liste, dans l'ordre :
1. ce que **vous** devez faire (vérifier, décider) ;
2. la répartition à 3 ;
3. les étapes techniques suivantes, chacune avec un **prompt à copier-coller** dans Claude Code.

---

## Étape 0 : à faire par vous (≈ 1 h, avant tout nouveau code)
1. **Lire** [`POSITION_A.md`](POSITION_A.md) et répondre aux 5 questions (le corrigé est en bas, replié).
2. **Cocher** [`VERIFY.md`](VERIFY.md), au minimum la section A (entrées de `config.yaml`) et la section B (`curated.yaml`).
3. **Trancher avec les organisateurs** :
   - l'arête `lends` (marché → actif prêté) est une **extension** des 6 types du brief : on la garde ?
   - `collateralized_by` (marché → collatéral) est « est collatéral de » **lu à l'envers**, pour garder une seule direction : OK ?
   - la racine `position` n'est pas un nœud, mais elle est `from` d'une arête : OK pour les équipes aval ?
   - `value_usd` = valeur du collatéral au prix de l'oracle (et non nette de la dette) : c'est ce qu'ils attendent ?
   - l'emprunteur réel `0x03BA…`, ou une position hypothétique à 1 M$ comme dans l'exemple du brief ?
4. Reporter les décisions dans `CLAUDE.md` et `vocab.py` (une PR relue par les 2 autres).

## Procédure à connaître : régénérer le cache
Le cache est lié au bloc figé. **Dès qu'un adaptateur fait un nouvel appel**, il faut régénérer :
```bash
# 1. config.yaml → snapshot_block: latest ; .env → ETH_RPC_URL=...
PYTHONPATH=src python -m discovery.build_graph            # en ligne, affiche « découverte au bloc #N »
# 2. config.yaml → snapshot_block: N   (recopier le numéro)
PYTHONPATH=src python -m discovery.build_graph --offline  # doit afficher 0 miss
python -m pytest                                          # le test golden compare à output/graph.json
git add data/cache output/graph.json config.yaml && git commit
```
Pour garder un cache propre, supprimez `data/cache/` avant l'étape 1. Avec un RPC non-archive, faites les étapes 1 et 2 dans la foulée (moins de ~25 min).

## Répartition à 3 (chacun ses fichiers, donc aucun conflit)
| Membre | Rôle | Fichiers qu'il est seul à modifier |
|---|---|---|
| **1 · Socle & démo** | orchestration, multi-positions, CI, performance, démo | `build_graph.py`, `rpc.py`, `cache.py`, `http.py`, `inspect_graph.py`, `.github/` |
| **2 · Prêt & prix** | autres marchés Morpho, nouveaux oracles, vaults | `adapters/morpho.py`, `adapters/morpho_api.py`, `adapters/oracles.py`, `adapters/ens.py` |
| **3 · Actifs & hors-chaîne** | Pendle (liquidité), Ethena (poids), couche curée | `adapters/pendle.py`, `adapters/erc4626.py`, `adapters/erc20.py`, `adapters/curated.py`, `curated.yaml` |

Fichiers partagés (PR relue par les 2 autres) : `vocab.py`, `graph.py`, `validate.py`, `ctx.py`, `config.yaml`, `CLAUDE.md`. Chacun teste dans `tests/test_<son_domaine>.py`.
Règle de branche : `feature/<membre>-<sujet>` → PR vers `main`.

---

## Étapes techniques et prompts

Chaque prompt est autonome. Collez-le tel quel dans une session Claude Code ouverte sur le repo.

### S1 · (Membre 2) Généraliser à d'autres marchés Morpho, et chasser les oracles inconnus
**Objectif :** prouver que le module n'est pas taillé sur mesure pour la position A. **Vérification :** 0 nœud `unresolved`, ou un handler ajouté pour chaque type inconnu.
```text
Lis CLAUDE.md en entier. Objectif : tester le Module de Découverte sur d'autres marchés Morpho Blue que la position A.
1. Avec l'API Morpho (URL dans config.yaml, appels via ctx.http donc cachés), liste les 10 plus gros marchés Ethereum
   non expirés dont le collatéral est un PT Pendle, un ERC-4626 (ex. wstETH, sUSDe) ou un token simple.
   Montre-moi la liste (marketId, collatéral/prêt, taille) et ATTENDS que je choisisse 3 marchés.
2. Pour chaque marché choisi, crée un config de test (configs/<nom>.yaml, user: null, et SURTOUT
   discovery.output_file: output/<nom>.json pour ne pas écraser output/graph.json), puis lance
   `python -m discovery.build_graph --config configs/<nom>.yaml`.
3. Liste tous les nœuds meta.unresolved=true et les oracles 'unknown'. Pour chacun : lis le code source vérifié sur
   Etherscan (dis-moi l'URL), explique le contrat en 5 lignes, puis ajoute un handler dans adapters/oracles.py
   avec un test FakeCtx dans tests/. N'invente aucun nom de fonction : sonde-les on-chain et cite la source.
4. Vérifie notamment les sondes NON VÉRIFIÉES du feed TWAP Pendle (market(), twapDuration()) sur un vrai contrat.
5. Fais un audit : contrat JSON valide, preuves présentes, pas d'adresse sortie de ta mémoire. Mets à jour docs/VERIFY.md.
```

### S2 · (Membre 3) Liquidité de sortie : combien coûte la revente de notre PT ?
**Objectif :** mesurer on-chain le glissement de prix si l'on liquide la position sur le pool Pendle. **Vérification :** une petite vente simulée ≈ le prix spot de l'AMM ; l'impact croît avec la taille.
```text
Lis CLAUDE.md. Objectif : ajouter au nœud liquidity_venue (pool Pendle) une mesure ON-CHAIN de la profondeur :
combien de SY (puis d'USDe) obtient-on en vendant 10 %, 50 % et 100 % du collatéral de notre position ?
1. Explique-moi d'abord ce qu'est le RouterStatic de Pendle et quelle fonction « preview » permet de simuler
   une vente de PT sans transaction. Cherche le nom exact et l'adresse UNIQUEMENT dans la doc Pendle ou le fichier
   officiel deployments/1-core.json, cite l'URL, et ajoute l'adresse dans config.yaml avec sa source.
2. Implémente l'appel dans adapters/pendle.py via ctx.call (donc caché, au bloc figé), stocke dans meta
   `exit_simulation` : taille vendue, SY reçus, prix moyen, impact vs pt_price_implied_by_amm.
3. Tests FakeCtx + mise à jour du test golden ; régénère le cache (procédure dans docs/NEXT_STEPS.md).
4. Audit final : aucune adresse sans source, contrat JSON valide, docs/POSITION_A.md mis à jour avec les chiffres.
```

### S3 · (Membre 3) Poids réels d'Ethena : où sont les réserves et les hedges ?
**Objectif :** remplacer les poids 1.0 (borne haute) par la répartition publiée. **Vérification :** les poids d'une même catégorie somment à environ 1, chaque ligne a une URL et une date.
```text
Lis CLAUDE.md. Objectif : compléter curated.yaml avec la RÉPARTITION des actifs de réserve d'USDe par custodian
et des hedges par exchange, telle que publiée par Ethena (pages de transparence / attestations).
1. Trouve la source officielle (site ou API publique d'Ethena), donne-moi l'URL et la date des chiffres, et
   ATTENDS ma validation de la source avant d'écrire quoi que ce soit.
2. Mets à jour curated.yaml : weight = part (0-1), weight_known: true, as_of = date des chiffres. Si une donnée
   vient d'une API, fais l'appel via ctx.http (caché) dans un adaptateur adapters/ethena.py plutôt qu'à la main.
3. Ajoute un test qui vérifie que les poids d'une même catégorie somment à ~1.
4. Audit : aucun chiffre sans source, rien d'extrapolé, docs/VERIFY.md section B à jour.
```

### S4 · (Membre 2) Les prêteurs : poids des vaults dans le marché
**Objectif :** donner un vrai `weight` à l'arête vault → marché (la part du marché financée par ce vault). **Vérification :** la somme des parts des vaults ≤ 1.
```text
Lis CLAUDE.md. Objectif : pour chaque vault qui prête à notre marché Morpho, calculer ON-CHAIN la part de l'offre
du marché qu'il représente : position(marketId, vault).supplyShares converties en actifs / total fourni.
1. Explique la différence entre un vault MetaMorpho v1 et un Morpho Vault V2 (adapters) : pour un V2, les fonds
   sont-ils détenus par le vault lui-même ou par un « adapter » ? Vérifie dans la doc Morpho (cite l'URL).
2. Lis la bonne adresse (vault ou adapter) via ctx.call, calcule la part, mets-la dans le weight de l'arête
   vault --deployed_in--> marché (et dans meta), en gardant la preuve on-chain dans evidence.
3. Tests FakeCtx, régénération du cache, audit (contrat valide, aucune adresse inventée).
```

### S5 · (Membre 1) Plusieurs positions et intégration continue
**Objectif :** `build_graph` traite une liste de positions ; GitHub Actions lance les tests hors ligne à chaque push. **Vérification :** CI verte sur une PR, et un fichier `output/<position>.json` par position.
```text
Lis CLAUDE.md. Objectif 1 : permettre une liste de positions dans config.yaml (clé `positions:`), produire
output/<slug>.json par position, en gardant output/graph.json pour la position A (compatibilité).
Objectif 2 : ajouter .github/workflows/tests.yml qui installe Python 3.11, requirements.txt, et lance
`python -m pytest` en mode offline (STACKTRACE_OFFLINE=1, sans secret RPC).
Contraintes : ne casse pas le contrat JSON ; tests ajoutés ; explique-moi chaque bloc YAML de la CI.
Audit final puis propose-moi le message de commit.
```

### S6 · (Membre 1) Performance : regrouper les appels (Multicall3)
**Objectif :** diviser le nombre de requêtes RPC (≈ 190 aujourd'hui) sans changer le graphe. **Vérification :** `output/graph.json` identique avant/après.
```text
Lis CLAUDE.md. Objectif : réduire le nombre de requêtes RPC lors d'un rafraîchissement, en regroupant les sondes
via le contrat Multicall3. Trouve son adresse UNIQUEMENT dans une source officielle (cite l'URL) et ajoute-la
dans config.yaml avec sa source. Le cache doit rester au niveau du provider (rpc.py) et le graphe produit doit être
STRICTEMENT identique (compare output/graph.json avant/après). Mesure le nombre d'appels réseau avant/après.
Garde le code simple et commenté : on est débutants.
```

### S7 · (Tous) Préparer la démo (5 min chrono)
```text
Lis CLAUDE.md, README.md et docs/POSITION_A.md. Prépare un script de démo de 5 minutes pour le jury :
1. coupure Wi-Fi → `build_graph --offline` (0 appel réseau) ;
2. `inspect_graph` : l'arbre ;
3. `inspect_graph --evidence` : zoom sur 3 preuves (une onchain, une api, une curated) ;
4. le cas du méta-oracle : pourquoi un depeg court ne liquide pas, et un depeg long si (chiffres de POSITION_A.md) ;
5. `inspect_graph --impact binance` : propagation hors chaîne → position.
Écris-le dans docs/DEMO.md avec les commandes exactes (PowerShell ET bash) et ce qu'on dit à chaque étape.
Vérifie que chaque commande marche réellement hors ligne.
```

### S8 · (Membre 2 ou 3) Le rachat du PT à l'échéance
**Objectif :** rendre explicite la chaîne de rachat après le 26/11/2026 (YT.redeemPY, sortie en sUSDe, cooldown). **Vérification :** les nœuds et arêtes ajoutés respectent le vocabulaire, sinon on demande une extension.
```text
Lis CLAUDE.md. Objectif : décider (avec moi) si le YT et le mécanisme de rachat doivent apparaître dans le graphe.
1. Explique comment on rachète un PT après l'échéance chez Pendle (quel contrat, quelle fonction), à partir de la
   doc Pendle (cite l'URL) et du code vérifié du YT de notre position (adresse dans meta.yt du PT).
2. Propose 2 options de modélisation compatibles avec vocab.py (sans nouveau type si possible) et ATTENDS mon choix.
3. Implémente, teste, régénère le cache, audit.
```

---

## Idées pour la suite (non prioritaires)
- Ajouter une position B sur un autre protocole (ex. Aave), c'est-à-dire un nouvel adaptateur racine.
- Exporter un JSON Schema du contrat pour les équipes qui ne codent pas en Python.
- Surveiller l'âge des feeds (`age_seconds` vs heartbeat Chainlink, lui aussi à sourcer).
