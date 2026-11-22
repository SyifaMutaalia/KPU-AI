import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = {
  title: 'KPU AI Agent Kepemiluan',
  description: 'Asisten informasi kepemiluan berbasis sumber resmi.',
};
// Terapkan tema tersimpan sebelum halaman tampil, agar tidak berkedip terang lalu gelap.
const themeScript = "try{var t=localStorage.getItem('kpu-theme');if(t==='dark'||t==='light')document.documentElement.dataset.theme=t}catch(e){}";
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="id" suppressHydrationWarning><head><script dangerouslySetInnerHTML={{ __html: themeScript }} /></head><body>{children}</body></html>;
}
