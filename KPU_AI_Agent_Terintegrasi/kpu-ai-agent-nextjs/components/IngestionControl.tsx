'use client';

import { FormEvent, useCallback, useEffect, useState } from 'react';
import { adminPost } from '@/lib/adminClient';

type RunResult = { status: string; message: string; n8n_execution_id: string };

/** Admin memicu WF1 n8n: pindai JDIH KPU atau ingest satu PDF resmi. */
export default function IngestionControl({ onStarted }: { onStarted?: () => void }) {
  const [pdfUrl, setPdfUrl] = useState('');
  const [title, setTitle] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  // Hitung mundur jeda 2 menit antar-permintaan ingestion (dari backend).
  const [waitSeconds, setWaitSeconds] = useState(0);
  const refreshCooldown = useCallback(async () => {
    try {
      const response = await fetch('/api/admin/dashboard/ingestion/cooldown', { cache: 'no-store' });
      if (response.ok) setWaitSeconds(Number((await response.json()).retry_after_seconds) || 0);
    } catch { /* abaikan: tombol tetap bisa dicoba */ }
  }, []);
  useEffect(() => { void refreshCooldown(); }, [refreshCooldown]);
  useEffect(() => {
    if (waitSeconds <= 0) return;
    const timer = window.setTimeout(() => setWaitSeconds((value) => Math.max(0, value - 1)), 1000);
    return () => window.clearTimeout(timer);
  }, [waitSeconds]);
  const waitLabel = waitSeconds > 60 ? `${Math.floor(waitSeconds / 60)} menit ${waitSeconds % 60} detik` : `${waitSeconds} detik`;

  async function run(body: { pdf_url?: string; title?: string }) {
    setBusy(true); setNotice(''); setError('');
    try {
      const result = await adminPost<RunResult>('dashboard/ingestion/run', body);
      setNotice(`${result.message} (execution n8n ${result.n8n_execution_id})`);
      setPdfUrl(''); setTitle('');
      setWaitSeconds(120);
      onStarted?.();
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : 'Ingestion gagal dijalankan.';
      if (message.startsWith('Kode 429')) { await refreshCooldown(); }
      else setError(message);
    } finally { setBusy(false); }
  }

  function submitUrl(event: FormEvent) {
    event.preventDefault();
    const url = pdfUrl.trim();
    if (!url) return;
    void run(title.trim() ? { pdf_url: url, title: title.trim() } : { pdf_url: url });
  }

  return <section className="admin-panel ingestion-control">
    <div className="panel-heading"><div><h2>Kontrol ingestion</h2><p>WF1 mengunduh PDF dari JDIH KPU atau JDIH Kabupaten Subang, membaca PDF scan dengan LLM, mengekstrak teks, membuat embedding, lalu menyimpannya ke Pinecone. Status setiap dokumen muncul di tabel di bawah.</p></div></div>
    <div className="ingestion-actions">
      <button className="button primary" disabled={busy || waitSeconds > 0} onClick={() => void run({})}>{busy ? 'Mengirim…' : 'Pindai JDIH sekarang'}</button>
      <form onSubmit={submitUrl} className="ingestion-url">
        <input value={pdfUrl} onChange={(event) => setPdfUrl(event.target.value)} placeholder="https://jdih.kpu.go.id/data/data_pkpu/....pdf" maxLength={2048} aria-label="URL PDF resmi" />
        <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Judul dokumen (opsional), mis. Peraturan Bupati Subang Nomor 18 Tahun 2026" maxLength={500} aria-label="Judul dokumen" />
        <button className="button secondary" type="submit" disabled={busy || waitSeconds > 0 || !pdfUrl.trim()}>Ingest PDF ini</button>
      </form>
    </div>
    {waitSeconds > 0 && <p className="ingestion-wait" role="status">⏳ Ingestion baru saja dijalankan. Tombol bisa dipakai lagi dalam <b>{waitLabel}</b>.</p>}
    {notice && <p className="auth-notice" role="status">{notice}</p>}
    {error && <div className="error-box" role="alert">{error}</div>}
  </section>;
}
