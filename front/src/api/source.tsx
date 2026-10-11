import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, normaliseBaseUrl } from './client'
import { bundleFor, recordedGraph, recordedIncident, recordedRisk, recordedValidation } from './recorded'
import type {
  BookResponse,
  GraphResponse,
  Health,
  IncidentRequest,
  IncidentResponse,
  PocketsResponse,
  RiskResponse,
  ValidationResponse,
} from './types'

export type SourceMode = 'live' | 'recorded'

/**
 * Where the data comes from. Live calls the backend; recorded replays real responses
 * captured on mainnet. A recorded method returns null when nothing was recorded for
 * that request: the screen then says so instead of inventing an answer.
 */
export interface DataSource {
  mode: SourceMode
  apiUrl: string
  pockets(holder: string, signal?: AbortSignal): Promise<PocketsResponse | null>
  book(holder: string, signal?: AbortSignal): Promise<BookResponse | null>
  risk(holder: string, pocket: string, signal?: AbortSignal): Promise<RiskResponse | null>
  graph(holder: string, pocket: string, signal?: AbortSignal): Promise<GraphResponse | null>
  incident(holder: string, pocket: string, req: IncidentRequest, signal?: AbortSignal): Promise<IncidentResponse | null>
  validation(signal?: AbortSignal): Promise<ValidationResponse | null>
}

function liveSource(apiUrl: string): DataSource {
  return {
    mode: 'live',
    apiUrl,
    pockets: (h, s) => api.pockets(apiUrl, h, s),
    book: (h, s) => api.book(apiUrl, h, s),
    risk: (h, p, s) => api.risk(apiUrl, h, p, s),
    graph: (h, p, s) => api.graph(apiUrl, h, p, s),
    incident: (h, p, r, s) => api.incident(apiUrl, h, p, r, s),
    // An API started before this route existed answers 404: fall back on the committed recording (same data).
    validation: (s) => api.validation(apiUrl, s).catch((e) => (s?.aborted ? Promise.reject(e) : recordedValidation)),
  }
}

function recordedSource(apiUrl: string): DataSource {
  return {
    mode: 'recorded',
    apiUrl,
    pockets: (h) => Promise.resolve(bundleFor(h)?.pockets ?? null),
    book: (h) => Promise.resolve(bundleFor(h)?.book ?? null),
    risk: (h, p) => Promise.resolve(recordedRisk(h, p)),
    graph: (h, p) => Promise.resolve(recordedGraph(h, p)),
    incident: (h, p, r) => Promise.resolve(recordedIncident(h, p, r)),
    validation: () => Promise.resolve(recordedValidation),
  }
}

export type Probe =
  | { status: 'off' }
  | { status: 'checking' }
  | { status: 'ok'; health: Health }
  | { status: 'down'; error: string }

interface SourceState {
  source: DataSource
  probe: Probe
  setMode(mode: SourceMode): void
  setApiUrl(url: string): void
  recheck(): void
}

const SourceContext = createContext<SourceState | null>(null)

const STORAGE = { mode: 'stacktrace.source', api: 'stacktrace.api' }
const DEFAULT_API = 'http://127.0.0.1:8000'

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

function write(key: string, value: string) {
  try {
    window.localStorage.setItem(key, value)
  } catch {
    // Storage blocked: the choice simply is not remembered.
  }
}

/**
 * Starting point, most specific first: ?source= / ?api= in the URL, then the
 * viewer's last choice, then the build's VITE_SOURCE / VITE_API_URL.
 * With no choice made yet, start on recorded data (instant, works offline) and
 * look for a running API in the background.
 */
function initialState(): { mode: SourceMode; apiUrl: string; probeEnabled: boolean } {
  const params = new URLSearchParams(window.location.search)
  const env = import.meta.env
  const buildSource = (env.VITE_SOURCE as string | undefined) ?? 'auto'
  const apiUrl = normaliseBaseUrl(
    params.get('api') ?? read(STORAGE.api) ?? (env.VITE_API_URL as string | undefined) ?? DEFAULT_API,
  )
  const asked = params.get('source') ?? read(STORAGE.mode) ?? (buildSource === 'auto' ? null : buildSource)
  // Live by default: the deck shows real data read now. Recorded only when asked for (URL, build, last choice).
  const mode: SourceMode = asked === 'recorded' ? 'recorded' : 'live'
  // Recorded on purpose (URL or build): no background call to an API nobody runs.
  const recordedOnPurpose = params.get('source') === 'recorded' || (buildSource === 'recorded' && !params.has('source'))
  return { mode, apiUrl, probeEnabled: !recordedOnPurpose || params.has('api') }
}

export function SourceProvider({ children }: { children: ReactNode }) {
  const [init] = useState(initialState)
  const [mode, setModeState] = useState<SourceMode>(init.mode)
  const [apiUrl, setApiUrlState] = useState(init.apiUrl)
  const [probe, setProbe] = useState<Probe>(init.probeEnabled ? { status: 'checking' } : { status: 'off' })
  const [probeRun, setProbeRun] = useState(0)

  useEffect(() => {
    if (!init.probeEnabled && probeRun === 0) return
    const controller = new AbortController()
    setProbe({ status: 'checking' })
    api
      .health(apiUrl, controller.signal)
      .then((health) => setProbe({ status: 'ok', health }))
      .catch((error: Error) => {
        if (!controller.signal.aborted) setProbe({ status: 'down', error: error.message })
      })
    return () => controller.abort()
  }, [apiUrl, probeRun, init.probeEnabled])

  const setMode = useCallback((next: SourceMode) => {
    setModeState(next)
    write(STORAGE.mode, next)
  }, [])

  const setApiUrl = useCallback((url: string) => {
    const clean = normaliseBaseUrl(url)
    setApiUrlState(clean)
    write(STORAGE.api, clean)
  }, [])

  const recheck = useCallback(() => setProbeRun((n) => n + 1), [])

  const source = useMemo(
    () => (mode === 'live' ? liveSource(apiUrl) : recordedSource(apiUrl)),
    [mode, apiUrl],
  )

  const value = useMemo(
    () => ({ source, probe, setMode, setApiUrl, recheck }),
    [source, probe, setMode, setApiUrl, recheck],
  )

  return <SourceContext.Provider value={value}>{children}</SourceContext.Provider>
}

export function useSource(): SourceState {
  const ctx = useContext(SourceContext)
  if (!ctx) throw new Error('useSource must be used inside <SourceProvider>')
  return ctx
}
