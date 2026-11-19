'use client';

import { FormEvent, useState } from 'react';
import { adminPost } from '@/lib/adminClient';

type RunResult = { status: string; message: string; n8n_execution_id: string };

/** Admin memicu WF1 n8n: pindai JDIH KPU atau ingest satu PDF resmi. */
export default function IngestionControl({ onStarted }: { onStarted?: () => void }) {
  const [pdfUrl, setPdfUrl] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  async function run(body: { pdf_url?: string }) {
    setBusy(true); setNotice(''); setError('');
    try {
      const result = await adminPost<RunResult>('dashboard/ingestion/run', body);
      setNotice(`${result.message} (execution n8n ${result.n8n_execution_id})`);
      setPdfUrl('');
      onStarted?.();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Ingestion gagal dijalankan.');
    } finally { setBusy(false); }
  }

  function submitUrl(event: FormEvent) {
    event.preventDefault();
    const url = pdfUrl.trim();
    if (!url) return;
    void run({ pdf_url: url });
  }

  return <section className="admin-panel ingestion-control">
    <div className="panel-heading"><div><h2>Kontrol ingestion</h2><p>WF1 mengunduh PDF dari JDIH KPU, mengekstrak teks, membuat embedding, lalu menyimpannya ke Pinecone. Status setiap dokumen muncul di tabel di bawah.</p></div></div>
    <div className="ingestion-actions">
      <button className="button primary" disabled={busy} onClick={() => void run({})}>{busy ? 'Mengirim…' : 'Pindai JDIH sekarang'}</button>
      <form onSubmit={submitUrl} className="ingestion-url">
        <input value={pdfUrl} onChange={(event) => setPdfUrl(event.target.value)} placeholder="https://jdih.kpu.go.id/data/data_pkpu/....pdf" maxLength={2048} aria-label="URL PDF resmi" />
        <button className="button secondary" type="submit" disabled={busy || !pdfUrl.trim()}>Ingest PDF ini</button>
      </form>
    </div>
    {notice && <p className="auth-notice" role="status">{notice}</p>}
    {error && <div className="error-box" role="alert">{error}</div>}
  </section>;
}
