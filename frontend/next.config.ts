import type { NextConfig } from 'next';

const apiBase = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

const securityHeaders = [
  { key: 'X-Content-Type-Options', value: 'nosniff' },
  { key: 'X-Frame-Options', value: 'SAMEORIGIN' },
  { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
  {
    key: 'Permissions-Policy',
    value: 'camera=(), microphone=(), geolocation=()',
  },
];

const nextConfig: NextConfig = {
  // Compressão Brotli/Gzip para responses do Next
  compress: true,

  // Reduz JS no client e headers de poweredBy
  poweredByHeader: false,

  // Strict mode — captura side-effects em dev
  reactStrictMode: true,

  // Imagens otimizadas — Linkedin/Pipedrive/Outlook
  images: {
    formats: ['image/avif', 'image/webp'],
    deviceSizes: [320, 480, 640, 750, 828, 1080, 1200, 1920],
    imageSizes: [16, 24, 32, 48, 64, 96, 128, 256],
    minimumCacheTTL: 60 * 60 * 24, // 1 dia
    remotePatterns: [
      { protocol: 'https', hostname: '**.licdn.com' },
      { protocol: 'https', hostname: '**.pipedrive.com' },
      { protocol: 'https', hostname: 'media.licdn.com' },
      { protocol: 'https', hostname: 'logo.clearbit.com' },
      { protocol: 'https', hostname: '**.googleusercontent.com' },
      { protocol: 'https', hostname: '**' }, // permite logos genéricos via clearbit/etc
    ],
  },

  // Otimizações experimentais (Next 15+/16)
  experimental: {
    optimizePackageImports: [
      'lucide-react',
      'reactflow',
      'react-hot-toast',
    ],
  },

  // Proxy para API em dev — evita CORS local
  async rewrites() {
    return [
      {
        source: '/api/proxy/:path*',
        destination: `${apiBase}/api/v1/:path*`,
      },
    ];
  },

  // Cabeçalhos globais de segurança e cache
  async headers() {
    return [
      {
        source: '/:path*',
        headers: securityHeaders,
      },
      {
        // Static assets: cache agressivo + immutable
        source: '/_next/static/:path*',
        headers: [
          {
            key: 'Cache-Control',
            value: 'public, max-age=31536000, immutable',
          },
        ],
      },
      {
        source: '/(.*\\.(?:png|jpg|jpeg|webp|avif|svg|ico|woff2|woff|ttf))',
        headers: [
          {
            key: 'Cache-Control',
            value: 'public, max-age=2592000, stale-while-revalidate=86400',
          },
        ],
      },
    ];
  },
};

export default nextConfig;
