import { useEffect, useMemo, useRef, useState } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import { LAYER_META, type LayerId, type Position } from '../data/mock'
import { usd, type NodeRisk } from '../lib/risk'

interface Props {
  position: Position
  nodes: NodeRisk[]
  selectedId: string | null
  onSelect: (id: string) => void
}

interface GraphNode {
  id: string
  label: string
  layer: LayerId
  tvl: number | null
  incident: boolean
  radius: number
  sublabel: string
  x: number
  y: number
  fx: number
  fy: number
}

const CANVAS_FONT = "-apple-system, BlinkMacSystemFont, 'SF Pro Text', system-ui, sans-serif"

/**
 * Depth runs along the long axis of the canvas: left to right on a wide screen,
 * top to bottom on a narrow one. Settlement sits at the start, your position at
 * the end. The cross-axis stagger keeps long edges clear of intervening nodes.
 */
const DEPTH = (layer: LayerId) => (layer - 3) * 280
const STAGGER: Record<LayerId, number> = { 1: 0, 2: -150, 3: 150, 4: 0, 5: 0 }
const NARROW_BREAKPOINT = 720

function radiusFor(tvl: number | null, minLog: number, maxLog: number): number {
  if (tvl === null) return 7
  if (maxLog === minLog) return 18
  return 9 + 18 * ((Math.log10(tvl) - minLog) / (maxLog - minLog))
}

