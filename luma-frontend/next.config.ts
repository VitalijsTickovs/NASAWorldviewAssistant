import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      { source: '/health', destination: 'https://agent-app.ambitiousground-87c13615.swedencentral.azurecontainerapps.io/health' },
      { source: '/api/:path*', destination: 'https://agent-app.ambitiousground-87c13615.swedencentral.azurecontainerapps.io/api/:path*' },
    ];
  },
};

export default nextConfig;