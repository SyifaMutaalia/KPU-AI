'use client';

import { useEffect, useState } from 'react';

type Theme = 'light' | 'dark';
const KEY = 'kpu-theme';

function systemTheme(): Theme {
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

/** Tombol tema terang/gelap. Pilihan disimpan di perangkat pengguna (localStorage). */
export default function ThemeToggle() {
  const [theme, setTheme] = useState<Theme | null>(null);

  useEffect(() => {
    let saved: string | null = null;
    try { saved = localStorage.getItem(KEY); } catch { /* penyimpanan diblokir */ }
    setTheme(saved === 'dark' || saved === 'light' ? saved : systemTheme());
  }, []);

  function toggle() {
    const next: Theme = theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem(KEY, next); } catch { /* abaikan */ }
    setTheme(next);
  }

  const dark = theme === 'dark';
  return <button type="button" className="theme-toggle" onClick={toggle} aria-pressed={dark}
    aria-label={dark ? 'Ganti ke tema terang' : 'Ganti ke tema gelap'} title={dark ? 'Tema terang' : 'Tema gelap'}>
    <span aria-hidden>{dark ? '☀' : '☾'}</span>{dark ? 'Terang' : 'Gelap'}
  </button>;
}