/** Section B — one idea: what this position actually depends on. */
export default function DependencyGraph({ position, nodes, selectedId, onSelect }: Props) {
  // react-force-graph exposes its camera imperatively; the typings vary by minor
  // version, so the handle is held loosely and only three methods are used.
  const fgRef = useRef<any>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  const ringRefs = useRef<Record<string, HTMLDivElement | null>>({})
  const [size, setSize] = useState({ width: 0, height: 0 })

  const narrow = size.width > 0 && size.width < NARROW_BREAKPOINT

  const graphData = useMemo(() => {
    const tvls = position.layers.map((n) => n.tvl).filter((t): t is number => t !== null)
    const logs = tvls.map((t) => Math.log10(t))
    const minLog = Math.min(...logs)
    const maxLog = Math.max(...logs)

    const byLayer = new Map<LayerId, number>()
    const graphNodes: GraphNode[] = position.layers.map((node) => {
      const seen = byLayer.get(node.layer) ?? 0
      byLayer.set(node.layer, seen + 1)
      const peers = position.layers.filter((n) => n.layer === node.layer).length
      const depth = DEPTH(node.layer)
      const stagger =
        (narrow ? STAGGER[node.layer] * 0.75 : STAGGER[node.layer]) +
        (seen - (peers - 1) / 2) * 160
      const x = narrow ? stagger : depth
      const y = narrow ? depth * 0.62 : stagger
      return {
        id: node.id,
        label: node.label,
        layer: node.layer,
        tvl: node.tvl,
        incident: node.incident,
        radius: radiusFor(node.tvl, minLog, maxLog),
        sublabel: `L${node.layer} · ${node.tvl === null ? 'no TVL at risk' : usd(node.tvl)}`,
        x,
        y,
        fx: x,
        fy: y,
      }
    })

    // Tuples read "dependent depends on dependency"; arrows are drawn the other
    // way round so the graph shows the direction risk travels.
    const links = position.edges.map(([dependent, dependency]) => ({
      source: dependency,
      target: dependent,
    }))

    return { nodes: graphNodes, links }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [position, narrow])

  const riskById = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes])
  const incidentNodes = useMemo(() => graphData.nodes.filter((n) => n.incident), [graphData])

  useEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const observer = new ResizeObserver((entries) => {
      const rect = entries[0].contentRect
      setSize({ width: Math.round(rect.width), height: Math.round(rect.height) })
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  // Frame the graph whenever the position or the viewport changes.
  useEffect(() => {
    if (!size.width || !size.height) return
    const id = requestAnimationFrame(() => fgRef.current?.zoomToFit(0, narrow ? 64 : 72))
    return () => cancelAnimationFrame(id)
  }, [graphData, narrow, size.width, size.height])

  // Keep each incident ring glued to its node. Written straight to the DOM so a
  // pan or zoom never costs a React render.
  useEffect(() => {
    if (incidentNodes.length === 0) return
    let frame = 0
    const tick = () => {
      const fg = fgRef.current
      if (fg) {
        const scale = typeof fg.zoom === 'function' ? fg.zoom() : 1
        for (const node of incidentNodes) {
          const el = ringRefs.current[node.id]
          if (!el) continue
          const screen = fg.graph2ScreenCoords(node.x, node.y)
          // Floor the ring so a small-but-critical dependency is still unmissable.
          const diameter = Math.max(node.radius * 2 * scale, 32)
          el.style.width = `${diameter}px`
          el.style.height = `${diameter}px`
          el.style.transform = `translate3d(${screen.x - diameter / 2}px, ${screen.y - diameter / 2}px, 0)`
        }
      }
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [incidentNodes])

  return (
    <section className="w-full px-8 py-32 md:px-16">
      <div className="mx-auto max-w-stage">
        <div className="flex flex-col gap-2 md:flex-row md:items-baseline md:justify-between">
          <h2 className="text-graph font-semibold text-chalk">
            Dependency graph — {position.name}
          </h2>
          <p className="text-caption font-normal text-neutral1 tabular">
            {position.layers.length} dependencies · 5 layers deep · arrows follow risk propagation
          </p>
        </div>

        <div ref={wrapRef} className="relative mt-12 h-[60vh] min-h-[520px] w-full overflow-hidden">
          {size.width > 0 && (
            <ForceGraph2D
              ref={fgRef}
              width={size.width}
              height={size.height}
              graphData={graphData}
              backgroundColor="#000000"
              warmupTicks={0}
              cooldownTicks={0}
              linkCurvature={0.16}
              linkWidth={1}
              linkDirectionalArrowLength={7}
              linkDirectionalArrowRelPos={0.94}
              linkColor={(link: any) => {
                const source = typeof link.source === 'object' ? link.source : null
                const target = typeof link.target === 'object' ? link.target : null
                return source?.incident || target?.incident ? '#8E8E93' : '#2C2C2E'
              }}
              nodeLabel={(node: any) => {
                const risk = riskById.get(node.id)
                return risk
                  ? `${risk.label} — ${(risk.effective_prob * 100).toFixed(1)}% incident probability`
                  : node.label
              }}
              onNodeClick={(node: any) => onSelect(node.id)}
              nodeCanvasObject={(node: any, ctx: CanvasRenderingContext2D, scale: number) => {
                const colour = LAYER_META[node.layer as LayerId].color
                const r = node.radius

                if (node.id === selectedId) {
                  ctx.beginPath()
                  ctx.arc(node.x, node.y, r + 6 / scale, 0, 2 * Math.PI)
                  ctx.strokeStyle = '#F5F5F7'
                  ctx.lineWidth = 1.5 / scale
                  ctx.stroke()
                }

                ctx.beginPath()
                ctx.arc(node.x, node.y, r, 0, 2 * Math.PI)
                ctx.fillStyle = colour
                ctx.fill()

                const top = node.y + Math.max(r, node.incident ? 17 / scale : 0) + 12 / scale
                ctx.textAlign = 'center'
                ctx.textBaseline = 'top'
                ctx.font = `600 ${13 / scale}px ${CANVAS_FONT}`
                ctx.fillStyle = '#F5F5F7'
                ctx.fillText(node.label, node.x, top)
                ctx.font = `400 ${13 / scale}px ${CANVAS_FONT}`
                ctx.fillStyle = '#8E8E93'
                ctx.fillText(node.sublabel, node.x, top + 18 / scale)
              }}
              nodePointerAreaPaint={(node: any, colour: string, ctx: CanvasRenderingContext2D) => {
                ctx.beginPath()
                ctx.arc(node.x, node.y, node.radius + 6, 0, 2 * Math.PI)
                ctx.fillStyle = colour
                ctx.fill()
              }}
            />
          )}

          {/* Incident ring — CSS keyframes only, pinned to the node in canvas space. */}
          {incidentNodes.map((node) => (
            <div
              key={node.id}
              aria-hidden="true"
              className="pointer-events-none absolute left-0 top-0 will-change-transform"
              ref={(el) => {
                ringRefs.current[node.id] = el
              }}
            >
              <span className="block h-full w-full rounded-full border-2 border-risk animate-pulse-ring" />
            </div>
          ))}
        </div>

        <ul className="mt-12 flex flex-wrap gap-x-12 gap-y-4">
          {([1, 2, 3, 4, 5] as LayerId[]).map((layer) => (
            <li key={layer} className="flex items-center gap-3 text-caption font-normal text-neutral1">
              <span
                className="h-[10px] w-[10px] shrink-0 rounded-full"
                style={{ backgroundColor: LAYER_META[layer].color }}
              />
              Layer {layer} · {LAYER_META[layer].label}
            </li>
          ))}
          <li className="flex items-center gap-3 text-caption font-normal text-neutral1">
            <span className="h-[10px] w-[10px] shrink-0 rounded-full border-2 border-risk" />
            Live incident
          </li>
        </ul>
        <p className="mt-4 text-caption font-normal text-neutral1">
          Node size tracks capital at risk in that dependency. Click any node for its
          probability and loss contribution.
        </p>
      </div>
    </section>
  )
}
