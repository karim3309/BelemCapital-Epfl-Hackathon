import { SLIDES, useSelection, type SlideId } from '../state/selection'

/** Right-hand rail: where you are in the deck, and a jump to any question. */
export default function SlideRail({ active }: { active: string }) {
  const { goTo } = useSelection()
  return (
    <nav aria-label="Diapositives" className="fixed right-5 top-1/2 z-30 hidden -translate-y-1/2 md:block">
      <ol className="flex flex-col items-end gap-4">
        {SLIDES.map((slide, i) => {
          const isActive = slide.id === active
          return (
            <li key={slide.id}>
              <button
                type="button"
                onClick={() => goTo(slide.id as SlideId)}
                aria-current={isActive ? 'step' : undefined}
                className="group flex items-center gap-3"
              >
                <span
                  className={`rounded-md bg-surface px-2 py-1 text-caption font-normal opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100 ${
                    isActive ? 'text-chalk' : 'text-neutral1'
                  }`}
                >
                  {i + 1}. {slide.label}
                </span>
                <span
                  className={`block transition-all ${
                    isActive
                      ? 'mr-[2px] h-6 w-[2px] bg-accent'
                      : 'h-[6px] w-[6px] rounded-full bg-neutral1 group-hover:bg-chalk'
                  }`}
                />
              </button>
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
