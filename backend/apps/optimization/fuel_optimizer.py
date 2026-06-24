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
        mpg: float = 10.0
    ) -> dict:
        """
        Calculates the optimal fuel stops, fuel quantities, and costs.
        
        Args:
            route_dist_miles: Total distance of the route in miles.
            candidate_stations: List of dicts representing fuel stations near the route.
                                Must contain 'name', 'address', 'city', 'state', 'price', 'dist', 'latitude', 'longitude'.
            capacity_gallons: Maximum fuel capacity of the vehicle (default 50.0).
            mpg: Fuel efficiency of the vehicle in miles per gallon (default 10.0).
            
        Returns:
            A dict containing:
                - fuel_stops: List of optimal refueling stops with details.
                - total_gallons: Total gallons of fuel purchased.
                - total_fuel_cost: Total cost of fuel purchased.
        """
        # 1. Sort stations by distance along the route
        stations = sorted(candidate_stations, key=lambda x: x["dist"])
        
        # 2. Add Start and Destination as dummy stations to build the full graph
        start_stop = {
            "name": "Start Location",
            "address": "Origin",
            "city": "Start",
            "state": "US",
            "price": float("inf"),  # Start has 'infinite' price so we always want to leave it ASAP
            "dist": 0.0,
            "latitude": 0.0,
            "longitude": 0.0
        }
        dest_stop = {
            "name": "Destination",
            "address": "Terminus",
            "city": "End",
            "state": "US",
            "price": 0.0,  # Destination price is 0.0 so we want to arrive with 0 fuel
            "dist": route_dist_miles,
            "latitude": 0.0,
            "longitude": 0.0
        }
        all_stops = [start_stop] + stations + [dest_stop]
        
        current_idx = 0
        current_fuel = capacity_gallons
        max_range = capacity_gallons * mpg
        purchases = []
        
        while current_idx < len(all_stops) - 1:
            curr = all_stops[current_idx]
            
            # Find all reachable stops from current position
            reachable_stops = []
            for j in range(current_idx + 1, len(all_stops)):
                dist_to_j = all_stops[j]["dist"] - curr["dist"]
                if dist_to_j <= max_range:
                    reachable_stops.append((j, all_stops[j]))
                else:
                    break
            
            if not reachable_stops:
                raise ValueError(
                    f"Route cannot be completed! No fuel stations are reachable within "
                    f"the {max_range:.0f}-mile vehicle range from '{curr['name']}' at mile {curr['dist']:.1f}."
                )
                
            # Find the first reachable stop that is cheaper than our current stop
            cheaper_stop = None
            for idx, stop in reachable_stops:
                if stop["price"] < curr["price"]:
                    cheaper_stop = (idx, stop)
                    break
                    
            if cheaper_stop:
                # Case A: Found a cheaper stop in range. Buy only enough fuel to reach it.
                next_idx, next_stop = cheaper_stop
                dist_to_next = next_stop["dist"] - curr["dist"]
                fuel_needed = dist_to_next / mpg
                
                if current_fuel >= fuel_needed:
                    fuel_to_buy = 0.0
                else:
                    fuel_to_buy = fuel_needed - current_fuel
                    
                if fuel_to_buy > 0.0:
                    cost = fuel_to_buy * curr["price"]
                    purchases.append({
                        "name": curr["name"],
                        "address": curr["address"],
                        "city": curr["city"],
                        "state": curr["state"],
                        "price": curr["price"],
                        "latitude": curr["latitude"],
                        "longitude": curr["longitude"],
                        "gallons": fuel_to_buy,
                        "cost": cost,
                        "dist": curr["dist"]
                    })
                    current_fuel = 0.0
                else:
                    current_fuel -= fuel_needed
                    
                current_idx = next_idx
            else:
                # Case B: No cheaper stop in range. Current stop is the cheapest local option.
                # Check if destination is reachable
                dest_in_range = False
                for idx, stop in reachable_stops:
                    if stop["name"] == "Destination":
                        dest_in_range = True
                        dest_idx = idx
                        dest_stop = stop
                        break
                        
                if dest_in_range:
                    # Subcase B1: Destination is reachable. Buy only enough to reach it.
                    dist_to_dest = dest_stop["dist"] - curr["dist"]
                    fuel_needed = dist_to_dest / mpg
                    
                    if current_fuel >= fuel_needed:
                        fuel_to_buy = 0.0
                    else:
                        fuel_to_buy = fuel_needed - current_fuel
                        
                    if fuel_to_buy > 0.0:
                        cost = fuel_to_buy * curr["price"]
                        purchases.append({
                            "name": curr["name"],
                            "address": curr["address"],
                            "city": curr["city"],
                            "state": curr["state"],
                            "price": curr["price"],
                            "latitude": curr["latitude"],
                            "longitude": curr["longitude"],
                            "gallons": fuel_to_buy,
                            "cost": cost,
                            "dist": curr["dist"]
                        })
                    break  # Destination reached, exit optimization loop
                else:
                    # Subcase B2: Destination is not reachable. Fill tank to maximum capacity here.
                    fuel_to_buy = capacity_gallons - current_fuel
                    if fuel_to_buy > 0.0:
                        cost = fuel_to_buy * curr["price"]
                        purchases.append({
                            "name": curr["name"],
                            "address": curr["address"],
                            "city": curr["city"],
                            "state": curr["state"],
                            "price": curr["price"],
                            "latitude": curr["latitude"],
                            "longitude": curr["longitude"],
                            "gallons": fuel_to_buy,
                            "cost": cost,
                            "dist": curr["dist"]
                        })
                    current_fuel = capacity_gallons
                    
                    # Move to the cheapest reachable station in range
                    # This station becomes our next decision point
                    cheapest_reachable = min(reachable_stops, key=lambda x: x[1]["price"])
                    next_idx, next_stop = cheapest_reachable
                    dist_to_next = next_stop["dist"] - curr["dist"]
                    current_fuel -= (dist_to_next / mpg)
                    current_idx = next_idx
                    
        total_gallons = sum(p["gallons"] for p in purchases)
        total_cost = sum(p["cost"] for p in purchases)
        
        return {
            "fuel_stops": purchases,
            "total_gallons": float(total_gallons),
            "total_fuel_cost": float(total_cost)
        }
