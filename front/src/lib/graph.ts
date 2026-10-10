import type { Graph, GraphEdge, GraphNode, NodeType } from '../api/types'
import { pct, pricingLabel, usdShort } from './format'

/*
 * Pure graph traversal over the backend's graph.json: layout, paths, labels.
 * No risk is computed here. Edge direction follows the contract: `from` depends
 * on `to`, and a failure travels against the arrows (from `to` back to `from`).
 */

export type ViewType = NodeType | 'position'

export interface ViewNode {
  id: string
  type: ViewType
  label: string
  title: string
  subtitle: string
  depth: number
  /** Largest share of the pocket that reaches this node along a single path (product of edge weights). */
  exposure: number
  pricingMode?: string
  node?: GraphNode
  radius: number
  x: number
  y: number
  fx: number
  fy: number
}

export interface ViewLink {
  key: string
  source: string
  target: string
  edge: GraphEdge
}

export interface GraphView {
  rootId: string
  nodes: ViewNode[]
  links: ViewLink[]
  hiddenChainEdges: number
}

export const edgeKey = (e: { from: string; to: string; type: string }) => `${e.from}|${e.type}|${e.to}`

const TYPE_ORDER: ViewType[] = [
  'position',
  'vault',
  'lending_market',
  'liquidity_venue',
  'asset',
  'oracle',
  'issuer',
  'offchain_counterparty',
  'chain',
]

const BASE_RADIUS: Record<string, number> = {
  position: 13,
  vault: 11,
  lending_market: 9,
  liquidity_venue: 9,
  asset: 7,
  oracle: 6,
  issuer: 6,
  offchain_counterparty: 6,
  chain: 6,
}

const clip = (text: string, max = 24) => (text.length > max ? `${text.slice(0, max - 1)}…` : text)

/** Short two-line label for the canvas; the full label stays in the node sheet. */
export function shortLabel(node: GraphNode): { title: string; subtitle: string } {
  const m = node.meta ?? {}
  switch (node.type) {
    case 'lending_market':
      return {
        title: node.label.replace(/^Morpho Blue\s+/, '').replace(/\s*\(LLTV[^)]*\)/, ''),
        subtitle: typeof m.lltv === 'number' ? `market · LLTV ${pct(m.lltv, 0)}` : 'lending market',
      }
    case 'oracle': {
      const pricing = pricingLabel(m.pricing_mode)
      if (node.label.startsWith('Chainlink ')) {
        return { title: node.label.slice('Chainlink '.length), subtitle: `Chainlink · ${pricing}` }
      }
      if (node.label.startsWith('MorphoChainlinkOracleV2')) {
        return { title: 'Market oracle', subtitle: pricing }
      }
      const parts = node.label.match(/^(?:Feed\s+)?(.*?)\s*\((.*?)\)\s*(.*)$/)
      if (parts) {
        const [, head, paren, tail] = parts
        return tail
          ? { title: tail, subtitle: `${head} · ${pricing}` }
          : { title: head, subtitle: `${paren} · ${pricing}` }
      }
      return { title: node.label.replace(/^Feed\s+/, ''), subtitle: pricing }
    }
    case 'vault':
      return { title: node.label, subtitle: 'vault' }
    case 'issuer':
      return {
        title: node.label.replace(/\s*\(curator\)\s*$/, ''),
        subtitle: m.role === 'vault_curator' ? 'curator' : 'issuer',
      }
    case 'asset':
      return { title: node.label, subtitle: m.asset_kind ? String(m.asset_kind).replace(/_/g, ' ') : 'asset' }
    case 'chain':
      return { title: node.label, subtitle: 'chain' }
    case 'offchain_counterparty':
      return { title: node.label, subtitle: 'off-chain' }
    default:
      return { title: node.label, subtitle: node.type }
  }
}

