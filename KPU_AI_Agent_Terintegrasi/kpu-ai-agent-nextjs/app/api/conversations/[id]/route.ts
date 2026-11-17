import { NextRequest, NextResponse } from 'next/server';
import { callFastAPI, checkRequestOrigin, isUuid } from '@/lib/backend';
export const runtime = 'nodejs';
type RouteContext = { params: Promise<{ id: string }> };
export async function GET(request: NextRequest, context: RouteContext) {
  const { id } = await context.params;
  if (!isUuid(id)) return NextResponse.json({ error: 'ID percakapan tidak valid.' }, { status: 400 });
  return callFastAPI(request, `/api/v1/conversations/${id}`);
}
export async function DELETE(request: NextRequest, context: RouteContext) {
  const denied = checkRequestOrigin(request); if (denied) return denied;
  const { id } = await context.params;
  if (!isUuid(id)) return NextResponse.json({ error: 'ID percakapan tidak valid.' }, { status: 400 });
  return callFastAPI(request, `/api/v1/conversations/${id}`, { method: 'DELETE', csrf: true });
}
