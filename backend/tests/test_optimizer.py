import pytest
from apps.optimization.fuel_optimizer import FuelOptimizer


def test_optimize_short_route_no_stops():
    # If route distance is 300 miles (less than 500 miles range), no stops are needed
    stations = [
        {
            "name": "S1",
            "address": "Addr 1",
            "city": "City 1",
            "state": "ST",
            "price": 3.0,
            "dist": 100.0,
            "latitude": 40.0,
            "longitude": -75.0,
        },
    ]
    res = FuelOptimizer.optimize(route_dist_miles=300.0, candidate_stations=stations)
    assert len(res["fuel_stops"]) == 0
    assert res["total_gallons"] == 0.0
    assert res["total_fuel_cost"] == 0.0


def test_optimize_greedy_cheaper_stop():
    # Route: 800 miles
    # Start: 0, S1: 300 (price 3.5), S2: 400 (price 3.0), S3: 600 (price 3.2)
    # Optimal: drive to S2, buy 30 gallons to reach Destination (800) with 0 fuel
    stations = [
        {
            "name": "S1",
            "address": "Addr 1",
            "city": "City 1",
            "state": "ST",
            "price": 3.5,
            "dist": 300.0,
            "latitude": 40.0,
            "longitude": -75.0,
        },
        {
            "name": "S2",
            "address": "Addr 2",
            "city": "City 2",
            "state": "ST",
            "price": 3.0,
            "dist": 400.0,
            "latitude": 41.0,
            "longitude": -76.0,
        },
        {
            "name": "S3",
            "address": "Addr 3",
            "city": "City 3",
            "state": "ST",
            "price": 3.2,
            "dist": 600.0,
            "latitude": 42.0,
            "longitude": -77.0,
        },
    ]
    res = FuelOptimizer.optimize(route_dist_miles=800.0, candidate_stations=stations)
    assert len(res["fuel_stops"]) == 1
    assert res["fuel_stops"][0]["name"] == "S2"
    assert (
        res["fuel_stops"][0]["gallons"] == 30.0
    )  # (800 - 400)/10 - 10 remaining fuel = 30
    assert res["total_fuel_cost"] == 90.0


def test_optimize_impossible_route():
    # S1 is 600 miles away, which is beyond our 500-mile vehicle range
    stations = [
        {
            "name": "S1",
            "address": "Addr 1",
            "city": "City 1",
            "state": "ST",
            "price": 3.0,
            "dist": 600.0,
            "latitude": 40.0,
            "longitude": -75.0,
        },
    ]
    with pytest.raises(ValueError) as excinfo:
        FuelOptimizer.optimize(route_dist_miles=1000.0, candidate_stations=stations)
    assert "Route cannot be completed" in str(excinfo.value)


def test_optimize_multiple_stops():
    # Route: 1200 miles
    # Start: 0, S1: 300 (price 3.5), S2: 400 (price 3.0), S3: 800 (price 3.2), S4: 900 (price 2.8)
    # Expected: S2 (buy 40 gallons), S4 (buy 30 gallons) -> total cost = 120 + 84 = 204
    stations = [
        {
            "name": "S1",
            "address": "Addr 1",
            "city": "City 1",
            "state": "ST",
            "price": 3.5,
            "dist": 300.0,
            "latitude": 40.0,
            "longitude": -75.0,
        },
        {
            "name": "S2",
            "address": "Addr 2",
            "city": "City 2",
            "state": "ST",
            "price": 3.0,
            "dist": 400.0,
            "latitude": 41.0,
            "longitude": -76.0,
        },
        {
            "name": "S3",
            "address": "Addr 3",
            "city": "City 3",
            "state": "ST",
            "price": 3.2,
            "dist": 800.0,
            "latitude": 42.0,
            "longitude": -77.0,
        },
        {
            "name": "S4",
            "address": "Addr 4",
            "city": "City 4",
            "state": "ST",
            "price": 2.8,
            "dist": 900.0,
            "latitude": 43.0,
            "longitude": -78.0,
        },
    ]
    res = FuelOptimizer.optimize(route_dist_miles=1200.0, candidate_stations=stations)
    assert len(res["fuel_stops"]) == 2
    assert res["fuel_stops"][0]["name"] == "S2"
    assert res["fuel_stops"][0]["gallons"] == 40.0
    assert res["fuel_stops"][1]["name"] == "S4"
    assert res["fuel_stops"][1]["gallons"] == 30.0
    assert res["total_fuel_cost"] == 204.0
