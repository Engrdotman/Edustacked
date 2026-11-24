const CACHE_PREFIX = 'edustacked-static-'
const CACHE_NAME = `${CACHE_PREFIX}v2`
const APP_SHELL = [
  '/',
  '/index.html',
  '/manifest.webmanifest',
  '/icons/edustacked-192.png',
  '/icons/edustacked-512.png',
]
const MAX_STATIC_ENTRIES = 80

async function cacheBuiltAssets(cache) {
  try {
    const response = await fetch('/build-manifest.json', { cache: 'no-store' })
    if (!response.ok) return
    const manifest = await response.json()
    const files = new Set()
    for (const entry of Object.values(manifest)) {
      if (entry.file) files.add(entry.file)
      for (const file of [...(entry.css || []), ...(entry.assets || [])]) files.add(file)
    }
    await Promise.all([...files].map(async (file) => {
      try {
        const request = new Request(`/${file.replace(/^\/+/, '')}`, { cache: 'reload' })
        const asset = await fetch(request)
        if (asset.ok && asset.type === 'basic') await cache.put(request, asset)
      } catch {
        // Keep the installable shell even if one optional chunk is temporarily unavailable.
      }
    }))
  } catch {
    // A build without a manifest still gets the static shell and runtime asset caching.
  }
}

self.addEventListener('install', (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(CACHE_NAME)
      await cache.addAll(APP_SHELL)
      await cacheBuiltAssets(cache)
      await self.skipWaiting()
    })(),
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((names) => Promise.all(names
        .filter((name) => name.startsWith(CACHE_PREFIX) && name !== CACHE_NAME)
        .map((name) => caches.delete(name))))
      .then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', (event) => {
  const request = event.request
  if (request.method !== 'GET') return

  const url = new URL(request.url)
  if (url.origin !== self.location.origin) return
  // Never persist API, authentication, student, payment, or uploaded media responses.
  if (/^\/(api|admin|media)(\/|$)/.test(url.pathname)) return

  if (request.mode === 'navigate') {
    event.respondWith(fetch(request).catch(async () => (
      await caches.match('/index.html') || Response.error()
    )))
    return
  }

  const isBundledAsset = url.pathname.startsWith('/assets/')
  const isInstallAsset = url.pathname.startsWith('/icons/') || url.pathname === '/manifest.webmanifest'
  if (!isBundledAsset && !isInstallAsset) return

  event.respondWith((async () => {
    const cache = await caches.open(CACHE_NAME)
    const cached = await cache.match(request)
    if (cached) return cached
    const response = await fetch(request)
    if (response.ok && response.type === 'basic') {
      await cache.put(request, response.clone())
      const keys = await cache.keys()
      if (keys.length > MAX_STATIC_ENTRIES) {
        await cache.delete(keys[0])
      }
    }
    return response
  })())
})
