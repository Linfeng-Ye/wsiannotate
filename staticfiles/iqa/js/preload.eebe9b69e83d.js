(function() {
    'use strict';

    var canPreload = (
        'serviceWorker' in navigator
        && 'caches' in window
        && 'fetch' in window
    );

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
        return navigator.serviceWorker.register('/iqa/preload-sw.js')
            .then(function(reg) {
                if (reg.active) return reg;
                return navigator.serviceWorker.ready;
            });
    }

    function fetchManifest(card) {
        var manifestUrl = card.dataset.manifestUrl;
        return fetch(manifestUrl, {
            credentials: 'same-origin',
            cache: 'no-store'
        }).then(function(response) {
            if (!response.ok) {
                throw new Error('Could not load image list.');
            }
            return response.json();
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
        return cache.match(url).then(function(cached) {
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
                return caches.open(manifest.cache_name || card.dataset.cacheName)
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
                        if (failed) {
                            setStatus(
                                card,
                                'Saved ' + (total - failed) + ' / '
                                + total + ' images locally.'
                            );
                        } else {
                            setStatus(
                                card,
                                'Saved ' + total + ' images locally.'
                            );
                        }
                    });
            })
            .catch(function(err) {
                setStatus(card, err.message || 'Preload failed.');
            })
            .finally(function() {
                setBusy(card, false);
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
    }

    document.addEventListener('DOMContentLoaded', function() {
        document.querySelectorAll('.preload-card').forEach(bindCard);
        if (!canPreload) {
            document.querySelectorAll('.preload-card').forEach(function(card) {
                setStatus(card, 'Browser cache preload is not supported.');
            });
        }
    });
}());
