// Trimmed from trade-sense. signalColor and signalBadgeClass described the equity strategy's
// oracle signals and have no meaning for this book.
import { clsx, type ClassValue } from 'clsx'

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs)
}

export function fmt(n: number | null | undefined, decimals = 2): string {
  if (n == null || !isFinite(n)) return '—'
  return n.toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
}

export function fmtDollar(n: number) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n)
}

export function fmtPct(n: number, decimals = 2) {
  return `${n >= 0 ? '+' : ''}${fmt(n, decimals)}%`
}



export function pnlColor(n: number) {
  if (n > 0) return 'text-buy'
  if (n < 0) return 'text-sell'
  return 'text-hold'
}

export function isMarketHours(): boolean {
  const now = new Date()
  const et = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }))
  const day = et.getDay()
  if (day === 0 || day === 6) return false
  const h = et.getHours()
  const m = et.getMinutes()
  const mins = h * 60 + m
  return mins >= 9 * 60 + 30 && mins < 16 * 60
}

export function pollInterval(base: number): number {
  return isMarketHours() ? base : base * 5
}

export function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const s = Math.floor(diff / 1000)
  if (s < 60) return `${s}s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const hr = Math.floor(m / 60)
  if (hr < 24) return `${hr}h ago`
  return `${Math.floor(hr / 24)}d ago`
}

export function isoDate(d: Date = new Date()) {
  return d.toISOString().slice(0, 10)
}

const MONTHS_SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const DAYS_SHORT = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

/**
 * Parse a date-ish API string ("2026-08-18" or "2026-08-18T00:00:00Z") into a *local*
 * Date. Built from explicit parts because `new Date("2026-08-18")` is parsed as UTC
 * midnight, which renders as the previous day in any negative-offset timezone.
 */
function parseDateParts(s: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s)
  if (!m) return null
  return new Date(+m[1], +m[2] - 1, +m[3])
}

/** Compact axis tick label, e.g. "Aug 18". */
export function fmtChartDate(s: string): string {
  const d = parseDateParts(s)
  if (!d) return s
  return `${MONTHS_SHORT[d.getMonth()]} ${d.getDate()}`
}

/** Intraday axis tick, e.g. "9:35 AM" — used by the 1D range where points are 5-minute bars. */
export function fmtChartTime(s: string): string {
  const d = new Date(s)
  if (isNaN(d.getTime())) return s
  return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
}

/** Intraday tooltip label, e.g. "Aug 19, 9:35 AM". */
export function fmtChartTimeLong(s: string): string {
  const d = new Date(s)
  if (isNaN(d.getTime())) return s
  return `${MONTHS_SHORT[d.getMonth()]} ${d.getDate()}, ${d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })}`
}

/** Verbose tooltip label, e.g. "Tue, Aug 18, 2026". */
export function fmtChartDateLong(s: string): string {
  const d = parseDateParts(s)
  if (!d) return s
  return `${DAYS_SHORT[d.getDay()]}, ${MONTHS_SHORT[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`
}
