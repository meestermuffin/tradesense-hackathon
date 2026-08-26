import { orders } from '@/lib/alpaca'

export const dynamic = 'force-dynamic'

export async function GET() {
  try {
    return Response.json(await orders())
  } catch (e) {
    return Response.json({ error: String(e) }, { status: 502 })
  }
}
