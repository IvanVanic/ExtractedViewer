const CACHE_NAME = 'vn-cg-viewer-v1';
const THUMBNAIL_CACHE_NAME = 'vn-cg-viewer-thumbnails-v1';
const THUMBNAIL_CACHE_MAX_SIZE = 500;
const NETWORK_TIMEOUT = 5000;

// Files to pre-cache on install
const STATIC_ASSETS = [
  '/',
  '/static/style.css',
  '/static/app.js',
  '/static/manifest.json'
];

/**
 * Install event: pre-cache static assets
 */
self.addEventListener('install', event => {
  console.log('[Service Worker] Installing...');

  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('[Service Worker] Pre-caching static assets');
        return cache.addAll(STATIC_ASSETS);
      })
      .then(() => {
        console.log('[Service Worker] Install complete');
        return self.skipWaiting();
      })
      .catch(error => {
        console.error('[Service Worker] Install failed:', error);
        // Continue with installation even if some assets fail to cache
        return Promise.resolve();
      })
  );
});

/**
 * Activate event: clean up old caches
 */
self.addEventListener('activate', event => {
  console.log('[Service Worker] Activating...');

  event.waitUntil(
    caches.keys()
      .then(cacheNames => {
        return Promise.all(
          cacheNames.map(cacheName => {
            // Delete old caches but keep current versions
            if (
              cacheName !== CACHE_NAME &&
              cacheName !== THUMBNAIL_CACHE_NAME &&
              cacheName.startsWith('vn-cg-viewer')
            ) {
              console.log('[Service Worker] Deleting old cache:', cacheName);
              return caches.delete(cacheName);
            }
          })
        );
      })
      .then(() => {
        console.log('[Service Worker] Activation complete');
        return self.clients.claim();
      })
      .catch(error => {
        console.error('[Service Worker] Activation failed:', error);
      })
  );
});

/**
 * Fetch event: implement caching strategies
 */
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // Only handle GET requests
  if (request.method !== 'GET') {
    return;
  }

  // Handle API requests for thumbnails and previews - cache-first with network fallback
  if (url.pathname.match(/\/api\/images\/.*\/(thumbnail|preview)$/)) {
    event.respondWith(handleThumbnailRequest(request));
    return;
  }

  // Handle other API requests - network-first with timeout and cache fallback
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(handleApiRequest(request));
    return;
  }

  // Handle static assets - cache-first with network fallback
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(handleStaticRequest(request));
    return;
  }

  // Handle everything else - network-first
  event.respondWith(handleNetworkFirstRequest(request));
});

/**
 * Handle thumbnail and preview requests - cache-first strategy
 * Maintains a size-limited cache for offline browsing
 */
async function handleThumbnailRequest(request) {
  const cacheName = THUMBNAIL_CACHE_NAME;

  try {
    // Try to get from cache first
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      console.log('[Service Worker] Thumbnail cache hit:', request.url);
      return cachedResponse;
    }

    // If not in cache, fetch from network
    console.log('[Service Worker] Fetching thumbnail from network:', request.url);
    const networkResponse = await fetchWithTimeout(request, NETWORK_TIMEOUT);

    if (!networkResponse || !networkResponse.ok) {
      return networkResponse || new Response('Thumbnail not found', { status: 404 });
    }

    // Cache the thumbnail response
    const responseToCache = networkResponse.clone();
    cacheWithSizeLimit(cacheName, request, responseToCache);

    return networkResponse;
  } catch (error) {
    console.error('[Service Worker] Thumbnail request failed:', error);

    // Try to return cached version as fallback
    try {
      const cachedResponse = await caches.match(request);
      if (cachedResponse) {
        return cachedResponse;
      }
    } catch (cacheError) {
      console.error('[Service Worker] Cache lookup failed:', cacheError);
    }

    return new Response('Thumbnail request failed', { status: 503 });
  }
}

/**
 * Handle API requests - network-first with timeout
 * Uses cache as fallback if network is slow or fails
 */
async function handleApiRequest(request) {
  try {
    console.log('[Service Worker] Fetching API from network:', request.url);
    const networkResponse = await fetchWithTimeout(request, NETWORK_TIMEOUT);

    if (networkResponse && networkResponse.ok) {
      // Cache successful API responses
      const responseToCache = networkResponse.clone();
      try {
        const cache = await caches.open(CACHE_NAME);
        cache.put(request, responseToCache);
      } catch (cacheError) {
        console.warn('[Service Worker] Failed to cache API response:', cacheError);
      }
      return networkResponse;
    }

    // Network response not ok, try cache
    console.log('[Service Worker] API response not ok, checking cache:', request.url);
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }

    return networkResponse || new Response('API request failed', { status: 503 });
  } catch (error) {
    console.error('[Service Worker] API request failed:', error);

    // Try cache as fallback
    try {
      const cachedResponse = await caches.match(request);
      if (cachedResponse) {
        console.log('[Service Worker] Using cached API response:', request.url);
        return cachedResponse;
      }
    } catch (cacheError) {
      console.error('[Service Worker] Cache lookup failed:', cacheError);
    }

    return new Response('API request failed', { status: 503 });
  }
}

