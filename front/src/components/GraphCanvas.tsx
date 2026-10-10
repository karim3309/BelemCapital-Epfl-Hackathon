import { useEffect, useMemo, useRef, useState } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import type { Graph } from '../api/types'
import { C } from '../lib/colors'
import { buildView, pathTo, type ViewLink, type ViewNode } from '../lib/graph'

export interface Highlight {
  nodes: Set<string>
  edges: Set<string>
}

interface Props {
  graph: Graph
  /** Edges and nodes to light up (an incident's contagion path). Hovering a node shows its own path. */
  highlight?: Highlight | null
  /** The node a failure starts from: red ring. */
  targetId?: string | null
  selectedId?: string | null
  onSelect?: (node: ViewNode) => void
  showChain?: boolean
  /** Only label the nodes on the highlighted path (small canvases). */
  quietLabels?: boolean
  /** On narrow screens, grow to the height the layout needs and let the page scroll through it. */
  autoHeight?: boolean
  className?: string
}

const FONT = "-apple-system, BlinkMacSystemFont, 'SF Pro Text', system-ui, sans-serif"
const NARROW = 720

const LINK_BASE: Record<string, string> = {
  onchain: 'rgba(142,142,147,0.5)',
  api: 'rgba(142,142,147,0.5)',
  curated: 'rgba(255,159,10,0.75)',
}
const LINK_DASH: Record<string, number[] | null> = { onchain: null, api: [5, 4], curated: [1.5, 3.5] }

function fillFor(n: ViewNode): string | null {
  switch (n.type) {
    case 'position':
    case 'asset':
      return C.chalk
    case 'vault':
    case 'lending_market':
    case 'liquidity_venue':
      return C.accent
    case 'oracle':
      // An oracle that does not follow the market is the API's risk #1.
      return n.pricingMode && n.pricingMode !== 'market' ? C.warn : C.neutral
    default:
      return null // issuers, counterparties, chain: drawn hollow
  }
}

