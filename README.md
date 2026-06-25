# Fuel Stops Optimization API (FuelOPTZ)

A production-quality REST API that calculates the optimal fuel stop locations and quantities to minimize total fuel costs for a vehicle driving between any two USA cities.

## Tech Stack

*   **Python**: 3.13+
*   **Django**: Latest Stable (6.x)
*   **Django REST Framework**
*   **PostgreSQL** (Hosted on Supabase)
*   **Pandas & Numpy**: For high-performance offline database lookups, geocoding calculations, and spatial proximity filtering
*   **Pytest**: Complete testing framework
*   **OpenRouteService API**: Route geometry and geocoding engine

---

## Architecture & Design

This system is built using **Clean Architecture** principles:
*   **View Layer**: Light, thin REST endpoints with DRF Serializers.
*   **Service Layer**: Handles coordination between external APIs, spatial queries, and database caching.
*   **Domain Layer**: Pure business logic (the Fuel Optimizer engine) decoupled from framework abstractions, facilitating isolated unit testing.
*   **Data Layer**: Raw, independently-executable SQL migration files for Supabase combined with Django models.

For details, see [docs/ARCHITECTURE.md](backend/docs/ARCHITECTURE.md).

---

## Setup & Local Installation

### 1. Configure Environment Variables
Create a `.env` file in the project root folder. You can use the template provided:
```bash
cp .env.example .env
```
Ensure you set the `DATABASE_URL` (Postgres connection string) and `ORS_API_KEY` (OpenRouteService key).

### 2. Install Dependencies
Set up a python virtual environment and install packages:
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# Install requirements
pip install -r backend/requirements.txt
```

### 3. Run Database Migrations
Create the Postgres tables and spatial indexes. This executes our raw SQL schemas inside Supabase:
```bash
python backend/manage.py migrate
```

### 4. Import & Geocode Fuel Prices
Load the OPIS Truckstop dataset from the CSV file. This command downloads the U.S. cities database, cleans and deduplicates records, geocodes missing entries via Nominatim/ORS, and performs a bulk upsert:
```bash
python backend/manage.py import_fuel_prices
```

### 5. Launch the Server
```bash
python backend/manage.py runserver
```
The endpoint is available at: `POST http://localhost:8000/api/v1/routes/optimize/`

---

## Running with Docker

You can spin up the entire application inside Docker in one command:
```bash
docker compose up --build
```
This builds the backend image, applies migrations, imports/caches fuel prices, and exposes the port `8000`.

---

## Running Tests

Execute the complete test suite (unit, integration, and API tests):
```bash
pytest backend/
```

---

## API Documentation
See [docs/API.md](backend/docs/API.md) for full endpoint schemas and cURL examples. A Postman collection is also provided at [docs/Postman_Collection.json](docs/Postman_Collection.json).

---

