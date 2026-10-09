/* Service worker da Pixelzada. Gerado por scripts/engine/build.py.
   Regra de ouro: matéria nova sempre vem da rede. O cache só entra quando a
   rede falha (sem sinal) ou para o que nunca muda (imagens e fontes). */
const VERSION = "pixelzada-v1";
const STATIC = VERSION + "-static";
const PAGES = VERSION + "-paginas";
const MAX_PAGES = 40;
const PRECACHE = ["/offline.html", "/assets/logo/icon-192.png", "/assets/logo/favicon.svg"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(STATIC).then((c) => c.addAll(PRECACHE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => !k.startsWith(VERSION)).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

function trim(cache) {
  return cache.keys().then((keys) => {
    if (keys.length <= MAX_PAGES) return;
    return cache.delete(keys[0]).then(() => trim(cache));
  });
}

function fromNetworkFirst(request) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 8000);
  return fetch(request, { signal: controller.signal })
    .then((response) => {
      clearTimeout(timer);
      if (response && response.ok) {
        const copy = response.clone();
        caches.open(PAGES).then((c) => c.put(request, copy).then(() => trim(c)));
      }
      return response;
    })
    .catch(() => {
      clearTimeout(timer);
      return caches.match(request).then((hit) => hit || caches.match("/offline.html"));
    });
}

function fromCacheFirst(request) {
  return caches.match(request).then((hit) => {
    if (hit) return hit;
    return fetch(request).then((response) => {
      if (response && response.ok) {
        const copy = response.clone();
        caches.open(STATIC).then((c) => c.put(request, copy));
      }
      return response;
    });
  });
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/ig/")) return;
  if (request.mode === "navigate") {
    event.respondWith(fromNetworkFirst(request));
    return;
  }
  if (url.pathname.startsWith("/assets/")) {
    event.respondWith(fromCacheFirst(request));
  }
});
