import { useValidation } from '../api/hooks'
import type { Replay } from '../api/types'
import Slide from '../components/Slide'
import { Failure, Pending } from '../components/States'
import { C } from '../lib/colors'
import { blockNumber, pct, usd } from '../lib/format'

/** On-chain price path (Chainlink rounds) as a step line, with the lowest point marked. Drawing only, no risk maths. */
function PricePath({ path, low }: { path: { t: number; price: number }[]; low: number }) {
  if (path.length < 2) return null
  const W = 320
  const H = 72
  const t0 = path[0].t
  const t1 = path[path.length - 1].t
  const lo = Math.min(low, ...path.map((p) => p.price)) - 0.002
  const hi = Math.max(1.002, ...path.map((p) => p.price))
  const x = (t: number) => ((t - t0) / Math.max(t1 - t0, 1)) * W
  const y = (p: number) => H - ((p - lo) / (hi - lo)) * H
  let d = `M ${x(path[0].t)} ${y(path[0].price)}`
  for (let i = 1; i < path.length; i++) d += ` H ${x(path[i].t)} V ${y(path[i].price)}`
  const min = path.reduce((a, b) => (b.price < a.price ? b : a))
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-[72px] w-full max-w-[320px]" role="img" aria-label="On-chain USDe price path">
      <line x1={0} x2={W} y1={y(1)} y2={y(1)} stroke={C.surface2} strokeDasharray="3 4" />
      <path d={d} fill="none" stroke={C.accent} strokeWidth={2} />
      <circle cx={x(min.t)} cy={y(min.price)} r={3.5} fill={C.warn} />
    </svg>
  )
}

function ReplayCard({ r }: { r: Replay }) {
  if (!r.available || !r.onchain || !r.designs) {
    return (
      <article className="rounded-xl bg-surface p-6">
        <h3 className="text-body font-semibold text-chalk">{r.title}</h3>
        <p className="mt-2 text-caption font-normal text-neutral1">Not replayable at the frozen block.</p>
      </article>
    )
  }
  const m = r.meta_oracle
  return (
    <article className="flex flex-col gap-6 rounded-xl bg-surface p-6 md:p-8">
      <header className="flex flex-col gap-2">
        <h3 className="text-body font-semibold text-chalk md:text-title">{r.title}</h3>
        {r.story && <p className="max-w-[880px] text-caption font-normal text-neutral1">{r.story}</p>}
      </header>

      <div className="grid gap-6 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="flex flex-col gap-2">
          <p className="text-caption font-normal text-neutral1">On-chain · every Chainlink USDe/USD round</p>
          <p className="text-title font-semibold tabular text-chalk">
            low ${r.onchain.min_price.toFixed(4)}
          </p>
          <PricePath path={r.onchain.path} low={r.onchain.min_price} />
          <p className="break-all text-caption font-normal text-neutral1">{r.onchain.evidence}</p>
        </div>
        {r.offchain ? (
          <div className="flex flex-col gap-2">
            <p className="text-caption font-normal text-neutral1">Off-chain · exchange order book (curated)</p>
            <p className="text-body font-normal text-chalk">{r.offchain.says}</p>
            <a
              href={r.offchain.evidence_url}
              target="_blank"
              rel="noreferrer"
              className="break-all text-caption font-normal text-accent hover:opacity-80"
            >
              {r.offchain.evidence_url}
            </a>
            <p className="text-caption font-normal text-neutral1">read on {r.offchain.as_of}</p>
          </div>
        ) : (
          m && (
            <div className="flex flex-col gap-2">
              <p className="text-caption font-normal text-neutral1">Meta-oracle switch rule (read on-chain)</p>
              <p className="text-body font-normal text-chalk">
                Largest gap {pct(m.max_deviation, 2)} vs threshold {pct(m.threshold, 2)}, above it for{' '}
                {Math.round(m.longest_above_threshold_minutes)} min out of the {Math.round(m.needed_minutes)} min needed
                to switch.
              </p>
            </div>
          )
        )}
      </div>

      <ul className="flex flex-col">
        {r.designs.map((d) => (
          <li
            key={d.design}
            className="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-x-6 gap-y-1 border-t border-surface2 py-3 md:grid-cols-[minmax(0,1.3fr)_120px_140px_minmax(0,1.6fr)]"
          >
            <span className="text-body font-normal text-chalk">{d.design}</span>
            <span className="text-right text-body font-semibold md:text-left" style={{ color: d.liquidated ? C.risk : C.safe }}>
              {d.liquidated ? 'LIQUIDATED' : 'HOLDS'}
            </span>
            <span className="text-caption font-normal tabular text-neutral1 md:text-body">
              lowest HF {d.min_hf.toFixed(3)}
              {d.liquidated && d.borrower_loss_usd !== null ? ` · −${usd(d.borrower_loss_usd)}` : ''}
            </span>
            <span className="col-span-2 text-caption font-normal text-neutral1 md:col-span-1">{d.why}</span>
          </li>
        ))}
      </ul>

      {r.takeaway && <p className="max-w-[880px] text-body font-semibold text-chalk">{r.takeaway}</p>}
    </article>
  )
}

/** Slide 7: counterfactual — TODAY's position put through real past price paths (not a back-test).
 * Everything shown is computed by Python. */
export default function ValidationSlide() {
  const v = useValidation()
  const data = v.data

  return (
    <Slide
      id="validation"
      eyebrow="Counterfactual · real price paths"
      title="Would today's position survive past crises?"
      aside={
        data ? (
          <p className="text-body font-normal text-neutral1 md:max-w-[380px] md:text-right">
            {data.position.label}: health factor {data.position.health_factor.toFixed(3)}, liquidated if the oracle
            drops {pct(data.position.oracle_drop_to_liquidation, 2)}. Block {blockNumber(data.snapshot.block)}.
          </p>
        ) : null
      }
    >
      <div className="mt-10 flex flex-col gap-8">
        {v.isPending && <Pending title="Loading the replays…" />}
        {v.isError && <Failure error={v.error} onRetry={() => v.refetch()} />}
        {data?.replays.map((r) => <ReplayCard key={r.id} r={r} />)}
      </div>
      {data && (
        <p className="mt-8 max-w-[880px] text-caption font-normal text-neutral1">
          {data.method} Counterfactual replay: today's position through past price paths. Next step: the xUSD / deUSD
          cascade of November 2025, replayed on the positions that existed then (needs an archive RPC).
        </p>
      )}
    </Slide>
  )
}
