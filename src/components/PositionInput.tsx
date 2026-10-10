import { useEffect, useRef, useState } from 'react'
import { addressBook, positions, presets } from '../data/mock'

interface Props {
  positionKey: string
  onSelect: (key: string) => void
  onScan: () => void
}

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 14 14"
      fill="none"
      aria-hidden="true"
      className={open ? 'rotate-180 transition-transform' : 'transition-transform'}
    >
      <path d="M3 5.5 7 9.5l4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  )
}

/** Section A — one idea: name the position you are worried about. */
export default function PositionInput({ positionKey, onSelect, onScan }: Props) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const wrapRef = useRef<HTMLDivElement>(null)

  const position = positions[positionKey]

  useEffect(() => {
    if (!open) return
    const onDown = (event: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(event.target as Node)) setOpen(false)
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const choosePreset = (key: string) => {
    onSelect(key)
    setQuery('')
    setNotice(null)
    setOpen(false)
  }

  const runScan = () => {
    const raw = query.trim()
    if (!raw) {
      setNotice(null)
      onScan()
      return
    }
    const resolved =
      addressBook[raw.toLowerCase()] ??
      presets.find((p) => p.name.toLowerCase() === raw.toLowerCase())?.key
    if (resolved) {
      onSelect(resolved)
      setNotice(null)
    } else {
      setNotice(
        `${raw.slice(0, 22)}${raw.length > 22 ? '…' : ''} is not in the demo index — showing ${position.name}.`,
      )
    }
    onScan()
  }

  return (
    <section className="w-full px-8 py-48 md:px-16">
      <div className="mx-auto max-w-stage">
        <h1 className="text-headline font-semibold text-chalk md:text-display">
          Analyse a position
        </h1>

        <div ref={wrapRef} className="relative mt-18">
          <div className="flex flex-col gap-4 md:flex-row md:items-stretch">
            <div className="relative flex flex-1 items-center bg-surface px-8 rounded-xl">
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') runScan()
                }}
                spellCheck={false}
                autoComplete="off"
                aria-label="Contract address"
                placeholder="Paste a contract address"
                className="h-[88px] w-full min-w-0 bg-transparent text-field font-normal text-chalk outline-none placeholder:font-normal"
              />
              <button
                type="button"
                onClick={() => setOpen((v) => !v)}
                aria-expanded={open}
                aria-haspopup="listbox"
                className="ml-6 flex shrink-0 items-center gap-3 text-body font-normal text-neutral1 hover:text-chalk"
              >
                <span className="hidden sm:inline">{position.name}</span>
                <span className="sm:hidden">Presets</span>
                <Chevron open={open} />
              </button>
            </div>

            <button
              type="button"
              onClick={runScan}
              className="h-[88px] shrink-0 bg-accent px-12 text-field font-semibold text-chalk rounded-xl hover:opacity-90"
            >
              Run dependency scan
            </button>
          </div>

          {open && (
            <ul
              role="listbox"
              className="absolute left-0 right-0 top-[96px] z-30 overflow-hidden bg-surface py-4 rounded-xl md:right-auto md:w-[640px]"
            >
              {presets.map((preset) => (
                <li key={preset.key}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={preset.key === positionKey}
                    onClick={() => choosePreset(preset.key)}
                    className="flex w-full flex-col items-start gap-1 px-8 py-6 text-left hover:bg-surface2"
                  >
                    <span className="text-body font-semibold text-chalk">
                      {preset.name}
                      <span className="font-normal text-neutral1"> · {preset.chain}</span>
                    </span>
                    <span className="text-caption font-normal text-neutral1">
                      {preset.description}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <p className="mt-10 max-w-[760px] text-caption font-normal text-neutral1">
          {notice ?? `${position.name} · ${position.venue} · ${position.chain}. ${position.description}`}
        </p>
      </div>
    </section>
  )
}
