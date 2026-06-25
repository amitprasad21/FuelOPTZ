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
@patch("apps.routing.services.RoutingService.geocode_address")
@patch("apps.routing.services.RoutingService.geocode_query")
@patch("requests.post")
def test_optimize_endpoint_success(
    mock_post, mock_geocode, mock_geocode_address, api_client, mock_fuel_stations
):
    url = reverse("optimize_route")

    # Setup mock geocoding results
    # Start: Columbus, OH -> 40.0, -83.0
    # Destination: Indianapolis, IN -> 39.7, -86.1
    mock_geocode.side_effect = [
        (40.0, -83.0),  # Start coordinates
        (39.7, -86.1),  # Destination coordinates
    ]
    mock_geocode_address.return_value = (39.7, -86.1)

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
    assert r.data["total_gallons"] == 18.0  # (180 miles / 10 mpg) refilled to full
    assert len(r.data["fuel_stops"]) == 1
    assert r.data["fuel_stops"][0]["name"] == "MOCK STOP B"
    assert r.data["total_fuel_cost"] == 45.0
    assert "map_url" in r.data
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


@pytest.mark.django_db
@patch("apps.routing.services.RoutingService.geocode_query")
def test_optimize_endpoint_outside_usa(mock_geocode, api_client):
    url = reverse("optimize_route")
    # Ottawa, Canada is outside the USA
    mock_geocode.side_effect = ValueError(
        "Location 'Ottawa, ON' is outside the United States."
    )

    payload = {"start": "Ottawa, ON", "destination": "New York, NY"}
    r = api_client.post(url, payload, format="json")
    assert r.status_code == status.HTTP_400_BAD_REQUEST
    assert "error" in r.data
    assert "outside the United States" in r.data["error"]


@pytest.mark.django_db
@patch("apps.routing.services.RoutingService.geocode_address")
@patch("apps.routing.services.RoutingService.geocode_query")
@patch("requests.post")
def test_map_view_success(
    mock_post, mock_geocode, mock_geocode_address, api_client, mock_fuel_stations
):
    # Setup mock geocoding results
    mock_geocode.side_effect = [
        (40.0, -83.0),
        (39.7, -86.1),
    ]
    mock_geocode_address.return_value = (39.7, -86.1)

    # First cache the route by calling the optimize endpoint
    route_url = reverse("optimize_route")
    mock_response = {
        "features": [
            {
                "properties": {
                    "summary": {
                        "distance": 180.0,
                        "duration": 10800.0,
                    }
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[-83.0, 40.0], [-86.1, 39.7]],
                },
            }
        ]
    }
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = mock_response

    payload = {"start": "Columbus, OH", "destination": "Indianapolis, IN"}
    api_client.post(route_url, payload, format="json")

    # Now request the map view
    map_url = reverse("route_map")
    r = api_client.get(
        map_url, {"start": "Columbus, OH", "destination": "Indianapolis, IN"}
    )
    assert r.status_code == 200
    assert b"<!DOCTYPE html>" in r.content
    assert b"FuelOPTZ" in r.content
    assert b"L.map" in r.content


def test_is_in_us_bounds():
    from apps.routing.services import RoutingService

    # Inside USA
    assert RoutingService.is_in_us(40.0, -83.0) is True
    assert RoutingService.is_in_us(39.7, -86.1) is True
    assert RoutingService.is_in_us(61.2, -149.9) is True  # Alaska
    assert RoutingService.is_in_us(21.3, -157.8) is True  # Hawaii

    # Far Outside USA
    assert RoutingService.is_in_us(51.5074, -0.1278) is False  # London, UK
    assert RoutingService.is_in_us(-33.8688, 151.2093) is False  # Sydney, Australia
