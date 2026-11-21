'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import AdminShell from '@/components/AdminShell';
import { httpErrorMessage } from '@/lib/httpError';

type Summary = {
  documents: Record<string, number>;
  indexed_chunks: number | null;
  indexed_pasal: number | null;
  last_sync: string | null;
  workflows: Record<string, { status: string; last_execution_at: string | null }>;
  activities: { type: string; workflow: string; status: string; at: string | null; execution_id: string }[];
  open_errors: number;
  latest_error_at: string | null;
};
type N8nMonitor = {
  configured: boolean;
  connected: boolean;
  message: string;
  workflows: { id: string; name: string; active: boolean; updated_at: string | null; tags: string[] }[];
  executions: { id: string; workflow_id: string; workflow_name: string; status: string; mode: string | null; started_at: string | null; stopped_at: string | null }[];
};

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleString('id-ID') : 'Belum tersedia';
}

export default function AdminDashboard() {
  const [data, setData] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [n8n, setN8n] = useState<N8nMonitor | null>(null);
  const [n8nError, setN8nError] = useState('');
  useEffect(() => {
    let active = true;
    fetch('/api/admin/dashboard/summary', { cache: 'no-store' })
      .then(async (response) => {
        const result = await response.json();
        if (!response.ok) throw new Error(httpErrorMessage(response.status, result));
        if (active) setData(result);
      })
      .catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : 'Gagal memuat ringkasan.'); })
      .finally(() => { if (active) setLoading(false); });
    fetch('/api/admin/dashboard/workflows', { cache: 'no-store' })
      .then(async (response) => {
        const result = await response.json();
        if (!response.ok) throw new Error(httpErrorMessage(response.status, result));
        if (active) setN8n(result);
      })
      .catch((reason: unknown) => { if (active) setN8nError(reason instanceof Error ? reason.message : 'Gagal memuat data n8n.'); });
    return () => { active = false; };
  }, []);

  const metrics = [
    ['Total dokumen', data?.documents.total ?? 0],
    ['Dokumen sukses', data?.documents.success ?? 0],
    ['Pending', data?.documents.pending ?? 0],
    ['Processing', data?.documents.processing ?? 0],
    ['Failed', data?.documents.failed ?? 0],
  ];

  return <AdminShell>
    <div className="admin-content">
      <header className="admin-heading"><div><p className="eyebrow">MONITORING</p><h1>Ringkasan sistem</h1><p>Status operasional ingestion dokumen dan workflow.</p></div></header>
      {loading && <p className="admin-state" role="status">Memuat metrik...</p>}
      {error && <div className="error-box" role="alert">{error}</div>}
      {!loading && !error && data && <>
        <section className="admin-panel">
          <div className="panel-heading"><div><h2>Workflow n8n</h2><p>{n8n?.message || n8nError || 'Memuat koneksi n8n...'}</p></div><Link href="/admin/dashboard/workflows">Lihat semua</Link></div>
          {n8nError && <div className="error-box" role="alert">{n8nError}</div>}
          {n8n?.connected && <>
            <div className="workflow-grid">{n8n.workflows.slice(0, 8).map((workflow) =>
              <article className="workflow-card" key={workflow.id}><b>{workflow.name}</b><span className={`status-pill status-${workflow.active ? 'success' : 'unknown'}`}>{workflow.active ? 'Aktif' : 'Nonaktif'}</span><small>Diubah: {formatDate(workflow.updated_at)}</small></article>,
            )}</div>
            <div className="panel-heading"><h3>Eksekusi terbaru</h3></div>
            {n8n.executions.length === 0 ? <p className="admin-empty">Belum ada data eksekusi dari n8n.</p> : <div className="activity-list">{n8n.executions.slice(0, 5).map((item) =>
              <article className="activity-row" key={item.id}><div><b>{item.workflow_name}</b><span>Execution {item.id}</span></div><span className={`status-pill status-${item.status}`}>{item.status}</span><time>{formatDate(item.started_at)}</time></article>,
            )}</div>}
          </>}
        </section>
        <section className="metric-grid" aria-label="Metrik dokumen">
          {metrics.map(([label, value]) => <article className="metric-card" key={label}><span>{label}</span><strong>{value}</strong></article>)}
        </section>
        <section className="metric-grid metric-grid-secondary">
          <article className="metric-card"><span>Chunk terkonfirmasi Pinecone</span><strong>{data.indexed_chunks ?? '—'}</strong></article>
          <article className="metric-card"><span>Pasal terindeks (jika tercatat)</span><strong>{data.indexed_pasal ?? '—'}</strong></article>
          <article className="metric-card"><span>Sinkronisasi terakhir</span><strong className="metric-date">{formatDate(data.last_sync)}</strong></article>
          <article className={`metric-card ${data.open_errors ? 'metric-alert' : ''}`}><span>Error belum ditangani</span><strong>{data.open_errors}</strong></article>
        </section>
        <section className="admin-panel">
          <div className="panel-heading"><h2>Status ingestion tercatat</h2><Link href="/admin/dashboard/errors">Lihat error</Link></div>
          <div className="workflow-grid">{['WF1', 'WF2'].map((name) => {
            const workflow = data.workflows[name];
            return <article className="workflow-card" key={name}><b>{name}</b><span className={`status-pill status-${workflow?.status || 'unknown'}`}>{workflow?.status || 'unknown'}</span><small>Aktivitas: {formatDate(workflow?.last_execution_at || null)}</small></article>;
          })}</div>
        </section>
        <section className="admin-panel">
          <div className="panel-heading"><h2>Aktivitas terbaru</h2><Link href="/admin/dashboard/documents">Daftar dokumen</Link></div>
          {data.activities.length === 0 ? <p className="admin-empty">Belum ada data aktivitas dari PostgreSQL.</p> : <div className="activity-list">{data.activities.map((item, index) =>
            <article className="activity-row" key={`${item.execution_id}-${index}`}><div><b>{item.workflow}</b><span>{item.type === 'error' ? 'Error' : 'Eksekusi'}</span></div><span className={`status-pill status-${item.status}`}>{item.status}</span><time>{formatDate(item.at)}</time></article>,
          )}</div>}
        </section>
      </>}
    </div>
  </AdminShell>;
}
