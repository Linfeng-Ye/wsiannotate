import csv
import hashlib
import json
import logging
import random
import string
from urllib.parse import quote

from django.db import transaction
from django.contrib import messages
from django.contrib.admin.views.decorators import (
    staff_member_required,
)
from django.contrib.auth.decorators import (
    login_required, user_passes_test,
)
from django.contrib.auth.models import User
from django.db.models import Count, Max
from django.http import HttpResponse, JsonResponse
from django.urls import reverse
from django.shortcuts import (
    get_object_or_404, redirect, render,
)
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.csrf import csrf_failure as default_csrf_failure
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .forms import BulkUserCreationForm
from .models import (
    Study, MOSStimulus, PairStimulus, QCStimulus,
    MOSResponse, PairResponse, QCResponse, StudyAssignment,
)
from .samplers import (
    get_next_stimulus, get_progress, get_upcoming_stimuli,
    ordered_stimulus_ids, response_model,
)

logger = logging.getLogger('iqa.prefetch')

# How many upcoming trials to warm ahead of the annotator.
PREFETCH_WINDOW = 8
PREFETCH_MAX_IMAGES = 24


class _SafeCsvWriter:
    """Escape cells that spreadsheet programs could execute as formulas."""

    def __init__(self, response):
        self.writer = csv.writer(response)

    def writerow(self, row):
        safe_row = []
        for value in row:
            text = '' if value is None else str(value)
            if text.startswith(('=', '+', '-', '@', '\t', '\r')):
                text = "'" + text
            safe_row.append(text)
        return self.writer.writerow(safe_row)


def _download_filename(value):
    return ''.join(
        char if char.isalnum() or char in '._-' else '_'
        for char in str(value)
    ) or 'responses'


def _image_url(request, image):
    if image is None:
        return None
    return request.build_absolute_uri(image.fname.url)


def _add_image_url(request, urls, seen, image):
    url = _image_url(request, image)
    if url and url not in seen:
        urls.append(url)
        seen.add(url)


def _prefetch_image_urls(request, study, stimuli):
    urls = []
    seen = set()
    if study.mode in (Study.MODE_MOS, Study.MODE_QC):
        for stimulus in stimuli:
            trial_urls = []
            trial_seen = set(seen)
            _add_image_url(
                request, trial_urls, trial_seen, stimulus.image,
            )
            _add_image_url(
                request, trial_urls, trial_seen, stimulus.reference,
            )
            if len(urls) + len(trial_urls) > PREFETCH_MAX_IMAGES:
                break
            urls.extend(trial_urls)
            seen.update(trial_urls)
    else:
        for stimulus in stimuli:
            trial_urls = []
            trial_seen = set(seen)
            _add_image_url(
                request, trial_urls, trial_seen, stimulus.reference_a,
            )
            _add_image_url(
                request, trial_urls, trial_seen, stimulus.reference_b,
            )
            _add_image_url(
                request, trial_urls, trial_seen, stimulus.image_a,
            )
            _add_image_url(
                request, trial_urls, trial_seen, stimulus.image_b,
            )
            if len(urls) + len(trial_urls) > PREFETCH_MAX_IMAGES:
                break
            urls.extend(trial_urls)
            seen.update(trial_urls)
    return urls


def _history_key(study_id):
    return f'iqa_previous_stimuli_{study_id}'


def _clean_history(raw_history):
    history = []
    for item in raw_history or []:
        try:
            history.append(int(item))
        except (TypeError, ValueError):
            continue
    return history


def _history_for_previous(request, study, current_stimulus_id=None):
    history = _clean_history(
        request.session.get(_history_key(study.id), [])
    )
    if current_stimulus_id is not None:
        try:
            current_stimulus_id = int(current_stimulus_id)
        except (TypeError, ValueError):
            current_stimulus_id = None
    while (
        current_stimulus_id is not None
        and history
        and history[-1] == current_stimulus_id
    ):
        history.pop()
    return history


def _answered_stimulus_ids(study, user):
    return set(
        response_model(study).objects.filter(
            user=user, stimulus__study=study,
        ).values_list('stimulus_id', flat=True)
    )


def _previous_answered_from_database(
    study, user, current_stimulus_id=None,
    exclude_ids=None,
):
    answered_ids = _answered_stimulus_ids(study, user)
    exclude_ids = set(exclude_ids or [])
    try:
        current_stimulus_id = int(current_stimulus_id)
    except (TypeError, ValueError):
        current_stimulus_id = None

    ordered_ids = ordered_stimulus_ids(study, user)
    if current_stimulus_id in ordered_ids:
        candidates = ordered_ids[
            :ordered_ids.index(current_stimulus_id)
        ]
    else:
        candidates = ordered_ids

    for stimulus_id in reversed(candidates):
        if stimulus_id in answered_ids and stimulus_id not in exclude_ids:
            return stimulus_id
    return None


def _can_go_previous(request, study, current_stimulus_id=None):
    history = _history_for_previous(
        request, study, current_stimulus_id,
    )
    if history:
        return True
    return _previous_answered_from_database(
        study,
        request.user,
        current_stimulus_id=current_stimulus_id,
        exclude_ids=history,
    ) is not None


def _remember_previous_stimulus(request, study, stimulus_id):
    try:
        stimulus_id = int(stimulus_id)
    except (TypeError, ValueError):
        return
    key = _history_key(study.id)
    history = _clean_history(request.session.get(key, []))
    if not history or history[-1] != stimulus_id:
        history.append(stimulus_id)
    request.session[key] = history[-100:]
    request.session.modified = True


