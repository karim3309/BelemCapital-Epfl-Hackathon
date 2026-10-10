import { LAYER_META, type LayerId, type LayerNode, type Position } from '../data/mock'

/** Scenario levers. The base case reads its values back off the position. */
export interface Scenario {
  /** Probability that the oracle layer fails, 0-100 (%). */
  oracleFailureProb: number
  /** Multiplier on lending-market incident probability, 1-5 (x). */
  cascadeFactor: number
  /** Slippage paid to unwind the position, 0-30 (%). */
  slippagePct: number
  /** How fast dependency liquidity leaves: fast doubles non-oracle incident rates. */
  drainSpeed: 'slow' | 'fast'
}

export interface NodeRisk extends LayerNode {
  /** Incident probability after scenario levers are applied. */
  effective_prob: number
  /** p x LGD, in percent of position value. */
  loss_contribution_pct: number
}

export interface Assessment {
  nodes: NodeRisk[]
  contributions: { layer: LayerId; label: string; pct: number; share: number }[]
  expectedLossPct: number
  expectedLossUsd: number
  exitCostPct: number
  exitCostUsd: number
  /** Expected loss at which staying and exiting cost the same — i.e. the exit cost. */
  breakEvenLossPct: number
  /** How many times the current expected loss would have to grow to reach it. */
  breakEvenMultiple: number
  /** Oracle failure probability (%) that would reach break-even, null if unreachable. */
  breakEvenOraclePct: number | null
  verdict: 'STAY' | 'EXIT'
  reasoning: string
  confidence: 'High' | 'Medium' | 'Low'
  /** Value preserved by acting on the verdict, in percent of position. */
  edgePct: number
  /** The same edge in dollars. */
  edgeUsd: number
}

const DRAIN_MULTIPLIER = { slow: 1, fast: 2 } as const
const clampProb = (p: number) => Math.min(1, Math.max(0, p))

/** The base-case scenario encoded by the position's own data. */
export function baseScenario(position: Position): Scenario {
  const oracle = position.layers.find((n) => n.layer === 3)
  return {
    oracleFailureProb: (oracle ? oracle.incident_prob : 0) * 100,
    cascadeFactor: 1,
    slippagePct: position.impact.exit_cost_breakdown.slippage_pct,
    drainSpeed: 'slow',
  }
}

/**
 * Stress case: every impact estimate doubles. Oracle failure probability, the
 * liquidation cascade factor and the non-oracle incident rates all double, so
 * each node's loss contribution — and therefore the total — is exactly 2x base.
 * Exit slippage doubles with them.
 */
export function stressScenario(position: Position): Scenario {
  const base = baseScenario(position)
  return {
    oracleFailureProb: Math.min(100, base.oracleFailureProb * 2),
    cascadeFactor: 2,
    slippagePct: Math.min(30, base.slippagePct * 2),
    drainSpeed: 'fast',
  }
}

export function scenariosEqual(a: Scenario, b: Scenario): boolean {
  return (
    Math.abs(a.oracleFailureProb - b.oracleFailureProb) < 0.01 &&
    Math.abs(a.cascadeFactor - b.cascadeFactor) < 0.01 &&
    Math.abs(a.slippagePct - b.slippagePct) < 0.01 &&
    a.drainSpeed === b.drainSpeed
  )
}

function effectiveProb(node: LayerNode, scenario: Scenario, baseOracleProb: number): number {
  if (node.layer === 3) {
    const ratio = baseOracleProb > 0 ? scenario.oracleFailureProb / 100 / baseOracleProb : 1
    return clampProb(node.incident_prob * ratio)
  }
  if (node.layer === 5) return clampProb(node.incident_prob * scenario.cascadeFactor)
  return clampProb(node.incident_prob * DRAIN_MULTIPLIER[scenario.drainSpeed])
}

/** 11 -> "11%", 3.24 -> "3.2%" — no trailing zero noise in a headline. */
export function pct(value: number, decimals = 1): string {
  const fixed = value.toFixed(decimals)
  return `${fixed.replace(/\.0+$/, '')}%`
}

