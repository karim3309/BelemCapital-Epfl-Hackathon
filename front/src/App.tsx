import { useEffect } from 'react'
import Header from './components/Header'
import SlideRail from './components/SlideRail'
import { useActiveSlide } from './lib/useActiveSlide'
import BookSlide from './slides/BookSlide'
import ConcentrationSlide from './slides/ConcentrationSlide'
import ExitSlide from './slides/ExitSlide'
import GraphSlide from './slides/GraphSlide'
import IncidentSlide from './slides/IncidentSlide'
import LossSlide from './slides/LossSlide'
import VerdictSlide from './slides/VerdictSlide'
import { SLIDES, useSelection } from './state/selection'

const SLIDE_IDS = SLIDES.map((s) => s.id)

function isTyping(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null
  if (!el) return false
  const tag = el.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable
}

export default function App() {
  const { stepPocket } = useSelection()
  const active = useActiveSlide(SLIDE_IDS)

  // ← → change pocket from anywhere in the deck; ↑ ↓ (native scrolling) move between questions.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (isTyping(e.target) || e.metaKey || e.ctrlKey || e.altKey) return
      if (e.key === 'ArrowLeft') {
        e.preventDefault()
        stepPocket(-1)
      } else if (e.key === 'ArrowRight') {
        e.preventDefault()
        stepPocket(1)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [stepPocket])

  return (
    <>
      <Header />
      <SlideRail active={active} />
      <main className="w-full bg-ink">
        <BookSlide />
        <VerdictSlide />
        <GraphSlide />
        <LossSlide />
        <ExitSlide />
        <IncidentSlide />
        <ConcentrationSlide />
      </main>
    </>
  )
}
