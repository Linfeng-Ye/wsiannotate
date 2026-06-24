import csv
import random
import string

from django.contrib import messages
from django.contrib.admin.views.decorators import (
    staff_member_required,
)
from django.contrib.auth.decorators import (
    login_required, user_passes_test,
)
from django.contrib.auth.models import User
from django.db.models import Count
from django.http import HttpResponse, JsonResponse
from django.urls import reverse
from django.shortcuts import (
    get_object_or_404, redirect, render,
)
from django.views.decorators.http import require_POST

from .forms import BulkUserCreationForm
from .models import (
    Study, MOSStimulus, PairStimulus,
    MOSResponse, PairResponse,
)
from .samplers import get_next_stimulus, get_progress


PRELOAD_SW_JS = """
const IQA_CACHE_PREFIX = 'iqa-study-images-';

self.addEventListener('install', function(event) {
    event.waitUntil(self.skipWaiting());
});

self.addEventListener('activate', function(event) {
    event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', function(event) {
    var url = new URL(event.request.url);
    var isMedia = url.pathname.indexOf('/media/') === 0;
    var isImage = event.request.destination === 'image';
    if (!isMedia && !isImage) return;

    event.respondWith(
        caches.match(event.request).then(function(cached) {
            if (cached) return cached;
            return fetch(event.request);
        })
    );
});
""".strip()


def _image_url(request, image):
    if image is None:
        return None
    return request.build_absolute_uri(image.fname.url)


def _add_image_url(request, urls, seen, image):
    url = _image_url(request, image)
    if url and url not in seen:
        urls.append(url)
        seen.add(url)


def _ordered_stimuli_for_preload(study, user):
    if study.mode == Study.MODE_MOS:
        done_ids = MOSResponse.objects.filter(
            user=user, stimulus__study=study,
        ).values_list('stimulus_id', flat=True)
        remaining = study.mos_stimuli.exclude(
            id__in=done_ids,
        ).select_related(
            'image', 'reference',
        )
    else:
        done_ids = PairResponse.objects.filter(
            user=user, stimulus__study=study,
        ).values_list('stimulus_id', flat=True)
        remaining = study.pair_stimuli.exclude(
            id__in=done_ids,
        ).select_related(
            'image_a', 'image_b',
            'reference_a', 'reference_b',
        )

    if study.sampler == Study.SAMPLER_LEAST_EVAL:
        resp_related = (
            'mosresponse'
            if study.mode == Study.MODE_MOS else 'pairresponse'
        )
        return remaining.annotate(
            n=Count(resp_related),
        ).order_by('n', 'order', 'id')
    return remaining.order_by('order', 'id')


def _rotate_from_current(stimuli, current_stimulus_id):
    if not current_stimulus_id:
        return stimuli
    stimulus_ids = [stimulus.id for stimulus in stimuli]
    try:
        start = stimulus_ids.index(int(current_stimulus_id))
    except (ValueError, TypeError):
        return stimuli
    return stimuli[start:] + stimuli[:start]


def _study_image_urls(request, study, current_stimulus_id=None):
    urls = []
    seen = set()
    stimuli = list(
        _ordered_stimuli_for_preload(study, request.user)
    )
    stimuli = _rotate_from_current(stimuli, current_stimulus_id)

    if study.mode == Study.MODE_MOS:
        for stimulus in stimuli:
            _add_image_url(request, urls, seen, stimulus.image)
            _add_image_url(request, urls, seen, stimulus.reference)
    else:
        for stimulus in stimuli:
            _add_image_url(request, urls, seen, stimulus.reference_a)
            _add_image_url(request, urls, seen, stimulus.reference_b)
            _add_image_url(request, urls, seen, stimulus.image_a)
            _add_image_url(request, urls, seen, stimulus.image_b)
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
    if study.mode == Study.MODE_MOS:
        return set(
            MOSResponse.objects.filter(
                user=user, stimulus__study=study,
            ).values_list('stimulus_id', flat=True)
        )
    return set(
        PairResponse.objects.filter(
            user=user, stimulus__study=study,
        ).values_list('stimulus_id', flat=True)
    )


def _ordered_stimuli_for_previous(study):
    if study.mode == Study.MODE_MOS:
        return study.mos_stimuli.order_by('order', 'id')
    return study.pair_stimuli.order_by('order', 'id')


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

    ordered_ids = list(
        _ordered_stimuli_for_previous(study)
        .values_list('id', flat=True)
    )
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
def preload_manifest(request, study_id):
    study = get_object_or_404(Study, id=study_id, is_active=True)
    current_stimulus_id = request.GET.get('current')
    urls = _study_image_urls(request, study, current_stimulus_id)
    return JsonResponse({
        'study_id': study.id,
        'study_name': study.name,
        'cache_name': f'iqa-study-images-{study.id}-v1',
        'image_count': len(urls),
        'urls': urls,
    })


