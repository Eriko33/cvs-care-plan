from django.db import migrations

import pgvector.django


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        pgvector.django.VectorExtension(),
    ]
