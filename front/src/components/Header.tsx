import { verdictColor } from '../lib/colors'
import { kindLabel, verdictText } from '../lib/format'
import { usePocketView, useSelection } from '../state/selection'
import SourcePill from './SourcePill'

function Arrow({ dir }: { dir: 'left' | 'right' }) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path
        d={dir === 'left' ? 'M10 3.5 5.5 8l4.5 4.5' : 'M6 3.5 10.5 8 6 12.5'}
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

/** Always on screen: which pocket, and whether to stay in it. */
export default function Header() {
  const { stepPocket, goTo } = useSelection()
  const view = usePocketView()
  const verdict = view.decision?.verdict ?? null

  return (
    <header className="fixed inset-x-0 top-0 z-40 bg-ink pt-[env(safe-area-inset-top,0px)]">
      <div className="mx-auto flex h-16 max-w-[1600px] items-center justify-between gap-4 px-4 md:px-8">
        <button
          type="button"
          onClick={() => goTo('portfolio')}
          className="hidden shrink-0 text-body font-semibold text-chalk hover:opacity-80 lg:block"
        >
          StackTrace
        </button>

        <div className="flex min-w-0 flex-1 items-center justify-center gap-1 md:gap-2">
          <button
            type="button"
            onClick={() => stepPocket(-1)}
            aria-label="Previous pocket"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-neutral1 hover:bg-surface hover:text-chalk"
          >
            <Arrow dir="left" />
          </button>
          <button
            type="button"
            onClick={() => goTo('verdict')}
            className="flex min-w-0 items-center gap-2 rounded-md px-2 py-1 hover:bg-surface md:gap-3"
          >
            <span className="hidden text-caption font-normal text-neutral1 tabular sm:inline">
              {view.count ? `${view.position}/${view.count}` : ''}
            </span>
            <span className="min-w-0 truncate text-caption font-semibold text-chalk md:max-w-[340px] md:text-body">
              {view.holding?.label ?? (view.holderUnrecorded ? 'Not recorded yet' : 'Loading pockets…')}
            </span>
            {view.holding && (
              <span className="hidden text-caption font-normal text-neutral1 md:inline">
                {kindLabel(view.holding.kind)}
              </span>
            )}
            <span
              className="flex shrink-0 items-center gap-2 text-caption font-semibold tabular"
              style={{ color: verdictColor(verdict) }}
            >
              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: verdictColor(verdict) }} />
              {view.decision ? verdictText(view.decision.verdict, view.decision.exit_fraction) : '…'}
            </span>
          </button>
          <button
            type="button"
            onClick={() => stepPocket(1)}
            aria-label="Next pocket"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-neutral1 hover:bg-surface hover:text-chalk"
          >
            <Arrow dir="right" />
          </button>
        </div>

        <SourcePill />
      </div>
    </header>
  )
}
