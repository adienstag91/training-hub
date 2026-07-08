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
│   │   └── otf_parser.py              # OrangeTheory email parser
│   └── ingestion/                      # Database insertion
│       └── ingest_otf_emails.py       # Idempotent OTF email → Postgres
│
├── tests/                              # Test suite (pytest)
│   ├── __init__.py
│   ├── conftest.py                    # Puts src/ on the import path
│   ├── fixtures/                       # Synthetic OTF emails (safe to commit)
│   │   ├── fixture_orange_90.html
│   │   ├── fixture_orange_60.html
│   │   ├── fixture_tread_50.html
│   │   └── fixture_strength_50.html
│   └── test_parser.py                 # Parser + classification tests
│
└── data/                               # Local data (gitignored)
    └── sample_data/
        └── otf/                        # Real OTF emails go here (never committed)
```

## Current Phase

**Done:** OTF parser, classification (all 4 class types), pytest suite with
synthetic fixtures, idempotent Postgres ingestion, dockerized local DB.

**Next:**
- Real email header parsing (Message-ID / Date / Subject)
- Strava publishing (`src/publishing/`)
- Event-driven email ingestion (webhook + Zapier/n8n)
- Additional source parsers (Strava, Peloton)

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