def _pop_previous_stimulus(request, study, current_stimulus_id=None):
    key = _history_key(study.id)
    history = _history_for_previous(
        request, study, current_stimulus_id,
    )
    if history:
        previous_id = history.pop()
    else:
        previous_id = _previous_answered_from_database(
            study,
            request.user,
            current_stimulus_id=current_stimulus_id,
        )
    request.session[key] = history
    request.session.modified = True
    return previous_id


def _evaluation_url(study, stimulus_id):
    if study.mode == Study.MODE_QC:
        # QC has no per-stimulus page; the browser drives the sequence.
        return reverse(
            'iqa:local_run', kwargs={'study_id': study.id},
        )
    if study.mode == Study.MODE_MOS:
        return reverse(
            'iqa:mos_evaluation',
            kwargs={
                'study_id': study.id,
                'stimulus_id': stimulus_id,
            },
        )
    return reverse(
        'iqa:pair_evaluation',
        kwargs={
            'study_id': study.id,
            'stimulus_id': stimulus_id,
        },
    )


def login_redirect(request):
    return redirect('iqa:home')


def csrf_failure(request, reason=''):
    """Recover from a stale login token instead of dead-ending on a 403.

    Both ``auth.login()`` and ``auth.logout()`` call ``rotate_token()``, so
    logging in anywhere in a browser silently invalidates the token embedded
    in any *other* login page already rendered -- a second tab, or a page the
    browser restored from a previous session. Submitting that form gives
    "CSRF token from POST incorrect", which annotators see as a raw yellow
    403 and work around by pressing Back and retrying. Do that for them.

    Only the login page is rewritten. Everything else keeps Django's default
    403 -- in particular the local-first ``submit-batch`` endpoint, whose
    client expects JSON and has its own retry path, so quietly redirecting it
    would hide a real failure.
    """
    logger.warning(
        'CSRF failure on %s (%s)', request.path, reason,
    )
    login_url = reverse('iqa:login')
    if request.path != login_url:
        return default_csrf_failure(request, reason=reason)

    # Already signed in elsewhere: the login they were attempting is moot.
    if request.user.is_authenticated:
        return redirect('iqa:home')

    next_url = request.GET.get('next') or request.POST.get('next')
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        login_url = f'{login_url}?next={quote(next_url)}'
    messages.warning(
        request,
        'This page had been open a while, so we refreshed it. '
        'Nothing was submitted — please sign in again.',
    )
    return redirect(login_url)


@login_required
def home(request):
    studies = Study.objects.filter(is_active=True)
    study_cards = []
    for study in studies:
        progress = get_progress(study, request.user)
        done = progress['done']
        total = progress['total']
        study_cards.append({
            'study': study,
            'progress': progress,
            'is_started': done > 0,
            'is_completed': total > 0 and done >= total,
        })
    return render(
        request, 'iqa/home.html',
        {'study_cards': study_cards},
    )


def _next_url_for_study(study, user):
    stimulus = get_next_stimulus(study, user)
    if stimulus is None:
        return None
    return _evaluation_url(study, stimulus.id)


@login_required
@require_POST
def next_stimulus(request):
    study_id = request.POST.get('study_id')
    study = get_object_or_404(Study, id=study_id)
    if _local_mode_available(study):
        return redirect('iqa:local_run', study_id=study.id)
    stimulus = get_next_stimulus(study, request.user)

    if stimulus is None:
        return render(
            request, 'iqa/study_done.html',
            {
                'study': study,
                'can_go_previous': _can_go_previous(request, study),
            },
        )

    if study.mode == Study.MODE_MOS:
        return redirect(
            'iqa:mos_evaluation',
            study_id=study.id,
            stimulus_id=stimulus.id,
        )
    return redirect(
        'iqa:pair_evaluation',
        study_id=study.id,
        stimulus_id=stimulus.id,
    )


@login_required
@require_POST
def previous_stimulus(request):
    study = get_object_or_404(
        Study, id=request.POST.get('study_id'),
    )
    current_stimulus_id = request.POST.get('stimulus_id')
    previous_id = _pop_previous_stimulus(
        request, study, current_stimulus_id,
    )
    if previous_id is None:
        if current_stimulus_id:
            return redirect(_evaluation_url(study, current_stimulus_id))
        return redirect('iqa:home')
    return redirect(_evaluation_url(study, previous_id))


@login_required
def study_done(request, study_id):
    study = get_object_or_404(Study, id=study_id)
    return render(
        request, 'iqa/study_done.html',
        {
            'study': study,
            'can_go_previous': _can_go_previous(request, study),
        },
    )


@login_required
@require_GET
def prefetch(request, study_id):
    """Return CDN image URLs for the next few unanswered trials.

    Small JSON manifest (metadata only) used by prefetch.js to warm the
    browser HTTP cache a few trials ahead of the annotator.
    """
    study = get_object_or_404(Study, id=study_id, is_active=True)
    try:
        current_id = int(request.GET.get('current'))
    except (TypeError, ValueError):
        current_id = None
    upcoming = get_upcoming_stimuli(
        study, request.user, current_id, PREFETCH_WINDOW,
    )
    urls = _prefetch_image_urls(request, study, upcoming)
    return JsonResponse({'images': urls})


