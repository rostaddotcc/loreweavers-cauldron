/* ═══════════ sw.js — The Lore Weaver's Cauldron (2026-09-23) ═══════════
   Konservativ service worker: installbarhet + asset-cache.
   HÅRDA REGLER:
   - navigation requests går ALLTID till nätverket (aldrig stale HTML —
     spelets sidor bär versionerade inline-block; en gammal cache-kopia
     skulle blanda gammal UI med ny backend)
   - /api/ rör ALDRIG (spelstate, tokens, kampanjer)
   - endast same-origin GET + fonts.gstatic.com cachas
   Cache namn-versioneras (v1) — activate rensar gamla. */
'use strict';

var CACHE = 'lwc-assets-v1';
var PRECACHE = [
  '/manifest.webmanifest',
  '/assets/icons/icon-192.png',
  '/assets/icons/icon-512.png',
  '/favicon.ico'
];

self.addEventListener('install', function (e) {
  e.waitUntil(
    caches.open(CACHE).then(function (c) { return c.addAll(PRECACHE); })
      .then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener('activate', function (e) {
  e.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.filter(function (k) { return k !== CACHE; })
        .map(function (k) { return caches.delete(k); }));
    }).then(function () { return self.clients.claim(); })
  );
});

function cacheable(url) {
  if (url.origin !== location.origin && url.hostname !== 'fonts.gstatic.com') return false;
  if (url.pathname.indexOf('/api/') === 0) return false;
  return /\.(css|js|webp|png|jpe?g|svg|ico|woff2?|webmanifest)(\?.*)?$/.test(url.pathname) ||
    url.hostname === 'fonts.gstatic.com';
}

self.addEventListener('fetch', function (e) {
  var req = e.request;
  if (req.method !== 'GET') return;
  // Navigation → nätverket alltid (ingen offline-fallback medvetet)
  if (req.mode === 'navigate') return;
  var url = new URL(req.url);
  if (!cacheable(url)) return;
  // stale-while-revalidate: svara från cache direkt, uppdatera i bakgrunden
  e.respondWith(
    caches.open(CACHE).then(function (cache) {
      return cache.match(req, { ignoreSearch: false }).then(function (hit) {
        var fetched = fetch(req).then(function (res) {
          if (res && res.status === 200 && (res.type === 'basic' || res.type === 'cors')) {
            cache.put(req, res.clone());
          }
          return res;
        }).catch(function () { return hit; });
        return hit || fetched;
      });
    })
  );
});
