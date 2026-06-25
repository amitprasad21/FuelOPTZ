import os
import json
import time
import logging
import csv
import io
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
    help = "Imports fuel prices from a CSV file, geocodes locations at address-level, and performs bulk inserts."

    def add_arguments(self, parser):
        parser.add_argument(
            "--csv-path",
            type=str,
            default=os.path.join(
                settings.BASE_DIR.parent, "fuel-prices-for-be-assessment.csv"
            ),
            help="Path to the fuel prices CSV file.",
        )
        parser.add_argument(
            "--force-download-cities",
            action="store_true",
            help="Forces re-downloading the cities database from GitHub.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Forces import even if database already contains fuel prices.",
        )

    def handle(self, *args, **options):
        csv_path = options["csv_path"]
        force_download = options["force_download_cities"]
        force_import = options["force"]

        t_start = time.time()

        # Download Leaflet JS & CSS if they don't exist
        static_dir = os.path.join(settings.BASE_DIR, "apps", "routing", "static", "routing")
        os.makedirs(static_dir, exist_ok=True)
        
        leaflet_css_path = os.path.join(static_dir, "leaflet.css")
        leaflet_js_path = os.path.join(static_dir, "leaflet.js")
        
        if not os.path.exists(leaflet_css_path):
            self.stdout.write(self.style.NOTICE("Downloading leaflet.css locally..."))
            try:
                r = requests.get("https://unpkg.com/leaflet@1.9.4/dist/leaflet.css", timeout=15)
                r.raise_for_status()
                with open(leaflet_css_path, "wb") as f:
                    f.write(r.content)
                self.stdout.write(self.style.SUCCESS("Downloaded leaflet.css successfully."))
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"Failed to download leaflet.css: {e}"))
                
        if not os.path.exists(leaflet_js_path):
            self.stdout.write(self.style.NOTICE("Downloading leaflet.js locally..."))
            try:
                r = requests.get("https://unpkg.com/leaflet@1.9.4/dist/leaflet.js", timeout=15)
                r.raise_for_status()
                with open(leaflet_js_path, "wb") as f:
                    f.write(r.content)
                self.stdout.write(self.style.SUCCESS("Downloaded leaflet.js successfully."))
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"Failed to download leaflet.js: {e}"))

        # 1. Skip logic if records exist
        if FuelPrice.objects.exists() and not force_import:
            self.stdout.write(
                self.style.SUCCESS(
                    "Fuel prices already imported in database. Skipping import (use --force to re-import)."
                )
            )
            return

        self.stdout.write(
            self.style.NOTICE(f"Starting fuel price import from {csv_path}...")
        )

        if not os.path.exists(csv_path):
            self.stdout.write(self.style.ERROR(f"CSV file not found at: {csv_path}"))
            return

        # 2. Download/Load US Cities Coordinates DB (for fallback)
        cities_csv_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "us_cities.csv"
        )
        if not os.path.exists(cities_csv_path) or force_download:
            self.stdout.write(
                self.style.NOTICE("Downloading US Cities Database from GitHub...")
            )
            try:
                r = requests.get(CITIES_DB_URL, timeout=30)
                r.raise_for_status()
                with open(cities_csv_path, "wb") as f:
                    f.write(r.content)
                self.stdout.write(
                    self.style.SUCCESS("Downloaded US Cities Database successfully.")
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"Failed to download cities database: {e}")
                )
                if not os.path.exists(cities_csv_path):
                    self.stdout.write(
                        self.style.ERROR("No local cities database available. Exiting.")
                    )
                    return

        df_cities = pd.read_csv(cities_csv_path)
        df_cities["city_clean"] = df_cities["CITY"].astype(str).str.strip().str.upper()
        df_cities["state_clean"] = (
            df_cities["STATE_CODE"].astype(str).str.strip().str.upper()
        )

        cities_coords = {}
        for _, row in df_cities.iterrows():
            key = (row["city_clean"], row["state_clean"])
            if key not in cities_coords:
                cities_coords[key] = (float(row["LATITUDE"]), float(row["LONGITUDE"]))

        # 3. Read and Clean Fuel Price CSV
        df_fuel = pd.read_csv(csv_path)
        df_fuel.columns = [col.strip() for col in df_fuel.columns]

        # 4. Filter out Canadian records (USA-only)
        canada_provinces = {
            "AB",
            "ON",
            "BC",
            "MB",
            "SK",
            "QC",
            "NB",
            "NS",
            "NL",
            "PE",
            "YT",
            "NT",
            "NU",
        }
        df_fuel = df_fuel[
            ~df_fuel["State"].astype(str).str.strip().str.upper().isin(canada_provinces)
        ]

        # 5. Deduplicate In Memory (keep cheapest price per unique station ID)
        df_fuel_sorted = df_fuel.sort_values(by="Retail Price", ascending=True)
        df_fuel_clean = df_fuel_sorted.drop_duplicates(
            subset=["OPIS Truckstop ID"], keep="first"
        )

        # 6. Load Geocoding Cache (for fallbacks)
        cache_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "geocoding_cache.json"
        )
        geo_cache = {}
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    geo_cache = json.load(f)
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(f"Could not load geocoding cache: {e}")
                )

        # 7. U.S. Census batch geocoding (exact address-level coordinates)
        self.stdout.write(
            self.style.NOTICE("Batch geocoding USA stations via U.S. Census Bureau...")
        )

        csv_buffer = io.StringIO()
        csv_writer = csv.writer(csv_buffer)
        for _, row in df_fuel_clean.iterrows():
            opis_id = int(row["OPIS Truckstop ID"])
            address = str(row["Address"]).strip()
            city = str(row["City"]).strip()
            state = str(row["State"]).strip()
            csv_writer.writerow([opis_id, address, city, state, ""])

        csv_payload = csv_buffer.getvalue()
        address_coords = {}

        try:
            url = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"
            payload = {"benchmark": "Public_AR_Current"}
            files = {
                "addressFile": ("batch.csv", io.BytesIO(csv_payload.encode("utf-8")))
            }

            r = requests.post(url, files=files, data=payload, timeout=120)
            if r.status_code == 200:
                response_buffer = io.StringIO(r.text)
                reader = csv.reader(response_buffer)
                match_count = 0
                for row_data in reader:
                    if len(row_data) >= 6 and row_data[2] == "Match":
                        opis_id = int(row_data[0])
                        lon_lat = row_data[5].split(",")
                        if len(lon_lat) == 2:
                            lon, lat = float(lon_lat[0]), float(lon_lat[1])
                            address_coords[opis_id] = (lat, lon)
                            match_count += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"U.S. Census geocoder matched {match_count} / {len(df_fuel_clean)} addresses."
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"U.S. Census batch geocoder returned status {r.status_code}."
                    )
                )
        except Exception as e:
            self.stdout.write(
                self.style.WARNING(f"U.S. Census batch geocoding failed: {e}.")
            )

        # 8. Geocoding Cache/Online Fallback Helper for City-level
        ors_key = os.environ.get("ORS_API_KEY")

        def geocode_city_state(city, state):
            city_clean = city.strip()
            state_clean = state.strip()
            cache_key = f"{city_clean}, {state_clean}".upper()

            if cache_key in geo_cache:
                return geo_cache[cache_key]

            # ORS Geocoding with USA boundary limitation
            if ors_key:
                try:
                    url = "https://api.openrouteservice.org/v1/geocode/search"
                    params = {
                        "text": f"{city_clean}, {state_clean}",
                        "api_key": ors_key,
                        "boundary.country": "USA",
                        "size": 1,
                    }
                    r = requests.get(url, params=params, timeout=10)
                    if r.status_code == 200:
                        data = r.json()
                        features = data.get("features", [])
                        if features:
                            coords = features[0]["geometry"]["coordinates"]
                            lon, lat = float(coords[0]), float(coords[1])
                            from apps.routing.services import RoutingService
                            if RoutingService.is_in_us(lat, lon):
                                geo_cache[cache_key] = (lat, lon)
                                return lat, lon
                except Exception as ex:
                    logger.warning(f"ORS geocoding failed: {ex}")

            # Nominatim geocoding with USA countrycodes limitation
            try:
                headers = {"User-Agent": "FuelOPTZ-Importer/1.0 (antigravity@gemini)"}
                url = "https://nominatim.openstreetmap.org/search"
                params = {
                    "city": city_clean,
                    "state": state_clean,
                    "countrycodes": "us",
                    "format": "json",
                    "limit": 1,
                }
                time.sleep(1.0)
                r = requests.get(url, params=params, headers=headers, timeout=10)
                if r.status_code == 200:
                    data = r.json()
                    if data:
                        lat, lon = float(data[0]["lat"]), float(data[0]["lon"])
                        from apps.routing.services import RoutingService
                        if RoutingService.is_in_us(lat, lon):
                            geo_cache[cache_key] = (lat, lon)
                            return lat, lon
            except Exception as ex:
                logger.warning(f"Nominatim geocoding failed: {ex}")

            return None

        # 9. Map remaining stations using offline cities database or geocoding fallbacks
        self.stdout.write(
            self.style.NOTICE("Resolving coordinates for unmatched stations...")
        )
        resolved_count = 0
        fallback_resolved = 0
        unresolved_count = 0

        location_coords = {}
        unique_locs = df_fuel_clean[["City", "State"]].drop_duplicates()

        for _, loc in unique_locs.iterrows():
            city = str(loc["City"]).strip()
            state = str(loc["State"]).strip()
            key_clean = (city.upper(), state.upper())

            if key_clean in cities_coords:
                location_coords[(city, state)] = cities_coords[key_clean]
                resolved_count += 1
            else:
                coords = geocode_city_state(city, state)
                if coords:
                    location_coords[(city, state)] = coords
                    fallback_resolved += 1
                else:
                    unresolved_count += 1
                    logger.warning(
                        f"Unable to resolve coordinates for city fallback: {city}, {state}"
                    )

        # Save geocoding cache back
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(geo_cache, f, indent=2)
        except Exception as e:
            self.stdout.write(
                self.style.WARNING(f"Could not save geocoding cache: {e}")
            )

        # 10. Prepare Model Instances
        fuel_price_instances = []
        for _, row in df_fuel_clean.iterrows():
            opis_id = int(row["OPIS Truckstop ID"])
            name = str(row["Truckstop Name"]).strip()
            address = str(row["Address"]).strip()
            city = str(row["City"]).strip()
            state = str(row["State"]).strip()
            rack_id = int(row["Rack ID"]) if pd.notna(row["Rack ID"]) else None
            price = float(row["Retail Price"])

            # Hybrid resolution: exact address coordinates first, then fallback
            if opis_id in address_coords:
                lat, lon = address_coords[opis_id]
            else:
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

        # 11. Bulk Upsert in Chunks
        chunk_size = 500
        total_created = 0
        self.stdout.write(
            self.style.NOTICE(
                f"Inserting/updating {len(fuel_price_instances)} stations in database..."
            )
        )

        try:
            with transaction.atomic():
                for i in range(0, len(fuel_price_instances), chunk_size):
                    chunk = fuel_price_instances[i : i + chunk_size]
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
            self.stdout.write(
                self.style.SUCCESS("Successfully processed database updates.")
            )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Database bulk insert failed: {e}"))
            return

        duration = time.time() - t_start
        self.stdout.write(
            self.style.SUCCESS(
                f"Import summary:\n"
                f"- Total USA records in CSV: {len(df_fuel)}\n"
                f"- Deduplicated unique stations: {len(fuel_price_instances)}\n"
                f"- Resolved via exact address (Census): {len(address_coords)}\n"
                f"- Resolved via local database: {resolved_count}\n"
                f"- Resolved via geocoding API fallback: {fallback_resolved}\n"
                f"- Unresolved locations: {unresolved_count}\n"
                f"- Total time elapsed: {duration:.2f} seconds."
            )
        )
