import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { useGraph, useIncident } from '../api/hooks'
import { recordedExample } from '../api/recorded'
import { useSource } from '../api/source'
import type { Incident, IncidentMode, IncidentRequest } from '../api/types'
import GraphCanvas from '../components/GraphCanvas'
import Slide from '../components/Slide'
import { Failure, Pending, Unrecorded } from '../components/States'
import VerdictWord from '../components/VerdictWord'
import { C, verdictColor } from '../lib/colors'
import { DEFAULT_HORIZON_DAYS, pct, pctAuto, pctFreq, usd } from '../lib/format'
import { pathFromEdges, pathTo } from '../lib/graph'
import { useDebounced } from '../lib/useDebounced'
import { usePocketView, useSelection } from '../state/selection'

// Belief slider on a log scale: 0.01% to 100%, where incident probabilities actually live.
const LOG_MIN = -4
/** Upper end of the severity slider when the calibrated range stops lower (e.g. a fiat stablecoin: 2-12 %). */
const EXPLORE_MAX_SEVERITY = 0.5
const toSlider = (p: number) => ((Math.log10(Math.max(p, 1e-4)) - LOG_MIN) / -LOG_MIN) * 1000
const fromSlider = (s: number) => 10 ** (LOG_MIN + (-LOG_MIN * s) / 1000)

const same = (a: number | undefined, b: number | undefined) =>
  a !== undefined && b !== undefined && Math.abs(a - b) < 1e-9

function Marker({ at, label, color }: { at: number; label: string; color: string }) {
  return (
    <span className="pointer-events-none absolute top-0 flex -translate-x-1/2 flex-col items-center" style={{ left: `${at / 10}%` }}>
      <span className="h-[18px] w-[2px]" style={{ backgroundColor: color }} />
      <span className="mt-1 whitespace-nowrap text-caption font-normal tabular" style={{ color }}>
        {label}
      </span>
    </span>
  )
}

