import hashlib
import random
from typing import List, Optional, Union

from django.contrib.auth.models import User
from django.db.models import Count, Q

from .models import (
    Study, MOSStimulus, PairStimulus,
    MOSResponse, PairResponse, StudyAssignment,
)

Stimulus = Union[MOSStimulus, PairStimulus]


def _seed(study: Study, user: User) -> int:
    raw = f'{study.id}:{user.id}:{user.username}'
    digest = hashlib.sha256(raw.encode('utf-8')).hexdigest()
    return int(digest[:16], 16)


def assigned_pair_ids(study: Study, user: User) -> Optional[set]:
    """The PairStimulus ids this rater may see, or ``None`` for "everything".

    - ``None``  → the study is not assignment-gated; the rater sees every
      pair (backward-compatible; also the case for MOS studies).
    - ``set``   → the study has assignments, so the rater is restricted to
      exactly this set (possibly empty, meaning "assigned nothing").
    """
    if study.mode != Study.MODE_2AFC:
        return None
    assignment = StudyAssignment.objects.filter(
        study=study, user=user,
    ).first()
    if assignment is not None:
        return set(
            assignment.pair_stimuli.values_list('id', flat=True)
        )
    if StudyAssignment.objects.filter(study=study).exists():
        return set()
    return None


def _base_queryset(study: Study):
    if study.mode == Study.MODE_MOS:
        return study.mos_stimuli.select_related('image', 'reference')
    return study.pair_stimuli.select_related(
        'image_a', 'image_b', 'reference_a', 'reference_b',
    )


def _response_relation(study: Study) -> str:
    return (
        'mosresponse'
        if study.mode == Study.MODE_MOS else 'pairresponse'
    )


def _answered_ids(study: Study, user: User) -> set:
    if study.mode == Study.MODE_MOS:
        model = MOSResponse
    else:
        model = PairResponse
    return set(
        model.objects.filter(
            user=user, stimulus__study=study,
        ).values_list('stimulus_id', flat=True)
    )


def ordered_stimulus_ids(study: Study, user: User) -> List[int]:
    """Return the deterministic stimulus order without loading image rows.

    The order is stable across requests for a given (study, user) so the
    next stimulus can be predicted for background prefetch:

    - ``sequential``: by (order, id).
    - ``random``: a per-user seeded shuffle (stable, unlike ``order_by('?')``).
    - ``least_evaluated``: by ascending global response count; best-effort,
      since counts change as other users respond.
    """
    queryset = _base_queryset(study).select_related(None)
    assigned = assigned_pair_ids(study, user)
    if assigned is not None:
        queryset = queryset.filter(id__in=assigned)
    if study.sampler == Study.SAMPLER_RANDOM:
        ids = list(queryset.values_list('id', flat=True))
        random.Random(_seed(study, user)).shuffle(ids)
        return ids
    if study.sampler == Study.SAMPLER_LEAST_EVAL:
        return list(
            queryset.annotate(
                n=Count(_response_relation(study)),
            ).order_by('n', 'order', 'id').values_list('id', flat=True)
        )
    return list(
        queryset.order_by('order', 'id').values_list('id', flat=True)
    )


def _fetch_by_ids(study: Study, stimulus_ids: List[int]) -> List[Stimulus]:
    if not stimulus_ids:
        return []
    by_id = {
        stimulus.id: stimulus
        for stimulus in _base_queryset(study).filter(id__in=stimulus_ids)
    }
    return [by_id[stimulus_id] for stimulus_id in stimulus_ids]


def ordered_stimuli(study: Study, user: User) -> List[Stimulus]:
    """Return the deterministic full order, primarily for admin/test use."""
    return _fetch_by_ids(study, ordered_stimulus_ids(study, user))


def get_next_stimulus(
    study: Study, user: User,
) -> Optional[Stimulus]:
    answered = _answered_ids(study, user)
    remaining = _base_queryset(study).exclude(id__in=answered)
    assigned = assigned_pair_ids(study, user)
    if assigned is not None:
        remaining = remaining.filter(id__in=assigned)
    if study.sampler == Study.SAMPLER_SEQUENTIAL:
        return remaining.order_by('order', 'id').first()
    if study.sampler == Study.SAMPLER_LEAST_EVAL:
        return remaining.annotate(
            n=Count(_response_relation(study)),
        ).order_by('n', 'order', 'id').first()
    for stimulus_id in ordered_stimulus_ids(study, user):
        if stimulus_id not in answered:
            return _fetch_by_ids(study, [stimulus_id])[0]
    return None


def get_upcoming_stimuli(
    study: Study, user: User,
    current_stimulus_id: Optional[int], count: int,
) -> List[Stimulus]:
    """The next ``count`` unanswered stimuli the user will see, in order.

    Used to warm the browser image cache a few trials ahead. If
    ``current_stimulus_id`` is in the order, prediction starts after it;
    otherwise it starts from the first unanswered stimulus.
    """
    answered = _answered_ids(study, user)
    assigned = assigned_pair_ids(study, user)

    if study.sampler == Study.SAMPLER_SEQUENTIAL:
        remaining = _base_queryset(study).exclude(id__in=answered)
        if assigned is not None:
            remaining = remaining.filter(id__in=assigned)
        current = _base_queryset(study).select_related(None).filter(
            id=current_stimulus_id,
        ).only('id', 'order').first()
        if current is not None:
            remaining = remaining.filter(
                Q(order__gt=current.order)
                | Q(order=current.order, id__gt=current.id)
            )
        return list(remaining.order_by('order', 'id')[:count])

    order = ordered_stimulus_ids(study, user)

    start = 0
    if current_stimulus_id is not None:
        for index, stimulus_id in enumerate(order):
            if stimulus_id == current_stimulus_id:
                start = index + 1
                break

    upcoming_ids = []
    for stimulus_id in order[start:]:
        if stimulus_id not in answered:
            upcoming_ids.append(stimulus_id)
            if len(upcoming_ids) >= count:
                break
    return _fetch_by_ids(study, upcoming_ids)


def get_progress(
    study: Study, user: User,
) -> dict:
    if study.mode == Study.MODE_MOS:
        total = study.mos_stimuli.count()
        done = MOSResponse.objects.filter(
            user=user, stimulus__study=study,
        ).count()
    else:
        assigned = assigned_pair_ids(study, user)
        done_qs = PairResponse.objects.filter(
            user=user, stimulus__study=study,
        )
        if assigned is not None:
            total = len(assigned)
            done = done_qs.filter(stimulus_id__in=assigned).count()
        else:
            total = study.pair_stimuli.count()
            done = done_qs.count()
    return {'done': done, 'total': total}
