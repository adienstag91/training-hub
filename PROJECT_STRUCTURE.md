# Training Hub - Final Project Structure

## Repository Layout

```
training-hub/
├── README.md                           # Main project documentation
├── .gitignore                          # Excludes personal data
├── requirements.txt                    # Python dependencies
├── schema.sql                          # PostgreSQL database schema
│
├── src/                                # Source code
│   ├── __init__.py
│   ├── parsers/                        # Source-specific parsers
│   │   ├── __init__.py
│   │   ├── otf_parser.py              # OrangeTheory email parser
│   │   ├── strava_parser.py           # (future) Strava API
│   │   └── peloton_parser.py          # (future) Peloton exports
│   ├── ingestion/                      # (future) Database insertion
│   │   └── __init__.py
│   └── publishing/                     # (future) Strava sync
│       └── __init__.py
│
├── tests/                              # Test suite
│   ├── __init__.py
│   └── test_parser.py                 # OTF parser tests
│
└── data/                               # Local data (gitignored)
    └── sample_data/
        ├── otf/                        # OTF email samples
        │   ├── sample_90_min.html
        │   ├── sample_60_min.html
        │   └── sample_tread50.html
        ├── strava/                     # (future)
        ├── peloton/                    # (future)
        └── apple_health/               # (future)
```

## Database Name

```sql
-- Database name updated to match project
createdb training_hub  
```

## Current Phase: OTF Parser Complete

**Implemented:**
- `src/parsers/otf_parser.py` - Full parser with classification
- `tests/test_parser.py` - 100% test coverage
- `schema.sql` - Multi-source ready schema
- Sample emails in `data/sample_data/otf/`

**Next Phase:**
- `src/ingestion/otf_ingestion.py` - Insert parsed data to DB
- Strava API integration
- Additional source parsers

## Multi-Source Vision

Each source gets:
1. **Parser** (`src/parsers/<source>_parser.py`)
2. **Raw table** (`<source>_raw` in schema)
3. **Ingestion script** (`src/ingestion/<source>_ingestion.py`)
4. **Tests** (`tests/test_<source>_parser.py`)

All sources normalize to:
- `workout_session` (unified)
- `workout_component` (granular)

This enables cross-platform analytics without source lock-in.
