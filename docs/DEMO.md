# Script de démo (5 minutes) : « à 3 h du matin, Léa n'a qu'une question »

Fil rouge : les questions de Léa, risk manager d'astreinte (cadrage §1).
1. Suis-je exposée, et par quel chemin ?
2. Combien je peux perdre ?
3. Combien coûte la sortie ?
4. Je sors tout, une partie, ou j'attends ?

Chiffres : bloc #26162087 (10/10/2026, 12:39 UTC), rejoué **sans réseau**.

## Avant la démo (une fois)
PowerShell :
```powershell
$env:PYTHONPATH="src"; python -m pytest -q; python -m risk.run; python -m risk.export_web
```
bash :
```bash
PYTHONPATH=src python -m pytest -q && PYTHONPATH=src python -m risk.run && PYTHONPATH=src python -m risk.export_web
```
Puis, dans un terminal laissé ouvert :
```bash
python -m http.server 8000 -d web
```
Ouvrir http://localhost:8000 (en plein écran, 1280 px ou plus). **Coupez le Wi-Fi** : tout doit marcher.

---

## 0:00 — Le problème (20 s)
**Écran :** la page se charge, la ligne de scan descend et révèle les couches.
**À dire :** « Une position DeFi, c'est une ligne dans un portefeuille. Celle-ci : un PT Pendle en gage sur Morpho, un emprunt
en USDC. Passons-la aux rayons X. »

## 0:20 — Le graphe prouvé (60 s) — *Découverte, 30 %*
**Écran :** le squelette. Survolez la légende : trait plein = on-chain, pointillé = API, ambre ▤ = curé.
**Action :** cliquez sur le nœud **USDe**, puis faites défiler la fiche jusqu'aux preuves.
**À dire :** « 28 nœuds et 45 arêtes, découverts par le code à partir d'un seul identifiant de marché. Chaque arête porte sa
preuve : contrat, fonction, résultat, numéro de bloc. Ce qui n'est pas on-chain (les coffres et les exchanges d'Ethena) est
curé : lien officiel et date. Rien n'est dessiné à la main. »

## 1:20 — Le cœur : l'oracle et la durée (70 s) — *Impact, 30 %*
**Action :** bouton **Scénario**. Curseur prix sur **0,93 $** et durée sur **6 h**, puis sur **24 h**.
**À dire :** « L'oracle du marché est un méta-oracle. En temps normal, il donne un prix fixé par une formule. Il ne passe au prix
de marché que si l'écart dépasse 0,75 % pendant 16 heures : ces deux paramètres sont lus on-chain. À 0,93 $ pendant 6 h, rien ne
se passe. Le même prix pendant 24 h, et on est liquidé : 37 000 $ perdus. **La durée compte autant que l'ampleur.** »
**Action :** carte **S-PENDLE-EXPLOIT** (mode Squelette, en bas).
**À dire :** « L'inverse : un exploit Pendle. L'oracle fixe ne voit rien, personne n'est liquidé… et ce sont les prêteurs qui
portent un trou de 152 000 $. C'est exactement le risque caché que Belem cherche. »

## 2:30 — Le replay d'un vrai incident (40 s) — *Démo sur données réelles, 15 %*
**Action :** dans le dock, **Replay 10 octobre 2025**.
**À dire :** « Le 10 octobre 2025, l'USDe est tombé à 0,65 $ sur Binance pendant une quarantaine de minutes. On-chain, Chainlink
n'est jamais descendu sous 0,9929 $ : on l'a relu round par round. Notre oracle tient, un oracle branché sur Chainlink aussi. Un
oracle branché sur le prix de Binance nous aurait liquidés. **La source de l'oracle compte.** »

## 3:10 — La décision (70 s) — *Décision, 25 %*
**Action :** bouton **Squelette**, puis lien **Fiche de risque**.
**À dire :** « Alerte : l'USDe perd 30 % durablement. Sortir maintenant coûte 854 $ : c'est certain, mesuré en simulant la vente
sur le vrai pool Pendle. Rester coûte 53 000 $ si l'incident arrive, toute la poche, et les prêteurs perdent 78 000 $ de plus.
Le seuil vaut **p\* = 1,6 %**. »
**Action :** cliquez sur un des **3 chemins les plus coûteux** : la fracture se dessine.
**Action :** mode **Scénario**, curseur « votre probabilité » de 1 % à 5 % : le verdict passe de STAY à PARTIAL puis EXIT.
**À dire :** « On ne demande pas à Léa d'estimer une perte : on lui demande si elle croit à plus de 1,6 %. Et la réponse n'est
pas toujours tout ou rien : le glissement croît plus vite que la taille, donc on sort parfois une partie. »

## 4:20 — La rigueur (30 s)
**Action :** fiche de risque, sections **Hypothèses** et **Sensibilité**.
**À dire :** « Chaque chiffre a un statut : sourcé, on-chain, ou hypothèse assumée. Le dataset de hacks étant payant, nos
fréquences d'exploit sont des hypothèses, et on le dit. C'est pour ça que la décision repose sur p\*, qui n'en dépend pas. »

## 4:50 — Phrase de fin (10 s)
« À 3 h du matin, Léa n'a qu'une question à se poser : est-ce que je crois à plus de 1,6 % de risque ? »

---

## Plan B si quelque chose plante
- La page ne charge pas → `python -m risk.export_web`, puis rechargez. N'ouvrez pas `index.html` en double-clic (le navigateur
  bloque les fichiers locaux) : passez par `http.server`.
- Plus rien ne marche → montrez `docs/screens/` (captures) et lancez dans le terminal :
  `PYTHONPATH=src python -m discovery.inspect_graph --impact binance`, puis `PYTHONPATH=src python -m risk.run`.
- Parcours guidé automatique : bouton **Explique-moi** (7 étapes, l'histoire d'Alice).
