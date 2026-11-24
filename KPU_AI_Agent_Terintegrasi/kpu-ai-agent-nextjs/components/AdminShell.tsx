'use client';

import Link from 'next/link';
import ThemeToggle from '@/components/ThemeToggle';
import { usePathname, useRouter } from 'next/navigation';
import { ReactNode, useEffect, useState } from 'react';
import KpuLogo from '@/components/KpuLogo';
import { httpErrorMessage } from '@/lib/httpError';

type Props = { children: ReactNode };

const SEEN_KEY = 'kpu-admin-errors-seen';

export default function AdminShell({ children }: Props) {
  const pathname = usePathname();
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [email, setEmail] = useState('');
  const [csrf, setCsrf] = useState('');
  const [error, setError] = useState('');
  const [n8nStatus, setN8nStatus] = useState('Memeriksa n8n...');
  const [openErrors, setOpenErrors] = useState(0);
  const [latestErrorAt, setLatestErrorAt] = useState<string | null>(null);
  const [seenErrorAt, setSeenErrorAt] = useState<string | null>(null);

  // Alert error cukup dilihat sekali: setelah Error log dibuka atau alert ditutup, alert baru muncul lagi
  // hanya jika ada error yang lebih baru. Penanda disimpan di perangkat admin.
  useEffect(() => {
    try { setSeenErrorAt(localStorage.getItem(SEEN_KEY)); } catch { /* penyimpanan diblokir */ }
  }, []);
  function markErrorsSeen(at: string | null) {
    if (!at) return;
    setSeenErrorAt(at);
    try { localStorage.setItem(SEEN_KEY, at); } catch { /* abaikan */ }
  }
  useEffect(() => { if (pathname.includes('/errors')) markErrorsSeen(latestErrorAt); }, [pathname, latestErrorAt]);
  // Error yang belum dilihat admin: ada error terbuka yang lebih baru dari penanda "sudah dicek".
  const unseenErrors = openErrors > 0 && !!latestErrorAt
    && (!seenErrorAt || new Date(latestErrorAt).getTime() > new Date(seenErrorAt).getTime());
  const hasUnseenErrors = unseenErrors && !pathname.includes('/errors');
  const [menuOpen, setMenuOpen] = useState(false);

  // Tutup sidebar mobile setiap pindah halaman.
  useEffect(() => { setMenuOpen(false); }, [pathname]);

  useEffect(() => {
    if (!email) return;
    let active = true;
    async function poll() {
      try {
        const response = await fetch('/api/admin/dashboard/summary', { cache: 'no-store' });
        if (!response.ok) return;
        const summary = await response.json();
        if (active) { setOpenErrors(Number(summary.open_errors) || 0); setLatestErrorAt(summary.latest_error_at ?? null); }
      } catch { /* alert berikutnya dicoba pada interval berikut */ }
    }
    void poll();
    const timer = window.setInterval(() => { void poll(); }, 60000);
    return () => { active = false; window.clearInterval(timer); };
  }, [email, pathname]);

  useEffect(() => {
    let active = true;
    async function authenticate() {
      try {
        const tokenResponse = await fetch('/api/admin/auth/csrf', { cache: 'no-store' });
        const tokenData = await tokenResponse.json();
        if (!tokenResponse.ok) throw new Error(httpErrorMessage(tokenResponse.status, tokenData));
        const response = await fetch('/api/admin/auth/me', { cache: 'no-store' });
        if (response.status === 401) {
          router.replace('/admin/login');
          return;
        }
        const user = await response.json();
        if (!response.ok) throw new Error(httpErrorMessage(response.status, user));
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
      if (!response.ok) throw new Error(httpErrorMessage(response.status, {}));
      router.replace('/admin/login');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Logout gagal.');
    }
  }

  // Di HP tabel admin tampil sebagai kartu: setiap sel diberi label dari judul kolomnya.
  useEffect(() => {
    const label = () => document.querySelectorAll<HTMLTableElement>('.admin-table').forEach((table) => {
      const heads = Array.from(table.querySelectorAll('thead th')).map((th) => th.textContent?.trim() ?? '');
      table.querySelectorAll('tbody tr').forEach((row) => Array.from(row.children).forEach((cell, index) => {
        if (heads[index] && cell.getAttribute('data-label') !== heads[index]) cell.setAttribute('data-label', heads[index]);
      }));
    });
    label();
    const observer = new MutationObserver(label);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, []);

  if (loading) return <main className="admin-loading" role="status">Memeriksa sesi admin...</main>;
  if (error && !email) return <main className="admin-loading"><p role="alert">{error}</p><Link href="/admin/login">Kembali ke login</Link></main>;

  return (
    <div className={`admin-layout ${menuOpen ? 'menu-open' : ''}`}>
      {menuOpen && <button className="sidebar-backdrop" aria-label="Tutup menu" onClick={() => setMenuOpen(false)} />}
      <aside className="admin-sidebar" id="admin-sidebar">
        <button className="sidebar-close" aria-label="Tutup menu" onClick={() => setMenuOpen(false)}>×</button>
        <Link className="admin-brand" href="/admin/dashboard"><KpuLogo /><span>KPU Admin<small>Monitoring ingestion</small></span></Link>
        <nav aria-label="Navigasi admin">
          <Link className={pathname === '/admin/dashboard' ? 'admin-nav active' : 'admin-nav'} href="/admin/dashboard">Ringkasan</Link>
          <Link className={pathname.includes('/workflows') ? 'admin-nav active' : 'admin-nav'} href="/admin/dashboard/workflows">Workflow n8n</Link>
          <Link className={pathname.includes('/documents') ? 'admin-nav active' : 'admin-nav'} href="/admin/dashboard/documents">Dokumen</Link>
          <Link className={pathname.includes('/errors') ? 'admin-nav active' : 'admin-nav'} href="/admin/dashboard/errors">Error log{unseenErrors && !pathname.includes('/errors') && <span className="nav-badge">{openErrors}</span>}</Link>
        </nav>
        <div className="admin-user"><span>{email}</span><button className="button secondary" onClick={logout}>Keluar</button></div>
      </aside>
      <main className="admin-main">
        <div className="admin-topline">
          <button className="menu-toggle" aria-label="Buka menu" aria-expanded={menuOpen} aria-controls="admin-sidebar" onClick={() => setMenuOpen(true)}><span /><span /><span /></button>
          <div className="admin-n8n-status" role="status">{n8nStatus}</div>
          <ThemeToggle />
        </div>
        {hasUnseenErrors && <div className="admin-alert" role="alert"><b>⚠ {openErrors} error ingestion belum ditangani.</b><span>Workflow n8n melaporkan kegagalan. Periksa detail dan jalankan Retry bila perlu.</span><Link href="/admin/dashboard/errors">Lihat error log</Link><button type="button" className="alert-close" aria-label="Tutup peringatan" title="Tutup" onClick={() => markErrorsSeen(latestErrorAt)}>×</button></div>}
        {error && <div className="error-box" role="alert">{error}</div>}
        {children}
      </main>
    </div>
  );
}
