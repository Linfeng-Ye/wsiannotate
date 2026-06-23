from typing import Optional, Union

from django.contrib.auth.models import User
from django.db.models import Count

from .models import (
    Study, MOSStimulus, PairStimulus,
    MOSResponse, PairResponse,
)

Stimulus = Union[MOSStimulus, PairStimulus]


def get_next_stimulus(
    study: Study, user: User,
) -> Optional[Stimulus]:
    if study.mode == Study.MODE_MOS:
        return _next_mos(study, user)
    return _next_pair(study, user)


def _next_mos(
    study: Study, user: User,
) -> Optional[MOSStimulus]:
    done_ids = MOSResponse.objects.filter(
        user=user, stimulus__study=study,
    ).values_list('stimulus_id', flat=True)
    remaining = study.mos_stimuli.exclude(
        id__in=done_ids,
    )
    return _pick(remaining, study.sampler, 'mosresponse')


def _next_pair(
    study: Study, user: User,
) -> Optional[PairStimulus]:
    done_ids = PairResponse.objects.filter(
        user=user, stimulus__study=study,
    ).values_list('stimulus_id', flat=True)
    remaining = study.pair_stimuli.exclude(
        id__in=done_ids,
    )
    return _pick(
        remaining, study.sampler, 'pairresponse',
    )


def _pick(queryset, sampler: str, resp_related: str):
    if not queryset.exists():
        return None
    if sampler == Study.SAMPLER_SEQUENTIAL:
        return queryset.order_by('order', 'id').first()
    if sampler == Study.SAMPLER_RANDOM:
        return queryset.order_by('?').first()
    if sampler == Study.SAMPLER_LEAST_EVAL:
        return queryset.annotate(
            n=Count(resp_related),
        ).order_by('n', 'order', 'id').first()
    return queryset.order_by('order', 'id').first()


def get_progress(
    study: Study, user: User,
) -> dict:
    if study.mode == Study.MODE_MOS:
        total = study.mos_stimuli.count()
        done = MOSResponse.objects.filter(
            user=user, stimulus__study=study,
        ).count()
    else:
        total = study.pair_stimuli.count()
        done = PairResponse.objects.filter(
            user=user, stimulus__study=study,
        ).count()
    return {'done': done, 'total': total}
