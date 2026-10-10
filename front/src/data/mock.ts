/**
 * Dependency + impact dataset.
 *
 * Every expected-loss figure in the UI is DERIVED, never asserted: each node
 * carries an incident probability (`incident_prob`) and a loss-given-incident
 * (`loss_given_incident`, as a fraction of position value). A node's loss
 * contribution is p x LGD, and the position's expected loss is the sum across
 * the dependency set. `impact.layer_contributions` below is the published base
 * case and reconciles exactly with those node-level inputs.
 *
 * Snapshot taken 2026-10-09. Swap this module for the indexer adapter to run
 * the same engine on live chain state — the shapes are the contract.
 */

export type LayerId = 1 | 2 | 3 | 4 | 5

export interface LayerNode {
  id: string
  label: string
  layer: LayerId
  /** Total value locked in the dependency itself, USD. Oracles hold none. */
  tvl: number | null
  /** Live incident affecting this dependency. */
  incident: boolean
  /** What this dependency does for the position. */
  role: string
  /** Why a failure here reaches the position. */
  transmission: string
  /** Probability of a loss-causing incident over a 30-day horizon. */
  incident_prob: number
  /** Share of position value lost if that incident happens. */
  loss_given_incident: number
}

export interface LayerContribution {
  layer: LayerId
  label: string
  pct: number
}

export interface ExitCost {
  slippage_pct: number
  market_impact_pct: number
  gas_pct: number
}

export interface Impact {
  expected_loss_pct: number
  exit_cost_pct: number
  verdict: 'STAY' | 'EXIT'
  reasoning: string
  confidence: 'High' | 'Medium' | 'Low'
  layer_contributions: LayerContribution[]
  exit_cost_breakdown: ExitCost
}

export interface Position {
  name: string
  chain: string
  description: string
  venue: string
  tvl_exposure: number
  layers: LayerNode[]
  edges: [string, string][]
  impact: Impact
}

export const LAYER_META: Record<LayerId, { label: string; color: string; short: string }> = {
  1: { label: 'Settlement chain', color: '#8E8E93', short: 'Settlement' },
  2: { label: 'Yield source', color: '#0071E3', short: 'Yield source' },
  3: { label: 'Oracle', color: '#FF9F0A', short: 'Oracle' },
  4: { label: 'AMM / Protocol', color: '#0071E3', short: 'Protocol AMM' },
  5: { label: 'Lending market', color: '#FF3B30', short: 'Lending market' },
}

