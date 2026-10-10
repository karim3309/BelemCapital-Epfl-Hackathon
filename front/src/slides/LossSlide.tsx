import { AnimatePresence, motion } from 'framer-motion'
import { useState } from 'react'
import type { Incident } from '../api/types'
import Slide from '../components/Slide'
import { Failure, Pending, Unrecorded } from '../components/States'
import { C } from '../lib/colors'
import { every, integer, pctAuto, usd } from '../lib/format'
import { usePocketView, useSelection } from '../state/selection'

const FAMILY_LABEL: Record<string, string> = {
  rwa_credit_event: 'Crédit RWA',
  stable_depeg: 'Depeg',
  protocol_exploit: 'Faille',
  curator_failure: 'Curateur',
  oracle_fault: 'Oracle faussé',
  admin_feed_compromise: 'Prix posé compromis',
  internal_rate_fault: 'Taux interne faussé',
  volatile_crash: 'Chute de marché',
}

function Stat({ label, value, note, tone }: { label: string; value: string; note?: string; tone?: string }) {
  return (
    <div className="flex flex-col gap-1">
      <p className="text-caption font-normal text-neutral1">{label}</p>
      <p className="text-sub font-semibold tabular" style={{ color: tone ?? C.chalk }}>
        {value}
      </p>
      {note && <p className="text-caption font-normal text-neutral1">{note}</p>}
    </div>
  )
}

function IncidentRow({
  incident,
  max,
  open,
  onToggle,
  onSimulate,
}: {
  incident: Incident
  max: number
  open: boolean
  onToggle: () => void
  onSimulate: () => void
}) {
  return (
    <li className={`rounded-xl ${open ? 'bg-surface' : ''}`}>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="grid w-full grid-cols-1 gap-2 rounded-xl px-4 py-4 text-left hover:bg-surface md:grid-cols-[minmax(0,1fr)_160px_120px_120px] md:items-center md:gap-6"
      >
        <span className="min-w-0">
          <span className="block text-body font-normal text-chalk">{incident.title}</span>
          <span className="mt-2 block h-[4px] bg-surface2">
            <span
              className="block h-full bg-warn"
              style={{ width: `${max > 0 ? Math.max(1, (incident.expected_loss_usd / max) * 100) : 0}%` }}
            />
          </span>
        </span>
        <span className="text-caption font-normal tabular text-neutral1 md:text-right">
          <span className="block text-body font-semibold text-chalk">{usd(incident.loss_if_incident_usd)}</span>
          si l'incident arrive
        </span>
        <span className="text-caption font-normal tabular text-neutral1 md:text-right">
          <span className="block text-body font-semibold text-chalk">{pctAuto(incident.p_horizon)}</span>
          notre estimation
          {every(incident.p_horizon) && <span className="block">{every(incident.p_horizon)}</span>}
        </span>
        <span className="text-caption font-normal tabular text-neutral1 md:text-right">
          <span className="block text-body font-semibold text-chalk">
            {incident.p_star === null ? '—' : incident.p_star >= 1 ? 'jamais' : pctAuto(incident.p_star)}
          </span>
          seuil p*
          {incident.p_star !== null && every(incident.p_star) && <span className="block">{every(incident.p_star)}</span>}
        </span>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="overflow-hidden"
          >
            <div className="flex flex-col gap-3 px-4 pb-5">
              <p className="text-caption font-normal text-neutral1">
                {FAMILY_LABEL[incident.family] ?? incident.family} · sévérité {pctAuto(incident.severity_range[0])} à{' '}
                {pctAuto(incident.severity_range[1])} · perte maximale {usd(incident.loss_if_incident_max_usd)}
              </p>
              <p className="text-body font-normal text-chalk">Règle : {incident.rule}</p>
              <p className="mono text-neutral1">{incident.contagion_path}</p>
              <button
                type="button"
                onClick={onSimulate}
                className="self-start text-body font-semibold text-accent hover:opacity-80"
              >
                Simuler cet incident
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </li>
  )
}

