(function() {
    'use strict';

    var MIN_PREVIEW_SIDE = 120;
    var MAX_PREVIEW_SIDE = 280;
    var MIN_LENS_SIDE = 24;
    var MAX_LENS_SIDE = 80;

    function factorFor(root) {
        var source = root && root.closest
            ? root.closest('[data-zoom-factor]')
            : null;
        if (!source) {
            source = document.querySelector('[data-zoom-factor]');
        }
        return parseFloat(source && source.dataset.zoomFactor) || 2;
    }

    function ensureZoomNodes(img) {
        var wrapper = img.closest('.image-wrapper');
        if (!wrapper) return null;
        wrapper.style.position = 'relative';

        var overlay = wrapper.querySelector(':scope > .zoom-overlay');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.className = 'zoom-overlay';
            wrapper.appendChild(overlay);
        }

        var source = wrapper.querySelector(':scope > .zoom-source-rect');
        if (!source) {
            source = document.createElement('div');
            source.className = 'zoom-source-rect';
            wrapper.appendChild(source);
        }

        return {
            wrapper: wrapper,
            overlay: overlay,
            source: source
        };
    }

    function clampUnit(value) {
        return Math.max(0, Math.min(1, value));
    }

    function clampRange(value, min, max) {
        return Math.max(min, Math.min(max, value));
    }

    function clampPosition(value, min, max) {
        if (max < min) {
            return min + (max - min) / 2;
        }
        return Math.max(min, Math.min(max, value));
    }

    function displayedImageBaseSide(img) {
        var rect = img.getBoundingClientRect();
        if (!rect.width || !rect.height) return 0;
        return Math.min(rect.width, rect.height);
    }

    function previewSideForImage(img) {
        var baseSide = displayedImageBaseSide(img);
        if (!baseSide) return MIN_PREVIEW_SIDE;
        return clampRange(
            Math.round(baseSide / 3),
            MIN_PREVIEW_SIDE,
            MAX_PREVIEW_SIDE
        );
    }

    function previewSideForImages(images) {
        var sides = images.map(displayedImageBaseSide).filter(function(side) {
            return side > 0;
        });
        if (!sides.length) return MIN_PREVIEW_SIDE;
        return clampRange(
            Math.round(Math.min.apply(null, sides) / 3),
            MIN_PREVIEW_SIDE,
            MAX_PREVIEW_SIDE
        );
    }

    function lensSideForPreview(previewSide) {
        return clampRange(
            Math.round(previewSide / 4),
            MIN_LENS_SIDE,
            MAX_LENS_SIDE
        );
    }

    function relativePoint(img, event) {
        var rect = img.getBoundingClientRect();
        if (!rect.width || !rect.height) {
            return {x: 0.5, y: 0.5};
        }
        return {
            x: clampUnit((event.clientX - rect.left) / rect.width),
            y: clampUnit((event.clientY - rect.top) / rect.height)
        };
    }

    function hideImage(img) {
        var nodes = img._zoomNodes;
        if (!nodes) return;
        nodes.overlay.style.display = 'none';
        nodes.source.style.display = 'none';
    }

    function hideImages(images) {
        images.forEach(hideImage);
    }

    function showImage(img, factor, point, previewSize) {
        var nodes = img._zoomNodes || ensureZoomNodes(img);
        if (!nodes) return;
        img._zoomNodes = nodes;

        var imageRect = img.getBoundingClientRect();
        if (!imageRect.width || !imageRect.height) return;

        var wrapperRect = nodes.wrapper.getBoundingClientRect();
        var imageLeft = imageRect.left - wrapperRect.left;
        var imageTop = imageRect.top - wrapperRect.top;
        var overlaySide = previewSize || previewSideForImage(img);
        var lensSide = lensSideForPreview(overlaySide);

        nodes.overlay.style.width = overlaySide + 'px';
        nodes.overlay.style.height = overlaySide + 'px';
        nodes.overlay.style.backgroundImage = (
            'url("' + (img.currentSrc || img.src) + '")'
        );
        nodes.overlay.style.backgroundSize = (
            (imageRect.width * factor) + 'px '
            + (imageRect.height * factor) + 'px'
        );

        var bgX = overlaySide / 2
            - point.x * imageRect.width * factor;
        var bgY = overlaySide / 2
            - point.y * imageRect.height * factor;
        bgX = Math.min(
            0,
            Math.max(bgX, overlaySide - imageRect.width * factor)
        );
        bgY = Math.min(
            0,
            Math.max(bgY, overlaySide - imageRect.height * factor)
        );

        nodes.overlay.style.backgroundPosition = bgX + 'px ' + bgY + 'px';
        nodes.overlay.style.left = clampPosition(
            point.x < 0.5
                ? imageLeft + imageRect.width - overlaySide
                : imageLeft,
            imageLeft,
            imageLeft + imageRect.width - overlaySide
        ) + 'px';
        nodes.overlay.style.top = clampPosition(
            point.y < 0.5
                ? imageTop + imageRect.height - overlaySide
                : imageTop,
            imageTop,
            imageTop + imageRect.height - overlaySide
        ) + 'px';
        nodes.overlay.style.display = 'block';

        nodes.source.style.width = lensSide + 'px';
        nodes.source.style.height = lensSide + 'px';
        nodes.source.style.left = clampPosition(
            imageLeft + point.x * imageRect.width - lensSide / 2,
            imageLeft,
            imageLeft + imageRect.width - lensSide
        ) + 'px';
        nodes.source.style.top = clampPosition(
            imageTop + point.y * imageRect.height - lensSide / 2,
            imageTop,
            imageTop + imageRect.height - lensSide
        ) + 'px';
        nodes.source.style.display = 'block';
    }

    function attachImage(img, groupImages, factor) {
        if (img.dataset.zoomAttached === '1') return;
        var nodes = ensureZoomNodes(img);
        if (!nodes) return;
        img._zoomNodes = nodes;
        img.dataset.zoomAttached = '1';

        img.addEventListener('mousemove', function(event) {
            var point = relativePoint(img, event);
            if (groupImages && groupImages.length > 1) {
                var previewSide = previewSideForImages(groupImages);
                groupImages.forEach(function(groupImg) {
                    showImage(
                        groupImg,
                        factor,
                        point,
                        previewSide
                    );
                });
                return;
            }
            showImage(img, factor, point);
        });

        img.addEventListener('mouseleave', function() {
            if (groupImages && groupImages.length > 1) {
                hideImages(groupImages);
                return;
            }
            hideImage(img);
        });

        img.addEventListener('error', function() {
            hideImage(img);
        });
    }

    function buildGroups(images) {
        var groups = {};
        images.forEach(function(img) {
            var group = img.dataset.syncZoomGroup;
            if (!group) return;
            if (!groups[group]) groups[group] = [];
            groups[group].push(img);
        });
        return groups;
    }

    window.IQAInitZoom = function(root) {
        root = root || document;
        var factor = factorFor(root);
        var images = Array.prototype.slice.call(
            root.querySelectorAll('.eval-image')
        );
        var groups = buildGroups(images);

        images.forEach(function(img) {
            var groupName = img.dataset.syncZoomGroup;
            var groupImages = groupName ? groups[groupName] : null;
            attachImage(img, groupImages, factor);
        });
    };

    document.addEventListener('DOMContentLoaded', function() {
        if (!document.querySelector('[data-zoom-factor]')) return;
        window.IQAInitZoom(document);
    });
})();
