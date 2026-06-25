import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('fuel', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='RouteCache',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('start_query', models.CharField(max_length=255)),
                ('destination_query', models.CharField(max_length=255)),
                ('start_lat', models.FloatField()),
                ('start_lon', models.FloatField()),
                ('dest_lat', models.FloatField()),
                ('dest_lon', models.FloatField()),
                ('distance_miles', models.FloatField()),
                ('estimated_duration', models.FloatField()),
                ('route_geometry', models.JSONField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'db_table': 'route_cache',
                'indexes': [
                    models.Index(fields=['start_query', 'destination_query'], name='idx_route_cache_queries'),
                ],
            },
        ),
    ]
