(function() {
    'use strict';

    var DEFAULT_FIELD_SIDE = 80;
    var MIN_FIELD_SIDE = 40;
    var MAX_FIELD_SIDE = 120;
    var MIN_PREVIEW_SIDE = 80;
    var MAX_PREVIEW_SIDE = 280;
    var lastPointer = null;

    function factorFor(root) {
        var source = root && root.closest
            ? root.closest('[data-zoom-factor]')
            : null;
        if (!source) {
            source = document.querySelector('[data-zoom-factor]');
        }
        return parseFloat(source && source.dataset.zoomFactor) || 2;
    }

    function fieldSideFor(root) {
        var control = document.querySelector('[data-zoom-field-slider]');
        var value = control
            ? parseInt(control.dataset.value, 10)
            : DEFAULT_FIELD_SIDE;
        return clampRange(
            value || DEFAULT_FIELD_SIDE,
            MIN_FIELD_SIDE,
            MAX_FIELD_SIDE
        );
    }

    function ensureZoomNodes(img) {
        var wrapper = img.closest('.image-wrapper');
        if (!wrapper) return null;
        wrapper.style.position = 'relative';

        var host = zoomPreviewHost(img, wrapper);
        if (!host) return null;

        var slot = img._zoomSlot;
        if (!slot) {
            slot = document.createElement('div');
            slot.className = 'zoom-preview-slot';
            host.appendChild(slot);
            img._zoomSlot = slot;
        }

        var overlay = slot.querySelector(':scope > .zoom-overlay');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.className = 'zoom-overlay';
            slot.appendChild(overlay);
        }

        var source = wrapper.querySelector(':scope > .zoom-source-rect');
        if (!source) {
            source = document.createElement('div');
            source.className = 'zoom-source-rect';
            wrapper.appendChild(source);
        }

        return {
            wrapper: wrapper,
            slot: slot,
            overlay: overlay,
            source: source
        };
    }

    function zoomPreviewHost(img, wrapper) {
        var layout = img.closest('.pair-shared-ref-layout, .mos-layout');
        if (layout) {
            var next = layout.nextElementSibling;
            if (!next || !next.classList.contains('zoom-preview-tray')) {
                next = document.createElement('div');
                next.className = 'zoom-preview-tray';
                layout.insertAdjacentElement('afterend', next);
            }
            return next;
        }

        var imageArea = img.closest('.pair-images-area');
        if (imageArea) {
            var tray = imageArea.querySelector(':scope > .zoom-preview-tray');
            if (!tray) {
                tray = document.createElement('div');
                tray.className = 'zoom-preview-tray';
                imageArea.appendChild(tray);
            }
            return tray;
        }

        var parent = wrapper.parentNode;
        if (!parent) return null;
        return parent;
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

    function previewSideForImage(img, factor, fieldSide) {
        var baseSide = displayedImageBaseSide(img);
        if (!baseSide) return Math.round(fieldSide * factor);
        return clampRange(
            Math.round(fieldSide * factor),
            MIN_PREVIEW_SIDE,
            Math.min(MAX_PREVIEW_SIDE, baseSide)
        );
    }

    function previewSideForImages(images, factor, fieldSide) {
        var sides = images.map(displayedImageBaseSide).filter(function(side) {
            return side > 0;
        });
        if (!sides.length) return Math.round(fieldSide * factor);
        return clampRange(
            Math.round(fieldSide * factor),
            MIN_PREVIEW_SIDE,
            Math.min(MAX_PREVIEW_SIDE, Math.min.apply(null, sides))
        );
    }

    function fieldSideForPreview(previewSide, factor, fieldSide, img) {
        var baseSide = displayedImageBaseSide(img);
        return clampRange(
            Math.round(previewSide / factor),
            MIN_FIELD_SIDE,
            Math.min(MAX_FIELD_SIDE, baseSide || MAX_FIELD_SIDE, fieldSide)
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
        nodes.slot.style.minHeight = '';
    }

    function hideImages(images) {
        images.forEach(hideImage);
    }

    function showImage(img, factor, fieldSide, point, previewSize) {
        var nodes = img._zoomNodes || ensureZoomNodes(img);
        if (!nodes) return;
        img._zoomNodes = nodes;

        var imageRect = img.getBoundingClientRect();
        if (!imageRect.width || !imageRect.height) return;

        var wrapperRect = nodes.wrapper.getBoundingClientRect();
        var imageLeft = imageRect.left - wrapperRect.left;
        var imageTop = imageRect.top - wrapperRect.top;
        var overlaySide = previewSize || previewSideForImage(
            img, factor, fieldSide
        );
        var lensSide = fieldSideForPreview(
            overlaySide, factor, fieldSide, img
        );

        nodes.slot.style.minHeight = overlaySide + 'px';
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

    // Distance (px) a touch must travel before it counts as a zoom drag
    // rather than a tap that selects the image.
    var TOUCH_DRAG_THRESHOLD = 8;

    function attachImage(img, groupImages, factor) {
        if (img.dataset.zoomAttached === '1') return;
        var nodes = ensureZoomNodes(img);
        if (!nodes) return;
        img._zoomNodes = nodes;
        img.dataset.zoomAttached = '1';

        function update(event) {
            var point = relativePoint(img, event);
            var fieldSide = fieldSideFor(img);
            lastPointer = {
                img: img,
                groupImages: groupImages,
                factor: factor,
                point: point
            };
            if (groupImages && groupImages.length > 1) {
                var previewSide = previewSideForImages(
                    groupImages, factor, fieldSide
                );
                groupImages.forEach(function(groupImg) {
                    showImage(
                        groupImg,
                        factor,
                        fieldSide,
                        point,
                        previewSide
                    );
                });
                return;
            }
            showImage(img, factor, fieldSide, point);
        }

        function hide() {
            lastPointer = null;
            if (groupImages && groupImages.length > 1) {
                hideImages(groupImages);
                return;
            }
            hideImage(img);
        }

        // Touch drag state: track the active finger and whether it has
        // moved far enough to be treated as a loupe drag.
        var touchId = null;
        var dragging = false;
        var startX = 0;
        var startY = 0;

        img.addEventListener('pointermove', function(event) {
            // Mouse hovers the loupe around directly.
            if (event.pointerType === 'mouse') {
                update(event);
                return;
            }
            if (event.pointerId !== touchId) return;
            if (!dragging) {
                if (Math.abs(event.clientX - startX) < TOUCH_DRAG_THRESHOLD
                        && Math.abs(event.clientY - startY)
                            < TOUCH_DRAG_THRESHOLD) {
                    return;
                }
                dragging = true;
                try {
                    img.setPointerCapture(touchId);
                } catch (err) { /* capture is best-effort */ }
            }
            // Keep the finger drag from scrolling the page.
            event.preventDefault();
            update(event);
        });

        img.addEventListener('pointerdown', function(event) {
            if (event.pointerType === 'mouse') return;
            touchId = event.pointerId;
            startX = event.clientX;
            startY = event.clientY;
            dragging = false;
        });

        function endTouch(event) {
            if (event.pointerType === 'mouse') return;
            if (event.pointerId !== touchId) return;
            touchId = null;
            if (dragging) {
                dragging = false;
                hide();
                // Swallow the trailing click so a drag never toggles the
                // A/B selection; a plain tap (no drag) still selects.
                event.preventDefault();
            }
        }

        img.addEventListener('pointerup', endTouch);
        img.addEventListener('pointercancel', endTouch);

        img.addEventListener('pointerleave', function(event) {
            if (event.pointerType === 'mouse') {
                hide();
            }
        });

        img.addEventListener('error', function() {
            hideImage(img);
        });

        // If the loupe is open over this image (or its group) and the picture
        // changes underneath a stationary pointer — e.g. the annotator advances
        // to the next pair with the keyboard while hovering — redraw it so it
        // shows the new image, not the stale one, without needing a mouse move.
        img.addEventListener('load', function() {
            if (!lastPointer) return;
            if (lastPointer.img === img
                    || (lastPointer.groupImages
                        && lastPointer.groupImages.indexOf(img) !== -1)) {
                refreshActiveZoom();
            }
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

    function refreshActiveZoom() {
        if (!lastPointer) return;
        var fieldSide = fieldSideFor(lastPointer.img);
        if (lastPointer.groupImages && lastPointer.groupImages.length > 1) {
            var previewSide = previewSideForImages(
                lastPointer.groupImages,
                lastPointer.factor,
                fieldSide
            );
            lastPointer.groupImages.forEach(function(groupImg) {
                showImage(
                    groupImg,
                    lastPointer.factor,
                    fieldSide,
                    lastPointer.point,
                    previewSide
                );
            });
            return;
        }
        showImage(
            lastPointer.img,
            lastPointer.factor,
            fieldSide,
            lastPointer.point
        );
    }

    function sliderNumber(slider, name, fallback) {
        var value = parseInt(slider.dataset[name], 10);
        return Number.isFinite(value) ? value : fallback;
    }

    function setSliderValue(slider, rawValue) {
        var min = sliderNumber(slider, 'min', MIN_FIELD_SIDE);
        var max = sliderNumber(slider, 'max', MAX_FIELD_SIDE);
        var step = sliderNumber(slider, 'step', 4);
        var value = clampRange(rawValue, min, max);
        value = min + Math.round((value - min) / step) * step;
        value = clampRange(value, min, max);

        var pct = ((value - min) / (max - min)) * 100;
        var fill = slider.querySelector('.zoom-field-fill');
        var thumb = slider.querySelector('.zoom-field-thumb');
        var output = slider
            .closest('.zoom-field-control')
            .querySelector('[data-zoom-field-output]');

        slider.dataset.value = String(value);
        slider.setAttribute('aria-valuenow', String(value));
        if (fill) fill.style.width = pct + '%';
        if (thumb) thumb.style.left = pct + '%';
        if (output) output.textContent = String(value);
        refreshActiveZoom();
    }

    function setSliderFromClientX(slider, clientX) {
        var rect = slider.getBoundingClientRect();
        if (!rect.width) return;
        var min = sliderNumber(slider, 'min', MIN_FIELD_SIDE);
        var max = sliderNumber(slider, 'max', MAX_FIELD_SIDE);
        var pct = clampUnit((clientX - rect.left) / rect.width);
        setSliderValue(slider, min + pct * (max - min));
    }

    function initZoomFieldControls() {
        document
            .querySelectorAll('[data-zoom-field-slider]')
            .forEach(function(slider) {
                setSliderValue(
                    slider,
                    sliderNumber(slider, 'value', DEFAULT_FIELD_SIDE)
                );

                var activePointer = null;

                function onMove(event) {
                    if (event.pointerId !== activePointer) return;
                    setSliderFromClientX(slider, event.clientX);
                }

                function stopDrag(event) {
                    if (event.pointerId !== activePointer) return;
                    activePointer = null;
                }

                slider.addEventListener('pointerdown', function(event) {
                    event.preventDefault();
                    activePointer = event.pointerId;
                    slider.setPointerCapture(event.pointerId);
                    setSliderFromClientX(slider, event.clientX);
                });
                slider.addEventListener('pointermove', onMove);
                slider.addEventListener('pointerup', stopDrag);
                slider.addEventListener('pointercancel', stopDrag);

                slider.addEventListener('keydown', function(event) {
                    var current = sliderNumber(
                        slider, 'value', DEFAULT_FIELD_SIDE
                    );
                    var min = sliderNumber(slider, 'min', MIN_FIELD_SIDE);
                    var max = sliderNumber(slider, 'max', MAX_FIELD_SIDE);
                    var step = sliderNumber(slider, 'step', 4);
                    if (event.key === 'ArrowLeft'
                            || event.key === 'ArrowDown') {
                        event.preventDefault();
                        setSliderValue(slider, current - step);
                    } else if (event.key === 'ArrowRight'
                            || event.key === 'ArrowUp') {
                        event.preventDefault();
                        setSliderValue(slider, current + step);
                    } else if (event.key === 'Home') {
                        event.preventDefault();
                        setSliderValue(slider, min);
                    } else if (event.key === 'End') {
                        event.preventDefault();
                        setSliderValue(slider, max);
                    }
                });
            });
    }

    document.addEventListener('DOMContentLoaded', function() {
        if (!document.querySelector('[data-zoom-factor]')) return;
        window.IQAInitZoom(document);
        initZoomFieldControls();
    });
})();
