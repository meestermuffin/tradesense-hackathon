'use client'
import { useEffect, useState } from 'react'
import { DrawdownChart } from '@/components/charts/DrawdownChart'
import { EquityCurve } from '@/components/charts/EquityCurve'
import { Panel, Stat } from '@/components/Stat'
import type { EquityPoint } from '@/lib/types'

type Point = EquityPoint & { benchmark?: number }

type Decomp = {
  premium_collected: number
  paid_to_close: number
  net: number
  round_trips: number
  still_open: number
  wins: number
  retained_pct: number | null
}
import { fmtDollar } from '@/lib/utils'

export default function Performance() {
  const [curve, setCurve] = useState<Point[]>([])
  const [d, setD] = useState<Decomp | null>(null)
  useEffect(() => {
    fetch('/api/equity')
      .then((r) => r.json())
      .then((c) => setCurve(Array.isArray(c) ? c : []))
    fetch('/api/decomposition')
      .then((r) => r.json())
      .then((x) => (x.error ? null : setD(x)))
  }, [])

  const first = curve[0]?.equity
  const last = curve[curve.length - 1]?.equity
  const change = first && last ? last - first : 0
  let peak = 0
  const drawdowns = curve.map((p) => {
    peak = Math.max(peak, p.equity)
    return { date: p.date, drawdown: peak ? (p.equity - peak) / peak : 0 }
  })
  const maxDd = drawdowns.reduce((m, p) => Math.min(m, p.drawdown), 0)

  const withBench = curve.filter((p) => p.benchmark != null)
  const stratPct = first && last ? (last - first) / first : null
  const benchPct =
    withBench.length > 1
      ? (withBench[withBench.length - 1].benchmark! - withBench[0].benchmark!) /
        withBench[0].benchmark!
      : null
  const gap = stratPct !== null && benchPct !== null ? stratPct - benchPct : null

  return (
    <div className="flex flex-col gap-5">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Sessions" value={String(curve.length)} sub="rows on the curve" />
        <Stat
          label="Change"
          value={curve.length ? `${change >= 0 ? '+' : '−'}${fmtDollar(Math.abs(change))}` : '—'}
          sub="since first recorded session"
          tone={change > 0 ? 'buy' : change < 0 ? 'sell' : 'plain'}
        />
        <Stat
          label="vs SPY"
          value={
            gap === null
              ? '—'
              : `${gap >= 0 ? '+' : '−'}${(Math.abs(gap) * 100).toFixed(2)}pp`
          }
          sub={
            stratPct !== null && benchPct !== null
              ? `book ${(stratPct * 100).toFixed(2)}% · SPY ${(benchPct * 100).toFixed(2)}%`
              : 'needs two sessions'
          }
          tone={gap === null ? 'plain' : gap > 0 ? 'buy' : gap < 0 ? 'sell' : 'plain'}
        />
        <Stat
          label="Max drawdown"
          value={`${(maxDd * 100).toFixed(2)}%`}
          sub="kill switch fires at −5%"
          tone={maxDd < -0.05 ? 'sell' : 'plain'}
        />
      </div>

      <Panel title="Equity" note="book against SPY, scaled to the same start">
        {curve.length > 1 ? (
          <EquityCurve data={curve} benchmarkLabel="SPY" />
        ) : (
          <p className="text-sm text-hold">Not enough sessions recorded yet.</p>
        )}
      </Panel>

      <Panel title="Drawdown" note="what the kill switch watches">
        {curve.length > 1 ? (
          <DrawdownChart data={drawdowns} />
        ) : (
          <p className="max-w-xl text-sm leading-relaxed text-hold">
            Shown because the kill switch triggers on it: a 5% drawdown flattens the book and stops
            opening. The book carries no per-position price stop — on a short credit spread that would
            close at the local worst price during a vol spike, on a position that often expires
            worthless.
          </p>
        )}
      </Panel>

      <Panel title="Where the P&L came from" note="components, not a ratio">
        {d && d.round_trips + d.still_open > 0 ? (
          <div className="flex flex-col gap-4">
            <div className="grid gap-3 sm:grid-cols-3">
              <div>
                <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-hold">
                  Premium collected
                </div>
                <div className="mt-1 font-mono text-xl tabular-nums text-buy">
                  {fmtDollar(d.premium_collected)}
                </div>
              </div>
              <div>
                <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-hold">
                  Paid to close
                </div>
                <div className="mt-1 font-mono text-xl tabular-nums text-sell">
                  {fmtDollar(d.paid_to_close)}
                </div>
              </div>
              <div>
                <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-hold">
                  Net
                </div>
                <div
                  className={`mt-1 font-mono text-xl tabular-nums ${d.net >= 0 ? 'text-buy' : 'text-sell'}`}
                >
                  {d.net >= 0 ? '+' : '−'}
                  {fmtDollar(Math.abs(d.net))}
                </div>
              </div>
            </div>
            <div className="text-sm text-slate-300">
              {d.wins} of {d.round_trips} round trips retained more than they gave back
              {d.still_open ? `, ${d.still_open} still open` : ''}
              {d.retained_pct !== null ? ` · ${d.retained_pct}% of premium retained` : ''}.
            </div>
          </div>
        ) : (
          <p className="text-sm text-hold">No completed trades yet.</p>
        )}
        <p className="mt-5 max-w-2xl text-xs leading-relaxed text-hold">
          Split rather than netted on purpose. A short-premium book can print a green week by
          collecting premium that decayed, or by being lucky about a move it was exposed to, and a net
          figure cannot tell those apart. A high proportion of winners is what this strategy looks
          like both when it works and when it is about to give it back.
        </p>
        <p className="mt-3 max-w-2xl text-xs leading-relaxed text-hold">
          <span className="text-slate-300">The SPY line is a comparison, not alpha.</span> This book
          is short puts, which is long delta, so its returns correlate with SPY by construction —
          crediting the gap to skill would be paying itself for exposure it is already carrying.
          Alpha means regressing that beta out, and a handful of sessions cannot support the
          regression.
        </p>
        <p className="mt-3 max-w-2xl text-xs leading-relaxed text-hold">
          No risk-adjusted ratio is shown, for the same family of reason. A Sharpe over five sessions
          cannot separate skill from luck: a book genuinely running at Sharpe 1 produces t ≈ 0.14 on
          five daily observations, which is indistinguishable from zero. The ratio would still render
          a confident-looking number, and that is the problem with it.
        </p>
      </Panel>
    </div>
  )
}
