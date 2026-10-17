// Rhymer service worker. __VERSION__ is replaced by build_static.py with a content hash, so any change
// to the app shell or data produces a new cache and old caches are deleted on activate.
const VERSION = "__VERSION__";
const CACHE = "rhymer-" + VERSION, FONTS = "rhymer-fonts";
const ASSETS = __ASSETS__;  // relative to the SW scope (/rhyme-app/)
self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS.map(a => new Request(a, {cache: "reload"})))).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k.startsWith("rhymer-") && k !== CACHE && k !== FONTS).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener("message", e => { if (e.data === "version") e.source.postMessage({version: VERSION}); });
self.addEventListener("fetch", e => {
  const req = e.request; if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin === location.origin) {
    // navigations: serve cached shell (ignoring ?w= query) so the app opens offline
    const key = req.mode === "navigate" ? new URL("./", self.registration.scope).href : req;
    e.respondWith(caches.open(CACHE).then(c => c.match(key, {ignoreSearch: req.mode === "navigate"}).then(hit => hit || fetch(req).then(r => {
      if (r.ok && url.pathname.startsWith(new URL(self.registration.scope).pathname)) c.put(req, r.clone()); return r;
    }))));
  } else if (/fonts\.(googleapis|gstatic)\.com$/.test(url.hostname)) {
    e.respondWith(caches.open(FONTS).then(c => c.match(req).then(hit => {
      const net = fetch(req).then(r => { if (r.ok || r.type === "opaque") c.put(req, r.clone()); return r; }).catch(() => hit);
      return hit || net;
    })));
  }
});
