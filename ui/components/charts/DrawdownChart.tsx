'use client'

import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis,
  Tooltip, CartesianGrid,
} from 'recharts'
import { fmtPct, fmtChartDate, fmtChartDateLong } from '@/lib/utils'

interface Point {
  date: string
  drawdown: number
}

export function DrawdownChart({
  data,
  tickFormatter = fmtChartDate,
  labelFormatter = fmtChartDateLong,
}: {
  data: Point[]
  tickFormatter?: (s: string) => string
  labelFormatter?: (s: string) => string
}) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="ddGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#f87171" stopOpacity={0.3} />
            <stop offset="95%" stopColor="#f87171" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
        <XAxis
          dataKey="date"
          tickFormatter={tickFormatter}
          minTickGap={24}
          tick={{ fontSize: 11, fill: '#64748b' }}
          tickLine={false}
          axisLine={false}
        />
        <YAxis
          tickFormatter={(v) => `${v.toFixed(1)}%`}
          tick={{ fontSize: 11, fill: '#64748b' }}
          tickLine={false}
          axisLine={false}
          width={48}
        />
        <Tooltip
          contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 6 }}
          labelStyle={{ color: '#94a3b8', fontSize: 11 }}
          labelFormatter={(l) => labelFormatter(String(l))}
          formatter={(v: number) => [fmtPct(v), 'Drawdown']}
        />
        <Area
          type="monotone"
          dataKey="drawdown"
          stroke="#f87171"
          strokeWidth={1.5}
          fill="url(#ddGrad)"
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}
