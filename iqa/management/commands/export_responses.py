"""
Export subjective experiment responses to CSV.

For MOS studies the columns are:
    study, stimulus_order, image, reference,
    user, score, timestamp

For 2AFC studies the columns are:
    study, stimulus_order, image_a, image_b,
    reference_a, reference_b, user, choice,
    display_choice, was_swapped, shown_image_a,
    shown_image_b, shown_reference_a, shown_reference_b,
    timestamp

By default, responses for every study are exported.
Use --study to restrict to a single study (by ID or
name).  Use -o / --output to write to a file instead
of stdout.
"""
import csv
import sys

from django.core.management.base import (
    BaseCommand, CommandError,
)

from iqa.models import (
    Study, MOSResponse, PairResponse,
)

MOS_HEADER = [
    'study', 'stimulus_order', 'image', 'reference',
    'user', 'score', 'timestamp',
]
PAIR_HEADER = [
    'study', 'stimulus_order',
    'image_a', 'image_b',
    'reference_a', 'reference_b',
    'user', 'choice',
    'display_choice', 'was_swapped',
    'shown_image_a', 'shown_image_b',
    'shown_reference_a', 'shown_reference_b',
    'timestamp',
]


def _image_str(image) -> str:
    if image is None:
        return ''
    return str(image.fname)


def _write_mos(writer, study: Study) -> int:
    """Write MOS responses for *study*. Return count."""
    responses = (
        MOSResponse.objects
        .filter(stimulus__study=study)
        .select_related(
            'stimulus', 'stimulus__image',
            'stimulus__reference', 'user',
        )
        .order_by('stimulus__order', 'user__username')
    )
    count = 0
    for r in responses:
        writer.writerow([
            study.name,
            r.stimulus.order,
            _image_str(r.stimulus.image),
            _image_str(r.stimulus.reference),
            r.user.username,
            r.score,
            r.timestamp.isoformat(),
        ])
        count += 1
    return count


def _write_pair(writer, study: Study) -> int:
    """Write 2AFC responses for *study*. Return count."""
    responses = (
        PairResponse.objects
        .filter(stimulus__study=study)
        .select_related(
            'stimulus',
            'stimulus__image_a',
            'stimulus__image_b',
            'stimulus__reference_a',
            'stimulus__reference_b',
            'user',
        )
        .order_by('stimulus__order', 'user__username')
    )
    count = 0
    for r in responses:
        writer.writerow([
            study.name,
            r.stimulus.order,
            _image_str(r.stimulus.image_a),
            _image_str(r.stimulus.image_b),
            _image_str(r.stimulus.reference_a),
            _image_str(r.stimulus.reference_b),
            r.user.username,
            r.choice,
            r.display_choice,
            r.was_swapped,
            r.shown_image_a,
            r.shown_image_b,
            r.shown_reference_a,
            r.shown_reference_b,
            r.timestamp.isoformat(),
        ])
        count += 1
    return count


def _resolve_study(value: str) -> Study:
    """Resolve a study by ID (if numeric) or name."""
    if value.isdigit():
        try:
            return Study.objects.get(id=int(value))
        except Study.DoesNotExist:
            pass
    try:
        return Study.objects.get(name=value)
    except Study.DoesNotExist:
        raise CommandError(
            f'No study matches "{value}". '
            f'Use the study ID or exact name.'
        )


class Command(BaseCommand):
    help = (
        'Export subjective-test responses to CSV'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '-s', '--study', type=str, default=None,
            metavar='ID_OR_NAME',
            help='Export only this study (ID or name).',
        )
        parser.add_argument(
            '-o', '--output', type=str, default=None,
            metavar='FILE',
            help='Write CSV to FILE instead of stdout.',
        )

    def handle(self, *args, **options):
        if options['study'] is not None:
            studies = [_resolve_study(options['study'])]
        else:
            studies = list(Study.objects.order_by('id'))
            if not studies:
                raise CommandError('No studies found.')

        modes = {s.mode for s in studies}
        if len(modes) > 1:
            raise CommandError(
                'Selected studies mix MOS and 2AFC '
                'modes.  Use --study to export one '
                'study at a time, or select studies '
                'of the same mode.'
            )
        mode = modes.pop()

        out_path = options['output']
        if out_path:
            dest = open(out_path, 'w', newline='')
        else:
            dest = sys.stdout

        try:
            writer = csv.writer(dest)
            if mode == Study.MODE_MOS:
                writer.writerow(MOS_HEADER)
                total = sum(
                    _write_mos(writer, s)
                    for s in studies
                )
            else:
                writer.writerow(PAIR_HEADER)
                total = sum(
                    _write_pair(writer, s)
                    for s in studies
                )
        finally:
            if out_path:
                dest.close()

        self.stderr.write(self.style.SUCCESS(
            f'Exported {total} responses '
            f'({len(studies)} '
            f'{"study" if len(studies) == 1 else "studies"}'
            f').'
        ))
