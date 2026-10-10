# Script de démo (5 minutes) : « à 3 h du matin, Léa n'a qu'une question »

Fil rouge : les questions de Léa, risk manager d'astreinte (cadrage §1).
1. Suis-je exposée, et par quel chemin ?
2. Combien je peux perdre ?
3. Combien coûte la sortie ?
4. Je sors tout, une partie, ou j'attends ?

Chiffres : réponses réelles enregistrées au bloc **#26162868** (`docs/api_examples/`), rejouées **sans réseau**.

## Avant la démo (une fois)
```bash
python -m pytest -q
```
```bash
cd front && npm install && npm run dev
```
Ouvrir http://localhost:5173 en plein écran (1280 px ou plus). La pastille en haut à droite doit dire **Enregistré**.
**Coupez le Wi-Fi** : tout doit marcher.

Option « en direct » (RPC requis, `/book` prend ~1 min 30 au premier appel) : `PYTHONPATH=src python -m stacktrace.api`,
puis choisir « direct » dans la pastille. À ne faire qu'après avoir préchauffé l'API.

---

## 0:00 — Le portefeuille (30 s)
**Écran :** diapositive 1, 11 poches, 26,4 M$.
**À dire :** « On part d'une seule adresse réelle. L'outil trouve toutes ses poches, et chaque montant est prouvé on-chain
au même bloc. Le brief parle d'un book en dix poches : en voici un vrai. »

## 0:30 — Le verdict d'une poche (40 s) — *Décision, 25 %*
**Action :** poche **Belem RWA EURCV**, diapositive 2.
**À dire :** « STAY. Sortir maintenant coûte 643 $, mais seuls 22 % de la poche sont retirables tout de suite. Le seuil :
sortez si vous croyez à plus de 0,6 % au risque principal. »

## 1:10 — Par quel chemin ? (60 s) — *Découverte, 30 %*
**Action :** diapositive 3, survoler le marché mGLOeuro, cliquer une arête pour afficher sa preuve.
**À dire :** « Le graphe est construit par le code : vault, adapters, marchés, collatéraux, oracles. Chaque arête porte sa
preuve : contrat, fonction, résultat, bloc. Et il révèle la concentration cachée : 85,8 % du vault est prêté contre un seul
collatéral, mGLOeuro, dont le prix est posé par un administrateur. Il ne suit pas le marché. »

## 2:10 — Combien je perds, combien coûte la sortie (50 s) — *Impact, 30 %*
**Action :** diapositives 4 et 5.
**À dire :** « Si mGLOeuro perd de la valeur, son oracle ne bouge pas : personne n'est liquidé à temps, et c'est la dette
irrécouvrable des emprunteurs que paient les prêteurs, calculée emprunteur par emprunteur. »
**Action :** passer (→) à la poche **Emprunt USDC contre PST**, diapositive 5.
**À dire :** « Ici, la sortie coûte 13 % du capital, et au-delà de 25 % de la dette le marché ne peut plus absorber la
vente. C'est l'arbitrage du brief : sortir coûte cher et c'est certain ; rester coûte peu, mais c'est incertain. »

## 3:00 — Et si ça arrive ? (70 s) — *Décision, 25 %*
**Action :** revenir à **Belem RWA EURCV**, diapositive 6, incident « Chute du collatéral mGLOeuro », sévérité 30 %.
Monter « votre probabilité » de 0 à 20 %.
**À dire :** « On ne demande pas à Léa d'estimer une perte : on lui demande si elle croit à plus de p\*. Au-dessus du seuil,
le verdict bascule en EXIT, et seulement pour la part sortable maintenant : 22 %. »

## 4:10 — La concentration (30 s)
**Action :** diapositive 7.
**À dire :** « Morpho est présent dans les 11 poches, Chainlink ETH/USD dans 4, Circle dans 4 : une même dépendance
cachée dans plusieurs poches. »

## 4:40 — Phrase de fin (20 s)
« Chaque chiffre a un statut : sourcé, on-chain, ou hypothèse affichée. Nos probabilités sont des hypothèses : c'est pour
ça que la décision repose sur p\*. À 3 h du matin, Léa n'a qu'une question : est-ce que je crois à plus de p\* ? »

---

## Plan B si quelque chose plante
- Page blanche → vérifier que `npm run dev` tourne, recharger ; forcer `http://localhost:5173/?source=recorded`.
- Plus rien ne marche → en terminal : `PYTHONPATH=src python -m risk.run` (fiche de risque de la position A, hors ligne).
