import { useState } from 'react'
import { useGraph, usePockets } from '../api/hooks'
import { recorded } from '../api/recorded'
import { useSource } from '../api/source'
import GraphCanvas from '../components/GraphCanvas'
import NodeSheet from '../components/NodeSheet'
import Slide from '../components/Slide'
import { Failure, Pending, Unrecorded } from '../components/States'
import { C } from '../lib/colors'
import { pricingLabel } from '../lib/format'
import { nonMarketOracles, sourceCounts, type ViewNode } from '../lib/graph'
import { useSelection } from '../state/selection'

function Swatch({ fill, hollow, label }: { fill?: string; hollow?: boolean; label: string }) {
  return (
    <span className="flex items-center gap-2 text-caption font-normal text-neutral1">
      <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true" className="shrink-0">
        {hollow ? (
          <circle cx="5" cy="5" r="4.25" fill={C.ink} stroke={C.neutral} strokeWidth="1.5" />
        ) : (
          <circle cx="5" cy="5" r="5" fill={fill} />
        )}
      </svg>
      {label}
    </span>
  )
}

function Stroke({ dash, color, label }: { dash?: string; color: string; label: string }) {
  return (
    <span className="flex items-center gap-2 text-caption font-normal text-neutral1">
      <svg width="28" height="6" aria-hidden="true">
        <line x1="0" y1="3" x2="28" y2="3" stroke={color} strokeWidth="1.5" strokeDasharray={dash} />
      </svg>
      {label}
    </span>
  )
}

/** Slide 3 — question 1: am I exposed, and through which path? Every edge carries its proof. */
export default function GraphSlide() {
  const { holder, pocketId, setPocketId } = useSelection()
  const { source } = useSource()
  const pockets = usePockets(holder)
  const graphQuery = useGraph(holder, pocketId)
  const [selected, setSelected] = useState<ViewNode | null>(null)
  const [showChain, setShowChain] = useState(false)
  const graph = graphQuery.data?.graph ?? null
  const holding = pockets.data?.holdings.find((h) => h.id === pocketId) ?? null
  const counts = graph ? sourceCounts(graph) : {}
  const risky = graph ? nonMarketOracles(graph) : []
  const chainEdges = graph ? graph.edges.filter((e) => e.type === 'settled_on').length : 0
  const recordedGraphPocket = recorded.graphs[0]?.pocket

  return (
    <Slide
      id="chemin"
      eyebrow="Question 1 sur 4 · Découverte"
      title="Par quel chemin suis-je exposée ?"
      aside={
        graph ? (
          <div className="flex flex-col gap-1 text-left md:text-right">
            <p className="text-body font-semibold text-chalk tabular">
              {graph.nodes.length} dépendances · {graph.edges.length} arêtes
            </p>
            <p className="text-caption font-normal text-neutral1 tabular">
              {counts.onchain ?? 0} prouvées on-chain · {counts.api ?? 0} par API · {counts.curated ?? 0} curées
            </p>
          </div>
        ) : null
      }
    >
      {risky.length > 0 && (
        <p className="mt-6 max-w-[920px] text-body font-normal text-chalk">
          <span className="font-semibold text-warn">Risque n°1 : </span>
          {risky.length === 1 ? "un oracle ne suit pas le marché" : `${risky.length} oracles ne suivent pas le marché`}
          {' — '}
          {risky.map((o) => `${o.label} (${pricingLabel(o.meta.pricing_mode)})`).join(', ')}. Personne n'est liquidé à
          temps si le prix réel décroche.
        </p>
      )}

      <div className="mt-6 min-h-0 flex-1">
        {graph && (
          <GraphCanvas
            graph={graph}
            showChain={showChain}
            selectedId={selected?.id ?? null}
            onSelect={setSelected}
            className="h-[62vh] min-h-[420px] md:h-[54vh]"
          />
        )}
        {graphQuery.isPending && pocketId && (
          <Pending
            title="Construction du graphe prouvé…"
            eta={source.mode === 'live' ? "Arrive juste après l'analyse de risque de la poche." : undefined}
          />
        )}
        {graphQuery.isError && <Failure error={graphQuery.error} onRetry={() => graphQuery.refetch()} />}
        {pockets.data === null && <Unrecorded>Aucune réponse enregistrée pour ce détenteur.</Unrecorded>}
        {graphQuery.data === null && (
          <Unrecorded
            action={
              recordedGraphPocket && (
                <button
                  type="button"
                  onClick={() => setPocketId(recordedGraphPocket.id)}
                  className="self-start text-body font-semibold text-accent hover:opacity-80"
                >
                  Voir le graphe enregistré : {recordedGraphPocket.label}
                </button>
              )
            }
          >
            Le graphe de cette poche n'a pas été enregistré.
          </Unrecorded>
        )}
      </div>

      {graph && (
        <div className="mt-6 flex flex-col gap-4">
          <div className="flex flex-wrap gap-x-6 gap-y-3">
            <Swatch fill={C.chalk} label="Votre poche, actifs" />
            <Swatch fill={C.accent} label="Coffre, marchés" />
            <Swatch fill={C.neutral} label="Oracle au marché" />
            <Swatch fill={C.warn} label="Oracle hors marché" />
            <Swatch hollow label="Émetteur, curateur" />
            <Stroke color={C.neutral} label="on-chain" />
            <Stroke color={C.neutral} dash="5 4" label="API" />
            <Stroke color={C.warn} dash="1.5 3.5" label="curé" />
          </div>
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
            <p className="text-caption font-normal text-neutral1">
              Survolez un nœud : le chemin par lequel sa panne vous atteint s'allume. Cliquez : ses preuves.
            </p>
            {chainEdges > 0 && (
              <button
                type="button"
                onClick={() => setShowChain((v) => !v)}
                className="text-caption font-semibold text-accent hover:opacity-80"
              >
                {showChain ? 'Masquer' : 'Afficher'} les {chainEdges} arêtes « réglé sur Ethereum »
              </button>
            )}
          </div>
        </div>
      )}

      <NodeSheet node={selected} graph={graph} holding={holding} onClose={() => setSelected(null)} />
    </Slide>
  )
}
