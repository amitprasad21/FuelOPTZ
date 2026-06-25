import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='FuelPrice',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('opis_truckstop_id', models.IntegerField(unique=True)),
                ('truckstop_name', models.CharField(max_length=255)),
                ('address', models.CharField(max_length=255)),
                ('city', models.CharField(max_length=255)),
                ('state', models.CharField(max_length=50)),
                ('rack_id', models.IntegerField(blank=True, null=True)),
                ('retail_price', models.DecimalField(decimal_places=4, max_digits=10)),
                ('latitude', models.FloatField(blank=True, null=True)),
                ('longitude', models.FloatField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'fuel_prices',
                'indexes': [
                    models.Index(fields=['latitude', 'longitude'], name='idx_fuel_prices_lat_lon'),
                    models.Index(fields=['state', 'city'], name='idx_fuel_prices_state_city'),
                    models.Index(fields=['retail_price'], name='idx_fuel_prices_price'),
                ],
            },
        ),
    ]
