"""StackTrace — Risk engine (parts 2 and 3 of the brief).

It reads ONLY three things:
  - output/graph.json        : the proven graph produced by the Discovery module;
  - output/risk_inputs.json  : a few extra on-chain reads (Pendle sale simulations,
                               Chainlink history, gas), made at the SAME block as the graph;
  - risk/params.yaml, risk/scenarios.yaml : our parameters, each with its status
                               (sourced / on-chain / hypothesis).

And it answers the brief's question: "should we stay or exit, and why?".
Entry point: `python -m risk.run`.
"""
