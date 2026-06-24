import os
import tempfile
import pandas as pd
import pytest
from django.core.management import call_command
from apps.fuel.models import FuelPrice

@pytest.mark.django_db
def test_import_fuel_prices_command():
    # Create temporary CSV file for testing
    csv_data = (
        "OPIS Truckstop ID,Truckstop Name,Address,City,State,Rack ID,Retail Price\n"
        "999901,TEST STATION A,123 Main St,Big Cabin,OK,307,3.109\n"
        "999901,TEST STATION A DUPE,123 Main St,Big Cabin,OK,307,2.909\n" # Duplicated ID with lower price
        "999902,TEST STATION B,456 Highway,Tomah,WI,420,3.509\n"
    )

    with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False) as f:
        f.write(csv_data)
        temp_csv_path = f.name

    try:
        # Run import command with our temporary CSV path
        call_command("import_fuel_prices", csv_path=temp_csv_path)

        # Verify database contents
        # Total unique stations should be 2 (due to deduplication)
        assert FuelPrice.objects.count() == 2

        # 999901 should have the CHEAPEST price (2.909) and name "TEST STATION A DUPE"
        station_a = FuelPrice.objects.get(opis_truckstop_id=999901)
        assert float(station_a.retail_price) == 2.909
        assert station_a.city == "Big Cabin"
        assert station_a.state == "OK"
        # Coordinates should be resolved via local database
        assert station_a.latitude is not None
        assert station_a.longitude is not None

        station_b = FuelPrice.objects.get(opis_truckstop_id=999902)
        assert float(station_b.retail_price) == 3.509
        assert station_b.city == "Tomah"
        assert station_b.state == "WI"
        assert station_b.latitude is not None
        assert station_b.longitude is not None

    finally:
        if os.path.exists(temp_csv_path):
            os.remove(temp_csv_path)
