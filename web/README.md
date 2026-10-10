# Front « Rayon X »

Une page statique : HTML + CSS + JavaScript natif (modules ES), **sans étape de build et sans aucune bibliothèque
externe**. Elle marche hors ligne.

## Lancer
```bash
PYTHONPATH=src python -m risk.run          # moteur de risque → output/risk_report.json + risk_grid.json
PYTHONPATH=src python -m risk.export_web   # copie les données dans web/data/ (+ view.json)
python -m http.server 8000 -d web          # puis http://localhost:8000
```
Ouvrir `index.html` en double-clic ne marche pas : le navigateur interdit le chargement de fichiers JSON locaux.

Raccourcis d'URL (pratiques pour la démo) : `#mode=scenario`, `#mode=impact&node=binance`, `#scenario=S-USDe-30`,
`#node=usde`, `#replay=R-OCT2025`.

## Principe : le front ne calcule AUCUN risque
Il lit 4 fichiers produits par Python (`web/data/`) :
- `graph.json` : le graphe prouvé (découverte) ;
- `risk_report.json` : scénarios, Monte Carlo, décision, replays, paramètres ;
- `risk_grid.json` : la grille prix USDe × durée, pré-calculée pour les curseurs ;
- `view.json` : les couches (« vertèbres »), les libellés courts et les textes vulgarisés.

Le seul calcul fait en JavaScript est un parcours de graphe : en mode Impact, il cherche tout ce qui dépend d'un nœud.
Ce n'est pas un calcul de risque. Un test (`tests/risk/test_web_data.py`) vérifie que `web/data/` est identique aux
sorties du moteur et que la page ne charge aucune ressource distante.

## Fichiers
| Fichier | Rôle |
|---|---|
| `index.html` | structure : barre du haut, constantes vitales, film (squelette), panneau, dock |
| `css/xray.css` | direction artistique : fond noir bleuté, os cyan, fractures magenta, grain de film, grille de calibration |
| `js/data.js` | chargement, format français des nombres, parcours de graphe (ancêtres, chemin) |
| `js/skeleton.js` | mise en page en couches et dessin SVG ; états visuels (sélection, surbrillance, fracture) |
| `js/panels.js` | constantes vitales, fiche de risque, fiche de l'os, scénario, impact, replay |
| `js/dock.js` | cartes de scénarios et curseurs |
| `js/tour.js` | parcours guidé « Explique-moi » (7 étapes) |
| `js/effects.js` | ligne de scan, texte qui se « décrypte », grain de film |
| `js/main.js` | état de l'application et branchements |

## Pourquoi aucune bibliothèque de graphe (ni D3 ni Cytoscape) ?
1. Le graphe est petit (~30 nœuds) et sa mise en page est **sémantique** (une couche = une vertèbre). Un algorithme maison de 40 lignes suffit, et il reste lisible pour des débutants.
2. Zéro dépendance, c'est zéro fichier à vendoriser, zéro licence à suivre, zéro risque de CDN pendant la démo.
3. Le SVG natif donne un contrôle total sur la direction artistique : halos, fractures animées, badges de preuve.

## Pourquoi pas React Bits ?
React Bits (licence « MIT + Commons Clause ») fournit des composants **React**. Il faut donc React, souvent GSAP ou
three.js, et une étape de build (JSX). Cela contredit deux contraintes du projet : pas de build, et une démo 100 % hors
ligne sans CDN. Les deux effets qui nous intéressaient (texte qui se décrypte, grain de film) ont donc été **réécrits
de zéro en JS natif** dans `effects.js`, dans le même esprit. Pour passer un jour à React, il faudrait ajouter
Vite et copier les composants voulus en respectant leur licence.

## Accessibilité
- `prefers-reduced-motion` : plus d'animation (ni scan ni fracture animée), tout est visible immédiatement.
- Les nœuds sont focusables au clavier (Tab, puis Entrée).
- Contraste clair sur fond sombre. Mise en page en une colonne sous 900 px (testée à 375 px).
