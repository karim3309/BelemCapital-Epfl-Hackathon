import { motion } from 'framer-motion'
import type { ExitInfo, RiskMarket } from '../api/types'
import Slide from '../components/Slide'
import { Failure, Pending, Unrecorded } from '../components/States'
import { C } from '../lib/colors'
import { pct, pctAuto, pricingLabel, usd, usdShort } from '../lib/format'
import { usePocketView } from '../state/selection'

const MAX_SLIPPAGE = 0.25 // backend: beyond this the market cannot absorb the sale

function Line({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-6 py-3">
      <span className="text-body font-normal text-neutral1">{label}</span>
      <span className="text-right text-body font-semibold tabular" style={{ color: tone ?? C.chalk }}>
        {value}
      </span>
    </div>
  )
}

function VaultExit({ exit }: { exit: ExitInfo }) {
  return (
    <div className="flex flex-col">
      <Line label="Withdrawable now" value={pctAuto(exit.withdrawable_now_fraction)} />
      <Line label="Of which penalty-free" value={pctAuto(exit.penalty_free_fraction)} />
      <Line label="Forced withdrawal penalty" value={pctAuto(exit.force_deallocate_penalty)} />
      <Line label="Yield forgone over the horizon" value={pctAuto(exit.forgone_yield_rate_over_horizon)} />
      <Line label="Markets' weighted APY" value={pctAuto(exit.supply_apy_weighted ?? null)} />
      {exit.note && <p className="pt-3 text-caption font-normal text-neutral1">{exit.note}</p>}
    </div>
  )
}

function BorrowExit({ exit }: { exit: ExitInfo }) {
  const quotes = exit.quotes ?? []
  return (
    <div className="flex flex-col gap-6">
      <div>
        <p className="text-body font-semibold text-chalk">Measured slippage, by exit size</p>
        <ul className="mt-4 flex flex-col gap-4">
          {quotes.map((q) => {
            const over = q.slippage > MAX_SLIPPAGE
            return (
              <li key={q.fraction} className="grid grid-cols-[96px_minmax(0,1fr)_72px] items-center gap-4">
                <span className="text-caption font-normal tabular text-neutral1">exit {pct(q.fraction, 0)}</span>
                <span className="relative h-[8px] bg-surface2">
                  <motion.span
                    className="absolute inset-y-0 left-0"
                    style={{ backgroundColor: over ? C.risk : C.accent }}
                    initial={{ width: 0 }}
                    whileInView={{ width: `${Math.min(100, q.slippage * 100)}%` }}
                    viewport={{ once: true }}
                    transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
                  />
                </span>
                <span className="text-right text-body font-semibold tabular" style={{ color: over ? C.risk : C.chalk }}>
                  {pctAuto(q.slippage)}
                </span>
              </li>
            )
          })}
        </ul>
        <p className="mt-3 text-caption font-normal text-neutral1">
          {exit.measured ? 'Real KyberSwap quotes' : 'Fallback hypothesis, not measured'}
          {exit.reference?.fetched ? ` · fetched ${new Date(exit.reference.fetched).toLocaleString('en-US', { timeZone: 'UTC' })} UTC` : ''}
          . Beyond {pct(MAX_SLIPPAGE, 0)} of slippage, exiting through the market is deemed impossible.
        </p>
      </div>
      {exit.market_capacity_note && <p className="text-body font-normal text-warn">{exit.market_capacity_note}</p>}
      <div className="flex flex-col">
        {typeof exit.collateral_to_sell_full === 'number' && (
          <Line label="Collateral to sell to repay everything" value={usdShort(exit.collateral_to_sell_full)} />
        )}
        <Line label="Net carry forgone over the horizon" value={pctAuto(exit.forgone_net_carry_rate_over_horizon)} />
      </div>
    </div>
  )
}

