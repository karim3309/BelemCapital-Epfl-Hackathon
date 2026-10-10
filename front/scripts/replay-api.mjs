#!/usr/bin/env node
/**
 * Replay server: answers the StackTrace API routes (src/stacktrace/api.py) with the real
 * responses recorded in docs/api_examples/. Lets the front run in "live" mode with no RPC
 * node. It never invents an answer: a request that was not recorded gets an explicit 422.
 *
 *   node scripts/replay-api.mjs [--port 8000] [--latency 0]
 *
 * --latency (ms) delays each first call per route, to rehearse the slow first analysis.
 */
import { readFileSync } from 'node:fs'
import { createServer } from 'node:http'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const args = process.argv.slice(2)
const opt = (name, fallback) => {
  const i = args.indexOf(`--${name}`)
  return i >= 0 ? Number(args[i + 1]) : fallback
}
const PORT = opt('port', 8000)
const LATENCY = opt('latency', 0)

const dir = join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'docs', 'api_examples')
const load = (name) => JSON.parse(readFileSync(join(dir, name), 'utf8'))
const health = load('health.json')
const pockets = load('pockets.json')
const book = load('book.json')
const graphs = [load('graph_vault.json')]
const risks = [load('risk_vault.json'), load('risk_borrow.json')]
const incidents = [load('incident.json')]

const same = (a, b) => String(a).toLowerCase() === String(b).toLowerCase()
const close = (a, b) => typeof a === 'number' && typeof b === 'number' && Math.abs(a - b) < 1e-9

function resolvePocket(key) {
  const hs = pockets.holdings
  if (/^\d+$/.test(key)) return hs[Number(key) - 1] ?? null
  return hs.find((h) => same(h.id, key)) ?? null
}

const notRecorded = (what) => [422, { detail: `réponse non enregistrée (serveur de rejeu) : ${what}` }]
const pocketList = () => pockets.holdings.map((h) => ({ index: h.index, id: h.id, label: h.label }))

function route(method, parts, body) {
  if (method === 'GET' && parts.length === 1 && parts[0] === 'health') return [200, health]
  if (parts[0] !== 'holders' || parts.length < 3) return [404, { detail: 'Not Found' }]
  const holder = decodeURIComponent(parts[1])
  if (!same(holder, pockets.holder)) return notRecorded(`détenteur ${holder}`)
  if (method === 'GET' && parts.length === 3 && parts[2] === 'book') return [200, book]
  if (method === 'GET' && parts.length === 3 && parts[2] === 'pockets') return [200, pockets]
  if (parts[2] !== 'pockets' || parts.length !== 5) return [404, { detail: 'Not Found' }]

  const key = decodeURIComponent(parts[3])
  const pocket = resolvePocket(key)
  if (!pocket) return [404, { detail: { error: `poche « ${key} » introuvable`, pockets: pocketList() } }]
  const risk = risks.find((r) => same(r.pocket.id, pocket.id))

  if (method === 'GET' && parts[4] === 'risk') return risk ? [200, risk] : notRecorded(`risque de ${pocket.label}`)
  if (method === 'GET' && parts[4] === 'graph') {
    const g = graphs.find((r) => same(r.pocket.id, pocket.id))
    return g ? [200, g] : notRecorded(`graphe de ${pocket.label}`)
  }
  if (method === 'POST' && parts[4] === 'incident') {
    for (const field of ['severity', 'p']) {
      const v = body?.[field]
      if (v !== undefined && v !== null && (typeof v !== 'number' || v < 0 || v > 1)) {
        return [422, { detail: [{ loc: ['body', field], msg: 'Input should be between 0 and 1', type: 'range' }] }]
      }
    }
    if (!risk) return notRecorded(`incidents de ${pocket.label}`)
    const known = risk.incidents.find((i) => i.id.toLowerCase().startsWith(String(body?.incident ?? '').toLowerCase()))
    if (!body?.incident || !known) {
      return [404, { detail: { error: `incident « ${body?.incident} » inconnu`, incidents: risk.incidents.map((i) => i.id) } }]
    }
    const hit = incidents.find(
      (r) =>
        same(r.pocket.id, pocket.id) &&
        r.incident_mode.incident === known.id &&
        close(body.severity, r.incident_mode.severity) &&
        close(body.p, r.incident_mode.p_used),
    )
    return hit ? [200, hit] : notRecorded(`incident ${known.id} avec ces paramètres`)
  }
  return [404, { detail: 'Not Found' }]
}

const seen = new Set()
createServer((req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*')
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST')
  res.setHeader('Access-Control-Allow-Headers', '*')
  if (req.method === 'OPTIONS') {
    res.writeHead(204).end()
    return
  }
  let raw = ''
  req.on('data', (chunk) => (raw += chunk))
  req.on('end', () => {
    const url = new URL(req.url, `http://${req.headers.host}`)
    const parts = url.pathname.split('/').filter(Boolean)
    let body = null
    try {
      body = raw ? JSON.parse(raw) : null
    } catch {
      body = null
    }
    const [status, payload] = route(req.method, parts, body)
    const key = `${req.method} ${parts.slice(0, 3).join('/')} ${parts[4] ?? ''}`
    const delay = LATENCY && !seen.has(key) ? LATENCY : 0
    seen.add(key)
    setTimeout(() => {
      res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8' })
      res.end(JSON.stringify(payload))
      console.log(`${status} ${req.method} ${url.pathname}${delay ? ` (+${delay} ms)` : ''}`)
    }, delay)
  })
}).listen(PORT, '127.0.0.1', () => {
  console.log(`Serveur de rejeu StackTrace sur http://127.0.0.1:${PORT} (bloc #${pockets.block}, réponses enregistrées)`)
})