@csrf_exempt
@login_required
@require_POST
def prefetch_report(request):
    """Log prefetch success/failure counts sent via navigator.sendBeacon.

    Best-effort metrics only; never writes to the database. CSRF-exempt
    because sendBeacon cannot attach the CSRF token, and the endpoint has
    no side effects beyond logging.
    """
    if request.META.get('CONTENT_LENGTH', '').isdigit():
        if int(request.META['CONTENT_LENGTH']) > 2048:
            return HttpResponse(status=204)
    try:
        payload = json.loads((request.body or b'').decode('utf-8') or '{}')
    except (ValueError, UnicodeDecodeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    def bounded_int(value, maximum):
        try:
            return max(0, min(int(value), maximum))
        except (TypeError, ValueError):
            return 0

    study_id = bounded_int(payload.get('study'), 2_147_483_647)
    if not Study.objects.filter(id=study_id, is_active=True).exists():
        study_id = 0
    ok = bounded_int(payload.get('ok'), 24)
    fail = bounded_int(payload.get('fail'), 24)
    logger.info(
        'prefetch report user_id=%d study_id=%d ok=%d fail=%d',
        request.user.id, study_id, ok, fail,
    )
    return HttpResponse(status=204)


@login_required
def mos_evaluation(request, study_id, stimulus_id):
    study = get_object_or_404(
        Study, id=study_id, mode=Study.MODE_MOS,
    )
    stimulus = get_object_or_404(
        MOSStimulus, id=stimulus_id, study=study,
    )
    existing = MOSResponse.objects.filter(
        stimulus=stimulus, user=request.user,
    ).first()
    progress = get_progress(study, request.user)
    scale_range = list(
        range(study.scale_min, study.scale_max + 1)
    )

    return render(
        request, 'iqa/mos_evaluation.html', {
            'study': study,
            'stimulus': stimulus,
            'existing': existing,
            'progress': progress,
            'scale_range': scale_range,
            'can_go_previous': _can_go_previous(
                request, study, stimulus.id,
            ),
        },
    )


def _refs_match(ref_a, ref_b) -> bool:
    if ref_a is None and ref_b is None:
        return True
    if ref_a is None or ref_b is None:
        return False
    if ref_a.pk == ref_b.pk:
        return True
    return str(ref_a.fname) == str(ref_b.fname)


def _pair_swap(study_id, user_id, stimulus_id) -> bool:
    """Deterministic A/B swap for a (study, user, pair).

    Local mode needs the swap to be stable across reloads and computable
    up-front for the whole manifest, so it is seeded from the identifiers
    rather than drawn randomly and stored in the session.
    """
    raw = f'swap:{study_id}:{user_id}:{stimulus_id}'
    digest = hashlib.sha256(raw.encode('utf-8')).hexdigest()
    return bool(int(digest[:8], 16) & 1)


def _record_pair_response(user, stimulus, display_choice, swap, revise=True):
    """Record one 2AFC response for (stimulus, user).

    ``display_choice`` is the on-screen A/B the annotator clicked; ``swap``
    is whether A/B were shown flipped, so we can recover the underlying
    choice and the exact images shown.

    ``revise`` controls what happens when the server already has an answer
    for this pair. A deliberate revision (the annotator navigated back to a
    pair they know they answered and changed it) overwrites. A *forward*
    answer does not: if the pair is already answered — e.g. on another
    device the annotator left open — the existing answer is kept, so a stale
    laptop can never clobber work done elsewhere. First write wins; only an
    explicit revise replaces it. Returns True if written, False if kept.
    """
    choice = display_choice
    if swap:
        choice = 'B' if display_choice == 'A' else 'A'
        shown_image_a = stimulus.image_b
        shown_image_b = stimulus.image_a
        shown_reference_a = stimulus.reference_b
        shown_reference_b = stimulus.reference_a
    else:
        shown_image_a = stimulus.image_a
        shown_image_b = stimulus.image_b
        shown_reference_a = stimulus.reference_a
        shown_reference_b = stimulus.reference_b

    defaults = {
        'choice': choice,
        'display_choice': display_choice,
        'was_swapped': swap,
        'shown_image_a': str(shown_image_a.fname),
        'shown_image_b': str(shown_image_b.fname),
        'shown_reference_a': (
            str(shown_reference_a.fname) if shown_reference_a else ''
        ),
        'shown_reference_b': (
            str(shown_reference_b.fname) if shown_reference_b else ''
        ),
    }

    return _upsert_response(
        PairResponse, user, stimulus, defaults, revise,
    )


def _record_qc_response(user, stimulus, choice, revise=True):
    """Record one QC yes/no verdict for (stimulus, user).

    Same first-write-wins rule as ``_record_pair_response``: a forward answer
    never clobbers an answer the server already holds (which may have come
    from another device), while a deliberate revision does.
    """
    defaults = {
        'choice': choice,
        'shown_image': str(stimulus.image.fname),
        'shown_reference': (
            str(stimulus.reference.fname) if stimulus.reference else ''
        ),
    }
    return _upsert_response(
        QCResponse, user, stimulus, defaults, revise,
    )


def _upsert_response(model, user, stimulus, defaults, revise):
    """Create the response, or overwrite it only when ``revise`` is set.

    Returns True if the database now holds ``defaults``, False if an existing
    answer was deliberately kept.
    """
    obj, created = model.objects.get_or_create(
        stimulus=stimulus, user=user, defaults=defaults,
    )
    if created:
        return True
    if not revise:
        # Forward answer to an already-answered trial: keep what is there.
        return False
    for field, value in defaults.items():
        setattr(obj, field, value)
    obj.save(update_fields=list(defaults.keys()))
    return True


@login_required
def pair_evaluation(request, study_id, stimulus_id):
    study = get_object_or_404(
        Study, id=study_id, mode=Study.MODE_2AFC,
    )
    if _local_mode_available(study):
        return redirect('iqa:local_run', study_id=study.id)
    stimulus = get_object_or_404(
        PairStimulus, id=stimulus_id, study=study,
    )
    existing = PairResponse.objects.filter(
        stimulus=stimulus, user=request.user,
    ).first()
    progress = get_progress(study, request.user)

    sess_key = f'pair_swap_{study.id}_{stimulus.id}'
    swap = request.session.get(sess_key)
    if swap is None:
        if existing is not None and existing.display_choice:
            swap = existing.was_swapped
        else:
            swap = bool(random.getrandbits(1))
        request.session[sess_key] = swap

    if swap:
        img_a = stimulus.image_b
        img_b = stimulus.image_a
        ref_a = stimulus.reference_b
        ref_b = stimulus.reference_a
    else:
        img_a = stimulus.image_a
        img_b = stimulus.image_b
        ref_a = stimulus.reference_a
        ref_b = stimulus.reference_b

    existing_display_choice = None
    if existing is not None:
        if existing.display_choice:
            existing_display_choice = existing.display_choice
        elif not swap:
            existing_display_choice = existing.choice
        else:
            existing_display_choice = (
                'B' if existing.choice == 'A' else 'A'
            )

    force_fallback = request.GET.get('fallback') == '1'
    want_shared_ref = (
        study.pair_shared_ref_layout and not force_fallback
    )
    refs_match = _refs_match(ref_a, ref_b)
    use_shared_ref = want_shared_ref and refs_match
    ref_mismatch_error = want_shared_ref and not refs_match

    shared_ref = ref_a if use_shared_ref else None

    return render(
        request, 'iqa/pair_evaluation.html', {
            'study': study,
            'stimulus': stimulus,
            'existing': existing,
            'existing_display_choice': existing_display_choice,
            'progress': progress,
            'img_a': img_a,
            'img_b': img_b,
            'ref_a': ref_a,
            'ref_b': ref_b,
            'swap': swap,
            'use_shared_ref': use_shared_ref,
            'shared_ref': shared_ref,
            'ref_mismatch_error': ref_mismatch_error,
            'user_identifier': request.user.username,
            'can_go_previous': _can_go_previous(
                request, study, stimulus.id,
            ),
        },
    )


@login_required
@require_POST
def evaluation_submit(request):
    study_id = request.POST.get('study_id')
    stimulus_id = request.POST.get('stimulus_id')
    study = get_object_or_404(Study, id=study_id)
    is_ajax = (
        request.headers.get('x-requested-with')
        == 'XMLHttpRequest'
    )

    if study.mode == Study.MODE_MOS:
        stimulus = get_object_or_404(
            MOSStimulus, id=stimulus_id, study=study,
        )
        try:
            score = int(request.POST.get('score', ''))
        except (TypeError, ValueError):
            if is_ajax:
                return JsonResponse(
                    {
                        'success': False,
                        'error': 'Invalid score.',
                    },
                    status=400,
                )
            return redirect(
                'iqa:mos_evaluation',
                study_id=study.id,
                stimulus_id=stimulus.id,
            )
        if score < study.scale_min or score > study.scale_max:
            if is_ajax:
                return JsonResponse(
                    {
                        'success': False,
                        'error': 'Score out of range.',
                    },
                    status=400,
                )
            return redirect(
                'iqa:mos_evaluation',
                study_id=study.id,
                stimulus_id=stimulus.id,
            )
        MOSResponse.objects.update_or_create(
            stimulus=stimulus, user=request.user,
            defaults={'score': score},
        )
    else:
        stimulus = get_object_or_404(
            PairStimulus, id=stimulus_id, study=study,
        )
        display_choice = request.POST.get('choice')
        if display_choice not in (
            PairResponse.CHOICE_A,
            PairResponse.CHOICE_B,
        ):
            if is_ajax:
                return JsonResponse(
                    {
                        'success': False,
                        'error': 'Invalid choice.',
                    },
                    status=400,
                )
            return redirect(
                'iqa:pair_evaluation',
                study_id=study.id,
                stimulus_id=stimulus.id,
            )
        swap = request.POST.get('swap') == '1'
        _record_pair_response(
            request.user, stimulus, display_choice, swap,
        )
        sess_key = f'pair_swap_{study.id}_{stimulus.id}'
        request.session.pop(sess_key, None)

    _remember_previous_stimulus(
        request, study, stimulus.id,
    )

    if is_ajax:
        progress = get_progress(study, request.user)
        next_url = _next_url_for_study(study, request.user)
        done_url = reverse(
            'iqa:study_done',
            kwargs={'study_id': study.id},
        )
        data = {
            'success': True,
            'completed': next_url is None,
            'progress': progress,
        }
        if next_url is None:
            data['done_url'] = done_url
        else:
            data['next_url'] = next_url
        return JsonResponse(data)

    return render(
        request,
        'iqa/next_stimulus_redirect.html',
        {'study': study},
    )


# ---------------------------------------------------------------------------
# Local-first evaluation (2AFC and QC)
#
# The browser downloads the whole study once, drives the trial sequence
# itself, records each answer to localStorage, and syncs to the server in
# the background. The server stays the source of truth via idempotent
# upserts, so a lost background request just re-appears as an unanswered
# trial (or is re-sent from localStorage on reload / page close).
#
# 2AFC opts in per study via ``use_local_mode``; QC has no server-driven
# page at all, so it always runs here.
# ---------------------------------------------------------------------------

LOCAL_TEMPLATES = {
    Study.MODE_2AFC: 'iqa/pair_local.html',
    Study.MODE_QC: 'iqa/qc_local.html',
}


def _local_mode_available(study) -> bool:
    if study.mode == Study.MODE_QC:
        return True
    return (
        study.mode == Study.MODE_2AFC
        and study.use_local_mode
    )


def _answered_choices(study, user, stimulus_ids=None) -> dict:
    """This user's answers as ``{stimulus_id: choice}`` for a local study.

    For 2AFC the value is the *display* choice (the on-screen A/B), which is
    what the client stores; for QC it is the Y/N verdict, which has no
    display/underlying distinction because QC never swaps.
    """
    scope = response_model(study).objects.filter(
        user=user, stimulus__study=study,
    )
    if stimulus_ids is not None:
        scope = scope.filter(stimulus_id__in=stimulus_ids)
    if study.mode == Study.MODE_QC:
        return {
            str(stimulus_id): choice
            for stimulus_id, choice in scope.values_list(
                'stimulus_id', 'choice',
            )
        }
    return {
        str(stimulus_id): display_choice or choice
        for stimulus_id, display_choice, choice in scope.values_list(
            'stimulus_id', 'display_choice', 'choice',
        )
    }


@login_required
def local_run(request, study_id):
    study = get_object_or_404(Study, id=study_id, is_active=True)
    if not _local_mode_available(study):
        # Fall back to the classic server-driven flow.
        return redirect('iqa:home')
    return render(
        request, LOCAL_TEMPLATES[study.mode], {'study': study},
    )


def _pair_trials(request, study, user, order):
    stimuli = {
        s.id: s
        for s in study.pair_stimuli.select_related(
            'image_a', 'image_b', 'reference_a', 'reference_b',
        )
    }
    trials = []
    for stimulus_id in order:
        stimulus = stimuli.get(stimulus_id)
        if stimulus is None:
            continue
        swap = _pair_swap(study.id, user.id, stimulus_id)
        if swap:
            img_a, img_b = stimulus.image_b, stimulus.image_a
            ref = stimulus.reference_b
        else:
            img_a, img_b = stimulus.image_a, stimulus.image_b
            ref = stimulus.reference_a
        trials.append({
            'id': stimulus_id,
            'swap': swap,
            'img_a': _image_url(request, img_a),
            'img_b': _image_url(request, img_b),
            'ref': _image_url(request, ref),
        })
    return trials


def _qc_trials(request, study, order):
    stimuli = {
        s.id: s
        for s in study.qc_stimuli.select_related('image', 'reference')
    }
    trials = []
    for stimulus_id in order:
        stimulus = stimuli.get(stimulus_id)
        if stimulus is None:
            continue
        trials.append({
            'id': stimulus_id,
            'img': _image_url(request, stimulus.image),
            'ref': _image_url(request, stimulus.reference),
        })
    return trials


@login_required
@require_GET
def study_manifest(request, study_id):
    """Everything the browser needs to run the whole study offline.

    Returns the trials in this user's deterministic order (2AFC trials come
    with the swap already applied to the image URLs) plus the set of answers
    the server already holds, so the client can resume and reconcile.
    """
    study = get_object_or_404(Study, id=study_id, is_active=True)
    if not _local_mode_available(study):
        return JsonResponse({'error': 'Local mode unavailable.'}, status=404)

    user = request.user
    order = ordered_stimulus_ids(study, user)
    if study.mode == Study.MODE_QC:
        trials = _qc_trials(request, study, order)
    else:
        trials = _pair_trials(request, study, user, order)

    return JsonResponse({
        'study': {
            'id': study.id,
            'name': study.name,
            'mode': study.mode,
            'prompt': study.prompt,
            'zoom_enabled': study.zoom_enabled,
            'zoom_factor': study.zoom_factor,
        },
        'trials': trials,
        'answered': _answered_choices(study, user),
        'total': len(trials),
    })


@login_required
@require_GET
def study_answered(request, study_id):
    """The server's answers for this user, as ``{stimulus_id: choice}``.

    Used by the client to verify completeness on the done screen and to
    reconcile after a reload without downloading the whole manifest again.
    Returning the *choice* (not just the id) lets the client tell whether the
    server actually holds its local answer, so a value that differs — e.g. a
    trial answered on another device, or an answer a background race left
    stale — is corrected instead of silently trusted.
    """
    study = get_object_or_404(Study, id=study_id, is_active=True)
    if not _local_mode_available(study):
        return JsonResponse({'error': 'Local mode unavailable.'}, status=404)
    return JsonResponse({
        'answered': _answered_choices(study, request.user),
    })


@login_required
@require_POST
def evaluation_submit_batch(request):
    """Upsert many local-mode answers at once. Idempotent on (stimulus, user).

    Serves both 2AFC (A/B choices, with the swap flag) and QC (Y/N verdicts);
    the study's mode decides which stimuli and choices are valid.

    Accepts either a JSON body (background flush via fetch) or a form field
    ``payload`` containing the JSON (page-close flush via sendBeacon, which
    can only send form/blob bodies and carries the CSRF token as a form
    field). CSRF protection stays on for both paths.
    """
    raw = request.POST.get('payload')
    if raw is None:
        try:
            data = json.loads((request.body or b'').decode('utf-8') or '{}')
        except (ValueError, UnicodeDecodeError):
            data = {}
    else:
        try:
            data = json.loads(raw)
        except ValueError:
            data = {}
    if not isinstance(data, dict):
        data = {}

    study = get_object_or_404(
        Study, id=data.get('study_id'),
        mode__in=[Study.MODE_2AFC, Study.MODE_QC],
    )
    is_qc = study.mode == Study.MODE_QC
    responses = data.get('responses')
    if not isinstance(responses, list):
        responses = []

    wanted_ids = []
    for item in responses:
        if isinstance(item, dict):
            try:
                wanted_ids.append(int(item.get('stimulus_id')))
            except (TypeError, ValueError):
                continue
    if is_qc:
        valid_choices = (QCResponse.CHOICE_YES, QCResponse.CHOICE_NO)
        stimuli = {
            s.id: s
            for s in study.qc_stimuli.filter(
                id__in=wanted_ids,
            ).select_related('image', 'reference')
        }
    else:
        valid_choices = (PairResponse.CHOICE_A, PairResponse.CHOICE_B)
        stimuli = {
            s.id: s
            for s in study.pair_stimuli.filter(
                id__in=wanted_ids,
            ).select_related(
                'image_a', 'image_b', 'reference_a', 'reference_b',
            )
        }

    saved = 0
    kept = 0
    touched_ids = []      # trials we actually processed (saved or kept)
    rejected_ids = []     # trials we can never save (unknown stimulus/bad choice)
    with transaction.atomic():
        for item in responses:
            if not isinstance(item, dict):
                continue
            try:
                stimulus_id = int(item.get('stimulus_id'))
            except (TypeError, ValueError):
                continue
            choice = item.get('choice')
            stimulus = stimuli.get(stimulus_id)
            if choice not in valid_choices or stimulus is None:
                # Unknown/deleted stimulus or a malformed choice: this item can
                # never be persisted. Tell the client so it stops resending it
                # forever (otherwise the done screen loops on "Upload now").
                rejected_ids.append(str(stimulus_id))
                continue
            revise = bool(item.get('revise'))
            if is_qc:
                wrote = _record_qc_response(
                    request.user, stimulus, choice, revise=revise,
                )
            else:
                wrote = _record_pair_response(
                    request.user, stimulus, choice,
                    bool(item.get('swap')), revise=revise,
                )
            if wrote:
                saved += 1
            else:
                kept += 1
            touched_ids.append(stimulus_id)

    # Hand back the choice the server now holds so the client can reconcile
    # (mark an answer synced only when the server truly has *its* value). When
    # a write was kept, this client is likely behind another device, so return
    # the full answered set for a complete catch-up; otherwise just the trials
    # in this batch keeps the response small on the hot submit path.
    answered = _answered_choices(
        study, request.user,
        stimulus_ids=None if kept else touched_ids,
    )

    return JsonResponse({
        'success': True,
        'saved': saved,
        'kept': kept,
        'answered': answered,
        'rejected_ids': rejected_ids,
    })


def _gen_password(length=12) -> str:
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))


