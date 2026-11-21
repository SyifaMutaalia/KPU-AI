'use client';

import Link from 'next/link';
import { FormEvent, useCallback, useEffect, useState } from 'react';
import AdminShell from '@/components/AdminShell';
import IngestionControl from '@/components/IngestionControl';
import { httpErrorMessage } from '@/lib/httpError';

type DocumentRow = {
  id: string; source_url: string; document_type: string | null; document_number: string | null;
  title: string | null; year: number | null; file_hash: string | null; status: string;
  namespace: string | null; last_processed_at: string | null; chunks_count: number | null;
  pasal_count: number | null; pinecone_confirmed: boolean;
};
type PageData = { items: DocumentRow[]; page: number; page_size: number; total: number };

export default function AdminDocuments() {
  const [data, setData] = useState<PageData | null>(null);
  const [status, setStatus] = useState('');
  const [query, setQuery] = useState('');
  const [submittedQuery, setSubmittedQuery] = useState('');
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    setLoading(true); setError('');
    const params = new URLSearchParams({ page: String(page), page_size: '25' });
    if (status) params.set('status', status);
    if (submittedQuery) params.set('q', submittedQuery);
    try {
      const response = await fetch(`/api/admin/dashboard/documents?${params}`, { cache: 'no-store' });
      const result = await response.json();
      if (!response.ok) throw new Error(httpErrorMessage(response.status, result));
      setData(result);
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Gagal memuat dokumen.'); }
    finally { setLoading(false); }
  }, [page, status, submittedQuery]);
  useEffect(() => { void load(); }, [load]);
  const hasProcessing = Boolean(data?.items.some((row) => row.status === 'processing'));
  useEffect(() => {
    if (!hasProcessing) return;
    const timer = window.setInterval(() => { void load(); }, 15000);
    return () => window.clearInterval(timer);
  }, [hasProcessing, load]);
  function search(event: FormEvent) { event.preventDefault(); setPage(1); setSubmittedQuery(query.trim()); }

  return <AdminShell><div className="admin-content">
    <header className="admin-heading"><div><p className="eyebrow">INGESTION</p><h1>Dokumen</h1><p>Dokumen yang diunduh WF1, jumlah chunk hasil embedding, dan konfirmasi insert Pinecone.</p></div></header>
    <IngestionControl onStarted={() => { window.setTimeout(() => void load(), 5000); }} />
    <form className="admin-filters" onSubmit={search}>
      <label>Status<select value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }}><option value="">Semua</option><option value="pending">Pending</option><option value="processing">Processing</option><option value="success">Sukses</option><option value="failed">Gagal</option></select></label>
      <label className="search-field">Cari<input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Judul, nomor, atau URL" maxLength={200} /></label>
      <button className="button primary" type="submit">Cari</button>
    </form>
    {loading && <p className="admin-state" role="status">Memuat dokumen...</p>}
    {error && <div className="error-box" role="alert">{error}<button onClick={() => void load()}>Coba lagi</button></div>}
    {!loading && !error && data && data.items.length === 0 && <p className="admin-empty">Tidak ada dokumen untuk filter ini.</p>}
    {!loading && !error && data && data.items.length > 0 && <>
      <div className="admin-table-wrap"><table className="admin-table"><thead><tr><th>Dokumen</th><th>Tipe / nomor</th><th>Tahun</th><th>Status DB</th><th>Pinecone</th><th>Namespace</th><th>Chunks / Pasal</th><th>Diproses</th><th>File hash</th></tr></thead>
        <tbody>{data.items.map((row) => <tr key={row.id}>
          <td>{row.source_url ? <Link href={row.source_url} target="_blank" rel="noreferrer">{row.title || row.source_url}</Link> : row.title || row.id}</td>
          <td>{row.document_type || '—'}<small>{row.document_number || '—'}</small></td>
          <td>{row.year ?? '—'}</td>
          <td><span className={`status-pill status-${row.status}`}>{row.status}</span></td>
          <td>{row.pinecone_confirmed ? 'Terkonfirmasi' : 'Belum dikonfirmasi'}</td>
          <td>{row.namespace || '—'}</td>
          <td>{row.chunks_count ?? '—'} / {row.pasal_count ?? '—'}</td>
          <td>{row.last_processed_at ? new Date(row.last_processed_at).toLocaleString('id-ID') : '—'}</td>
          <td className="hash-cell">{row.file_hash || '—'}</td>
        </tr>)}</tbody>
      </table></div>
      <div className="pagination"><span>{data.total} dokumen · Halaman {data.page}</span><div><button className="button secondary" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>Sebelumnya</button><button className="button secondary" disabled={page * data.page_size >= data.total} onClick={() => setPage((value) => value + 1)}>Berikutnya</button></div></div>
    </>}
  </div></AdminShell>;
}
