/** Pesan error yang ramah untuk pengguna, selalu disertai kode HTTP bila ada. */
const MEANING: Record<number, string> = {
  400: 'Permintaan tidak valid',
  401: 'Sesi berakhir atau belum login',
  403: 'Akses ditolak, muat ulang halaman',
  404: 'Data tidak ditemukan',
  409: 'Permintaan bentrok, tunggu sebentar',
  413: 'Isian terlalu panjang',
  422: 'Isian tidak sesuai format',
  429: 'Batas permintaan tercapai, coba lagi sebentar lagi',
  500: 'Terjadi kesalahan di server',
  502: 'Layanan AI tidak merespons',
  503: 'Layanan sedang sibuk atau belum siap',
  504: 'Waktu tunggu habis',
};

function detailText(data: Record<string, unknown>): string {
  const detail = data.error ?? data.detail ?? data.message;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    // Error validasi FastAPI (422) berupa daftar objek {loc, msg}.
    return detail.map(item => (item && typeof item === 'object' && 'msg' in item ? String((item as { msg: unknown }).msg) : String(item))).join('; ');
  }
  return '';
}

export function httpErrorMessage(status: number, data: Record<string, unknown> = {}): string {
  const meaning = MEANING[status] ?? (status >= 500 ? 'Terjadi kesalahan di server' : 'Permintaan gagal');
  const detail = detailText(data);
  return detail && detail !== meaning ? `Kode ${status} · ${meaning}. ${detail}` : `Kode ${status} · ${meaning}.`;
}

/** fetch() melempar TypeError ketika koneksi putus: tidak ada kode HTTP sama sekali. */
export function networkErrorMessage(reason: unknown, fallback: string): string {
  if (reason instanceof TypeError) return 'Tanpa kode HTTP · Koneksi ke server terputus. Periksa internet Anda lalu coba lagi.';
  return reason instanceof Error ? reason.message : fallback;
}

export async function readJson(response: Response): Promise<Record<string, unknown>> {
  let data: Record<string, unknown> = {};
  try { data = await response.json(); } catch { /* respons bukan JSON */ }
  if (!response.ok) throw new Error(httpErrorMessage(response.status, data));
  return data;
}
