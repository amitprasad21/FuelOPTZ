import time
import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from apps.routing.serializers import OptimizeRouteSerializer
from apps.routing.services import RoutingService
from apps.fuel.services import FuelService
from apps.optimization.fuel_optimizer import FuelOptimizer

logger = logging.getLogger(__name__)


class OptimizeRouteView(APIView):
    def post(self, request, *args, **kwargs):
        t_start = time.time()
        logger.info(
            f"OptimizeRouteView: Request received from {request.META.get('REMOTE_ADDR')}"
        )

        # 1. Validate Request Data
        serializer = OptimizeRouteSerializer(data=request.data)
        if not serializer.is_valid():
            logger.warning(f"OptimizeRouteView: Validation failed: {serializer.errors}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        start = serializer.validated_data["start"]
        destination = serializer.validated_data["destination"]

        try:
            # 2. Get Geocoded & Cached Route
            logger.info(
                f"OptimizeRouteView: Fetching route from '{start}' to '{destination}'"
            )
            route = RoutingService.get_route(start, destination)

            # Extract coordinates from GeoJSON LineString (GeoJSON uses [lon, lat])
            geojson_coords = route.route_geometry.get("coordinates", [])
            if not geojson_coords:
                raise ValueError("Route geometry does not contain coordinates.")

            # Convert from [lon, lat] to (lat, lon) for our calculations
            route_coords = [(float(pt[1]), float(pt[0])) for pt in geojson_coords]

            # 3. Retrieve Candidate Fuel Stops Near Route
            logger.info("OptimizeRouteView: Filtering fuel stations near the route...")
            nearby_stations = FuelService.get_stations_near_route(
                route_coords, max_distance_miles=15.0
            )
            logger.info(
                f"OptimizeRouteView: Found {len(nearby_stations)} fuel stations near the route."
            )

            # 4. Optimize Refuel Stops
            logger.info("OptimizeRouteView: Starting fuel stop optimization...")
            optimization_result = FuelOptimizer.optimize(
                route_dist_miles=route.distance_miles,
                candidate_stations=nearby_stations,
                capacity_gallons=50.0,
                mpg=10.0,
            )
            logger.info(
                "OptimizeRouteView: Fuel stop optimization completed successfully."
            )

            # 5. Format Response
            total_duration = time.time() - t_start
            logger.info(
                f"OptimizeRouteView: Request processed successfully in {total_duration*1000:.2f}ms"
            )

            response_data = {
                "distance_miles": float(route.distance_miles),
                "estimated_duration": float(route.estimated_duration),
                "fuel_stops": optimization_result["fuel_stops"],
                "total_gallons": float(optimization_result["total_gallons"]),
                "total_fuel_cost": float(optimization_result["total_fuel_cost"]),
                "route_geometry": route.route_geometry,
            }

            return Response(response_data, status=status.HTTP_200_OK)

        except ValueError as ve:
            logger.warning(f"OptimizeRouteView: Validation/Route error: {ve}")
            return Response({"error": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception(f"OptimizeRouteView: Unexpected error occurred: {e}")
            return Response(
                {
                    "error": "An unexpected error occurred while processing the route optimization. Please try again later."
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
