import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = {
  title: 'KPU AI Agent Kepemiluan',
  description: 'Asisten informasi kepemiluan berbasis sumber resmi.',
};
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="id"><body>{children}</body></html>;
}