@login_required
def preload_service_worker(request):
    response = HttpResponse(
        PRELOAD_SW_JS,
        content_type='application/javascript',
    )
    response['Service-Worker-Allowed'] = '/'
    response['Cache-Control'] = 'no-cache'
    return response


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


@login_required
def pair_evaluation(request, study_id, stimulus_id):
    study = get_object_or_404(
        Study, id=study_id, mode=Study.MODE_2AFC,
    )
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
        choice = display_choice
        if swap:
            choice = 'B' if display_choice == 'A' else 'A'

        if swap:
            shown_image_a = stimulus.image_b
            shown_image_b = stimulus.image_a
            shown_reference_a = stimulus.reference_b
            shown_reference_b = stimulus.reference_a
        else:
            shown_image_a = stimulus.image_a
            shown_image_b = stimulus.image_b
            shown_reference_a = stimulus.reference_a
            shown_reference_b = stimulus.reference_b

        PairResponse.objects.update_or_create(
            stimulus=stimulus, user=request.user,
            defaults={
                'choice': choice,
                'display_choice': display_choice,
                'was_swapped': swap,
                'shown_image_a': str(shown_image_a.fname),
                'shown_image_b': str(shown_image_b.fname),
                'shown_reference_a': (
                    str(shown_reference_a.fname)
                    if shown_reference_a else ''
                ),
                'shown_reference_b': (
                    str(shown_reference_b.fname)
                    if shown_reference_b else ''
                ),
            },
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
    studies = Study.objects.all()
    mos_data = []
    pair_data = []
    study = None

    if study_id:
        study = get_object_or_404(Study, id=study_id)
        if study.mode == Study.MODE_MOS:
            mos_data = MOSResponse.objects.filter(
                stimulus__study=study,
            ).select_related(
                'stimulus__image', 'stimulus__reference',
                'user',
            ).order_by('stimulus__order', 'user__username')
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

    return render(
        request, 'iqa/view_responses.html', {
            'studies': studies,
            'study': study,
            'mos_data': mos_data,
            'pair_data': pair_data,
        },
    )


@login_required
def export_own_responses_csv(request, study_id: int):
    study = get_object_or_404(
        Study, id=study_id, allow_self_export=True,
    )
    response = HttpResponse(content_type='text/csv')
    fname = study.name.replace(' ', '_')
    response['Content-Disposition'] = (
        f'attachment; filename="{fname}_my_responses.csv"'
    )
    writer = csv.writer(response)

    if study.mode == Study.MODE_MOS:
        writer.writerow([
            'user', 'stimulus_order',
            'image', 'reference', 'score',
        ])
        for r in MOSResponse.objects.filter(
            stimulus__study=study, user=request.user,
        ).select_related(
            'stimulus__image', 'stimulus__reference',
            'user',
        ).order_by('stimulus__order'):
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
        for r in PairResponse.objects.filter(
            stimulus__study=study, user=request.user,
        ).select_related(
            'stimulus__image_a', 'stimulus__image_b',
            'stimulus__reference_a',
            'stimulus__reference_b',
            'user',
        ).order_by('stimulus__order'):
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

    return response


@staff_member_required
def export_responses_csv(request, study_id):
    study = get_object_or_404(Study, id=study_id)
    response = HttpResponse(content_type='text/csv')
    fname = study.name.replace(' ', '_')
    response['Content-Disposition'] = (
        f'attachment; filename="{fname}_responses.csv"'
    )
    writer = csv.writer(response)

    if study.mode == Study.MODE_MOS:
        writer.writerow([
            'user', 'stimulus_order',
            'image', 'reference', 'score',
        ])
        for r in MOSResponse.objects.filter(
            stimulus__study=study,
        ).select_related(
            'stimulus__image', 'stimulus__reference',
            'user',
        ).order_by('stimulus__order', 'user__username'):
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
        for r in PairResponse.objects.filter(
            stimulus__study=study,
        ).select_related(
            'stimulus__image_a', 'stimulus__image_b',
            'stimulus__reference_a',
            'stimulus__reference_b',
            'user',
        ).order_by('stimulus__order', 'user__username'):
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

    return response
