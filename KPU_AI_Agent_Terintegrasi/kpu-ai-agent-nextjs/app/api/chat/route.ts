import { NextRequest, NextResponse } from 'next/server';
import { callFastAPI, checkRequestOrigin, isUuid, parseJsonBody } from '@/lib/backend';
export const runtime = 'nodejs';
export async function POST(request: NextRequest) {
  const denied = checkRequestOrigin(request); if (denied) return denied;
  const data = await parseJsonBody(request);
  if (!data || typeof data !== 'object') return NextResponse.json({ error: 'JSON tidak valid.' }, { status: 400 });
  const body = data as Record<string, unknown>;
  if (typeof body.message !== 'string' || !body.message.trim() || body.message.length > 2000) {
    return NextResponse.json({ error: 'Pesan harus berisi 1–2000 karakter.' }, { status: 400 });
  }
  if (body.conversation_id != null && (typeof body.conversation_id !== 'string' || !isUuid(body.conversation_id))) {
    return NextResponse.json({ error: 'conversation_id tidak valid.' }, { status: 400 });
  }
  return callFastAPI(request, '/api/v1/chat', {
    method: 'POST', csrf: true,
    body: { message: body.message.trim(), conversation_id: body.conversation_id ?? null },
  });
}
