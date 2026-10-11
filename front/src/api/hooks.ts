import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { ApiError } from './client'
import { useSource } from './source'
import type { IncidentRequest } from './types'

/*
 * The backend computes one request at a time and the first analysis of a block is
 * slow, so the order matters: the pocket list first (~5 s), then the selected
 * pocket's risk (10-30 s), its graph (instant once the risk exists), and the whole
 * book (~1 min 30) last. Recorded data has no such constraint.
 */

// Results are cached server-side for the block, and the block renews every 2 min.
const STALE_MS = 120_000

const retry = (count: number, error: unknown) =>
  !(error instanceof ApiError && error.status >= 400 && error.status < 500) && count < 1

function useKeyBase() {
  const { source } = useSource()
  return { source, base: [source.mode, source.mode === 'live' ? source.apiUrl : 'recorded'] as const }
}

export function usePockets(holder: string) {
  const { source, base } = useKeyBase()
  return useQuery({
    queryKey: [...base, 'pockets', holder.toLowerCase()],
    queryFn: ({ signal }) => source.pockets(holder, signal),
    staleTime: STALE_MS,
    retry,
  })
}

export function useRisk(holder: string, pocketId: string | null) {
  const { source, base } = useKeyBase()
  const pockets = usePockets(holder)
  return useQuery({
    queryKey: [...base, 'risk', holder.toLowerCase(), pocketId],
    queryFn: ({ signal }) => source.risk(holder, pocketId!, signal),
    enabled: !!pocketId && pockets.isSuccess && pockets.data !== null,
    staleTime: STALE_MS,
    retry,
  })
}

export function useGraph(holder: string, pocketId: string | null) {
  const { source, base } = useKeyBase()
  const risk = useRisk(holder, pocketId)
  const riskSettled = risk.isSuccess || risk.isError
  return useQuery({
    queryKey: [...base, 'graph', holder.toLowerCase(), pocketId],
    queryFn: ({ signal }) => source.graph(holder, pocketId!, signal),
    // Live: wait for the risk analysis, whose graph the server then reuses.
    enabled: !!pocketId && (source.mode === 'recorded' || riskSettled),
    staleTime: STALE_MS,
    retry,
  })
}

export function useBook(holder: string, pocketId: string | null) {
  const { source, base } = useKeyBase()
  const pockets = usePockets(holder)
  const risk = useRisk(holder, pocketId)
  return useQuery({
    queryKey: [...base, 'book', holder.toLowerCase()],
    queryFn: ({ signal }) => source.book(holder, signal),
    // Live: the book re-runs every pocket's analysis, so let the selected pocket go first
    // (a pocket is always selected once the list has arrived, unless the holder has none).
    enabled:
      source.mode === 'recorded' ||
      (pockets.isSuccess &&
        pockets.data !== null &&
        (pockets.data.holdings.length === 0 || (!!pocketId && (risk.isSuccess || risk.isError)))),
    staleTime: STALE_MS,
    retry,
  })
}

/** Real incidents replayed (frozen block): no dependency on the selected holder or pocket. */
export function useValidation() {
  const { source, base } = useKeyBase()
  return useQuery({
    queryKey: [...base, 'validation'],
    queryFn: ({ signal }) => source.validation(signal),
    staleTime: Infinity,
    retry,
  })
}

export function useIncident(holder: string, pocketId: string | null, req: IncidentRequest | null) {
  const { source, base } = useKeyBase()
  const risk = useRisk(holder, pocketId)
  return useQuery({
    queryKey: [...base, 'incident', holder.toLowerCase(), pocketId, req],
    queryFn: ({ signal }) => source.incident(holder, pocketId!, req!, signal),
    enabled: !!pocketId && !!req && risk.isSuccess && risk.data !== null,
    staleTime: STALE_MS,
    placeholderData: keepPreviousData,
    retry,
  })
}
