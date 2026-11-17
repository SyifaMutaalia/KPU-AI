import { NextRequest, NextResponse } from 'next/server';
import { callFastAPI, checkRequestOrigin, parseJsonBody } from '@/lib/backend';
export const runtime = 'nodejs';
export async function POST(request: NextRequest) {
  const denied = checkRequestOrigin(request); if (denied) return denied;
  const data = await parseJsonBody(request);
  if (!data || typeof data !== 'object') return NextResponse.json({ error: 'JSON tidak valid.' }, { status: 400 });
  const body = data as Record<string, unknown>;
  const information_needed = body.information_needed;
  const purpose = body.purpose ?? '';
  if (typeof information_needed !== 'string' || information_needed.trim().length < 10 || information_needed.length > 1000 || typeof purpose !== 'string' || purpose.length > 500) {
    return NextResponse.json({ error: 'Isi informasi minimal 10 dan maksimal 1000 karakter; tujuan maksimal 500 karakter.' }, { status: 400 });
  }
  return callFastAPI(request, '/api/v1/eppid/draft', {
    method: 'POST', csrf: true,
    body: { information_needed: information_needed.trim(), purpose: purpose.trim() },
  });
}
