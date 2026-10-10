import { AnimatePresence, motion } from 'framer-motion'
import { useState } from 'react'
import type { Incident } from '../api/types'
import Slide from '../components/Slide'
import { Failure, Pending, Unrecorded } from '../components/States'
import { C } from '../lib/colors'
import { every, integer, pctAuto, usd } from '../lib/format'
import { usePocketView, useSelection } from '../state/selection'

const FAMILY_LABEL: Record<string, string> = {
  rwa_credit_event: 'RWA credit',
  stable_depeg: 'Depeg',
  protocol_exploit: 'Exploit',
  curator_failure: 'Curator',
  oracle_fault: 'Skewed oracle',
  admin_feed_compromise: 'Compromised set price',
  internal_rate_fault: 'Skewed internal rate',
  volatile_crash: 'Market crash',
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
          if the incident happens
        </span>
        <span className="text-caption font-normal tabular text-neutral1 md:text-right">
          <span className="block text-body font-semibold text-chalk">{pctAuto(incident.p_horizon)}</span>
          our estimate
          {every(incident.p_horizon) && <span className="block">{every(incident.p_horizon)}</span>}
        </span>
        <span className="text-caption font-normal tabular text-neutral1 md:text-right">
          <span className="block text-body font-semibold text-chalk">
            {incident.p_star === null ? '—' : incident.p_star >= 1 ? 'never' : pctAuto(incident.p_star)}
          </span>
          threshold p*
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
                {FAMILY_LABEL[incident.family] ?? incident.family} · severity {pctAuto(incident.severity_range[0])} to{' '}
                {pctAuto(incident.severity_range[1])} · maximum loss {usd(incident.loss_if_incident_max_usd)}
              </p>
              <p className="text-body font-normal text-chalk">Rule: {incident.rule}</p>
              <p className="mono text-neutral1">{incident.contagion_path}</p>
              <button
                type="button"
                onClick={onSimulate}
                className="self-start text-body font-semibold text-accent hover:opacity-80"
              >
                Simulate this incident
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
    <Slide id="loss" eyebrow="Question 2 of 4 · Impact" title="How much can I lose?">
      {mc ? (
        <>
          <div className="mt-8 grid grid-cols-2 gap-8 md:grid-cols-4">
            <div className="col-span-2 flex flex-col gap-1 md:col-span-1">
              <p className="text-caption font-normal text-neutral1">Expected loss · {mc.horizon_days} days</p>
              <p className="text-figure font-semibold tabular text-chalk">{usd(mc.expected_loss_usd)}</p>
              <p className="text-caption font-normal text-neutral1 tabular">
                {pctAuto(value ? mc.expected_loss_usd / value : null)} of the pocket
              </p>
            </div>
            <Stat label="VaR 99.9%" value={usd(mc.var999_usd)} note={`VaR 99%: ${usd(mc.var99_usd)}`} />
            <Stat
              label="Probability of a loss"
              value={pctAuto(mc.p_any_loss)}
              note={[every(mc.p_any_loss, mc.horizon_days), `over ${mc.horizon_days} days`].filter(Boolean).join(' · ')}
            />
            <Stat label="Monte Carlo draws" value={integer(mc.samples)} note="incidents drawn independently" />
          </div>

          <div className="mt-10 min-h-0 flex-1">
            <div className="flex items-baseline justify-between gap-4">
              <h3 className="text-body font-semibold text-chalk">Incidents, from the most to the least costly</h3>
              <p className="hidden text-caption font-normal text-neutral1 md:block">
                Click: the computation rule and the contagion path.
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
                {showZero ? 'Hide' : 'Show'} the {harmless.length} incidents that cost this pocket nothing
              </button>
            )}
            <p className="mt-4 text-caption font-normal text-neutral1">
              Probabilities: orders of magnitude, shown as hypotheses. The decision rests on p*, which does not depend on them.
            </p>
          </div>
        </>
      ) : (
        <div className="mt-8 flex flex-col gap-8">
          {v.row && (
            <div className="flex flex-col gap-1">
              <p className="text-caption font-normal text-neutral1">Expected loss over the horizon</p>
              <p className="text-figure font-semibold tabular text-chalk">{usd(v.row.expected_loss_usd)}</p>
              {v.topRisk && (
                <p className="text-body font-normal text-neutral1">
                  Main risk: {v.topRisk.title}, {usd(v.topRisk.loss_if_incident_usd)} if the incident happens.
                </p>
              )}
            </div>
          )}
          {v.holderUnrecorded && <Unrecorded>No recorded response for this holder.</Unrecorded>}
          {v.riskWaiting && <Pending title="Analysing the pocket's risk…" eta="10 to 30 s on the first call." />}
          {v.riskQuery.isError && <Failure error={v.riskQuery.error} onRetry={() => v.riskQuery.refetch()} />}
          {v.riskQuery.data === null && (
            <Unrecorded>The incident details of this pocket were not recorded.</Unrecorded>
          )}
        </div>
      )}
    </Slide>
  )
}
