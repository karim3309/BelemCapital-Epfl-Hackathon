import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useBook, usePockets, useRisk } from '../api/hooks'
import { RECORDED_HOLDER } from '../api/recorded'
import type { BookPocket, Decision, Holding, Incident, RiskResponse } from '../api/types'

export const SLIDES = [
  { id: 'portefeuille', label: 'Portefeuille' },
  { id: 'verdict', label: 'Verdict' },
  { id: 'chemin', label: 'Par quel chemin ?' },
  { id: 'perte', label: 'Combien je perds ?' },
  { id: 'sortie', label: 'Combien coûte la sortie ?' },
  { id: 'incident', label: 'Et si ça arrive ?' },
  { id: 'concentration', label: 'Concentration' },
] as const

export type SlideId = (typeof SLIDES)[number]['id']

interface SelectionState {
  holder: string
  setHolder(holder: string): void
  pocketId: string | null
  setPocketId(id: string): void
  stepPocket(delta: number): void
  incidentId: string | null
  setIncidentId(id: string | null): void
  goTo(slide: SlideId): void
}

const SelectionContext = createContext<SelectionState | null>(null)

const STORAGE_POCKET = 'stacktrace.pocket'

function readParam(name: string): string | null {
  return new URLSearchParams(window.location.search).get(name)
}

function remembered(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_POCKET)
  } catch {
    return null
  }
}

export function SelectionProvider({ children }: { children: ReactNode }) {
  const [holder, setHolderState] = useState(() => readParam('holder') ?? RECORDED_HOLDER)
  const [pocketId, setPocketIdState] = useState<string | null>(null)
  const [incidentId, setIncidentId] = useState<string | null>(null)
  const pockets = usePockets(holder)
  const holdings = pockets.data?.holdings

  // Default pocket: the last one viewed, else the first vault (the lender's view), else the largest.
  useEffect(() => {
    if (!holdings || holdings.length === 0) return
    if (pocketId && holdings.some((h) => h.id === pocketId)) return
    const last = remembered()
    const pick =
      holdings.find((h) => h.id === last) ?? holdings.find((h) => h.kind.startsWith('morpho_vault')) ?? holdings[0]
    setPocketIdState(pick.id)
  }, [holdings, pocketId])

  const setPocketId = useCallback((id: string) => {
    setPocketIdState(id)
    setIncidentId(null)
    try {
      window.localStorage.setItem(STORAGE_POCKET, id)
    } catch {
      // not remembered
    }
  }, [])

  const stepPocket = useCallback(
    (delta: number) => {
      if (!holdings || holdings.length === 0) return
      const i = Math.max(0, holdings.findIndex((h) => h.id === pocketId))
      const next = holdings[(i + delta + holdings.length) % holdings.length]
      setPocketId(next.id)
    },
    [holdings, pocketId, setPocketId],
  )

  const setHolder = useCallback((next: string) => {
    setHolderState(next.trim())
    setPocketIdState(null)
    setIncidentId(null)
  }, [])

  const goTo = useCallback((slide: SlideId) => {
    document.getElementById(slide)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [])

  const value = useMemo(
    () => ({ holder, setHolder, pocketId, setPocketId, stepPocket, incidentId, setIncidentId, goTo }),
    [holder, setHolder, pocketId, setPocketId, stepPocket, incidentId, goTo],
  )
  return <SelectionContext.Provider value={value}>{children}</SelectionContext.Provider>
}

export function useSelection(): SelectionState {
  const ctx = useContext(SelectionContext)
  if (!ctx) throw new Error('useSelection must be used inside <SelectionProvider>')
  return ctx
}

export interface PocketView {
  holding: Holding | null
  row: BookPocket | null
  risk: RiskResponse | null
  /** The decision to show: the full analysis when we have it, else the book's line. */
  decision: Decision | null
  expectedLoss: number | null
  exitCost: number | null
  exitableNow: number | null
  topRisk: Incident | null
  position: number
  count: number
}

/** Everything known about the selected pocket, from whichever responses have arrived. */
export function usePocketView(): PocketView & {
  riskQuery: ReturnType<typeof useRisk>
  bookQuery: ReturnType<typeof useBook>
  /** The pocket's analysis is on its way (or the pocket list it depends on is). */
  riskWaiting: boolean
  /** Recorded mode, and nothing was recorded for this holder. */
  holderUnrecorded: boolean
} {
  const { holder, pocketId } = useSelection()
  const pockets = usePockets(holder)
  const bookQuery = useBook(holder, pocketId)
  const riskQuery = useRisk(holder, pocketId)
  const holdings = pockets.data?.holdings ?? []
  const holding = holdings.find((h) => h.id === pocketId) ?? null
  const row = bookQuery.data?.pockets.find((p) => p.id === pocketId) ?? null
  const risk = riskQuery.data ?? null
  const decision = risk?.decision ?? (row ? { verdict: row.verdict, exit_fraction: row.exit_fraction, sentence: row.sentence } : null)
  return {
    holding,
    row,
    risk,
    decision,
    expectedLoss: risk?.monte_carlo.expected_loss_usd ?? row?.expected_loss_usd ?? null,
    exitCost: risk?.exit.cost_full_usd ?? row?.exit_cost_usd ?? null,
    exitableNow: risk?.exit.f_max_now ?? row?.exit_fraction_now ?? null,
    topRisk: risk?.incidents.find((i) => i.loss_if_incident_usd > 0) ?? row?.top_risk ?? null,
    position: Math.max(0, holdings.findIndex((h) => h.id === pocketId)) + 1,
    count: holdings.length,
    riskQuery,
    bookQuery,
    riskWaiting: riskQuery.isLoading || pockets.isLoading,
    holderUnrecorded: pockets.data === null,
  }
}
