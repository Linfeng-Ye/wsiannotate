"""
Import per-rater stimulus assignments for a 2AFC or QC study from a JSON file.

Once a study has any assignment, it becomes assignment-gated: each rater
sees only the stimuli assigned to them (overlaps between raters are fine and
by design). A rater with no assignment sees nothing. A study with no
assignments at all behaves as before (every rater sees everything).

JSON format:
{
    "study_id": 5,                     # or "study_name": "WSI Distortion Test (50 pairs)"
    "assignments": [
        {"username": "rater1", "pairs": ["000001_x14152_y152922_0000", ...]},
        {"username": "rater2", "pairs": ["000002_...", ...]}
    ]
}

Each entry in "pairs" (also accepted as "stimuli") identifies a stimulus by
its *stem* -- for 2AFC the shared prefix of the a/b/ref filenames, e.g.
"000001_x14152_y152922_0000" for
"images/Test/000001_x14152_y152922_0000_a.png"; for QC the image filename
without its extension. The full image path and the bare filename are also
accepted in both modes.

Re-importing replaces each listed rater's assignment for the study, so a
corrected JSON can be applied idempotently. Raters not present in the JSON
are left untouched. All usernames must already exist (create them first via
the bulk-create-users page); unknown users abort the import.
"""
import json
import re

from django.contrib.auth.models import User
from django.core.management.base import (
    BaseCommand, CommandError,
)
from django.db import transaction

from iqa.models import Study, StudyAssignment

_A_SUFFIX = re.compile(r'_a\.[^.]+$')
_ANY_SUFFIX = re.compile(r'\.[^.]+$')


def _stimulus_key_lookup(study: Study) -> dict:
    """Map every accepted identifier -> stimulus for the study's stimuli.

    2AFC pairs are keyed off ``image_a`` (whose ``_a`` suffix is stripped to
    give the pair stem); QC stimuli are keyed off their single image.
    """
    lookup = {}
    if study.mode == Study.MODE_QC:
        stimuli = study.qc_stimuli.select_related('image')
        image_attr, strip = 'image', _ANY_SUFFIX
    else:
        stimuli = study.pair_stimuli.select_related('image_a')
        image_attr, strip = 'image_a', _A_SUFFIX
    for stimulus in stimuli:
        rel = getattr(stimulus, image_attr).fname.name  # images/Test/....png
        base = rel.rsplit('/', 1)[-1]                   # ....png
        stem = strip.sub('', base)
        for key in (rel, base, stem):
            lookup[key] = stimulus
    return lookup


class Command(BaseCommand):
    help = (
        'Import per-rater stimulus assignments for a 2AFC or QC study '
        'from JSON.'
    )

    def add_arguments(self, parser):
        parser.add_argument('json_file', type=str)

    def handle(self, *args, **options):
        path = options['json_file']
        try:
            with open(path) as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            raise CommandError(f'Cannot read {path}: {e}') from e

        study = self._resolve_study(data)
        if study.mode not in (Study.MODE_2AFC, Study.MODE_QC):
            raise CommandError(
                f'Study "{study.name}" is {study.mode}; assignments '
                f'are only supported for 2AFC and QC studies.'
            )

        assignments = data.get('assignments', [])
        if not isinstance(assignments, list) or not assignments:
            raise CommandError('JSON has no "assignments" list.')

        lookup = _stimulus_key_lookup(study)

        # Resolve everything up front so a bad key aborts before any write.
        resolved = []          # list of (User, [stimulus, ...])
        unknown_users = []
        unknown_pairs = {}     # username -> [bad keys]
        for entry in assignments:
            username = entry.get('username')
            keys = entry.get('pairs') or entry.get('stimuli') or []
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                unknown_users.append(username)
                continue
            stimuli = []
            bad = []
            seen = set()
            for key in keys:
                stimulus = lookup.get(str(key))
                if stimulus is None:
                    bad.append(key)
                elif stimulus.id not in seen:
                    seen.add(stimulus.id)
                    stimuli.append(stimulus)
            if bad:
                unknown_pairs[username] = bad
            resolved.append((user, stimuli))

        if unknown_users:
            raise CommandError(
                'These usernames do not exist (create them first): '
                + ', '.join(str(u) for u in unknown_users)
            )
        if unknown_pairs:
            lines = [
                f'  {u}: {len(b)} unknown -> {b[:5]}'
                + ('...' if len(b) > 5 else '')
                for u, b in unknown_pairs.items()
            ]
            raise CommandError(
                'Some keys did not match any stimulus in study '
                f'"{study.name}":\n' + '\n'.join(lines)
            )

        noun = 'stimuli' if study.mode == Study.MODE_QC else 'pairs'
        with transaction.atomic():
            for user, stimuli in resolved:
                assignment, _ = StudyAssignment.objects.get_or_create(
                    study=study, user=user,
                )
                # ``stimuli()`` picks the M2M matching the study's mode.
                assignment.stimuli().set(stimuli)

        self.stdout.write(self.style.SUCCESS(
            f'Imported assignments for study "{study.name}" '
            f'(id={study.id}):'
        ))
        for user, stimuli in resolved:
            self.stdout.write(
                f'  {user.username}: {len(stimuli)} {noun}'
            )
        total_raters = StudyAssignment.objects.filter(study=study).count()
        self.stdout.write(
            f'Study now has {total_raters} rater assignment(s).'
        )

    def _resolve_study(self, data) -> Study:
        study_id = data.get('study_id')
        study_name = data.get('study_name')
        if study_id is not None:
            try:
                return Study.objects.get(id=study_id)
            except Study.DoesNotExist:
                raise CommandError(f'No study with id={study_id}.')
        if study_name:
            matches = Study.objects.filter(name=study_name)
            if not matches:
                raise CommandError(f'No study named "{study_name}".')
            if matches.count() > 1:
                raise CommandError(
                    f'Multiple studies named "{study_name}"; '
                    f'use "study_id" instead.'
                )
            return matches.first()
        raise CommandError('JSON must set "study_id" or "study_name".')
