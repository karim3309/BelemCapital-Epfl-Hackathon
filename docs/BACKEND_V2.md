# Backend v2: from a real address to STAY / EXIT

This backend answers the question of the Belem brief, on **real, live data**:

> "Does the expected loss from staying in this position justify exiting it, despite the exit cost?"

It replaces the single position hard-coded in `config.yaml` (position A) with **any real holder**. The v1 code (`src/discovery`, `src/risk`, position A, offline demo) is untouched and its tests still pass.

## What is a "position"?
It is **one row of a holder's portfolio**, a "pocket" in the sense of the brief ("a book split across ten pockets"). We start from **the holder's address**, and the tool finds all of its pockets. The test address comes from the Dune dashboard provided by Belem ([RockawayX vaults](https://dune.com/rockawayxvault/rockawayx-dashboard)): `0x4F87…0545`, main depositor of the "Belem RWA EURCV" vault. ⚠ **Whether this address belongs to Belem is still to be confirmed with them.**

Supported pocket types:
- `morpho_vault_v2`: deposit in a Morpho V2 vault (we are a **lender**);
- `morpho_market_borrow`: borrowing on a Morpho market (we are a **borrower**, with leverage);
- `morpho_market_supply`: direct lending on a market.

## The pipeline

```
address ─▶ 1. online session (RPC, pinned block)                          session.py
        ─▶ 2. pockets: the API locates, the chain proves the amounts      portfolio.py
        ─▶ 3. proven graph of the pocket (vault → adapters → markets…)    graph_build.py, vault_v2.py
        ─▶ 4. risk data: borrowers, oracle profile                        market_data.py
        ─▶ 5. incidents generated from the graph → loss of the pocket     risk_engine.py
        ─▶ 6. exit cost (liquidity, DEX quotes, penalty, gas)             exit_cost.py
        ─▶ 7. STAY / EXIT decision, p*, contagion paths                   analyze.py
        ─▶ HTTP API for the front                                         api.py  (contract: API.md)
```

## Commands (PowerShell)

```powershell
$env:PYTHONPATH="src"
.venv313\Scripts\python -m stacktrace.doctor                                   # is everything responding?
.venv313\Scripts\python -m stacktrace.portfolio 0x4F87De7d21aeF48090958f7342E1F69Dff790545
.venv313\Scripts\python -m stacktrace.graph_build 0x4F87De7d21aeF48090958f7342E1F69Dff790545 "Belem RWA"
.venv313\Scripts\python -m stacktrace.analyze 0x4F87De7d21aeF48090958f7342E1F69Dff790545          # the whole portfolio
.venv313\Scripts\python -m stacktrace.analyze 0x4F87De7d21aeF48090958f7342E1F69Dff790545 --pocket "Belem RWA" --incident rwa_credit_event:mgloeuro --severity 0.3 --p 0.2
.venv313\Scripts\python -m stacktrace.api                                      # API on http://127.0.0.1:8000
```

Outputs go to `output/live/` (ignored by git). The online cache goes to `data/cache_live/` (ignored too).

## The model, in plain words

**We never guess.** Every address and every function is proven on-chain, or checked in verified source code (Etherscan, official repository). Every number in `risk/params_v2.yaml` is **sourced** or **marked as a hypothesis**, with its reason and its sensitivity range. The loader rejects everything else.

### What a lender loses (vault pocket)
Only the borrowers' **bad debt**, computed **borrower by borrower** (an aggregate would hide the risky borrowers):
- if the collateral is priced **at market** and falls **gradually**, the borrowers are liquidated in time and the lender loses nothing;
- in case of a **sudden** shock, or if the oracle **does not follow the market** (internal rate, price set by an admin), nobody is liquidated in time: loss = max(0, D − V·(1−d)·(1−slippage));
- if a feed is **skewed upwards**, an attacker borrows the available liquidity. They only gain if (1+u)·LLTV > 1. Example: the Midas feed is capped at +10% and the LLTV is 77%; 1.10 × 0.77 < 1, so the attack yields nothing;
- a **depeg** of the pocket's asset, a Morpho exploit or a curator failure directly loses the value × the severity.

### What a borrower loses (borrow pocket)
- **Liquidation**: penalty ρ·D·(LIF − 1), with the official Morpho formula.
- A **wrongful liquidation** if a feed errs downwards.
- The collateral's **own** loss of value: default of an RWA, depeg of an LST priced at the exchange rate.
- ⚠ Deliberate choice (parameter `borrow_market_beta_excluded`): a drop in ETH or BTC **only counts through the liquidation** it triggers. Belem is market-neutral: a market drop is a chosen exposure, not a dependency risk.

### The decision
- **Exiting costs a certain amount**, measured:
  - for a vault: the liquidity withdrawable now, the forced-withdrawal penalty (beyond the "liquidity source" market), the forgone yield and gas;
  - for a borrow: the slippage measured by **real KyberSwap quotes** at several sizes, the forgone yield and gas. The share whose slippage exceeds 25% is deemed **not exitable through the market**.
- **We exit the fraction f** that minimises cost(f) + expected loss × (1 − f). If f > 0, it is **EXIT**, otherwise **STAY**.
- **p\* = exit cost / loss if the incident happens.** This is the threshold to give the manager: "exit if you believe in more than p\*". It does **not** depend on our probabilities, which are hypotheses, only on measured quantities.

## Known limitations (to tell the jury)
- **Incident probabilities are orders of magnitude** (displayed hypotheses). Hence the importance of p\*.
- **Incidents are drawn independently**: cross-contagion between pockets is not simulated. Shared dependencies are **listed** (`/book` → `shared_dependencies`).
- **The dollar price of a pocket's asset comes from the Morpho API** (marked `source: api`).
- **Exiting an RWA by redemption with its issuer** (e.g. Huma for PST) is not modelled: only exiting through the market is.
- **Only the Morpho Ethereum ecosystem is covered.** Midas, Kamino/Solana and the other protocols in the Dune dashboard are the next steps.
- **The Reserve basket (ETH+) is not taken apart**: its oracle is marked `unknown`.

## To be verified by the team ("never an address from memory" rule)
- The sources of the new oracles (Etherscan verified code cited in `src/discovery/adapters/oracles.py`).
- The Morpho Vault V2 interface ([IVaultV2.sol](https://github.com/morpho-org/vault-v2/blob/main/src/interfaces/IVaultV2.sol)) and the two adapter versions (cited in `src/stacktrace/vault_v2.py`).
- The KyberSwap API docs ([specification](https://docs.kyberswap.com/kyberswap-solutions/kyberswap-aggregator/aggregator-api-specification/evm-swaps)).
