'use client';

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
  // Tanpa tautan: atur ulang dengan email + kode verifikasi 6 digit dari email.
  return <AdminAuthForms kind="reset" token={token || undefined} />;
}
