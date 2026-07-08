# OTF Training Data Spine

A production-grade data engineering pipeline for parsing OrangeTheory Fitness workout data, normalizing multi-modal training sessions, and publishing to Strava.

## Overview

OrangeTheory classes are **composite workouts** — a single session contains treadmill, rowing, and strength training. This presents a data engineering challenge: OTF emails don't explicitly state class type or duration, and Strava doesn't support composite activities well.

This project solves that by:
- **Parsing** OTF performance emails with rule-based classification
- **Normalizing** multi-modal sessions into granular components (run/row/strength)
- **Publishing** separate Strava activities per component
- **Storing** everything in a PostgreSQL database as the source of truth

## Why This is Interesting

- **Real-world messiness**: No explicit class type in emails, strength time must be derived
- **Idempotent ingestion**: Event-driven pipeline with proper source/entity keys
- **ELT pattern**: Raw emails stored first, normalized downstream
- **Type-safe schema**: Database constraints enforce component-specific rules
- **Portfolio-grade code**: Clean functions, 100% test coverage, professional architecture

## Project Status

**Phase 1 Complete ✅**
- [x] Email parser with HTML extraction
- [x] Rule-based workout classification (all 4 class types)
- [x] Strength time calculation (residual)
- [x] Distance standardization (meters)
- [x] PostgreSQL schema design
- [x] pytest suite with synthetic fixture emails (runs in any clone, no personal data)

**Phase 2 (In Progress)**
- [x] PostgreSQL ingestion script (idempotent, env-configured, verified end-to-end)
- [ ] Real email header parsing (Message-ID / Date / Subject — currently derived from filename)
- [ ] Strava API integration
- [ ] Event-based email ingestion (webhook + Zapier/n8n)

**Phase 3 (Planned)**
- [ ] Weekly insights rollup
- [ ] Training plan generation (v1)
- [ ] Google Calendar sync

## Quick Start

### Prerequisites
- Python 3.8+
- Docker (for PostgreSQL)

### Installation
```bash
# Clone repo
git clone https://github.com/adienstag91/training-hub.git
cd training-hub

# Install dependencies
make setup          # or: pip install -r requirements.txt

# Start PostgreSQL (schema applied automatically on first run; port 5434)
make db             # or: docker compose up -d
```

### Run Tests
```bash
make test           # or: python -m pytest tests/ -v
```
Tests run against synthetic fixture emails in `tests/fixtures/` — they mirror
the structure of real OTF emails but contain no personal data.

### Ingest Emails
```bash
# Ingest a single OTF email
python src/ingestion/ingest_otf_emails.py path/to/email.html 2026-07-01

# Or drop real emails in data/sample_data/otf/ (gitignored) and run
make ingest
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

```sql
otf_email_raw          -- Raw emails (never modified)
  ├── message_id (unique)
  └── raw_html

workout_session        -- Normalized sessions
  ├── entity_key (unique)
  ├── class_type
  └── class_minutes

workout_component      -- Granular components
  ├── entity_key (unique)
  ├── component_type (run/row/strength)
  ├── duration_seconds
  └── distance_meters

strava_activity        -- Output adapter
  ├── workout_component_id (FK)
  └── strava_activity_id
```

## Test Results

```
✅ ORANGE_90  — tread 23:45 (5165m) + row 17:30 (4189m) + strength 48:45 (residual)
✅ ORANGE_60  — tread 25:15 (5149m) + row 3:45 (932m) + strength 31:00 (residual)
✅ TREAD_50   — tread 44:30 (9253m), no strength component
✅ STRENGTH_50 — no cardio sections, full 50 min strength

Coverage: 4/4 workout types, plus time-parsing and classification
boundary tests (15 tests, all passing)
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
- Clean data engineering
- Production-grade patterns (ELT, idempotency, event-driven)
- Portfolio-worthy architecture
- Foundation for training plan generation

**What this is NOT:**
- A coaching app
- ML-driven decision making
- Strava-first (DB is source of truth)
- Heavy UI work

## Contributing

This is a personal portfolio project, but feedback is welcome! Open an issue if you spot bugs or have suggestions.

## License

MIT License - see LICENSE file for details

## Contact

Andrew Dienstag - [Email](mailto:andrew.dienstag@gmail.com)

---

**Built with production-grade data engineering principles**  
*Idempotent pipelines • Type-safe schemas • Event-driven architecture*
