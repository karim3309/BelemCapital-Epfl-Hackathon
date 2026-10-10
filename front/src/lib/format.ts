/**
 * French number formatting, matching the backend's own sentences
 * ("643 $", "0,6 %", "26,4 M$"). Fractions come in as 0-1.
 */

const NBSP = ' '
const int = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 0 })
const dec = (d: number) => new Intl.NumberFormat('fr-FR', { minimumFractionDigits: d, maximumFractionDigits: d })

/** Full dollar amount: 407 675 $. */
export function usd(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  if (Math.abs(value) > 0 && Math.abs(value) < 1) return `${dec(2).format(value)}${NBSP}$`
  return `${int.format(value)}${NBSP}$`
}

/** Compact dollar amount for headlines: 26,4 M$, 1,2 Md$, 12 k$. */
export function usdShort(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  const abs = Math.abs(value)
  if (abs >= 1e9) return `${dec(1).format(value / 1e9)}${NBSP}Md$`
  if (abs >= 1e6) return `${dec(1).format(value / 1e6)}${NBSP}M$`
  if (abs >= 1e4) return `${int.format(value / 1e3)}${NBSP}k$`
  return usd(value)
}

/** Percentage with explicit decimals: pct(0.0064, 1) -> 0,6 %. */
export function pct(fraction: number | null | undefined, decimals = 1): string {
  if (fraction === null || fraction === undefined || !Number.isFinite(fraction)) return '—'
  return `${dec(decimals).format(fraction * 100)}${NBSP}%`
}

/** Percentage that keeps small probabilities readable: 0,10 %, 2,4 %, 86 %. */
export function pctAuto(fraction: number | null | undefined): string {
  if (fraction === null || fraction === undefined || !Number.isFinite(fraction)) return '—'
  const v = fraction * 100
  if (v === 0) return `0${NBSP}%`
  if (v < 0.01) return `<${NBSP}0,01${NBSP}%`
  if (v < 1) return `${dec(2).format(v)}${NBSP}%`
  if (v < 10) return `${dec(1).format(v)}${NBSP}%`
  return `${int.format(v)}${NBSP}%`
}

/** Horizon de décision du backend (risk/params_v2.yaml, horizon_days) quand la réponse ne le donne pas. */
export const DEFAULT_HORIZON_DAYS = 7

/**
 * Small probability over the horizon -> intuitive frequency, same formula as src/risk/fmt.py::every:
 * p over h days ~ an event that happens once every h / -ln(1 - p) days. 0,10 % over 7 days -> "≈ une fois
 * tous les 20 ans". Empty above 20 % ("1 chance sur 5" speaks for itself).
 */
export function every(fraction: number | null | undefined, days: number = DEFAULT_HORIZON_DAYS): string {
  if (fraction === null || fraction === undefined || !(fraction > 0 && fraction < 0.2) || !(days > 0)) return ''
  const d = days / -Math.log1p(-fraction)
  if (d < 21) return `≈ une fois tous les ${Math.round(d)} jours`
  if (d < 90) return `≈ une fois toutes les ${Math.round(d / 7)} semaines`
  if (d < 730) return `≈ une fois tous les ${Math.round(d / 30.44)} mois`
  return `≈ une fois tous les ${int.format(d / 365.25)} ans`
}

/** Probability plus its frequency: "0,10 % (≈ une fois tous les 20 ans)". */
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

const dateFmt = new Intl.DateTimeFormat('fr-FR', {
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
  if (seconds < 60) return `il y a ${Math.max(0, Math.round(seconds))} s`
  if (seconds < 3600) return `il y a ${Math.round(seconds / 60)} min`
  return `il y a ${Math.round(seconds / 3600)} h`
}

export const KIND_LABEL: Record<string, string> = {
  morpho_vault_v2: 'Coffre',
  morpho_market_borrow: 'Emprunt',
  morpho_market_supply: 'Prêt direct',
}

export const kindLabel = (kind: string) => KIND_LABEL[kind] ?? kind

export const PRICING_LABEL: Record<string, string> = {
  market: 'suit le marché',
  fixed: 'prix fixe',
  internal_rate: 'taux interne',
  hybrid: 'hybride',
  unknown: 'non prouvé',
}

export const pricingLabel = (mode: string | undefined) => (mode ? PRICING_LABEL[mode] ?? mode : '—')

export const NODE_TYPE_LABEL: Record<string, string> = {
  position: 'Votre poche',
  chain: 'Chaîne',
  asset: 'Actif',
  issuer: 'Émetteur',
  oracle: 'Oracle',
  liquidity_venue: 'Pool de liquidité',
  lending_market: 'Marché de prêt',
  vault: 'Coffre',
  offchain_counterparty: 'Contrepartie hors chaîne',
}

export const EDGE_TYPE_LABEL: Record<string, string> = {
  deployed_in: 'placé dans',
  collateralized_by: 'garanti par',
  lends: 'prête',
  priced_by: 'pricé par',
  redeemable_into: 'rachetable en',
  issued_by: 'émis par',
  settled_on: 'réglé sur',
}

export const SOURCE_LABEL: Record<string, string> = {
  onchain: 'on-chain',
  api: 'API',
  curated: 'curé',
}

/** Verdict with the share to exit when it is partial: "EXIT 50 %". */
export function verdictText(verdict: string, exitFraction: number): string {
  if (verdict === 'EXIT' && exitFraction > 0 && exitFraction < 0.999) return `EXIT ${pct(exitFraction, 0)}`
  return verdict
}

export function integer(value: number): string {
  return int.format(value)
}
