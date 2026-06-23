#!/usr/bin/env python3
"""Generate a dev test image set from the LIVE IQA dataset.

Randomly selects distorted images, center-crops each (and its
reference) to 512x512, saves them as PNG, and produces a JSON
file ready for ``import_study``.

Supports two modes:
- **MOS**: samples individual distorted images.
- **2AFC**: pairs distorted images that share the same
  reference scene by default.  Use ``--cross-ref FRAC``
  to control the fraction of cross-scene pairs (where
  each side has its own reference).

Usage::

    python scripts/generate_dev_test.py /path/to/LIVE
    python scripts/generate_dev_test.py /path/to/LIVE --mode 2AFC
    python scripts/generate_dev_test.py /path/to/LIVE --mode 2AFC --cross-ref 0.3

The LIVE directory should contain::

    /path/to/LIVE/
    ├── refimgs/          (reference BMPs)
    ├── jp2k/             (JPEG 2000 distortions)
    ├── jpeg/
    ├── wn/               (white noise)
    ├── gblur/            (Gaussian blur)
    └── fastfading/
"""
import argparse
import csv
import json
import random
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

from PIL import Image

N_SAMPLES = 50
SEED = 42
CROP_SIZE = 512

BASE = Path(__file__).resolve().parent.parent
CSV_PATH = BASE / 'tmp' / 'filelist.csv'
IMG_DIR = BASE / 'images' / 'live_dev'


