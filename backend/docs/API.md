# API Documentation

## Optimize Route & Fuel Stops
Calculates the optimal fuel stop locations and prices for a vehicle driving between two USA cities.

*   **Endpoint**: `/api/v1/routes/optimize/`
*   **Method**: `POST`
*   **Content-Type**: `application/json`

### Request Payload
```json
{
  "start": "New York, NY",
  "destination": "Los Angeles, CA"
}
```

### Success Response (`200 OK`)
```json
{
  "distance_miles": 2794.3,
  "estimated_duration": 149200.0,
  "fuel_stops": [
    {
      "name": "PILOT TRAVEL CENTER #348",
      "address": "I-80, EXIT 4",
      "city": "Shorter",
      "state": "AL",
      "price": 3.154,
      "latitude": 32.399,
      "longitude": -85.955,
      "gallons": 50.0,
      "cost": 157.7,
      "dist": 420.5
    }
  ],
  "total_gallons": 229.43,
  "total_fuel_cost": 720.55,
  "route_geometry": {
    "type": "LineString",
    "coordinates": [
      [-74.006, 40.7128],
      [-75.165, 39.9526],
      [-118.243, 34.0522]
    ]
  }
}
```

### Error Responses

#### Bad Request (`400 Bad Request`)
If the start or destination locations are missing or cannot be geocoded, or if the route cannot be completed (e.g. islands/disconnected areas):
```json
{
  "error": "Could not geocode location: 'InvalidCity, ZZ'"
}
```
Or if request parameters fail validation:
```json
{
  "start": [
    "Start location cannot be empty."
  ]
}
```

#### Internal Server Error (`500 Internal Server Error`)
If external APIs fail or database connection errors occur:
```json
{
  "error": "An unexpected error occurred while processing the route optimization. Please try again later."
}
```

---

## cURL Example
```bash
curl -X POST http://localhost:8000/api/v1/routes/optimize/ \
     -H "Content-Type: application/json" \
     -d '{"start": "New York, NY", "destination": "Los Angeles, CA"}'
```
