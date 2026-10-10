# Audit complet : StackTrace face au brief Belem (10/10/2026)

> But : savoir, critère par critère du barème, où on prend des points, où on en perd, et quoi faire **avant le gel des
> fonctionnalités**. Ce document ne modifie aucun code : chaque correction proposée attend l'accord de l'équipe.

## 0. Méthode
**Lu :**
- le brief (`docs/BelemCapital_EPFL-Hackathon_DeFi-Risk-Dependency-Challenge_EN_v1.pdf`) et le cadrage (`docs/Belem DeFi Risk — Cadrage & Guideline.pdf`) ;
- tout `src/` (discovery, risk, stacktrace), `risk/*.yaml`, `config.yaml` ;
- les sorties (`output/`, `docs/api_examples/`) et toute la doc.

**Exécuté (hors ligne) :**
- `pytest` : **129 tests verts**, 2 ignorés (tests réseau) ;
- `discovery.build_graph --offline` : 1027 lectures en cache, **0 appel réseau** ;
- `discovery.validate` : contrat valide ;
- `risk.run` : rapport identique au rapport commité ;
- `npm run build` du front `front/` : la compilation passe.

**Contre-expériences :** quelques cas lancés à la main pour tester le moteur (section 3.2).

**Pas vérifié :**
- le tableau Dune RockawayX : `dune.com` est bloqué par le réseau de cet environnement (section 4) ;
- le backend v2 en direct : il faut un RPC, et aucune clé n'est présente ici. Il a été jugé sur ses réponses enregistrées (`docs/api_examples/`, bloc #26162868).

---

## 1. Verdict en 30 secondes
Le projet répond **à la lettre** à l'énoncé et au cadrage :
- un graphe de dépendances **prouvé** (5 couches du brief, et même 7 sauts jusqu'aux custodians d'Ethena) ;
- un impact en **$**, propagé selon une règle par type d'arête ;
- une décision **STAY / PARTIAL / EXIT** fondée sur **p\*** ;
- un replay réel, un book réel de 11 poches tiré du tableau Dune ;
- une démo qui tourne sans réseau.

C'est déjà au-dessus de ce qu'on attend d'une équipe de débutants.

Les points perdus se cachent à trois endroits :
1. **trois artefacts du moteur** qu'un expert du jury peut trouver en 5 minutes (section 3.2) ;
2. **le coût de sortie « temps calme »**, utilisé même quand l'alerte est déjà tombée (section 3.3) ;
3. **un récit de démo à deux têtes** : deux moteurs, deux fronts, deux blocs (section 3.4).

