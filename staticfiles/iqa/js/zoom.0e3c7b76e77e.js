document.addEventListener('DOMContentLoaded', function() {
    'use strict';
    var root = document.querySelector('[data-zoom-factor]');
    if (!root) return;
    var factor =
        parseFloat(root.dataset.zoomFactor) || 2;
    var images =
        document.querySelectorAll('.eval-image');
    if (!images.length) return;

    images.forEach(function(img) {
        var wrapper = img.closest('.image-wrapper');
        if (!wrapper) return;
        wrapper.style.position = 'relative';
        var ov = document.createElement('div');
        ov.className = 'zoom-overlay';
        wrapper.appendChild(ov);
        var src = document.createElement('div');
        src.className = 'zoom-source-rect';
        wrapper.appendChild(src);
        img._zoomOv = ov;
        img._zoomSrc = src;
        img._zoomWrap = wrapper;
    });

    function show(relX, relY) {
        images.forEach(function(img) {
            var ov = img._zoomOv;
            var src = img._zoomSrc;
            if (!ov || !src) return;
            var ir = img.getBoundingClientRect();
            var wr = img._zoomWrap
                .getBoundingClientRect();
            var iw = ir.width, ih = ir.height;
            var oL = ir.left - wr.left;
            var oT = ir.top - wr.top;
            var ow = Math.round(iw / 3);
            var oh = Math.round(ih / 3);

            ov.style.width = ow + 'px';
            ov.style.height = oh + 'px';
            ov.style.backgroundImage =
                'url("' + img.src + '")';
            ov.style.backgroundSize =
                (iw * factor) + 'px '
                + (ih * factor) + 'px';

            var bx = ow / 2 - relX * iw * factor;
            var by = oh / 2 - relY * ih * factor;
            bx = Math.min(
                0, Math.max(bx, ow - iw * factor)
            );
            by = Math.min(
                0, Math.max(by, oh - ih * factor)
            );
            ov.style.backgroundPosition =
                bx + 'px ' + by + 'px';

            var left = (relX < 0.5)
                ? oL + iw - ow : oL;
            var top = (relY < 0.5)
                ? oT + ih - oh : oT;
            ov.style.left = left + 'px';
            ov.style.top = top + 'px';
            ov.style.display = 'block';

            var srcW = ow / factor;
            var srcH = oh / factor;
            var srcL = oL + (-bx) / factor;
            var srcT = oT + (-by) / factor;
            src.style.width = srcW + 'px';
            src.style.height = srcH + 'px';
            src.style.left = srcL + 'px';
            src.style.top = srcT + 'px';
            src.style.display = 'block';
        });
    }

    function hide() {
        images.forEach(function(img) {
            if (img._zoomOv)
                img._zoomOv.style.display = 'none';
            if (img._zoomSrc)
                img._zoomSrc.style.display = 'none';
        });
    }

    images.forEach(function(img) {
        img.addEventListener('mousemove', function(e) {
            var r = img.getBoundingClientRect();
            var rx = (e.clientX - r.left) / r.width;
            var ry = (e.clientY - r.top) / r.height;
            rx = Math.max(0, Math.min(1, rx));
            ry = Math.max(0, Math.min(1, ry));
            show(rx, ry);
        });
        img.addEventListener('mouseleave', hide);
    });
});