@user_passes_test(lambda u: u.is_superuser)
def bulk_create_users(request):
    if request.method == 'POST':
        form = BulkUserCreationForm(request.POST)
        if form.is_valid():
            created = []
            raw = form.cleaned_data['usernames']
            if raw and raw.strip():
                for name in raw.splitlines():
                    name = name.strip()
                    if not name:
                        continue
                    if User.objects.filter(
                        username=name,
                    ).exists():
                        continue
                    pw = _gen_password()
                    User.objects.create_user(
                        username=name, password=pw,
                    )
                    created.append((name, pw))

            num = form.cleaned_data.get(
                'number_of_users',
            )
            if num:
                counter = User.objects.count()
                for _ in range(num):
                    uname = f'user{counter + 1}'
                    while User.objects.filter(
                        username=uname,
                    ).exists():
                        counter += 1
                        uname = f'user{counter + 1}'
                    pw = _gen_password()
                    User.objects.create_user(
                        username=uname, password=pw,
                    )
                    created.append((uname, pw))
                    counter += 1

            request.session['created_users'] = created
            return redirect('iqa:user_creation_results')
    else:
        form = BulkUserCreationForm()

    return render(
        request, 'iqa/bulk_create_users.html',
        {'form': form},
    )


@user_passes_test(lambda u: u.is_superuser)
def user_creation_results(request):
    created = request.session.pop('created_users', [])
    return render(
        request, 'iqa/user_creation_results.html',
        {'created_users': created},
    )


