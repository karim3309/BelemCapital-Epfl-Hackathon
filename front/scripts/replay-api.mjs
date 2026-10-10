#!/usr/bin/env node
/**
 * Replay server: answers the StackTrace API routes (src/stacktrace/api.py) with the real
 * responses recorded by `python -m stacktrace.record <holder>` in docs/api_examples/recordings/. Lets the front run in "live" mode with no RPC
 * node. It never invents an answer: a request that was not recorded gets an explicit 422.
 *
 *   node scripts/replay-api.mjs [--port 8000] [--latency 0]
 *
 * --latency (ms) delays each first call per route, to rehearse the slow first analysis.
 */
import { existsSync, readdirSync, readFileSync } from 'node:fs'
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
const load = (name, folder = dir) => JSON.parse(readFileSync(join(folder, name), 'utf8'))
const health = load('health.json')

const same = (a, b) => String(a).toLowerCase() === String(b).toLowerCase()
const close = (a, b) => typeof a === 'number' && typeof b === 'number' && Math.abs(a - b) < 1e-9

// One bundle per holder: every docs/api_examples/recordings/<holder>/ folder written by `python -m stacktrace.record`.
const bundles = []
const recordings = join(dir, 'recordings')
if (existsSync(recordings)) {
  for (const name of readdirSync(recordings)) {
    const folder = join(recordings, name)
    if (!existsSync(join(folder, 'pockets.json'))) continue
    const files = readdirSync(folder)
    const pick = (prefix) => files.filter((f) => f.startsWith(prefix)).map((f) => load(f, folder))
    bundles.push({
      pockets: load('pockets.json', folder),
      book: files.includes('book.json') ? load('book.json', folder) : null,
      graphs: pick('graph_'),
      risks: pick('risk_'),
      incidents: pick('incident'),
    })
  }
}
if (bundles.length === 0) console.warn('No recording yet: run python -m stacktrace.record book:rockawayx')

function resolvePocket(pockets, key) {
  const hs = pockets.holdings
  if (/^\d+$/.test(key)) return hs[Number(key) - 1] ?? null
  return hs.find((h) => same(h.id, key)) ?? null
}

const notRecorded = (what) => [422, { detail: `response not recorded (replay server): ${what}` }]
const pocketList = (pockets) => pockets.holdings.map((h) => ({ index: h.index, id: h.id, label: h.label }))

function route(method, parts, body) {
  if (method === 'GET' && parts.length === 1 && parts[0] === 'health') return [200, health]
  if (parts[0] !== 'holders' || parts.length < 3) return [404, { detail: 'Not Found' }]
  const holder = decodeURIComponent(parts[1])
  const bundle = bundles.find((b) => same(b.pockets.holder, holder))
  if (!bundle) return notRecorded(`holder ${holder}`)
  const { pockets, book, graphs, risks, incidents } = bundle
  if (method === 'GET' && parts.length === 3 && parts[2] === 'book') return book ? [200, book] : notRecorded('book')
  if (method === 'GET' && parts.length === 3 && parts[2] === 'pockets') return [200, pockets]
  if (parts[2] !== 'pockets' || parts.length !== 5) return [404, { detail: 'Not Found' }]

  const key = decodeURIComponent(parts[3])
  const pocket = resolvePocket(pockets, key)
  if (!pocket) return [404, { detail: { error: `pocket "${key}" not found`, pockets: pocketList(pockets) } }]
  const risk = risks.find((r) => same(r.pocket.id, pocket.id))

  if (method === 'GET' && parts[4] === 'risk') return risk ? [200, risk] : notRecorded(`risk of ${pocket.label}`)
  if (method === 'GET' && parts[4] === 'graph') {
    const g = graphs.find((r) => same(r.pocket.id, pocket.id))
    return g ? [200, g] : notRecorded(`graph of ${pocket.label}`)
  }
  if (method === 'POST' && parts[4] === 'incident') {
    for (const field of ['severity', 'p']) {
      const v = body?.[field]
      if (v !== undefined && v !== null && (typeof v !== 'number' || v < 0 || v > 1)) {
        return [422, { detail: [{ loc: ['body', field], msg: 'Input should be between 0 and 1', type: 'range' }] }]
      }
    }
    if (!risk) return notRecorded(`incidents of ${pocket.label}`)
    const known = risk.incidents.find((i) => i.id.toLowerCase().startsWith(String(body?.incident ?? '').toLowerCase()))
    if (!body?.incident || !known) {
      return [404, { detail: { error: `incident "${body?.incident}" unknown`, incidents: risk.incidents.map((i) => i.id) } }]
    }
    const hit = incidents.find(
      (r) =>
        same(r.pocket.id, pocket.id) &&
        r.incident_mode.incident === known.id &&
        close(body.severity, r.incident_mode.severity) &&
        close(body.p, r.incident_mode.p_used),
    )
    return hit ? [200, hit] : notRecorded(`incident ${known.id} with these parameters`)
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
  console.log(`StackTrace replay server on http://127.0.0.1:${PORT} (recorded responses of ${bundles.length} holder(s): ` +
    `${bundles.map((b) => `${b.pockets.holder} #${b.pockets.block}`).join(', ')})`)
})
