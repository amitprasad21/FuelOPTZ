import numpy as np
from apps.fuel.models import FuelPrice


class FuelService:
    @staticmethod
    def haversine_distance_vectorized(lats1, lons1, lats2, lons2):
        """
        Computes Haversine distance in miles between arrays of coordinates.
        Supports numpy broadcasting.
        """
        R = 3958.8  # Earth's radius in miles

        # Convert degrees to radians
        lats1, lons1, lats2, lons2 = map(np.radians, [lats1, lons1, lats2, lons2])

        dlat = lats2 - lats1
        dlon = lons2 - lons1

        a = (
            np.sin(dlat / 2.0) ** 2
            + np.cos(lats1) * np.cos(lats2) * np.sin(dlon / 2.0) ** 2
        )
        c = 2.0 * np.arcsin(np.sqrt(a))

        return R * c

    @classmethod
    def get_stations_near_route(
        cls, route_coords: list[tuple[float, float]], max_distance_miles: float = 15.0
    ) -> list[dict]:
        """
        Given a list of (latitude, longitude) route coordinates:
        1. Queries stations in the database within the expanded route bounding box.
        2. Filters stations within max_distance_miles of the route.
        3. Projects each station to the closest point on the route to determine its mile marker.
        4. Returns a list of station dicts sorted by their distance along the route.
        """
        if not route_coords:
            return []

        route_lats = np.array([pt[0] for pt in route_coords], dtype=np.float64)
        route_lons = np.array([pt[1] for pt in route_coords], dtype=np.float64)

        # 1. Compute bounding box and query candidates from database
        # 15 miles ~ 0.25 degrees of latitude/longitude as an approximation
        margin = max_distance_miles / 69.0  # 69 miles per degree of latitude
        min_lat = float(np.min(route_lats)) - margin
        max_lat = float(np.max(route_lats)) + margin

        # Longitude degrees shrink as we go north. At US average latitude (38 degrees), 1 degree is ~55 miles.
        margin_lon = max_distance_miles / 55.0
        min_lon = float(np.min(route_lons)) - margin_lon
        max_lon = float(np.max(route_lons)) + margin_lon

        stations_qs = FuelPrice.objects.filter(
            latitude__range=(min_lat, max_lat), longitude__range=(min_lon, max_lon)
        )

        if not stations_qs.exists():
            return []

        # Load stations into memory
        stations = list(stations_qs)
        station_lats = np.array([s.latitude for s in stations], dtype=np.float64)
        station_lons = np.array([s.longitude for s in stations], dtype=np.float64)

        # 2. Compute cumulative distances along the route (mile markers)
        seg_dists = cls.haversine_distance_vectorized(
            route_lats[:-1], route_lons[:-1], route_lats[1:], route_lons[1:]
        )
        route_cum_dists = np.zeros(len(route_coords), dtype=np.float64)
        route_cum_dists[1:] = np.cumsum(seg_dists)

        # 2b. Downsample route points for spatial distance matrix to keep it under ~2ms
        downsampled_coords = [route_coords[0]]
        downsampled_indices = [0]
        for idx in range(1, len(route_coords) - 1):
            pt = route_coords[idx]
            last_pt = downsampled_coords[-1]
            dist = cls.haversine_distance_vectorized(
                last_pt[0], last_pt[1], pt[0], pt[1]
            )
            if dist >= 1.5:
                downsampled_coords.append(pt)
                downsampled_indices.append(idx)
        if (len(route_coords) - 1) not in downsampled_indices:
            downsampled_coords.append(route_coords[-1])
            downsampled_indices.append(len(route_coords) - 1)

        downsampled_lats = np.array(
            [pt[0] for pt in downsampled_coords], dtype=np.float64
        )
        downsampled_lons = np.array(
            [pt[1] for pt in downsampled_coords], dtype=np.float64
        )

        # 3. Vectorized distance calculation from stations to all downsampled route points
        # Shape: (num_stations, num_downsampled_route_points)
        # Using numpy broadcasting to compute pairwise distances
        dists = cls.haversine_distance_vectorized(
            station_lats[:, np.newaxis],
            station_lons[:, np.newaxis],
            downsampled_lats,
            downsampled_lons,
        )

        # Find the index of the closest downsampled route point for each station
        closest_downsampled_indices = np.argmin(dists, axis=1)
        # Map back to original route indices
        closest_indices = np.array(downsampled_indices)[closest_downsampled_indices]
        # Get the actual distance to the closest route point in miles
        min_dists = dists[np.arange(len(stations)), closest_downsampled_indices]
        # Get the cumulative distance along the route at that closest point (projected mile marker)
        station_cum_dists = route_cum_dists[closest_indices]

        # 4. Filter stations within max_distance_miles and format output
        nearby_stations = []
        for idx, station in enumerate(stations):
            dist_to_route = min_dists[idx]
            if dist_to_route <= max_distance_miles:
                nearby_stations.append(
                    {
                        "id": str(station.id),
                        "opis_truckstop_id": station.opis_truckstop_id,
                        "name": station.truckstop_name,
                        "address": station.address,
                        "city": station.city,
                        "state": station.state,
                        "price": float(station.retail_price),
                        "latitude": station.latitude,
                        "longitude": station.longitude,
                        "dist_to_route": float(dist_to_route),
                        "dist": float(
                            station_cum_dists[idx]
                        ),  # Cumulative distance (mile marker) along the route
                    }
                )

        # Sort stations by cumulative distance along the route (mile marker)
        nearby_stations.sort(key=lambda x: x["dist"])
        return nearby_stations
