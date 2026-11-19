import { NextRequest } from 'next/server';
import { callAdminFastAPI, parseJsonBody } from '@/lib/backend';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

type RouteContext = { params: Promise<{ path: string[] }> };

async function forward(request: NextRequest, context: RouteContext, method: 'GET' | 'POST') {
  const { path } = await context.params;
  const suffix = path.join('/');
  const url = `/api/v1/admin/${suffix}${request.nextUrl.search}`;
  const csrf = method === 'POST';
  return callAdminFastAPI(request, url, {
    method,
    csrf,
    body: method === 'POST' ? await parseJsonBody(request) : undefined,
  });
}

export async function GET(request: NextRequest, context: RouteContext) {
  return forward(request, context, 'GET');
}

export async function POST(request: NextRequest, context: RouteContext) {
  return forward(request, context, 'POST');
}
