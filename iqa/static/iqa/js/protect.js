/*
 * Casual image-download deterrence for the evaluation images.
 *
 * Blocks the everyday ways an annotator would save a study image — right-click
 * "Save image as", drag-to-desktop, and the mobile long-press menu. This is
 * deterrence only: anything the browser displays it has already downloaded, so
 * a determined user with DevTools can still get the bytes. It does NOT touch
 * pointer events, so the zoom loupe and tap-to-select keep working.
 */
(function () {
    'use strict';

    function isEvalImage(t) {
        return !!(t && t.classList && t.classList.contains('eval-image'));
    }

    // Right-click / long-press context menu on an image.
    document.addEventListener('contextmenu', function (e) {
        if (isEvalImage(e.target)) e.preventDefault();
    });

    // Drag-to-save (drag the image out to the desktop or another app).
    document.addEventListener('dragstart', function (e) {
        if (isEvalImage(e.target)) e.preventDefault();
    });
}());
