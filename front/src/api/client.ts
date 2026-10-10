import type {
  ApiErrorBody,
  BookResponse,
  GraphResponse,
  Health,
  IncidentRequest,
  IncidentResponse,
  PocketsResponse,
  RiskResponse,
} from './types'

/** An HTTP error from the API, with FastAPI's `detail` kept intact. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: ApiErrorBody['detail'],
  ) {
    super(typeof detail === 'string' ? detail : detail.error)
    this.name = 'ApiError'
  }
}

/** The API never answered (down, wrong URL, blocked, or too slow). */
export class UnreachableError extends Error {
  constructor(readonly url: string, cause: string) {
    super(`API unreachable (${url}): ${cause}`)
    this.name = 'UnreachableError'
  }
}

/*
 * First calls are slow on the backend (hundreds of RPC calls, see docs/API.md):
 * /pockets ~5 s, /risk 10-30 s, /book ~1 min 30. Timeouts leave generous room.
 */
const TIMEOUT_MS = {
  health: 20_000,
  pockets: 90_000,
  risk: 180_000,
  graph: 180_000,
  incident: 90_000,
  book: 360_000,
} as const

function withTimeout(ms: number, outer?: AbortSignal): AbortSignal {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(new DOMException('timeout', 'TimeoutError')), ms)
  const stop = () => {
    clearTimeout(timer)
    controller.abort(outer?.reason)
  }
  if (outer) {
    if (outer.aborted) stop()
    else outer.addEventListener('abort', stop, { once: true })
  }
  controller.signal.addEventListener('abort', () => clearTimeout(timer), { once: true })
  return controller.signal
}

export function normaliseBaseUrl(url: string): string {
  return url.trim().replace(/\/+$/, '')
}

async function request<T>(
  base: string,
  path: string,
  timeoutMs: number,
  init: RequestInit = {},
  outer?: AbortSignal,
): Promise<T> {
  const url = `${normaliseBaseUrl(base)}${path}`
  let response: Response
  try {
    response = await fetch(url, {
      ...init,
      headers: { Accept: 'application/json', ...(init.body ? { 'Content-Type': 'application/json' } : {}) },
      signal: withTimeout(timeoutMs, outer),
    })
  } catch (error) {
    if (outer?.aborted) throw error
    const reason =
      error instanceof DOMException && error.name === 'TimeoutError'
        ? `no response after ${Math.round(timeoutMs / 1000)} s`
        : 'connection failed'
    throw new UnreachableError(base, reason)
  }
  if (!response.ok) {
    let detail: ApiErrorBody['detail'] = `${response.status} ${response.statusText}`
    try {
      const body = (await response.json()) as ApiErrorBody
      if (body && body.detail !== undefined) {
        detail = Array.isArray(body.detail)
          ? // FastAPI validation errors (422) arrive as a list of {loc, msg}.
            (body.detail as { msg: string }[]).map((d) => d.msg).join(' · ')
          : body.detail
      }
    } catch {
      // Non-JSON error body: keep the status line.
    }
    throw new ApiError(response.status, detail)
  }
  return (await response.json()) as T
}

const holderPath = (holder: string) => `/holders/${encodeURIComponent(holder)}`
const pocketPath = (holder: string, pocket: string) =>
  `${holderPath(holder)}/pockets/${encodeURIComponent(pocket)}`

export const api = {
  health: (base: string, signal?: AbortSignal) =>
    request<Health>(base, '/health', TIMEOUT_MS.health, {}, signal),
  pockets: (base: string, holder: string, signal?: AbortSignal) =>
    request<PocketsResponse>(base, `${holderPath(holder)}/pockets`, TIMEOUT_MS.pockets, {}, signal),
  graph: (base: string, holder: string, pocket: string, signal?: AbortSignal) =>
    request<GraphResponse>(base, `${pocketPath(holder, pocket)}/graph`, TIMEOUT_MS.graph, {}, signal),
  risk: (base: string, holder: string, pocket: string, signal?: AbortSignal) =>
    request<RiskResponse>(base, `${pocketPath(holder, pocket)}/risk`, TIMEOUT_MS.risk, {}, signal),
  incident: (base: string, holder: string, pocket: string, body: IncidentRequest, signal?: AbortSignal) =>
    request<IncidentResponse>(
      base,
      `${pocketPath(holder, pocket)}/incident`,
      TIMEOUT_MS.incident,
      { method: 'POST', body: JSON.stringify(body) },
      signal,
    ),
  book: (base: string, holder: string, signal?: AbortSignal) =>
    request<BookResponse>(base, `${holderPath(holder)}/book`, TIMEOUT_MS.book, {}, signal),
}
