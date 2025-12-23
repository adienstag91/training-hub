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
- [x] Rule-based workout classification
- [x] Strength time calculation (residual)
- [x] Distance standardization (meters)
- [x] PostgreSQL schema design
- [x] 100% test coverage

**Phase 2 (In Progress)**
- [ ] PostgreSQL ingestion script
- [ ] Strava API integration
- [ ] Event-based email ingestion (Zapier)

**Phase 3 (Planned)**
- [ ] Weekly insights rollup
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
git clone https://github.com/yourusername/otf-training-pipeline.git
cd otf-training-pipeline

# Install dependencies
pip install -r requirements.txt

# Set up database
createdb otf_training
psql otf_training < schema.sql
```

### Run Tests
```bash
# Place sample OTF emails in data/sample_emails/
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

Andrew Dienstag - [LinkedIn](https://linkedin.com/in/yourprofile) | [Email](mailto:andrew.dienstag@gmail.com)

---

**Built with production-grade data engineering principles**  
*Idempotent pipelines • Type-safe schemas • Event-driven architecture*
# training-hub
