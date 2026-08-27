'use client'

import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis,
  Tooltip, CartesianGrid, Legend,
} from 'recharts'
import { fmtDollar, fmtChartDate, fmtChartDateLong } from '@/lib/utils'

interface Point {
  date: string
  equity: number
  benchmark?: number
}

export function EquityCurve({
  data,
  benchmarkLabel = 'Benchmark',
  tickFormatter = fmtChartDate,
  labelFormatter = fmtChartDateLong,
}: {
  data: Point[]
  benchmarkLabel?: string
  /** Swapped for time formatters on the intraday (1D) range. */
  tickFormatter?: (s: string) => string
  labelFormatter?: (s: string) => string
}) {
  const hasBenchmark = data.some((d) => d.benchmark != null)
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
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
          tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
          tick={{ fontSize: 11, fill: '#64748b' }}
          tickLine={false}
          axisLine={false}
          width={52}
        />
        <Tooltip
          contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 6 }}
          labelStyle={{ color: '#94a3b8', fontSize: 11 }}
          labelFormatter={(l) => labelFormatter(String(l))}
          formatter={(v: number, name) => [fmtDollar(v), name]}
        />
        {hasBenchmark && <Legend wrapperStyle={{ fontSize: 11 }} />}
        <Line
          type="monotone"
          dataKey="equity"
          name="Equity"
          stroke="#3b82f6"
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 4, fill: '#3b82f6' }}
        />
        {hasBenchmark && (
          <Line
            type="monotone"
            dataKey="benchmark"
            name={benchmarkLabel}
            stroke="#64748b"
            strokeWidth={1.5}
            strokeDasharray="4 4"
            dot={false}
          />
        )}
      </LineChart>
    </ResponsiveContainer>
  )
}