export function usd(value: number): string {
  if (Math.abs(value) >= 1_000_000_000) return `$${(value / 1_000_000_000).toFixed(1)}B`
  if (Math.abs(value) >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`
  if (Math.abs(value) >= 1_000) return `$${Math.round(value / 1_000)}K`
  return `$${Math.round(value)}`
}

export function severityColor(lossPct: number): string {
  if (lossPct < 1) return '#34C759'
  if (lossPct <= 5) return '#FF9F0A'
  return '#FF3B30'
}

export function assess(position: Position, scenario: Scenario): Assessment {
  const oracle = position.layers.find((n) => n.layer === 3)
  const baseOracleProb = oracle ? oracle.incident_prob : 0

  const nodes: NodeRisk[] = position.layers.map((node) => {
    const effective_prob = effectiveProb(node, scenario, baseOracleProb)
    return {
      ...node,
      effective_prob,
      loss_contribution_pct: effective_prob * node.loss_given_incident * 100,
    }
  })

  const expectedLossPct = nodes.reduce((sum, n) => sum + n.loss_contribution_pct, 0)

  const contributions = ([1, 2, 3, 4, 5] as LayerId[]).map((layer) => {
    const layerPct = nodes
      .filter((n) => n.layer === layer)
      .reduce((sum, n) => sum + n.loss_contribution_pct, 0)
    return {
      layer,
      label: LAYER_META[layer].short,
      pct: layerPct,
      share: expectedLossPct > 0 ? layerPct / expectedLossPct : 0,
    }
  })

  const { market_impact_pct, gas_pct } = position.impact.exit_cost_breakdown
  const exitCostPct = scenario.slippagePct + market_impact_pct + gas_pct

  // Expected loss is linear in oracle failure probability, so the break-even
  // probability solves exitCost = nonOracleLoss + (p/100) * oracleSensitivity.
  const nonOracleLossPct = nodes
    .filter((n) => n.layer !== 3)
    .reduce((sum, n) => sum + n.loss_contribution_pct, 0)
  const oracleSensitivity =
    baseOracleProb > 0
      ? nodes
          .filter((n) => n.layer === 3)
          .reduce((sum, n) => sum + n.incident_prob * n.loss_given_incident * 100, 0) /
        baseOracleProb
      : 0
  const solvedOracle =
    oracleSensitivity > 0 ? ((exitCostPct - nonOracleLossPct) / oracleSensitivity) * 100 : null
  const breakEvenOraclePct =
    solvedOracle !== null && solvedOracle >= 0 && solvedOracle <= 100 ? solvedOracle : null

  const verdict: 'STAY' | 'EXIT' = expectedLossPct > exitCostPct ? 'EXIT' : 'STAY'
  const edgePct = Math.abs(expectedLossPct - exitCostPct)

  const reasoning =
    verdict === 'STAY'
      ? `Expected loss (${pct(expectedLossPct)}) is below exit cost (${pct(exitCostPct)}). Staying is optimal.`
      : `Expected loss (${pct(expectedLossPct)}) exceeds exit cost (${pct(exitCostPct)}). Exiting now preserves ${pct(edgePct)} of position value.`

  const relativeMargin = edgePct / Math.max(exitCostPct, 0.1)
  const marginTier: Assessment['confidence'] =
    relativeMargin >= 0.5 ? 'High' : relativeMargin >= 0.2 ? 'Medium' : 'Low'
  const order = { High: 2, Medium: 1, Low: 0 } as const
  const ladder = ['Low', 'Medium', 'High'] as const
  let level = Math.min(order[marginTier], order[position.impact.confidence])
  // A hand-moved scenario is one step less certain than the published base case.
  if (!scenariosEqual(scenario, baseScenario(position))) level = Math.max(0, level - 1)

  return {
    nodes,
    contributions,
    expectedLossPct,
    expectedLossUsd: (expectedLossPct / 100) * position.tvl_exposure,
    exitCostPct,
    exitCostUsd: (exitCostPct / 100) * position.tvl_exposure,
    breakEvenLossPct: exitCostPct,
    breakEvenMultiple: expectedLossPct > 0 ? exitCostPct / expectedLossPct : 0,
    breakEvenOraclePct,
    verdict,
    reasoning,
    confidence: ladder[level],
    edgePct,
    edgeUsd: (edgePct / 100) * position.tvl_exposure,
  }
}
