const CACHE_NAME = "carga-coche-shell-v2";
// Relative to the service worker's own scope, so this works whether the
// app is served at the domain root or under a subpath (e.g. GitHub Pages'
// https://<user>.github.io/<repo>/).
const SHELL_FILES = [
  "./",
  "./index.html",
  "./css/styles.css",
  "./js/calculator.js",
  "./js/api.js",
  "./js/app.js",
  "./manifest.webmanifest",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_FILES))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // Never cache API calls: this is live charging/cost data. Only relevant
  // when a backend is actually present (see api.js:detectApi()).
  if (url.pathname.includes("/api/")) {
    return;
  }

  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request))
  );
});
