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
        userId: root.dataset.userId || '0',
        csrf: root.dataset.csrf,
        manifestUrl: root.dataset.manifestUrl,
        answeredUrl: root.dataset.answeredUrl,
        batchUrl: root.dataset.batchUrl,
        homeUrl: root.dataset.homeUrl,
    };

    var PRELOAD_AHEAD = 6;       // trials to warm images for
    var RETRY_INTERVAL_MS = 15000;
    // Scope storage per (study, user) so two annotators sharing a browser never
    // load — or sync under the wrong account — each other's answers.
    var STORAGE_KEY = 'iqa_local_' + cfg.studyId + '_' + cfg.userId;

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
    var imageWarnEl = root.querySelector('[data-image-warning]');
    var positionEl = root.querySelector('[data-position]');
    var answeredEl = root.querySelector('[data-answered]');
    var submitBtn = root.querySelector('[data-submit]');
    var prevBtn = root.querySelector('[data-previous]');
    var nextBtn = root.querySelector('[data-next]');
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
    var imagesOk = true;         // false when the current pair failed to load

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
        // Position (which pair you're on) changes as you navigate; the
        // answered count is your overall progress.
        if (positionEl) {
            positionEl.textContent = (current >= 0)
                ? (current + 1) + ' / ' + trials.length
                : '– / ' + trials.length;
        }
        if (answeredEl) answeredEl.textContent = String(doneCount());
    }

    // Next is only allowed from an already-answered pair (never skip an
    // unanswered one) and never past the last pair.
    function canGoNext() {
        return current >= 0 && current < trials.length - 1
            && isDone(trials[current].id);
    }

    // --- Background sync ---------------------------------------------------
    function unsyncedItems() {
        var out = [];
        Object.keys(responses).forEach(function (id) {
            var r = responses[id];
            // Skip rejected pairs (server can never save them) so they don't
            // resend forever.
            if (r && !r.synced && !r.rejected) {
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

    // Reconcile one local answer against what the server holds
    // (serverChoice[id]). First-write-wins: the server is the source of truth
    // for a forward answer, while a deliberate revise keeps resending until the
    // server reflects it. Marking synced by *choice match* (not "we sent it")
    // is what makes an in-flight race safe: if the local choice changed while a
    // stale request was in flight, that request's success never marks the newer
    // answer synced.
    function reconcileOne(id) {
        id = String(id);
        var r = responses[id];
        if (!r) return;
        if (r.rejected) { r.synced = true; return; }   // unsavable: stop trying
        var srv = serverChoice[id];
        if (srv == null) {
            r.synced = false;                 // server lacks it -> resend
        } else if (r.choice === srv) {
            r.synced = true;                  // server already holds our choice
        } else if (!r.revise) {
            r.choice = srv; r.synced = true;  // forward answer lost first-write
        } else {
            r.synced = false;                 // revise not yet accepted -> resend
        }
    }

    // Merge a server choice map ({id: 'A'|'B'}) into local state and reconcile
    // every id it mentions. Returns true if anything changed.
    function mergeServerAnswered(answered) {
        if (!answered) return false;
        var changed = false;
        Object.keys(answered).forEach(function (id) {
            id = String(id);
            if (serverChoice[id] !== answered[id]) {
                serverChoice[id] = answered[id];
                changed = true;
            }
            var before = responses[id] ? responses[id].synced : undefined;
            reconcileOne(id);
            if (responses[id] && responses[id].synced !== before) changed = true;
        });
        return changed;
    }

    var flushInFlight = false;

    // Batch flush of everything still unsynced (per submit / retry / reload /
    // done). Idempotent upsert, so re-sending an item is harmless. Only one
    // flush runs at a time; anything left unsynced is picked up by the next
    // flush (submit/timer/focus), so nothing is lost by skipping.
    function flushBatch() {
        if (flushInFlight) return Promise.resolve(0);
        var items = unsyncedItems();
        if (!items.length) return Promise.resolve(0);
        flushInFlight = true;
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
            return resp.ok ? resp.json() : null;
        }).then(function (data) {
            if (!data) return 0;
            // Pairs the server can never save (deleted stimulus, bad payload):
            // stop resending them so the done screen can't loop forever.
            (data.rejected_ids || []).forEach(function (id) {
                id = String(id);
                if (responses[id]) {
                    responses[id].rejected = true;
                    reconcileOne(id);   // marks synced so it leaves the queue
                }
            });
            // Reconcile against the choice the server actually holds.
            applyServerAnswered(data.answered);
            saveLocal();
            updateProgress();
            return items.length;
        }).catch(function () { return 0; })
          .then(function (n) { flushInFlight = false; return n; });
    }

    // Merge the server's authoritative answers and catch up. If the pair on
    // screen was already answered elsewhere and the annotator hasn't started
    // it, jump to the true position instead of re-showing a done pair.
    function applyServerAnswered(answered) {
        var changed = mergeServerAnswered(answered);
        if (changed) { saveLocal(); updateProgress(); }
        if (!finished && chosen == null
                && current >= 0 && current < trials.length
                && isDone(trials[current].id)) {
            var next = firstUnanswered();
            if (next === -1) showDone();
            else renderTrial(next);
        }
    }

    // Pull the latest server progress and catch up. Called when this tab
    // regains focus/visibility, so a device the annotator left behind (while
    // they worked on another laptop) learns what the server now has.
    function resyncFromServer() {
        if (finished || resyncInFlight) return;
        resyncInFlight = true;
        flushBatch();   // also push anything this device still owes
        fetch(cfg.answeredUrl, { credentials: 'same-origin' })
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (data) {
                if (data) applyServerAnswered(data.answered);
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
    // Submit needs a choice AND both target images actually loaded, so a
    // blank/failed pair can never be "answered" during a network outage.
    function syncSubmitState() {
        submitBtn.disabled =
            !((chosen === 'A' || chosen === 'B') && imagesOk);
    }
    function clearChoice() {
        chosen = null;
        pairBtns.forEach(function (b) { b.classList.remove('active'); });
        choiceWrappers.forEach(function (w) { w.classList.remove('selected'); });
        syncSubmitState();
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
        syncSubmitState();
    }

    // A pair is viewable only if both target images have pixels. Still-loading
    // images are treated as fine (optimistic); an error flips it to broken.
    function evaluateImages() {
        var a = imgEls.a, b = imgEls.b;
        var broken = (a.complete && a.naturalWidth === 0)
            || (b.complete && b.naturalWidth === 0);
        imagesOk = !broken;
        if (imageWarnEl) imageWarnEl.style.display = broken ? '' : 'none';
        syncSubmitState();
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
        imagesOk = true;               // optimistic until an image errors
        imgEls.a.src = t.img_a;
        imgEls.b.src = t.img_b;
        if (imgEls.ref) imgEls.ref.src = t.ref || '';
        setChoice(choiceFor(t.id));    // restore prior answer or clear
        evaluateImages();              // catch already-cached failures
        prevBtn.disabled = (i <= 0);
        nextBtn.disabled = !canGoNext();
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
        // Push everything still unsynced, not just this one — so the first
        // submit after the network returns carries the whole backlog of
        // earlier failed answers, rather than waiting for the retry timer.
        flushBatch();                   // background, non-blocking
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
            // The done-screen fetch is the full authoritative answer set, so
            // rebuild serverChoice from it and reconcile every local answer
            // (choice-aware): anything the server is missing or holds a
            // different value for stays unsynced and gets resent.
            var answered = (data && data.answered) ? data.answered : {};
            var serverSet = new Set(Object.keys(answered).map(String));
            serverChoice = {};
            serverSet.forEach(function (id) { serverChoice[id] = answered[id]; });
            Object.keys(responses).forEach(reconcileOne);
            saveLocal();

            var pending = [];   // never answered anywhere -> must be done
            var unsent = [];    // answered locally, server doesn't have it yet
            var skipped = 0;    // pairs the server rejected (no longer exist)
            trials.forEach(function (t) {
                var id = sid(t);
                if (serverSet.has(id)) return;
                var r = responses[id];
                if (r && r.rejected) { skipped++; return; }
                if (r) unsent.push(t); else pending.push(t);
            });
            renderDone(serverSet.size, pending, unsent, skipped);
        }).catch(function () {
            // Offline at the very end: local answers are still on disk and
            // will resend next time. Be honest about it.
            renderDoneOffline();
        });
    }

    function renderDone(serverCount, pending, unsent, skipped) {
        skipped = skipped || 0;
        var skipNote = skipped
            ? '<p class="local-sync-note">' + skipped + ' pair(s) are no ' +
              'longer part of this study and were skipped.</p>'
            : '';
        if (pending.length === 0 && unsent.length === 0) {
            doneEl.className = 'local-done';
            doneEl.innerHTML =
                '<h2>All done ✓</h2>' +
                '<p><span class="local-done-count">' + serverCount +
                '</span> of <span class="local-done-count">' + trials.length +
                '</span> responses are saved on the server.</p>' + skipNote +
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
                // Don't let Enter bubble to the document handler, or the same
                // keystroke would select *and* submit in one go.
                e.stopPropagation();
                setChoice(w.dataset.imageChoice);
            }
        });
    });
    submitBtn.addEventListener('click', submit);
    prevBtn.addEventListener('click', function () {
        if (current > 0) renderTrial(current - 1);
    });
    nextBtn.addEventListener('click', function () {
        if (canGoNext()) renderTrial(current + 1);
    });
    quitBtn.addEventListener('click', goHome);

    // Re-evaluate viewability whenever a target image loads or fails.
    [imgEls.a, imgEls.b].forEach(function (im) {
        if (!im) return;
        im.addEventListener('load', evaluateImages);
        im.addEventListener('error', evaluateImages);
    });

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
                // synced only if the server holds *its* choice. Re-derive the
                // flag so anything the server is missing or disagrees with gets
                // resent, even if this device once thought it was saved.
                Object.keys(responses).forEach(reconcileOne);
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
