"use client";

import dynamic from 'next/dynamic';

const NetworkGraph = dynamic(() => import('@/components/NetworkGraph'), { ssr: false });

export default function Home() {
  return (
    <main>
      <NetworkGraph />
    </main>
  );
}
