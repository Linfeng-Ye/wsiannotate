(function() {
    'use strict';
    if (!('requestIdleCallback' in window)) return;

    window.requestIdleCallback(function() {
        document.querySelectorAll('img[data-preload-src]').forEach(function(img) {
            var src = img.getAttribute('data-preload-src');
            if (src) {
                var preload = new Image();
                preload.src = src;
            }
        });
    });
}());
