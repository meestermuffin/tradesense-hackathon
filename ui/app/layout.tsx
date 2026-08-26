import type { Metadata } from 'next'
import './globals.css'
import { Nav } from '@/components/Nav'

export const metadata: Metadata = {
  title: 'tradesense',
  description: 'Short-premium options book — account, orders and performance',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      {/* flex-col, not flex. trade-sense's Nav was a vertical sidebar, so the body was a flex row;
          with a horizontal top bar that put the nav and the page side by side at half width each. */}
      <body className="flex min-h-dvh flex-col bg-bg text-slate-100">
        <Nav />
        <main className="mx-auto w-full max-w-6xl flex-1 px-5 py-6">{children}</main>
      </body>
    </html>
  )
}