def center_crop_and_save(
    src: Path, dst: Path,
) -> None:
    """Open *src*, center-crop to 512x512, save as PNG."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as img:
        w, h = img.size
        left = (w - CROP_SIZE) // 2
        top = (h - CROP_SIZE) // 2
        cropped = img.crop((
            left, top,
            left + CROP_SIZE, top + CROP_SIZE,
        ))
        cropped.save(dst, 'PNG')


def crop_one(
    row: dict,
    live_dir: Path,
    img_dir: Path,
    refs_done: set[str],
) -> dict | None:
    """Crop a distorted image and its reference.

    Returns a dict with ``dist`` and ``ref`` relative paths,
    or *None* if a source file is missing.
    """
    dist_bmp = row['filenames'].strip()
    ref_bmp = row['ref_names'].strip()

    src_dist = live_dir / dist_bmp
    src_ref = live_dir / 'refimgs' / ref_bmp
    if not src_dist.is_file():
        print(f'  skip (not found): {src_dist}')
        return None
    if not src_ref.is_file():
        print(f'  skip (ref not found): {src_ref}')
        return None

    dist_png = dist_bmp.rsplit('.', 1)[0] + '.png'
    ref_png = ref_bmp.rsplit('.', 1)[0] + '.png'

    center_crop_and_save(src_dist, img_dir / dist_png)
    if ref_bmp not in refs_done:
        center_crop_and_save(
            src_ref, img_dir / 'refimgs' / ref_png,
        )
        refs_done.add(ref_bmp)

    rel = img_dir.relative_to(BASE)
    return {
        'dist': f'{rel}/{dist_png}',
        'ref': f'{rel}/refimgs/{ref_png}',
    }


def generate_mos(
    distorted: list[dict],
    n: int,
    live_dir: Path,
    img_dir: Path,
) -> tuple[list[dict], int, int]:
    """Return (stimuli, n_refs, n_skipped) for MOS."""
    selected = random.sample(
        distorted, min(n, len(distorted)),
    )
    selected.sort(key=lambda r: r['filenames'])

    refs_done: set[str] = set()
    stimuli: list[dict] = []
    skipped = 0

    for row in selected:
        info = crop_one(row, live_dir, img_dir, refs_done)
        if info is None:
            skipped += 1
            continue
        stimuli.append({
            'image': info['dist'],
            'reference': info['ref'],
        })

    return stimuli, len(refs_done), skipped


def _build_pair_pools(
    distorted: list[dict],
) -> tuple[list[tuple[dict, dict]],
           list[tuple[dict, dict]]]:
    """Build same-ref and cross-ref pair pools."""
    by_ref: dict[str, list[dict]] = defaultdict(list)
    for row in distorted:
        by_ref[row['ref_names'].strip()].append(row)

    same: list[tuple[dict, dict]] = []
    for rows in by_ref.values():
        if len(rows) >= 2:
            same.extend(combinations(rows, 2))

    groups = list(by_ref.values())
    cross: list[tuple[dict, dict]] = []
    if len(groups) >= 2:
        for gi, gj in combinations(range(len(groups)), 2):
            for a in groups[gi]:
                for b in groups[gj]:
                    cross.append((a, b))

    return same, cross


def _crop_pairs(
    selected: list[tuple[dict, dict]],
    live_dir: Path,
    img_dir: Path,
) -> tuple[list[dict], int, int]:
    """Crop selected pairs. Returns (stimuli, n_refs, skipped)."""
    refs_done: set[str] = set()
    stimuli: list[dict] = []
    skipped = 0

    for row_a, row_b in selected:
        info_a = crop_one(
            row_a, live_dir, img_dir, refs_done,
        )
        info_b = crop_one(
            row_b, live_dir, img_dir, refs_done,
        )
        if info_a is None or info_b is None:
            skipped += 1
            continue
        stimuli.append({
            'image_a': info_a['dist'],
            'image_b': info_b['dist'],
            'reference_a': info_a['ref'],
            'reference_b': info_b['ref'],
        })

    return stimuli, len(refs_done), skipped


def generate_2afc(
    distorted: list[dict],
    n: int,
    cross_ref_ratio: float,
    live_dir: Path,
    img_dir: Path,
) -> tuple[list[dict], int, int]:
    """Return (stimuli, n_refs, n_skipped) for 2AFC.

    *cross_ref_ratio* (0.0--1.0) controls the fraction of
    pairs drawn from different reference scenes.
    """
    same_pool, cross_pool = _build_pair_pools(distorted)

    n_cross = round(n * cross_ref_ratio)
    n_same = n - n_cross

    if n_same > 0 and not same_pool:
        sys.exit(
            'Error: no same-scene pairs available '
            '(need >= 2 distortions per reference).'
        )
    if n_cross > 0 and not cross_pool:
        sys.exit(
            'Error: no cross-scene pairs available '
            '(need images from >= 2 reference scenes).'
        )

    selected_same = random.sample(
        same_pool, min(n_same, len(same_pool)),
    ) if n_same > 0 else []
    selected_cross = random.sample(
        cross_pool, min(n_cross, len(cross_pool)),
    ) if n_cross > 0 else []

    selected = selected_same + selected_cross
    selected.sort(
        key=lambda p: (
            p[0]['filenames'], p[1]['filenames'],
        ),
    )

    stimuli, n_refs, skipped = _crop_pairs(
        selected, live_dir, img_dir,
    )

    actual_same = len(selected_same)
    actual_cross = len(selected_cross)
    total = actual_same + actual_cross
    print(
        f'Pair mix:   {actual_same} same-scene '
        f'+ {actual_cross} cross-scene'
        + (f' ({actual_cross/total:.0%} cross)'
           if total else ''),
    )

    return stimuli, n_refs, skipped


def build_study(
    mode: str, stimuli: list[dict],
) -> dict:
    """Build the study JSON dict."""
    if mode == 'MOS':
        return {
            'name': 'LIVE Dev Test (MOS)',
            'mode': 'MOS',
            'prompt': (
                'Rate the quality of the test image '
                'compared to the reference.'
            ),
            'scale_min': 1,
            'scale_max': 5,
            'scale_min_label': 'Bad',
            'scale_max_label': 'Excellent',
            'sampler': 'random',
            'stimuli': stimuli,
        }
    return {
        'name': 'LIVE Dev Test (2AFC)',
        'mode': '2AFC',
        'prompt': 'Which image has better quality?',
        'sampler': 'random',
        'stimuli': stimuli,
    }


def main():
    parser = argparse.ArgumentParser(
        description='Generate a dev test set from LIVE.',
    )
    parser.add_argument(
        'live_dir', type=Path,
        help=(
            'Root of the LIVE dataset '
            '(contains refimgs/, jp2k/, ...)'
        ),
    )
    parser.add_argument(
        '--mode', choices=['MOS', '2AFC'], default='MOS',
        help='Study mode (default MOS)',
    )
    parser.add_argument(
        '--cross-ref', type=float, default=0.0,
        metavar='FRAC',
        help='2AFC only: fraction (0.0-1.0) of pairs '
             'drawn from different reference scenes '
             '(default 0.0 = all same-scene)',
    )
    parser.add_argument(
        '--csv', type=Path, default=CSV_PATH,
        help=f'Path to filelist CSV '
             f'(default {CSV_PATH})',
    )
    parser.add_argument(
        '--outdir', type=Path, default=IMG_DIR,
        help=f'Output directory for cropped images '
             f'(default {IMG_DIR})',
    )
    parser.add_argument(
        '--json', type=Path, default=None,
        help='Output JSON path (default: '
             'scripts/live_dev_{mode}.json)',
    )
    parser.add_argument(
        '-n', type=int, default=N_SAMPLES,
        help=f'Number of stimuli to sample '
             f'(default {N_SAMPLES})',
    )
    parser.add_argument(
        '--seed', type=int, default=SEED,
        help=f'Random seed (default {SEED})',
    )
    args = parser.parse_args()

    live_dir: Path = args.live_dir.resolve()
    csv_path: Path = args.csv.resolve()
    img_dir: Path = args.outdir.resolve()
    mode: str = args.mode

    if args.json is not None:
        json_out = args.json.resolve()
    else:
        suffix = 'mos' if mode == 'MOS' else '2afc'
        json_out = BASE / 'scripts' / (
            f'live_dev_{suffix}.json'
        )

    if not (live_dir / 'refimgs').is_dir():
        sys.exit(
            f'Error: {live_dir}/refimgs/ not found. '
            f'Is this the LIVE dataset root?'
        )

    random.seed(args.seed)

    with open(csv_path, newline='') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    distorted = [
        r for r in rows if r['is_orgs'].strip() == '0'
    ]

    cross_ref = args.cross_ref
    if cross_ref and mode != '2AFC':
        sys.exit('Error: --cross-ref requires --mode 2AFC')
    if not (0.0 <= cross_ref <= 1.0):
        sys.exit('Error: --cross-ref must be 0.0-1.0')

    if mode == 'MOS':
        stimuli, n_refs, skipped = generate_mos(
            distorted, args.n, live_dir, img_dir,
        )
    else:
        stimuli, n_refs, skipped = generate_2afc(
            distorted, args.n, cross_ref,
            live_dir, img_dir,
        )

    study = build_study(mode, stimuli)

    json_out.parent.mkdir(parents=True, exist_ok=True)
    with open(json_out, 'w') as f:
        json.dump(study, f, indent=2)

    print(f'Mode:       {mode}')
    print(f'Processed {len(stimuli)} stimuli '
          f'({n_refs} references).')
    if skipped:
        print(f'Skipped {skipped} (source not found).')
    print(f'Images:     {img_dir}/')
    print(f'Study JSON: {json_out}')
    print()
    print('To import:')
    print(f'  python manage.py import_study '
          f'{json_out.relative_to(BASE)} --activate')


if __name__ == '__main__':
    main()
