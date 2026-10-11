import { motion } from 'framer-motion'
import { useState } from 'react'
import { useBook } from '../api/hooks'
import { useSource } from '../api/source'
import Slide from '../components/Slide'
import { Failure, Pending, Unrecorded } from '../components/States'
import { C } from '../lib/colors'
import { NODE_TYPE_LABEL, usdShort } from '../lib/format'
import { useSelection } from '../state/selection'

const TYPE_TONE: Record<string, string> = {
  oracle: C.warn,
  issuer: C.neutral,
  lending_market: C.accent,
  vault: C.accent,
  asset: C.chalk,
}

/** Slide 8: what the pockets share. A dependency in many pockets is one failure hitting many lines. */
export default function ConcentrationSlide() {
  const { holder, pocketId } = useSelection()
  const { source } = useSource()
  const book = useBook(holder, pocketId)
  const [all, setAll] = useState(false)
  const data = book.data
  const shared = data?.shared_dependencies ?? []
  const shown = all ? shared : shared.slice(0, 10)
  const total = data?.total_value_usd ?? 0
  const count = data?.pockets.length ?? 0

  return (
    <Slide
      id="concentration"
      eyebrow="Portfolio · hidden concentration"
      title="What your pockets share."
      aside={
        data ? (
          <p className="text-body font-normal text-neutral1 md:max-w-[360px] md:text-right">
            {shared.length} dependencies show up in at least two pockets: a single failure can hit several
            lines at once.
          </p>
        ) : null
      }
    >
      <div className="mt-10 min-h-0 flex-1">
        {book.isPending && (
          <Pending
            title="Analysing the whole portfolio…"
            eta={source.mode === 'live' ? 'About 1 min 30 on the first call, then instant.' : undefined}
          />
        )}
        {book.isError && <Failure error={book.error} onRetry={() => book.refetch()} />}
        {book.data === null && <Unrecorded>No portfolio analysis recorded for this holder.</Unrecorded>}

        {data && (
          <ul className="thin-scroll max-h-[44vh] overflow-y-auto">
            {shown.map((d, i) => (
              <li
                key={`${d.dependency}-${i}`}
                className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-6 gap-y-2 py-3 md:grid-cols-[minmax(0,1.1fr)_140px_minmax(0,1fr)_88px]"
              >
                <span className="min-w-0">
                  <span className="block truncate text-body font-normal text-chalk">{d.dependency}</span>
                  <span className="block text-caption font-normal" style={{ color: TYPE_TONE[d.type] ?? C.neutral }}>
                    {NODE_TYPE_LABEL[d.type] ?? d.type}
                  </span>
                </span>
                <span className="text-right text-body font-semibold tabular text-chalk md:text-left">
                  {d.pockets} / {count} pockets
                </span>
                <span className="col-span-2 h-[6px] bg-surface2 md:col-span-1">
                  <motion.span
                    className="block h-full"
                    style={{ backgroundColor: TYPE_TONE[d.type] ?? C.neutral }}
                    initial={{ width: 0 }}
                    whileInView={{ width: `${total ? (d.exposed_value_usd / total) * 100 : 0}%` }}
                    viewport={{ once: true }}
                    transition={{ duration: 0.6, delay: Math.min(i, 10) * 0.03, ease: [0.22, 1, 0.36, 1] }}
                  />
                </span>
                <span className="hidden text-right text-body font-semibold tabular text-chalk md:block">
                  {usdShort(d.exposed_value_usd)}
                </span>
              </li>
            ))}
          </ul>
        )}
        {data && shared.length > 10 && (
          <button
            type="button"
            onClick={() => setAll((a) => !a)}
            className="mt-4 text-caption font-semibold text-accent hover:opacity-80"
          >
            {all ? 'Show the first 10' : `Show the ${shared.length} shared dependencies`}
          </button>
        )}
      </div>

      {data && (
        <p className="mt-8 max-w-[880px] text-body font-semibold text-chalk">
          At 3 a.m., a single question per pocket: do you believe the risk is above p*? The rest is measured.
        </p>
      )}
      {data && (
        <p className="mt-2 text-caption font-normal text-neutral1">
          Exposed value: sum of the pockets that contain the dependency (full bar = {usdShort(total)}). Cross-pocket
          contagion is not simulated, only listed.
        </p>
      )}
    </Slide>
  )
}
