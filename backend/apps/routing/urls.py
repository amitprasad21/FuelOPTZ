from django.urls import path
from apps.routing.views import OptimizeRouteView, RouteMapView

urlpatterns = [
    path("optimize/", OptimizeRouteView.as_view(), name="optimize_route"),
    path("map/", RouteMapView.as_view(), name="route_map"),
]
