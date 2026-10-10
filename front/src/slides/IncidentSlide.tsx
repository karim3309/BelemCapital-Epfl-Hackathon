import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { useGraph, useIncident } from '../api/hooks'
import { recorded } from '../api/recorded'
import { useSource } from '../api/source'
import type { Incident, IncidentMode, IncidentRequest } from '../api/types'
import GraphCanvas from '../components/GraphCanvas'
import Slide from '../components/Slide'
import { Failure, Pending, Unrecorded } from '../components/States'
import VerdictWord from '../components/VerdictWord'
import { C, verdictColor } from '../lib/colors'
import { pct, pctAuto, usd } from '../lib/format'
import { pathFromEdges, pathTo } from '../lib/graph'
import { useDebounced } from '../lib/useDebounced'
import { usePocketView, useSelection } from '../state/selection'

// Belief slider on a log scale: 0,01 % to 100 %, where incident probabilities actually live.
const LOG_MIN = -4
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
  const example = recorded.incidents.find((r) => r.pocket.id === pocketId)?.incident_mode

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
              {usd(i.loss_if_incident_usd)} · seuil {i.p_star === null ? '—' : i.p_star >= 1 ? 'jamais' : pctAuto(i.p_star)}
            </span>
          </button>
        </li>
      ))}
    </ul>
  )

  return (
    <Slide id="incident" eyebrow="Question 4 sur 4 · Décision" title="Et si ça arrive ?">
      {!v.risk && (
        <div className="mt-8">
          {v.holderUnrecorded && <Unrecorded>Aucune réponse enregistrée pour ce détenteur.</Unrecorded>}
          {v.riskWaiting && <Pending title="Analyse de risque de la poche…" eta="10 à 30 s au premier appel." />}
          {v.riskQuery.isError && <Failure error={v.riskQuery.error} onRetry={() => v.riskQuery.refetch()} />}
          {v.riskQuery.data === null && <Unrecorded>Les incidents de cette poche n'ont pas été enregistrés.</Unrecorded>}
        </div>
      )}

      {v.risk && !incident && (
        <p className="mt-8 max-w-[720px] text-lead font-normal text-chalk">
          Aucun incident ne coûte quoi que ce soit à cette poche : il n'y a pas de seuil à tester.
        </p>
      )}

      {v.risk && incident && (
        <div className="mt-8 grid flex-1 grid-cols-1 gap-10 lg:grid-cols-[260px_minmax(0,1fr)_minmax(0,0.9fr)] lg:gap-12">
          <div className="hidden lg:block">
            <p className="mb-3 text-caption font-normal text-neutral1">Incidents qui coûtent à cette poche</p>
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
                ? `« ${incident.title} » : aucune sortie possible maintenant.`
                : pStar >= 1
                  ? `Même certain, « ${incident.title} » coûterait moins que la sortie.`
                  : `Croyez-vous à plus de ${pctAuto(pStar)} de risque « ${incident.title} » ?`}
            </p>

            <div className="mt-6">
              <div className="flex items-baseline justify-between gap-4">
                <label htmlFor="belief" className="text-body font-normal text-neutral1">
                  Votre estimation, sur l'horizon
                </label>
                <span className="text-sub font-semibold tabular text-chalk">{pctAuto(p)}</span>
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
                {pStar !== null && pStar < 1 && <Marker at={toSlider(pStar)} label={`seuil p* ${pctAuto(pStar)}`} color={C.chalk} />}
                <Marker at={toSlider(incident.p_horizon)} label="notre estimation" color={C.neutral} />
              </div>
            </div>

            {source.mode === 'live' && severity !== undefined && incident.severity_range[1] > incident.severity_range[0] && (
              <div className="mt-4">
                <div className="flex items-baseline justify-between gap-4">
                  <label htmlFor="severity" className="text-body font-normal text-neutral1">
                    Sévérité du choc
                  </label>
                  <span className="text-body font-semibold tabular text-chalk">{pct(severity, 0)}</span>
                </div>
                <input
                  id="severity"
                  type="range"
                  min={incident.severity_range[0]}
                  max={incident.severity_range[1]}
                  step={(incident.severity_range[1] - incident.severity_range[0]) / 100}
                  value={severity}
                  onChange={(e) => setSeverity(Number(e.target.value))}
                  style={
                    {
                      '--fill': `${((severity - incident.severity_range[0]) / (incident.severity_range[1] - incident.severity_range[0])) * 100}%`,
                    } as CSSProperties
                  }
                  className="slider mt-3"
                />
              </div>
            )}

            <div className="mt-4 flex flex-wrap items-end gap-x-6 gap-y-2">
              <VerdictWord verdict={verdict} className="text-[clamp(80px,9.5vw,148px)] leading-[0.9] tracking-[-0.05em]" />
              {verdict === 'EXIT' && (
                <span className="pb-3 text-sub font-semibold tabular" style={{ color: verdictColor('EXIT') }}>
                  {exact ? (fraction < 0.999 ? `${pct(fraction, 0)} de la poche` : 'toute la poche') : `jusqu'à ${pct(fMax, 0)} sortables`}
                </span>
              )}
            </div>

            <p className={`mt-4 text-body font-normal text-chalk tabular ${query.isFetching ? 'opacity-60' : ''}`}>
              {exact
                ? exact.sentence
                : pStar === null
                  ? 'Aucune liquidité pour sortir maintenant : rester est la seule option.'
                  : `Si l'incident arrive, la poche perd ${usd(loss)}. ${
                      verdict === 'EXIT'
                        ? `À ${pctAuto(p)}, au-dessus du seuil, sortir coûte moins que rester.`
                        : `À ${pctAuto(p)}, sous le seuil, rester coûte moins que sortir.`
                    }`}
            </p>
            <p className="mt-3 text-caption font-normal text-neutral1">
              {exact
                ? `Calcul exact du backend · probabilité ${exact.p_source === 'manager' ? 'fixée par vous' : 'par défaut'}.`
                : source.mode === 'live'
                  ? query.isError
                    ? "Seuil p* du backend appliqué ; le calcul exact n'a pas abouti."
                    : 'Seuil p* du backend appliqué tout de suite ; le calcul exact arrive.'
                  : `Règle du backend : sortez si vous croyez à plus de p*, coût de sortie ÷ perte si l'incident arrive.${
                      convexExit ? ' Sous le seuil, une sortie partielle peut rester rentable : calcul exact en direct.' : ''
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
                <span className="text-caption font-normal text-neutral1">Exemple enregistré, calculé par le backend</span>
                <span className="text-body font-normal text-chalk">
                  « {example.title} », sévérité {pct(example.severity, 0)}, probabilité {pct(example.p_used, 0)} →{' '}
                  <span className="font-semibold" style={{ color: verdictColor(example.verdict) }}>
                    {example.verdict} {example.exit_fraction > 0 && example.exit_fraction < 0.999 ? pct(example.exit_fraction, 0) : ''}
                  </span>
                </span>
                <span className="text-caption font-semibold text-accent">Rejouer cet exemple</span>
              </button>
            )}
          </div>

          <div className="flex min-w-0 flex-col">
            <p className="text-caption font-normal text-neutral1">Chemin de contagion</p>
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
