// Helper sisi browser untuk permintaan admin yang mengubah data (butuh token CSRF).
export async function adminCsrfToken(): Promise<string> {
  const response = await fetch('/api/admin/auth/csrf', { cache: 'no-store' });
  const value = await response.json();
  if (!response.ok) throw new Error(value.detail || value.error || 'Gagal mendapatkan token CSRF.');
  sessionStorage.setItem('admin-csrf-token', value.csrf_token);
  return value.csrf_token as string;
}

export async function adminPost<T>(path: string, body: unknown): Promise<T> {
  const csrf = await adminCsrfToken();
  const response = await fetch(`/api/admin/${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
    body: JSON.stringify(body),
  });
  let result: Record<string, unknown> = {};
  try { result = await response.json(); } catch { /* respons non-JSON */ }
  if (!response.ok) {
    const message = result.detail || result.error || `Permintaan gagal (${response.status}).`;
    throw new Error(typeof message === 'string' ? message : `Permintaan gagal (${response.status}).`);
  }
  return result as T;
}
