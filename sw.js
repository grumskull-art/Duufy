const CACHE_NAME = 'duufy-shell-v4';
const APP_SHELL = [
  '/app',
  '/manifest.json',
  '/icon-192.png',
  '/icon-512.png'
];

function isSameOrigin(url) {
  return url.origin === self.location.origin;
}

function isApiRequest(url) {
  return [
    '/items',
    '/groups',
    '/active-groups',
    '/auth',
    '/ai',
    '/config',
    '/health'
  ].some((prefix) => url.pathname.startsWith(prefix));
}

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const cacheNames = await caches.keys();
    await Promise.all(
      cacheNames
        .filter((name) => name !== CACHE_NAME)
        .map((name) => caches.delete(name))
    );
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  if (request.method !== 'GET' || !isSameOrigin(url)) {
    return;
  }

  if (isApiRequest(url)) {
    event.respondWith(fetch(request));
    return;
  }

  if (request.mode === 'navigate') {
    event.respondWith((async () => {
      try {
        const fresh = await fetch(request);
        const cache = await caches.open(CACHE_NAME);
        cache.put('/app', fresh.clone());
        return fresh;
      } catch {
        return (await caches.match('/app')) || Response.error();
      }
    })());
    return;
  }

  event.respondWith((async () => {
    const cache = await caches.open(CACHE_NAME);
    const cached = await cache.match(request);

    try {
      const fresh = await fetch(request);
      if (fresh.ok && (
        request.destination === 'style' ||
        request.destination === 'script' ||
        request.destination === 'image' ||
        url.pathname.endsWith('.json')
      )) {
        cache.put(request, fresh.clone());
      }
      return fresh;
    } catch {
      return cached || Response.error();
    }
  })());
});