@staff_member_required
def view_responses(request):
    study_id = request.GET.get('study_id')
    user_id = request.GET.get('user_id')
    studies = Study.objects.all()
    users = User.objects.filter(is_active=True).order_by('username')
    mos_data = []
    pair_data = []
    qc_data = []
    study = None
    selected_user = None

    if user_id:
        selected_user = get_object_or_404(User, id=user_id)

    if study_id:
        study = get_object_or_404(Study, id=study_id)
        if study.mode == Study.MODE_QC:
            qc_data = QCResponse.objects.filter(
                stimulus__study=study,
            ).select_related(
                'stimulus__image', 'stimulus__reference', 'user',
            ).order_by('stimulus__order', 'user__username')
            if selected_user is not None:
                qc_data = qc_data.filter(user=selected_user)
        elif study.mode == Study.MODE_MOS:
            mos_data = MOSResponse.objects.filter(
                stimulus__study=study,
            ).select_related(
                'stimulus__image', 'stimulus__reference',
                'user',
            ).order_by('stimulus__order', 'user__username')
            if selected_user is not None:
                mos_data = mos_data.filter(user=selected_user)
        else:
            pair_data = PairResponse.objects.filter(
                stimulus__study=study,
            ).select_related(
                'stimulus__image_a',
                'stimulus__image_b',
                'stimulus__reference_a',
                'stimulus__reference_b',
                'user',
            ).order_by('stimulus__order', 'user__username')
            if selected_user is not None:
                pair_data = pair_data.filter(user=selected_user)

    return render(
        request, 'iqa/view_responses.html', {
            'studies': studies,
            'users': users,
            'study': study,
            'selected_user': selected_user,
            'mos_data': mos_data,
            'pair_data': pair_data,
            'qc_data': qc_data,
        },
    )


