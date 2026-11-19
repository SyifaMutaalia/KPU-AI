'use client';

import { useEffect, useRef, useState } from 'react';
import CitationText from '../components/CitationText';
import KpuLogo from '../components/KpuLogo';

type Source = { title: string; url: string };
type ChatMessage = { id: string; role: 'user' | 'assistant'; text: string; sources?: Source[] };
type Conversation = { id: string; title: string; updated_at: string };
type ConversationDetail = Conversation & { messages: Array<{ id: string; role: string; content: string; sources: Source[] }> };
type Draft = { informasi_yang_dimohon: string; tujuan_penggunaan_informasi: string; official_url: string; note: string };

const prompts = [
  ['◷', 'Tahapan & jadwal', 'Temukan tahapan, jadwal, dan program kepemiluan.', 'Apa saja tahapan dan jadwal pemilu yang perlu saya ketahui?'],
  ['▤', 'Aturan kepemiluan', 'Pahami regulasi dan persyaratan yang berlaku.', 'Apa aturan dan persyaratan untuk menjadi badan ad hoc?'],
  ['◎', 'Hak & kewajiban', 'Pelajari hak, kewajiban, dan larangan pemilih.', 'Apa hak dan kewajiban pemilih?'],
  ['↗', 'Permintaan informasi', 'Ketahui jalur resmi untuk permintaan informasi.', 'Bagaimana cara mengajukan permintaan informasi resmi ke KPU?'],
];

async function responseData(response: Response) {
  let data: Record<string, unknown> = {};
  try { data = await response.json(); } catch { /* upstream may not return JSON */ }
  if (!response.ok) {
    const message = data.error ?? data.detail ?? `Permintaan gagal (${response.status})`;
    throw new Error(typeof message === 'string' ? message : `Permintaan gagal (${response.status})`);
  }
  return data;
}

