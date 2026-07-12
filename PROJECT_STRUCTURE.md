# Training Hub - Project Structure

## Repository Layout

```
training-hub/
├── README.md                           # Main project documentation
├── PROJECT_STRUCTURE.md                # This file
├── .gitignore                          # Excludes personal data (real emails, tokens)
├── .env.example                        # DB connection template
├── requirements.txt                    # Python dependencies
├── schema.sql                          # PostgreSQL database schema
├── docker-compose.yml                  # Local Postgres (port 5434, auto-loads schema)
├── Makefile                            # setup / db / test / ingest shortcuts
│
├── src/                                # Source code
│   ├── __init__.py
│   ├── parsers/                        # Source-specific parsers
│   │   ├── __init__.py
│   │   ├── otf_parser.py              # v1 (legacy — superseded by v3)
│   │   ├── otf_parser_v3.py           # OTF parser: headers + body datetime
│   │   ├── apple_health_parser.py     # Health Auto Export JSON
│   │   └── peloton_parser.py          # Peloton workouts.csv export
│   ├── ingestion/                      # Database insertion (all idempotent)
│   │   ├── ingest_otf_emails.py       # OTF email → Postgres
│   │   ├── ingest_apple_health.py     # Apple Health JSON → Postgres (CLI + webhook)
│   │   └── ingest_peloton_csv.py      # Peloton CSV → Postgres
│   ├── strava/                         # Strava output adapter
│   │   ├── strava_auth.py             # One-time OAuth flow
│   │   └── publish_to_strava.py       # Per-component publishing + token refresh
│   ├── webhook/                        # Event-driven ingestion
│   │   └── webhook_server.py          # Flask: /ingest (OTF), /ingest/apple
│   └── utils/
│       ├── db.py                      # Shared DB connection (DATABASE_URL / POSTGRES_*)
│       └── clean_db.py                # Wipe tables for testing
│
├── tests/                              # Test suite (pytest)
│   ├── __init__.py
│   ├── conftest.py                    # Puts the project root on the import path
│   ├── fixtures/                       # Synthetic fixtures (safe to commit)
│   │   ├── fixture_orange_90.html
│   │   ├── fixture_orange_60.html
│   │   ├── fixture_tread_50.html
│   │   ├── fixture_strength_50.html
│   │   ├── fixture_apple_health.json
│   │   └── fixture_peloton.csv
│   ├── test_parser.py                 # OTF parser v3 + classification tests
│   ├── test_apple_health_parser.py    # Apple Health parser tests
│   └── test_peloton_parser.py         # Peloton CSV parser tests
│
├── migrations/                         # Incremental schema changes for existing DBs
│   └── 001_apple_health_and_component_types.sql
│
└── data/                               # Local data (gitignored)
    └── sample_data/
        └── otf/                        # Real OTF emails go here (never committed)
```

## Current Phase

**Done:** OTF parser v3 (real Message-ID + workout datetime from the email),
classification (all 4 class types), schema v2 (component detail tables,
multi-source), idempotent ingestion, Strava OAuth + publishing, Flask webhook
for Zapier/n8n, Apple Health parsing, pytest suite with synthetic fixtures,
dockerized local DB.

**Next:**
- Deploy the webhook server (currently local + ngrok)
- Re-verify the parser against current OTF email format
- Additional source parsers (Strava-native, Peloton)

## Multi-Source Vision

Each source gets:
1. **Parser** (`src/parsers/<source>_parser.py`)
2. **Raw table** (`<source>_raw` in schema)
3. **Ingestion script** (`src/ingestion/ingest_<source>.py`)
4. **Tests** (`tests/test_<source>_parser.py`)

All sources normalize to:
- `workout_session` (unified)
- `workout_component` (granular)

This enables cross-platform analytics without source lock-in.
