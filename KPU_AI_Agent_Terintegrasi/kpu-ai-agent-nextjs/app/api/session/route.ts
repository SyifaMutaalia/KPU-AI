import { NextRequest } from 'next/server';
import { callFastAPI } from '@/lib/backend';
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export async function GET(request: NextRequest) {
  return callFastAPI(request, '/api/v1/session');
}
