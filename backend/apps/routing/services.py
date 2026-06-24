import os
import logging
import requests
from apps.routing.models import RouteCache

logger = logging.getLogger(__name__)


class RoutingService:
    @staticmethod
    def geocode_query(query: str) -> tuple[float, float]:
        """
        Geocodes a search string (e.g. 'New York, NY') to (latitude, longitude)
        Tries OpenRouteService first, falls back to Nominatim.
        """
        query_clean = query.strip()
        ors_key = os.environ.get("ORS_API_KEY")

        # 1. Try OpenRouteService Geocoding
        if ors_key:
            try:
                url = "https://api.openrouteservice.org/v1/geocode/search"
                params = {"text": query_clean, "api_key": ors_key, "size": 1}
                r = requests.get(url, params=params, timeout=10)
                if r.status_code == 200:
                    data = r.json()
                    features = data.get("features", [])
                    if features:
                        coords = features[0]["geometry"]["coordinates"]
                        # ORS returns [longitude, latitude]
                        lon, lat = float(coords[0]), float(coords[1])
                        logger.info(f"Geocoded '{query}' via ORS to ({lat}, {lon})")
                        return lat, lon
            except Exception as e:
                logger.warning(f"ORS Geocoding failed for '{query_clean}': {e}")

        # 2. Fallback to OpenStreetMap Nominatim
        try:
            url = "https://nominatim.openstreetmap.org/search"
            headers = {"User-Agent": "FuelOPTZ-Routing/1.0 (antigravity@gemini)"}
            params = {"q": query_clean, "format": "json", "limit": 1}
            r = requests.get(url, params=params, headers=headers, timeout=10)
            if r.status_code == 200:
                data = r.json()
                if data:
                    lat, lon = float(data[0]["lat"]), float(data[0]["lon"])
                    logger.info(f"Geocoded '{query}' via Nominatim to ({lat}, {lon})")
                    return lat, lon
        except Exception as e:
            logger.error(f"Nominatim Geocoding failed for '{query_clean}': {e}")

        raise ValueError(f"Could not geocode location: '{query}'")

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
