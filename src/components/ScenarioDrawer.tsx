import { useEffect, type CSSProperties } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { pct, severityColor, usd, type Assessment, type Scenario } from '../lib/risk'

interface Props {
  open: boolean
  scenario: Scenario
  assessment: Assessment
  onChange: (next: Scenario) => void
  onReset: () => void
  onClose: () => void
}

interface SliderProps {
  label: string
  readout: string
  min: number
  max: number
  step: number
  value: number
  onChange: (value: number) => void
  ticks: [string, string]
}

function Slider({ label, readout, min, max, step, value, onChange, ticks }: SliderProps) {
  return (
    <div className="mt-12">
      <div className="flex items-baseline justify-between gap-6">
        <label className="text-body font-normal text-chalk" htmlFor={label}>
          {label}
        </label>
        <span className="text-body font-semibold text-chalk tabular">{readout}</span>
      </div>
      <input
        id={label}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        style={{ '--fill': `${((value - min) / (max - min)) * 100}%` } as CSSProperties}
        className="slider mt-6 accent-accent"
      />
      <div className="flex justify-between text-caption font-normal text-neutral1">
        <span>{ticks[0]}</span>
        <span>{ticks[1]}</span>
      </div>
    </div>
  )
}

/** Stress scenario levers. Every change re-runs the engine on the next render. */
export default function ScenarioDrawer({
  open,
  scenario,
  assessment,
  onChange,
  onReset,
  onClose,
}: Props) {
  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            key="scenario-overlay"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={onClose}
            className="fixed inset-0 z-40 bg-ink/80"
            aria-hidden="true"
          />
          <motion.aside
            key="scenario-drawer"
            initial={{ x: 420 }}
            animate={{ x: 0 }}
            exit={{ x: 420 }}
            transition={{ type: 'tween', duration: 0.28, ease: [0.32, 0.72, 0, 1] }}
            className="fixed right-0 top-0 z-50 h-full w-[420px] max-w-full overflow-y-auto bg-surface px-12 py-18"
            role="dialog"
            aria-label="Stress scenario"
          >
            <div className="flex items-start justify-between gap-8">
              <h3 className="text-panel font-semibold text-chalk">Stress scenario</h3>
              <button
                type="button"
                onClick={onClose}
                aria-label="Close"
                className="shrink-0 text-sub font-normal text-neutral1 hover:text-chalk"
              >
                ×
              </button>
            </div>

            <div className="mt-12">
              <p className="text-caption font-normal text-neutral1">Expected loss</p>
              <p
                className="mt-2 text-figure font-semibold tabular"
                style={{ color: severityColor(assessment.expectedLossPct) }}
              >
                {pct(assessment.expectedLossPct)}
              </p>
              <p className="mt-3 text-body font-semibold tabular text-chalk">
                {assessment.verdict} · exit cost {pct(assessment.exitCostPct)}
              </p>
              <p className="mt-2 text-caption font-normal text-neutral1 tabular">
                {usd(assessment.expectedLossUsd)} at risk · confidence {assessment.confidence}
              </p>
            </div>

            <Slider
              label="Oracle failure probability"
              readout={pct(scenario.oracleFailureProb, 0)}
              min={0}
              max={100}
              step={1}
              value={scenario.oracleFailureProb}
              onChange={(oracleFailureProb) => onChange({ ...scenario, oracleFailureProb })}
              ticks={['0%', '100%']}
            />
            <Slider
              label="Liquidation cascade factor"
              readout={`${scenario.cascadeFactor.toFixed(1)}×`}
              min={1}
              max={5}
              step={0.1}
              value={scenario.cascadeFactor}
              onChange={(cascadeFactor) => onChange({ ...scenario, cascadeFactor })}
              ticks={['1×', '5×']}
            />
            <Slider
              label="Slippage on exit"
              readout={pct(scenario.slippagePct)}
              min={0}
              max={30}
              step={0.5}
              value={scenario.slippagePct}
              onChange={(slippagePct) => onChange({ ...scenario, slippagePct })}
              ticks={['0%', '30%']}
            />
            <Slider
              label="TVL drain speed"
              readout={scenario.drainSpeed === 'fast' ? 'Fast' : 'Slow'}
              min={0}
              max={1}
              step={1}
              value={scenario.drainSpeed === 'fast' ? 1 : 0}
              onChange={(value) =>
                onChange({ ...scenario, drainSpeed: value === 1 ? 'fast' : 'slow' })
              }
              ticks={['Slow', 'Fast']}
            />

            <button
              type="button"
              onClick={onReset}
              className="mt-18 mb-18 text-caption font-normal text-neutral1 hover:text-chalk"
            >
              Reset to base case
            </button>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  )
}