/** Slide 4 — question 2: how much can I lose? Monte Carlo, then each incident with its rule. */
export default function LossSlide() {
  const { setIncidentId, goTo } = useSelection()
  const v = usePocketView()
  const [openId, setOpenId] = useState<string | null>(null)
  const [showZero, setShowZero] = useState(false)
  const mc = v.risk?.monte_carlo
  const incidents = v.risk?.incidents ?? []
  const costly = incidents.filter((i) => i.loss_if_incident_usd > 0)
  const harmless = incidents.filter((i) => i.loss_if_incident_usd <= 0)
  const max = Math.max(0, ...costly.map((i) => i.expected_loss_usd))
  const value = v.holding?.value_usd ?? 0

  const simulate = (id: string) => {
    setIncidentId(id)
    goTo('incident')
  }

  return (
    <Slide id="perte" eyebrow="Question 2 sur 4 · Impact" title="Combien puis-je perdre ?">
      {mc ? (
        <>
          <div className="mt-8 grid grid-cols-2 gap-8 md:grid-cols-4">
            <div className="col-span-2 flex flex-col gap-1 md:col-span-1">
              <p className="text-caption font-normal text-neutral1">Perte attendue · {mc.horizon_days} jours</p>
              <p className="text-figure font-semibold tabular text-chalk">{usd(mc.expected_loss_usd)}</p>
              <p className="text-caption font-normal text-neutral1 tabular">
                {pctAuto(value ? mc.expected_loss_usd / value : null)} de la poche
              </p>
            </div>
            <Stat label="VaR 99,9 %" value={usd(mc.var999_usd)} note={`VaR 99 % : ${usd(mc.var99_usd)}`} />
            <Stat
              label="Probabilité d'une perte"
              value={pctAuto(mc.p_any_loss)}
              note={[every(mc.p_any_loss, mc.horizon_days), `sur ${mc.horizon_days} jours`].filter(Boolean).join(' · ')}
            />
            <Stat label="Tirages Monte Carlo" value={integer(mc.samples)} note="incidents tirés indépendamment" />
          </div>

          <div className="mt-10 min-h-0 flex-1">
            <div className="flex items-baseline justify-between gap-4">
              <h3 className="text-body font-semibold text-chalk">Incidents, du plus coûteux au moins coûteux</h3>
              <p className="hidden text-caption font-normal text-neutral1 md:block">
                Cliquez : la règle de calcul et le chemin de contagion.
              </p>
            </div>
            <ul className="thin-scroll mt-3 max-h-[40vh] overflow-y-auto">
              {costly.map((incident) => (
                <IncidentRow
                  key={incident.id}
                  incident={incident}
                  max={max}
                  open={openId === incident.id}
                  onToggle={() => setOpenId((cur) => (cur === incident.id ? null : incident.id))}
                  onSimulate={() => simulate(incident.id)}
                />
              ))}
              {showZero &&
                harmless.map((incident) => (
                  <IncidentRow
                    key={incident.id}
                    incident={incident}
                    max={max}
                    open={openId === incident.id}
                    onToggle={() => setOpenId((cur) => (cur === incident.id ? null : incident.id))}
                    onSimulate={() => simulate(incident.id)}
                  />
                ))}
            </ul>
            {harmless.length > 0 && (
              <button
                type="button"
                onClick={() => setShowZero((s) => !s)}
                className="mt-4 text-caption font-semibold text-accent hover:opacity-80"
              >
                {showZero ? 'Masquer' : 'Afficher'} les {harmless.length} incidents qui ne coûtent rien à cette poche
              </button>
            )}
            <p className="mt-4 text-caption font-normal text-neutral1">
              Probabilités : ordres de grandeur, affichés comme hypothèses. La décision repose sur p*, qui n'en dépend pas.
            </p>
          </div>
        </>
      ) : (
        <div className="mt-8 flex flex-col gap-8">
          {v.row && (
            <div className="flex flex-col gap-1">
              <p className="text-caption font-normal text-neutral1">Perte attendue sur l'horizon</p>
              <p className="text-figure font-semibold tabular text-chalk">{usd(v.row.expected_loss_usd)}</p>
              {v.topRisk && (
                <p className="text-body font-normal text-neutral1">
                  Risque principal : {v.topRisk.title}, {usd(v.topRisk.loss_if_incident_usd)} si l'incident arrive.
                </p>
              )}
            </div>
          )}
          {v.holderUnrecorded && <Unrecorded>Aucune réponse enregistrée pour ce détenteur.</Unrecorded>}
          {v.riskWaiting && <Pending title="Analyse de risque de la poche…" eta="10 à 30 s au premier appel." />}
          {v.riskQuery.isError && <Failure error={v.riskQuery.error} onRetry={() => v.riskQuery.refetch()} />}
          {v.riskQuery.data === null && (
            <Unrecorded>Le détail des incidents de cette poche n'a pas été enregistré.</Unrecorded>
          )}
        </div>
      )}
    </Slide>
  )
}