export function buildView(graph: Graph, opts: { showChain: boolean; vertical: boolean }): GraphView {
  const rootId = graph.position.id
  const byId = new Map<string, GraphNode>(graph.nodes.map((n) => [n.id, n]))
  const keep = (id: string) => id === rootId || (byId.has(id) && (opts.showChain || byId.get(id)!.type !== 'chain'))

  const edges = graph.edges.filter((e) => keep(e.from) && keep(e.to))
  const hiddenChainEdges = graph.edges.length - edges.length
  const ids = [rootId, ...graph.nodes.map((n) => n.id).filter((id) => keep(id))]
  const limit = ids.length

  // Longest path from the position: each layer is one more hop of dependency.
  const depth = new Map<string, number>([[rootId, 0]])
  const exposure = new Map<string, number>([[rootId, 1]])
  for (let round = 0; round < limit; round++) {
    let changed = false
    for (const e of edges) {
      const du = depth.get(e.from)
      if (du === undefined) continue
      const next = Math.min(du + 1, limit)
      if ((depth.get(e.to) ?? -1) < next) {
        depth.set(e.to, next)
        changed = true
      }
      const share = Math.min(1, (exposure.get(e.from) ?? 0) * (Number.isFinite(e.weight) ? e.weight : 1))
      if ((exposure.get(e.to) ?? 0) < share) {
        exposure.set(e.to, share)
        changed = true
      }
    }
    if (!changed) break
  }
  const maxDepth = Math.max(0, ...depth.values())

  const columns = new Map<number, string[]>()
  for (const id of ids) {
    const d = depth.get(id) ?? maxDepth + 1
    depth.set(id, d)
    if (!columns.has(d)) columns.set(d, [])
    columns.get(d)!.push(id)
  }

  const typeOf = (id: string): ViewType => (id === rootId ? 'position' : byId.get(id)!.type)
  const order = new Map<string, number>()
  for (const [, col] of [...columns.entries()].sort((a, b) => a[0] - b[0])) {
    col.sort((a, b) => {
      const t = TYPE_ORDER.indexOf(typeOf(a)) - TYPE_ORDER.indexOf(typeOf(b))
      return t !== 0 ? t : (byId.get(a)?.label ?? '').localeCompare(byId.get(b)?.label ?? '')
    })
    col.forEach((id, i) => order.set(id, i - (col.length - 1) / 2))
  }

  // Two barycentre sweeps: place each node near the dependents that point at it.
  const parents = new Map<string, string[]>()
  for (const e of edges) {
    if (!parents.has(e.to)) parents.set(e.to, [])
    parents.get(e.to)!.push(e.from)
  }
  for (let sweep = 0; sweep < 2; sweep++) {
    for (const [d, col] of [...columns.entries()].sort((a, b) => a[0] - b[0])) {
      if (d === 0) continue
      const bary = (id: string) => {
        const ps = (parents.get(id) ?? []).filter((p) => (depth.get(p) ?? 0) < d)
        return ps.length ? ps.reduce((s, p) => s + (order.get(p) ?? 0), 0) / ps.length : order.get(id) ?? 0
      }
      const scored = col.map((id) => ({ id, b: bary(id) }))
      scored.sort((a, b) => a.b - b.b)
      col.splice(0, col.length, ...scored.map((s) => s.id))
      col.forEach((id, i) => order.set(id, i - (col.length - 1) / 2))
    }
  }

  // Wide screens: depth runs left to right. Phones: top to bottom, wide layers wrap in rows of three.
  const pos = new Map<string, { x: number; y: number }>()
  if (opts.vertical) {
    const PER_ROW = 3
    const ACROSS = 118
    const SUB_ROW = 64
    const GAP = 72
    let cursor = 0
    for (const [, col] of [...columns.entries()].sort((a, b) => a[0] - b[0])) {
      col.forEach((id, i) => {
        const r = Math.floor(i / PER_ROW)
        const inRow = Math.min(PER_ROW, col.length - r * PER_ROW)
        pos.set(id, { x: ((i % PER_ROW) - (inRow - 1) / 2) * ACROSS, y: cursor + r * SUB_ROW })
      })
      cursor += Math.ceil(col.length / PER_ROW) * SUB_ROW + GAP
    }
  } else {
    for (const id of ids) pos.set(id, { x: (depth.get(id) ?? 0) * 250, y: (order.get(id) ?? 0) * 52 })
  }

  const nodes: ViewNode[] = ids.map((id) => {
    const node = byId.get(id)
    const type = typeOf(id)
    const exp = exposure.get(id) ?? 0
    const label = node ? node.label : 'Your pocket'
    const { title, subtitle } = node
      ? shortLabel(node)
      : { title: 'Your pocket', subtitle: usdShort(graph.position.value_usd) }
    const { x, y } = pos.get(id)!
    return {
      id,
      type,
      label,
      title: clip(title, opts.vertical ? 12 : 24),
      subtitle: clip(subtitle, opts.vertical ? 18 : 30),
      depth: depth.get(id) ?? 0,
      exposure: exp,
      pricingMode: node?.type === 'oracle' ? node.meta?.pricing_mode : undefined,
      node,
      radius: (BASE_RADIUS[type] ?? 6) * (0.75 + 0.5 * Math.sqrt(exp)),
      x,
      y,
      fx: x,
      fy: y,
    }
  })

  const links: ViewLink[] = edges.map((edge) => ({ key: edgeKey(edge), source: edge.from, target: edge.to, edge }))
  return { rootId, nodes, links, hiddenChainEdges }
}