/** Slide 6 — question 4: if this incident happens, do I leave? The manager's belief against p*. */
export default function IncidentSlide() {
  const { holder, pocketId, incidentId, setIncidentId } = useSelection()
  const { source } = useSource()
  const v = usePocketView()
  const graphQuery = useGraph(holder, pocketId)
  const graph = graphQuery.data?.graph ?? null
  const incidents = useMemo(() => (v.risk?.incidents ?? []).filter((i) => i.loss_if_incident_usd > 0), [v.risk])
  const incident: Incident | null =
    incidents.find((i) => i.id === incidentId) ?? (v.risk?.incidents.find((i) => i.id === incidentId) || incidents[0]) ?? null

  const [p, setP] = useState(0.01)
  const days = v.risk?.monte_carlo.horizon_days ?? DEFAULT_HORIZON_DAYS
  const [severity, setSeverity] = useState<number | undefined>(undefined)
  // Settings to apply once a requested incident switch has happened (the recorded example).
  const pendingRef = useRef<{ id: string; p: number; severity: number } | null>(null)

  // A new incident starts from our own estimate and the backend's default severity (live only:
  // recorded data has no loss curve to move along).
  useEffect(() => {
    if (!incident) return
    const pending = pendingRef.current
    if (pending && pending.id === incident.id) {
      pendingRef.current = null
      setP(pending.p)
      setSeverity(pending.severity)
      return
    }
    setP(Math.max(incident.p_horizon, 1e-4))
    setSeverity(source.mode === 'live' ? (incident.severity_range[0] + incident.severity_range[1]) / 2 : undefined)
  }, [incident?.id, source.mode]) // eslint-disable-line react-hooks/exhaustive-deps

  // Exploration goes beyond the calibrated range (stress tests on past crises), up to 50 %, never below it.
  const sevMax = incident ? Math.max(incident.severity_range[1], EXPLORE_MAX_SEVERITY) : EXPLORE_MAX_SEVERITY
  const req: IncidentRequest | null = incident ? { incident: incident.id, p, ...(severity !== undefined ? { severity } : {}) } : null
  const settledReq = useDebounced(req, source.mode === 'live' ? 250 : 0)
  const query = useIncident(holder, pocketId, settledReq)
  const current = query.isPlaceholderData ? null : query.data?.incident_mode ?? null

  // p* and the loss depend on the incident and its severity, never on p: the last exact answer
  // for this same shock keeps serving them while the belief slider moves.
  const [shock, setShock] = useState<IncidentMode | null>(null)
  useEffect(() => {
    if (current) setShock(current)
  }, [current])
  const sameShock =
    !!shock && !!incident && shock.incident === incident.id && severity !== undefined && same(shock.severity, severity)
  const pStar = sameShock ? shock!.p_star : incident?.p_star ?? null
  const loss = sameShock ? shock!.loss_if_incident_usd : incident?.loss_if_incident_usd ?? 0
  const exact =
    current && incident && current.incident === incident.id && same(current.p_used, p) &&
    (severity === undefined || same(current.severity, severity))
      ? current
      : null

  const fMax = v.risk?.exit.f_max_now ?? 0
  const thresholdVerdict = pStar !== null && p > pStar ? 'EXIT' : 'STAY'
  const verdict = exact ? exact.verdict : thresholdVerdict
  const fraction = exact ? exact.exit_fraction : thresholdVerdict === 'EXIT' ? fMax : 0
  const convexExit = v.holding?.kind === 'morpho_market_borrow'

  const highlight = graph && incident ? (exact?.contagion_edges?.length ? pathFromEdges(exact.contagion_edges) : pathTo(graph, incident.target)) : null
  const example = recordedExample(holder, pocketId)

  const pickList = (
    <ul className="thin-scroll flex max-h-[48vh] flex-col gap-1 overflow-y-auto">
      {incidents.map((i) => (
        <li key={i.id}>
          <button
            type="button"
            onClick={() => setIncidentId(i.id)}
            aria-pressed={i.id === incident?.id}
            className={`w-full rounded-xl px-4 py-3 text-left ${i.id === incident?.id ? 'bg-surface' : 'hover:bg-surface'}`}
          >
            <span className="block text-body font-normal text-chalk">{i.title}</span>
            <span className="block text-caption font-normal tabular text-neutral1">
              {usd(i.loss_if_incident_usd)} · threshold {i.p_star === null ? '—' : i.p_star >= 1 ? 'never' : pctFreq(i.p_star, days)}
            </span>
          </button>
        </li>
      ))}
    </ul>
  )

  return (
    <Slide id="incident" eyebrow="Question 4 of 4 · Decision" title="What if it happens?">
      {!v.risk && (
        <div className="mt-8">
          {v.holderUnrecorded && <Unrecorded>No recorded response for this holder.</Unrecorded>}
          {v.riskWaiting && <Pending title="Analysing the pocket's risk…" eta="10 to 30 s on the first call." />}
          {v.riskQuery.isError && <Failure error={v.riskQuery.error} onRetry={() => v.riskQuery.refetch()} />}
          {v.riskQuery.data === null && <Unrecorded>The incidents of this pocket were not recorded.</Unrecorded>}
        </div>
      )}

      {v.risk && !incident && (
        <p className="mt-8 max-w-[720px] text-lead font-normal text-chalk">
          No incident costs this pocket anything: there is no threshold to test.
        </p>
      )}

      {v.risk && incident && (
        <div className="mt-8 grid flex-1 grid-cols-1 gap-10 lg:grid-cols-[260px_minmax(0,1fr)_minmax(0,0.9fr)] lg:gap-12">
          <div className="hidden lg:block">
            <p className="mb-3 text-caption font-normal text-neutral1">Incidents that cost this pocket</p>
            {pickList}
          </div>
          <div className="lg:hidden">
            <label htmlFor="incident-pick" className="text-caption font-normal text-neutral1">
              Incident
            </label>
            <select
              id="incident-pick"
              value={incident.id}
              onChange={(e) => setIncidentId(e.target.value)}
              className="mt-2 w-full rounded-xl bg-surface px-4 py-3 text-body text-chalk outline-none"
            >
              {incidents.map((i) => (
                <option key={i.id} value={i.id}>
                  {i.title}
                </option>
              ))}
            </select>
          </div>

          <div className="flex min-w-0 flex-col">
            <p className="text-lead font-normal text-chalk [text-wrap:balance]">
              {pStar === null
                ? `“${incident.title}”: no exit possible right now.`
                : pStar >= 1
                  ? `Even if certain, “${incident.title}” would cost less than exiting.`
                  : `Do you believe the risk “${incident.title}” is above ${pctFreq(pStar, days)}?`}
            </p>

            <div className="mt-6">
              <div className="flex items-baseline justify-between gap-4">
                <label htmlFor="belief" className="text-body font-normal text-neutral1">
                  Your estimate, over the horizon
                </label>
                <span className="text-sub font-semibold tabular text-chalk">{pctFreq(p, days)}</span>
              </div>
              <input
                id="belief"
                type="range"
                min={0}
                max={1000}
                step={1}
                value={toSlider(p)}
                onChange={(e) => setP(fromSlider(Number(e.target.value)))}
                style={{ '--fill': `${toSlider(p) / 10}%` } as CSSProperties}
                className="slider mt-3"
              />
              <div className="relative h-10">
                {pStar !== null && pStar < 1 && <Marker at={toSlider(pStar)} label={`threshold p* ${pctAuto(pStar)}`} color={C.chalk} />}
                <Marker at={toSlider(incident.p_horizon)} label="our estimate" color={C.neutral} />
              </div>
            </div>

            {source.mode === 'live' && severity !== undefined && incident.severity_range[1] > incident.severity_range[0] && (
              <div className="mt-4">
                <div className="flex items-baseline justify-between gap-4">
                  <label htmlFor="severity" className="text-body font-normal text-neutral1">
                    Shock severity
                  </label>
                  <span className="text-body font-semibold tabular text-chalk">{pct(severity, 0)}</span>
                </div>
                <input
                  id="severity"
                  type="range"
                  min={0}
                  max={sevMax}
                  step={sevMax / 200}
                  value={severity}
                  onChange={(e) => setSeverity(Number(e.target.value))}
                  style={{ '--fill': `${(severity / sevMax) * 100}%` } as CSSProperties}
                  className="slider mt-3"
                />
                <p className="mt-2 text-caption font-normal text-neutral1">
                  Calibrated range {pct(incident.severity_range[0], 0)}–{pct(incident.severity_range[1], 0)} (hypothesis,
                  used by the Monte Carlo).{' '}
                  {severity > incident.severity_range[1] + 1e-9
                    ? 'You are beyond it: stress test, not the calibrated case.'
                    : `Up to ${pct(sevMax, 0)} to stress-test past crises.`}
                </p>
              </div>
            )}

            <div className="mt-4 flex flex-wrap items-end gap-x-6 gap-y-2">
              <VerdictWord verdict={verdict} className="text-[clamp(80px,9.5vw,148px)] leading-[0.9] tracking-[-0.05em]" />
              {verdict === 'EXIT' && (
                <span className="pb-3 text-sub font-semibold tabular" style={{ color: verdictColor('EXIT') }}>
                  {exact ? (fraction < 0.999 ? `${pct(fraction, 0)} of the pocket` : 'the whole pocket') : `up to ${pct(fMax, 0)} exitable`}
                </span>
              )}
            </div>

            <p className={`mt-4 text-body font-normal text-chalk tabular ${query.isFetching ? 'opacity-60' : ''}`}>
              {exact
                ? exact.sentence
                : pStar === null
                  ? 'No liquidity to exit right now: staying is the only option.'
                  : `If the incident happens, the pocket loses ${usd(loss)}. ${
                      verdict === 'EXIT'
                        ? `At ${pctAuto(p)}, above the threshold, exiting costs less than staying.`
                        : `At ${pctAuto(p)}, below the threshold, staying costs less than exiting.`
                    }`}
            </p>
            <p className="mt-3 text-caption font-normal text-neutral1">
              {exact
                ? `Exact backend computation · probability ${exact.p_source === 'manager' ? 'set by you' : 'default'}.`
                : source.mode === 'live'
                  ? query.isError
                    ? "Backend threshold p* applied; the exact computation did not complete."
                    : 'Backend threshold p* applied right away; the exact computation is on its way.'
                  : `Backend rule: exit if you believe in more than p*, exit cost ÷ loss if the incident happens.${
                      convexExit ? ' Below the threshold, a partial exit can still pay off: exact computation live.' : ''
                    }`}
            </p>
            {query.isError && source.mode === 'live' && (
              <div className="mt-4">
                <Failure error={query.error} onRetry={() => query.refetch()} />
              </div>
            )}

            {source.mode === 'recorded' && example && (
              <button
                type="button"
                onClick={() => {
                  const id = v.risk!.incidents.find((i) => example.incident.startsWith(i.id))?.id ?? example.incident
                  if (incident.id === id) {
                    setP(example.p_used)
                    setSeverity(example.severity)
                  } else {
                    pendingRef.current = { id, p: example.p_used, severity: example.severity }
                    setIncidentId(id)
                  }
                }}
                className="mt-5 flex flex-col items-start gap-1 rounded-xl bg-surface p-4 text-left hover:bg-surface2"
              >
                <span className="text-caption font-normal text-neutral1">Recorded example, computed by the backend</span>
                <span className="text-body font-normal text-chalk">
                  “{example.title}”, severity {pct(example.severity, 0)}, probability {pct(example.p_used, 0)} →{' '}
                  <span className="font-semibold" style={{ color: verdictColor(example.verdict) }}>
                    {example.verdict} {example.exit_fraction > 0 && example.exit_fraction < 0.999 ? pct(example.exit_fraction, 0) : ''}
                  </span>
                </span>
                <span className="text-caption font-semibold text-accent">Replay this example</span>
              </button>
            )}
          </div>

          <div className="flex min-w-0 flex-col">
            <p className="text-caption font-normal text-neutral1">Contagion path</p>
            {graph ? (
              <GraphCanvas
                graph={graph}
                highlight={highlight}
                targetId={incident.target}
                quietLabels
                autoHeight={false}
                className="mt-3 h-[44vh] min-h-[320px]"
              />
            ) : (
              <p className="mono mt-3 text-neutral1">{incident.contagion_path}</p>
            )}
            <p className="mt-3 text-caption font-normal text-neutral1">{incident.rule}</p>
          </div>
        </div>
      )}
    </Slide>
  )
}
