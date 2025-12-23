# Git Repository Setup Instructions

## Quick Setup (5 minutes)

```bash
# 1. Navigate to your project directory
cd /Users/andrewdienstag

# 2. Create new directory with proper name
mkdir training-hub
cd training-hub

# 3. Create proper folder structure
mkdir -p src/parsers tests data/sample_data/otf

# Move downloaded files to proper locations
# (Assuming files are in ~/Downloads or ~/otf)
mv ~/otf/otf_parser.py src/parsers/
mv ~/otf/test_parser.py tests/
mv ~/otf/schema.sql .
mv ~/Downloads/README_GITHUB.md README.md
mv ~/Downloads/.gitignore .
mv ~/Downloads/requirements.txt .

# Create __init__.py files for Python packages
touch src/__init__.py
touch src/parsers/__init__.py
touch tests/__init__.py

# 4. Move your sample emails (they'll be gitignored)
mv ~/otf/emails/*.html data/sample_data/otf/

# 5. Initialize git repository
git init
git branch -M main

# 6. Make initial commit
git add .
git commit -m "Initial commit: OrangeTheory parser for Training Hub

Phase 1 Complete:
- Parse OTF emails (tread/row/strength metrics)
- Classify workout types (ORANGE_60/90, TREAD_50, STRENGTH_50)
- Calculate strength time as residual
- Standardize all distances to meters
- 100% test coverage on 3 sample emails
- PostgreSQL schema with idempotency keys
- ELT pattern with raw email storage

Technical highlights:
- Function-based architecture (no classes)
- Type-safe CHECK constraints in schema
- Idempotent ingestion with source + entity keys
- Multi-source ready (OTF is first of many sources)
"

# 7. Create GitHub repo and push
# Option A: Using GitHub CLI
gh repo create training-hub --public --source=. --push --description "Multi-source training data pipeline with normalized workout storage and cross-platform analytics"

# Option B: Manual
# - Go to github.com/new
# - Create repo named "training-hub"
# - Then run:
git remote add origin https://github.com/YOUR_USERNAME/training-hub.git
git push -u origin main
```

## Verify Setup

```bash
# Run tests to confirm everything works
cd /Users/andrewdienstag/training-hub
python tests/test_parser.py

# Expected output: "🎉 All tests passed!"
```

## Update Test Script Imports

## Update Test Script Imports

After moving files, update `tests/test_parser.py` import:

```python
# Add this at the top of the file:
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.parsers.otf_parser import parse_otf_email
```

And update email paths:

```python
# In main() function, change:
emails_dir = os.path.join(script_dir, 'emails')

# To:
emails_dir = os.path.join(os.path.dirname(script_dir), 'data', 'sample_data', 'otf')
```

## Next Steps After Push

1. Add GitHub repo description: "Multi-source training data pipeline with normalized workout storage"
2. Add topics: `data-engineering`, `python`, `postgres`, `fitness-analytics`, `etl-pipeline`
3. Consider adding a LICENSE file (MIT recommended)
4. Update README with your actual GitHub username and LinkedIn

## Commit Message Convention Going Forward

Use conventional commits:
- `feat: add PostgreSQL ingestion script`
- `fix: handle edge case in TREAD_50 classification`
- `refactor: extract component insertion to helper function`
- `docs: add architecture diagram`
- `test: add validation for STRENGTH_50 class`
