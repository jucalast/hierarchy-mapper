import './globals.css';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Hierarchy Mapper',
  description: 'Enterprise visual hierarchy and supply chain network mapper',
};

import Footer from '@/components/layout/Footer';
import { Providers } from './providers';

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="pt-br">
      <head>
        <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Google+Symbols:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200" />
        <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Google+Sans:wght@400;500;700&family=Inter:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500;700&display=swap" />
      </head>
      <body>
        <Providers>
          <div style={{ height: 'calc(100vh - 24px)', overflow: 'hidden', position: 'relative' }}>
            {children}
          </div>
          <Footer />
        </Providers>
      </body>
    </html>
  );
}
