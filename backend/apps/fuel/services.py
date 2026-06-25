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
        3. Projects each station to the closest point on the route segments to determine its exact mile marker.
        4. Returns a list of station dicts sorted by their distance along the route.
        """
        if not route_coords:
            return []

        route_lats = np.array([pt[0] for pt in route_coords], dtype=np.float64)
        route_lons = np.array([pt[1] for pt in route_coords], dtype=np.float64)

        # 1. Compute bounding box and query candidates from database
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

        # 3. Project stations onto route segments to find closest point and distance
        seg_start_lats = route_lats[:-1]
        seg_start_lons = route_lons[:-1]
        seg_end_lats = route_lats[1:]
        seg_end_lons = route_lons[1:]

        nearby_stations = []

        for idx, station in enumerate(stations):
            s_lat = station_lats[idx]
            s_lon = station_lons[idx]

            # Vector from segment start to segment end: v = P_end - P_start
            v_lat = seg_end_lats - seg_start_lats
            v_lon = seg_end_lons - seg_start_lons

            # Vector from segment start to station: w = S - P_start
            w_lat = s_lat - seg_start_lats
            w_lon = s_lon - seg_start_lons

            # Dot product w . v
            dot_wv = w_lat * v_lat + w_lon * v_lon
            # Dot product v . v
            dot_vv = v_lat * v_lat + v_lon * v_lon

            # Projection factor t
            t = np.zeros_like(dot_wv)
            mask = dot_vv > 1e-12
            t[mask] = dot_wv[mask] / dot_vv[mask]
            t = np.clip(t, 0.0, 1.0)

            # Projected coordinates on segments
            proj_lats = seg_start_lats + t * v_lat
            proj_lons = seg_start_lons + t * v_lon

            # Compute distance from station to projected points on segments
            dists_to_proj = cls.haversine_distance_vectorized(
                s_lat, s_lon, proj_lats, proj_lons
            )

            # Find the segment that is closest to the station
            best_seg_idx = np.argmin(dists_to_proj)
            min_dist = dists_to_proj[best_seg_idx]

            if min_dist <= max_distance_miles:
                # Cumulative distance at segment start plus fraction t of segment distance
                seg_len = seg_dists[best_seg_idx]
                station_cum_dist = route_cum_dists[best_seg_idx] + t[best_seg_idx] * seg_len

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
                        "dist_to_route": float(min_dist),
                        "dist": float(station_cum_dist),
                    }
                )

        # Sort stations by cumulative distance along the route (mile marker)
        nearby_stations.sort(key=lambda x: x["dist"])
        return nearby_stations
