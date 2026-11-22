'use client';

import Link from 'next/link';
import { FormEvent, useCallback, useState } from 'react';
import { useRouter } from 'next/navigation';
import KpuLogo from '@/components/KpuLogo';
import GoogleLoginButton from '@/components/GoogleLoginButton';
import PasswordInput from '@/components/PasswordInput';
import { httpErrorMessage } from '@/lib/httpError';

type FormKind = 'login' | 'forgot' | 'reset' | 'change';
type Props = { kind: FormKind; token?: string; initialEmail?: string; initialNotice?: string };

async function getCsrf() {
  const response = await fetch('/api/admin/auth/csrf', { cache: 'no-store' });
  const data = await response.json();
  if (!response.ok) throw new Error(httpErrorMessage(response.status, data));
  sessionStorage.setItem('admin-csrf-token', data.csrf_token);
  return data.csrf_token as string;
}

export default function AdminAuthForms({ kind, token, initialEmail = '', initialNotice = '' }: Props) {
  const router = useRouter();
  const [email, setEmail] = useState(initialEmail);
  const [password, setPassword] = useState('');
  const [currentPassword, setCurrentPassword] = useState('');
  const [code, setCode] = useState('');
  const useCode = kind === 'reset' && !token;
  const [notice, setNotice] = useState(initialNotice);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const titles: Record<FormKind, string> = {
    login: 'Masuk Admin',
    forgot: 'Lupa kata sandi',
    reset: 'Atur kata sandi baru',
    change: 'Ganti kata sandi awal',
  };
  const descriptions: Record<FormKind, string> = {
    login: 'Masuk untuk melihat status ingestion dokumen dan error workflow.',
    forgot: 'Jika email terdaftar, kode verifikasi 6 digit dan tautan reset akan dikirim ke email Anda.',
    reset: token ? 'Tautan reset hanya dapat digunakan sekali dan memiliki masa berlaku.' : 'Masukkan email admin dan kode verifikasi 6 digit dari email (berlaku 15 menit).',
    change: 'Penggantian kata sandi wajib dilakukan sebelum mengakses dashboard.',
  };

  const onGoogleLoggedIn = useCallback((result: { csrf_token: string; user: { must_change_password: boolean } }) => {
    sessionStorage.setItem('admin-csrf-token', result.csrf_token);
    router.replace(result.user.must_change_password ? '/admin/change-password' : '/admin/dashboard');
  }, [router]);
  const onGoogleError = useCallback((message: string) => setError(message), []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const csrf = await getCsrf();
      const body = kind === 'login'
        ? { email, password }
        : kind === 'forgot'
          ? { email }
          : kind === 'reset'
            ? (useCode ? { email, code, password } : { token, password })
            : { current_password: currentPassword, new_password: password };
      const endpoint = kind === 'login' ? 'login'
        : kind === 'forgot' ? 'forgot-password'
          : kind === 'reset' ? 'reset-password' : 'change-password';
      const response = await fetch(`/api/admin/auth/${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
        body: JSON.stringify(body),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(httpErrorMessage(response.status, result));
      if (kind === 'login') {
        sessionStorage.setItem('admin-csrf-token', result.csrf_token);
        router.replace(result.user.must_change_password ? '/admin/change-password' : '/admin/dashboard');
        return;
      }
      if (kind === 'change') {
        sessionStorage.setItem('admin-csrf-token', result.csrf_token);
        router.replace('/admin/dashboard');
        return;
      }
      if (kind === 'forgot') {
        // Langsung ke halaman isi kode; email dibawa lewat sessionStorage (tidak ditaruh di URL).
        try { sessionStorage.setItem('admin-reset-email', email); } catch { /* abaikan */ }
        router.push('/admin/reset-password?kode=terkirim');
        return;
      }
      setNotice(result.message || 'Permintaan diterima.');
      setPassword('');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Terjadi kesalahan. Silakan coba kembali.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-card" aria-labelledby="admin-auth-title">
        <div className="auth-brand"><KpuLogo /><span>KPU Admin</span></div>
        <h1 id="admin-auth-title">{titles[kind]}</h1>
        <p>{descriptions[kind]}</p>
        {notice && <p className="auth-notice" role="status">{notice}</p>}
        {error && <p className="error-box" role="alert">{error}</p>}
        <form onSubmit={submit}>
          {kind === 'login' || kind === 'forgot' || useCode ? (
            <label>Email admin<input type="email" autoComplete="email" required maxLength={320} value={email} onChange={(event) => setEmail(event.target.value)} /></label>
          ) : null}
          {useCode ? (
            <label>Kode verifikasi<input inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" required maxLength={6} value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, ''))} placeholder="6 digit" /></label>
          ) : null}
          {kind === 'change' ? (
            <label>Kata sandi saat ini<PasswordInput autoComplete="current-password" required value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} /></label>
          ) : null}
          {kind !== 'forgot' ? (
            <label>{kind === 'login' ? 'Kata sandi' : 'Kata sandi baru'}
              <PasswordInput
                autoComplete={kind === 'login' ? 'current-password' : 'new-password'}
                required minLength={kind === 'login' ? 1 : 12} maxLength={128}
                value={password} onChange={(event) => setPassword(event.target.value)}
              />
            </label>
          ) : null}
          <button className="auth-submit" type="submit" disabled={busy}>{busy ? 'Memproses...' : titles[kind]}</button>
        </form>
        {kind === 'login' && <GoogleLoginButton getCsrf={getCsrf} onLoggedIn={onGoogleLoggedIn} onError={onGoogleError} />}
        <div className="auth-links">
          {kind === 'login' && <Link href="/admin/forgot-password">Lupa kata sandi?</Link>}
          {kind === 'forgot' && <Link href="/admin/reset-password">Sudah menerima kode? Masukkan di sini</Link>}
          {kind === 'reset' && !token && <Link href="/admin/forgot-password">Belum menerima kode? Kirim ulang</Link>}
          {(kind === 'forgot' || kind === 'reset') && <Link href="/admin/login">Kembali ke login</Link>}
        </div>
        <small className="auth-foot">Akses terbatas untuk administrator. Tidak tersedia registrasi publik.</small>
      </section>
    </main>
  );
}