export const positions: Record<string, Position> = {
  pendle_pt_susde: {
    name: 'Pendle PT-sUSDE',
    chain: 'Ethereum',
    venue: 'Pendle · PT-sUSDE Dec 2026 maturity',
    description:
      'Fixed-yield principal token on Ethena sUSDe, held to maturity and pledged as Aave collateral.',
    tvl_exposure: 2_400_000,
    layers: [
      {
        id: 'eth',
        label: 'Ethereum',
        layer: 1,
        tvl: 400_000_000_000,
        incident: false,
        role: 'Settlement and finality for every contract in the stack.',
        transmission: 'A reorg or sustained congestion blocks redemption and liquidation alike.',
        incident_prob: 0.004,
        loss_given_incident: 0.25,
      },
      {
        id: 'ethena',
        label: 'Ethena (sUSDe)',
        layer: 2,
        tvl: 3_800_000_000,
        incident: false,
        role: 'Underlying yield: delta-neutral basis trade backing sUSDe.',
        transmission: 'Negative funding or custodial failure breaks the PT redemption value at maturity.',
        incident_prob: 0.02,
        loss_given_incident: 0.2,
      },
      {
        id: 'chainlink',
        label: 'Chainlink Oracle',
        layer: 3,
        tvl: null,
        incident: true,
        role: 'Prices PT-sUSDE for the Aave collateral position.',
        transmission:
          'A stale or mispriced feed liquidates the collateral at a price the market never printed.',
        incident_prob: 0.4,
        loss_given_incident: 0.055,
      },
      {
        id: 'pendle_amm',
        label: 'Pendle AMM',
        layer: 4,
        tvl: 890_000_000,
        incident: false,
        role: 'Only venue with depth to exit PT before maturity.',
        transmission: 'Liquidity withdrawal widens the PT discount and raises the real cost of exit.',
        incident_prob: 0.03,
        loss_given_incident: 0.1,
      },
      {
        id: 'aave_col',
        label: 'Aave (collateral)',
        layer: 5,
        tvl: 12_000_000_000,
        incident: false,
        role: 'Lending market where the PT is pledged against borrowed stables.',
        transmission: 'Cascading liquidations of the same collateral dump PT into a thin book.',
        incident_prob: 0.025,
        loss_given_incident: 0.08,
      },
    ],
    edges: [
      ['pendle_amm', 'eth'],
      ['pendle_amm', 'ethena'],
      ['pendle_amm', 'chainlink'],
      ['aave_col', 'pendle_amm'],
    ],
    impact: {
      expected_loss_pct: 3.2,
      exit_cost_pct: 11.0,
      verdict: 'STAY',
      reasoning: 'Expected loss (3.2%) is below exit cost (11%). Staying is optimal.',
      confidence: 'High',
      layer_contributions: [
        { layer: 1, label: 'Settlement', pct: 0.1 },
        { layer: 2, label: 'Yield source', pct: 0.4 },
        { layer: 3, label: 'Oracle', pct: 2.2 },
        { layer: 4, label: 'Protocol AMM', pct: 0.3 },
        { layer: 5, label: 'Lending market', pct: 0.2 },
      ],
      exit_cost_breakdown: { slippage_pct: 6.0, market_impact_pct: 4.2, gas_pct: 0.8 },
    },
  },

  aave_usdc_supply: {
    name: 'Aave USDC supply',
    chain: 'Ethereum',
    venue: 'Aave v3 · USDC core market',
    description: 'Variable-rate USDC deposit in the Aave v3 core market, no borrow leg.',
    tvl_exposure: 8_100_000,
    layers: [
      {
        id: 'eth',
        label: 'Ethereum',
        layer: 1,
        tvl: 400_000_000_000,
        incident: false,
        role: 'Settlement and finality for the deposit.',
        transmission: 'Congestion delays withdrawal during a run on the pool.',
        incident_prob: 0.004,
        loss_given_incident: 0.25,
      },
      {
        id: 'circle',
        label: 'Circle (USDC)',
        layer: 2,
        tvl: 43_500_000_000,
        incident: false,
        role: 'Issuer holding the reserves that make the deposit redeemable at par.',
        transmission: 'A reserve or banking failure depegs the asset itself, not just the position.',
        incident_prob: 0.005,
        loss_given_incident: 0.2,
      },
      {
        id: 'chainlink',
        label: 'Chainlink Oracle',
        layer: 3,
        tvl: null,
        incident: false,
        role: 'Prices USDC and every asset borrowed against it.',
        transmission: 'A mispriced collateral feed lets bad debt accrue against this pool.',
        incident_prob: 0.05,
        loss_given_incident: 0.02,
      },
      {
        id: 'aave_v3',
        label: 'Aave v3 Pool',
        layer: 4,
        tvl: 24_000_000_000,
        incident: false,
        role: 'Custody and accounting contract for the supplied balance.',
        transmission: 'A contract failure or governance mistake freezes or impairs the balance.',
        incident_prob: 0.01,
        loss_given_incident: 0.05,
      },
      {
        id: 'aave_market',
        label: 'Aave USDC market',
        layer: 5,
        tvl: 6_400_000_000,
        incident: false,
        role: 'Borrower book whose repayments fund withdrawals.',
        transmission: 'Bad debt from under-collateralised borrowers is socialised across suppliers.',
        incident_prob: 0.01,
        loss_given_incident: 0.05,
      },
    ],
    edges: [
      ['aave_v3', 'eth'],
      ['aave_v3', 'circle'],
      ['aave_v3', 'chainlink'],
      ['circle', 'eth'],
      ['aave_market', 'aave_v3'],
    ],
    impact: {
      expected_loss_pct: 0.4,
      exit_cost_pct: 0.9,
      verdict: 'STAY',
      reasoning: 'Expected loss (0.4%) is below exit cost (0.9%). Staying is optimal.',
      confidence: 'High',
      layer_contributions: [
        { layer: 1, label: 'Settlement', pct: 0.1 },
        { layer: 2, label: 'Yield source', pct: 0.1 },
        { layer: 3, label: 'Oracle', pct: 0.1 },
        { layer: 4, label: 'Protocol AMM', pct: 0.05 },
        { layer: 5, label: 'Lending market', pct: 0.05 },
      ],
      exit_cost_breakdown: { slippage_pct: 0.15, market_impact_pct: 0.7, gas_pct: 0.05 },
    },
  },

  kamino_sol_vault: {
    name: 'Kamino SOL vault',
    chain: 'Solana',
    venue: 'Kamino · JitoSOL-SOL multiply vault',
    description: 'Leveraged JitoSOL strategy vault, borrowing SOL against staked SOL on Kamino Lend.',
    tvl_exposure: 1_150_000,
    layers: [
      {
        id: 'sol',
        label: 'Solana',
        layer: 1,
        tvl: 95_000_000_000,
        incident: false,
        role: 'Settlement and finality for the vault and its lending leg.',
        transmission: 'A halt or congestion window stops deleveraging while prices move.',
        incident_prob: 0.012,
        loss_given_incident: 0.25,
      },
      {
        id: 'jito',
        label: 'Jito (JitoSOL)',
        layer: 2,
        tvl: 2_900_000_000,
        incident: false,
        role: 'Liquid staking yield backing the long leg of the strategy.',
        transmission: 'Validator slashing or an unstake queue breaks the JitoSOL/SOL ratio.',
        incident_prob: 0.03,
        loss_given_incident: 0.2,
      },
      {
        id: 'pyth',
        label: 'Pyth Oracle',
        layer: 3,
        tvl: null,
        incident: true,
        role: 'Prices JitoSOL and SOL for the vault health factor.',
        transmission: 'A stale push during volatility liquidates the vault below fair value.',
        incident_prob: 0.4,
        loss_given_incident: 0.11,
      },
      {
        id: 'kamino_vault',
        label: 'Kamino vault',
        layer: 4,
        tvl: 2_100_000_000,
        incident: false,
        role: 'Strategy contract holding the leveraged position and its rebalance logic.',
        transmission: 'Rebalance failure or a drained pool turns a paper loss into a realised one.',
        incident_prob: 0.08,
        loss_given_incident: 0.15,
      },
      {
        id: 'klend',
        label: 'Kamino Lend',
        layer: 5,
        tvl: 1_650_000_000,
        incident: true,
        role: 'Lending market supplying the borrowed SOL leg.',
        transmission: 'A liquidation cascade in the same collateral forces exit at the worst price.',
        incident_prob: 0.22,
        loss_given_incident: 0.15,
      },
    ],
    edges: [
      ['kamino_vault', 'sol'],
      ['kamino_vault', 'jito'],
      ['kamino_vault', 'pyth'],
      ['jito', 'sol'],
      ['klend', 'kamino_vault'],
      ['klend', 'pyth'],
    ],
    impact: {
      expected_loss_pct: 9.8,
      exit_cost_pct: 4.1,
      verdict: 'EXIT',
      reasoning: 'Expected loss (9.8%) exceeds exit cost (4.1%). Exiting preserves 5.7% of value.',
      confidence: 'Medium',
      layer_contributions: [
        { layer: 1, label: 'Settlement', pct: 0.3 },
        { layer: 2, label: 'Yield source', pct: 0.6 },
        { layer: 3, label: 'Oracle', pct: 4.4 },
        { layer: 4, label: 'Protocol AMM', pct: 1.2 },
        { layer: 5, label: 'Lending market', pct: 3.3 },
      ],
      exit_cost_breakdown: { slippage_pct: 2.6, market_impact_pct: 1.2, gas_pct: 0.3 },
    },
  },
}

export type PositionKey = keyof typeof positions

export const presets: { key: string; name: string; chain: string; description: string }[] = [
  {
    key: 'pendle_pt_susde',
    name: 'Pendle PT-sUSDE',
    chain: 'Ethereum',
    description: positions.pendle_pt_susde.description,
  },
  {
    key: 'aave_usdc_supply',
    name: 'Aave USDC supply',
    chain: 'Ethereum',
    description: positions.aave_usdc_supply.description,
  },
  {
    key: 'kamino_sol_vault',
    name: 'Kamino SOL vault',
    chain: 'Solana',
    description: positions.kamino_sol_vault.description,
  },
]

/** Resolves a pasted contract address to a preset, so the demo never dead-ends. */
export const addressBook: Record<string, string> = {
  '0x9ec558f5c8bdf1fbc7fa2a3b0da6e3fbd9a3a0a1': 'pendle_pt_susde',
  '0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2': 'aave_usdc_supply',
  '6labavoa1pcbcy2afmzqscj3rmcayaqvnt2dpnbhesnd': 'kamino_sol_vault',
}