export default function Home() {
  const [prompt, setPrompt] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [view, setView] = useState<'chat' | 'draft'>('chat');
  const [needed, setNeeded] = useState('');
  const [purpose, setPurpose] = useState('');
  const [draft, setDraft] = useState<Draft | null>(null);
  const csrfRef = useRef<string | null>(null);

  async function initialize() {
    const sessionResponse = await fetch('/api/session', { cache: 'no-store' });
    const session = await responseData(sessionResponse);
    if (typeof session.csrf_token !== 'string') throw new Error('Token sesi tidak tersedia.');
    csrfRef.current = session.csrf_token;
    const listResponse = await fetch('/api/conversations', { cache: 'no-store' });
    const list = await responseData(listResponse);
    // JSON arrays are objects in JavaScript; responseData is typed conservatively.
    setConversations(Array.isArray(list) ? list as Conversation[] : []);
  }

  const started = useRef(false);
  useEffect(() => {
    if (started.current) return; // Avoid duplicate anonymous sessions in React Strict Mode.
    started.current = true;
    void initialize().then(() => setReady(true)).catch(e => {
      setError(e instanceof Error ? e.message : 'Sesi gagal diinisialisasi.');
      setReady(false);
    });
  }, []);

  async function refreshConversations() {
    const response = await fetch('/api/conversations', { cache: 'no-store' });
    const list = await responseData(response);
    setConversations(Array.isArray(list) ? list as Conversation[] : []);
  }

  async function send(text = prompt) {
    const question = text.trim();
    if (!question || busy || !ready) return;
    setError(''); setBusy(true); setPrompt('');
    setMessages(old => [...old, { id: `local-${Date.now()}`, role: 'user', text: question }]);
    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfRef.current ?? '' },
        body: JSON.stringify({ message: question, conversation_id: conversationId }),
      });
      const data = await responseData(response);
      setMessages(old => [...old, {
        id: `reply-${Date.now()}`,
        role: 'assistant',
        text: String(data.answer ?? ''),
        sources: Array.isArray(data.sources) ? data.sources as Source[] : [],
      }]);
      if (typeof data.conversation_id === 'string') setConversationId(data.conversation_id);
      await refreshConversations();
    } catch (e) {
      // Avoid inventing an assistant answer when the backend fails.
      setError(e instanceof Error ? e.message : 'Layanan tidak dapat dihubungi.');
    } finally { setBusy(false); }
  }

  async function openConversation(id: string) {
    if (busy) return;
    setError(''); setBusy(true);
    try {
      const response = await fetch(`/api/conversations/${encodeURIComponent(id)}`, { cache: 'no-store' });
      const detail = await responseData(response) as unknown as ConversationDetail;
      setConversationId(detail.id);
      setMessages(detail.messages.map(m => ({ id: m.id, role: m.role === 'user' ? 'user' : 'assistant', text: m.content, sources: m.sources })));
      setView('chat');
    } catch (e) { setError(e instanceof Error ? e.message : 'Riwayat gagal dibuka.'); }
    finally { setBusy(false); }
  }

  function newChat() {
    if (busy) return;
    setView('chat'); setMessages([]); setConversationId(null); setError('');
  }

  async function deleteConversation(id: string) {
    if (busy) return;
    setBusy(true); setError('');
    try {
      const response = await fetch(`/api/conversations/${encodeURIComponent(id)}`, {
        method: 'DELETE', headers: { 'X-CSRF-Token': csrfRef.current ?? '' },
      });
      await responseData(response);
      if (conversationId === id) { setMessages([]); setConversationId(null); }
      await refreshConversations();
    } catch (e) { setError(e instanceof Error ? e.message : 'Riwayat gagal dihapus.'); }
    finally { setBusy(false); }
  }

  async function generateDraft() {
    if (busy || needed.trim().length < 10 || !ready) return;
    setBusy(true); setError(''); setDraft(null);
    try {
      const response = await fetch('/api/eppid/draft', {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfRef.current ?? '' },
        body: JSON.stringify({ information_needed: needed.trim(), purpose: purpose.trim() }),
      });
      setDraft(await responseData(response) as unknown as Draft);
    } catch (e) { setError(e instanceof Error ? e.message : 'Draf tidak bisa dibuat.'); }
    finally { setBusy(false); }
  }

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><KpuLogo /><b>KPU <span>AI Agent</span></b></div>
      <button className="new-chat" onClick={newChat} disabled={busy}>＋　Percakapan baru</button>
      <div className="nav-label">WORKSPACE</div>
      <button className={`nav-item ${view === 'chat' ? 'active' : ''}`} onClick={() => setView('chat')}>◉　Chat Kepemiluan</button>
      <button className={`nav-item ${view === 'draft' ? 'active' : ''}`} onClick={() => setView('draft')}>▤　Draf e-PPID</button>
      <div className="nav-label history-label">RIWAYAT CHAT</div>
      <div className="history-list">
        {conversations.length === 0 ? <div className="history-empty">Belum ada percakapan pada sesi ini.</div> : conversations.map(item => <div className="history-row" key={item.id}>
          <button disabled={busy} title={item.title} className={`history-entry ${conversationId === item.id ? 'selected' : ''}`} onClick={() => void openConversation(item.id)}>{item.title}</button>
          <button disabled={busy} className="history-delete" aria-label={`Hapus ${item.title}`} title="Hapus riwayat" onClick={() => void deleteConversation(item.id)}>×</button>
        </div>)}
      </div>
      <div className="profile"><span className="avatar">P</span><div><b>Pengguna</b><small>Tanpa login · Sesi anonim</small></div></div>
    </aside>
    <main className="main">
      <header className="topbar"><div><b>{view === 'chat' ? 'Chat Kepemiluan' : 'Draf Permohonan e-PPID'}</b><span className="status">{ready ? 'Sesi aktif' : 'Belum terhubung'}</span></div></header>
      <section className="workspace">
        {error && <div className="error-box" role="alert">{error} {!ready && <button onClick={() => { setError(''); void initialize().then(() => setReady(true)).catch(e => setError(e instanceof Error ? e.message : 'Sesi gagal.')); }}>Coba lagi</button>}</div>}
        {view === 'chat' ? <>
          {messages.length === 0 ? <div className="welcome"><span className="eyebrow"><i/> ASISTEN INFORMASI KEPEMILUAN</span><h1>Informasi pemilu,<br/><em>lebih mudah dipahami.</em></h1><p className="intro">Ajukan pertanyaan tentang tahapan dan regulasi kepemiluan. Jawaban berbasis RAG dilengkapi rujukan dokumen resmi yang tersedia.</p><div className="suggestions">{prompts.map(([icon, title, desc, q]) => <button key={title} className="suggestion" disabled={!ready || busy} onClick={() => void send(q)}><b>{icon}　{title}</b><small>{desc}</small></button>)}</div></div> : <div className="chat-log">{messages.map(m => <div key={m.id} className={`message ${m.role}`}>{m.role === 'assistant' && <KpuLogo small />}<div className="message-body"><div><CitationText text={m.text} sources={m.sources ?? []} /></div>{m.role === 'assistant' && m.sources && m.sources.length > 0 && <div className="sources"><b>Sumber resmi</b>{m.sources.map((s, i) => <a key={`${s.url}-${i}`} href={s.url} target="_blank" rel="noopener noreferrer">{s.title}</a>)}</div>}</div></div>)}{busy && <div className="message assistant"><KpuLogo small /><div>Memproses pertanyaan…</div></div>}</div>}
          <div className="composer-wrap"><form className="composer" onSubmit={e => { e.preventDefault(); void send(); }}><textarea aria-label="Pesan" value={prompt} maxLength={2000} onChange={e => setPrompt(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void send(); } }} placeholder="Tanyakan tentang informasi kepemiluan…" rows={2}/><div className="composer-bottom"><div className="helper-note">Pertanyaan tanpa data pribadi · maksimal 2.000 karakter</div><button className="send" disabled={!ready || busy || !prompt.trim()} aria-label="Kirim">↑</button></div></form><p className="disclaimer">AI dapat membuat kesalahan. Verifikasi informasi penting melalui sumber resmi KPU.</p></div>
        </> : <div className="draft-view"><span className="eyebrow"><i/> PERSIAPAN PERMOHONAN INFORMASI</span><h1>Draf e-PPID</h1><p className="intro">Isi kebutuhan informasimu. AI hanya menyiapkan teks yang dapat disalin. Permohonan harus tetap dikirim melalui kanal e-PPID resmi.</p><label>Informasi yang ingin dimohon<textarea value={needed} maxLength={1000} onChange={e => setNeeded(e.target.value)} placeholder="Contoh: Rekapitulasi hasil Pemilu 2024 tingkat Kabupaten Subang"/></label><label>Tujuan penggunaan (opsional)<textarea value={purpose} maxLength={500} onChange={e => setPurpose(e.target.value)} placeholder="Contoh: Bahan penelitian akademik"/></label><p className="disclaimer">Jangan masukkan NIK, nomor telepon, email, atau identitas pribadi.</p><button className="auth-submit" disabled={!ready || busy || needed.trim().length < 10} onClick={() => void generateDraft()}>{busy ? 'Menyusun draf…' : 'Buat draf isian'}</button>{draft && <div className="draft-result"><h2>Hasil draf</h2><b>Informasi yang dimohon</b><p>{draft.informasi_yang_dimohon}</p><button onClick={() => void navigator.clipboard.writeText(draft.informasi_yang_dimohon)}>Salin isian</button><b>Tujuan penggunaan informasi</b><p>{draft.tujuan_penggunaan_informasi || '(belum diberikan)'}</p><button onClick={() => void navigator.clipboard.writeText(draft.tujuan_penggunaan_informasi)}>Salin tujuan</button><p>{draft.note}</p><a href={draft.official_url} target="_blank" rel="noopener noreferrer">Buka e-PPID resmi</a></div>}</div>}
      </section>
    </main>
  </div>;
}
