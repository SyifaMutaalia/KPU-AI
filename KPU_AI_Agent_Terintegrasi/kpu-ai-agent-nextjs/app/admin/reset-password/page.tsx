'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import AdminAuthForms from '@/components/AdminAuthForms';

export default function AdminResetPasswordPage() {
  const [token, setToken] = useState('');
  const [checked, setChecked] = useState(false);
  useEffect(() => {
    const value = new URLSearchParams(window.location.hash.slice(1)).get('token') || '';
    window.history.replaceState(null, '', window.location.pathname);
    setToken(value);
    setChecked(true);
  }, []);
  if (!checked) return <main className="auth-page"><p role="status">Memeriksa tautan reset...</p></main>;
  if (!token) return <main className="auth-page"><section className="auth-card"><h1>Tautan reset tidak valid</h1><p>Gunakan tautan terbaru dari email, atau minta reset ulang.</p><Link href="/admin/forgot-password">Minta reset ulang</Link></section></main>;
  return <AdminAuthForms kind="reset" token={token} />;
}