@login_required
def export_own_responses_csv(request, study_id: int):
    study = get_object_or_404(
        Study, id=study_id, allow_self_export=True,
    )
    response = HttpResponse(content_type='text/csv')
    fname = _download_filename(study.name)
    response['Content-Disposition'] = (
        f'attachment; filename="{fname}_my_responses.csv"'
    )
    _write_study_responses(
        _SafeCsvWriter(response), study, user=request.user,
    )
    return response


def _write_study_responses(writer, study, user=None):
    """Write a study's responses to ``writer``, optionally for one user.

    Same column layout whether or not ``user`` is set, so a per-annotator
    export is a strict row-subset of the whole-study export.
    """
    if study.mode == Study.MODE_QC:
        writer.writerow([
            'user', 'stimulus_order',
            'image', 'reference', 'choice',
            'shown_image', 'shown_reference',
        ])
        rows = QCResponse.objects.filter(
            stimulus__study=study,
        ).select_related(
            'stimulus__image', 'stimulus__reference', 'user',
        ).order_by('stimulus__order', 'user__username')
        if user is not None:
            rows = rows.filter(user=user)
        for r in rows:
            ref = ''
            if r.stimulus.reference:
                ref = str(r.stimulus.reference.fname)
            writer.writerow([
                r.user.username,
                r.stimulus.order,
                str(r.stimulus.image.fname),
                ref,
                r.choice,
                r.shown_image,
                r.shown_reference,
            ])
    elif study.mode == Study.MODE_MOS:
        writer.writerow([
            'user', 'stimulus_order',
            'image', 'reference', 'score',
        ])
        rows = MOSResponse.objects.filter(
            stimulus__study=study,
        ).select_related(
            'stimulus__image', 'stimulus__reference', 'user',
        ).order_by('stimulus__order', 'user__username')
        if user is not None:
            rows = rows.filter(user=user)
        for r in rows:
            ref = ''
            if r.stimulus.reference:
                ref = str(r.stimulus.reference.fname)
            writer.writerow([
                r.user.username,
                r.stimulus.order,
                str(r.stimulus.image.fname),
                ref,
                r.score,
            ])
    else:
        writer.writerow([
            'user', 'stimulus_order',
            'image_a', 'image_b',
            'reference_a', 'reference_b', 'choice',
            'display_choice', 'was_swapped',
            'shown_image_a', 'shown_image_b',
            'shown_reference_a', 'shown_reference_b',
        ])
        rows = PairResponse.objects.filter(
            stimulus__study=study,
        ).select_related(
            'stimulus__image_a', 'stimulus__image_b',
            'stimulus__reference_a', 'stimulus__reference_b',
            'user',
        ).order_by('stimulus__order', 'user__username')
        if user is not None:
            rows = rows.filter(user=user)
        for r in rows:
            ref_a = ''
            if r.stimulus.reference_a:
                ref_a = str(r.stimulus.reference_a.fname)
            ref_b = ''
            if r.stimulus.reference_b:
                ref_b = str(r.stimulus.reference_b.fname)
            writer.writerow([
                r.user.username,
                r.stimulus.order,
                str(r.stimulus.image_a.fname),
                str(r.stimulus.image_b.fname),
                ref_a, ref_b, r.choice,
                r.display_choice,
                r.was_swapped,
                r.shown_image_a,
                r.shown_image_b,
                r.shown_reference_a,
                r.shown_reference_b,
            ])


