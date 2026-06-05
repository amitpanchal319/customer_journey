/** @type {import('next').NextConfig} */
// Where Next's server-side proxy forwards /api/* calls. In Docker this is set to
// the backend service (e.g. http://api:8000); locally it defaults to the dev API.
// Use 127.0.0.1 (not "localhost"): Node resolves "localhost" to IPv6 ::1 on some
// requests, but uvicorn binds IPv4 only — that mismatch makes the proxy return a
// 500 "Internal Server Error" intermittently. In Docker this is overridden to the
// backend service name via API_PROXY_TARGET.
const API_PROXY_TARGET = process.env.API_PROXY_TARGET || 'http://127.0.0.1:8002'

const nextConfig = {
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${API_PROXY_TARGET}/api/:path*`,
      },
    ]
  },
}

module.exports = nextConfig
