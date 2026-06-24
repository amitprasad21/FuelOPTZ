from django.urls import path
from apps.routing.views import OptimizeRouteView

urlpatterns = [
    path("optimize/", OptimizeRouteView.as_view(), name="optimize_route"),
]
