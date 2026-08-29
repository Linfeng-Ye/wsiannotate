/* Submit an evaluation without the blank "loading next stimulus" page.
 *
 * evaluation_submit already answers AJAX requests with a small JSON payload
 * ({next_url | done_url}).  We POST the form in the background, show a light
 * spinner, then navigate straight to the next trial (whose images are already
 * warmed by prefetch.js).  On any failure we fall back to a normal submit so
 * the response is never lost.
 */
(function () {
    var spinner = null;

    function showNavSpinner() {
        if (spinner) return;
        spinner = document.createElement('div');
        spinner.className = 'nav-spinner';
        var dot = document.createElement('div');
        dot.className = 'nav-spinner-dot';
        spinner.appendChild(dot);
        document.body.appendChild(spinner);
    }

    function hideNavSpinner() {
        if (spinner && spinner.parentNode) {
            spinner.parentNode.removeChild(spinner);
        }
        spinner = null;
    }

    window.iqaAjaxSubmit = function (form) {
        if (form.dataset.iqaSubmitting === '1') return;
        form.dataset.iqaSubmitting = '1';
        showNavSpinner();

        fetch(form.action, {
            method: 'POST',
            body: new FormData(form),
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
            credentials: 'same-origin',
        }).then(function (resp) {
            return resp.ok ? resp.json() : Promise.reject();
        }).then(function (data) {
            var target = data && data.success
                && (data.next_url || data.done_url);
            if (!target) return Promise.reject();
            window.location.href = target;
        }).catch(function () {
            // Fall back to a plain navigation submit (bypasses this handler).
            form.dataset.iqaSubmitting = '';
            hideNavSpinner();
            HTMLFormElement.prototype.submit.call(form);
        });
    };

    // Keep the server connection warm. App Runner speaks HTTP/1.1, and on
    // high-RTT / NAT-dropping networks an idle TLS connection is torn down
    // between trials, so each click otherwise pays a fresh TCP+TLS handshake
    // (~1-2s) that dwarfs the ~300ms of actual work. A cheap periodic ping to
    // the health endpoint keeps an established connection in the socket pool
    // for the next submit/navigation to reuse.
    var HEARTBEAT_MS = 10000;

    function heartbeat() {
        if (document.visibilityState === 'hidden') return;
        try {
            fetch('/healthz', {
                method: 'GET',
                cache: 'no-store',
                credentials: 'same-origin',
            }).catch(function () { /* best-effort */ });
        } catch (err) { /* best-effort */ }
    }

    setInterval(heartbeat, HEARTBEAT_MS);
    document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'visible') heartbeat();
    });
    heartbeat();
}());
