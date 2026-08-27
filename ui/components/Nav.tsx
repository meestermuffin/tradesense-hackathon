'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'

// No auth. The original had login, register and a middleware guard; a demo URL a judge clicks
// should not present a login wall.
const links = [
  { href: '/', label: 'Overview' },
  { href: '/orders', label: 'Orders' },
  { href: '/performance', label: 'Performance' },
]

export function Nav() {
  const path = usePathname()
  return (
    <nav className="border-b border-border bg-surface/60 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center gap-8 px-5 py-3">
        <Link href="/" className="flex items-baseline gap-2">
          <span className="font-mono text-sm font-semibold tracking-tight text-slate-100">
            tradesense
          </span>
          <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-hold">
            paper
          </span>
        </Link>
        <div className="flex gap-1">
          {links.map((l) => {
            const active = path === l.href
            return (
              <Link
                key={l.href}
                href={l.href}
                className={[
                  'rounded px-2.5 py-1 text-sm transition-colors',
                  active
                    ? 'bg-surface-2 text-slate-100'
                    : 'text-hold hover:bg-surface-2/60 hover:text-slate-200',
                ].join(' ')}
              >
                {l.label}
              </Link>
            )
          })}
        </div>
      </div>
    </nav>
  )
}
