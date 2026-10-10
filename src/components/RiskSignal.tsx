import { useState } from 'react'
import { LAYER_META, type Position } from '../data/mock'
import { pct, severityColor, usd, type Assessment } from '../lib/risk'

interface Props {
  position: Position
  assessment: Assessment
}

function Row({ label, value, colour }: { label: string; value: string; colour?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-8 py-6">
      <span className="text-body font-normal text-neutral1">{label}</span>
      <span className="text-sub font-semibold tabular" style={{ color: colour ?? '#F5F5F7' }}>
        {value}
      </span>
    </div>
  )
}

/** Section C, left — one idea: where the loss comes from. */
export default function RiskSignal({ position, assessment }: Props) {
  const [hovered, setHovered] = useState<number | null>(null)

  const { expectedLossPct, expectedLossUsd, exitCostPct, contributions } = assessment
  const severity = severityColor(expectedLossPct)
  const leading = contributions.reduce((a, b) => (b.pct > a.pct ? b : a), contributions[0])
  const hoveredContribution = contributions.find((c) => c.layer === hovered)

  return (
    <div>
      <p className="text-body font-normal text-neutral1">Expected loss</p>
      <p className="mt-4 text-figure font-semibold tabular" style={{ color: severity }}>
        {pct(expectedLossPct)}
      </p>
      <p className="mt-4 text-body font-normal text-neutral1 tabular">
        {usd(expectedLossUsd)} of {usd(position.tvl_exposure)} exposure, over a 30-day horizon.
      </p>

      <div className="relative mt-18">
        <div className="flex h-[8px] w-full">
          {contributions.map((contribution) => (
            <div
              key={contribution.layer}
              onMouseEnter={() => setHovered(contribution.layer)}
              onMouseLeave={() => setHovered(null)}
              style={{
                width: `${Math.max(contribution.share * 100, 0.6)}%`,
                backgroundColor: LAYER_META[contribution.layer].color,
                opacity: hovered === null || hovered === contribution.layer ? 1 : 0.4,
              }}
              className="h-full"
              aria-label={`${contribution.label} ${pct(contribution.pct, 2)}`}
            />
          ))}
        </div>

        {hoveredContribution && (
          <div className="absolute left-0 top-[-44px] bg-surface px-4 py-2 text-caption font-normal text-chalk rounded-md tabular">
            {hoveredContribution.label} · {pct(hoveredContribution.pct, 2)} of position ·{' '}
            {Math.round(hoveredContribution.share * 100)}% of total loss
          </div>
        )}
      </div>

      <p className="mt-6 text-caption font-normal text-neutral1 tabular">
        {leading.label} drives {Math.round(leading.share * 100)}% of expected loss.
      </p>

      <div className="mt-18">
        <Row label="Execution cost to exit" value={pct(exitCostPct)} />
        <Row label="Expected loss if staying" value={pct(expectedLossPct)} colour={severity} />
        <Row
          label="Break-even threshold"
          value={`${assessment.breakEvenMultiple.toFixed(1)}× base loss`}
        />
      </div>

      <p className="mt-8 max-w-[560px] text-caption font-normal text-neutral1 tabular">
        Staying stops being optimal once expected loss passes {pct(assessment.breakEvenLossPct)}
        {assessment.breakEvenOraclePct !== null
          ? ` — reached at an oracle failure probability of ${pct(assessment.breakEvenOraclePct, 0)}.`
          : assessment.verdict === 'STAY'
            ? ' — out of reach even if the oracle fails with certainty.'
            : ' — already passed, with the oracle layer alone over the line.'}
      </p>
    </div>
  )
}
