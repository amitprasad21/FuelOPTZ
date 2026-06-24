import pytest
from unittest.mock import patch
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from apps.fuel.models import FuelPrice
from apps.routing.models import RouteCache


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def mock_fuel_stations():
    # Insert a few mock fuel stations in DB
    FuelPrice.objects.create(
        opis_truckstop_id=888801,
        truckstop_name="MOCK STOP A",
        address="100 Interstate",
        city="Columbus",
        state="OH",
        retail_price=3.00,
        latitude=40.0,
        longitude=-83.0,
    )
    FuelPrice.objects.create(
        opis_truckstop_id=888802,
        truckstop_name="MOCK STOP B",
        address="200 Highway",
        city="Indianapolis",
        state="IN",
        retail_price=2.50,
        latitude=39.7,
        longitude=-86.1,
    )


@pytest.mark.django_db
def test_optimize_endpoint_validation_errors(api_client):
    url = reverse("optimize_route")

    # 1. Missing start and destination
    r = api_client.post(url, {}, format="json")
    assert r.status_code == status.HTTP_400_BAD_REQUEST
    assert "start" in r.data
    assert "destination" in r.data

    # 2. Empty values
    r = api_client.post(url, {"start": "", "destination": "Chicago, IL"}, format="json")
    assert r.status_code == status.HTTP_400_BAD_REQUEST
    assert "start" in r.data

    # 3. Same locations
    r = api_client.post(
        url, {"start": "Chicago, IL", "destination": "Chicago, IL"}, format="json"
    )
    assert r.status_code == status.HTTP_400_BAD_REQUEST
    assert "non_field_errors" in r.data


@pytest.mark.django_db
@patch("apps.routing.services.RoutingService.geocode_query")
@patch("requests.post")
def test_optimize_endpoint_success(
    mock_post, mock_geocode, api_client, mock_fuel_stations
):
    url = reverse("optimize_route")

    # Setup mock geocoding results
    # Start: Columbus, OH -> 40.0, -83.0
    # Destination: Indianapolis, IN -> 39.7, -86.1
    mock_geocode.side_effect = [
        (40.0, -83.0),  # Start coordinates
        (39.7, -86.1),  # Destination coordinates
    ]

    # Setup mock OpenRouteService Directions API response
    mock_response = {
        "features": [
            {
                "properties": {
                    "summary": {
                        "distance": 180.0,  # 180 miles
                        "duration": 10800.0,  # 3 hours
                    }
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[-83.0, 40.0], [-84.5, 39.8], [-86.1, 39.7]],
                },
            }
        ]
    }
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = mock_response

    payload = {"start": "Columbus, OH", "destination": "Indianapolis, IN"}

    # First request: Cache MISS, calls geocoding and directions mock APIs
    r = api_client.post(url, payload, format="json")
    assert r.status_code == status.HTTP_200_OK
    assert r.data["distance_miles"] == 180.0
    assert r.data["estimated_duration"] == 10800.0
    assert (
        r.data["total_gallons"] == 0.0
    )  # distance is 180 miles < 500 range, no fuel stop needed
    assert len(r.data["fuel_stops"]) == 0
    assert "route_geometry" in r.data

    # Verify Cache was created
    assert RouteCache.objects.filter(
        start_query="COLUMBUS, OH", destination_query="INDIANAPOLIS, IN"
    ).exists()

    # Second request: Cache HIT, no API calls
    mock_geocode.reset_mock()
    mock_post.reset_mock()

    r_cached = api_client.post(url, payload, format="json")
    assert r_cached.status_code == status.HTTP_200_OK
    assert r_cached.data["distance_miles"] == 180.0
    mock_geocode.assert_not_called()
    mock_post.assert_not_called()
