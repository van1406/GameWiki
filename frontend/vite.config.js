import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Dev server proxies /api -> FastAPI so the frontend needs no CORS config in dev.
// The backend port defaults to 8000 (see README); override it in one place with
//   BACKEND_PORT=8001 npm run dev
// if you start uvicorn with a different --port.
const BACKEND_PORT = process.env.BACKEND_PORT || '8000'
// uvicorn binds 127.0.0.1 by default. `localhost` resolves to ::1 FIRST on many
// machines (including this one) while uvicorn only listens on IPv4, so pin the
// target to the address the backend actually listens on.
const BACKEND_HOST = process.env.BACKEND_HOST || '127.0.0.1'
const BACKEND_URL = `http://${BACKEND_HOST}:${BACKEND_PORT}`

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: BACKEND_URL,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
        // When the backend is not running, http-proxy answers with an empty
        // HTTP 500 (text/plain), which the UI can only show as
        // "Request failed (HTTP 500)". Answer with a real JSON body instead so
        // the user gets an actionable message (and the status reflects the
        // real problem: the backend is unavailable, not that we errored).
        configure(proxy) {
          proxy.on('error', (err, req, res) => {
            if (!res || res.headersSent || typeof res.writeHead !== 'function') return
            res.writeHead(503, { 'Content-Type': 'application/json' })
            res.end(
              JSON.stringify({
                detail:
                  `Backend unreachable at ${BACKEND_URL} ` +
                  `(${err.code || err.message}). ` +
                  `Start it with: uvicorn backend.main:app --reload --port ${BACKEND_PORT}`,
              }),
            )
          })
        },
      },
    },
  },
})
