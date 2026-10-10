/**
 * en-US number formatting, matching the backend's own sentences
 * ("$643", "0.6%", "$26.4M"). Fractions come in as 0-1.
 */

const int = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 })
const dec = (d: number) => new Intl.NumberFormat('en-US', { minimumFractionDigits: d, maximumFractionDigits: d })
const sign = (value: number) => (value < 0 ? '-' : '')

/** Full dollar amount: $407,675. */
export function usd(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  const abs = Math.abs(value)
  if (abs > 0 && abs < 1) return `${sign(value)}$${dec(2).format(abs)}`
  return `${sign(value)}$${int.format(abs)}`
}

/** Compact dollar amount for headlines: $26.4M, $1.2B, $12k. */
export function usdShort(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  const abs = Math.abs(value)
  if (abs >= 1e9) return `${sign(value)}$${dec(1).format(abs / 1e9)}B`
  if (abs >= 1e6) return `${sign(value)}$${dec(1).format(abs / 1e6)}M`
  if (abs >= 1e4) return `${sign(value)}$${int.format(abs / 1e3)}k`
  return usd(value)
}

/** Percentage with explicit decimals: pct(0.0064, 1) -> 0.6%. */
export function pct(fraction: number | null | undefined, decimals = 1): string {
  if (fraction === null || fraction === undefined || !Number.isFinite(fraction)) return '—'
  return `${dec(decimals).format(fraction * 100)}%`
}

/** Percentage that keeps small probabilities readable: 0.10%, 2.4%, 86%. */
export function pctAuto(fraction: number | null | undefined): string {
  if (fraction === null || fraction === undefined || !Number.isFinite(fraction)) return '—'
  const v = fraction * 100
  if (v === 0) return '0%'
  if (v < 0.01) return '< 0.01%'
  if (v < 1) return `${dec(2).format(v)}%`
  if (v < 10) return `${dec(1).format(v)}%`
  return `${int.format(v)}%`
}

/** Backend decision horizon (risk/params_v2.yaml, horizon_days) when the response does not give it. */
export const DEFAULT_HORIZON_DAYS = 7

/**
 * Small probability over the horizon -> intuitive frequency, same formula as src/risk/fmt.py::every:
 * p over h days ~ an event that happens once every h / -ln(1 - p) days. 0.10% over 7 days -> "≈ once
 * every 20 years". Empty above 20% ("1 chance in 5" speaks for itself).
 */
export function every(fraction: number | null | undefined, days: number = DEFAULT_HORIZON_DAYS): string {
  if (fraction === null || fraction === undefined || !(fraction > 0 && fraction < 0.2) || !(days > 0)) return ''
  const d = days / -Math.log1p(-fraction)
  if (d < 21) return `≈ once every ${Math.round(d)} days`
  if (d < 90) return `≈ once every ${Math.round(d / 7)} weeks`
  if (d < 730) return `≈ once every ${Math.round(d / 30.44)} months`
  return `≈ once every ${int.format(d / 365.25)} years`
}

/** Probability plus its frequency: "0.10% (≈ once every 20 years)". */
export function pctFreq(fraction: number | null | undefined, days: number = DEFAULT_HORIZON_DAYS): string {
  const f = every(fraction, days)
  return `${pctAuto(fraction)}${f ? ` (${f})` : ''}`
}

export function shortAddress(address: string): string {
  return address.length > 12 ? `${address.slice(0, 6)}…${address.slice(-4)}` : address
}

export function blockNumber(block: number): string {
  return `#${int.format(block)}`
}

const dateFmt = new Intl.DateTimeFormat('en-US', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  timeZone: 'UTC',
})

export function blockTime(timestamp: number): string {
  return `${dateFmt.format(new Date(timestamp * 1000))} UTC`
}

export function ago(seconds: number): string {
  if (seconds < 60) return `${Math.max(0, Math.round(seconds))} s ago`
  if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`
  return `${Math.round(seconds / 3600)} h ago`
}

export const KIND_LABEL: Record<string, string> = {
  morpho_vault_v2: 'Vault',
  morpho_market_borrow: 'Borrow',
  morpho_market_supply: 'Direct supply',
}

export const kindLabel = (kind: string) => KIND_LABEL[kind] ?? kind

export const PRICING_LABEL: Record<string, string> = {
  market: 'market price',
  fixed: 'fixed price',
  internal_rate: 'internal rate',
  hybrid: 'hybrid',
  unknown: 'not proven',
}

export const pricingLabel = (mode: string | undefined) => (mode ? PRICING_LABEL[mode] ?? mode : '—')

export const NODE_TYPE_LABEL: Record<string, string> = {
  position: 'Your pocket',
  chain: 'Chain',
  asset: 'Asset',
  issuer: 'Issuer',
  oracle: 'Oracle',
  liquidity_venue: 'Liquidity pool',
  lending_market: 'Lending market',
  vault: 'Vault',
  offchain_counterparty: 'Off-chain counterparty',
}

export const EDGE_TYPE_LABEL: Record<string, string> = {
  deployed_in: 'deployed in',
  collateralized_by: 'collateralized by',
  lends: 'lends',
  priced_by: 'priced by',
  redeemable_into: 'redeemable into',
  issued_by: 'issued by',
  settled_on: 'settled on',
}

export const SOURCE_LABEL: Record<string, string> = {
  onchain: 'on-chain',
  api: 'API',
  curated: 'curated',
}

/** Verdict with the share to exit when it is partial: "EXIT 50%". */
export function verdictText(verdict: string, exitFraction: number): string {
  if (verdict === 'EXIT' && exitFraction > 0 && exitFraction < 0.999) return `EXIT ${pct(exitFraction, 0)}`
  return verdict
}

export function integer(value: number): string {
  return int.format(value)
}
