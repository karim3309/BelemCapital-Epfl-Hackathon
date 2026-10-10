/**
 * Contract of the StackTrace v2 HTTP API (backend: src/stacktrace/api.py).
 * Source of truth: docs/API.md and the real responses recorded in docs/api_examples/.
 * The front reads these shapes and computes no risk of its own.
 */

export type Verdict = 'STAY' | 'EXIT'
export type PocketKind = 'morpho_vault_v2' | 'morpho_market_borrow' | 'morpho_market_supply'
export type EdgeSource = 'onchain' | 'api' | 'curated'
export type NodeType =
  | 'chain'
  | 'asset'
  | 'issuer'
  | 'oracle'
  | 'liquidity_venue'
  | 'lending_market'
  | 'vault'
  | 'offchain_counterparty'
export type EdgeType =
  | 'deployed_in'
  | 'collateralized_by'
  | 'lends'
  | 'priced_by'
  | 'redeemable_into'
  | 'issued_by'
  | 'settled_on'
export type PricingMode = 'market' | 'fixed' | 'internal_rate' | 'hybrid' | 'unknown'

/** Every response carries the block it was computed at. */
export interface BlockMeta {
  block: number
  block_timestamp: number
  chain_id: number
}

export interface Health extends BlockMeta {
  status: 'ok' | 'degraded'
  version: string
  rpc_host: string
  block_age_s: number
  /** The API keeps this block until it restarts (python -m stacktrace.api --hold-block). */
  block_held?: boolean
  apis: Record<string, string>
}

export interface PocketRef {
  id: string
  kind: PocketKind | string
  label: string
  value_usd?: number
  share_of_book?: number
}

export interface Holding {
  index: number
  id: string
  kind: PocketKind | string
  label: string
  protocol: string
  chain: string
  address: string
  market_id: string | null
  asset_symbol: string
  asset_address: string
  amount: number
  price_usd: number
  value_usd: number
  price_source: string
  evidence: string[]
  api_amount?: number
  api_gap?: number
  details?: Record<string, unknown> & { health_factor?: number; lltv?: number }
  share_of_book: number
}

export interface PocketsResponse extends BlockMeta {
  holder: string
  chain: string
  located_by: string
  total_value_usd: number
  holdings: Holding[]
  ignored: { id: string; label: string; reason: string; value_usd: number | null }[]
  notes: string[]
}

export interface GraphNode {
  id: string
  type: NodeType
  label: string
  address: string | null
  chain: string
  // Node metadata varies by type; it is displayed, never interpreted as risk.
  meta: Record<string, any>
}

export interface GraphEdge {
  from: string
  to: string
  type: EdgeType
  weight: number
  source: EdgeSource
  evidence: string
}

export interface Graph {
  position: { id: string; value_usd: number }
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface GraphResponse extends BlockMeta {
  pocket: PocketRef
  graph: Graph
}

export interface Incident {
  id: string
  title: string
  family: string
  target: string
  annual_rate: number
  p_horizon: number
  severity_range: [number, number]
  loss_if_incident_usd: number
  loss_if_incident_max_usd: number
  expected_loss_usd: number
  /** Exit if you believe the incident is more likely than this. Null when no exit is possible. */
  p_star: number | null
  rule: string
  contagion_path: string
}

export interface RiskMarket {
  label: string
  collateral_pricing: PricingMode | string
  collateral_class: string
  lltv: number
  utilization: number | null
  liquidity: number
  our_supply: number
  borrowers: number
  borrowers_source: string
}

export interface MonteCarlo {
  samples: number
  horizon_days: number
  expected_loss_usd: number
  var95_usd: number
  var99_usd: number
  var999_usd: number
  p_any_loss: number
  independence_note: string
}

export interface ExitQuote {
  fraction: number
  slippage: number
}

export interface ExitInfo {
  f_max_now: number
  cost_full_usd: number
  cost_full_pct: number
  gas?: string
  note?: string
  // vault pockets
  withdrawable_now_fraction?: number
  penalty_free_fraction?: number
  force_deallocate_penalty?: number
  forgone_yield_rate_over_horizon?: number
  supply_apy_weighted?: number | null
  // borrow pockets
  quote_api?: string
  collateral_to_sell_full?: number
  reference?: { collateral_in: number; rate_out_per_in_raw: number; fetched: string }
  quotes?: ExitQuote[]
  measured?: boolean
  market_capacity_note?: string
  forgone_net_carry_rate_over_horizon?: number
}

export interface Decision {
  verdict: Verdict
  exit_fraction: number
  sentence: string
}

export interface RiskResponse extends BlockMeta {
  pocket: PocketRef
  graph: { nodes: number; edges: number; position_id: string }
  markets: RiskMarket[]
  monte_carlo: MonteCarlo
  exit: ExitInfo
  decision: Decision
  incidents: Incident[]
}

export interface IncidentRequest {
  incident: string
  severity?: number
  p?: number
  horizon?: number
}

export interface IncidentMode {
  incident: string
  title: string
  severity: number
  loss_if_incident_usd: number
  loss_if_incident_pct: number
  p_used: number
  p_source: string
  p_star: number | null
  verdict: Verdict
  exit_fraction: number
  rule: string
  contagion_path: string
  contagion_edges: GraphEdge[]
  sentence: string
}

export interface IncidentResponse extends BlockMeta {
  pocket: PocketRef
  baseline_decision: Decision
  incident_mode: IncidentMode
}

export interface BookPocket {
  index: number
  id: string
  label: string
  kind: PocketKind | string
  value_usd: number
  share_of_book: number
  verdict: Verdict
  exit_fraction: number
  expected_loss_usd: number
  exit_cost_usd: number
  exit_fraction_now: number
  sentence: string
  top_risk: Incident | null
}

export interface SharedDependency {
  dependency: string
  type: NodeType
  pockets: number
  exposed_value_usd: number
}

export interface BookResponse extends BlockMeta {
  holder: string
  total_value_usd: number
  expected_loss_usd: number
  pockets: BookPocket[]
  skipped: { id: string; label: string; reason: unknown }[]
  shared_dependencies: SharedDependency[]
}

/** FastAPI error body: `detail` is a string or an object (404 lists the valid pockets / incidents). */
export interface ApiErrorBody {
  detail: string | { error: string; pockets?: { index: number; id: string; label: string }[]; incidents?: string[] }
}
