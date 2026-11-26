import express from 'express'
import { createProxyMiddleware } from 'express-http-proxy'
import { fileURLToPath } from 'url'
import { dirname, join } from 'path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

const app = express()
const PORT = process.env.PORT || 3000
const API_BACKEND = process.env.VITE_API_BASE_URL || 'https://edustacked-production.up.railway.app'

console.log('Starting frontend server...')
console.log(`API Backend: ${API_BACKEND}`)

// Proxy API requests to the backend
app.use('/api', createProxyMiddleware({
  target: API_BACKEND,
  changeOrigin: true,
  pathRewrite: (path) => {
    console.log(`[PROXY] Original path: ${path}`)
    // Keep the full path as-is, the backend expects /api/v1/...
    return path
  },
  onError: (err, req, res) => {
    console.error(`[PROXY ERROR] ${req.method} ${req.path}:`, err.message)
    res.status(502).json({ error: 'API gateway error', details: err.message })
  },
  onProxyRes: (proxyRes, req, res) => {
    console.log(`[PROXY] ${req.method} ${req.path} -> ${proxyRes.statusCode}`)
  },
  logLevel: 'info',
}))

// Serve static files from the dist directory
app.use(express.static(join(__dirname, 'dist'), {
  maxAge: '1h',
  etag: false,
  setHeaders: (res, path) => {
    if (path.endsWith('.html')) {
      res.set('Cache-Control', 'no-cache, no-store, must-revalidate')
      res.set('Pragma', 'no-cache')
      res.set('Expires', '0')
    }
    if (path.endsWith('sw.js')) {
      res.set('Cache-Control', 'no-cache, no-store, must-revalidate')
      res.set('Service-Worker-Allowed', '/')
    }
    if (path.endsWith('manifest.webmanifest')) {
      res.set('Cache-Control', 'no-cache')
    }
  },
}))

// SPA fallback - serve index.html for all non-API and non-static routes
app.get('*', (req, res) => {
  console.log(`[SPA] Serving index.html for: ${req.path}`)
  res.sendFile(join(__dirname, 'dist', 'index.html'), (err) => {
    if (err) {
      console.error(`[SPA ERROR] ${err.message}`)
      res.status(404).send('Not found')
    }
  })
})

const server = app.listen(PORT, '0.0.0.0', () => {
  console.log(`✓ Frontend server running on port ${PORT}`)
  console.log(`✓ API proxy configured for: ${API_BACKEND}`)
  console.log(`✓ Static files served from: ${join(__dirname, 'dist')}`)
})

process.on('SIGTERM', () => {
  console.log('SIGTERM received, shutting down gracefully')
  server.close(() => {
    console.log('Server closed')
    process.exit(0)
  })
})
