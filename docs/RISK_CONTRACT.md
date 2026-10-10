# `risk_report.json` / `risk_grid.json` contract (risk engine outputs)

Produced by `python -m risk.run` from `output/graph.json` (discovery contract, see
[`CONTRACT.md`](CONTRACT.md)) and `output/risk_inputs.json`. They are validated at every run by
`src/risk/validate_report.py`. The framing note named this file `risk_report.json`; that is the name we kept.

**Units:** amounts in **USD** (`*_usd`) or in **USDC** (`*_usdc`); fractions between 0 and 1 (`0.016` = 1.6%);
durations in hours (`*_hours`, `null` = lasting); `hf` = health factor (< 1 = liquidatable).
**Convention:** `borrower_loss_usd` > 0 = loss for the borrower (negative = gain); `lender_loss_usd` ≥ 0.

## `risk_report.json`

| Key | Content |
|---|---|
| `contract_version` | 1 |
| `snapshot` | `{block, timestamp, time_iso}`: the block of the snapshot (the same as graph.json) |
| `position` | starting state: `collateral_pt`, `debt_usdc`, `pt_market_usd` (market price of one PT), `oracle_price`, `gross_value_usd`, `equity_usd` (**pocket V** = net capital), `health_factor`, `ltv`, `lltv`, `lif` (Morpho liquidation bonus), `borrow_apy`, `oracle_drop_to_liquidation`, ids of the key nodes (`market`, `collateral`, `loan`, `oracle`, `exit_venue`) |
| `headline` | **the risk sheet**: `scenario` (main alert), `verdict` (STAY/PARTIAL/EXIT), `exit_fraction`, `p_star`, `p_default`, `loss_if_incident_usd`, `loss_if_incident_pct_equity`, `lender_loss_usd`, `exit_cost_usd`, `exit_cost_pct_equity`, `sentence`, `three_am_question` |
| `baseline` | "no alert" verdict (Monte Carlo expected loss vs exit cost) + sentence |
| `exit_cost.full` | cost of a full exit: `slippage_rate` / `slippage_usd` (measured on-chain), `second_leg_usd`, `gas_usd`, `carry_usd`, `total_usd`, `feasible` |
| `exit_cost.curves` | `{"1.0": [...], "0.5": [...], "0.1": [...]}`: cost for each fraction 0 → 100% (5% steps), depending on whether the pool has its full liquidity, ÷2 or ÷10 |
| `exit_cost.simulations_evidence` | evidence of the RouterStatic simulations (contract.function(args) = result @ address #block) |
| `monte_carlo` | `samples`, `seed`, `horizon_days`, `p_any_event`, `p_loss`, `p_liquidation`, `expected_loss_usd`, `var95_usd`, `var99_usd`, `es99_usd`, `expected_lender_loss_usd`, `conditional_loss_usd`, `events[]` (λ, probability over the horizon, contribution to the expected loss), `top_paths[]` (3 costliest paths, graph.json edges with evidence) |
| `scenarios[]` | one object per stress scenario (see below) |
| `replays[]` | real incidents replayed: `chainlink_path` (on-chain), `meta_oracle` (max gap, time above the threshold, switch?), `designs[]` (3 oracle designs: min HF, liquidated?, loss), `offchain_source` (URL + date) |
| `sensitivity[]` | tornado: for each hypothesis, low/high values → `el_low/high` (expected loss), `headline_loss_low/high`, `headline_p_star_low/high`; sorted by impact (`el_swing`) |
| `calibration` | statistics of the Chainlink USDe/USD history (worst gap, episodes below each threshold, annual frequency) |
| `params[]` | **all** parameters: `name`, `value`, `status` (`source` / `onchain` / `hypothesis`), `source` + `as_of`, or `field`, or `why`, and `range` |
| `confidence` | confidence level of p* and of the expected loss, in plain language |

### A scenario (`scenarios[]`)
| Key | Content |
|---|---|
| `id`, `family`, `title`, `story`, `why` | identity and justification of the scenario |
| `shocks[]` | `{node, kind, severity, duration_hours, panic}`: the shock applied (a graph.json node) |
| `propagation_trace[]` | the rules applied, in plain English |
| `asset_multipliers` | `{asset_id: value multiplier}` (0.9 = −10%) |
| `oracle` | `price_normal` → `price`, effective `mode`, `switched`, `switch_after_hours`, `deviation`, `challenge_possible`, `timeline[]` (challenge, switch, return) |
| `outcome` | `hf_before/after`, `liquidatable`, `liquidated`, `liquidation_profitable`, `seized_pt`, `repaid_usdc`, `bad_debt_usdc`, `equity_before/after_usd`, `borrower_loss_usd`, `lender_loss_usd`, `lgi` (loss / pocket), `who_loses`, `recovered_before_horizon`, `trace[]` |
| `decision` | `p_star`, `p_default`, `verdict`, `exit_fraction`, `sentence`, `exit_cost_full`, `table[]` (for p = 0 → 1 in steps of 0.01: optimal fraction and verdict) |
| `contagion_paths[]` | paths position → shocked node; each edge = the one from graph.json + `rule` (transmission rule) |
| `params_used[]`, `confidence` | parameters used and confidence level |

## `risk_grid.json` (front slider)
| Key | Content |
|---|---|
| `usde_node`, `usde_price_now` | the shocked asset and its price at the block |
| `prices[]`, `durations_hours[]` | axes of the grid (`null` = lasting) |
| `p_grid[]` | probabilities 0 → 1 (step 0.01) |
| `cells[i][j]` | cell (price i, duration j): `oracle_state` (`primary` / `challenge` / `switched`), `oracle_price`, `deviation`, `hf`, `liquidated`, `liquidatable`, `borrower_loss_usd`, `lender_loss_usd`, `who_loses`, `p_star`, `verdict_default`, `fraction_by_p[]` (optimal fraction for each p of `p_grid`), `status` ("LIQUIDATED" / "lenders exposed" / "not liquidated"), `sentence` |

## Guarantees (checked by the validator)
- no NaN or infinity; VaR95 ≤ VaR99; verdicts in {STAY, PARTIAL, EXIT}; p* ≥ 0;
- every parameter has a status; a hypothesis always has a `why`; a documentary source has an https URL and a date;
- every edge of a contagion path **exists in graph.json with the same evidence** (nothing invented or modified along the way);
- the grid is complete (consistent dimensions, one fraction for each p).
