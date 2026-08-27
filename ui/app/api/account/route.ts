import { account } from '@/lib/alpaca'

export const dynamic = 'force-dynamic'

export async function GET() {
  try {
    return Response.json(await account())
  } catch (e) {
    return Response.json({ error: String(e) }, { status: 502 })
  }
}