/** Nodes that can reach `target` (its dependents, all the way up to the position). */
function dependentsOf(edges: GraphEdge[], target: string): Set<string> {
  const reverse = new Map<string, string[]>()
  for (const e of edges) {
    if (!reverse.has(e.to)) reverse.set(e.to, [])
    reverse.get(e.to)!.push(e.from)
  }
  const seen = new Set<string>([target])
  const stack = [target]
  while (stack.length) {
    const id = stack.pop()!
    for (const p of reverse.get(id) ?? []) {
      if (!seen.has(p)) {
        seen.add(p)
        stack.push(p)
      }
    }
  }
  return seen
}

/** Every edge on a path between the position and `target`: how a failure there reaches the pocket. */
export function pathTo(graph: Graph, target: string): { nodes: Set<string>; edges: Set<string> } {
  const onPath = dependentsOf(graph.edges, target)
  if (!onPath.has(graph.position.id)) return { nodes: new Set(), edges: new Set() }
  const edges = new Set<string>()
  for (const e of graph.edges) {
    if (onPath.has(e.from) && onPath.has(e.to)) edges.add(edgeKey(e))
  }
  return { nodes: onPath, edges }
}

/** The same highlight, from the exact edges the backend returned for an incident. */
export function pathFromEdges(edges: GraphEdge[]): { nodes: Set<string>; edges: Set<string> } {
  const nodes = new Set<string>()
  const keys = new Set<string>()
  for (const e of edges) {
    nodes.add(e.from)
    nodes.add(e.to)
    keys.add(edgeKey(e))
  }
  return { nodes, edges: keys }
}

export function proofsFor(graph: Graph, id: string) {
  return {
    dependsOn: graph.edges.filter((e) => e.from === id),
    dependedOnBy: graph.edges.filter((e) => e.to === id),
  }
}

export function sourceCounts(graph: Graph) {
  return graph.edges.reduce<Record<string, number>>((acc, e) => {
    acc[e.source] = (acc[e.source] ?? 0) + 1
    return acc
  }, {})
}

/** Oracles whose price does not follow the market — the API flags these as risk #1. */
export function nonMarketOracles(graph: Graph): GraphNode[] {
  return graph.nodes.filter((n) => n.type === 'oracle' && n.meta?.pricing_mode && n.meta.pricing_mode !== 'market')
}
