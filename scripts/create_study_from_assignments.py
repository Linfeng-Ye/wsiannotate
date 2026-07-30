"""Create a 2AFC or QC study straight from an assignments JSON, in one transaction.

The assignment file is the source of truth: the study gets exactly the union
of the stems it names -- extra stems sitting in the image bucket are ignored.
Each stem expands by mode:

  2AFC  image_a=<stem>_a.png, image_b=<stem>_b.png,
        reference_a=reference_b=<stem>_ref.png  (shared-reference layout)
  QC    image=<stem>_a.png, reference=<stem>_ref.png  (yes/no on the A image)

``import_study`` + ``import_assignments`` do the same job one round-trip per
row, which is hours over the Tokyo pooler and leaves a half-built study if it
is interrupted. This batches multi-row INSERTs inside a single atomic block
instead, so it either lands whole or not at all.

    python scripts/create_study_from_assignments.py <assignments.json> \
        [--mode 2AFC|QC] [--name NAME] [--image-dir images/Test] \
        [--assign-all-to u1,u2,...] [--activate]

Usernames are matched case-insensitively, so a JSON saying "Matsuda" binds to
the ``matsuda`` account. ``--assign-all-to`` ignores the per-rater lists and
gives every named user the full union of stems instead -- for a qualification
screen that the whole cohort takes.
"""
import argparse
import json
import os
import sys

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'iqa_site.settings')
django.setup()

from django.contrib.auth.models import User          # noqa: E402
from django.db import transaction                    # noqa: E402

from iqa.models import (                             # noqa: E402
    Image, PairStimulus, QCStimulus, Study, StudyAssignment,
)

DEFAULT_PROMPTS = {
    '2AFC': 'Which image looks closer to the reference in quality?',
    'QC': 'Is this image good enough to use for training?',
}

parser = argparse.ArgumentParser()
parser.add_argument('json_file')
parser.add_argument('--mode', choices=('2AFC', 'QC'), default='2AFC')
parser.add_argument('--name', default=None,
                    help='Override the JSON\'s "study_name".')
parser.add_argument('--image-dir', default='images/Test',
                    help='MEDIA_ROOT-relative directory holding the PNGs.')
parser.add_argument('--assign-all-to', default=None,
                    help='Comma-separated usernames; each gets the full '
                         'union of stems, ignoring the per-rater lists.')
parser.add_argument('--activate', action='store_true')
parser.add_argument('--prompt', default=None)
args = parser.parse_args()

with open(args.json_file) as fh:
    data = json.load(fh)

mode = args.mode
name = args.name or data['study_name']
image_dir = args.image_dir.rstrip('/')
prompt = args.prompt or DEFAULT_PROMPTS[mode]

entries = [
    (e['username'], e.get('pairs') or e.get('stimuli') or [])
    for e in data['assignments']
]
stems = sorted({s for _u, keys in entries for s in keys})

if args.assign_all_to:
    entries = [(u.strip(), stems) for u in args.assign_all_to.split(',')
               if u.strip()]

# --- resolve raters before writing anything -------------------------------
by_lower = {u.username.lower(): u for u in User.objects.all()}
missing = [u for u, _k in entries if u.lower() not in by_lower]
if missing:
    sys.exit(f'These usernames do not exist: {", ".join(missing)}')

if Study.objects.filter(name=name).exists():
    sys.exit(f'A study named "{name}" already exists -- refusing to '
             f'create a duplicate.')

suffixes = ('_a.png', '_b.png', '_ref.png') if mode == '2AFC' \
    else ('_a.png', '_ref.png')
paths = {f'{image_dir}/{stem}{suffix}'
         for stem in stems for suffix in suffixes}

print(f'{mode}: {len(entries)} raters, {len(stems)} unique stems')

with transaction.atomic():
    # Reuse Image rows that already exist for these paths; create the rest.
    images = {
        img.fname.name: img
        for img in Image.objects.filter(fname__in=paths)
    }
    fresh = [
        Image(fname=p, name=p.rsplit('/', 1)[-1])
        for p in sorted(paths - set(images))
    ]
    Image.objects.bulk_create(fresh, batch_size=1000)
    images.update({img.fname.name: img for img in fresh})
    print(f'images: {len(fresh)} created, '
          f'{len(paths) - len(fresh)} reused ({len(paths)} total)')

    study = Study.objects.create(
        name=name,
        mode=mode,
        prompt=prompt,
        sampler=Study.SAMPLER_RANDOM,
        image_sizing=Study.SIZING_FIT,
        zoom_enabled=True,
        zoom_factor=2.0,
        pair_shared_ref_layout=(mode == '2AFC'),
        use_local_mode=(mode == '2AFC'),   # QC always runs local-first anyway
        is_active=args.activate,
    )

    if mode == '2AFC':
        PairStimulus.objects.bulk_create([
            PairStimulus(
                study=study,
                image_a=images[f'{image_dir}/{stem}_a.png'],
                image_b=images[f'{image_dir}/{stem}_b.png'],
                reference_a=images[f'{image_dir}/{stem}_ref.png'],
                reference_b=images[f'{image_dir}/{stem}_ref.png'],
                order=i,
            )
            for i, stem in enumerate(stems)
        ], batch_size=1000)
        created = study.pair_stimuli.select_related('image_a')
        stem_of = (lambda s: s.image_a.fname.name.rsplit('/', 1)[-1][:-6])
        through = StudyAssignment.pair_stimuli.through
        link_field = 'pairstimulus_id'
    else:
        QCStimulus.objects.bulk_create([
            QCStimulus(
                study=study,
                image=images[f'{image_dir}/{stem}_a.png'],
                reference=images[f'{image_dir}/{stem}_ref.png'],
                order=i,
            )
            for i, stem in enumerate(stems)
        ], batch_size=1000)
        created = study.qc_stimuli.select_related('image')
        stem_of = (lambda s: s.image.fname.name.rsplit('/', 1)[-1][:-6])
        through = StudyAssignment.qc_stimuli.through
        link_field = 'qcstimulus_id'

    stimulus_by_stem = {stem_of(s): s for s in created}
    print(f'stimuli: {len(stimulus_by_stem)}')

    links = []
    for username, keys in entries:
        user = by_lower[username.lower()]
        assignment = StudyAssignment.objects.create(study=study, user=user)
        ids = {stimulus_by_stem[k].id for k in keys}
        links += [
            through(studyassignment_id=assignment.id, **{link_field: sid})
            for sid in sorted(ids)
        ]
        print(f'  {user.username}: {len(ids)}')
    through.objects.bulk_create(links, batch_size=2000)

print(f'created study "{study.name}" (id={study.id}), '
      f'active={study.is_active}, {len(links)} assignment links')
