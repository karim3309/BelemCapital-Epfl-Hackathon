import { usd, type Assessment } from '../lib/risk'

export type ScenarioMode = 'base' | 'stress' | 'custom'

interface Props {
  assessment: Assessment
  mode: ScenarioMode
  onBase: () => void
  onStress: () => void
}

const VERDICT_COLOR = { STAY: '#34C759', EXIT: '#FF3B30' } as const

/** Section C, right — one idea: the decision. The largest type on the page. */
export default function VerdictPanel({ assessment, mode, onBase, onStress }: Props) {
  const colour = VERDICT_COLOR[assessment.verdict]

  return (
    <div className="flex h-full flex-col">
      <p className="text-body font-normal text-neutral1">Signal</p>
      <p className="mt-4 text-verdict font-semibold" style={{ color: colour }}>
        {assessment.verdict}
      </p>

      <p className="mt-8 max-w-[460px] text-body font-normal text-chalk tabular">
        {assessment.reasoning}
      </p>
      <p className="mt-4 max-w-[460px] text-caption font-normal text-neutral1 tabular">
        {assessment.verdict === 'STAY'
          ? `Exiting now would cost ${usd(assessment.exitCostUsd)} to avoid ${usd(
              assessment.expectedLossUsd,
            )} of expected loss.`
          : `Exiting costs ${usd(assessment.exitCostUsd)} and avoids ${usd(
              assessment.expectedLossUsd,
            )} of expected loss — a ${usd(assessment.edgeUsd)} saving.`}
      </p>

      <p className="mt-10 text-caption font-normal text-neutral1">
        Signal confidence: {assessment.confidence}
      </p>

      <div className="mt-18">
        <p className="text-caption font-normal text-neutral1">Scenario</p>
        <div className="mt-4 flex items-center gap-10">
          <button
            type="button"
            onClick={onBase}
            aria-pressed={mode === 'base'}
            className={
              mode === 'base'
                ? 'border-b-2 border-accent pb-2 text-body font-semibold text-chalk'
                : 'pb-2 text-body font-normal text-neutral1 hover:text-chalk'
            }
          >
            Base
          </button>
          <button
            type="button"
            onClick={onStress}
            aria-pressed={mode !== 'base'}
            className={
              mode !== 'base'
                ? 'border-b-2 border-accent pb-2 text-body font-semibold text-chalk'
                : 'pb-2 text-body font-normal text-neutral1 hover:text-chalk'
            }
          >
            Stress
          </button>
          <span className="text-caption font-normal text-neutral1">
            {mode === 'base'
              ? 'Published base case'
              : mode === 'stress'
                ? 'All impact estimates doubled'
                : 'Levers adjusted by hand'}
          </span>
        </div>
      </div>
    </div>
  )
}
