type Source = { title: string; url: string; kind?: string; note?: string | null };

/** Mengubah [1], [2], dst menjadi tautan yang jelas ke sumber resmi.
 * Referensi internal [D1] tetap teks karena belum ada URL terverifikasi.
 */
export default function CitationText({ text, sources }: { text: string; sources: Source[] }) {
  return <>
    {text.split(/(\[\d+\])/g).map((piece, i) => {
      const match = /^\[(\d+)\]$/.exec(piece);
      const source = match ? sources[Number(match[1]) - 1] : undefined;
      return source ? (
        <a key={i} href={source.url} target="_blank" rel="noopener noreferrer" title={source.title}>
          {piece}
        </a>
      ) : <span key={i}>{piece}</span>;
    })}
  </>;
}
