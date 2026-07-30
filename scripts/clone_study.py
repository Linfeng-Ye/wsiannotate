"""Clone a 2AFC or QC study to a fresh study id, carrying its per-rater assignments.

Why this exists: local-first mode keys its ``localStorage`` on
``iqa_local_<studyId>_<userId>`` (see ``iqa/static/iqa/js/local_eval.js``), and
``mergeServerAnswered()`` only reconciles ids the *server* mentions. So after
wiping responses server-side, an annotator who already worked still sees their
old progress and never re-uploads or forgets it. Giving the round a new study id
orphans that local state for free -- no client-side change, no asking eight
remote raters to clear site data.

The clone reuses the existing ``Image`` rows, so it is a handful of batched
INSERTs rather than a re-import from the assignment JSON.

    python scripts/clone_study.py 7 --activate --retire-source

Responses are deliberately *not* copied: the point is a clean round.
"""
import argparse
import os
import sys

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'iqa_site.settings')
django.setup()

from django.db import transaction                    # noqa: E402

from iqa.models import (                             # noqa: E402
    PairStimulus, QCStimulus, Study, StudyAssignment,
)

parser = argparse.ArgumentParser()
parser.add_argument('study_id', type=int)
parser.add_argument('--name', default=None,
                    help='Name for the clone (default: the source name).')
parser.add_argument('--activate', action='store_true',
                    help='Mark the clone active.')
parser.add_argument('--retire-source', action='store_true',
                    help='Deactivate the source study and suffix its name, '
                         'so raters see only the clone.')
parser.add_argument('--retire-suffix', default=' (retired)')
args = parser.parse_args()

BATCH = 1000


def clone_stimuli(model, src, dst, fields):
    """Copy every stimulus row, returning old->new in source order.

    Copies the raw ``*_id`` values rather than the related objects, so this
    stays one SELECT plus batched INSERTs instead of an image lookup per
    field per row over the Tokyo pooler.
    """
    old = list(model.objects.filter(study=src).order_by('order', 'id'))
    new = [
        model(
            study=dst, order=o.order,
            **{f'{f}_id': getattr(o, f'{f}_id') for f in fields},
        )
        for o in old
    ]
    model.objects.bulk_create(new, batch_size=BATCH)
    return dict(zip((o.id for o in old), (n.id for n in new)))


with transaction.atomic():
    src = Study.objects.get(id=args.study_id)
    is_qc = src.mode == Study.MODE_QC
    if src.mode == Study.MODE_MOS:
        sys.exit('MOS studies are not supported (no assignments).')

    src_name = src.name
    dst = Study.objects.get(id=args.study_id)
    dst.pk = None
    dst.id = None
    dst._state.adding = True
    dst.name = args.name or src_name
    dst.is_active = args.activate
    dst.save()

    if is_qc:
        id_map = clone_stimuli(
            QCStimulus, src, dst, ('image', 'reference'),
        )
    else:
        id_map = clone_stimuli(
            PairStimulus, src, dst,
            ('image_a', 'image_b', 'reference_a', 'reference_b'),
        )
    print(f'cloned {len(id_map)} stimuli -> study {dst.id}')

    n_links = 0
    for old_assign in StudyAssignment.objects.filter(study=src):
        new_assign = StudyAssignment.objects.create(
            study=dst, user=old_assign.user,
        )
        old_ids = old_assign.stimuli().values_list('id', flat=True)
        new_ids = [id_map[i] for i in old_ids]
        new_assign.stimuli().add(*new_ids)
        n_links += len(new_ids)
        print(f'  {old_assign.user.username}: {len(new_ids)} stimuli')
    print(f'cloned {n_links} assignment links')

    if args.retire_source:
        src.is_active = False
        if not src.name.endswith(args.retire_suffix):
            src.name = f'{src.name}{args.retire_suffix}'
        src.save(update_fields=['is_active', 'name'])
        print(f'retired source study {src.id}: {src.name!r}')

print(
    f'study {args.study_id} -> {dst.id} '
    f'({dst.mode}, {dst.name!r}, active={dst.is_active})'
)
