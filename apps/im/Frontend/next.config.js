
/** @type {import('next').NextConfig} */
const nextConfig = {
    // TODO Start: [Student] Enable standalone build
    output: 'standalone',
    // TODO End
    reactStrictMode: false, /* @note: To prevent duplicated call of useEffect */
    // swcMinify: true,

    async headers() {
        return [
            {
                source: '/(.*)',
                headers: [
                    { key: 'X-Content-Type-Options', value: 'nosniff' },
                    { key: 'X-Frame-Options', value: 'SAMEORIGIN' },
                    { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
                ],
            },
        ];
    },

    async rewrites() {
        // 仅在本地开发时生效（NEXT_PUBLIC_API_URL 未设置时）。
        // 生产部署时 nginx 已将 /api/ 代理到后端，Next.js 的 rewrite 不会被触发。
        const backendUrl = (process.env.VIC_BACKEND_URL || 'http://backend:80').replace(/\/$/, '');
        return [{
            source: '/api/:path*',
            destination: `${backendUrl}/api/:path*`,
        }];
    }
};

// eslint-disable-next-line no-undef
module.exports = nextConfig;