@staff_member_required
def export_responses_csv(request, study_id):
    study = get_object_or_404(Study, id=study_id)
    response = HttpResponse(content_type='text/csv')
    fname = _download_filename(study.name)
    response['Content-Disposition'] = (
        f'attachment; filename="{fname}_responses.csv"'
    )
    _write_study_responses(_SafeCsvWriter(response), study)
    return response


@staff_member_required
def export_study_user_csv(request, study_id, user_id):
    """One annotator's responses for one study, downloaded on its own."""
    study = get_object_or_404(Study, id=study_id)
    user = get_object_or_404(User, id=user_id)
    response = HttpResponse(content_type='text/csv')
    fname = (
        f'{_download_filename(study.name)}'
        f'_{_download_filename(user.username)}'
    )
    response['Content-Disposition'] = (
        f'attachment; filename="{fname}_responses.csv"'
    )
    _write_study_responses(_SafeCsvWriter(response), study, user=user)
    return response


@staff_member_required
def annotator_progress(request):
    """Staff dashboard: every user's progress across the studies that matter.

    Retired and never-used studies would only add columns of ``0/4000 not
    started`` for every rater, so a study shows up while it is active or
    actually holds answers. Deactivating a study therefore tidies the board
    without ever hiding data that exists.
    """
    answered_study_ids = set()
    for model in (PairResponse, MOSResponse, QCResponse):
        answered_study_ids.update(
            model.objects
            .values_list('stimulus__study_id', flat=True)
            .distinct()
        )
    studies = [
        s for s in Study.objects.all().order_by('id')
        if s.is_active or s.id in answered_study_ids
    ]
    users = list(
        User.objects.filter(is_active=True).order_by('username')
    )
    totals = {s.id: s.stimulus_count() for s in studies}

    # done count + last activity per (user, study), across all three modes.
    done = {}
    for model in (PairResponse, MOSResponse, QCResponse):
        for row in model.objects.values(
            'user_id', 'stimulus__study_id',
        ).annotate(n=Count('id'), last=Max('timestamp')):
            key = (row['user_id'], row['stimulus__study_id'])
            done[key] = (row['n'], row['last'])

    # Per-rater assignments: an assigned rater's denominator is their own
    # stimulus count, and their "done" only counts answers within that set.
    # Unassigned users keep the full-study total (backward-compatible).
    # 2AFC assignments live on pair_stimuli and QC ones on qc_stimuli, so the
    # study's mode picks which side to read (and which responses to count).
    assigned = {}  # (user_id, study_id) -> set(stimulus_ids)
    for sa in StudyAssignment.objects.select_related('study').prefetch_related(
        'pair_stimuli', 'qc_stimuli',
    ):
        assigned[(sa.user_id, sa.study_id)] = set(
            sa.stimuli().values_list('id', flat=True)
        )
    assigned_done = {}  # (user_id, study_id) -> answers within assignment
    gated_study_ids = {sid for (_uid, sid) in assigned}
    if gated_study_ids:
        for model in (PairResponse, QCResponse):
            for uid, stim_id, sid in model.objects.filter(
                stimulus__study_id__in=gated_study_ids,
            ).values_list('user_id', 'stimulus_id', 'stimulus__study_id'):
                stimuli = assigned.get((uid, sid))
                if stimuli is not None and stim_id in stimuli:
                    akey = (uid, sid)
                    assigned_done[akey] = assigned_done.get(akey, 0) + 1

    rows = []
    for user in users:
        cells = []
        overall_done = 0
        last_activity = None
        for study in studies:
            n, last = done.get((user.id, study.id), (0, None))
            total = totals[study.id]
            akey = (user.id, study.id)
            if akey in assigned:
                total = len(assigned[akey])
                n = assigned_done.get(akey, 0)
            overall_done += n
            if last and (last_activity is None or last > last_activity):
                last_activity = last
            cells.append({
                'study': study,
                'done': n,
                'total': total,
                'pct': round(100 * n / total) if total else 0,
                'started': n > 0,
                'completed': total > 0 and n >= total,
            })
        rows.append({
            'user': user,
            'cells': cells,
            'overall_done': overall_done,
            'last_activity': last_activity,
        })

    return render(
        request, 'iqa/annotator_progress.html', {
            'studies': studies,
            'rows': rows,
        },
    )


