/**
 * Real API responses recorded from Ethereum mainnet, imported straight from the backend's
 * docs/api_examples/ so there is one copy only. Used when no API is running: the demo then
 * works with no network at all.
 *
 * Two kinds of recordings, one "bundle" per holder:
 *  - the original example (holder 0x4F87…0545, block #26162868): the files at the root of api_examples/;
 *  - every folder docs/api_examples/recordings/<holder>/ written by `python -m stacktrace.record <holder>`
 *    (a curator book "book:<key>", a whole vault "vault:0x…" or an address). They are picked up by
 *    themselves: record, commit, and the front replays it.
 */
import bookJson from '../../../docs/api_examples/book.json'
import graphVaultJson from '../../../docs/api_examples/graph_vault.json'
import healthJson from '../../../docs/api_examples/health.json'
import incidentJson from '../../../docs/api_examples/incident.json'
import pocketsJson from '../../../docs/api_examples/pockets.json'
import riskBorrowJson from '../../../docs/api_examples/risk_borrow.json'
import riskVaultJson from '../../../docs/api_examples/risk_vault.json'
import type {
  BookResponse,
  GraphResponse,
  Health,
  IncidentRequest,
  IncidentResponse,
  PocketsResponse,
  RiskResponse,
} from './types'

export interface Bundle {
  holder: string
  pockets: PocketsResponse
  book: BookResponse | null
  risks: RiskResponse[]
  graphs: GraphResponse[]
  incidents: IncidentResponse[]
}

const original: Bundle = {
  holder: (pocketsJson as unknown as PocketsResponse).holder,
  pockets: pocketsJson as unknown as PocketsResponse,
  book: bookJson as unknown as BookResponse,
  graphs: [graphVaultJson as unknown as GraphResponse],
  risks: [riskVaultJson as unknown as RiskResponse, riskBorrowJson as unknown as RiskResponse],
  incidents: [incidentJson as unknown as IncidentResponse],
}

/** Folders written by the recorder: recordings/<holder>/{pockets,book,risk_n,graph_n,incident}.json */
function recordingBundles(): Bundle[] {
  const files = import.meta.glob('../../../docs/api_examples/recordings/*/*.json', { eager: true, import: 'default' })
  const folders = new Map<string, Record<string, unknown>>()
  for (const [path, data] of Object.entries(files)) {
    const m = path.match(/recordings\/([^/]+)\/([^/]+)\.json$/)
    if (!m) continue
    folders.set(m[1], { ...(folders.get(m[1]) ?? {}), [m[2]]: data })
  }
  const out: Bundle[] = []
  for (const f of folders.values()) {
    const pockets = f.pockets as PocketsResponse | undefined
    if (!pockets) continue
    const pick = <T,>(prefix: string) =>
      Object.entries(f)
        .filter(([name]) => name.startsWith(prefix))
        .map(([, data]) => data as T)
    out.push({
      holder: pockets.holder,
      pockets,
      book: (f.book as BookResponse | undefined) ?? null,
      risks: pick<RiskResponse>('risk_'),
      graphs: pick<GraphResponse>('graph_'),
      incidents: pick<IncidentResponse>('incident'),
    })
  }
  return out
}

const same = (a: string, b: string) => a.toLowerCase() === b.toLowerCase()

const fresh = recordingBundles()
/** Every recorded holder; a new recording of the original holder replaces the original example. */
export const bundles: Bundle[] = [...fresh, ...(fresh.some((b) => same(b.holder, original.holder)) ? [] : [original])]

export const recordedHealth = healthJson as unknown as Health

/** The holder shown first: the original example, unless it was re-recorded elsewhere in the list. */
export const RECORDED_HOLDER = original.holder

export const bundleFor = (holder: string) => bundles.find((b) => same(b.holder, holder)) ?? null

export const isRecordedHolder = (holder: string) => bundleFor(holder) !== null

/** Block of the recording of this holder (the original one when nothing is recorded for it). */
export const recordedBlock = (holder: string) => (bundleFor(holder) ?? original).pockets.block
export const recordedTimestamp = (holder: string) => (bundleFor(holder) ?? original).pockets.block_timestamp

/** The pocket an index or id refers to, as the API resolves it. */
function resolvePocket(b: Bundle, pocket: string): string | null {
  const holdings = b.pockets.holdings
  if (/^\d+$/.test(pocket)) return holdings[Number(pocket) - 1]?.id ?? null
  return holdings.find((h) => same(h.id, pocket))?.id ?? null
}

function find<T extends { pocket: { id: string } }>(holder: string, pocket: string, pick: (b: Bundle) => T[]): T | null {
  const b = bundleFor(holder)
  const id = b && resolvePocket(b, pocket)
  return (b && id && pick(b).find((r) => same(r.pocket.id, id))) || null
}

export const recordedRisk = (holder: string, pocket: string) => find(holder, pocket, (b) => b.risks)

export const recordedGraph = (holder: string, pocket: string) => find(holder, pocket, (b) => b.graphs)

/** Only the exact recorded call is answered: no decision is extrapolated. */
export const recordedIncident = (holder: string, pocket: string, req: IncidentRequest) => {
  const b = bundleFor(holder)
  const id = b && resolvePocket(b, pocket)
  if (!b || !id) return null
  return (
    b.incidents.find((r) => {
      const m = r.incident_mode
      return (
        same(r.pocket.id, id) &&
        m.incident.toLowerCase().startsWith(req.incident.toLowerCase()) &&
        req.severity !== undefined &&
        Math.abs(req.severity - m.severity) < 1e-6 &&
        req.p !== undefined &&
        Math.abs(req.p - m.p_used) < 1e-6
      )
    }) ?? null
  )
}

/** The recorded incident example of a pocket, if any (to offer it as a one-click demo). */
export const recordedExample = (holder: string, pocketId: string | null) =>
  (pocketId && bundleFor(holder)?.incidents.find((r) => same(r.pocket.id, pocketId))?.incident_mode) || undefined

/** A pocket of this holder whose graph was recorded (to offer it when the selected one was not). */
export const recordedGraphPocket = (holder: string) => bundleFor(holder)?.graphs[0]?.pocket

/** Which pockets have a full recorded analysis (risk, graph). */
export const recordedCoverage = (holder: string, pocketId: string) => ({
  risk: recordedRisk(holder, pocketId) !== null,
  graph: recordedGraph(holder, pocketId) !== null,
})
