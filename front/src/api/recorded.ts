/**
 * Real API responses recorded from Ethereum mainnet at block #26162868 (10 Oct 2026),
 * imported straight from the backend's docs/api_examples/ so there is one copy only.
 * Used when no API is running: the demo then works with no network at all.
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

export const recorded = {
  health: healthJson as unknown as Health,
  pockets: pocketsJson as unknown as PocketsResponse,
  book: bookJson as unknown as BookResponse,
  graphs: [graphVaultJson as unknown as GraphResponse],
  risks: [riskVaultJson as unknown as RiskResponse, riskBorrowJson as unknown as RiskResponse],
  incidents: [incidentJson as unknown as IncidentResponse],
}

export const RECORDED_HOLDER = recorded.pockets.holder
export const RECORDED_BLOCK = recorded.pockets.block
export const RECORDED_TIMESTAMP = recorded.pockets.block_timestamp

const same = (a: string, b: string) => a.toLowerCase() === b.toLowerCase()

export const isRecordedHolder = (holder: string) => same(holder, RECORDED_HOLDER)

/** The pocket an index or id refers to, as the API resolves it. */
function resolvePocket(pocket: string): string | null {
  const holdings = recorded.pockets.holdings
  if (/^\d+$/.test(pocket)) return holdings[Number(pocket) - 1]?.id ?? null
  return holdings.find((h) => same(h.id, pocket))?.id ?? null
}

export const recordedRisk = (pocket: string) => {
  const id = resolvePocket(pocket)
  return recorded.risks.find((r) => id && same(r.pocket.id, id)) ?? null
}

export const recordedGraph = (pocket: string) => {
  const id = resolvePocket(pocket)
  return recorded.graphs.find((g) => id && same(g.pocket.id, id)) ?? null
}

/** Only the exact recorded call is answered: no decision is extrapolated. */
export const recordedIncident = (pocket: string, req: IncidentRequest) => {
  const id = resolvePocket(pocket)
  return (
    recorded.incidents.find((r) => {
      const m = r.incident_mode
      return (
        id &&
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

/** Which pockets have a full recorded analysis (risk, graph). */
export const recordedCoverage = (pocketId: string) => ({
  risk: recordedRisk(pocketId) !== null,
  graph: recordedGraph(pocketId) !== null,
})
