-- Migration 001: Apple Health raw storage + wider component types
-- For databases created from the pre-migration schema.sql.
-- Fresh databases (docker compose first boot) already include all of this.
--
-- Apply with:
--   psql "$DATABASE_URL" -f migrations/001_apple_health_and_component_types.sql

BEGIN;

-- Raw storage for Apple Health workouts (ELT: keep the source JSON)
CREATE TABLE IF NOT EXISTS apple_health_raw (
    id SERIAL PRIMARY KEY,
    apple_workout_id TEXT NOT NULL UNIQUE,
    fetched_at TIMESTAMPTZ NOT NULL,
    raw_json JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Source FK for Apple Health sessions
ALTER TABLE workout_session
    ADD COLUMN IF NOT EXISTS apple_health_id INTEGER REFERENCES apple_health_raw(id);

-- Allow sessions with no source FK ('manual', and pre-migration Apple rows)
-- and include the new Apple FK in the exclusivity check.
ALTER TABLE workout_session DROP CONSTRAINT IF EXISTS check_single_source;
ALTER TABLE workout_session ADD CONSTRAINT check_single_source CHECK (
    (otf_email_id IS NOT NULL)::INTEGER +
    (strava_activity_id IS NOT NULL)::INTEGER +
    (peloton_workout_id IS NOT NULL)::INTEGER +
    (apple_health_id IS NOT NULL)::INTEGER <= 1
);

-- Widen component types for Apple Health / Peloton disciplines
ALTER TABLE workout_component DROP CONSTRAINT IF EXISTS workout_component_component_type_check;
ALTER TABLE workout_component ADD CONSTRAINT workout_component_component_type_check CHECK (
    component_type IN ('run', 'row', 'bike', 'strength', 'walk', 'hiit', 'yoga', 'flexibility', 'other')
);

COMMIT;
