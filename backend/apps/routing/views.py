import time
import json
import logging
from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from apps.routing.models import RouteCache
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

            # On-the-fly geocoding for recommended stops to guarantee precise coordinates
            for stop in optimization_result["fuel_stops"]:
                try:
                    from apps.fuel.models import FuelPrice

                    station_db = FuelPrice.objects.filter(
                        opis_truckstop_id=stop["opis_truckstop_id"]
                    ).first()
                    if station_db:
                        coords = RoutingService.geocode_address(
                            station_db.address, station_db.city, station_db.state
                        )
                        if coords:
                            lat, lon = coords
                            station_db.latitude = lat
                            station_db.longitude = lon
                            station_db.save(update_fields=["latitude", "longitude"])
                            stop["latitude"] = lat
                            stop["longitude"] = lon
                except Exception as ex:
                    logger.warning(
                        f"On-the-fly geocoding failed for stop {stop['name']}: {ex}"
                    )

            # 5. Format Response
            total_duration = time.time() - t_start
            logger.info(
                f"OptimizeRouteView: Request processed successfully in {total_duration*1000:.2f}ms"
            )

            from django.urls import reverse
            import urllib.parse

            map_base_url = request.build_absolute_uri(reverse("route_map"))
            params = urllib.parse.urlencode(
                {"start": start, "destination": destination}
            )
            map_url = f"{map_base_url}?{params}"

            response_data = {
                "distance_miles": float(route.distance_miles),
                "estimated_duration": float(route.estimated_duration),
                "fuel_stops": optimization_result["fuel_stops"],
                "total_gallons": float(optimization_result["total_gallons"]),
                "total_fuel_cost": float(optimization_result["total_fuel_cost"]),
                "map_url": map_url,
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


class RouteMapView(APIView):
    def get(self, request, *args, **kwargs):
        start = request.GET.get("start")
        destination = request.GET.get("destination")

        if not start or not destination:
            return HttpResponse("Missing start or destination parameter.", status=400)

        try:
            start_clean = start.strip().upper()
            dest_clean = destination.strip().upper()
            route = RouteCache.objects.filter(
                start_query=start_clean, destination_query=dest_clean
            ).first()

            if not route:
                route = RoutingService.get_route(start, destination)

            geojson_coords = route.route_geometry.get("coordinates", [])
            if not geojson_coords:
                raise ValueError("Route geometry does not contain coordinates.")

            route_coords = [(float(pt[1]), float(pt[0])) for pt in geojson_coords]

            nearby_stations = FuelService.get_stations_near_route(
                route_coords, max_distance_miles=15.0
            )

            optimization_result = FuelOptimizer.optimize(
                route_dist_miles=route.distance_miles,
                candidate_stations=nearby_stations,
                capacity_gallons=50.0,
                mpg=10.0,
            )

            # Geocode recommended stops on the fly for exact coordinates
            for stop in optimization_result["fuel_stops"]:
                try:
                    from apps.fuel.models import FuelPrice

                    station_db = FuelPrice.objects.filter(
                        opis_truckstop_id=stop["opis_truckstop_id"]
                    ).first()
                    if station_db:
                        coords = RoutingService.geocode_address(
                            station_db.address, station_db.city, station_db.state
                        )
                        if coords:
                            lat, lon = coords
                            station_db.latitude = lat
                            station_db.longitude = lon
                            station_db.save(update_fields=["latitude", "longitude"])
                            stop["latitude"] = lat
                            stop["longitude"] = lon
                except Exception as ex:
                    logger.warning(
                        f"On-the-fly geocoding failed for stop {stop['name']}: {ex}"
                    )

            html_content = self.render_map_html(
                route, route_coords, optimization_result
            )
            return HttpResponse(html_content, content_type="text/html")

        except Exception as e:
            logger.exception(f"Error rendering route map: {e}")
            return HttpResponse(f"Error rendering route map: {str(e)}", status=500)

    def render_map_html(self, route, route_coords, optimization_result) -> str:
        route_geojson = {
            "type": "Feature",
            "geometry": route.route_geometry,
            "properties": {},
        }
        stops_js = json.dumps(optimization_result["fuel_stops"])

        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>FuelOPTZ - Route Map</title>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap" rel="stylesheet">
    <style>
        body, html {{
            margin: 0;
            padding: 0;
            height: 100%;
            font-family: 'Outfit', sans-serif;
            background-color: #121212;
            color: #e0e0e0;
        }}
        #map {{
            height: 100vh;
            width: 100vw;
            z-index: 1;
        }}
        .control-panel {{
            position: absolute;
            top: 20px;
            left: 20px;
            z-index: 1000;
            background: rgba(18, 18, 18, 0.85);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
            max-width: 320px;
        }}
        .control-panel h1 {{
            margin: 0 0 8px 0;
            font-size: 22px;
            font-weight: 800;
            color: #ffffff;
            letter-spacing: -0.5px;
            background: linear-gradient(45deg, #00f2fe, #4facfe);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .route-info {{
            margin-top: 15px;
            font-size: 14px;
            border-top: 1px solid rgba(255, 255, 255, 0.1);
            padding-top: 15px;
        }}
        .route-info-row {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 8px;
        }}
        .route-info-label {{
            color: #888888;
        }}
        .route-info-value {{
            font-weight: 600;
            color: #ffffff;
        }}
        .leaflet-popup-content-wrapper {{
            background: #1e1e1e !important;
            color: #ffffff !important;
            border-radius: 8px !important;
            box-shadow: 0 3px 14px rgba(0,0,0,0.4) !important;
            border: 1px solid rgba(255,255,255,0.1) !important;
        }}
        .leaflet-popup-tip {{
            background: #1e1e1e !important;
        }}
        .leaflet-container a {{
            color: #4facfe !important;
        }}
        .marker-title {{
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 4px;
            color: #ffffff;
        }}
        .marker-details {{
            font-size: 13px;
            color: #aaaaaa;
            line-height: 1.4;
        }}
        .marker-price {{
            font-size: 14px;
            font-weight: 600;
            color: #00f2fe;
            margin-top: 6px;
        }}
    </style>
