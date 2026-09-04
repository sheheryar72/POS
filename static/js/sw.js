/*
 * Biryani Boss POS — Service Worker
 *
 * Three distinct caching strategies (per app requirement, not a generic
 * PWA template):
 *
 *   1. STATIC_CACHE   — app shell (CSS/JS/icons/login background). Cache-first:
 *                       these are versioned by CACHE_VERSION below and rarely
 *                       change at runtime, so serving from cache is safe and fast.
 *
 *   2. MASTER_CACHE    — read-only reference data the POS needs to function
 *                       offline (currently just GET /api/menu/). Network-first
 *                       with a cache fallback: always try to get the freshest
 *                       menu, but if offline, serve the last-known-good copy
 *                       so the cashier can still take orders.
 *
 *   3. Never cached    — everything else: order placement/sync, kitchen queue,
 *                       history, dashboard, manage-menu CRUD, auth, and the
 *                       HTML pages themselves. These are transactional or
 *                       user/session-specific; serving a stale or
 *                       cross-session cached copy would be a correctness and
 *                       privacy bug, not a convenience. The app's own
 *                       JS (pos.js + posSync.js) is responsible for reading/
 *                       writing IndexedDB when these requests fail offline —
 *                       the service worker does not try to fake these responses.
 */

const CACHE_VERSION = 'bb-pos-v1';
const STATIC_CACHE = `${CACHE_VERSION}-static`;
const MASTER_CACHE = `${CACHE_VERSION}-master`;

const STATIC_ASSETS = [
  '/static/css/pos.css',
  '/static/js/pos.js',
  '/static/js/kitchen.js',
  '/static/js/history.js',
  '/static/js/dashboard.js',
  '/static/js/manage.js',
  '/static/js/idb.js',
  '/static/js/posSync.js',
  '/static/images/login-bg.jpeg',
  '/static/manifest.json',
  '/static/icons/icon-16.png',
  '/static/icons/icon-32.png',
  '/static/icons/icon-72.png',
  '/static/icons/icon-96.png',
  '/static/icons/icon-128.png',
  '/static/icons/icon-144.png',
  '/static/icons/icon-152.png',
  '/static/icons/icon-180.png',
  '/static/icons/icon-192.png',
  '/static/icons/icon-384.png',
  '/static/icons/icon-512.png',
];

const MASTER_DATA_PATHS = ['/api/menu/'];

// Endpoints that must NEVER be served from cache, even as a fallback.
// (Belt-and-suspenders: the fetch handler below already only special-cases
// STATIC_ASSETS and MASTER_DATA_PATHS, so anything not in those lists falls
// through to a plain network passthrough — this list exists to make the
// exclusion explicit and easy to audit.)
const NEVER_CACHE_PREFIXES = [
  '/api/orders/',
  '/api/dashboard/',
  '/api/manage/',
  '/admin/',
  '/login/',
  '/logout/',
];

self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(STATIC_CACHE).then(function (cache) {
      return cache.addAll(STATIC_ASSETS);
    }).then(function () {
      return self.skipWaiting();
    })
  );
});

self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(
        keys
          .filter(function (key) { return key.indexOf(CACHE_VERSION) !== 0; })
          .map(function (key) { return caches.delete(key); })
      );
    }).then(function () {
      return self.clients.claim();
    })
  );
});

function isStaticAsset(url) {
  return STATIC_ASSETS.some(function (path) { return url.pathname === path; });
}

function isMasterData(url) {
  return MASTER_DATA_PATHS.some(function (path) { return url.pathname === path; });
}

function isNeverCache(url) {
  return NEVER_CACHE_PREFIXES.some(function (prefix) { return url.pathname.indexOf(prefix) === 0; });
}

self.addEventListener('fetch', function (event) {
  const request = event.request;
  if (request.method !== 'GET') {
    return; // never intercept POST/DELETE — those go straight to the network
  }

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) {
    return;
  }

  if (isNeverCache(url)) {
    return; // explicit passthrough, no caching involved
  }

  if (isStaticAsset(url)) {
    event.respondWith(
      caches.match(request).then(function (cached) {
        return cached || fetch(request);
      })
    );
    return;
  }

  if (isMasterData(url)) {
    event.respondWith(
      fetch(request)
        .then(function (response) {
          const copy = response.clone();
          caches.open(MASTER_CACHE).then(function (cache) { cache.put(request, copy); });
          return response;
        })
        .catch(function () {
          return caches.match(request, { cacheName: MASTER_CACHE });
        })
    );
    return;
  }

  // Everything else (HTML pages, unlisted paths): plain network passthrough.
  // Not cached, not faked offline — if it fails, it fails visibly.
});
