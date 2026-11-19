"""Buat backup dan pasang sitasi klik pada Next.js jika anchor asli masih cocok."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
page = root / "kpu-ai-agent-nextjs" / "app" / "page.tsx"
text = page.read_text(encoding="utf-8")
import_line = "import CitationText from '../components/CitationText';"
old = "<div>{m.text}</div>"
new = "<div><CitationText text={m.text} sources={m.sources ?? []} /></div>"
if import_line in text and new in text:
    print("Sitasi inline sudah terpasang.")
elif "import { useEffect, useRef, useState } from 'react';" in text and old in text:
    backup = page.with_suffix(".tsx.bak")
    if not backup.exists():
        backup.write_text(text, encoding="utf-8")
    text = text.replace("import { useEffect, useRef, useState } from 'react';",
                        "import { useEffect, useRef, useState } from 'react';\n" + import_line, 1)
    text = text.replace(old, new, 1)
    page.write_text(text, encoding="utf-8")
    print("Sitasi inline ditambahkan; backup:", backup)
else:
    raise SystemExit("Struktur page.tsx berbeda; belum diubah. Tambahkan CitationText secara manual.")
