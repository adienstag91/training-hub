-- Set schema to public
SET search_path TO public;

-- Training Hub Database Schema v2
-- Component-specific tables with raw metrics only
-- All distances in meters, all durations in seconds

-- ============================================================================
-- RAW SOURCE STORAGE (immutable)
-- ============================================================================

-- OrangeTheory email storage
CREATE TABLE otf_email_raw (
    id SERIAL PRIMARY KEY,
    message_id TEXT NOT NULL,
    workout_date DATE NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    subject TEXT,
    raw_html TEXT NOT NULL,
    parsed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    
    -- Hard idempotency: prevent duplicate ingestion
    CONSTRAINT unique_email_source UNIQUE (message_id, workout_date)
);

-- Strava activity storage (future)
CREATE TABLE strava_activity_raw (
    id SERIAL PRIMARY KEY,
    strava_activity_id BIGINT NOT NULL UNIQUE,
    fetched_at TIMESTAMPTZ NOT NULL,
    raw_json JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Peloton workout storage (CSV export rows or API payloads)
CREATE TABLE peloton_workout_raw (
    id SERIAL PRIMARY KEY,
    peloton_workout_id TEXT NOT NULL UNIQUE,
    fetched_at TIMESTAMPTZ NOT NULL,
    raw_json JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Apple Health workout storage (Health Auto Export JSON)
CREATE TABLE apple_health_raw (
    id SERIAL PRIMARY KEY,
    apple_workout_id TEXT NOT NULL UNIQUE,
    fetched_at TIMESTAMPTZ NOT NULL,
    raw_json JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- NORMALIZED WORKOUT DATA (source-agnostic)
-- ============================================================================

-- Unified workout sessions across all sources
CREATE TABLE workout_session (
    id SERIAL PRIMARY KEY,
    
    -- Source tracking (nullable FKs for different sources)
    otf_email_id INTEGER REFERENCES otf_email_raw(id),
    strava_activity_id INTEGER REFERENCES strava_activity_raw(id),
    peloton_workout_id INTEGER REFERENCES peloton_workout_raw(id),
    apple_health_id INTEGER REFERENCES apple_health_raw(id),
    source_type TEXT NOT NULL CHECK (source_type IN ('otf', 'strava', 'peloton', 'apple_health', 'manual')),
    
    -- Canonical entity key (stable linkage)
    entity_key TEXT NOT NULL UNIQUE,
    
    -- Workout metadata
    workout_date DATE NOT NULL,
    start_time TIMESTAMPTZ,
    
    -- OTF-specific (nullable for other sources)
    otf_class_type TEXT CHECK (otf_class_type IN ('ORANGE_60', 'ORANGE_90', 'TREAD_50', 'STRENGTH_50')),
    
    -- Overall session metrics (raw only)
    total_duration_seconds INTEGER,
    total_calories INTEGER,  -- Raw from source, not calculated
    
    -- Source-specific metadata (JSON for flexibility)
    source_metadata JSONB,
    
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    
    -- At most one source FK is populated ('manual' sessions have none)
    CONSTRAINT check_single_source CHECK (
        (otf_email_id IS NOT NULL)::INTEGER +
        (strava_activity_id IS NOT NULL)::INTEGER +
        (peloton_workout_id IS NOT NULL)::INTEGER +
        (apple_health_id IS NOT NULL)::INTEGER <= 1
    )
);

-- Base component table (minimal, shared fields only)
CREATE TABLE workout_component (
    id SERIAL PRIMARY KEY,
    workout_session_id INTEGER NOT NULL REFERENCES workout_session(id) ON DELETE CASCADE,
    
    -- Canonical entity key
    entity_key TEXT NOT NULL UNIQUE,
    
    -- Component type
    component_type TEXT NOT NULL CHECK (
        component_type IN ('run', 'row', 'bike', 'strength', 'walk', 'hiit', 'yoga', 'flexibility', 'other')
    ),
    
    -- Universal raw metrics (what every component has)
    duration_seconds INTEGER NOT NULL,
    
    -- Metadata
    is_derived BOOLEAN DEFAULT FALSE,  -- True if calculated (e.g., strength time as residual)
    sequence_order INTEGER,  -- Order within session (e.g., 1, 2, 3 for OTF blocks)
    
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    
    -- Enforce component-type rules via detail tables (checked in application)
    CONSTRAINT check_duration_positive CHECK (duration_seconds > 0)
);

-- ============================================================================
-- COMPONENT-SPECIFIC DETAIL TABLES (raw metrics only)
-- ============================================================================

-- Running component details
CREATE TABLE run_component (
    id SERIAL PRIMARY KEY,
    component_id INTEGER NOT NULL UNIQUE REFERENCES workout_component(id) ON DELETE CASCADE,
    
    -- Raw metrics (from source)
    distance_meters INTEGER NOT NULL,
    elevation_gain_meters INTEGER,
    elevation_loss_meters INTEGER,
    
    -- Heart rate (raw, not calculated)
    avg_heart_rate_bpm INTEGER,
    max_heart_rate_bpm INTEGER,
    
    -- Cadence (raw)
    avg_cadence_spm INTEGER,  -- Steps per minute
    
    -- GPS/Route (for outdoor runs)
    route_polyline TEXT,  -- Encoded polyline
    start_latitude DECIMAL(10, 8),
    start_longitude DECIMAL(11, 8),
    
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT check_distance_positive CHECK (distance_meters > 0)
);

-- Rowing component details
CREATE TABLE row_component (
    id SERIAL PRIMARY KEY,
    component_id INTEGER NOT NULL UNIQUE REFERENCES workout_component(id) ON DELETE CASCADE,
    
    -- Raw metrics
    distance_meters INTEGER NOT NULL,
    
    -- Stroke data (raw)
    avg_stroke_rate_spm INTEGER,  -- Strokes per minute
    avg_watts INTEGER,
    
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT check_distance_positive CHECK (distance_meters > 0)
);

-- Cycling component details
CREATE TABLE bike_component (
    id SERIAL PRIMARY KEY,
    component_id INTEGER NOT NULL UNIQUE REFERENCES workout_component(id) ON DELETE CASCADE,
    
    -- Raw metrics
    distance_meters INTEGER,  -- Nullable for stationary bike
    elevation_gain_meters INTEGER,  -- Nullable for stationary bike
    
    -- Heart rate
    avg_heart_rate_bpm INTEGER,
    max_heart_rate_bpm INTEGER,
    
    -- Cycling-specific
    avg_cadence_rpm INTEGER,  -- Revolutions per minute
    avg_power_watts INTEGER,
    avg_resistance INTEGER,  -- 0-100 scale for Peloton
    
    -- Peloton-specific
    instructor_name TEXT,
    
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Strength training component details
CREATE TABLE strength_component (
    id SERIAL PRIMARY KEY,
    component_id INTEGER NOT NULL UNIQUE REFERENCES workout_component(id) ON DELETE CASCADE,
    
    -- No distance for strength
    
    -- Heart rate
    avg_heart_rate_bpm INTEGER,
    max_heart_rate_bpm INTEGER,
    
    -- Strength-specific (optional tracking)
    exercises_json JSONB,  -- Array of {exercise, sets, reps, weight}
    muscle_groups TEXT[],  -- Array: ['chest', 'triceps']
    equipment_used TEXT[],  -- Array: ['dumbbells', 'barbell']
    
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- OUTPUT ADAPTERS (publishing back to external platforms)
-- ============================================================================

-- Strava activity publishing status
CREATE TABLE strava_activity_publish (
    id SERIAL PRIMARY KEY,
    workout_component_id INTEGER NOT NULL REFERENCES workout_component(id),
    
    -- Strava identifiers
    strava_activity_id BIGINT UNIQUE,
    
    -- Publishing status
    published_at TIMESTAMPTZ,
    last_synced_at TIMESTAMPTZ,
    sync_status TEXT CHECK (sync_status IN ('pending', 'published', 'failed', 'deleted')),
    sync_error TEXT,
    
    -- Raw Strava response
    strava_response JSONB,
    
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- INDEXES
-- ============================================================================

CREATE INDEX idx_workout_session_date ON workout_session(workout_date DESC);
CREATE INDEX idx_workout_session_source ON workout_session(source_type);
CREATE INDEX idx_workout_component_session ON workout_component(workout_session_id);
CREATE INDEX idx_workout_component_type ON workout_component(component_type);

-- ============================================================================
-- COMMENTS
-- ============================================================================

COMMENT ON TABLE otf_email_raw IS 'Raw OTF emails - immutable source of truth';
COMMENT ON TABLE workout_session IS 'Normalized sessions across all sources';
COMMENT ON TABLE workout_component IS 'Base component table - shared fields only';
COMMENT ON TABLE run_component IS 'Running-specific metrics (raw only, no calculated fields)';
COMMENT ON TABLE row_component IS 'Rowing-specific metrics (raw only)';
COMMENT ON TABLE bike_component IS 'Cycling-specific metrics (raw only)';
COMMENT ON TABLE strength_component IS 'Strength training metrics';

COMMENT ON COLUMN workout_component.is_derived IS 'True if calculated (e.g., OTF strength time as residual)';
COMMENT ON COLUMN run_component.distance_meters IS 'Raw distance - calculate pace downstream';
COMMENT ON COLUMN bike_component.distance_meters IS 'NULL for stationary bike (Peloton), populated for outdoor cycling';
