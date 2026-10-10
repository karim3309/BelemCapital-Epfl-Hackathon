# Prompt pour finir le projet (parties 2 et 3 + front « Rayon X »)

## Avant de lancer
1. **Mettez le brief Belem dans le repo** sous `docs/BRIEF.md` (copier-coller du texte, ou le PDF dans `docs/`). Le prompt s'appuie dessus pour savoir exactement ce que demandent les parties 2 et 3. Sans brief, il partira de l'hypothèse écrite plus bas et vous le signalera.
2. Ouvrez une session Claude Code sur le repo, branche `feature/discovery-position-a` à jour, en effort maximal.
3. Collez **tout le bloc ci-dessous**.

---

```text
Tu es le Tech Lead de l'équipe StackTrace (hackathon Belem DeFi Risk). Tu travailles EN AUTONOMIE pendant une
longue session : l'équipe (3 débutants) lit pendant ce temps et reviendra ensuite tout comprendre et affiner.
Ton objectif : livrer les PARTIES 2 ET 3 du projet, avec un front « Rayon X » démontrable hors ligne.

══════════════════════════════════════════════════════════════════════════════
0. LIRE AVANT TOUT (ne saute rien)
══════════════════════════════════════════════════════════════════════════════
- CLAUDE.md en entier (règles, vocabulaire FIGÉ, méthode), README.md, docs/GUIDE_DEBUTANT.md,
  docs/POSITION_A.md, docs/CONTRACT.md, docs/AUDIT.md, docs/NEXT_STEPS.md, puis output/graph.json.
- docs/BRIEF.md (ou le PDF du brief dans docs/) : c'est LA référence pour le contenu exact des parties 2 et 3
  et pour les critères de notation. Résume-moi en 10 lignes ce que demandent les parties 2 et 3 et comment
  elles sont notées, puis continue sans attendre.
- S'il n'y a PAS de brief : pars de l'hypothèse suivante, écris-la en tête de docs/PARTS_2_3.md, et signale-la
  dans ton rapport final :
    Partie 2 = moteur de risque : propager des chocs dans le graphe et mesurer l'effet sur la position ;
    Partie 3 = restitution : une interface qui rend le graphe, les preuves et les scénarios compréhensibles.

══════════════════════════════════════════════════════════════════════════════
1. RÈGLES NON NÉGOCIABLES
══════════════════════════════════════════════════════════════════════════════
- Le Module de Découverte (src/discovery/, output/graph.json, data/cache/) est TERMINÉ et son contrat JSON est
  FIGÉ. Tu le CONSOMMES, tu ne le modifies pas. Exception : un vrai bug, que tu corriges avec un test et que
  tu notes dans docs/AUDIT.md.
- Zéro hallucination, comme pour la découverte :
  · aucune adresse ni endpoint sorti de ta mémoire ;
  · AUCUN paramètre de risque inventé (bonus de liquidation, formules Morpho, seuils...). Chaque paramètre vit
    dans un fichier risk/params.yaml avec, au choix :
      `source: <URL officielle>` (doc Morpho, Pendle, Ethena, Chainlink, Steakhouse...) + `as_of`, ou
      `source: onchain` (déjà dans graph.json, on cite le champ), ou
      `hypothesis: true` + une justification en une phrase (paramètre de scénario choisi par nous).
    Le front affiche ces trois statuts différemment. Un chargeur strict refuse un paramètre sans statut.
  · Exemple : la formule d'incitation de liquidation de Morpho Blue (fonction du LLTV) doit être trouvée dans
    la doc ou le code officiel de Morpho, avec l'URL. Ne la recopie pas de mémoire.
- Tout doit marcher HORS LIGNE pour la démo : aucun CDN au runtime, aucune police distante, aucun appel réseau
  depuis le front. Les bibliothèques JS sont copiées dans le repo (vendor) avec leur version et leur licence.
- Stack : Python 3.11 (moteur de risque, comme la découverte : web3.py n'est PAS nécessaire, on lit graph.json),
  networkx. Front statique : HTML + CSS + JavaScript sans étape de build, servi par `python -m http.server`.
  Une seule bibliothèque de graphe vendorisée au maximum (ex. D3 ou Cytoscape.js, version figée).
  Justifie ton choix en 3 lignes.
- Pédagogie (CLAUDE.md) : chaque module commence par une docstring qui explique le concept comme dans
  GUIDE_DEBUTANT.md (analogies, zéro jargon non défini). Pas de gros blocs opaques.
- Git : nouvelle branche feature/risk-and-xray depuis feature/discovery-position-a. Commits petits et
  fréquents, avec un message clair. Push à la fin (et à chaque grosse étape). Ne touche pas à main.

══════════════════════════════════════════════════════════════════════════════
2. PARTIE 2 — MOTEUR DE RISQUE (src/risk/)
══════════════════════════════════════════════════════════════════════════════
But : répondre à « si TEL choc arrive, que devient la position A ? », en s'appuyant UNIQUEMENT sur graph.json
et risk/params.yaml.

2.1 Modèle de propagation (src/risk/propagate.py)
  - Un choc = (nœud ciblé, nature, intensité, durée). Il se propage À CONTRE-COURANT des flèches (convention
    du projet : from = dépendant, to = dépendance).
  - Une règle par type d'arête, documentée et testée :
      redeemable_into : la valeur du `from` suit celle du `to` (× taux interne lu dans meta) ;
      issued_by / deployed_in vers le hors-chaîne : un choc d'émetteur ou de contrepartie se traduit en
        dépréciation de l'actif émis (intensité = paramètre de scénario, hypothesis: true) ;
      priced_by : un oracle ne transmet le choc QUE selon son pricing_mode (market transmet, fixed ne
        transmet pas, internal_rate transmet seulement un choc sur le taux, hybrid = logique du méta-oracle) ;
      collateralized_by / lends : le marché encaisse la variation du collatéral / de l'actif prêté.
  - MÉTA-ORACLE : simule fidèlement la règle sourcée dans meta.switch_rule (seuil deviationThreshold, timelock
    challenge, healing), avec la formule d'écart de la doc Steakhouse. C'est LE point fort de notre analyse :
    la durée du choc compte autant que son ampleur.
  - Aucune mise en cache réseau n'est nécessaire (pas d'appel réseau), mais le calcul doit être déterministe.

2.2 Effet sur la position (src/risk/position.py)
  - À partir de meta.position : nouveau prix oracle → nouveau health factor → liquidable oui/non.
  - Si liquidable : perte estimée = bonus de liquidation (formule SOURCÉE) + coût de sortie du collatéral.
  - Coût de sortie : glissement de prix sur le pool Pendle. Commence par un modèle simple et documenté
    à partir de reserve_pt / reserve_sy (dis honnêtement que c'est une approximation). Si tu as le temps,
    remplace-le par une simulation ON-CHAIN via le RouterStatic de Pendle : adresse et nom de fonction trouvés
    dans la doc officielle, appel fait via le cache de la découverte (prompt S2 de docs/NEXT_STEPS.md).
  - Côté prêteurs aussi : dette potentiellement irrécouvrable (collatéral × vrai prix < dette) quand l'oracle
    est fixe et ne voit pas le choc.

2.3 Scénarios (risk/scenarios.yaml), au minimum :
  - S-USDe : depeg de l'USDe à {0,99 ; 0,98 ; 0,95 ; 0,93 ; 0,90 ; 0,85} $ × durée {1 h ; 6 h ; 16 h ; 24 h ; 72 h} ;
  - S-EXCH : défaillance d'un exchange de hedge d'Ethena (Binance seul, puis plusieurs) → dépréciation
    hypothétique de l'USDe (paramètre hypothesis: true, bien affiché) ;
  - S-CUST : défaillance d'un custodian (Copper / Ceffu / Fireblocks) ;
  - S-ORACLE : feed Chainlink USDe/USD figé ou faux ;
  - S-POOL : liquidité du pool Pendle divisée par 2 / par 10 ;
  - S-USDC : depeg de l'USDC (l'actif emprunté) ;
  - S-TIME : simple passage du temps jusqu'à l'échéance (le PT converge vers 1, la dette accrue au borrow_apy).

2.4 Sorties
  - output/risk.json : contrat que tu définis, documenté dans docs/RISK_CONTRACT.md (champs, unités, sens).
    Pour chaque scénario : chemin de propagation (liste d'arêtes du graph.json, avec leurs preuves), prix oracle
    avant/après, health factor avant/après, liquidable, perte estimée, qui perd (emprunteur / prêteurs),
    et la liste des paramètres utilisés avec leur statut (source / onchain / hypothesis).
  - output/risk_grid.json : la grille USDe (prix × durée) précalculée, pour alimenter le curseur du front.
  - Un score de risque synthétique UNIQUEMENT si le brief le demande. Sinon, n'en fabrique pas : expose des
    métriques claires.
  - CLI : `python -m risk.run` (lit output/graph.json, écrit output/risk*.json, affiche un résumé en français).
  - Validateur de risk.json (comme discovery/validate.py) lancé à chaque run.

2.5 Tests (tests/risk/)
  - règles de propagation unitaires (petits graphes faits main) ;
  - méta-oracle : choc court → pas de bascule ; choc long → bascule ; healing ;
  - cohérence : choc nul → HF inchangé ; HF après bascule = HF × (prix secours / prix primaire) ;
  - les seuils de POSITION_A.md (bascule dès que USDe < ~0,9925 $ ; liquidation sous ~0,9525 $ après 16 h)
    doivent sortir NATURELLEMENT du moteur. Sinon, trouve qui a tort (le moteur ou le doc) et corrige.

══════════════════════════════════════════════════════════════════════════════
3. PARTIE 3 — FRONT « RAYON X » (web/)
══════════════════════════════════════════════════════════════════════════════
Concept : on passe la position A « aux rayons X ». Ce qui a l'air d'être un simple dépôt + un emprunt révèle
son SQUELETTE : toutes les couches cachées jusqu'à Ethereum et aux entreprises hors chaîne.

Direction artistique :
  - fond quasi noir bleuté, traits et nœuds en cyan / blanc lumineux (lueur, « glow »), légère texture de
    film radiographique, grille de calibration discrète, typographie mono pour les données ;
  - une LIGNE DE SCAN horizontale qui balaie l'écran au chargement et révèle les couches une à une, de haut en
    bas : Position → Marché Morpho → Oracle(s) → PT / pool Pendle → SY → sUSDe → USDe → Ethena → custodians /
    exchanges → Ethereum ;
  - une mise en page en COUCHES HORIZONTALES (comme des vertèbres), pas un graphe « boule de spaghetti » :
    la profondeur de dépendance se lit de haut en bas ;
  - code couleur de la PREUVE sur chaque arête : onchain = trait plein lumineux, api = pointillés,
    curated = trait fin ambré + icône « document daté » ;
  - code couleur du PRIX sur les oracles : fixed / market / internal_rate / hybrid (légende visible) ;
  - quand un scénario est actif, les « fractures » apparaissent en rouge/magenta et se propagent le long du
    chemin, comme une fissure sur une radio.
  - Respecte prefers-reduced-motion (pas d'animation si l'utilisateur la refuse) et un contraste lisible.

Fonctionnalités (dans cet ordre de priorité) :
  1. Vue « squelette » du graph.json : survol = nom en clair ; clic = panneau latéral « fiche de l'os » :
     explication vulgarisée du type de nœud (texte repris du glossaire de GUIDE_DEBUTANT.md), meta utiles
     (prix, TVL, mode de prix, proxy upgradeable ?), et la liste des arêtes avec leur PREUVE complète
     (lien Etherscan pour les adresses, URL cliquable pour api/curated, numéro de bloc).
  2. Bandeau « constantes vitales » de la position : HF, LTV / LLTV, distance à la liquidation, valeur,
     dette, bloc de la photo et date.
  3. Mode SCÉNARIO : un curseur prix USDe + un curseur durée, branchés sur risk_grid.json (aucun calcul de
     risque dans le JS : il lit seulement les résultats du moteur Python, source de vérité unique). Affiche
     l'état de l'arbitre du méta-oracle (primaire / challenge en cours / basculé), le HF, et
     « LIQUIDÉ / pas liquidé / prêteurs exposés ».
  4. Mode IMPACT : on clique un nœud (ex. Binance), « que se passe-t-il s'il casse ? », et le chemin vers la
     position s'illumine (ancêtres calculés depuis graph.json).
  5. Liste des scénarios de risk.json (cartes) ; clic = la fracture s'anime sur le squelette.
  6. Mode « Explique-moi » : un parcours guidé en 6-8 étapes qui raconte l'histoire d'Alice (GUIDE_DEBUTANT
     §9) en surlignant les couches. C'est ce qu'on montrera au jury.
- Données : le front charge output/graph.json, output/risk.json et output/risk_grid.json (copiés ou servis
  depuis web/data/ par un petit script `python -m risk.export_web`). Si un fichier manque, message clair.
- Lancer : `python -m http.server 8000 -d web` → http://localhost:8000. Doc dans web/README.md.
- Vérifie VISUELLEMENT avec le navigateur intégré : captures d'écran du chargement, de la vue complète, d'un
  clic sur un nœud, d'un scénario USDe 0,93 $ / 24 h, du mode impact Binance, et en largeur mobile (375 px).
  Corrige ce qui est moche, illisible ou qui déborde. Garde 3-4 captures dans docs/screens/ pour le README.

══════════════════════════════════════════════════════════════════════════════
4. MÉTHODE DE TRAVAIL (obligatoire)
══════════════════════════════════════════════════════════════════════════════
- Ordre : (a) moteur de risque minimal + tests → (b) risk.json + grille → (c) front squelette + fiche de l'os
  → (d) scénarios + impact → (e) parcours guidé + polish visuel → (f) docs et démo.
  Le front doit être montrable dès la fin de (c), au cas où le temps manque.
- Après CHAQUE étape : AUDIT de tout le projet au regard du brief, de CLAUDE.md et de ce prompt (paramètre
  non sourcé ? preuve perdue en route ? contrat cassé ? test manquant ? front qui appelle le réseau ? texte
  incompréhensible pour un débutant ?). Corrige, puis note l'audit dans docs/AUDIT.md (même format que les
  audits 1 à 4). Recommence jusqu'à ce que l'audit ne trouve plus rien d'important.
- `python -m pytest` doit rester vert du début à la fin (les 67 tests de la découverte compris).
- Avant le push final : simulation d'un coéquipier, avec un clone neuf, sans réseau → tests, `python -m risk.run`,
  front servi en local, tout marche.

══════════════════════════════════════════════════════════════════════════════
5. LIVRABLES ATTENDUS
══════════════════════════════════════════════════════════════════════════════
- src/risk/ (+ tests), risk/params.yaml, risk/scenarios.yaml, output/risk.json, output/risk_grid.json
- web/ (index.html, css, js, vendor/ avec versions et licences, README.md)
- docs/PARTS_2_3.md : ce que demandent les parties 2 et 3 (d'après le brief) → ce qu'on a fait → où c'est
- docs/RISK_CONTRACT.md, docs/DEMO.md (script de démo de 5 minutes, commandes PowerShell ET bash, quoi dire
  à chaque écran), docs/screens/
- docs/GUIDE_DEBUTANT.md complété par 2 nouveaux chapitres dans le MÊME style très vulgarisé :
  « Comment on mesure le risque » et « Comment lire le Rayon X »
- README.md mis à jour (captures, commandes), docs/AUDIT.md complété
- Rapport final dans le chat : ce qui est fait, ce qui ne l'est pas, les hypothèses (paramètres
  hypothesis: true), les décisions à faire valider par l'équipe, et les 5 points les plus importants à
  comprendre pour la soutenance.
```

---

## Ce que ce prompt garantit (et pourquoi il est écrit comme ça)
- **Le brief fait foi.** Je ne connais pas le texte exact des parties 2 et 3. Le prompt oblige donc à le lire d'abord, et sinon à écrire noir sur blanc l'hypothèse retenue.
- **Pas d'hallucination côté risque non plus.** Chaque chiffre du moteur a un statut visible : sourcé, on-chain ou hypothèse. Le jury verra la même rigueur que dans la découverte.
- **Une seule source de vérité.** Le Python calcule, le front affiche. Pas de deuxième moteur de risque caché dans le JavaScript.
- **Démo à l'abri des pannes.** Tout fonctionne hors ligne, y compris les bibliothèques JS.
- **Un front montrable tôt.** L'ordre de travail permet d'avoir quelque chose à montrer même si la session est coupée.
- **Vous gardez la main.** Le guide débutant est complété, la démo est écrite, et le rapport final liste ce que vous devez valider.
