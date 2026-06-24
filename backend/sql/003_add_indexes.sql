-- Indexes for fuel stops search
CREATE INDEX IF NOT EXISTS idx_fuel_prices_lat_lon ON fuel_prices (latitude, longitude);
CREATE INDEX IF NOT EXISTS idx_fuel_prices_state_city ON fuel_prices (state, city);
CREATE INDEX IF NOT EXISTS idx_fuel_prices_price ON fuel_prices (retail_price);

-- Indexes for route cache search
CREATE INDEX IF NOT EXISTS idx_route_cache_queries ON route_cache (start_query, destination_query);
