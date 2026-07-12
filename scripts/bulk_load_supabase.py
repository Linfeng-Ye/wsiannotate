"""Fast bulk loader: deserialize the fixture and bulk_create per model.

Django's loaddata saves one object at a time (update-then-insert = two
round-trips each), which is painfully slow over a high-latency link. This
groups objects by model and issues batched multi-row INSERTs inside one
transaction instead.
"""
import os
import sys

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

import django
from django.core.management.color import no_style
from django.core.serializers import deserialize
from django.db import connection, transaction

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'iqa_site.settings')
django.setup()

fixture_path = sys.argv[1]

with open(fixture_path) as fh:
    payload = fh.read()

# Preserve order so FK targets (Image, Study) load before PairStimulus.
groups = []
index = {}
for obj in deserialize('json', payload):
    instance = obj.object
    model = type(instance)
    if model not in index:
        index[model] = len(groups)
        groups.append((model, []))
    groups[index[model]][1].append(instance)

with transaction.atomic():
    for model, instances in groups:
        model.objects.bulk_create(instances, batch_size=500)
        print(f'{model.__name__}: {len(instances)} rows')

    # Fixtures carry explicit primary keys. PostgreSQL does not advance model
    # sequences for explicit-ID inserts, so reset every imported model before
    # normal application writes resume.
    sequence_sql = connection.ops.sequence_reset_sql(
        no_style(), [model for model, _instances in groups],
    )
    with connection.cursor() as cursor:
        for statement in sequence_sql:
            cursor.execute(statement)

print('done')
