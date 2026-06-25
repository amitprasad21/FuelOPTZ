import os
import logging
import requests
import pandas as pd
from apps.routing.models import RouteCache

logger = logging.getLogger(__name__)

_cities_cache = None


class RoutingService:
    @staticmethod
    def is_in_us(lat: float, lon: float) -> bool:
        """
        Validates if coordinates are within USA bounding boxes.
        Includes Mainland, Alaska, and Hawaii.
        """
        # Mainland: 24.396308 to 49.384358 lat, -125.0011 to -66.93457 lon
        # Alaska: 51.214183 to 71.387687 lat, -179.148909 to -129.97951 lon
        # Hawaii: 18.91619 to 28.402169 lat, -178.334698 to -154.806773 lon
        if 24.0 <= lat <= 50.0 and -125.0 <= lon <= -66.0:
            return True
        if 51.0 <= lat <= 72.0 and -180.0 <= lon <= -129.0:
            return True
        if 18.0 <= lat <= 29.0 and -179.0 <= lon <= -154.0:
            return True
        return False

    @staticmethod
    def geocode_query(query: str) -> tuple[float, float]:
        """
        Geocodes a search string (e.g. 'New York, NY') to (latitude, longitude)
        Tries offline database lookup first, then OpenRouteService, and falls back to Nominatim.
        """
        global _cities_cache
        query_clean = query.strip()

        # 0. Try offline cities database lookup
        parts = [p.strip() for p in query_clean.split(",")]
        if len(parts) == 2:
            city, state = parts[0].upper(), parts[1].upper()
            if _cities_cache is None:
                try:
                    base_dir = os.path.dirname(
                        os.path.dirname(os.path.abspath(__file__))
                    )
                    csv_path = os.path.join(
                        base_dir, "fuel", "management", "commands", "us_cities.csv"
                    )
                    if os.path.exists(csv_path):
                        df = pd.read_csv(csv_path)
                        cache = {}
                        for _, row in df.iterrows():
                            c_clean = str(row["CITY"]).strip().upper()
                            s_clean = str(row["STATE_CODE"]).strip().upper()
                            cache[(c_clean, s_clean)] = (
                                float(row["LATITUDE"]),
                                float(row["LONGITUDE"]),
                            )
                            if "STATE_NAME" in row:
                                s_name = str(row["STATE_NAME"]).strip().upper()
                                cache[(c_clean, s_name)] = (
                                    float(row["LATITUDE"]),
                                    float(row["LONGITUDE"]),
                                )
                        _cities_cache = cache
                    else:
                        _cities_cache = {}
                except Exception as e:
                    logger.warning(f"Failed to load offline cities database: {e}")
                    _cities_cache = {}

            coords = _cities_cache.get((city, state))
            if coords:
                lat, lon = coords
                logger.info(f"Geocoded '{query}' offline to ({lat}, {lon})")
                return lat, lon

        # 1. Try OpenRouteService Geocoding
        ors_key = os.environ.get("ORS_API_KEY")
        if ors_key:
            try:
                url = "https://api.openrouteservice.org/v1/geocode/search"
                params = {
                    "text": query_clean,
                    "api_key": ors_key,
                    "size": 1,
                    "boundary.country": "USA",
                }
                r = requests.get(url, params=params, timeout=10)
                if r.status_code == 200:
                    data = r.json()
                    features = data.get("features", [])
                    if features:
                        coords = features[0]["geometry"]["coordinates"]
                        lon, lat = float(coords[0]), float(coords[1])

                        # Extra validation: check if the geocoder properties identify the country as USA
                        props = features[0].get("properties", {})
                        country = props.get("country", "").upper()
                        country_code = props.get("country_a", "").upper()
                        if (
                            country
                            and country
                            not in ["UNITED STATES", "USA", "UNITED STATES OF AMERICA"]
                        ) or (country_code and country_code not in ["US", "USA"]):
                            raise ValueError(
                                f"Location '{query}' is outside the United States."
                            )

                        logger.info(f"Geocoded '{query}' via ORS to ({lat}, {lon})")
                        if not RoutingService.is_in_us(lat, lon):
                            raise ValueError(
                                f"Location '{query}' is outside the United States."
                            )
                        return lat, lon
            except Exception as e:
                logger.warning(f"ORS Geocoding failed for '{query_clean}': {e}")
                if "outside the United States" in str(e):
                    raise

        # 2. Fallback to OpenStreetMap Nominatim
        try:
            url = "https://nominatim.openstreetmap.org/search"
            headers = {"User-Agent": "FuelOPTZ-Routing/1.0 (antigravity@gemini)"}
            params = {
                "q": query_clean,
                "format": "json",
                "limit": 1,
                "countrycodes": "us",
            }
            r = requests.get(url, params=params, headers=headers, timeout=10)
            if r.status_code == 200:
                data = r.json()
                if data:
                    lat, lon = float(data[0]["lat"]), float(data[0]["lon"])
                    display_name = data[0].get("display_name", "")
                    if (
                        "United States" not in display_name
                        and "USA" not in display_name
                    ):
                        if any(
                            c in display_name
                            for c in [", Canada", ", United Kingdom", ", Mexico"]
                        ):
                            raise ValueError(
                                f"Location '{query}' is outside the United States."
                            )

                    logger.info(f"Geocoded '{query}' via Nominatim to ({lat}, {lon})")
                    if not RoutingService.is_in_us(lat, lon):
                        raise ValueError(
                            f"Location '{query}' is outside the United States."
                        )
                    return lat, lon
        except Exception as e:
            logger.error(f"Nominatim Geocoding failed for '{query_clean}': {e}")
            if "outside the United States" in str(e):
                raise

        raise ValueError(f"Could not geocode location: '{query}'")

    @staticmethod
    def geocode_address(
        address: str, city: str, state: str
    ) -> tuple[float, float] | None:
        """
        Geocodes a street address on the fly using ORS or Nominatim.
        """
        query = f"{address}, {city}, {state}"
        ors_key = os.environ.get("ORS_API_KEY")
        if ors_key:
            try:
                url = "https://api.openrouteservice.org/v1/geocode/search"
                params = {
                    "text": query,
                    "api_key": ors_key,
                    "size": 1,
                    "boundary.country": "USA",
                }
                r = requests.get(url, params=params, timeout=5)
                if r.status_code == 200:
                    data = r.json()
                    features = data.get("features", [])
                    if features:
                        coords = features[0]["geometry"]["coordinates"]
                        return float(coords[1]), float(coords[0])
            except Exception as e:
                logger.warning(f"Failed to geocode address via ORS: {e}")

        try:
            url = "https://nominatim.openstreetmap.org/search"
            headers = {"User-Agent": "FuelOPTZ-Routing/1.0 (antigravity@gemini)"}
            params = {"q": query, "format": "json", "limit": 1, "countrycodes": "us"}
            r = requests.get(url, params=params, headers=headers, timeout=5)
            if r.status_code == 200:
                data = r.json()
                if data:
                    return float(data[0]["lat"]), float(data[0]["lon"])
        except Exception as e:
            logger.warning(f"Failed to geocode address via Nominatim: {e}")

        return None

    @classmethod
    def get_route(cls, start_query: str, dest_query: str) -> RouteCache:
        """
        Retrieves route from database cache or calls OpenRouteService to fetch,
        caching the result before returning.
        """
        start_clean = start_query.strip().upper()
        dest_clean = dest_query.strip().upper()

        # 1. Check Cache
        cached_route = RouteCache.objects.filter(
            start_query=start_clean, destination_query=dest_clean
        ).first()

        if cached_route:
            logger.info(f"Route Cache HIT: {start_clean} to {dest_clean}")
            return cached_route

        logger.info(
            f"Route Cache MISS: {start_clean} to {dest_clean}. Fetching from routing API..."
        )

        # 2. Geocode start and destination queries
        start_lat, start_lon = cls.geocode_query(start_query)
        dest_lat, dest_lon = cls.geocode_query(dest_query)

        if abs(start_lat - dest_lat) < 1e-6 and abs(start_lon - dest_lon) < 1e-6:
            raise ValueError(
                "Start and destination coordinates are the same."
            )

        # 3. Call OpenRouteService Directions API (GeoJSON endpoint)
        ors_key = os.environ.get("ORS_API_KEY")
        if not ors_key:
            raise ValueError(
                "OpenRouteService API key (ORS_API_KEY) is missing in environment."
            )

        url = "https://api.openrouteservice.org/v2/directions/driving-car/geojson"
        headers = {"Authorization": ors_key, "Content-Type": "application/json"}
        # ORS coordinates are passed as [longitude, latitude]
        body = {
            "coordinates": [[start_lon, start_lat], [dest_lon, dest_lat]],
            "geometry": True,
            "units": "mi",  # request distance in miles
        }

        try:
            r = requests.post(url, json=body, headers=headers, timeout=15)
            if r.status_code != 200:
                logger.error(
                    f"ORS directions API returned error: {r.status_code} - {r.text}"
                )
                raise ValueError(
                    f"Directions API request failed with status {r.status_code}"
                )

            data = r.json()
        except Exception as e:
            logger.error(f"Failed to fetch directions from ORS: {e}")
            raise

        # 4. Parse the GeoJSON response
        try:
            feature = data["features"][0]
            properties = feature["properties"]
            summary = properties["summary"]

            # ORS units='mi' gives distance in miles, duration is in seconds
            distance_miles = float(summary["distance"])
            duration_seconds = float(summary["duration"])
            geometry = feature["geometry"]  # Contains LineString coordinates
        except (KeyError, IndexError, TypeError) as e:
            logger.error(f"Failed to parse directions GeoJSON response: {e}")
            raise ValueError("Invalid response format received from routing API.")

        # 5. Save to Cache
        cached_route = RouteCache.objects.create(
            start_query=start_clean,
            destination_query=dest_clean,
            start_lat=start_lat,
            start_lon=start_lon,
            dest_lat=dest_lat,
            dest_lon=dest_lon,
            distance_miles=distance_miles,
            estimated_duration=duration_seconds,
            route_geometry=geometry,
        )
        logger.info(
            f"Route Cache saved: {start_clean} to {dest_clean} ({distance_miles} miles)"
        )
        return cached_route
