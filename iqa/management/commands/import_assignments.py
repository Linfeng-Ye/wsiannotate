"""
Import per-rater pair assignments for a 2AFC study from a JSON file.

Once a study has any assignment, it becomes assignment-gated: each rater
sees only the pairs assigned to them (overlaps between raters are fine and
by design). A rater with no assignment sees nothing. A study with no
assignments at all behaves as before (every rater sees every pair).

JSON format:
{
    "study_id": 5,                     # or "study_name": "WSI Distortion Test (50 pairs)"
    "assignments": [
        {"username": "rater1", "pairs": ["000001_x14152_y152922_0000", ...]},
        {"username": "rater2", "pairs": ["000002_...", ...]}
    ]
}

Each entry in "pairs" identifies a PairStimulus by its *stem* -- the shared
prefix of the a/b/ref filenames, e.g. "000001_x14152_y152922_0000" for
"images/Test/000001_x14152_y152922_0000_a.png". The full image_a path
("images/Test/000001_x14152_y152922_0000_a.png") and the bare a-filename
("000001_x14152_y152922_0000_a.png") are also accepted.

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

from iqa.models import Study, PairStimulus, StudyAssignment

_A_SUFFIX = re.compile(r'_a\.[^.]+$')


def _pair_key_lookup(study: Study) -> dict:
    """Map every accepted identifier -> PairStimulus for the study's pairs."""
    lookup = {}
    pairs = study.pair_stimuli.select_related('image_a')
    for pair in pairs:
        rel = pair.image_a.fname.name  # e.g. images/Test/..._a.png
        base = rel.rsplit('/', 1)[-1]  # ..._a.png
        stem = _A_SUFFIX.sub('', base)  # ...
        for key in (rel, base, stem):
            lookup[key] = pair
    return lookup


class Command(BaseCommand):
    help = (
        'Import per-rater pair assignments for a 2AFC study from JSON.'
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
        if study.mode != Study.MODE_2AFC:
            raise CommandError(
                f'Study "{study.name}" is {study.mode}; assignments '
                f'are only supported for 2AFC studies.'
            )

        assignments = data.get('assignments', [])
        if not isinstance(assignments, list) or not assignments:
            raise CommandError('JSON has no "assignments" list.')

        lookup = _pair_key_lookup(study)

        # Resolve everything up front so a bad key aborts before any write.
        resolved = []          # list of (User, [PairStimulus, ...])
        unknown_users = []
        unknown_pairs = {}     # username -> [bad keys]
        for entry in assignments:
            username = entry.get('username')
            keys = entry.get('pairs', [])
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                unknown_users.append(username)
                continue
            pairs = []
            bad = []
            seen = set()
            for key in keys:
                pair = lookup.get(str(key))
                if pair is None:
                    bad.append(key)
                elif pair.id not in seen:
                    seen.add(pair.id)
                    pairs.append(pair)
            if bad:
                unknown_pairs[username] = bad
            resolved.append((user, pairs))

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
                'Some pair keys did not match any pair in study '
                f'"{study.name}":\n' + '\n'.join(lines)
            )

        with transaction.atomic():
            for user, pairs in resolved:
                assignment, _ = StudyAssignment.objects.get_or_create(
                    study=study, user=user,
                )
                assignment.pair_stimuli.set(pairs)

        self.stdout.write(self.style.SUCCESS(
            f'Imported assignments for study "{study.name}" '
            f'(id={study.id}):'
        ))
        for user, pairs in resolved:
            self.stdout.write(f'  {user.username}: {len(pairs)} pairs')
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
