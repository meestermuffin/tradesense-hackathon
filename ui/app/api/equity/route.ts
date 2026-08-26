import fs from 'node:fs'
import path from 'node:path'

export const dynamic = 'force-dynamic'

// Reads the committed equity curve rather than querying Alpaca. That file is written once per
// session by a job kept deliberately independent of the trading cycle, so the curve has no gaps even
// when a cycle is skipped. Max drawdown runs against a peak, so a missing row understates it.
//
// SPY is attached as a benchmark, scaled to the book's starting equity so both fit one axis. It is a
// comparison, NOT alpha: this book is short puts, which is long delta, so its returns correlate with
// SPY by construction. Calling the gap alpha would credit skill for exposure. Real alpha means
// regressing out beta, and a handful of sessions cannot support that regression.
async function spyCloses(from: string, to: string) {
  const key = process.env.ALPACA_KEY_ID
  const secret = process.env.ALPACA_SECRET_KEY
  if (!key || !secret) return {}
  const url =
    `https://data.alpaca.markets/v2/stocks/SPY/bars` +
    `?timeframe=1Day&adjustment=raw&start=${from}&end=${to}&limit=1000&feed=iex`
  const res = await fetch(url, {
    headers: { 'APCA-API-KEY-ID': key, 'APCA-API-SECRET-KEY': secret },
    cache: 'no-store',
  })
  if (!res.ok) return {}
  const j = await res.json()
  const out: Record<string, number> = {}
  for (const b of j.bars ?? []) out[String(b.t).slice(0, 10)] = Number(b.c)
  return out
}

export async function GET() {
  const dir = path.join(process.cwd(), '..', 'data', 'equity')
  if (!fs.existsSync(dir)) return Response.json([])
  const points: { date: string; equity: number; benchmark?: number }[] = []
  for (const f of fs.readdirSync(dir).filter((x) => x.endsWith('.csv'))) {
    const lines = fs.readFileSync(path.join(dir, f), 'utf8').trim().split('\n')
    const head = lines[0].split(',')
    const di = head.indexOf('day')
    const ei = head.indexOf('equity')
    for (const line of lines.slice(1)) {
      const c = line.split(',')
      if (c[di] && c[ei]) points.push({ date: c[di], equity: Number(c[ei]) })
    }
  }
  points.sort((a, b) => a.date.localeCompare(b.date))
  if (points.length < 2) return Response.json(points)

  try {
    const spy = await spyCloses(points[0].date, points[points.length - 1].date)
    const base = spy[points[0].date]
    if (base) {
      const start = points[0].equity
      for (const p of points) {
        const c = spy[p.date]
        if (c) p.benchmark = Math.round((start * (c / base)) * 100) / 100
      }
    }
  } catch {
    // A missing benchmark is not a reason to lose the curve.
  }
  return Response.json(points)
}