| Critère (poids) | Note estimée aujourd'hui | Après les correctifs P0 | Pourquoi |
|---|---|---|---|
| Découverte (30 %) | 4 / 5 | 4 / 5 (4,5 avec P1) | Très solide sur la position A ; graphes v2 plus courts (pas d'émetteurs ni de hors-chaîne pour les RWA de Belem) |
| Impact (30 %) | 3,5 / 5 | 4,2 / 5 | Mécanique fine (méta-oracle, LIF Morpho, glissement mesuré), mais liquidation « tout ou rien » non monotone et collatéral mal classé en v2 |
| Décision (25 %) | 4 / 5 | 4,5 / 5 | p\* et sortie partielle : exactement ce que veut le brief. Il manque le coût de sortie **sous stress** et une zone d'indifférence |
| Démo (15 %) | 4 / 5 | 4,5 / 5 | Hors ligne et reproductible, mais en mode enregistré 9 poches sur 11 n'ont pas de détail |
| **Total pondéré** | **≈ 3,85 / 5** | **≈ 4,3 / 5** | estimation personnelle, pas une note officielle |

---

## 2. Ce que demande le brief → ce qu'on a
| Exigence du brief | Statut | Où |
|---|---|---|
| « Automatically identify the dependencies of a position » | ✅ v1 part d'un `marketId` + `user` ; v2 part de **n'importe quelle adresse** de détenteur | `src/discovery/`, `src/stacktrace/portfolio.py` |
| Les 5 couches de l'exemple Pendle PT (chaîne, source de rendement + émetteur, oracle, AMM PT, marché de prêt) | ✅ toutes présentes pour la position A, chacune avec sa preuve | `output/graph.json` |
| « Estimate the potential economic impact […] when one of them is affected » | ✅ 15 scénarios, une grille de 228 cas, un Monte Carlo, des pertes emprunteur **et** prêteurs | `src/risk/` |
| « Explain how that incident propagates through the dependency stack » | ✅ en v1 (règle par arête + trace + chemins) ; ⚠ plus court en v2 (section 3.2, C) | `src/risk/propagate.py` |
| « Stay or exit […] despite slippage and execution costs » | ✅ p\* = C_exit / perte, sortie partielle, phrase de décision | `src/risk/decide.py`, `src/stacktrace/analyze.py` |
| Book de 10 poches, une poche touchée, sortie à 11 % | ✅ book réel de 11 poches et dépendances partagées (v2) ; ⚠ l'exemple chiffré du brief (10 × 10 %, 11 %) n'est pas rejoué tel quel | `/book`, `front/` diapo 7 |
| « Runs on real data » | ✅ mainnet, bloc figé, cache commité, replay du 10/10/2025 | `data/cache/`, `src/risk/replay.py` |
| Scope : analyse de la **qualité des feeds** | ⚠ partiel : mode de prix (marché / fixe / taux interne), bornes Midas, historique Chainlink. **Pas de comparaison âge ↔ heartbeat**, ni de seuil de déviation | `adapters/oracles.py` |
| Scope : vault qui déploie vers un **venue externe (perp)** | ⚠ couvert indirectement (Ethena → exchanges, couche curée) ; la position C du cadrage n'est pas faite | `curated.yaml` |
| Scope : protocole qui **concentre une grosse part de la TVL** | ❌ non traité (on a `tvl_usd` par nœud, mais aucune part de TVL de la chaîne) | — |
| Scope : autres écosystèmes (Solana, Canton, Tempo) | ❌ Ethereum + Morpho seulement. Le tableau Dune contient aussi des vaults **Kamino (Solana)** | — |

---

## 3. Critère par critère

### 3.1 Découverte (30 %) : « depth and correctness »
**Forces (à mettre en avant devant le jury)**
- **Zéro arête dessinée à la main.** Chaque arête porte `source` et preuve (`Contrat.fonction(args) = résultat @ adresse #bloc`). Le validateur refuse le reste.
- **Recalculs indépendants :**
  - l'id du marché est recalculé (keccak) ;
  - le prix de chaque oracle Morpho est recalculé ;
  - les intérêts courus sont recalculés (0,0001 % d'écart avec l'API).
- **Provenance prouvée :** factory des oracles, `isValidMarket` pour le pool Pendle, ENS pour le feed Chainlink.
- **Profondeur :** position → marché → PT → SY → sUSDe → USDe → Ethena → custodians / exchanges, soit 7 sauts. Le brief en montre 5.
- **Le méta-oracle Steakhouse** (seuil 0,75 %, délai 16 h, lus on-chain) : un détail que peu d'équipes trouveront.
- **v2 :** depuis une adresse réelle, 11 poches découvertes, vault V2 → adapters → marchés. Les emprunteurs sont lus un par un.

**Ce qui coûte des points**
1. **Les graphes v2 s'arrêtent au collatéral.** Le vault « Belem RWA EURCV » a 25 nœuds, mais ses seuls émetteurs sont Chainlink, Morpho et RockawayX. Aucun nœud pour :
   - l'émetteur d'**EURCV**, de **mGLOeuro**, de **PST**, de **cbBTC**, de **WBTC**, de **wstETH**, de **weETH** ;
   - leurs custodians ou leurs fonds sous-jacents.

   Or c'est **le book de Belem**, et c'est la couche 2 du brief (« underlying yield source and its issuer »). `curated.yaml` ne couvre que la position A.
2. **Les réserves de l'USDe ne sont pas modélisées.** On a les custodians et les exchanges d'Ethena, mais pas la **composition** des réserves (actifs liquides, LST, stablecoins…).
3. **La voie de sortie n'est pas découverte.** La 2ᵉ jambe (sUSDe → USDC) est une hypothèse à 5 pb (`risk/params.yaml:80`). Les pools secondaires ne sont pas dans le graphe. C'est pourtant là que le glissement explose en crise. Pour mémoire, le cooldown sUSDe (1 jour, lu on-chain) interdit la voie « déstaker ».
4. **Qualité des feeds :** `age_seconds` est lu, mais jamais comparé au heartbeat publié par Chainlink. Le scope du brief cite explicitement « feed-quality analysis ».
5. **`lends` et `collateralized_by`** sont toujours « à confirmer avec les orgas » (`vocab.py`). C'est une question de 30 secondes à poser à un mentor.

### 3.2 Impact (30 %) : « is the number defensible »
**Forces**
- Liquidation **Morpho officielle** (LIF = min(1,15 ; 1/(0,3·LLTV + 0,7)), source citée).
- Le liquidateur n'agit que si c'est rentable **après un glissement mesuré on-chain** (RouterStatic Pendle).
- **Le méta-oracle simulé fidèlement.** La démonstration « 0,93 $ pendant 6 h = 0 $, pendant 24 h = −37 k$ » est le meilleur moment de la démo.
- **Les pertes des prêteurs sont distinguées** de celles de l'emprunteur (exploit Pendle : 152 k$ de dette irrécouvrable sans liquidation). C'est l'insight que le cadrage attend.
- **Chaque paramètre a un statut**, une plage et une tornade de sensibilité. Aucun « score magique ».

**Trois artefacts vérifiés, qu'un expert peut trouver vite**

**A. Liquidation « tout ou rien » : un marché pire réduit la perte (non-monotonie).**
- *Où :* `src/risk/position.py:107-117`. Le liquidateur rembourse 100 % de la dette d'un coup, et ne le fait que si c'est rentable sur ce bloc entier.
- *Ce qu'on a lancé :* le scénario USDe à 0,93 $ pendant 24 h, avec une décote AMM supplémentaire de 3 % (le haut de sa plage de sensibilité).

| Décote AMM supplémentaire | Liquidation | Perte emprunteur |
|---|---|---|
| 0 % | oui | 37 556 $ |
| 3 % (pire marché) | non (« pas rentable ») | **0 $** |

  La même chose se voit dans la tornade : la perte attendue passe de 147 $ à 42 $ quand le marché empire.
- *Pourquoi c'est faux en vrai :* sur Morpho, un liquidateur choisit **la taille** qu'il rembourse. Si tout rembourser n'est pas rentable, une partie l'est souvent, car le glissement est plus faible sur une petite vente.
- *Correctif (≈ 1 h) :* chercher la plus grande fraction remboursée qui reste rentable (grille de 5 % en 5 %), au lieu d'un oui / non sur 100 %.

**B. v2 : un collatéral composite ne reçoit qu'un seul type de choc.**
- *Où :* `src/stacktrace/market_data.py:111` et `:161-164`, `src/stacktrace/risk_engine.py:240`.
- *Ce qui se passe :* si **une** brique de l'oracle est un taux interne, tout le collatéral est classé `rwa_or_synthetic`. Exemple : weETH, pricé par le taux weETH/eETH × ETH/USD.
- *Conséquences dans `docs/api_examples/book.json` :*
  - le même weETH reçoit l'incident `volatile_crash` dans la poche 1 (weETH/RLUSD), mais `rwa_credit_event` (5 %/an, −5 à −50 %) dans la poche 4 (weETH/USDT, 2,56 M$) ;
  - dans la poche 4, **un krach de l'ETH qui déclencherait la liquidation n'est pas modélisé du tout** ;
  - dans le vault RockawayX wETH, on voit même un incident `rwa_credit_event:eth`.
- *Correctif (≈ 1 h 30) :* générer **deux** familles pour un collatéral composite :
  - la composante marché (ETH), que l'oracle suit, donc avec liquidation ;
  - la composante propre (depeg du LST ou du RWA), que l'oracle ne voit pas, donc dette irrécouvrable.

**C. Deux moteurs, deux profondeurs de propagation.**
- **v1** (`src/risk/propagate.py`) propage n'importe quel choc, arête par arête, depuis n'importe quel nœud. Ethena, un custodian, un exchange : tout remonte jusqu'à la position.
- **v2** (`risk_engine.py`) ne génère des incidents que sur le collatéral direct, ses émetteurs directs, les feeds, le protocole et le curateur. Une défaillance « profonde » (sous-jacent d'un PT, réserves d'un stablecoin) est donc fondue dans un `rwa_credit_event` générique.
- **Risque devant le jury :** « Quel est votre moteur ? » Une réponse claire est nécessaire, voir la section 5.

**Autres faiblesses (déjà assumées en partie dans `docs/AUDIT.md`)**
- **Probabilité du titre incohérente avec notre propre modèle.**
  - Le titre dit « EXIT — vous estimez 10 % de chances » d'un depeg USDe −30 % en 7 jours (`risk/scenarios.yaml:21`).
  - Notre Monte Carlo donne ≈ **0,19 %** par semaine pour **toute** la famille « depeg sévère » (λ = 0,1/an).
  - Défendable seulement si on dit clairement que c'est **une probabilité conditionnelle à l'alerte**, saisie par le manager. Aujourd'hui, ce n'est écrit nulle part.
- **Monte Carlo v2 indépendant** (`risk_engine.py:281`) : aucune corrélation entre incidents ni entre poches. Le v1, lui, corrèle par les parents communs.
- **Lenders v2 et collatéral volatil :** la perte est **toujours 0** (« chute progressive »). Un krach éclair (le 10/10/2025, justement) peut sauter la marge 1 − LLTV = 14 %. Il faudrait au moins un cas « gap ».
- **Couche 1 (chaîne) :** l'unique scénario donne 0 $. C'est cohérent (24 h d'arrêt, prix revenus avant l'horizon), mais la couche paraît « gratuite ». Un cas « arrêt + depeg durable » montrerait l'effet.
- **Fréquences d'exploit :** ce sont des hypothèses (dataset DeFiLlama payant). Bien assumé ; p\* protège la décision.

### 3.3 Décision (25 %) : « stay or exit, and why »
**Forces :** p\* est **exactement** l'arbitrage du brief (« exiting is expensive and certain, staying is cheap and uncertain »). Il y a la sortie partielle, une phrase par verdict, le tableau p → verdict lu par le front, et une liquidité de vault limitée (`f_max` = 22 % sortable pour Belem RWA EURCV). Très fort.

**Ce qui manque**
1. **Le coût de sortie est mesuré « à froid ».**
   - Pour S-USDe-30, p\* = 854 $ / 53 133 $ = 1,6 %, avec un pool Pendle intact et une 2ᵉ jambe à 5 pb (`src/risk/scenarios.py:92` : pas de stress de liquidité dans ce scénario).
   - Or le brief dit « **one pocket is affected**. Unwinding it costs 11 % ». C'est le coût de sortie **pendant** l'incident.
   - *Correctif (≈ 1 h) :* afficher p\* sur une plage, « 1,6 % si on sort avant que le marché réagisse, X % si le pool a déjà perdu la moitié de sa liquidité ». On a déjà les facteurs de pool (`exit_model.cost(f, pool_factor)`).
2. **Pas de zone d'indifférence.**
   - La poche 9 (PST/PYUSD, 40 k$) affiche **EXIT** parce que la perte attendue (46 $) dépasse le coût (45 $) de **1 $**.
   - Un manager veut « STAY (indifférent) » quand l'écart est sous un seuil de matérialité. *Correctif :* 20 min.
3. **Vocabulaire différent entre v1 et v2.**
   - v1 : STAY / PARTIAL x % / EXIT.
   - v2 : STAY / EXIT seulement (`analyze.py:141,182`). Sur l'incident mGLOeuro, le v2 dit « EXIT » pour 22 % de la poche.
   - Le cadrage demande « STAY / PARTIAL x % / EXIT ». *Correctif :* 15 min.
4. **La question 5 de Léa** (« combien de temps avant que la liquidité disparaisse ? ») n'a pas de réponse explicite.
   - On a les ingrédients : la fenêtre de 16 h du méta-oracle, et `f_max` du vault, qui baisse si les autres déposants sortent avant nous.
   - Une ligne « vous avez ≈ 16 h avant la bascule de l'oracle », ou « la liquidité retirable est de 22 % et elle se partage avec N autres déposants », serait très parlante.

### 3.4 Démo sur données réelles (15 %)
**Forces :**
- tout est rejouable hors ligne, au même bloc, avec un test qui vérifie que `web/data/` est identique aux sorties ;
- le replay du 10/10/2025 est **un vrai incident**, avec la leçon « la source de l'oracle compte » ;
- un script de démo minuté (`docs/DEMO.md`) et un plan B.

**Risques**
1. **Deux histoires :**
   - « Rayon X » v1 : `web/`, position A, bloc #26162087 ;
   - « Diapositives » v2 : `front/`, book réel, bloc #26162868.

   `docs/DEMO.md` ne parle que du v1. Or le v2 (le book réel du tableau Dune fourni par Belem) est ce qui parlera **le plus** à leur équipe risk.
2. **Le front v2 en mode enregistré** n'a le détail que de 2 poches sur 11 (`front/README.md`). Si le Wi-Fi ou le RPC tombe, 9 poches affichent « calculé en direct ». Le cache en ligne (`data/cache_live/`) est ignoré par git, ce qui va contre la règle « tout est en cache » de `CLAUDE.md`.
3. **Le replay principal du cadrage** (xUSD / deUSD, nov. 2025) n'est pas fait. Le plan B (10/10/2025) l'est : c'est acceptable, mais il faut le dire.
4. **Chiffres de la doc en retard :** « 97 tests » dans `CLAUDE.md:114`, `README.md:119` et `docs/NEXT_STEPS.md:11`, contre **129** aujourd'hui. Un jury qui lance `pytest` le verra.

---

## 4. Le tableau Dune RockawayX fourni par Belem
- **Accès :** impossible depuis cet environnement (le proxy refuse `dune.com`). Je n'ai donc **pas** vérifié son contenu. À faire par un humain : comparer la liste des vaults du tableau avec les 11 poches de `docs/api_examples/book.json`.
- **Sources publiques sur RockawayX :**
  - RockawayX curate des vaults sur **Morpho (Ethereum)** et sur **Kamino (Solana)** ;
  - ses premiers vaults Morpho sont USDC Prime, USDC Yield et wETH.

  Sources : [RockawayX, vaults sur Morpho](https://rockawayx.com/insights/rockawayx-launches-three-curated-vaults-on-morpho), [aperçu de la curation RockawayX](https://rockawayx.com/insights/rockawayx-vault-curation-an-overview-of-products-capabilities), [forum Morpho](https://forum.morpho.org/t/introducing-rockawayx-vaults-on-morpho/2214).
- **Ce qu'on en fait déjà (bien) :**
  - le détenteur `0x4F87…0545`, déposant principal du vault « Belem RWA EURCV » ;
  - 11 poches réelles (26,4 M$) ;
  - les dépendances partagées (Morpho : 11 poches ; Chainlink : 7 ; RockawayX curateur : 4).
- **Ce qui manque :**
  - les vaults **Kamino / Solana** du même curateur (le brief cite Solana dans le scope) ;
  - la confirmation, par Belem, que `0x4F87…` est bien à eux (encore « à confirmer » dans `docs/BACKEND_V2.md`). **Question n°1 à poser au mentor.**
- **Un petit défaut visible :** dans `shared_dependencies`, deux nœuds différents portent le même nom « Chainlink ETH / USD ». Sur la diapo « Concentration », c'est déroutant. Il faut afficher l'adresse courte, ou fusionner.

---

## 5. Les questions que le jury va poser (et la réponse à préparer)
| Question probable | Réponse prête |
|---|---|
| « Vos probabilités d'exploit sortent d'où ? » | « Ce sont des hypothèses affichées, avec une sensibilité ×0,5 / ×2. La décision repose sur **p\***, qui n'en dépend pas. » ✅ |
| « Pourquoi EXIT si vous estimez 10 % ? Votre Monte Carlo dit 0,2 %/semaine. » | ⚠ À préparer : « 10 % est la probabilité **conditionnelle à l'alerte**, saisie par le manager. Sans alerte, on dit STAY. » L'écrire aussi dans le front. |
| « Votre perte baisse quand le marché empire ? » | ❌ Aujourd'hui, pas de bonne réponse → correctif A. |
| « Si l'USDe est déjà à 0,93, sortir coûte toujours 854 $ ? » | ⚠ → correctif 3.3-1 (p\* sur une plage, avec le pool stressé). |
| « V = 53 k$ ou 410 k$ ? » | « Le capital net : c'est ce que le fonds a alloué à la poche. Avec un levier ×7,7, LGI = 100 %. » La réponse existe, mais elle n'est pas validée par les mentors (`NEXT_STEPS.md`). |
| « v1 ou v2, c'est quoi votre moteur ? » | Proposition : « v1 = la profondeur (propagation arête par arête, sur l'exemple exact du brief) ; v2 = le passage à l'échelle sur le **vrai book**. Même découverte, mêmes preuves, même règle p\*. » |
| « Ça marche sur Solana ? » | « Non, et c'est assumé : Ethereum + Morpho couvrent 11 poches réelles. L'architecture adaptateur par protocole est faite pour en ajouter. » |
| « Qui vous dit que les custodians d'Ethena sont ceux-là ? » | « La couche curée : URL officielle + date, sur chaque ligne. Les poids sont à 1,0 (borne haute) et c'est écrit dans la preuve. » ✅ |

---

## 6. Plan d'action priorisé
Les rôles suivent le cadrage : **P1** = Découverte, **P2** = Moteur de risque, **P3** = Démo et récit. Chaque correctif touche une zone de code et se teste seul.

### P0 : avant le gel (≈ 5 h en tout, à se répartir)
| # | Qui | Quoi | Effort | Gain |
|---|---|---|---|---|
| 1 | P2 | **Liquidation partielle rentable** (artefact A) + un test de monotonie : « perte(marché pire) ≥ perte(marché normal) » | 1 h | Impact |
| 2 | P2 | **Collatéral composite en v2** : deux familles (marché + propre) (artefact B) + un test sur un oracle weETH | 1 h 30 | Impact |
| 3 | P2 | **p\* sur une plage** : coût de sortie normal et stressé (pool ÷2), affiché dans le titre et sur la diapo Verdict | 1 h | Décision |
| 4 | P2 | **Zone d'indifférence** + label **PARTIAL** en v2 | 30 min | Décision |
| 5 | P3 | **Un seul fil de démo :** Rayon X (position A, 3 min) → bascule « et sur le vrai book de Belem » (front v2, 1 min 30). Mettre à jour `DEMO.md` | 45 min | Démo |
| 6 | P3 | **Enregistrer les 11 poches** (`/risk` et `/graph` de chacune) dans `docs/api_examples/` pour le mode hors ligne du front v2 | 30 min (avec un RPC) | Démo |
| 7 | P3 | **Doc à jour :** 129 tests ; « p = probabilité conditionnelle à l'alerte » dans le front et le README | 15 min | Démo |

### P1 : si le temps le permet
| # | Qui | Quoi | Effort |
|---|---|---|---|
| 8 | P1 | **Couche curée pour les actifs du book Belem.** Émetteur, et custodian si publié, pour EURCV, mGLOeuro, PST, cbBTC, WBTC, wstETH, weETH. Chaque ligne : URL officielle + date, cochée dans `VERIFY.md` | 1 h 30 |
| 9 | P1 | **Qualité des feeds :** heartbeat et seuil de déviation (doc Chainlink, ligne curée sourcée) comparés à `age_seconds`, avec un drapeau « feed en retard » | 1 h |
| 10 | P1 | **Concentration de TVL** (scope du brief) : part de la TVL de la chaîne pour Morpho, Pendle, Ethena, via l'API publique DeFiLlama (endpoint à vérifier dans leur doc, réponse mise en cache) | 1 h |
| 11 | P2 | **Rejouer l'exemple du brief** : 10 poches × 10 %, sortie à 11 %. Montrer que p\* = 11 % / LGI. Une ligne de plus dans la diapo Verdict | 30 min |

### P2 : à dire au jury plutôt qu'à coder aujourd'hui
- Le replay xUSD / deUSD (il faut un RPC archive).
- Kamino / Solana.
- Les corrélations entre poches en v2 (réutiliser la logique « parents communs » du v1).
- Une calibration publique des fréquences d'exploit.
- La fusion des deux moteurs.

---

## 7. Questions encore ouvertes pour les mentors Belem
1. L'adresse `0x4F87…0545` (déposant principal de « Belem RWA EURCV ») est-elle bien la vôtre ?
2. Horizon de décision : 24 h ou 7 jours ? (aujourd'hui : 7 jours, hypothèse)
3. Taille de poche **V** : le capital net (53 k$) ou la valeur brute (410 k$) ?
4. L'extension `lends`, et la direction `collateralized_by` (« est collatéral de », lu à l'envers) : acceptées ?
5. p\* vous parle-t-il plus qu'une probabilité qu'on estimerait nous-mêmes ?
6. Le tableau Dune RockawayX : quelles poches voulez-vous voir en priorité, Morpho ou Kamino ?
