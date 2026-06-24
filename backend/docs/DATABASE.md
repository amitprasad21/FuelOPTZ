# Database Documentation

The database schema is fully managed using PostgreSQL. The project follows a hybrid migrations strategy:
- Database tables and indexes are described in raw, independently-executable SQL scripts located under `backend/sql/`.
- Django migrations read these raw SQL files and execute them directly on the Supabase database. This guarantees that Django models and database schemas are always in perfect sync, while allowing administrators to run the SQL directly in the Supabase SQL editor.

---

## Schema Diagrams

### `fuel_prices` Table
Stores geocoded fuel stop prices imported from the CSV.

*   `id`: UUID (Primary Key, default: `uuid_generate_v4()`)
*   `opis_truckstop_id`: Integer (Unique, indexed)
*   `truckstop_name`: VarChar(255)
*   `address`: VarChar(255)
*   `city`: VarChar(255)
*   `state`: VarChar(50)
*   `rack_id`: Integer (Nullable)
*   `retail_price`: Decimal(10, 4)
*   `latitude`: Double Precision (Nullable, indexed)
*   `longitude`: Double Precision (Nullable, indexed)
*   `created_at`: Timestamp with timezone
*   `updated_at`: Timestamp with timezone

### `route_cache` Table
Caches geocoded route geometry and metadata to minimize OpenRouteService API usage.

*   `id`: UUID (Primary Key, default: `uuid_generate_v4()`)
*   `start_query`: VarChar(255) (Indexed)
*   `destination_query`: VarChar(255) (Indexed)
*   `start_lat`: Double Precision
*   `start_lon`: Double Precision
*   `dest_lat`: Double Precision
*   `dest_lon`: Double Precision
*   `distance_miles`: Double Precision
*   `estimated_duration`: Double Precision
*   `route_geometry`: JSONB (Contains the GeoJSON LineString coordinates)
*   `created_at`: Timestamp with timezone

---

## Indexes & Performance Optimizations

1.  **Unique Constraint on `opis_truckstop_id`**: Enables highly performant `ON CONFLICT DO UPDATE` bulk upserts during CSV import, preventing duplicate records.
2.  **Spatial Coordinate Index on `(latitude, longitude)`**: Used for fast bounding-box queries to retrieve candidate fuel stations along a route.
3.  **Compound Index on `(start_query, destination_query)`**: Accelerates route cache hits, enabling lookups in less than 5ms.
