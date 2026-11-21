import { Fragment, ReactNode } from 'react';

type Source = { title: string; url: string; kind?: string; note?: string | null };

/**
 * Menampilkan jawaban agent tanpa simbol markdown mentah.
 * **tebal** → huruf tebal, *miring* → huruf miring, daftar "- " / "1. " → daftar,
 * judul "### " → subjudul, dan [1], [2] → tautan ke sumber rujukan.
 * Tidak memakai dangerouslySetInnerHTML: semua teks dirender sebagai node React.
 */
export default function RichText({ text, sources }: { text: string; sources: Source[] }) {
  const blocks = toBlocks(text);
  return <div className="rich-text">{blocks.map((block, i) => renderBlock(block, i, sources))}</div>;
}

type Block =
  | { kind: 'p'; lines: string[] }
  | { kind: 'h'; text: string }
  | { kind: 'ul'; items: string[] }
  | { kind: 'ol'; items: string[] };

function toBlocks(text: string): Block[] {
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  const flush = () => { if (paragraph.length) { blocks.push({ kind: 'p', lines: paragraph }); paragraph = []; } };
  for (const raw of text.replace(/\r\n/g, '\n').split('\n')) {
    const line = raw.trimEnd();
    if (!line.trim()) { flush(); continue; }
    const heading = /^\s{0,3}#{1,6}\s+(.*)$/.exec(line);
    const bullet = /^\s*(?:[-*•])\s+(.*)$/.exec(line);
    const numbered = /^\s*\d+[.)]\s+(.*)$/.exec(line);
    if (heading) { flush(); blocks.push({ kind: 'h', text: heading[1] }); continue; }
    if (bullet || numbered) {
      flush();
      const kind: 'ul' | 'ol' = bullet ? 'ul' : 'ol';
      const item = (bullet ?? numbered)![1];
      const last = blocks[blocks.length - 1];
      if (last && last.kind === kind) last.items.push(item);
      else blocks.push(kind === 'ul' ? { kind: 'ul', items: [item] } : { kind: 'ol', items: [item] });
      continue;
    }
    // Baris lanjutan dari butir daftar (diindentasi) digabung ke butir terakhir.
    const last = blocks[blocks.length - 1];
    if (!paragraph.length && /^\s{2,}\S/.test(raw) && last && (last.kind === 'ul' || last.kind === 'ol')) {
      last.items[last.items.length - 1] += ' ' + line.trim();
      continue;
    }
    paragraph.push(line);
  }
  flush();
  return blocks;
}

function renderBlock(block: Block, key: number, sources: Source[]): ReactNode {
  if (block.kind === 'h') return <p key={key} className="rich-heading"><strong>{inline(block.text, sources)}</strong></p>;
  if (block.kind === 'ul') return <ul key={key}>{block.items.map((item, i) => <li key={i}>{inline(item, sources)}</li>)}</ul>;
  if (block.kind === 'ol') return <ol key={key}>{block.items.map((item, i) => <li key={i}>{inline(item, sources)}</li>)}</ol>;
  return <p key={key}>{block.lines.map((line, i) => <Fragment key={i}>{i > 0 && <br />}{inline(line, sources)}</Fragment>)}</p>;
}

// Urutan penting: tautan markdown, sitasi, tebal, miring, kode.
const TOKEN = /(\[[^\]]+\]\(https:\/\/[^)\s]+\)|\[\d+\]|\*\*[^*]+?\*\*|__[^_]+?__|\*[^*\s][^*]*?\*|`[^`]+`)/g;

function inline(text: string, sources: Source[]): ReactNode[] {
  return text.split(TOKEN).filter(Boolean).map((piece, i) => {
    const link = /^\[([^\]]+)\]\((https:\/\/[^)\s]+)\)$/.exec(piece);
    if (link) return <a key={i} href={link[2]} target="_blank" rel="noopener noreferrer">{link[1]}</a>;
    const cite = /^\[(\d+)\]$/.exec(piece);
    if (cite) {
      const source = sources[Number(cite[1]) - 1];
      return source
        ? <a key={i} className="cite" href={source.url} target="_blank" rel="noopener noreferrer" title={source.title}>[{cite[1]}]</a>
        : <span key={i}>{piece}</span>;
    }
    if (/^(\*\*|__)/.test(piece)) return <strong key={i}>{inline(piece.slice(2, -2), sources)}</strong>;
    if (/^\*/.test(piece)) return <em key={i}>{inline(piece.slice(1, -1), sources)}</em>;
    if (/^`/.test(piece)) return <code key={i}>{piece.slice(1, -1)}</code>;
    // Sisa bintang yang tidak berpasangan tidak ditampilkan.
    return <span key={i}>{piece.replace(/\*{1,3}/g, '')}</span>;
  });
}
