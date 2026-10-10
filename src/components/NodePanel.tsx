import { useEffect } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { LAYER_META } from '../data/mock'
import { pct, usd, type NodeRisk } from '../lib/risk'

interface Props {
  node: NodeRisk | null
  exposureUsd: number
  onClose: () => void
}

function Stat({ label, value, colour }: { label: string; value: string; colour?: string }) {
  return (
    <div className="mt-12">
      <p className="text-caption font-normal text-neutral1">{label}</p>
      <p className="mt-2 text-sub font-semibold tabular" style={{ color: colour ?? '#F5F5F7' }}>
        {value}
      </p>
    </div>
  )
}

/** Node detail — slides in from the right when a dependency is clicked. */
export default function NodePanel({ node, exposureUsd, onClose }: Props) {
  useEffect(() => {
    if (!node) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [node, onClose])

  return (
    <AnimatePresence>
      {node && (
        <motion.aside
          key="node-panel"
          initial={{ x: 420 }}
          animate={{ x: 0 }}
          exit={{ x: 420 }}
          transition={{ type: 'tween', duration: 0.28, ease: [0.32, 0.72, 0, 1] }}
          className="fixed right-0 top-0 z-40 h-full w-[420px] max-w-full overflow-y-auto bg-surface px-12 py-18"
          aria-label={`${node.label} detail`}
        >
          <div className="flex items-start justify-between gap-8">
            <div>
              <h3 className="text-sub font-semibold text-chalk">{node.label}</h3>
              <p className="mt-3 flex items-center gap-3 text-caption font-normal text-neutral1">
                <span
                  className="h-[10px] w-[10px] shrink-0 rounded-full"
                  style={{ backgroundColor: LAYER_META[node.layer].color }}
                />
                Layer {node.layer} · {LAYER_META[node.layer].label}
                {node.incident ? ' · live incident' : ''}
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="shrink-0 text-sub font-normal text-neutral1 hover:text-chalk"
            >
              ×
            </button>
          </div>

          <Stat
            label="Capital at risk in this dependency"
            value={node.tvl === null ? 'No TVL at risk' : usd(node.tvl)}
          />
          <Stat
            label="Incident probability · 30 days"
            value={pct(node.effective_prob * 100)}
            colour={node.incident ? '#FF3B30' : undefined}
          />
          <Stat
            label="Loss if the incident happens"
            value={pct(node.loss_given_incident * 100)}
          />
          <Stat
            label="Expected loss contribution"
            value={`${pct(node.loss_contribution_pct, 2)} · ${usd(
              (node.loss_contribution_pct / 100) * exposureUsd,
            )}`}
          />

          <div className="mt-18">
            <p className="text-caption font-normal text-neutral1">Role</p>
            <p className="mt-3 text-body font-normal text-chalk">{node.role}</p>
          </div>

          <div className="mt-12 pb-18">
            <p className="text-caption font-normal text-neutral1">How a failure reaches you</p>
            <p className="mt-3 text-body font-normal text-chalk">{node.transmission}</p>
          </div>
        </motion.aside>
      )}
    </AnimatePresence>
  )
}