export default function GraphCanvas({
  graph,
  highlight,
  targetId,
  selectedId,
  onSelect,
  showChain = false,
  quietLabels = false,
  autoHeight = true,
  className = 'h-[60vh] min-h-[420px]',
}: Props) {
  // react-force-graph exposes its camera imperatively; only zoom/zoomToFit are used.
  const fgRef = useRef<any>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ width: 0, height: 0 })
  const [hoverId, setHoverId] = useState<string | null>(null)
  const vertical = size.width > 0 && size.width < NARROW

  useEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const ro = new ResizeObserver(([entry]) =>
      setSize({ width: Math.round(entry.contentRect.width), height: Math.round(entry.contentRect.height) }),
    )
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const view = useMemo(() => buildView(graph, { showChain, vertical }), [graph, showChain, vertical])
  const tallHeight = useMemo(() => {
    if (!vertical || !autoHeight || view.nodes.length === 0) return undefined
    const ys = view.nodes.map((n) => n.y)
    return Math.max(420, Math.round((Math.max(...ys) - Math.min(...ys)) * 0.8 + 96))
  }, [vertical, autoHeight, view])
  const data = useMemo(() => ({ nodes: view.nodes, links: view.links }), [view])
  const hoverPath = useMemo(() => (hoverId ? pathTo(graph, hoverId) : null), [graph, hoverId])
  const active: Highlight | null = highlight ?? hoverPath

  // Fit the nodes AND their labels: labels sit right of the node (wide) or under it (narrow)
  // at a constant screen size, so their room is reserved in pixels, not graph units.
  const fit = (ms = 0) => {
    const fg = fgRef.current
    if (!fg || !size.width || view.nodes.length === 0) return
    const xs = view.nodes.map((n) => n.x)
    const ys = view.nodes.map((n) => n.y)
    const minX = Math.min(...xs) - 16
    const maxX = Math.max(...xs) + 16
    const minY = Math.min(...ys) - 16
    const maxY = Math.max(...ys) + 16
    const pad = vertical ? 12 : 32
    const labelW = vertical ? 96 : 200
    const labelH = vertical ? 24 : 22
    const k = Math.min(
      2,
      (size.width - 2 * pad - labelW) / Math.max(1, maxX - minX),
      (size.height - 2 * pad - labelH) / Math.max(1, maxY - minY),
    )
    const cx = (minX + maxX) / 2 + (vertical ? 0 : labelW / 2 / k)
    const cy = (minY + maxY) / 2 + labelH / 2 / k
    fg.centerAt(cx, cy, ms)
    fg.zoom(k, ms)
  }

  useEffect(() => {
    if (!size.width || !size.height) return
    const id = requestAnimationFrame(() => fit())
    return () => cancelAnimationFrame(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, size.width, size.height])

  const zoomBy = (k: number) => {
    const fg = fgRef.current
    if (fg) fg.zoom(fg.zoom() * k, 250)
  }

  const touch = typeof window !== 'undefined' && window.matchMedia?.('(pointer: coarse)').matches

  return (
    <div
      ref={wrapRef}
      className={`relative w-full overflow-hidden ${className}`}
      style={tallHeight ? { height: tallHeight, minHeight: tallHeight } : undefined}
    >
      {size.width > 0 && (
        <ForceGraph2D
          ref={fgRef}
          width={size.width}
          height={size.height}
          graphData={data}
          backgroundColor={C.ink}
          warmupTicks={0}
          cooldownTicks={0}
          enableNodeDrag={false}
          // Wheel scrolls the deck; zoom has buttons. Touch drags scroll the page.
          enableZoomInteraction={false}
          enablePanInteraction={!touch}
          linkWidth={(l: ViewLink) => (active?.edges.has(l.key) ? 2.4 : 1)}
          linkColor={(l: ViewLink) =>
            active
              ? active.edges.has(l.key)
                ? C.risk
                : 'rgba(142,142,147,0.12)'
              : LINK_BASE[l.edge.source] ?? LINK_BASE.onchain
          }
          linkLineDash={(l: ViewLink) => LINK_DASH[l.edge.source] ?? null}
          linkDirectionalArrowLength={4}
          linkDirectionalArrowRelPos={1}
          nodeLabel={() => ''}
          onNodeHover={(n: ViewNode | null) => setHoverId(n ? n.id : null)}
          onNodeClick={(n: ViewNode) => onSelect?.(n)}
          nodeCanvasObject={(n: ViewNode, ctx: CanvasRenderingContext2D, scale: number) => {
            const x = n.x
            const y = n.y
            const r = n.radius
            const dim = active ? !active.nodes.has(n.id) : false
            ctx.globalAlpha = dim ? 0.2 : 1

            if (n.id === targetId) {
              ctx.beginPath()
              ctx.arc(x, y, r + 6 / scale, 0, 2 * Math.PI)
              ctx.strokeStyle = C.risk
              ctx.lineWidth = 2 / scale
              ctx.stroke()
            }
            if (n.id === selectedId) {
              ctx.beginPath()
              ctx.arc(x, y, r + (n.id === targetId ? 10 : 5) / scale, 0, 2 * Math.PI)
              ctx.strokeStyle = C.chalk
              ctx.lineWidth = 1.5 / scale
              ctx.stroke()
            }

            const fill = fillFor(n)
            ctx.beginPath()
            ctx.arc(x, y, r, 0, 2 * Math.PI)
            if (fill) {
              ctx.fillStyle = fill
              ctx.fill()
            } else {
              ctx.fillStyle = C.ink
              ctx.fill()
              ctx.strokeStyle = C.neutral
              ctx.lineWidth = 1.5 / scale
              ctx.stroke()
            }
            if (n.type === 'position') {
              ctx.beginPath()
              ctx.arc(x, y, r + 3 / scale, 0, 2 * Math.PI)
              ctx.strokeStyle = C.accent
              ctx.lineWidth = 2 / scale
              ctx.stroke()
            }

            if (quietLabels && dim) {
              ctx.globalAlpha = 1
              return
            }
            const fs = (vertical ? 12 : 13) / scale
            ctx.font = `600 ${fs}px ${FONT}`
            ctx.fillStyle = C.chalk
            if (vertical) {
              ctx.textAlign = 'center'
              ctx.textBaseline = 'top'
              ctx.fillText(n.title, x, y + r + 5 / scale)
            } else {
              ctx.textAlign = 'left'
              ctx.textBaseline = 'alphabetic'
              ctx.fillText(n.title, x + r + 8 / scale, y - 1 / scale)
              ctx.font = `400 ${12 / scale}px ${FONT}`
              ctx.fillStyle = n.pricingMode && n.pricingMode !== 'market' ? C.warn : C.neutral
              ctx.textBaseline = 'top'
              ctx.fillText(n.subtitle, x + r + 8 / scale, y + 3 / scale)
            }
            ctx.globalAlpha = 1
          }}
          nodePointerAreaPaint={(n: ViewNode, colour: string, ctx: CanvasRenderingContext2D) => {
            ctx.beginPath()
            ctx.arc(n.x, n.y, n.radius + 8, 0, 2 * Math.PI)
            ctx.fillStyle = colour
            ctx.fill()
          }}
        />
      )}

      <div className="absolute bottom-3 right-3 flex gap-1">
        {[
          { label: 'Zoom in', text: '+', act: () => zoomBy(1.35) },
          { label: 'Zoom out', text: '−', act: () => zoomBy(1 / 1.35) },
          { label: 'Show everything', text: 'Fit', act: () => fit(300) },
        ].map((b) => (
          <button
            key={b.label}
            type="button"
            aria-label={b.label}
            onClick={b.act}
            className="h-8 min-w-8 rounded-md bg-surface px-3 text-caption font-semibold text-chalk hover:bg-surface2"
          >
            {b.text}
          </button>
        ))}
      </div>
    </div>
  )
}
