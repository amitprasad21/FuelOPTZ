-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Fuel Price Table
CREATE TABLE IF NOT EXISTS fuel_prices (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    opis_truckstop_id INTEGER NOT NULL UNIQUE,
    truckstop_name VARCHAR(255) NOT NULL,
    address VARCHAR(255) NOT NULL,
    city VARCHAR(255) NOT NULL,
    state VARCHAR(50) NOT NULL,
    rack_id INTEGER,
    retail_price DECIMAL(10, 4) NOT NULL,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
