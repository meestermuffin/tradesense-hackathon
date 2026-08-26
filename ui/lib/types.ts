// Trimmed from trade-sense. The equity strategy's fields — sentiment_exit, stop_triggered,
// oracle signals, model metadata — are gone: this book has no sentiment exit and deliberately
// no per-position price stop, so carrying those types would describe a strategy we do not run.

export type Order = {
  id: string
  symbol: string            // underlying for a spread, contract for a single leg
  // For a spread this is 'credit' or 'debit' — a multi-leg parent carries no meaningful side of
  // its own, and legs[0].side is whichever leg Alpaca returns first. Single-leg orders keep buy/sell.
  side: 'buy' | 'sell' | 'credit' | 'debit' | '—'
  qty: string
  status: string
  submitted_at: string
  filled_price: number | null
  structure?: string        // 'put_credit' etc, absent for single-leg
  legs?: { symbol: string; side: string; filled_avg_price: string | null }[]
}

export type EquityPoint = {
  date: string
  equity: number
}

export type Account = {
  account_number: string
  status: string
  equity: number
  last_equity: number
  cash: number
  open_legs: number
  options_level: number | null
  market_open: boolean
}
