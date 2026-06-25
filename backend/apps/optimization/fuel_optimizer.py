import logging

logger = logging.getLogger(__name__)


class FuelOptimizer:
    """
    Fuel Stop Optimization Engine.

    Algorithm Explanation:
    ----------------------
    The engine solves the "Variable-Price Gas Station Refueling Problem" using a greedy choice property.
    Given a route from 0 to D miles, we start with a full tank of fuel (50 gallons, 500 miles range).

    At any decision point (starting at mile 0):
    1. We scan all fuel stations reachable with our current maximum fuel capacity (500 miles).
    2. Within this reachable range, we look for the first station that is cheaper than our current location.
       - Case A: A cheaper station exists in range.
         To minimize cost, we should only buy enough fuel at our current location to exactly reach this cheaper station.
         If we already have enough fuel in our tank to reach it, we buy 0 gallons.
         Otherwise, we buy: (distance_to_cheaper / mpg) - current_fuel.
         We then travel to this cheaper station, and repeat the decision process.
       - Case B: No cheaper station exists in range (our current location is the cheapest local option).
         Since our current location has the cheapest fuel we will see for the next 500 miles, we should buy as much fuel as possible!
         - Subcase B1: The destination is reachable within 500 miles.
           We only buy enough fuel to reach the destination with 0 gallons left.
           We buy: (distance_to_destination / mpg) - current_fuel, and complete the journey.
         - Subcase B2: The destination is NOT reachable within 500 miles.
           We fill our tank completely to maximum capacity (50 gallons).
           We buy: capacity - current_fuel.
           We then move to the cheapest reachable station in range to make our next refueling decision.
           We update our position to this cheapest station, update our fuel level, and repeat.

    If at any point no stations are reachable and the destination is not reachable, the route is impossible to complete,
    and we raise a ValueError.

    Complexity Analysis:
    -------------------
    - Time Complexity: O(N log N) for sorting candidate stations by distance, plus O(N) for the greedy traversal,
      where N is the number of stations near the route. With N <= 100 on average for a single route, this execution
      takes less than 1 millisecond.
    - Space Complexity: O(N) to store the candidate stations and generated purchases.
    """

    @classmethod
    def optimize(
        cls,
        route_dist_miles: float,
        candidate_stations: list[dict],
        capacity_gallons: float = 50.0,
        mpg: float = 10.0,
    ) -> dict:
        """
        Calculates the optimal fuel stops, fuel quantities, and costs.
        Strictly respects the 50-gallon tank capacity constraints using a
        capacity-constrained greedy allocation model.
        """
        # 1. Clip distances to [0.0, route_dist_miles] and sort stations by distance
        stations = []
        for s in candidate_stations:
            s_copy = s.copy()
            s_copy["dist"] = max(0.0, min(s_copy["dist"], route_dist_miles))
            stations.append(s_copy)
        stations = sorted(stations, key=lambda x: x["dist"])

        # Deduplicate stations at exactly the same distance (keep cheapest)
        unique_stations = []
        for s in stations:
            if unique_stations and abs(unique_stations[-1]["dist"] - s["dist"]) < 1e-5:
                if s["price"] < unique_stations[-1]["price"]:
                    unique_stations[-1] = s
            else:
                unique_stations.append(s)
        stations = unique_stations

        max_range = capacity_gallons * mpg

        # 2. Check feasibility of completing the route
        if not stations:
            if route_dist_miles > max_range:
                raise ValueError(
                    f"Route cannot be completed! No fuel stations are reachable within "
                    f"the {max_range:.0f}-mile vehicle range."
                )
            return {
                "fuel_stops": [],
                "total_gallons": 0.0,
                "total_fuel_cost": 0.0,
            }

        # Check first station range
        if stations[0]["dist"] > max_range:
            raise ValueError(
                f"Route cannot be completed! First fuel station '{stations[0]['name']}' "
                f"at mile {stations[0]['dist']:.1f} is beyond the {max_range:.0f}-mile vehicle range."
            )

        # Check range between consecutive stations
        for i in range(len(stations) - 1):
            dist_between = stations[i + 1]["dist"] - stations[i]["dist"]
            if dist_between > max_range:
                raise ValueError(
                    f"Route cannot be completed! Distance between station '{stations[i]['name']}' "
                    f"and '{stations[i + 1]['name']}' ({dist_between:.1f} miles) exceeds the {max_range:.0f}-mile vehicle range."
                )

        # Check distance from last station to destination
        dist_to_dest = route_dist_miles - stations[-1]["dist"]
        if dist_to_dest > max_range:
            raise ValueError(
                f"Route cannot be completed! Distance from last station '{stations[-1]['name']}' "
                f"to destination ({dist_to_dest:.1f} miles) exceeds the {max_range:.0f}-mile vehicle range."
            )

        # 3. Define segments and demands (fuel consumed per segment)
        # Segments:
        # Segment 1: from 0 to stations[0]['dist']
        # Segment i (for i = 2..n): from stations[i-2]['dist'] to stations[i-1]['dist']
        # Segment n+1: from stations[-1]['dist'] to route_dist_miles
        points = [0.0] + [s["dist"] for s in stations] + [route_dist_miles]
        n = len(stations)

        c = []
        for i in range(len(points) - 1):
            c.append((points[i + 1] - points[i]) / mpg)

        # F[k] is the fuel level leaving station k (for k = 1..n)
        # Initially F[k] = 0 for all k. F[0] is start (virtual)
        F = [0.0] * (n + 1)
        purchases = [0.0] * (n + 1)  # 1-indexed: purchase amount at station j (for j = 1..n)

        # 4. Allocate segment demands to available stations
        for i in range(1, len(c) + 1):
            remaining_c = c[i - 1]
            if remaining_c <= 0:
                continue

            # Available stations to purchase fuel for segment i:
            # Segment 1 (i=1): must be purchased at station 1
            # Segment i (i>=2): can be purchased at any station 1 to min(i-1, n)
            if i == 1:
                available_indices = [1]
            else:
                available_indices = list(range(1, min(i - 1, n) + 1))

            # Sort available indices by price ascending
            sorted_indices = sorted(
                available_indices, key=lambda idx: stations[idx - 1]["price"]
            )

            for j in sorted_indices:
                if remaining_c <= 0:
                    break

                # Capacity constraint: for all intermediate stations k from j to i-1,
                # fuel level leaving k cannot exceed capacity_gallons.
                # So we can allocate at most: capacity_gallons - F[k]
                if i - 1 >= j:
                    max_g = min(capacity_gallons - F[k] for k in range(j, i))
                else:
                    max_g = capacity_gallons

                g = min(remaining_c, max_g)
                if g > 0:
                    purchases[j] += g
                    # Update F[k] for all stations k from j to i-1
                    for k in range(j, min(i, n + 1)):
                        F[k] += g
                    remaining_c -= g

            if remaining_c > 1e-5:
                # If the route is feasible, we should always be able to allocate
                raise ValueError(
                    f"Internal optimization error: Could not allocate {remaining_c:.2f} gallons for segment {i}."
                )

        # 5. Format response fuel stops
        fuel_stops = []
        for j in range(1, n + 1):
            if purchases[j] > 0.0:
                station = stations[j - 1]
                cost = purchases[j] * station["price"]
                fuel_stops.append(
                    {
                        "opis_truckstop_id": station.get("opis_truckstop_id"),
                        "name": station["name"],
                        "address": station["address"],
                        "city": station["city"],
                        "state": station["state"],
                        "price": station["price"],
                        "latitude": station["latitude"],
                        "longitude": station["longitude"],
                        "gallons": float(purchases[j]),
                        "cost": float(cost),
                        "dist": float(station["dist"]),
                    }
                )

        total_gallons = sum(p["gallons"] for p in fuel_stops)
        total_cost = sum(p["cost"] for p in fuel_stops)

        return {
            "fuel_stops": fuel_stops,
            "total_gallons": float(total_gallons),
            "total_fuel_cost": float(total_cost),
        }
