import { AnimatePresence, motion } from 'framer-motion'
import { useEffect, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import type { Graph, GraphEdge, Holding } from '../api/types'
import { C } from '../lib/colors'
import {
  EDGE_TYPE_LABEL,
  NODE_TYPE_LABEL,
  SOURCE_LABEL,
  ago,
  pct,
  pctAuto,
  pricingLabel,
  shortAddress,
  usd,
} from '../lib/format'
import { proofsFor, type ViewNode } from '../lib/graph'

interface Props {
  node: ViewNode | null
  graph: Graph | null
  holding: Holding | null
  onClose: () => void
}

function Row({ label, value, tone }: { label: string; value: ReactNode; tone?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-6 py-2">
      <span className="text-caption font-normal text-neutral1">{label}</span>
      <span className="text-right text-body font-semibold tabular" style={{ color: tone ?? C.chalk }}>
        {value}
      </span>
    </div>
  )
}

const num = (v: unknown, digits = 0) =>
  typeof v === 'number' ? new Intl.NumberFormat('fr-FR', { maximumFractionDigits: digits }).format(v) : '—'

function Facts({ node }: { node: ViewNode }) {
  const m = node.node?.meta ?? {}
  switch (node.type) {
    case 'vault':
      return (
        <>
          <Row label="Actif" value={m.asset_symbol ?? '—'} />
          <Row label="Total des actifs" value={num(m.total_assets_human)} />
          <Row label="Part du détenteur" value={pct(m.holder_share_of_vault, 1)} />
          <Row label="Retirable maintenant" value={num(m.exit_liquidity?.withdrawable_now_human)} />
          {Array.isArray(m.allocations) &&
            m.allocations.map((a: any) => (
              <Row
                key={a.market_id}
                label={`Marché ${shortAddress(a.market_id)}`}
                value={`${pct(a.share_of_vault, 1)} · util. ${pct(a.market_utilization, 0)}`}
              />
            ))}
        </>
      )
    case 'lending_market':
      return (
        <>
          <Row label="LLTV" value={pct(m.lltv, 0)} />
          <Row label="Utilisation" value={pct(m.utilization, 1)} />
          <Row label="Liquidité disponible" value={num(m.available_liquidity_human)} />
          <Row label="APY d'emprunt" value={pct(m.borrow_apy, 2)} />
          <Row label="Taux officiel (AdaptiveCurve)" value={m.irm_is_official_adaptive_curve ? 'oui' : 'non'} />
        </>
      )
    case 'oracle':
      return (
        <>
          <Row
            label="Mode de prix"
            value={pricingLabel(m.pricing_mode)}
            tone={m.pricing_mode && m.pricing_mode !== 'market' ? C.warn : C.chalk}
          />
          {m.description && <Row label="Paire" value={m.description} />}
          {typeof m.answer === 'number' && <Row label="Valeur lue" value={num(m.answer, 6)} />}
          {typeof m.price === 'number' && <Row label="Prix calculé" value={num(m.price, 6)} />}
          {typeof m.age_seconds === 'number' && <Row label="Dernière mise à jour" value={ago(m.age_seconds)} />}
          {m.pricing_detail && <p className="py-2 text-caption font-normal text-neutral1">{String(m.pricing_detail)}</p>}
          {m.formula && <p className="mono py-2 text-neutral1">{String(m.formula)}</p>}
        </>
      )
    case 'asset':
      return (
        <>
          <Row label="Symbole" value={m.symbol ?? node.label} />
          <Row label="Offre totale" value={num(m.total_supply_human)} />
          <Row
            label="Contrat modifiable"
            value={m.proxy?.upgradeable === true ? 'oui (proxy)' : m.proxy?.upgradeable === false ? 'non' : 'non prouvé'}
          />
        </>
      )
    case 'issuer':
    case 'offchain_counterparty':
      return (
        <>
          <Row label="Rôle" value={m.role === 'vault_curator' ? 'curateur du coffre' : 'émetteur'} />
          {m.note && <p className="py-2 text-caption font-normal text-neutral1">{String(m.note)}</p>}
          {(m.website || m.evidence_url) && (
            <a
              href={m.website ?? m.evidence_url}
              target="_blank"
              rel="noreferrer"
              className="block py-2 text-caption font-normal text-accent hover:opacity-80"
            >
              Source officielle
            </a>
          )}
        </>
      )
    default:
      return null
  }
}

function Proof({ edge, graph, outgoing }: { edge: GraphEdge; graph: Graph; outgoing: boolean }) {
  const other = outgoing ? edge.to : edge.from
  const otherLabel =
    other === graph.position.id ? 'Votre poche' : graph.nodes.find((n) => n.id === other)?.label ?? other
  const tone = edge.source === 'curated' ? C.warn : edge.source === 'api' ? C.neutral : C.safe
  return (
    <li className="flex flex-col gap-2 py-4">
      <div className="flex items-baseline justify-between gap-4">
        <span className="text-body font-normal text-chalk">
          <span className="text-neutral1">{EDGE_TYPE_LABEL[edge.type] ?? edge.type}</span> {otherLabel}
        </span>
        <span className="shrink-0 text-caption font-semibold" style={{ color: tone }}>
          {SOURCE_LABEL[edge.source] ?? edge.source}
          {edge.weight < 1 ? ` · ${pct(edge.weight, 1)}` : ''}
        </span>
      </div>
      <p className="mono text-neutral1">{edge.evidence}</p>
    </li>
  )
}

/** Everything the backend proved about one dependency, with the evidence behind each edge. */
export default function NodeSheet({ node, graph, holding, onClose }: Props) {
  useEffect(() => {
    if (!node) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [node, onClose])

  const proofs = node && graph ? proofsFor(graph, node.id) : null
  const address = node?.node?.address ?? (node?.type === 'position' ? holding?.address : null)

  // Portalled: a fixed panel inside an animated (transformed) slide would be trapped by it.
  return createPortal(
    <AnimatePresence>
      {node && graph && (
        <motion.aside
          key="node-sheet"
          initial={{ x: 460 }}
          animate={{ x: 0 }}
          exit={{ x: 460 }}
          transition={{ type: 'tween', duration: 0.28, ease: [0.32, 0.72, 0, 1] }}
          className="thin-scroll fixed bottom-0 right-0 top-0 z-50 w-[460px] max-w-full overflow-y-auto bg-surface px-8 pb-16 pt-[calc(env(safe-area-inset-top,0px)+40px)]"
          aria-label={`Détail : ${node.label}`}
        >
          <div className="flex items-start justify-between gap-6">
            <div className="min-w-0">
              <p className="text-caption font-normal text-neutral1">{NODE_TYPE_LABEL[node.type] ?? node.type}</p>
              <h3 className="mt-2 text-panel font-semibold text-chalk [overflow-wrap:anywhere]">{node.label}</h3>
            </div>
            <button
              type="button"
              onClick={onClose}
              aria-label="Fermer"
              className="shrink-0 text-sub font-normal text-neutral1 hover:text-chalk"
            >
              ×
            </button>
          </div>

          {address && (
            <div className="mt-4 flex flex-wrap items-center gap-4">
              <span className="mono select-all text-chalk">{address}</span>
              <a
                href={`https://etherscan.io/address/${address}`}
                target="_blank"
                rel="noreferrer"
                className="text-caption font-normal text-accent hover:opacity-80"
              >
                Etherscan
              </a>
            </div>
          )}

          <div className="mt-8">
            {node.type === 'position' && holding ? (
              <>
                <Row label="Valeur" value={usd(holding.value_usd)} />
                <Row label="Montant" value={`${num(holding.amount, 2)} ${holding.asset_symbol}`} />
                <Row label="Part du portefeuille" value={pct(holding.share_of_book, 1)} />
                {typeof holding.api_gap === 'number' && (
                  <Row label="Écart chaîne / API Morpho" value={pctAuto(holding.api_gap)} />
                )}
              </>
            ) : (
              <>
                <Row label="Part de la poche exposée" value={pctAuto(node.exposure)} />
                <Facts node={node} />
              </>
            )}
          </div>

          {node.type === 'position' && holding && holding.evidence.length > 0 && (
            <section className="mt-10">
              <h4 className="text-body font-semibold text-chalk">Montant prouvé on-chain</h4>
              <ul className="mt-2">
                {holding.evidence.map((line) => (
                  <li key={line} className="mono py-2 text-neutral1">
                    {line}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {proofs && proofs.dependsOn.length > 0 && (
            <section className="mt-10">
              <h4 className="text-body font-semibold text-chalk">Dépend de</h4>
              <ul>
                {proofs.dependsOn.map((e) => (
                  <Proof key={`${e.type}${e.to}`} edge={e} graph={graph} outgoing />
                ))}
              </ul>
            </section>
          )}
          {proofs && proofs.dependedOnBy.length > 0 && (
            <section className="mt-10">
              <h4 className="text-body font-semibold text-chalk">Touché si ce nœud casse</h4>
              <ul>
                {proofs.dependedOnBy.map((e) => (
                  <Proof key={`${e.type}${e.from}`} edge={e} graph={graph} outgoing={false} />
                ))}
              </ul>
            </section>
          )}

          {node.node && (
            <details className="mt-10">
              <summary className="cursor-pointer text-caption font-normal text-neutral1 hover:text-chalk">
                Données brutes du nœud
              </summary>
              <pre className="mono mt-3 max-h-[360px] overflow-auto whitespace-pre-wrap rounded-md bg-ink p-4 text-neutral1">
                {JSON.stringify(node.node.meta, null, 2)}
              </pre>
            </details>
          )}
        </motion.aside>
      )}
    </AnimatePresence>,
    document.body,
  )
}
