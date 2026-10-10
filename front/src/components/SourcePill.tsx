import { useEffect, useRef, useState } from 'react'
import { usePockets } from '../api/hooks'
import { recordedBlock, recordedTimestamp } from '../api/recorded'
import { useSource } from '../api/source'
import { ago, blockNumber, blockTime } from '../lib/format'
import { useSelection } from '../state/selection'

/** Where the numbers come from, always visible: recorded block or live block and its age. */
export default function SourcePill() {
  const { source, probe, setMode, setApiUrl, recheck } = useSource()
  const { holder } = useSelection()
  const pockets = usePockets(holder)
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState(source.apiUrl)
  const ref = useRef<HTMLDivElement>(null)
  const [now, setNow] = useState(() => Date.now() / 1000)

  useEffect(() => setDraft(source.apiUrl), [source.apiUrl])

  useEffect(() => {
    if (source.mode !== 'live') return
    const t = setInterval(() => setNow(Date.now() / 1000), 15_000)
    return () => clearInterval(t)
  }, [source.mode])

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const live = source.mode === 'live'
  const liveBlock = pockets.data?.block
  const liveTs = pockets.data?.block_timestamp
  const dot = live ? (pockets.isError ? 'bg-risk' : liveBlock ? 'bg-safe' : 'bg-warn') : 'bg-neutral1'
  const label = live
    ? liveBlock && liveTs
      ? `Live · block ${blockNumber(liveBlock)} · ${ago(now - liveTs)}`
      : pockets.isError
        ? 'Live · API error'
        : 'Live · connecting…'
    : `Recorded · block ${blockNumber(recordedBlock(holder))}`

  return (
    <div ref={ref} className="relative flex items-center gap-4">
      {!live && probe.status === 'ok' && (
        <button
          type="button"
          onClick={() => setMode('live')}
          className="hidden text-caption font-semibold text-accent hover:opacity-80 lg:block"
        >
          API detected · go live
        </button>
      )}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex items-center gap-2 rounded-md bg-surface px-3 py-2 text-caption font-normal text-chalk hover:bg-surface2"
      >
        <span className={`h-2 w-2 shrink-0 rounded-full ${dot}`} />
        <span className="tabular sm:hidden">{live ? 'Live' : 'Recorded'}</span>
        <span className="hidden tabular sm:inline">{label}</span>
      </button>

      {open && (
        <div className="absolute right-0 top-12 z-50 w-[min(92vw,400px)] rounded-xl bg-surface p-6">
          <p className="text-caption font-normal text-neutral1">Data source</p>
          <div className="mt-3 flex flex-col gap-2">
            {(['live', 'recorded'] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setMode(m)}
                aria-pressed={source.mode === m}
                className={`flex flex-col items-start rounded-md px-4 py-3 text-left ${
                  source.mode === m ? 'bg-surface2' : 'hover:bg-surface2'
                }`}
              >
                <span className="text-body font-semibold text-chalk">
                  {m === 'live' ? 'Live (StackTrace API)' : 'Recorded responses'}
                </span>
                <span className="text-caption font-normal text-neutral1">
                  {m === 'live'
                    ? 'Ethereum mainnet, block refreshed every 2 minutes.'
                    : `Mainnet at block ${blockNumber(recordedBlock(holder))}, ${blockTime(recordedTimestamp(holder))}. No network needed.`}
                </span>
              </button>
            ))}
          </div>

          <form
            className="mt-6 flex flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault()
              setApiUrl(draft)
              recheck()
            }}
          >
            <label htmlFor="api-url" className="text-caption font-normal text-neutral1">
              API address
            </label>
            <div className="flex gap-2">
              <input
                id="api-url"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                spellCheck={false}
                className="min-w-0 flex-1 rounded-md bg-ink px-3 py-2 text-caption text-chalk outline-none"
              />
              <button type="submit" className="rounded-md bg-accent px-4 py-2 text-caption font-semibold text-chalk">
                Tester
              </button>
            </div>
            <p className="text-caption font-normal text-neutral1" role="status">
              {probe.status === 'checking' && 'Testing…'}
              {probe.status === 'ok' &&
                `Responding · block ${blockNumber(probe.health.block)} · ${probe.health.status === 'ok' ? 'all good' : 'degraded'} · Morpho ${probe.health.apis.morpho ?? '—'}`}
              {probe.status === 'down' && probe.error}
              {probe.status === 'off' && 'Not tested yet.'}
            </p>
          </form>

          <p className="mt-6 text-caption font-normal text-neutral1">Start the API at the root of the repository:</p>
          <p className="mono mt-2 select-all rounded-md bg-ink px-3 py-2 text-chalk">
            PYTHONPATH=src python -m stacktrace.api
          </p>
        </div>
      )}
    </div>
  )
}
