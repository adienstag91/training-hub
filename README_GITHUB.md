# Training Hub

A production-grade data engineering pipeline for normalizing multi-source training data. Ingests workouts from OrangeTheory, Strava, Peloton, and Apple Health into a unified PostgreSQL database, enabling cross-platform analytics and training plan generation.

## Overview

Modern athletes use multiple training platforms — OrangeTheory for structured classes, Strava for outdoor runs, Peloton for cycling, Apple Watch for daily tracking. Each platform has its own data format, metrics, and idiosyncrasies.

**Training Hub** solves this by:
- **Ingesting** workouts from multiple sources with source-specific parsers
- **Normalizing** into a unified schema (sessions → components)
- **Enriching** with computed metrics (intensity proxies, volume rollups)
- **Publishing** back to platforms like Strava (optional output adapter)
- **Analyzing** across all sources for training insights

## Why This is Interesting

**Phase 1 Focus: OrangeTheory Parser**

OrangeTheory classes are **composite workouts** — a single session contains treadmill, rowing, and strength training. This presents unique challenges:
- Emails don't explicitly state class type or duration
- Strength time isn't tracked (must be derived)
- Strava doesn't support composite activities
- Need granular component tracking for accurate analytics

This project demonstrates:
- Real-world data messiness and inference
- Idempotent ingestion with proper source/entity keys
- ELT pattern (store raw, normalize downstream)
- Type-safe schemas with database constraints
- Clean, testable, production-grade code

## Project Status

**Phase 1: OrangeTheory Parser ✅**
- [x] Email parser with HTML extraction
- [x] Rule-based workout classification
- [x] Strength time calculation (residual)
- [x] Distance standardization (meters)
- [x] PostgreSQL schema design
- [x] 100% test coverage

**Phase 2: Database Integration (In Progress)**
- [ ] PostgreSQL ingestion script
- [ ] Strava API integration
- [ ] Event-based email ingestion (Zapier)

**Phase 3: Multi-Source Expansion (Planned)**
- [ ] Strava activity ingestion (outdoor runs)
- [ ] Peloton workout parser
- [ ] Apple Health data import
- [ ] Unified workout view across sources

**Phase 4: Analytics & Insights (Planned)**
- [ ] Weekly volume rollups
- [ ] Training load calculations
- [ ] Rest day detection
- [ ] Training plan generation (v1)
- [ ] Google Calendar sync

## Quick Start

### Prerequisites
```bash
# Python 3.8+
python --version

# PostgreSQL
brew install postgresql  # macOS
brew services start postgresql
```

### Installation
```bash
# Clone repo
git clone https://github.com/yourusername/training-hub.git
cd training-hub

# Install dependencies
pip install -r requirements.txt

# Set up database
createdb training_hub
psql training_hub < schema.sql
```

### Run Tests
```bash
# Place sample OTF emails in data/sample_data/otf/
# (They're gitignored to protect personal info)

python tests/test_parser.py
```

## Example Usage

```python
from src.otf_parser import parse_otf_email

# Parse an OTF email
with open('otbeat_email.html', 'r') as f:
    html = f.read()

parsed = parse_otf_email(html, message_id='abc123')

# Output:
{
    'classification': {
        'class_type': 'ORANGE_90',
        'class_minutes': 90,
        'tread_seconds': 1436,
        'row_seconds': 1073,
        'strength_seconds': 2891  # Calculated residual
    },
    'tread': {
        'distance_meters': 5165,  # Converted from miles
        'total_time_minutes': 23.93
    },
    'row': {
        'distance_meters': 4189,
        'total_time_minutes': 17.88
    },
    'total_calories': 1090,
    'splat_points': 17
}
```

## Architecture Decisions

### 1. Rule-Based Classification
No ML black box. Deterministic rules based on cardio time:
```python
if tread_time >= 40 and no_row:
    → TREAD_50
elif tread_time + row_time >= 40:
    → ORANGE_90
else:
    → ORANGE_60
```

### 2. ELT Pattern (Not ETL)
```
Raw Email → otf_email_raw (immutable)
          ↓
        Parse & Normalize
          ↓
workout_session + workout_component (normalized)
          ↓
        Publish to Strava (output adapter)
```

**Why?** Re-parsing is trivial. Schema evolution is easy. Bugs don't destroy data.

### 3. Idempotency Keys
```python
# Source key (prevents duplicate ingestion)
source_key = f"otf_email:{message_id}:{workout_date}"

# Entity key (stable linkage across systems)
entity_key = f"workout:{date}:otf_{type}:{session_id}"
```

### 4. Single Component Table
One table for run/row/strength with CHECK constraints:
```sql
-- Run must have distance
CHECK (component_type != 'run' OR distance_meters IS NOT NULL)

-- Strength cannot have distance
CHECK (component_type != 'strength' OR distance_meters IS NULL)
```

**Why not separate tables?** Simpler queries, easier to add new types (bike, strider), still fully normalized (3NF).

### 5. Distance in Meters (Always)
Tread distance converted from miles → meters at parse time. Single unit throughout system prevents conversion bugs.

## Database Schema

Designed for multi-source ingestion with source-specific raw tables:

```sql
-- Source-specific raw storage (immutable)
otf_email_raw          -- OrangeTheory emails
strava_activity_raw    -- Strava API responses (future)
peloton_workout_raw    -- Peloton exports (future)

-- Normalized training data (source-agnostic)
workout_session        -- Unified sessions across all sources
  ├── source_type (otf/strava/peloton/apple_health)
  ├── entity_key (unique, stable)
  ├── class_type
  └── workout_date

workout_component      -- Granular components (run/row/bike/strength)
  ├── component_type
  ├── duration_seconds
  └── distance_meters

-- Output adapters (optional publishing)
strava_activity        -- Sync status for Strava publishing
```

## Test Results

```
✅ 90-min ORANGE class
   Tread: 23.93 min (5165m)
   Row: 17.88 min (4189m)
   Strength: 48.18 min (calculated)

✅ 60-min ORANGE class
   Tread: 25.88 min (5149m)
   Row: 3.85 min (932m)
   Strength: 30.27 min (calculated)

✅ TREAD_50
   Tread: 44.87 min (9253m)
   Strength: 0 min (no component created)

Coverage: 3/3 workout types (100%)
```

## Technology Stack

- **Language**: Python 3.8+
- **Parsing**: BeautifulSoup4
- **Database**: PostgreSQL
- **Event Ingestion**: Zapier → Webhook
- **Publishing**: Strava API
- **Deployment**: (TBD - AWS Lambda/ECS)

## Project Principles

**What this IS:**
- Multi-source training data hub
- Production-grade data engineering (ELT, idempotency, event-driven)
- Portfolio-worthy architecture
- Foundation for cross-platform training analytics

**What this is NOT:**
- A coaching app or UI-heavy product
- ML-driven decision making (deterministic rules only)
- Strava-first (database is source of truth)
- A consumer product (personal data engineering project)

## Contributing

This is a personal portfolio project, but feedback is welcome! Open an issue if you spot bugs or have suggestions.

## License

MIT License - see LICENSE file for details

## Contact

Andrew Dienstag - [LinkedIn](https://linkedin.com/in/yourprofile) | [Email](mailto:andrew.dienstag@gmail.com)

---

**Built with production-grade data engineering principles**  
*Idempotent pipelines • Type-safe schemas • Event-driven architecture*
