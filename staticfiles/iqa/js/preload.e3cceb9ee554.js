(function() {
    'use strict';

    var CACHE_TTL_MS = 30 * 24 * 60 * 60 * 1000;
    var META_PATH = '/iqa/preload-cache-meta.json';

    var canPreload = (
        'serviceWorker' in navigator
        && 'caches' in window
        && 'fetch' in window
    );
    var workerRegistrationPromise = null;

    function setStatus(card, text) {
        var status = card.querySelector('.preload-status');
        if (status) status.textContent = text;
    }

    function setBusy(card, busy) {
        card.querySelectorAll('[data-preload-action]').forEach(function(btn) {
            btn.disabled = busy;
        });
    }

    function registerWorker() {
        if (!canPreload) {
            return Promise.reject(
                new Error('Browser cache preload is not supported.')
            );
        }
        if (!workerRegistrationPromise) {
            workerRegistrationPromise = navigator.serviceWorker
                .register('/iqa/preload-sw.js')
                .then(function(reg) {
                    var updatePromise = reg.update
                        ? reg.update().catch(function() { return reg; })
                        : Promise.resolve(reg);
                    return updatePromise.then(function() {
                        if (reg.active) return reg;
                        return navigator.serviceWorker.ready;
                    });
                })
                .catch(function(err) {
                    workerRegistrationPromise = null;
                    throw err;
                });
        }
        return workerRegistrationPromise;
    }

    function fetchManifest(card) {
        var manifestUrl = card.dataset.manifestUrl;
        return fetchJson(manifestUrl);
    }

    function fetchJson(url) {
        return fetch(url, {
            credentials: 'same-origin',
            cache: 'no-store'
        }).then(function(response) {
            if (!response.ok) {
                throw new Error('Could not load image list.');
            }
            return response.json();
        });
    }

    function metadataRequest(cacheName) {
        return new Request(
            window.location.origin + META_PATH
            + '?cache=' + encodeURIComponent(cacheName),
            {credentials: 'same-origin'}
        );
    }

    function formatDate(timestamp) {
        if (!timestamp) return 'unknown';
        return new Date(timestamp).toLocaleDateString(
            undefined,
            {year: 'numeric', month: 'short', day: 'numeric'}
        );
    }

    function isExpired(metadata) {
        return !metadata
            || !metadata.expires_at
            || Date.now() > metadata.expires_at;
    }

    function readMetadata(cache, cacheName) {
        return cache.match(metadataRequest(cacheName))
            .then(function(response) {
                if (!response) return null;
                return response.clone().json().catch(function() {
                    return null;
                });
            });
    }

    function writeMetadata(cache, cacheName, manifest, saved, failed, complete) {
        var now = Date.now();
        return readMetadata(cache, cacheName)
            .then(function(existing) {
                if (existing && isExpired(existing)) {
                    existing = null;
                }
                var metadata = {
                    cache_name: cacheName,
                    study_id: manifest.study_id,
                    study_name: manifest.study_name,
                    image_count: manifest.image_count
                        || (manifest.urls || []).length,
                    saved_count: Math.max(
                        saved,
                        existing && existing.saved_count || 0
                    ),
                    failed_count: failed,
                    created_at: existing && existing.created_at || now,
                    expires_at: existing && existing.expires_at
                        || now + CACHE_TTL_MS,
                    ttl_days: 30,
                    complete: !!(
                        complete
                        || existing && existing.complete
                    )
                };
                var response = new Response(JSON.stringify(metadata), {
                    headers: {
                        'Content-Type': 'application/json',
                        'Cache-Control': 'no-store'
                    }
                });
                return cache.put(metadataRequest(cacheName), response)
                    .then(function() {
                        return metadata;
                    });
            });
    }

    function countCachedImages(cache) {
        return cache.keys().then(function(keys) {
            return keys.filter(function(request) {
                var url = new URL(request.url);
                return !(
                    url.origin === window.location.origin
                    && url.pathname === META_PATH
                );
            }).length;
        });
    }

    function cacheExists(cacheName) {
        return caches.keys().then(function(names) {
            return names.indexOf(cacheName) !== -1;
        });
    }

    function cachedStatus(metadata, count) {
        var total = metadata && metadata.image_count
            ? ' / ' + metadata.image_count : '';
        var message = 'Cached ' + count + total + ' images.';
        if (
            metadata
            && metadata.image_count
            && count < metadata.image_count
        ) {
            message += ' Click Preload Images to continue.';
        }
        return message + ' Expires ' + formatDate(metadata.expires_at) + '.';
    }

    function updateCacheStatus(card) {
        if (!canPreload) {
            setStatus(card, 'Browser cache preload is not supported.');
            return Promise.resolve();
        }

        var cacheName = card.dataset.cacheName;
        setStatus(card, 'Checking cache...');
        return registerWorker()
            .then(function() {
                return cacheExists(cacheName);
            })
            .then(function(exists) {
                if (!exists) {
                    setStatus(card, 'No saved images.');
                    return null;
                }
                return caches.open(cacheName)
                    .then(function(cache) {
                        return Promise.all([
                            readMetadata(cache, cacheName),
                            countCachedImages(cache)
                        ]);
                    })
                    .then(function(results) {
                        var metadata = results[0];
                        var count = results[1];

                        if (!metadata && count) {
                            setStatus(
                                card,
                                'Cached ' + count
                                + ' images. Click Preload Images to continue.'
                            );
                            return null;
                        }

                        if (!metadata) {
                            setStatus(card, 'No saved images.');
                            return null;
                        }

                        if (isExpired(metadata)) {
                            return caches.delete(cacheName).then(function() {
                                setStatus(
                                    card,
                                    'Saved images expired. Please preload again.'
                                );
                            });
                        }

                        if (!count) {
                            setStatus(card, 'No saved images.');
                            return null;
                        }

                        setStatus(card, cachedStatus(metadata, count));
                        return null;
                    });
            })
            .catch(function() {
                setStatus(card, 'Could not read cache status.');
            });
    }

    function isSameOrigin(url) {
        return new URL(url, window.location.href).origin
            === window.location.origin;
    }

    function cacheRequest(url) {
        if (isSameOrigin(url)) return url;
        return new Request(url, {
            mode: 'no-cors',
            credentials: 'omit'
        });
    }

    function preloadOne(cache, url) {
        var request = cacheRequest(url);
        return cache.match(request).then(function(cached) {
            if (cached) return 'cached';
            if (typeof request !== 'string') {
                return cache.match(url);
            }
            return null;
        }).then(function(cached) {
            if (cached) return 'cached';
            return fetch(request, {
                cache: 'reload'
            }).then(function(response) {
                if (!response.ok && response.type !== 'opaque') {
                    throw new Error('Image download failed.');
                }
                return cache.put(request, response.clone()).then(function() {
                    return 'downloaded';
                });
            });
        });
    }

    function preloadCard(card) {
        var activeCache = null;
        var cacheName = null;

        setBusy(card, true);
        setStatus(card, 'Preparing...');
        return registerWorker()
            .then(function() {
                return fetchManifest(card);
            })
            .then(function(manifest) {
                var urls = manifest.urls || [];
                var total = urls.length;
                var done = 0;
                var failed = 0;
                if (!total) {
                    setStatus(card, 'No images to preload.');
                    return null;
                }
                setStatus(card, '0 / ' + total);
                cacheName = manifest.cache_name || card.dataset.cacheName;
                return caches.open(cacheName)
                    .then(function(cache) {
                        activeCache = cache;
                        return writeMetadata(
                            activeCache,
                            cacheName,
                            manifest,
                            0,
                            0,
                            false
                        ).then(function() {
                            return cache;
                        });
                    })
                    .then(function(cache) {
                        var index = 0;
                        var concurrency = Math.min(8, total);

                        function worker() {
                            if (index >= total) {
                                return Promise.resolve();
                            }
                            var url = urls[index];
                            index += 1;
                            return preloadOne(cache, url)
                                .catch(function() {
                                    failed += 1;
                                    return 'failed';
                                })
                                .then(function() {
                                    done += 1;
                                    setStatus(
                                        card,
                                        done + ' / ' + total
                                    );
                                    return worker();
                                });
                        }

                        var workers = [];
                        for (var i = 0; i < concurrency; i += 1) {
                            workers.push(worker());
                        }
                        return Promise.all(workers);
                    })
                    .then(function() {
                        return writeMetadata(
                            activeCache,
                            cacheName,
                            manifest,
                            total - failed,
                            failed,
                            failed === 0
                        );
                    })
                    .then(function(metadata) {
                        return countCachedImages(activeCache)
                            .then(function(count) {
                                setStatus(
                                    card,
                                    cachedStatus(metadata, count)
                                );
                            });
                    });
            })
            .catch(function(err) {
                setStatus(card, err.message || 'Preload failed.');
            })
            .finally(function() {
                setBusy(card, false);
            });
    }

    function backgroundPreloadFromManifest(manifestUrl) {
        if (!canPreload) return Promise.resolve();

        var activeCache = null;
        var cacheName = null;
        return registerWorker()
            .then(function() {
                return fetchJson(manifestUrl);
            })
            .then(function(manifest) {
                var urls = manifest.urls || [];
                var total = urls.length;
                var failed = 0;
                if (!total) return null;

                cacheName = manifest.cache_name;
                return caches.open(cacheName)
                    .then(function(cache) {
                        activeCache = cache;
                        return writeMetadata(
                            activeCache,
                            cacheName,
                            manifest,
                            0,
                            0,
                            false
                        ).then(function() {
                            return cache;
                        });
                    })
                    .then(function(cache) {
                        var index = 0;
                        var concurrency = Math.min(3, total);

                        function worker() {
                            if (index >= total) {
                                return Promise.resolve();
                            }
                            var url = urls[index];
                            index += 1;
                            return preloadOne(cache, url)
                                .catch(function() {
                                    failed += 1;
                                })
                                .then(worker);
                        }

                        var workers = [];
                        for (var i = 0; i < concurrency; i += 1) {
                            workers.push(worker());
                        }
                        return Promise.all(workers);
                    })
                    .then(function() {
                        return countCachedImages(activeCache);
                    })
                    .then(function(count) {
                        return writeMetadata(
                            activeCache,
                            cacheName,
                            manifest,
                            count,
                            failed,
                            false
                        );
                    });
            })
            .catch(function() {
                return null;
            });
    }

    function deleteCardCache(card) {
        setBusy(card, true);
        setStatus(card, 'Deleting...');
        caches.delete(card.dataset.cacheName)
            .then(function(deleted) {
                setStatus(
                    card,
                    deleted ? 'Saved images deleted.' : 'No saved images.'
                );
            })
            .catch(function() {
                setStatus(card, 'Could not delete saved images.');
            })
            .finally(function() {
                setBusy(card, false);
                updateCacheStatus(card);
            });
    }

    function bindCard(card) {
        card.querySelectorAll('[data-preload-action]').forEach(function(btn) {
            if (!canPreload) {
                btn.disabled = true;
            }
            btn.addEventListener('click', function() {
                if (btn.dataset.preloadAction === 'delete') {
                    deleteCardCache(card);
                } else {
                    preloadCard(card);
                }
            });
        });
        updateCacheStatus(card);
    }

    document.addEventListener('DOMContentLoaded', function() {
        document.querySelectorAll('.preload-card').forEach(bindCard);
        document
            .querySelectorAll('[data-background-preload-url]')
            .forEach(function(el) {
                backgroundPreloadFromManifest(
                    el.dataset.backgroundPreloadUrl
                );
            });
        if (!canPreload) {
            document.querySelectorAll('.preload-card').forEach(function(card) {
                setStatus(card, 'Browser cache preload is not supported.');
            });
        }
    });
}());
