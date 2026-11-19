'use client';

import { useCallback, useEffect, useState } from 'react';
import AdminShell from '@/components/AdminShell';

type Workflow = { id: string; name: string; active: boolean; updated_at: string | null; tags: string[] };
type Execution = {
  id: string; workflow_id: string; workflow_name: string; status: string;
  mode: string | null; started_at: string | null; stopped_at: string | null;
};
type Monitor = {
  configured: boolean; connected: boolean; message: string;
  workflows: Workflow[]; executions: Execution[];
};

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleString('id-ID') : '—';
}

export default function AdminWorkflows() {
  const [data, setData] = useState<Monitor | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const response = await fetch('/api/admin/dashboard/workflows', { cache: 'no-store' });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || result.error || 'Gagal memuat workflow n8n.');
      setData(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Gagal memuat workflow n8n.');
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  return <AdminShell><div className="admin-content">
    <header className="admin-heading"><div><p className="eyebrow">INTEGRASI LANGSUNG</p><h1>Workflow n8n</h1><p>Daftar workflow dan 100 eksekusi terbaru dibaca langsung dari API n8n. Halaman ini tidak mengubah, menjalankan, atau mengaktifkan workflow.</p></div></header>
    {loading && <p className="admin-state" role="status">Memuat data n8n...</p>}
    {error && <div className="error-box" role="alert">{error}<button onClick={() => void load()}>Coba lagi</button></div>}
    {!loading && !error && data && <>
      <p className={data.connected ? 'auth-notice' : 'error-box'} role={data.connected ? 'status' : 'alert'}>{data.message}</p>
      {data.connected && <>
        <section className="admin-panel">
          <div className="panel-heading"><h2>Semua workflow ({data.workflows.length})</h2></div>
          {data.workflows.length === 0 ? <p className="admin-empty">n8n tidak mengembalikan workflow.</p> : <div className="admin-table-wrap"><table className="admin-table"><thead><tr><th>Workflow</th><th>Status</th><th>Tag</th><th>Terakhir diubah</th></tr></thead>
            <tbody>{data.workflows.map((workflow) => <tr key={workflow.id}><td>{workflow.name}<small>ID: {workflow.id}</small></td><td><span className={`status-pill status-${workflow.active ? 'success' : 'unknown'}`}>{workflow.active ? 'Aktif' : 'Nonaktif'}</span></td><td>{workflow.tags.length ? workflow.tags.join(', ') : '—'}</td><td>{formatDate(workflow.updated_at)}</td></tr>)}</tbody>
          </table></div>}
        </section>
        <section className="admin-panel">
          <div className="panel-heading"><h2>Eksekusi terbaru ({data.executions.length})</h2></div>
          {data.executions.length === 0 ? <p className="admin-empty">Belum ada eksekusi tersedia.</p> : <div className="admin-table-wrap"><table className="admin-table"><thead><tr><th>Waktu mulai</th><th>Workflow</th><th>Execution</th><th>Status</th><th>Mode</th><th>Selesai</th></tr></thead>
            <tbody>{data.executions.map((execution) => <tr key={execution.id}><td>{formatDate(execution.started_at)}</td><td>{execution.workflow_name}<small>{execution.workflow_id}</small></td><td>{execution.id}</td><td><span className={`status-pill status-${execution.status}`}>{execution.status}</span></td><td>{execution.mode || '—'}</td><td>{formatDate(execution.stopped_at)}</td></tr>)}</tbody>
          </table></div>}
        </section>
      </>}
    </>}
  </div></AdminShell>;
}
