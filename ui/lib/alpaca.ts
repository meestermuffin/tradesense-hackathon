// Server-side only. Credentials never reach the browser.
//
// Replaces trade-sense's lib/api.ts, which was the single file that knew about ORACLE_URL,
// TRADER_URL, PULSE_URL and KEYMASTER_URL. Nothing else in the UI referenced a backend, so
// rewriting this one module was the whole port.

import type { Order } from './types'

const DATA = 'https://data.alpaca.markets'
const TRADE = 'https://paper-api.alpaca.markets'

function headers() {
  const key = process.env.ALPACA_KEY_ID
  const secret = process.env.ALPACA_SECRET_KEY
  if (!key || !secret) throw new Error('ALPACA_KEY_ID / ALPACA_SECRET_KEY not set')
  return { 'APCA-API-KEY-ID': key, 'APCA-API-SECRET-KEY': secret }
}

async function get(host: string, path: string) {
  const res = await fetch(host + path, { headers: headers(), cache: 'no-store' })
  if (!res.ok) throw new Error(`${res.status} ${path}`)
  return res.json()
}

export async function account() {
  const [a, positions, clock] = await Promise.all([
    get(TRADE, '/v2/account'),
    get(TRADE, '/v2/positions'),
    get(TRADE, '/v2/clock'),
  ])
  return {
    account_number: a.account_number,
    status: a.status,
    equity: Number(a.equity),
    last_equity: Number(a.last_equity),
    cash: Number(a.cash),
    open_legs: positions.length,
    options_level: a.options_approved_level ?? null,
    market_open: Boolean(clock.is_open),
  }
}

export async function orders(limit = 50): Promise<Order[]> {
  const raw = await get(TRADE, `/v2/orders?status=all&limit=${limit}&direction=desc`)
  // A multi-leg order arrives as a parent with legs. Showing the legs separately would present
  // one spread as two unrelated trades, so the parent is summarised to the underlying.
  return raw.map((o: Record<string, unknown>): Order => {
    const legs = (o.legs as Record<string, unknown>[] | undefined) ?? []
    const first = legs[0]?.symbol as string | undefined
    const underlying = first ? first.replace(/\d{6}[CP]\d+$/, '') : (o.symbol as string)
    return {
      id: o.id as string,
      symbol: underlying,
      // A multi-leg parent carries an empty side, and legs[0].side is whichever leg Alpaca
      // happens to return first -- here the long one -- so it says nothing useful. What matters
      // for a spread is whether it was opened for a credit or a debit, which the sign of the net
      // fill gives directly. Alpaca reports a credit as a negative net price.
      side: (legs.length
        ? Number(o.filled_avg_price ?? 0) < 0
          ? 'credit'
          : Number(o.filled_avg_price ?? 0) > 0
            ? 'debit'
            : '—'
        : ((o.side as string) || '—')) as Order['side'],
      qty: String(o.qty ?? ''),
      status: o.status as string,
      submitted_at: o.submitted_at as string,
      filled_price: o.filled_avg_price ? Number(o.filled_avg_price) : null,
      structure: legs.length === 2 ? 'vertical' : legs.length === 4 ? 'condor' : undefined,
      legs: legs.map((l) => ({
        symbol: l.symbol as string,
        side: l.side as string,
        filled_avg_price: (l.filled_avg_price as string) ?? null,
      })),
    }
  })
}