</head>
<body>
    <div class="control-panel">
        <h1>FuelOPTZ</h1>
        <div style="font-size: 12px; color: #888888;">Optimal Fuel Stops Route Map</div>
        <div class="route-info">
            <div class="route-info-row">
                <span class="route-info-label">From:</span>
                <span class="route-info-value" id="info-start"></span>
            </div>
            <div class="route-info-row">
                <span class="route-info-label">To:</span>
                <span class="route-info-value" id="info-dest"></span>
            </div>
            <div class="route-info-row">
                <span class="route-info-label">Distance:</span>
                <span class="route-info-value">{route.distance_miles:.1f} miles</span>
            </div>
            <div class="route-info-row">
                <span class="route-info-label">Total Gallons:</span>
                <span class="route-info-value">{optimization_result["total_gallons"]:.1f} gal</span>
            </div>
            <div class="route-info-row">
                <span class="route-info-label">Total Fuel Cost:</span>
                <span class="route-info-value" style="color: #00f2fe">${optimization_result["total_fuel_cost"]:.2f}</span>
            </div>
        </div>
    </div>
    
    <div id="map"></div>

    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
        document.getElementById("info-start").innerText = "{route.start_query}";
        document.getElementById("info-dest").innerText = "{route.destination_query}";

        const map = L.map('map', {{
            zoomControl: false
        }});
        
        L.control.zoom({{ position: 'bottomright' }}).addTo(map);

        L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
            subdomains: 'abcd',
            maxZoom: 20
        }}).addTo(map);

        const routeGeoJSON = {json.dumps(route_geojson)};
        const routeLayer = L.geoJSON(routeGeoJSON, {{
            style: {{
                color: '#4facfe',
                weight: 5,
                opacity: 0.8
            }}
        }}).addTo(map);

        map.fitBounds(routeLayer.getBounds(), {{ padding: [50, 50] }});

        const createSvgIcon = (color, char) => L.divIcon({{
            html: `<svg width="32" height="32" viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg">
                    <path d="M16 0C9.37 0 4 5.37 4 12c0 9 12 20 12 20s12-11 12-20c0-6.63-5.37-12-12-12z" fill="${{color}}"/>
                    <circle cx="16" cy="12" r="6" fill="#121212"/>
                    <text x="16" y="15" fill="#ffffff" font-size="10" font-family="'Outfit', sans-serif" font-weight="bold" text-anchor="middle">${{char}}</text>
                   </svg>`,
            className: 'custom-svg-icon',
            iconSize: [32, 32],
            iconAnchor: [16, 32],
            popupAnchor: [0, -32]
        }});

        const startIcon = createSvgIcon('#2ecc71', 'S');
        const destIcon = createSvgIcon('#e74c3c', 'D');
        const fuelIcon = createSvgIcon('#f39c12', 'F');

        const startCoord = [{route.start_lat}, {route.start_lon}];
        L.marker(startCoord, {{ icon: startIcon }})
            .bindPopup(`<div class="marker-title">Start Location</div><div class="marker-details">{route.start_query}</div>`)
            .addTo(map);

        const destCoord = [{route.dest_lat}, {route.dest_lon}];
        L.marker(destCoord, {{ icon: destIcon }})
            .bindPopup(`<div class="marker-title">Destination</div><div class="marker-details">{route.destination_query}</div>`)
            .addTo(map);

        const stops = {stops_js};
        stops.forEach((stop, index) => {{
            if (stop.latitude && stop.longitude) {{
                const popupContent = `
                    <div class="marker-title">#${{index + 1}} Refueling Stop</div>
                    <div class="marker-details">
                        <strong>${{stop.name}}</strong><br/>
                        ${{stop.address}}<br/>
                        ${{stop.city}}, ${{stop.state}}<br/>
                        <strong>Distance:</strong> ${{stop.dist.toFixed(1)}} mi
                    </div>
                    <div class="marker-price">
                        <strong>Price:</strong> $${{stop.price.toFixed(2)}}/gal<br/>
                        <strong>Buy:</strong> ${{stop.gallons.toFixed(1)}} gal<br/>
                        <strong>Cost:</strong> $${{stop.cost.toFixed(2)}}
                    </div>
`;
                L.marker([stop.latitude, stop.longitude], {{ icon: fuelIcon }})
                    .bindPopup(popupContent)
                    .addTo(map);
            }}
        }});
    </script>
</body>
</html>
"""
        return html
