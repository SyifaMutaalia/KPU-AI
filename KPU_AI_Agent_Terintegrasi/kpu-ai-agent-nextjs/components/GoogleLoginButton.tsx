'use client';

import { useEffect, useRef, useState } from 'react';
import { httpErrorMessage } from '@/lib/httpError';

type GoogleId = {
  initialize: (options: { client_id: string; callback: (reply: { credential?: string }) => void; ux_mode?: string }) => void;
  renderButton: (element: HTMLElement, options: Record<string, unknown>) => void;
};
declare global { interface Window { google?: { accounts: { id: GoogleId } } } }

const SCRIPT_SRC = 'https://accounts.google.com/gsi/client';

function loadScript(): Promise<void> {
  if (window.google?.accounts?.id) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(`script[src="${SCRIPT_SRC}"]`);
    const script = existing ?? Object.assign(document.createElement('script'), { src: SCRIPT_SRC, async: true, defer: true });
    script.addEventListener('load', () => resolve(), { once: true });
    script.addEventListener('error', () => reject(new Error('Skrip Google gagal dimuat.')), { once: true });
    if (!existing) document.head.appendChild(script);
  });
}

/**
 * Tombol "Masuk dengan Google" untuk admin. Hanya tampil bila backend mengaktifkan GOOGLE_CLIENT_ID.
 * Backend memverifikasi token Google dan hanya menerima email yang sudah terdaftar sebagai admin.
 */
export default function GoogleLoginButton({ getCsrf, onLoggedIn, onError }: {
  getCsrf: () => Promise<string>;
  onLoggedIn: (result: { csrf_token: string; user: { must_change_password: boolean } }) => void;
  onError: (message: string) => void;
}) {
  const box = useRef<HTMLDivElement | null>(null);
  const [enabled, setEnabled] = useState(false);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const config = await (await fetch('/api/admin/auth/google/config', { cache: 'no-store' })).json();
        if (!config?.enabled || !config.client_id || !active) return;
        setEnabled(true);
        await loadScript();
        if (!active || !box.current || !window.google) return;
        window.google.accounts.id.initialize({
          client_id: config.client_id,
          callback: async (reply) => {
            if (!reply.credential) { onError('Login Google dibatalkan.'); return; }
            try {
              const csrf = await getCsrf();
              const response = await fetch('/api/admin/auth/google', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
                body: JSON.stringify({ credential: reply.credential }),
              });
              const result = await response.json();
              if (!response.ok) throw new Error(httpErrorMessage(response.status, result));
              onLoggedIn(result);
            } catch (reason) {
              onError(reason instanceof Error ? reason.message : 'Login Google gagal.');
            }
          },
        });
        window.google.accounts.id.renderButton(box.current, { theme: 'outline', size: 'large', text: 'signin_with', shape: 'pill', width: 320, locale: 'id' });
      } catch { /* login Google tidak tersedia: formulir email/kata sandi tetap bisa dipakai */ }
    })();
    return () => { active = false; };
  }, [getCsrf, onLoggedIn, onError]);

  if (!enabled) return null;
  return <div className="google-login"><span className="google-divider">atau</span><div ref={box} /></div>;
}
