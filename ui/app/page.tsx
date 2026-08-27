'use client'
import { useEffect, useState } from 'react'
import { EquityCurve } from '@/components/charts/EquityCurve'
import { Panel, Stat } from '@/components/Stat'
import type { Account, EquityPoint, Order } from '@/lib/types'
import { fmtDollar } from '@/lib/utils'

export default function Overview() {
  const [acct, setAcct] = useState<Account | null>(null)
  const [curve, setCurve] = useState<EquityPoint[]>([])
  const [orders, setOrders] = useState<Order[]>([])
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    const load = () =>
      Promise.all([
        fetch('/api/account').then((r) => r.json()),
        fetch('/api/equity').then((r) => r.json()),
        fetch('/api/orders').then((r) => r.json()),
      ])
        .then(([a, c, o]) => {
          if (a.error) return setErr(a.error)
          setAcct(a)
          setCurve(Array.isArray(c) ? c : [])
          setOrders(Array.isArray(o) ? o : [])
        })
        .catch((e) => setErr(String(e)))
    load()
    const t = setInterval(load, 30_000)
    return () => clearInterval(t)
  }, [])

  if (err)
    return (
      <div className="rounded-md border border-sell/40 bg-sell/5 px-4 py-3 text-sm text-sell">
        Could not reach the account. {err}
      </div>
    )
  if (!acct) return <div className="text-sm text-hold">Loading…</div>

  const day = acct.equity - acct.last_equity
  const filled = orders.filter((o) => o.status === 'filled').length

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-baseline justify-between">
        <h1 className="text-lg font-semibold tracking-tight text-slate-100">tradesense</h1>
        <span
          className={`badge ${acct.market_open ? 'badge-buy' : 'badge-hold'}`}
        >
          {acct.market_open ? 'market open' : 'market closed'}
        </span>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Equity" value={fmtDollar(acct.equity)} sub={acct.account_number} />
        <Stat
          label="Session"
          value={`${day >= 0 ? '+' : '−'}${fmtDollar(Math.abs(day))}`}
          sub="against previous close"
          tone={day > 0 ? 'buy' : day < 0 ? 'sell' : 'plain'}
        />
        <Stat label="Open legs" value={String(acct.open_legs)} sub="contracts held" />
        <Stat
          label="Orders filled"
          value={String(filled)}
          sub={`${orders.length} submitted`}
        />
      </div>

      <Panel
        title="Equity curve"
        note={curve.length ? `${curve.length} sessions` : 'awaiting first session'}
      >
        {curve.length > 1 ? (
          <EquityCurve data={curve} />
        ) : (
          <p className="max-w-xl text-sm leading-relaxed text-hold">
            {curve.length === 0 ? 'No sessions recorded yet.' : 'One session recorded.'} The curve is
            written once per session by a job kept deliberately separate from the trading cycle, so a
            skipped cycle still leaves a row. Drawdown is measured against a running peak, so a
            missing session would move the peak and quietly understate it.
          </p>
        )}
      </Panel>
    </div>
  )
}
