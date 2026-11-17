import { NextRequest, NextResponse } from 'next/server';

// BFF: browser hanya berkomunikasi dengan Next.js. Kunci AI tetap ada di FastAPI.
const UPSTREAM_TIMEOUT_MS = 65_000;
const SESSION_COOKIE_NAME = 'kpu_session';

export function checkRequestOrigin(request: NextRequest): NextResponse | null {
  const origin = request.headers.get('origin');
  const configured = process.env.APP_ORIGIN;
  const allowed = configured ? new URL(configured).origin : request.nextUrl.origin;
  if (origin && origin !== allowed) {
    return NextResponse.json({ error: 'Origin tidak diizinkan.' }, { status: 403 });
  }
  return null;
}

export async function callFastAPI(
  request: NextRequest,
  path: string,
  options: { method?: 'GET' | 'POST' | 'DELETE'; body?: unknown; csrf?: boolean } = {},
): Promise<NextResponse> {
  const base = process.env.FASTAPI_BASE_URL;
  if (!base) {
    return NextResponse.json({ error: 'FASTAPI_BASE_URL belum dikonfigurasi.' }, { status: 503 });
  }
  try {
    const url = new URL(path, base.endsWith('/') ? base : `${base}/`);
    const headers = new Headers({ Accept: 'application/json' });
    if (options.body !== undefined) headers.set('Content-Type', 'application/json');
    // Hanya cookie anonim milik backend yang diteruskan, tidak seluruh header browser.
    const cookie = request.cookies.get(SESSION_COOKIE_NAME)?.value;
    if (cookie) headers.set('Cookie', `${SESSION_COOKIE_NAME}=${cookie}`);
    if (options.csrf) {
      const token = request.headers.get('x-csrf-token');
      if (!token) return NextResponse.json({ error: 'Token CSRF belum tersedia. Muat ulang halaman.' }, { status: 403 });
      headers.set('X-CSRF-Token', token);
    }
    const upstream = await fetch(url, {
      method: options.method ?? 'GET',
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      cache: 'no-store',
      redirect: 'manual',
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
    });
    // Hindari redirect keluar ketika terjadi kesalahan konfigurasi upstream.
    if (upstream.status >= 300 && upstream.status < 400) {
      return NextResponse.json({ error: 'Pengalihan dari backend tidak didukung.' }, { status: 502 });
    }
    const body = upstream.status === 204 ? null : await upstream.text();
    const response = new NextResponse(body, {
      status: upstream.status,
      headers: {
        'Content-Type': upstream.headers.get('content-type') || 'application/json; charset=utf-8',
        'Cache-Control': 'no-store',
      },
    });
    // Set-Cookie dari FastAPI harus sampai ke browser pada domain Next.js.
    // Cookie HttpOnly tetap tidak dapat dibaca JavaScript frontend.
    const setCookie = upstream.headers.get('set-cookie');
    if (setCookie) response.headers.set('Set-Cookie', setCookie);
    return response;
  } catch {
    return NextResponse.json({ error: 'FastAPI tidak bisa dihubungi. Periksa URL dan server backend.' }, { status: 502 });
  }
}

export async function parseJsonBody(request: NextRequest): Promise<unknown> {
  try { return await request.json(); } catch { return null; }
}

export function isUuid(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
}
