import './globals.css';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Hierarchy Mapper',
  description: 'Enterprise visual hierarchy and supply chain network mapper',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
