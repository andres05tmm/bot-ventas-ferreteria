// Service Worker — Ferretería Punto Rojo Dashboard
// Estrategia: Network First para la API, Cache First para assets estáticos

const CACHE_NAME = 'puntorojo-v1'

// Assets que se cachean al instalar
const PRECACHE = [
  '/',
  '/manifest.json',
]

// ── Instalación ──────────────────────────────────────────────────────────────
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(PRECACHE))
      .then(() => self.skipWaiting())
  )
})

// ── Activación ───────────────────────────────────────────────────────────────
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  )
})

// ── Fetch ────────────────────────────────────────────────────────────────────
self.addEventListener('fetch', event => {
  const { request } = event
  const url = new URL(request.url)

  // Requests a la API → siempre red (datos en tiempo real)
  if (
    url.pathname.startsWith('/ventas') ||
    url.pathname.startsWith('/caja') ||
    url.pathname.startsWith('/chat') ||
    url.pathname.startsWith('/gastos') ||
    url.pathname.startsWith('/compras') ||
    url.pathname.startsWith('/inventario') ||
    url.pathname.startsWith('/catalogo') ||
    url.pathname.startsWith('/kardex') ||
    url.pathname.startsWith('/resultados') ||
    url.pathname.startsWith('/historico') ||
    url.pathname.startsWith('/clientes') ||
    url.pathname.startsWith('/api')
  ) {
    event.respondWith(
      fetch(request).catch(() =>
        new Response(JSON.stringify({ error: 'Sin conexión' }), {
          headers: { 'Content-Type': 'application/json' },
        })
      )
    )
    return
  }

  // Assets estáticos (JS, CSS, imágenes) → Cache First, fallback a red
  if (
    url.pathname.startsWith('/assets/') ||
    url.pathname.startsWith('/icons/')  ||
    url.pathname === '/manifest.json'
  ) {
    event.respondWith(
      caches.match(request).then(cached => {
        if (cached) return cached
        return fetch(request).then(response => {
          // Guardar en cache si la respuesta es válida
          if (response && response.status === 200) {
            const clone = response.clone()
            caches.open(CACHE_NAME).then(cache => cache.put(request, clone))
          }
          return response
        })
      })
    )
    return
  }

  // Todo lo demás (HTML del SPA) → Network First, fallback a cache
  event.respondWith(
    fetch(request)
      .then(response => {
        if (response && response.status === 200) {
          const clone = response.clone()
          caches.open(CACHE_NAME).then(cache => cache.put(request, clone))
        }
        return response
      })
      .catch(() => caches.match('/'))
  )
})
