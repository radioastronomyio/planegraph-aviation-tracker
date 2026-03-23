-- 010: FAA Aircraft Registry lookup table
-- Refreshed weekly from FAA ReleasableAircraft.zip

CREATE TABLE IF NOT EXISTS aircraft_registry (
    hex VARCHAR(6) PRIMARY KEY,           -- ICAO 24-bit address (uppercase hex)
    n_number VARCHAR(10),                  -- FAA N-number (e.g., "N551CP")
    manufacturer VARCHAR(100),
    model VARCHAR(100),
    aircraft_type VARCHAR(50),             -- From ACFTREF: "Fixed Wing Single-Engine", etc.
    engine_type VARCHAR(50),               -- "Turbo-Fan", "Reciprocating", etc.
    engine_count SMALLINT,
    weight_class VARCHAR(20),              -- "CLASS 1", "CLASS 2", "CLASS 3", "CLASS 4"
    owner_name VARCHAR(100),
    owner_city VARCHAR(50),
    owner_state VARCHAR(2),
    fleet_category VARCHAR(20) NOT NULL DEFAULT 'Unknown',  -- Computed: Commercial/GA/Military/Cargo/Unknown
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_registry_n_number ON aircraft_registry (n_number);
CREATE INDEX IF NOT EXISTS idx_registry_fleet_category ON aircraft_registry (fleet_category);

COMMENT ON TABLE aircraft_registry IS 'FAA aircraft registry, refreshed weekly. Source: FAA ReleasableAircraft.zip';
