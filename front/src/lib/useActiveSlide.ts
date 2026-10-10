import { useEffect, useState } from 'react'

/** Which slide fills most of the viewport right now. */
export function useActiveSlide(ids: readonly string[]): string {
  const [active, setActive] = useState(ids[0])
  useEffect(() => {
    const ratios = new Map<string, number>()
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) ratios.set(entry.target.id, entry.intersectionRatio)
        let best = ids[0]
        let bestRatio = -1
        for (const id of ids) {
          const r = ratios.get(id) ?? 0
          if (r > bestRatio) {
            best = id
            bestRatio = r
          }
        }
        setActive(best)
      },
      { threshold: [0, 0.2, 0.4, 0.6, 0.8, 1] },
    )
    for (const id of ids) {
      const el = document.getElementById(id)
      if (el) observer.observe(el)
    }
    return () => observer.disconnect()
  }, [ids])
  return active
}
