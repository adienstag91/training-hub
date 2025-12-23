-- OTF Training Data Spine Schema
-- Core principle: ELT pattern - store raw first, normalize downstream

-- Raw email storage (idempotency via message_id + workout_date)
CREATE TABLE otf_email_raw (
    id SERIAL PRIMARY KEY,
    message_id TEXT NOT NULL,
    workout_date DATE NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    subject TEXT,
    raw_html TEXT NOT NULL,
    parsed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    
    -- Hard idempotency key: prevents duplicate ingestion
    CONSTRAINT unique_email_source UNIQUE (message_id, workout_date)
);

-- Normalized workout sessions
CREATE TABLE workout_session (
    id SERIAL PRIMARY KEY,
    
    -- Source tracking
    otf_email_id INTEGER REFERENCES otf_email_raw(id),
    source_type TEXT NOT NULL CHECK (source_type IN ('otf', 'strava', 'peloton')),
    
    -- Canonical entity key (stable linkage)
    entity_key TEXT NOT NULL UNIQUE,
    
    -- Workout metadata
    workout_date DATE NOT NULL,
    class_type TEXT CHECK (class_type IN ('ORANGE_60', 'ORANGE_90', 'TREAD_50', 'STRENGTH_50')),
    class_minutes INTEGER,
    
    -- Overall metrics
    total_calories INTEGER,
    splat_points INTEGER,
    avg_heart_rate INTEGER,
    max_heart_rate INTEGER,
    
    -- Classification evidence (stored as JSON for debugging)
    classification_evidence JSONB,
    
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Granular workout components (first-class run/row/strength)
CREATE TABLE workout_component (
    id SERIAL PRIMARY KEY,
    
    -- Link to session
    workout_session_id INTEGER NOT NULL REFERENCES workout_session(id) ON DELETE CASCADE,
    
    -- Canonical entity key for this component
    entity_key TEXT NOT NULL UNIQUE,
    
    -- Component type
    component_type TEXT NOT NULL CHECK (component_type IN ('run', 'row', 'strength')),
    
    -- Time metrics
    duration_seconds INTEGER NOT NULL,
    
    -- Distance metrics (always in meters for consistency)
    distance_meters INTEGER,  -- NULL for strength, populated for run/row
    
    -- Performance metrics
    avg_speed NUMERIC(5,2),
    max_speed NUMERIC(5,2),
    avg_pace TEXT, -- format: MM:SS
    
    -- Rowing-specific
    split_500m TEXT, -- format: MM:SS
    avg_watts INTEGER,
    
    -- Calculation metadata
    is_derived BOOLEAN DEFAULT FALSE, -- true if calculated (e.g., strength time as residual)
    
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    
    -- Enforce component-specific rules
    CONSTRAINT check_run_has_distance CHECK (
        component_type != 'run' OR distance_meters IS NOT NULL
    ),
    CONSTRAINT check_row_has_distance CHECK (
        component_type != 'row' OR distance_meters IS NOT NULL
    ),
    CONSTRAINT check_strength_no_distance CHECK (
        component_type != 'strength' OR distance_meters IS NULL
    )
);

-- Strava publishing tracking (output adapter)
CREATE TABLE strava_activity (
    id SERIAL PRIMARY KEY,
    
    -- Link back to source component
    workout_component_id INTEGER NOT NULL REFERENCES workout_component(id),
    
    -- Strava identifiers
    strava_activity_id BIGINT UNIQUE,
    
    -- Publishing metadata
    published_at TIMESTAMPTZ,
    last_synced_at TIMESTAMPTZ,
    sync_status TEXT CHECK (sync_status IN ('pending', 'published', 'failed', 'deleted')),
    sync_error TEXT,
    
    -- Raw Strava response
    strava_response JSONB,
    
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for common queries
CREATE INDEX idx_workout_session_date ON workout_session(workout_date DESC);
CREATE INDEX idx_workout_session_entity_key ON workout_session(entity_key);
CREATE INDEX idx_workout_component_session ON workout_component(workout_session_id);
CREATE INDEX idx_workout_component_entity_key ON workout_component(entity_key);
CREATE INDEX idx_strava_activity_component ON strava_activity(workout_component_id);

-- Comments for documentation
COMMENT ON TABLE otf_email_raw IS 'Raw OTF emails - never modified after insert. Source of truth for re-parsing.';
COMMENT ON TABLE workout_session IS 'Normalized workout sessions. One session may have multiple components.';
COMMENT ON TABLE workout_component IS 'Granular components: run, row, strength. Preserves OTF multi-modal structure.';
COMMENT ON TABLE strava_activity IS 'Strava publishing adapter. Tracks sync status, not source of truth.';

COMMENT ON COLUMN otf_email_raw.message_id IS 'Email Message-ID header - used for idempotency';
COMMENT ON COLUMN workout_session.entity_key IS 'Stable identifier: workout:{date}:otf:{studio_id}';
COMMENT ON COLUMN workout_component.entity_key IS 'Stable identifier: workout:{date}:otf_{type}:{session_id}';
COMMENT ON COLUMN workout_component.is_derived IS 'True if calculated (e.g. strength time = class_minutes - tread - row)';