function Markets({ markets }: { markets: RiskMarket[] }) {
  if (markets.length === 0) return null
  return (
    <div className="mt-10 overflow-x-auto">
      <table className="w-full min-w-[720px] text-left">
        <thead>
          <tr className="text-caption font-normal text-neutral1">
            <th className="py-2 pr-4 font-normal">Market</th>
            <th className="py-2 pr-4 font-normal">Collateral pricing</th>
            <th className="py-2 pr-4 text-right font-normal">LLTV</th>
            <th className="py-2 pr-4 text-right font-normal">Utilization</th>
            <th className="py-2 pr-4 text-right font-normal">Liquidity</th>
            <th className="py-2 pr-4 text-right font-normal">Our deposit</th>
            <th className="py-2 text-right font-normal">Borrowers</th>
          </tr>
        </thead>
        <tbody className="text-body tabular">
          {markets.map((m) => (
            <tr key={m.label}>
              <td className="py-2 pr-4 text-chalk">{m.label.replace(/^Morpho Blue\s+/, '').replace(/\s*\(LLTV[^)]*\)/, '')}</td>
              <td className="py-2 pr-4" style={{ color: m.collateral_pricing !== 'market' ? C.warn : C.chalk }}>
                {pricingLabel(m.collateral_pricing)}
              </td>
              <td className="py-2 pr-4 text-right text-chalk">{pct(m.lltv, 0)}</td>
              <td className="py-2 pr-4 text-right text-chalk">{pct(m.utilization, 1)}</td>
              <td className="py-2 pr-4 text-right text-chalk">{usdShort(m.liquidity)}</td>
              <td className="py-2 pr-4 text-right text-chalk">{m.our_supply > 0 ? usdShort(m.our_supply) : '—'}</td>
              <td className="py-2 text-right text-chalk">{m.borrowers}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Slide 5 — question 3: what does leaving cost? A certain, measured cost. */
export default function ExitSlide() {
  const v = usePocketView()
  const exit = v.risk?.exit
  const borrow = v.holding?.kind === 'morpho_market_borrow'

  return (
    <Slide id="exit" eyebrow="Question 3 of 4 · Exit" title="What does exiting cost?">
      {exit ? (
        <>
          <div className="mt-8 grid grid-cols-1 gap-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] lg:gap-16">
            <div className="flex flex-col gap-10">
              <div>
                <p className="text-caption font-normal text-neutral1">Certain cost to exit the exitable share</p>
                <p className="text-figure font-semibold tabular text-chalk">{usd(exit.cost_full_usd)}</p>
                <p className="text-caption font-normal text-neutral1 tabular">{pctAuto(exit.cost_full_pct)} of the pocket</p>
              </div>
              <div>
                <p className="text-caption font-normal text-neutral1">Exitable now</p>
                <p className="text-figure font-semibold tabular text-chalk">{pct(exit.f_max_now, 0)}</p>
                <div className="mt-3 h-[8px] bg-surface2">
                  <motion.div
                    className="h-full bg-accent"
                    initial={{ width: 0 }}
                    whileInView={{ width: `${exit.f_max_now * 100}%` }}
                    viewport={{ once: true }}
                    transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
                  />
                </div>
                <p className="mt-3 text-caption font-normal text-neutral1">
                  {borrow
                    ? "Share of the debt that can be repaid by selling collateral on the market."
                    : "Liquidity available in the markets where the vault placed the funds."}
                </p>
              </div>
            </div>
            {borrow ? <BorrowExit exit={exit} /> : <VaultExit exit={exit} />}
          </div>
          {v.risk && <Markets markets={v.risk.markets} />}
          {exit.gas && <p className="mono mt-6 text-neutral1">Gas: {exit.gas}</p>}
        </>
      ) : (
        <div className="mt-8 flex flex-col gap-8">
          {v.row && (
            <div className="flex flex-wrap gap-16">
              <div>
                <p className="text-caption font-normal text-neutral1">Exit cost</p>
                <p className="text-figure font-semibold tabular text-chalk">{usd(v.row.exit_cost_usd)}</p>
              </div>
              <div>
                <p className="text-caption font-normal text-neutral1">Exitable now</p>
                <p className="text-figure font-semibold tabular text-chalk">{pct(v.row.exit_fraction_now, 0)}</p>
              </div>
            </div>
          )}
          {v.holderUnrecorded && <Unrecorded>No recorded response for this holder.</Unrecorded>}
          {v.riskWaiting && <Pending title="Measuring the exit cost…" eta="10 to 30 s on the first call." />}
          {v.riskQuery.isError && <Failure error={v.riskQuery.error} onRetry={() => v.riskQuery.refetch()} />}
          {v.riskQuery.data === null && (
            <Unrecorded>The exit cost details of this pocket were not recorded.</Unrecorded>
          )}
        </div>
      )}
    </Slide>
  )
}
