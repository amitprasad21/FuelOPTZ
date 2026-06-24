-- Route Cache Table
CREATE TABLE IF NOT EXISTS route_cache (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    start_query VARCHAR(255) NOT NULL,
    destination_query VARCHAR(255) NOT NULL,
    start_lat DOUBLE PRECISION NOT NULL,
    start_lon DOUBLE PRECISION NOT NULL,
    dest_lat DOUBLE PRECISION NOT NULL,
    dest_lon DOUBLE PRECISION NOT NULL,
    distance_miles DOUBLE PRECISION NOT NULL,
    estimated_duration DOUBLE PRECISION NOT NULL,
    route_geometry JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
