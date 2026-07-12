/*
 * Local-first 2AFC evaluation.
 *
 * The browser downloads the whole study once (manifest), drives the trial
 * sequence itself, and records each answer to localStorage so a click is
 * instant with zero network on the critical path. Answers sync to the server
 * in the background:
 *   - one fire-and-forget POST per submit (non-blocking),
 *   - a periodic retry of anything still unsynced,
 *   - a re-send on reload, and a sendBeacon flush on page close.
 * The server is the source of truth (idempotent upsert on (stimulus, user)),
 * so a lost background request simply re-appears as an unanswered trial.
 */
(function () {
    'use strict';

    var root = document.querySelector('[data-local-eval]');
    if (!root) return;

    var cfg = {
        studyId: root.dataset.studyId,
        csrf: root.dataset.csrf,
        manifestUrl: root.dataset.manifestUrl,
        answeredUrl: root.dataset.answeredUrl,
        batchUrl: root.dataset.batchUrl,
        homeUrl: root.dataset.homeUrl,
    };

    var PRELOAD_AHEAD = 6;       // trials to warm images for
    var RETRY_INTERVAL_MS = 15000;
    var STORAGE_KEY = 'iqa_local_' + cfg.studyId;

    // --- DOM ---------------------------------------------------------------
    var imgEls = {
        a: root.querySelector('[data-img="a"]'),
        b: root.querySelector('[data-img="b"]'),
        ref: root.querySelector('[data-img="ref"]'),
    };
    var layoutEl = root.querySelector('[data-images]');
    var choicesEl = root.querySelector('[data-choices]');
    var controlsEl = root.querySelector('[data-controls]');
    var statusEl = root.querySelector('[data-status]');
    var toolbarEl = root.querySelector('[data-toolbar]');
    var doneEl = root.querySelector('[data-done]');
    var progressEl = root.querySelector('[data-progress]');
    var submitBtn = root.querySelector('[data-submit]');
    var prevBtn = root.querySelector('[data-previous]');
    var quitBtn = root.querySelector('[data-quit]');
    var pairBtns = root.querySelectorAll('.pair-btn');
    var choiceWrappers = root.querySelectorAll('[data-image-choice]');

    // --- State -------------------------------------------------------------
    var trials = [];             // [{id, swap, img_a, img_b, ref}]
    var indexById = {};          // stimId(str) -> array index
    var responses = loadLocal(); // stimId(str) -> {choice, swap, synced}
    var serverChoice = {};       // stimId(str) -> displayChoice (from server)
    var current = -1;            // index into trials
    var chosen = null;           // 'A' | 'B' | null for the current trial
    var finished = false;
    var resyncInFlight = false;

    // --- localStorage ------------------------------------------------------
    function loadLocal() {
        try {
            var v = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
            return (v && typeof v === 'object') ? v : {};
        } catch (e) { return {}; }
    }
    function saveLocal() {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(responses));
        } catch (e) { /* storage full/blocked: server sync still covers us */ }
    }

    // --- Helpers -----------------------------------------------------------
    function sid(trial) { return String(trial.id); }
    function isDone(id) {
        id = String(id);
        return responses[id] != null || serverChoice[id] != null;
    }
    function choiceFor(id) {
        id = String(id);
        if (responses[id]) return responses[id].choice;
        return serverChoice[id] || null;
    }
    function doneCount() {
        var n = 0;
        for (var i = 0; i < trials.length; i++) {
            if (isDone(trials[i].id)) n++;
        }
        return n;
    }
    function updateProgress() {
        if (progressEl) {
            progressEl.textContent = doneCount() + ' / ' + trials.length;
        }
    }

    // --- Background sync ---------------------------------------------------
    function unsyncedItems() {
        var out = [];
        Object.keys(responses).forEach(function (id) {
            var r = responses[id];
            if (r && !r.synced) {
                out.push({
                    stimulus_id: parseInt(id, 10),
                    choice: r.choice,
                    swap: !!r.swap,
                    revise: !!r.revise,
                });
            }
        });
        return out;
    }

    function markSynced(id) {
        id = String(id);
        if (responses[id]) responses[id].synced = true;
        serverChoice[id] = choiceFor(id);
    }

    // One fire-and-forget POST for a single answer. Uses the batch endpoint
    // (pure idempotent upsert) so the server does no sampler/next-stimulus
    // work on the click path — the client drives the sequence itself.
    function syncOne(id) {
        id = String(id);
        var r = responses[id];
        if (!r) return;
        fetch(cfg.batchUrl, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': cfg.csrf,
            },
            body: JSON.stringify({
                study_id: parseInt(cfg.studyId, 10),
                responses: [{
                    stimulus_id: parseInt(id, 10),
                    choice: r.choice,
                    swap: !!r.swap,
                    revise: !!r.revise,
                }],
            }),
        }).then(function (resp) {
            if (resp.ok) { markSynced(id); saveLocal(); }
        }).catch(function () { /* retried later */ });
    }

    // Batch flush of everything still unsynced (retry / reload / done).
    function flushBatch() {
        var items = unsyncedItems();
        if (!items.length) return Promise.resolve(0);
        return fetch(cfg.batchUrl, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': cfg.csrf,
            },
            body: JSON.stringify({
                study_id: parseInt(cfg.studyId, 10),
                responses: items,
            }),
        }).then(function (resp) {
            if (!resp.ok) return 0;
            items.forEach(function (it) { markSynced(it.stimulus_id); });
            saveLocal();
            updateProgress();
            return items.length;
        }).catch(function () { return 0; });
    }

    // Pull the latest server progress and catch up. Called when this tab
    // regains focus/visibility, so a device the annotator left behind (while
    // they worked on another laptop) learns what the server now has instead of
    // re-showing — and overwriting — pairs another session already answered.
    function resyncFromServer() {
        if (finished || resyncInFlight) return;
        resyncInFlight = true;
        flushBatch();   // also push anything this device still owes
        fetch(cfg.answeredUrl, { credentials: 'same-origin' })
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (data) {
                if (data && data.answered) {
                    var changed = false;
                    data.answered.forEach(function (id) {
                        id = String(id);
                        if (serverChoice[id] == null) {
                            serverChoice[id] =
                                responses[id] ? responses[id].choice : 'A';
                            changed = true;
                        }
                        if (responses[id]) responses[id].synced = true;
                    });
                    if (changed) { saveLocal(); updateProgress(); }
                    // If the trial on screen was answered elsewhere and the
                    // annotator hasn't started this one, jump to the true
                    // position rather than re-answering it.
                    if (!finished && chosen == null
                            && current >= 0 && current < trials.length
                            && isDone(trials[current].id)) {
                        var next = firstUnanswered();
                        if (next === -1) showDone();
                        else renderTrial(next);
                    }
                }
            })
            .catch(function () { /* stay put; retried on next focus */ })
            .then(function () { resyncInFlight = false; });
    }

    // Page-close flush: sendBeacon can only carry a form/blob body, so the
    // CSRF token rides as a form field and the payload as JSON text.
    function beaconFlush() {
        var items = unsyncedItems();
        if (!items.length || !navigator.sendBeacon) return;
        try {
            var fd = new FormData();
            fd.append('csrfmiddlewaretoken', cfg.csrf);
            fd.append('payload', JSON.stringify({
                study_id: parseInt(cfg.studyId, 10),
                responses: items,
            }));
            navigator.sendBeacon(cfg.batchUrl, fd);
        } catch (e) { /* best-effort */ }
    }

    // --- Choice UI ---------------------------------------------------------
    function clearChoice() {
        chosen = null;
        pairBtns.forEach(function (b) { b.classList.remove('active'); });
        choiceWrappers.forEach(function (w) { w.classList.remove('selected'); });
        submitBtn.disabled = true;
    }
    function setChoice(c) {
        if (c !== 'A' && c !== 'B') { clearChoice(); return; }
        chosen = c;
        pairBtns.forEach(function (b) {
            b.classList.toggle('active', b.dataset.choice === c);
        });
        choiceWrappers.forEach(function (w) {
            w.classList.toggle('selected', w.dataset.imageChoice === c);
        });
        submitBtn.disabled = false;
    }

    // --- Rendering ---------------------------------------------------------
    function preload(fromIndex) {
        for (var i = fromIndex;
             i < Math.min(fromIndex + PRELOAD_AHEAD, trials.length); i++) {
            var t = trials[i];
            [t.img_a, t.img_b, t.ref].forEach(function (u) {
                if (!u) return;
                var im = new Image();
                im.fetchPriority = 'low';
                im.src = u;
            });
        }
    }

    function renderTrial(i) {
        if (i < 0 || i >= trials.length) return;
        current = i;
        var t = trials[i];
        imgEls.a.src = t.img_a;
        imgEls.b.src = t.img_b;
        if (imgEls.ref) imgEls.ref.src = t.ref || '';
        setChoice(choiceFor(t.id));    // restore prior answer or clear
        prevBtn.disabled = (i <= 0);
        updateProgress();
        preload(i + 1);
    }

    function firstUnanswered() {
        for (var i = 0; i < trials.length; i++) {
            if (!isDone(trials[i].id)) return i;
        }
        return -1;
    }
    function nextUnansweredFrom(start) {
        var i;
        for (i = start; i < trials.length; i++) {
            if (!isDone(trials[i].id)) return i;
        }
        for (i = 0; i < start && i < trials.length; i++) {
            if (!isDone(trials[i].id)) return i;
        }
        return -1;
    }

    function submit() {
        if (finished) return;
        var t = trials[current];
        if (!t || (chosen !== 'A' && chosen !== 'B')) return;
        var id = sid(t);
        // A revise = re-answering a pair we already know is answered (the
        // annotator navigated back to it). A first-time forward answer is not
        // a revise, so the server will not let it clobber an answer made on
        // another device the annotator left open.
        var revise = isDone(id);
        responses[id] = {
            choice: chosen, swap: !!t.swap, synced: false, revise: revise,
        };
        saveLocal();
        updateProgress();
        syncOne(id);                    // background, non-blocking
        var next = nextUnansweredFrom(current + 1);
        if (next === -1) { showDone(); } else { renderTrial(next); }
    }

    // --- Done / verification ----------------------------------------------
    // Visibility is controlled with inline display because the layout's CSS
    // (grid/flex/fixed) outranks the UA `[hidden]` rule.
    function disp(el, value) { if (el) el.style.display = value; }

    function showEval() {
        finished = false;
        disp(statusEl, 'none');
        disp(doneEl, 'none');
        disp(layoutEl, '');
        disp(toolbarEl, '');
        disp(choicesEl, '');
        disp(controlsEl, '');
    }

    function showDone() {
        finished = true;
        disp(layoutEl, 'none');
        disp(toolbarEl, 'none');
        disp(choicesEl, 'none');
        disp(controlsEl, 'none');
        disp(statusEl, 'none');
        disp(doneEl, '');
        doneEl.className = 'local-done';
        doneEl.innerHTML =
            '<h2>Verifying your responses&hellip;</h2>' +
            '<p>Making sure everything reached the server.</p>';

        // Push anything unsynced, then confirm against the server.
        flushBatch().then(function () {
            return fetch(cfg.answeredUrl, { credentials: 'same-origin' })
                .then(function (r) { return r.ok ? r.json() : null; });
        }).then(function (data) {
            var serverSet = new Set(
                (data && data.answered ? data.answered : []).map(String)
            );
            // Trust the server: re-derive synced from what it confirms, so a
            // response it is still missing stays unsynced and gets resent.
            serverSet.forEach(function (id) {
                if (serverChoice[id] == null) serverChoice[id] = 'A';
            });
            Object.keys(responses).forEach(function (id) {
                responses[id].synced = serverSet.has(id);
            });
            saveLocal();

            var pending = [];   // never answered anywhere -> must be done
            var unsent = [];    // answered locally, server doesn't have it yet
            trials.forEach(function (t) {
                var id = sid(t);
                if (serverSet.has(id)) return;
                if (responses[id]) unsent.push(t); else pending.push(t);
            });
            renderDone(serverSet.size, pending, unsent);
        }).catch(function () {
            // Offline at the very end: local answers are still on disk and
            // will resend next time. Be honest about it.
            renderDoneOffline();
        });
    }

    function renderDone(serverCount, pending, unsent) {
        if (pending.length === 0 && unsent.length === 0) {
            doneEl.className = 'local-done';
            doneEl.innerHTML =
                '<h2>All done ✓</h2>' +
                '<p><span class="local-done-count">' + serverCount +
                '</span> of <span class="local-done-count">' + trials.length +
                '</span> responses are saved on the server.</p>' +
                '<div class="local-done-actions">' +
                '<button type="button" class="btn btn-primary" data-go-home>' +
                'Back to studies</button></div>';
        } else if (unsent.length > 0) {
            doneEl.className = 'local-done is-warning';
            doneEl.innerHTML =
                '<h2>Almost there</h2>' +
                '<p><span class="local-done-count">' + unsent.length +
                '</span> response(s) haven’t reached the server yet ' +
                '(they’re saved on this device). Click to upload them.</p>' +
                '<div class="local-done-actions">' +
                '<button type="button" class="btn btn-primary" data-retry-upload>' +
                'Upload now</button>' +
                '<button type="button" class="btn" data-go-home>' +
                'Back to studies</button></div>' +
                (pending.length ? '<p class="local-sync-note">' +
                    pending.length + ' pair(s) still need a response.</p>' : '');
        } else {
            // Only truly-unanswered pairs remain (e.g. lost on another device).
            doneEl.className = 'local-done is-warning';
            doneEl.innerHTML =
                '<h2>' + pending.length + ' pair(s) still need a response</h2>' +
                '<p>These weren’t found on the server. You can finish ' +
                'them now.</p>' +
                '<div class="local-done-actions">' +
                '<button type="button" class="btn btn-primary" data-resume>' +
                'Continue</button>' +
                '<button type="button" class="btn" data-go-home>' +
                'Back to studies</button></div>';
        }
        wireDoneButtons();
    }

    function renderDoneOffline() {
        doneEl.className = 'local-done is-warning';
        doneEl.innerHTML =
            '<h2>Saved on this device</h2>' +
            '<p>Your responses are stored locally but the server couldn’t ' +
            'be reached to confirm. Please retry while online before ' +
            'switching devices.</p>' +
            '<div class="local-done-actions">' +
            '<button type="button" class="btn btn-primary" data-retry-upload>' +
            'Retry upload</button>' +
            '<button type="button" class="btn" data-go-home>' +
            'Back to studies</button></div>';
        wireDoneButtons();
    }

    function wireDoneButtons() {
        var home = doneEl.querySelector('[data-go-home]');
        if (home) home.addEventListener('click', goHome);
        var retry = doneEl.querySelector('[data-retry-upload]');
        if (retry) retry.addEventListener('click', function () {
            retry.disabled = true;
            retry.textContent = 'Uploading…';
            flushBatch().then(function () { showDone(); });
        });
        var resume = doneEl.querySelector('[data-resume]');
        if (resume) resume.addEventListener('click', function () {
            var next = firstUnanswered();
            if (next === -1) { showDone(); return; }
            showEval();
            renderTrial(next);
        });
    }

    function goHome() {
        beaconFlush();
        window.location.href = cfg.homeUrl;
    }

    // --- Events ------------------------------------------------------------
    pairBtns.forEach(function (b) {
        b.addEventListener('click', function () { setChoice(b.dataset.choice); });
    });
    choiceWrappers.forEach(function (w) {
        w.addEventListener('click', function () {
            setChoice(w.dataset.imageChoice);
        });
        w.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                setChoice(w.dataset.imageChoice);
            }
        });
    });
    submitBtn.addEventListener('click', submit);
    prevBtn.addEventListener('click', function () {
        if (current > 0) renderTrial(current - 1);
    });
    quitBtn.addEventListener('click', goHome);

    document.addEventListener('keydown', function (e) {
        if (finished) return;
        var key = e.key.toUpperCase();
        if (key === 'A' || e.key === '1') setChoice('A');
        else if (key === 'B' || e.key === '2') setChoice('B');
        else if (e.key === 'Enter' && !submitBtn.disabled) {
            e.preventDefault();
            submit();
        }
    });

    // Flush on the way out (tab close, navigation, backgrounding); pull the
    // latest server progress on the way back in (returning to this tab).
    window.addEventListener('pagehide', beaconFlush);
    window.addEventListener('focus', resyncFromServer);
    document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'hidden') beaconFlush();
        else resyncFromServer();
    });

    // Belt-and-suspenders push retry of anything still unsynced (never on the
    // click path). This only re-sends this device's own answers; it does not
    // pull progress — that is event-driven via resyncFromServer.
    setInterval(function () {
        if (document.visibilityState === 'visible') flushBatch();
    }, RETRY_INTERVAL_MS);

    // --- Boot --------------------------------------------------------------
    function showError(msg) {
        disp(layoutEl, 'none');
        disp(toolbarEl, 'none');
        disp(choicesEl, 'none');
        disp(controlsEl, 'none');
        disp(doneEl, 'none');
        disp(statusEl, '');
        statusEl.className = 'local-status is-error';
        statusEl.textContent = msg;
    }

    function boot() {
        fetch(cfg.manifestUrl, { credentials: 'same-origin' })
            .then(function (r) {
                if (!r.ok) throw new Error('manifest ' + r.status);
                return r.json();
            })
            .then(function (data) {
                trials = data.trials || [];
                trials.forEach(function (t, i) { indexById[String(t.id)] = i; });
                serverChoice = {};
                Object.keys(data.answered || {}).forEach(function (id) {
                    serverChoice[String(id)] = data.answered[id];
                });
                // The server is the source of truth: an answer counts as
                // synced only if the server actually confirms it. Re-derive
                // the flag so anything the server is missing gets resent,
                // even if this device once thought it was saved.
                Object.keys(responses).forEach(function (id) {
                    responses[id].synced = (serverChoice[id] != null);
                });
                saveLocal();
                flushBatch();

                if (!trials.length) {
                    showError('This study has no trials.');
                    return;
                }
                var start = firstUnanswered();
                if (start === -1) { showDone(); return; }
                showEval();
                renderTrial(start);
            })
            .catch(function () {
                showError('Could not load the study. Check your connection ' +
                    'and reload.');
            });
    }

    boot();
}());
