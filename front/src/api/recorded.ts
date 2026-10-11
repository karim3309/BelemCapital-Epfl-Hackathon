/**
 * Real API responses recorded from Ethereum mainnet, for the offline demo (no API, no network).
 *
 * One "bundle" per holder: every folder docs/api_examples/recordings/<holder>/ written by
 * `python -m stacktrace.record <holder>` (the curator book "book:rockawayx", a whole vault "vault:0x…").
 * They are picked up by themselves: record, commit, and the front replays it.
 */
import type {
  BookResponse,
  GraphResponse,
  IncidentRequest,
  IncidentResponse,
  PocketsResponse,
  RiskResponse,
  ValidationResponse,
} from './types'
import validationRecording from '../../../docs/api_examples/validation.json'

/** What the deck opens on: the RockawayX curator book (config.yaml → curator_books.rockawayx). */
export const DEFAULT_HOLDER = 'book:rockawayx'

export interface Bundle {
  holder: string
  pockets: PocketsResponse
  book: BookResponse | null
  risks: RiskResponse[]
  graphs: GraphResponse[]
  incidents: IncidentResponse[]
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

/** Real incidents replayed by the engine (python -m risk.validation): frozen block, same for every holder. */
export const recordedValidation = validationRecording as ValidationResponse

/** Every recorded holder (one folder each under docs/api_examples/recordings/). */
export const bundles: Bundle[] = recordingBundles()

export const bundleFor = (holder: string) => bundles.find((b) => same(b.holder, holder)) ?? null

export const isRecordedHolder = (holder: string) => bundleFor(holder) !== null

/** Block and time of the recording of this holder, or null when it was not recorded yet. */
export const recordedBlock = (holder: string) => bundleFor(holder)?.pockets.block ?? null
export const recordedTimestamp = (holder: string) => bundleFor(holder)?.pockets.block_timestamp ?? null

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
