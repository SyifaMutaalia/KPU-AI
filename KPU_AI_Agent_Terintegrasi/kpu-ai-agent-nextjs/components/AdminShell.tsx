'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { ReactNode, useEffect, useState } from 'react';
import KpuLogo from '@/components/KpuLogo';

type Props = { children: ReactNode };

export default function AdminShell({ children }: Props) {
  const pathname = usePathname();
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [email, setEmail] = useState('');
  const [csrf, setCsrf] = useState('');
  const [error, setError] = useState('');
  const [n8nStatus, setN8nStatus] = useState('Memeriksa n8n...');

  useEffect(() => {
    let active = true;
    async function authenticate() {
      try {
        const tokenResponse = await fetch('/api/admin/auth/csrf', { cache: 'no-store' });
        const tokenData = await tokenResponse.json();
        if (!tokenResponse.ok) throw new Error(tokenData.detail || tokenData.error || 'Gagal memuat proteksi sesi.');
        const response = await fetch('/api/admin/auth/me', { cache: 'no-store' });
        if (response.status === 401) {
          router.replace('/admin/login');
          return;
        }
        const user = await response.json();
        if (!response.ok) throw new Error(user.detail || 'Tidak dapat memverifikasi akses admin.');
        if (user.must_change_password && pathname !== '/admin/change-password') {
          router.replace('/admin/change-password');
          return;
        }
        if (active) {
          setEmail(user.email);
          setCsrf(tokenData.csrf_token);
          sessionStorage.setItem('admin-csrf-token', tokenData.csrf_token);
          setLoading(false);
          void fetch('/api/admin/dashboard/workflows', { cache: 'no-store' })
            .then(async (monitorResponse) => {
              const monitor = await monitorResponse.json();
              if (!monitorResponse.ok) throw new Error('n8n tidak dapat dihubungi.');
              if (!active) return;
              setN8nStatus(monitor.connected ? 'n8n terhubung' : 'n8n belum dikonfigurasi');
            })
            .catch(() => { if (active) setN8nStatus('n8n tidak tersedia'); });
        }
      } catch (reason) {
        if (active) {
          setError(reason instanceof Error ? reason.message : 'Terjadi kesalahan.');
          setLoading(false);
        }
      }
    }
    void authenticate();
    return () => { active = false; };
  }, [pathname, router]);

  async function logout() {
    setError('');
    try {
      const response = await fetch('/api/admin/auth/logout', {
        method: 'POST',
        headers: { 'X-CSRF-Token': sessionStorage.getItem('admin-csrf-token') || csrf },
      });
      if (!response.ok) throw new Error('Logout gagal. Coba muat ulang halaman.');
      router.replace('/admin/login');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Logout gagal.');
    }
  }

  if (loading) return <main className="admin-loading" role="status">Memeriksa sesi admin...</main>;
  if (error && !email) return <main className="admin-loading"><p role="alert">{error}</p><Link href="/admin/login">Kembali ke login</Link></main>;

  return (
    <div className="admin-layout">
      <aside className="admin-sidebar">
        <Link className="admin-brand" href="/admin/dashboard"><KpuLogo /><span>KPU Admin<small>Monitoring ingestion</small></span></Link>
        <nav aria-label="Navigasi admin">
          <Link className={pathname === '/admin/dashboard' ? 'admin-nav active' : 'admin-nav'} href="/admin/dashboard">Ringkasan</Link>
          <Link className={pathname.includes('/workflows') ? 'admin-nav active' : 'admin-nav'} href="/admin/dashboard/workflows">Workflow n8n</Link>
          <Link className={pathname.includes('/documents') ? 'admin-nav active' : 'admin-nav'} href="/admin/dashboard/documents">Dokumen</Link>
          <Link className={pathname.includes('/errors') ? 'admin-nav active' : 'admin-nav'} href="/admin/dashboard/errors">Error log</Link>
        </nav>
        <div className="admin-user"><span>{email}</span><button className="button secondary" onClick={logout}>Keluar</button></div>
      </aside>
      <main className="admin-main">
        <div className="admin-n8n-status" role="status">{n8nStatus}</div>
        {error && <div className="error-box" role="alert">{error}</div>}
        {children}
      </main>
    </div>
  );
}
