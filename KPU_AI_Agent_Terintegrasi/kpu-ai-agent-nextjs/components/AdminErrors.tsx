'use client';

import { useCallback, useEffect, useState } from 'react';
import AdminShell from '@/components/AdminShell';
import { adminCsrfToken } from '@/lib/adminClient';

type ErrorRow = {
  id: string; occurred_at: string; workflow: string; execution_id: string; node: string;
  message: string; status: string; details: string; retry_attempts: number;
};
type PageData = { items: ErrorRow[]; page: number; page_size: number; total: number };

export default function AdminErrors() {
  const [data, setData] = useState<PageData | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const response = await fetch(`/api/admin/dashboard/errors?page=${page}&page_size=25`, { cache: 'no-store' });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || result.error || 'Gagal memuat error log.');
      setData(result);
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Gagal memuat error log.'); }
    finally { setLoading(false); }
  }, [page]);
  useEffect(() => { void load(); }, [load]);

  async function retry(item: ErrorRow) {
    if (!window.confirm(`Minta n8n menjalankan retry untuk ${item.workflow} / execution ${item.execution_id}? Permintaan yang telah dikirim tidak dapat diulang untuk mencegah duplikasi.`)) return;
    setNotice(''); setError('');
    try {
      const csrf = await adminCsrfToken();
      const response = await fetch(`/api/admin/dashboard/errors/${encodeURIComponent(item.id)}/retry`, {
        method: 'POST', headers: { 'X-CSRF-Token': csrf },
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || result.error || 'Retry belum dikonfirmasi.');
      setNotice(result.message || 'n8n menerima retry; hasil masih menunggu konfirmasi.');
      await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Retry gagal.'); }
  }

  return <AdminShell><div className="admin-content">
    <header className="admin-heading"><div><p className="eyebrow">OPERASIONAL</p><h1>Error log</h1><p>Retry hanya mengirim permintaan; status sukses menunggu konfirmasi workflow.</p></div></header>
    {notice && <p className="auth-notice" role="status">{notice}</p>}
    {loading && <p className="admin-state" role="status">Memuat error...</p>}
    {error && <div className="error-box" role="alert">{error}<button onClick={() => void load()}>Coba lagi</button></div>}
    {!loading && !error && data && data.items.length === 0 && <p className="admin-empty">Belum ada error tercatat.</p>}
    {!loading && !error && data && data.items.length > 0 && <>
      <div className="admin-table-wrap"><table className="admin-table"><thead><tr><th>Waktu</th><th>Workflow / execution</th><th>Node</th><th>Pesan</th><th>Status</th><th>Detail</th><th>Aksi</th></tr></thead>
        <tbody>{data.items.map((item) => <tr key={item.id}>
          <td>{new Date(item.occurred_at).toLocaleString('id-ID')}</td>
          <td>{item.workflow}<small>{item.execution_id}</small></td>
          <td>{item.node || '—'}</td>
          <td>{item.message}</td>
          <td><span className={`status-pill status-${item.status}`}>{item.status}</span></td>
          <td><details><summary>Lihat detail</summary><pre className="error-details">{item.details}</pre></details></td>
          <td><button className="button secondary" disabled={!['failed', 'error'].includes(item.status) || item.retry_attempts > 0} onClick={() => void retry(item)}>Retry</button></td>
        </tr>)}</tbody>
      </table></div>
      <div className="pagination"><span>{data.total} error · Halaman {data.page}</span><div><button className="button secondary" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>Sebelumnya</button><button className="button secondary" disabled={page * data.page_size >= data.total} onClick={() => setPage((value) => value + 1)}>Berikutnya</button></div></div>
    </>}
  </div></AdminShell>;
}
