/*
 * Sliding-window image prefetch.
 *
 * On page load, ask the server for the CDN URLs of the next few unanswered
 * trials, then warm the browser HTTP cache by loading them in the background
 * with a small concurrency cap. Entirely non-blocking: the real <img> tags on
 * the evaluation page still load normally from CloudFront if prefetch fails.
 */
(function () {
    'use strict';

    var CONCURRENCY = 3;      // parallel background image loads
    var MAX_IN_FLIGHT = 24;   // complete 8-trial 2AFC window (3 images each)
    var STORAGE_KEY = 'iqa-prefetched-urls';

    function storedUrls() {
        try {
            return JSON.parse(sessionStorage.getItem(STORAGE_KEY) || '[]');
        } catch (err) {
            return [];
        }
    }

    function rememberUrl(url) {
        try {
            var urls = storedUrls().filter(function(item) {
                return item !== url;
            });
            urls.push(url);
            sessionStorage.setItem(
                STORAGE_KEY, JSON.stringify(urls.slice(-200))
            );
        } catch (err) { /* storage is an optional optimization */ }
    }

    function warm(urls, reportUrl, studyId) {
        var alreadyWarm = new Set(storedUrls());
        var queue = urls.filter(function(url) {
            return !alreadyWarm.has(url);
        }).slice(0, MAX_IN_FLIGHT);
        var index = 0;
        var active = 0;
        var ok = 0;
        var fail = 0;
        var reported = false;

        function report() {
            if (reported) return;
            reported = true;
            if (fail > 0 && reportUrl && navigator.sendBeacon) {
                try {
                    navigator.sendBeacon(reportUrl, new Blob(
                        [JSON.stringify({ study: studyId, ok: ok, fail: fail })],
                        { type: 'application/json' }
                    ));
                } catch (err) { /* ignore */ }
            }
        }

        function pump() {
            if (index >= queue.length) {
                if (active === 0) report();
                return;
            }
            var url = queue[index++];
            active += 1;
            var img = new Image();
            img.fetchPriority = 'low';
            img.onload = function () {
                rememberUrl(url);
                ok += 1; active -= 1; pump();
            };
            img.onerror = function () {
                fail += 1; active -= 1; pump();
            };
            img.src = url;
        }

        for (var i = 0; i < CONCURRENCY; i += 1) pump();
    }

    function start() {
        var el = document.querySelector('[data-prefetch-url]');
        if (!el) return;
        var url = el.getAttribute('data-prefetch-url');
        var reportUrl = el.getAttribute('data-prefetch-report-url');
        var studyId = el.getAttribute('data-prefetch-study');
        if (!url) return;

        fetch(url, { credentials: 'same-origin' })
            .then(function (resp) { return resp.ok ? resp.json() : null; })
            .then(function (data) {
                if (data && data.images && data.images.length) {
                    warm(data.images, reportUrl, studyId);
                }
            })
            .catch(function () { /* non-blocking */ });
    }

    if (document.readyState === 'complete') {
        start();
    } else {
        window.addEventListener('load', start, { once: true });
    }
})();
