export function Stat({
  label,
  value,
  sub,
  tone = 'plain',
}: {
  label: string
  value: string
  sub?: string
  tone?: 'plain' | 'buy' | 'sell'
}) {
  const toneClass = tone === 'buy' ? 'text-buy' : tone === 'sell' ? 'text-sell' : 'text-slate-100'
  return (
    <div className="rounded-md border border-border bg-surface px-4 py-3.5">
      <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-hold">{label}</div>
      <div className={`mt-1.5 font-mono text-[1.65rem] leading-none tabular-nums ${toneClass}`}>
        {value}
      </div>
      {sub ? <div className="mt-1.5 text-xs text-hold">{sub}</div> : null}
    </div>
  )
}

export function Panel({
  title,
  note,
  children,
}: {
  title: string
  note?: string
  children: React.ReactNode
}) {
  return (
    <section className="rounded-md border border-border bg-surface">
      <header className="flex items-baseline justify-between border-b border-border px-4 py-2.5">
        <h2 className="font-mono text-[11px] uppercase tracking-[0.14em] text-slate-300">{title}</h2>
        {note ? <span className="text-xs text-hold">{note}</span> : null}
      </header>
      <div className="p-4">{children}</div>
    </section>
  )
}