/**
 * Handle static asset requests - cache-first strategy
 */
async function handleStaticRequest(request) {
  try {
    // Try to get from cache first
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      console.log('[Service Worker] Static cache hit:', request.url);
      return cachedResponse;
    }

    // If not in cache, fetch from network
    console.log('[Service Worker] Fetching static asset from network:', request.url);
    const networkResponse = await fetchWithTimeout(request, NETWORK_TIMEOUT);

    if (!networkResponse || !networkResponse.ok) {
      return networkResponse || new Response('Not found', { status: 404 });
    }

    // Cache the response for future use
    const responseToCache = networkResponse.clone();
    try {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, responseToCache);
    } catch (cacheError) {
      console.warn('[Service Worker] Failed to cache static asset:', cacheError);
    }

    return networkResponse;
  } catch (error) {
    console.error('[Service Worker] Static asset request failed:', error);

    // Try to return cached version as fallback
    try {
      const cachedResponse = await caches.match(request);
      if (cachedResponse) {
        return cachedResponse;
      }
    } catch (cacheError) {
      console.error('[Service Worker] Cache lookup failed:', cacheError);
    }

    return new Response('Static asset request failed', { status: 503 });
  }
}

/**
 * Handle network-first requests
 */
async function handleNetworkFirstRequest(request) {
  try {
    console.log('[Service Worker] Fetching from network:', request.url);
    const networkResponse = await fetchWithTimeout(request, NETWORK_TIMEOUT);

    if (networkResponse && networkResponse.ok) {
      return networkResponse;
    }

    // Network response not ok, try cache
    console.log('[Service Worker] Network response not ok, checking cache:', request.url);
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }

    return networkResponse || new Response('Request failed', { status: 503 });
  } catch (error) {
    console.error('[Service Worker] Network request failed:', error);

    // Try cache as fallback
    try {
      const cachedResponse = await caches.match(request);
      if (cachedResponse) {
        console.log('[Service Worker] Using cached response:', request.url);
        return cachedResponse;
      }
    } catch (cacheError) {
      console.error('[Service Worker] Cache lookup failed:', cacheError);
    }

    return new Response('Request failed', { status: 503 });
  }
}

/**
 * Fetch with timeout
 * Rejects if the fetch takes longer than the specified timeout
 */
function fetchWithTimeout(request, timeout = NETWORK_TIMEOUT) {
  return Promise.race([
    fetch(request),
    new Promise((_, reject) =>
      setTimeout(() => reject(new Error('Fetch timeout')), timeout)
    )
  ]);
}

/**
 * Cache with size limit
 * Removes oldest entries when cache exceeds max size
 */
async function cacheWithSizeLimit(cacheName, request, response) {
  try {
    const cache = await caches.open(cacheName);
    const keys = await cache.keys();

    // If we've exceeded the size limit, remove oldest entry
    if (keys.length >= THUMBNAIL_CACHE_MAX_SIZE) {
      console.log('[Service Worker] Thumbnail cache at max size, removing oldest entry');
      const oldestKey = keys[0];
      await cache.delete(oldestKey);
    }

    // Add the new response to cache
    await cache.put(request, response);
  } catch (error) {
    console.error('[Service Worker] Failed to cache with size limit:', error);
  }
}

/**
 * Message handler for cache management
 */
self.addEventListener('message', event => {
  const { type } = event.data;

  if (type === 'SKIP_WAITING') {
    self.skipWaiting();
  } else if (type === 'CLEAR_THUMBNAILS') {
    caches.delete(THUMBNAIL_CACHE_NAME)
      .then(() => {
        console.log('[Service Worker] Thumbnail cache cleared');
        event.ports[0].postMessage({ success: true });
      })
      .catch(error => {
        console.error('[Service Worker] Failed to clear thumbnail cache:', error);
        event.ports[0].postMessage({ success: false, error: error.message });
      });
  } else if (type === 'CLEAR_ALL_CACHES') {
    caches.keys()
      .then(cacheNames => {
        return Promise.all(
          cacheNames.map(name => caches.delete(name))
        );
      })
      .then(() => {
        console.log('[Service Worker] All caches cleared');
        event.ports[0].postMessage({ success: true });
      })
      .catch(error => {
        console.error('[Service Worker] Failed to clear caches:', error);
        event.ports[0].postMessage({ success: false, error: error.message });
      });
  }
});
