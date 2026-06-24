import os
import json
import time
import logging
import requests
import pandas as pd
from django.core.management.base import BaseCommand
from django.db import transaction
from django.conf import settings
from apps.fuel.models import FuelPrice

logger = logging.getLogger(__name__)

# URL of a comprehensive US Cities Database
CITIES_DB_URL = "https://raw.githubusercontent.com/kelvins/US-Cities-Database/main/csv/us_cities.csv"

class Command(BaseCommand):
    help = "Imports fuel prices from a CSV file, geocodes locations, and performs deduplication and bulk inserts."

    def add_arguments(self, parser):
        parser.add_argument(
            "--csv-path",
            type=str,
            default=os.path.join(settings.BASE_DIR.parent, "fuel-prices-for-be-assessment.csv"),
            help="Path to the fuel prices CSV file.",
        )
        parser.add_argument(
            "--force-download-cities",
            action="store_true",
            help="Forces re-downloading the cities database from GitHub.",
        )

    def handle(self, *args, **options):
        csv_path = options["csv_path"]
        force_download = options["force_download_cities"]
        
        t_start = time.time()
        self.stdout.write(self.style.NOTICE(f"Starting fuel price import from {csv_path}..."))

        if not os.path.exists(csv_path):
            self.stdout.write(self.style.ERROR(f"CSV file not found at: {csv_path}"))
            return

        # 1. Download/Load US Cities Coordinates DB
        cities_csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "us_cities.csv")
        if not os.path.exists(cities_csv_path) or force_download:
            self.stdout.write(self.style.NOTICE(f"Downloading US Cities Database from GitHub..."))
            try:
                r = requests.get(CITIES_DB_URL, timeout=30)
                r.raise_for_status()
                with open(cities_csv_path, "wb") as f:
                    f.write(r.content)
                self.stdout.write(self.style.SUCCESS("Downloaded US Cities Database successfully."))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Failed to download cities database: {e}"))
                # Fallback if download fails and file doesn't exist
                if not os.path.exists(cities_csv_path):
                    self.stdout.write(self.style.ERROR("No local cities database available. Exiting."))
                    return

        df_cities = pd.read_csv(cities_csv_path)
        # Standardize cities data
        df_cities["city_clean"] = df_cities["CITY"].astype(str).str.strip().str.upper()
        df_cities["state_clean"] = df_cities["STATE_CODE"].astype(str).str.strip().str.upper()
        
        # Build local dictionary for fast O(1) coordinate lookups
        cities_coords = {}
        for _, row in df_cities.iterrows():
            key = (row["city_clean"], row["state_clean"])
            if key not in cities_coords:
                cities_coords[key] = (float(row["LATITUDE"]), float(row["LONGITUDE"]))

        # 2. Read and Clean Fuel Price CSV
        df_fuel = pd.read_csv(csv_path)
        # Strip whitespace from headers
        df_fuel.columns = [col.strip() for col in df_fuel.columns]
        
        # 3. Load Geocoding Cache to avoid repeat API hits
        cache_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "geocoding_cache.json")
        geo_cache = {}
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    geo_cache = json.load(f)
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"Could not load geocoding cache: {e}"))

        # Geocoding helper function (Nominatim / ORS)
        ors_key = os.environ.get("ORS_API_KEY")
        
        def geocode_city_state(city, state):
            city_clean = city.strip()
            state_clean = state.strip()
            cache_key = f"{city_clean}, {state_clean}".upper()
            
            if cache_key in geo_cache:
                return geo_cache[cache_key]

            # Try OpenRouteService Geocoding if key is available
            if ors_key:
                try:
                    url = "https://api.openrouteservice.org/v1/geocode/search"
                    params = {
                        "text": f"{city_clean}, {state_clean}, USA",
                        "api_key": ors_key,
                        "size": 1
                    }
                    r = requests.get(url, params=params, timeout=10)
                    if r.status_code == 200:
                        data = r.json()
                        features = data.get("features", [])
                        if features:
                            coords = features[0]["geometry"]["coordinates"]
                            # ORS returns [lon, lat]
                            lon, lat = float(coords[0]), float(coords[1])
                            geo_cache[cache_key] = (lat, lon)
                            self.stdout.write(self.style.SUCCESS(f"Geocoded via ORS: {cache_key} -> {lat}, {lon}"))
                            return lat, lon
                except Exception as ex:
                    self.stdout.write(self.style.WARNING(f"ORS geocoding failed for {cache_key}: {ex}"))

            # Fallback to Nominatim OpenStreetMap
            try:
                headers = {"User-Agent": "FuelOPTZ-Importer/1.0 (antigravity@gemini)"}
                url = "https://nominatim.openstreetmap.org/search"
                params = {
                    "city": city_clean,
                    "state": state_clean,
                    "country": "United States",
                    "format": "json",
                    "limit": 1
                }
                # Also try without country if Canadian province (e.g. AB, ON)
                if state_clean in ["AB", "ON", "BC", "MB", "SK", "QC", "NB", "NS", "NL", "PE", "YT", "NT", "NU"]:
                    params["country"] = "Canada"

                time.sleep(1.0) # Nominatim policy requires max 1 req/sec
                r = requests.get(url, params=params, headers=headers, timeout=10)
                if r.status_code == 200:
                    data = r.json()
                    if data:
                        lat, lon = float(data[0]["lat"]), float(data[0]["lon"])
                        geo_cache[cache_key] = (lat, lon)
                        self.stdout.write(self.style.SUCCESS(f"Geocoded via Nominatim: {cache_key} -> {lat}, {lon}"))
                        return lat, lon
            except Exception as ex:
                self.stdout.write(self.style.WARNING(f"Nominatim geocoding failed for {cache_key}: {ex}"))

            # Return None if both failed
            return None

        # 4. Resolve Coordinates
        self.stdout.write(self.style.NOTICE("Resolving fuel station coordinates..."))
        resolved_count = 0
        cache_hit_count = 0
        api_hit_count = 0
        unresolved_count = 0

        station_records = []
        
        # We process unique city-state combinations to minimize lookups
        unique_locations = df_fuel[["City", "State"]].drop_duplicates()
        location_coords = {}

        for _, loc in unique_locations.iterrows():
            city = str(loc["City"]).strip()
            state = str(loc["State"]).strip()
            key_clean = (city.upper(), state.upper())
            
            # Try offline database first
            if key_clean in cities_coords:
                location_coords[(city, state)] = cities_coords[key_clean]
                resolved_count += 1
            else:
                # Try geocoding cache / API
                coords = geocode_city_state(city, state)
                if coords:
                    location_coords[(city, state)] = coords
                    api_hit_count += 1
                else:
                    unresolved_count += 1
                    logger.warning(f"Unable to resolve coordinates for {city}, {state}")

        # Save geocoding cache back
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(geo_cache, f, indent=2)
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Could not save geocoding cache: {e}"))

        # 5. Clean & Deduplicate Data in Memory
        # Sort by Retail Price ascending, so that drop_duplicates will keep the CHEAPEST retail price for duplicates of the same OPIS Truckstop ID
        df_fuel_sorted = df_fuel.sort_values(by="Retail Price", ascending=True)
        df_fuel_clean = df_fuel_sorted.drop_duplicates(subset=["OPIS Truckstop ID"], keep="first")
        
        # 6. Prepare Model Instances
        fuel_price_instances = []
        for _, row in df_fuel_clean.iterrows():
            opis_id = int(row["OPIS Truckstop ID"])
            name = str(row["Truckstop Name"]).strip()
            address = str(row["Address"]).strip()
            city = str(row["City"]).strip()
            state = str(row["State"]).strip()
            rack_id = int(row["Rack ID"]) if pd.notna(row["Rack ID"]) else None
            price = float(row["Retail Price"])
            
            # Fetch coordinates
            coords = location_coords.get((city, state))
            lat, lon = (coords[0], coords[1]) if coords else (None, None)

            fuel_price_instances.append(
                FuelPrice(
                    opis_truckstop_id=opis_id,
                    truckstop_name=name,
                    address=address,
                    city=city,
                    state=state,
                    rack_id=rack_id,
                    retail_price=price,
                    latitude=lat,
                    longitude=lon,
                )
            )

        # 7. Bulk Upsert in Chunks
        chunk_size = 500
        total_created = 0
        total_updated = 0
        self.stdout.write(self.style.NOTICE(f"Inserting/updating {len(fuel_price_instances)} stations in database..."))

        try:
            with transaction.atomic():
                for i in range(0, len(fuel_price_instances), chunk_size):
                    chunk = fuel_price_instances[i:i+chunk_size]
                    # bulk_create performs upsert using PostgreSQL's ON CONFLICT
                    res = FuelPrice.objects.bulk_create(
                        chunk,
                        update_conflicts=True,
                        update_fields=[
                            "truckstop_name",
                            "address",
                            "city",
                            "state",
                            "rack_id",
                            "retail_price",
                            "latitude",
                            "longitude",
                            "updated_at",
                        ],
                        unique_fields=["opis_truckstop_id"],
                    )
                    total_created += len(res)
            self.stdout.write(self.style.SUCCESS(f"Successfully processed database updates."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Database bulk insert failed: {e}"))
            return

        duration = time.time() - t_start
        self.stdout.write(
            self.style.SUCCESS(
                f"Import summary:\n"
                f"- Total records in CSV: {len(df_fuel)}\n"
                f"- Deduplicated unique stations: {len(fuel_price_instances)}\n"
                f"- Resolved via local database: {resolved_count}\n"
                f"- Resolved via Geocoding API: {api_hit_count}\n"
                f"- Unresolved locations: {unresolved_count}\n"
                f"- Total time elapsed: {duration:.2f} seconds."
            )
        )
