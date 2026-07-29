"""Create a 2AFC study straight from an assignments JSON, in one transaction.

The assignment file is the source of truth: the study gets exactly the union
of the pair stems it names -- extra stems sitting in the image bucket are
ignored. Each stem expands to ``<dir>/<stem>_a.png``, ``_b.png`` and
``_ref.png`` (the shared reference is used for both sides, which is what the
shared-reference layout requires).

``import_study`` + ``import_assignments`` do the same job one round-trip per
row, which is hours over the Tokyo pooler and leaves a half-built study if it
is interrupted. This batches multi-row INSERTs inside a single atomic block
instead, so it either lands whole or not at all.

    python scripts/create_2afc_study_from_assignments.py <assignments.json> \
        [--name NAME] [--image-dir images/Test] [--activate]

Usernames are matched case-insensitively, so a JSON saying "Matsuda" binds to
the ``matsuda`` account.
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
    Image, PairStimulus, Study, StudyAssignment,
)

parser = argparse.ArgumentParser()
parser.add_argument('json_file')
parser.add_argument('--name', default=None,
                    help='Override the JSON\'s "study_name".')
parser.add_argument('--image-dir', default='images/Test',
                    help='MEDIA_ROOT-relative directory holding the PNGs.')
parser.add_argument('--activate', action='store_true')
parser.add_argument('--prompt',
                    default='Which image looks closer to the reference '
                            'in quality?')
args = parser.parse_args()

with open(args.json_file) as fh:
    data = json.load(fh)

name = args.name or data['study_name']
entries = data['assignments']
image_dir = args.image_dir.rstrip('/')

# --- resolve raters before writing anything -------------------------------
by_lower = {u.username.lower(): u for u in User.objects.all()}
missing = [e['username'] for e in entries
           if e['username'].lower() not in by_lower]
if missing:
    sys.exit(f'These usernames do not exist: {", ".join(missing)}')

if Study.objects.filter(name=name).exists():
    sys.exit(f'A study named "{name}" already exists -- refusing to '
             f'create a duplicate.')

# --- the study's pair set is the union of every rater's list --------------
stems = sorted({s for e in entries for s in e['pairs']})
print(f'{len(entries)} raters, {len(stems)} unique pairs')

paths = set()
for stem in stems:
    for suffix in ('_a.png', '_b.png', '_ref.png'):
        paths.add(f'{image_dir}/{stem}{suffix}')

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
        mode=Study.MODE_2AFC,
        prompt=args.prompt,
        sampler=Study.SAMPLER_RANDOM,
        image_sizing=Study.SIZING_FIT,
        zoom_enabled=True,
        zoom_factor=2.0,
        pair_shared_ref_layout=True,
        use_local_mode=True,
        is_active=args.activate,
    )

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

    stimulus_by_stem = {
        p.image_a.fname.name.rsplit('/', 1)[-1][:-6]: p
        for p in study.pair_stimuli.select_related('image_a')
    }
    print(f'pair stimuli: {len(stimulus_by_stem)}')

    through = StudyAssignment.pair_stimuli.through
    links = []
    for entry in entries:
        user = by_lower[entry['username'].lower()]
        assignment = StudyAssignment.objects.create(study=study, user=user)
        ids = {stimulus_by_stem[s].id for s in entry['pairs']}
        links += [
            through(studyassignment_id=assignment.id, pairstimulus_id=sid)
            for sid in sorted(ids)
        ]
        print(f'  {user.username}: {len(ids)} pairs')
    through.objects.bulk_create(links, batch_size=2000)

print(f'created study "{study.name}" (id={study.id}), '
      f'active={study.is_active}, {len(links)} assignment links')
