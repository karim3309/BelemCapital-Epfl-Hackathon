"""StackTrace — Moteur de risque (parties 2 et 3 du brief).

Il ne lit QUE trois choses :
  - output/graph.json        : le graphe prouvé produit par le Module de Découverte ;
  - output/risk_inputs.json  : quelques lectures on-chain en plus (simulations de vente Pendle,
                               historique Chainlink, gas), faites au MÊME bloc que le graphe ;
  - risk/params.yaml, risk/scenarios.yaml : nos paramètres, chacun avec son statut
                               (sourcé / on-chain / hypothèse).

Et il répond à la question du brief : « faut-il rester ou sortir, et pourquoi ? ».
Point d'entrée : `python -m risk.run`.
"""
