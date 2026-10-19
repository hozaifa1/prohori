/* Prohori service worker: caches the app shell only. Never touches /api/* or /health. */
const CACHE = "prohori-shell-v3";
const SHELL = [
  "/",
  "/static/style.css",
  "/static/app.js",
  "/static/icon-192.png",
  "/static/icons.svg",
  "/static/fonts/geist-latin-wght-normal.woff2",
  "/static/fonts/geist-mono-latin-wght-normal.woff2",
  "/manifest.webmanifest",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()).catch(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname === "/health" || url.pathname.startsWith("/docs")) return;
  if (url.pathname.startsWith("/static/samples/")) return;

  // Network first, so a redeploy shows up immediately; cache is the offline fallback.
  event.respondWith(
    fetch(req)
      .then((res) => {
        if (res && res.ok && (SHELL.includes(url.pathname) || req.mode === "navigate")) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req.mode === "navigate" ? "/" : req, copy)).catch(() => {});
        }
        return res;
      })
      .catch(() => caches.match(req).then((hit) => hit || caches.match("/")))
  );
});
