import { AnimatePresence, motion } from 'framer-motion'
import { verdictColor } from '../lib/colors'

interface Props {
  verdict: string | null | undefined
  className?: string
}

/** STAY or EXIT, in its colour. A change of verdict is the one thing that moves on screen. */
export default function VerdictWord({ verdict, className = 'text-giant' }: Props) {
  const text = verdict ?? '—'
  return (
    <span className={`relative inline-grid font-semibold tabular ${className}`} aria-live="polite">
      <AnimatePresence mode="popLayout" initial={false}>
        <motion.span
          key={text}
          initial={{ opacity: 0, y: '0.18em' }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: '-0.18em' }}
          transition={{ duration: 0.32, ease: [0.22, 1, 0.36, 1] }}
          style={{ color: verdictColor(verdict) }}
          className="col-start-1 row-start-1"
        >
          {text}
        </motion.span>
      </AnimatePresence>
    </span>
  )
}
