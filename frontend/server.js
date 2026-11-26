import express from 'express'
import { fileURLToPath } from 'url'
import { dirname, join } from 'path'
import { createProxyMiddleware } from 'express-http-proxy'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

const app = express()
const PORT = process.env.PORT || 3000
const API_BACKEND = process.env.VITE_API_BASE_URL || 'https://edustacked-production.up.railway.app'

// Middleware to log requests
app.use((req, res, next) => {
  console.log(`${req.method} ${req.path}`)
  next()
})

// Proxy API requests to the backend
app.use('/api', createProxyMiddleware({
  target: API_BACKEND,
  changeOrigin: true,
  pathRewrite: { '^/api': '/api' },
  onError: (err, req, res) => {
    console.error('Proxy error:', err)
    res.status(502).json({ error: 'API gateway error' })
  },
  logLevel: 'debug',
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

// SPA fallback - serve index.html for all non-API routes
app.get('*', (req, res) => {
  res.sendFile(join(__dirname, 'dist', 'index.html'))
})

app.listen(PORT, () => {
  console.log(`Frontend server running on port ${PORT}`)
  console.log(`API backend: ${API_BACKEND}`)
})
