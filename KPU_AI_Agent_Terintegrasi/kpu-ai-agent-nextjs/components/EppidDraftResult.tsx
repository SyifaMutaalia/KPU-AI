'use client';

import { useEffect, useMemo, useRef, useState } from 'react';

export type EppidDraft = {
  informasi_yang_dimohon: string;
  tujuan_penggunaan_informasi: string;
  official_url: string;
  form_url?: string;
  note: string;
  jenis_pemohon?: string;
  cara_memperoleh_informasi?: string;
  cara_memperoleh_salinan?: string;
  format_salinan?: string;
};

// Nilai radio pada formulir resmi subangkabppid.kpu.go.id/formulir-permohonan.
const USERTYPE: Record<string, string> = { Perorangan: '1', 'Kelompok Orang': '2', 'Badan Hukum': '3' };
const INFOGET: Record<string, string> = {
  'Melihat / Membaca / Mendengarkan / Mencatat': '1',
  'Mendapat Salinan Informasi Hardcopy': '2',
  'Mendapat Salinan Informasi Softcopy': '3',
};
const COPYGET: Record<string, string> = { 'Mengambil Langsung': '1', Email: '2', 'Kurir/POS': '3', Faksimili: '4' };
const INFOFORMAT: Record<string, string> = { Tercetak: '1', Terkirim: '2' };

/** Bookmarklet: dijalankan pengguna sendiri di halaman formulir e-PPID setelah login.
 * Hanya mengisi kolom permohonan; kolom identitas tetap diisi pemohon. Tidak menekan Simpan. */
function bookmarklet(draft: EppidDraft): string {
  const data = {
    i: draft.informasi_yang_dimohon,
    p: draft.tujuan_penggunaan_informasi,
    u: USERTYPE[draft.jenis_pemohon ?? ''] ?? '1',
    g: INFOGET[draft.cara_memperoleh_informasi ?? ''] ?? '3',
    c: COPYGET[draft.cara_memperoleh_salinan ?? ''] ?? '2',
    f: INFOFORMAT[draft.format_salinan ?? ''] ?? '2',
  };
  const code = `(function(){var d=${JSON.stringify(data)};`
    + `if(!document.getElementById('information')){alert('Buka halaman Formulir Permohonan e-PPID KPU Subang (setelah login), lalu klik lagi.');return;}`
    + `function t(id,v){var e=document.getElementById(id);if(e&&v){e.value=v;e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));}}`
    + `function r(n,v){var e=document.querySelector('input[name="'+n+'"][value="'+v+'"]');if(e){e.click();}}`
    + `r('usertype',d.u);t('information',d.i);t('purpose',d.p);r('infoget',d.g);r('copyget',d.c);r('infoformat',d.f);`
    + `alert('Draf permohonan terisi. Lengkapi identitas Anda, periksa kembali, lalu tekan Simpan.');})();`;
  return 'javascript:' + encodeURIComponent(code);
}

export default function EppidDraftResult({ draft }: { draft: EppidDraft }) {
  const [copied, setCopied] = useState('');
  const linkRef = useRef<HTMLAnchorElement>(null);
  const href = useMemo(() => bookmarklet(draft), [draft]);
  const formUrl = draft.form_url || draft.official_url;

  // React tidak merender href "javascript:" secara langsung, jadi dipasang lewat DOM.
  useEffect(() => { linkRef.current?.setAttribute('href', href); }, [href]);

  const fields: Array<[string, string]> = [
    ['Jenis Pemohon', draft.jenis_pemohon ?? 'Perorangan'],
    ['Rincian Informasi Yang Dibutuhkan', draft.informasi_yang_dimohon],
    ['Tujuan Penggunaan Informasi', draft.tujuan_penggunaan_informasi || '(tidak disebutkan, isi sendiri bila diperlukan)'],
    ['Cara Memperoleh Informasi', draft.cara_memperoleh_informasi ?? 'Mendapat Salinan Informasi Softcopy'],
    ['Cara Memperoleh Salinan', draft.cara_memperoleh_salinan ?? 'Email'],
    ['Format Salinan Informasi', draft.format_salinan ?? 'Terkirim'],
  ];

  async function copy(label: string, text: string) {
    try { await navigator.clipboard.writeText(text); setCopied(label); window.setTimeout(() => setCopied(''), 1800); }
    catch { setCopied(''); }
  }

  const all = fields.map(([label, value]) => `${label}:\n${value}`).join('\n\n');

  return <div className="draft-result">
    <h2>Isian formulir e-PPID</h2>
    <p className="draft-hint">Urutan sama dengan formulir resmi. Identitas (nama, nomor identitas, kontak, alamat) diisi sendiri di e-PPID.</p>
    {fields.map(([label, value]) => {
      const pasteable = label === 'Rincian Informasi Yang Dibutuhkan' || label === 'Tujuan Penggunaan Informasi';
      return <div className="draft-field" key={label}>
        <div className="draft-field-head"><b>{label}</b>{pasteable && <button onClick={() => void copy(label, value)}>{copied === label ? 'Tersalin ✓' : 'Salin'}</button>}{!pasteable && <span className="draft-choice">pilih opsi ini</span>}</div>
        <p>{value}</p>
      </div>;
    })}
    <div className="draft-actions">
      <a className="draft-primary" href={formUrl} target="_blank" rel="noopener noreferrer">Buka formulir e-PPID</a>
      <button onClick={() => void copy('semua', all)}>{copied === 'semua' ? 'Tersalin ✓' : 'Salin semua'}</button>
    </div>
    <div className="draft-autofill">
      <b>Isi otomatis (komputer)</b>
      <ol>
        <li>Seret tombol di bawah ke bookmark bar browser.</li>
        <li>Login di e-PPID dan buka <i>Formulir Permohonan</i>.</li>
        <li>Klik bookmark tersebut: rincian, tujuan, dan pilihan cara memperoleh terisi otomatis.</li>
      </ol>
      <a ref={linkRef} className="draft-bookmarklet" onClick={(e) => { e.preventDefault(); setCopied('seret'); }} draggable>Isi otomatis e-PPID</a>
      {copied === 'seret' && <small>Jangan diklik di sini — seret tombol ke bookmark bar, lalu klik di halaman e-PPID.</small>}
    </div>
    <p className="draft-note">{draft.note}</p>
  </div>;
}
