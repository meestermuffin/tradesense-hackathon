'use client'
import { useEffect, useState } from 'react'
import { Panel } from '@/components/Stat'
import type { Order } from '@/lib/types'

function statusBadge(s: string) {
  if (s === 'filled') return 'badge badge-buy'
  if (s === 'canceled' || s === 'expired' || s === 'rejected') return 'badge badge-hold'
  return 'badge badge-hold'
}

export default function Orders() {
  const [orders, setOrders] = useState<Order[]>([])
  const [loaded, setLoaded] = useState(false)
  useEffect(() => {
    fetch('/api/orders')
      .then((r) => r.json())
      .then((o) => {
        setOrders(Array.isArray(o) ? o : [])
        setLoaded(true)
      })
  }, [])

  return (
    <Panel title="Orders" note={loaded ? `${orders.length} submitted` : undefined}>
      <div className="-mx-4 -my-4 overflow-x-auto">
        <table className="w-full min-w-[46rem] text-sm">
          <thead>
            <tr className="border-b border-border">
              {['Submitted', 'Underlying', 'Structure', 'Net', 'Qty', 'Fill', 'Status'].map((h) => (
                <th
                  key={h}
                  className="px-4 py-2.5 text-left font-mono text-[10px] uppercase tracking-[0.14em] font-medium text-hold"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {orders.map((o) => (
              <tr key={o.id} className="border-b border-border/60 last:border-0 hover:bg-surface-2/40">
                <td className="px-4 py-2.5 font-mono text-xs tabular-nums text-hold">
                  {o.submitted_at?.slice(0, 16).replace('T', ' ')}
                </td>
                <td className="px-4 py-2.5 font-medium text-slate-100">{o.symbol}</td>
                <td className="px-4 py-2.5 text-slate-400">{o.structure ?? 'single'}</td>
                <td className="px-4 py-2.5">
                  <span
                    className={
                      o.side === 'credit'
                        ? 'text-buy'
                        : o.side === 'debit'
                          ? 'text-sell'
                          : 'text-hold'
                    }
                  >
                    {o.side}
                  </span>
                </td>
                <td className="px-4 py-2.5 font-mono tabular-nums text-slate-300">{o.qty}</td>
                <td className="px-4 py-2.5 font-mono tabular-nums text-slate-300">
                  {o.filled_price === null ? '—' : Math.abs(o.filled_price).toFixed(2)}
                </td>
                <td className="px-4 py-2.5">
                  <span className={statusBadge(o.status)}>{o.status}</span>
                </td>
              </tr>
            ))}
            {loaded && orders.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-10 text-center text-sm text-hold">
                  No orders yet.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
      <p className="mt-6 max-w-2xl text-xs leading-relaxed text-hold">
        A multi-leg order appears once, as its underlying — listing the legs separately would present
        one spread as two unrelated trades. Net shows whether the spread opened for a credit or closed
        for a debit, since a multi-leg parent carries no meaningful side of its own.
      </p>
    </Panel>
  )
}
