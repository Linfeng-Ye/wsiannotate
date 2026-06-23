"""
Import a study from a JSON file, or append stimuli
to an existing study.

JSON format for MOS:
{
    "name": "My MOS Study",
    "mode": "MOS",
    "prompt": "Rate the quality of the image.",
    "scale_min": 1, "scale_max": 5,
    "scale_min_label": "Bad",
    "scale_max_label": "Excellent",
    "sampler": "sequential",
    "stimuli": [
        {
            "image": "images/dist_001.png",
            "reference": "images/ref_001.png"
        },
        {
            "image": "images/dist_002.png"
        }
    ]
}

JSON format for 2AFC:
{
    "name": "My 2AFC Study",
    "mode": "2AFC",
    "prompt": "Which image has better quality?",
    "sampler": "random",
    "stimuli": [
        {
            "image_a": "images/a_001.png",
            "image_b": "images/b_001.png",
            "reference_a": "images/ref_001.png",
            "reference_b": "images/ref_001.png"
        }
    ]
}

When using --append-to, only the "stimuli" list from
the JSON is used; all other fields are ignored.

Image paths are relative to MEDIA_ROOT.
"""
import json

from django.core.management.base import (
    BaseCommand, CommandError,
)

from iqa.models import (
    Image, Study, MOSStimulus, PairStimulus,
)


def _get_or_create_image(fname: str) -> Image:
    img, _ = Image.objects.get_or_create(
        fname=fname,
        defaults={'name': fname.rsplit('/', 1)[-1]},
    )
    return img


def _append_stimuli(
    study: Study,
    stimuli: list,
    start_order: int,
) -> int:
    """Append stimuli to an existing study.

    Returns the number of stimuli created.
    """
    count = 0
    if study.mode == Study.MODE_MOS:
        for i, s in enumerate(stimuli):
            img = _get_or_create_image(s['image'])
            ref = None
            if s.get('reference'):
                ref = _get_or_create_image(
                    s['reference'],
                )
            MOSStimulus.objects.create(
                study=study, image=img,
                reference=ref,
                order=start_order + i,
            )
            count += 1
    else:
        for i, s in enumerate(stimuli):
            img_a = _get_or_create_image(
                s['image_a'],
            )
            img_b = _get_or_create_image(
                s['image_b'],
            )
            ref_a = None
            if s.get('reference_a'):
                ref_a = _get_or_create_image(
                    s['reference_a'],
                )
            ref_b = None
            if s.get('reference_b'):
                ref_b = _get_or_create_image(
                    s['reference_b'],
                )
            PairStimulus.objects.create(
                study=study,
                image_a=img_a, image_b=img_b,
                reference_a=ref_a,
                reference_b=ref_b,
                order=start_order + i,
            )
            count += 1
    return count


class Command(BaseCommand):
    help = (
        'Import an IQA study from a JSON file, '
        'or append stimuli to an existing study'
    )

    def add_arguments(self, parser):
        parser.add_argument('json_file', type=str)
        parser.add_argument(
            '--activate', action='store_true',
            help=(
                'Mark the study as active immediately '
                '(ignored when appending)'
            ),
        )
        parser.add_argument(
            '--append-to', type=int, default=None,
            metavar='STUDY_ID',
            help=(
                'Append the stimuli from the JSON to '
                'an existing study (by ID) instead of '
                'creating a new one.  Only the '
                '"stimuli" list in the JSON is used.'
            ),
        )

    def handle(self, *args, **options):
        path = options['json_file']
        try:
            with open(path) as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            raise CommandError(
                f'Cannot read {path}: {e}'
            ) from e

        stimuli = data.get('stimuli', [])
        append_id = options['append_to']

        if append_id is not None:
            return self._handle_append(
                append_id, stimuli, data,
            )

        return self._handle_create(data, options)

    def _handle_append(
        self, study_id: int, stimuli: list, data,
    ):
        try:
            study = Study.objects.get(id=study_id)
        except Study.DoesNotExist:
            raise CommandError(
                f'Study with id={study_id} '
                f'does not exist.'
            )

        mode_in_json = data.get('mode')
        if mode_in_json and mode_in_json != study.mode:
            raise CommandError(
                f'JSON mode "{mode_in_json}" does not '
                f'match study mode "{study.mode}".'
            )

        if study.mode == Study.MODE_MOS:
            max_order = (
                study.mos_stimuli
                .order_by('-order')
                .values_list('order', flat=True)
                .first()
            )
        else:
            max_order = (
                study.pair_stimuli
                .order_by('-order')
                .values_list('order', flat=True)
                .first()
            )
        start = (max_order + 1) if max_order is not None else 0

        count = _append_stimuli(study, stimuli, start)

        self.stdout.write(self.style.SUCCESS(
            f'Appended {count} stimuli to '
            f'study "{study.name}" (id={study.id}).'
        ))

    def _handle_create(self, data, options):
        mode = data.get('mode', 'MOS')
        if mode not in ('MOS', '2AFC'):
            raise CommandError(
                f'Invalid mode: {mode}'
            )

        study = Study.objects.create(
            name=data['name'],
            mode=mode,
            prompt=data.get('prompt', ''),
            scale_min=data.get('scale_min', 1),
            scale_max=data.get('scale_max', 5),
            scale_min_label=data.get(
                'scale_min_label', 'Bad',
            ),
            scale_max_label=data.get(
                'scale_max_label', 'Excellent',
            ),
            sampler=data.get(
                'sampler', 'sequential',
            ),
            image_sizing=data.get(
                'image_sizing', 'fit_screen',
            ),
            image_scale_factor=data.get(
                'image_scale_factor', 1.0,
            ),
            zoom_enabled=data.get(
                'zoom_enabled', False,
            ),
            zoom_factor=data.get(
                'zoom_factor', 2.0,
            ),
            pair_shared_ref_layout=data.get(
                'pair_shared_ref_layout', False,
            ),
            is_active=options['activate'],
        )

        stimuli = data.get('stimuli', [])
        count = _append_stimuli(study, stimuli, 0)

        self.stdout.write(self.style.SUCCESS(
            f'Created study "{study.name}" '
            f'with {count} stimuli.'
        ))
