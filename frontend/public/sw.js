const CACHE_NAME = 'zubchek-v3-private-reports';
const STATIC_ASSETS = [
  '/',
  '/manifest.json',
  '/icons/icon-192.png',
  '/icons/icon-512.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS);
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      );
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);
  // Never cache API responses, cross-origin photos, or authenticated content.
  if (url.origin !== self.location.origin || url.pathname.startsWith('/api/') ||
      event.request.headers.has('Authorization') || event.request.headers.has('X-Report-Token')) return;
  
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (!response.ok || response.headers.get('Cache-Control')?.includes('no-store')) return response;
        const responseClone = response.clone();
        caches.open(CACHE_NAME).then((cache) => {
          cache.put(event.request, responseClone);
        });
        return response;
      })
      .catch(() => {
        return caches.match(event.request);
      })
  );
});
