import { motion } from 'framer-motion'
import type { ReactNode } from 'react'

interface Props {
  id: string
  eyebrow?: string
  title?: ReactNode
  aside?: ReactNode
  children: ReactNode
}

/** One screen, one question. Content rises in once, the first time the slide is reached. */
export default function Slide({ id, eyebrow, title, aside, children }: Props) {
  return (
    <section id={id} className="slide relative flex w-full flex-col px-6 pb-16 pt-28 md:px-16 md:pb-24 md:pt-32">
      <motion.div
        initial={{ opacity: 0.3, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, amount: 0.15 }}
        transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
        className="mx-auto flex w-full max-w-stage flex-1 flex-col"
      >
        {(eyebrow || title || aside) && (
          <header className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
            <div className="flex min-w-0 flex-col gap-3">
              {eyebrow && <p className="text-caption font-normal text-neutral1">{eyebrow}</p>}
              {title && (
                <h2 className="text-title font-semibold text-chalk [text-wrap:balance] md:text-headline">{title}</h2>
              )}
            </div>
            {aside}
          </header>
        )}
        {children}
      </motion.div>
    </section>
  )
}