@staff_member_required
def export_user_responses_csv(request, user_id):
    """Download one annotator's responses across all studies as CSV."""
    user = get_object_or_404(User, id=user_id)
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = (
        'attachment; filename="'
        f'{_download_filename(user.username)}_responses.csv"'
    )
    writer = _SafeCsvWriter(response)
    writer.writerow([
        'study', 'mode', 'stimulus_order', 'timestamp',
        'choice', 'score', 'display_choice', 'was_swapped',
        'image_a', 'image_b', 'reference_a', 'reference_b',
        'shown_image_a', 'shown_image_b',
        'shown_reference_a', 'shown_reference_b',
    ])

    for r in PairResponse.objects.filter(user=user).select_related(
        'stimulus__study', 'stimulus__image_a', 'stimulus__image_b',
        'stimulus__reference_a', 'stimulus__reference_b',
    ).order_by('stimulus__study_id', 'stimulus__order'):
        st = r.stimulus
        writer.writerow([
            st.study.name, '2AFC', st.order, r.timestamp.isoformat(),
            r.choice, '', r.display_choice, r.was_swapped,
            str(st.image_a.fname), str(st.image_b.fname),
            str(st.reference_a.fname) if st.reference_a else '',
            str(st.reference_b.fname) if st.reference_b else '',
            r.shown_image_a, r.shown_image_b,
            r.shown_reference_a, r.shown_reference_b,
        ])

    for r in MOSResponse.objects.filter(user=user).select_related(
        'stimulus__study', 'stimulus__image', 'stimulus__reference',
    ).order_by('stimulus__study_id', 'stimulus__order'):
        st = r.stimulus
        writer.writerow([
            st.study.name, 'MOS', st.order, r.timestamp.isoformat(),
            '', r.score, '', '',
            str(st.image.fname), '',
            str(st.reference.fname) if st.reference else '', '',
            '', '', '', '',
        ])

    # Single-image modes reuse the "_a" slot for their one image/reference,
    # the same way MOS rows do above.
    for r in QCResponse.objects.filter(user=user).select_related(
        'stimulus__study', 'stimulus__image', 'stimulus__reference',
    ).order_by('stimulus__study_id', 'stimulus__order'):
        st = r.stimulus
        writer.writerow([
            st.study.name, 'QC', st.order, r.timestamp.isoformat(),
            r.choice, '', '', '',
            str(st.image.fname), '',
            str(st.reference.fname) if st.reference else '', '',
            r.shown_image, '', r.shown_reference, '',
        ])

    return response
