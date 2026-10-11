import { motion } from 'framer-motion'
import { recordedCoverage } from '../api/recorded'
import { useSource } from '../api/source'
import Slide from '../components/Slide'
import { Failure, Pending, Unrecorded } from '../components/States'
import VerdictWord from '../components/VerdictWord'
import { C, verdictColor } from '../lib/colors'
import { DEFAULT_HORIZON_DAYS, kindLabel, pct, pctAuto, pctFreq, usd, usdShort } from '../lib/format'
import { usePocketView, useSelection } from '../state/selection'

function Big({ label, value, note, tone }: { label: string; value: string; note?: string; tone?: string }) {
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

/** Slide 2: the answer. Largest type in the deck, nothing competing with it. */
export default function VerdictSlide() {
  const { holder, stepPocket, goTo, setIncidentId } = useSelection()
  const { source } = useSource()
  const v = usePocketView()
  const d = v.decision
  const partial = d && d.verdict === 'EXIT' && d.exit_fraction > 0 && d.exit_fraction < 0.999
  // Both bars come from the backend (decision.avoided_usd / exit_cost_usd): the front computes no risk, so the
  // bars can never contradict the sentence. Fallback only for an old recording without those fields.
  const avoided =
    d?.avoided_usd ?? (v.expectedLoss !== null && v.exitableNow !== null ? v.expectedLoss * v.exitableNow : null)
  const exitCost = d?.exit_cost_usd ?? v.exitCost
  const unavoidable = d?.expected_loss_unavoidable_usd ?? 0
  const scale = Math.max(avoided ?? 0, exitCost ?? 0, 1)
  const top = v.topRisk
  const days = v.risk?.monte_carlo.horizon_days ?? DEFAULT_HORIZON_DAYS
  const fullAnalysis = v.risk !== null || (source.mode === 'recorded' && v.holding && recordedCoverage(holder, v.holding.id).risk)

  return (
    <Slide
      id="verdict"
      eyebrow={
        v.holding
          ? `Pocket ${v.position} of ${v.count} · ${kindLabel(v.holding.kind)} · ${usdShort(v.holding.value_usd)} · ${pct(v.holding.share_of_book, 1)} of the portfolio`
          : 'Verdict'
      }
      title={v.holding?.label ?? 'Stay or exit?'}
    >
      <div className="mt-6 grid flex-1 grid-cols-1 items-center gap-12 lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)] lg:gap-16">
        <div className="flex flex-col">
          <div className="flex items-center gap-2 md:gap-6">
            <button
              type="button"
              onClick={() => stepPocket(-1)}
              aria-label="Previous pocket"
              className="hidden h-14 w-14 shrink-0 items-center justify-center rounded-xl text-sub text-neutral1 hover:bg-surface hover:text-chalk md:flex"
            >
              ‹
            </button>
            {d ? (
              <VerdictWord verdict={d.verdict} />
            ) : v.holderUnrecorded ? (
              <Unrecorded>No recorded response for this holder.</Unrecorded>
            ) : v.riskQuery.isError && (v.bookQuery.isError || v.bookQuery.isSuccess) ? (
              <Failure error={v.riskQuery.error} onRetry={() => v.riskQuery.refetch()} />
            ) : (
              <Pending title="Computing the verdict…" eta="10 to 30 s on the first call for this pocket." />
            )}
            <button
              type="button"
              onClick={() => stepPocket(1)}
              aria-label="Next pocket"
              className="hidden h-14 w-14 shrink-0 items-center justify-center rounded-xl text-sub text-neutral1 hover:bg-surface hover:text-chalk md:flex"
            >
              ›
            </button>
          </div>
          {partial && (
            <p className="mt-2 text-sub font-semibold tabular" style={{ color: verdictColor('EXIT') }}>
              Exit {pct(d!.exit_fraction, 0)} of the pocket
            </p>
          )}
          {d && (
            <motion.p
              key={d.sentence}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.4 }}
              className="mt-8 max-w-[720px] text-lead font-normal text-chalk tabular"
            >
              {d.sentence}
            </motion.p>
          )}
          {d && !fullAnalysis && (
            <p className="mt-4 text-caption font-normal text-neutral1">
              Verdict from the portfolio analysis. This pocket's details are computed live.
            </p>
          )}
        </div>

        <div className="flex flex-col gap-10">
          <div className="flex flex-col gap-6">
            <div>
              <div className="flex items-baseline justify-between gap-4">
                <span className="text-body font-normal text-neutral1">Exiting would avoid</span>
                <span className="text-sub font-semibold tabular text-chalk">{usd(avoided)}</span>
              </div>
              <div className="mt-2 h-[8px] bg-surface2">
                <motion.div
                  className="h-full bg-warn"
                  initial={false}
                  animate={{ width: `${((avoided ?? 0) / scale) * 100}%` }}
                  transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
                />
              </div>
              <p className="mt-2 text-caption font-normal text-neutral1 tabular">
                avoidable expected loss {usd(d?.expected_loss_avoidable_usd ?? v.expectedLoss)} ×{' '}
                {pctAuto(v.exitableNow)} exitable now
                {unavoidable >= 1 ? ` · ${usd(unavoidable)} not avoidable by exiting (stays with the asset you get back)` : ''}
              </p>
            </div>
            <div>
              <div className="flex items-baseline justify-between gap-4">
                <span className="text-body font-normal text-neutral1">Exiting would cost</span>
                <span className="text-sub font-semibold tabular text-chalk">{usd(exitCost)}</span>
              </div>
              <div className="mt-2 h-[8px] bg-surface2">
                <motion.div
                  className="h-full bg-accent"
                  initial={false}
                  animate={{ width: `${((exitCost ?? 0) / scale) * 100}%` }}
                  transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
                />
              </div>
              <p className="mt-2 text-caption font-normal text-neutral1">certain cost to exit the exitable share, measured at the block</p>
            </div>
          </div>

          {top && top.p_star !== null && top.p_star < 1 && (
            <button
              type="button"
              onClick={() => {
                setIncidentId(top.id)
                goTo('incident')
              }}
              className="flex flex-col items-start gap-2 rounded-xl bg-surface p-6 text-left hover:bg-surface2"
            >
              <span className="text-caption font-normal text-neutral1">The 3 a.m. question</span>
              <span className="text-body font-normal text-chalk">
                Do you believe the risk “{top.title}” is above <span className="font-semibold">{pctAuto(top.p_star)}</span>
                ?
              </span>
              <span className="text-caption font-normal text-neutral1 tabular">
                Our estimate: {pctFreq(top.p_horizon, days)}. Above the threshold, exiting costs less than staying.
              </span>
              <span className="text-caption font-semibold text-accent">Test your estimate</span>
            </button>
          )}
          {top && (top.p_star === null || top.p_star >= 1) && (
            <Big
              label="Main risk"
              value={usd(top.loss_if_incident_usd)}
              note={`if “${top.title}” happens. Even if certain, it would cost less than exiting.`}
            />
          )}
        </div>
      </div>

      <div className="mt-10 flex items-center justify-between gap-4 md:hidden">
        <button type="button" onClick={() => stepPocket(-1)} className="text-body font-semibold text-accent">
          ‹ Previous
        </button>
        <button type="button" onClick={() => stepPocket(1)} className="text-body font-semibold text-accent">
          Next ›
        </button>
      </div>
    </Slide>
  )
}
