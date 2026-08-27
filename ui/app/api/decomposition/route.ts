import { orders } from '@/lib/alpaca'

export const dynamic = 'force-dynamic'

const MULTIPLIER = 100

// Where the P&L came from, rather than a ratio the sample cannot support.
//
// A short-premium book can print a green week two ways: by collecting premium that decayed, or by
// being lucky about a move it was exposed to. A net figure cannot tell those apart, and a high
// proportion of winners is what this strategy looks like both when it is working and when it is
// about to give it back. So the components are reported and the net is left as their difference.
export async function GET() {
  try {
    const all = await orders(200)
    const filled = all.filter((o) => o.status === 'filled' && o.filled_price !== null)

    // A close carries the same contracts as its open, so the leg set identifies the round trip.
    const trips = new Map<string, { credit: number; debit: number }>()
    for (const o of filled) {
      const key = (o.legs ?? []).map((l) => l.symbol).sort().join('|') || `${o.symbol}:${o.id}`
      const t = trips.get(key) ?? { credit: 0, debit: 0 }
      const dollars = Math.abs(o.filled_price as number) * MULTIPLIER * Number(o.qty || 1)
      if ((o.filled_price as number) < 0) t.credit += dollars
      else t.debit += dollars
      trips.set(key, t)
    }

    const v = [...trips.values()]
    const closed = v.filter((t) => t.credit > 0 && t.debit > 0)
    const open = v.filter((t) => t.credit > 0 && t.debit === 0)
    const collected = v.reduce((s, t) => s + t.credit, 0)
    const paid = v.reduce((s, t) => s + t.debit, 0)

    return Response.json({
      premium_collected: Math.round(collected * 100) / 100,
      paid_to_close: Math.round(paid * 100) / 100,
      net: Math.round((collected - paid) * 100) / 100,
      round_trips: closed.length,
      still_open: open.length,
      wins: closed.filter((t) => t.credit > t.debit).length,
      retained_pct: collected > 0 ? Math.round(((collected - paid) / collected) * 1000) / 10 : null,
    })
  } catch (e) {
    return Response.json({ error: String(e) }, { status: 502 })
  }
}
