"""
Ingest Single OTF Email
Quick utility for testing with one workout.
"""

import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Get project root (training-hub directory)
PROJECT_ROOT = Path(__file__).parent.parent.parent
ENV_PATH = PROJECT_ROOT / '.env'

# Load environment variables from project root
load_dotenv(ENV_PATH)

# Add parent directory to path
sys.path.insert(0, str(PROJECT_ROOT))
from src.ingestion.ingest_otf_emails import ingest_otf_email


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python ingest_single.py <filename>")
        print("Example: python ingest_single.py sample_60_min_0104.html")
        sys.exit(1)
    
    filename = sys.argv[1]
    filepath = PROJECT_ROOT / 'data' / 'sample_otf_emails' / filename
    
    if not filepath.exists():
        print(f"❌ File not found: {filepath}")
        sys.exit(1)
    
    print(f"\n📧 Ingesting single file: {filename}\n")
    
    result = ingest_otf_email(filepath)
    
    if result:
        print(f"\n✅ Success! Session ID: {result['session_id']}, Components: {result['component_count']}")
    else:
        print(f"\n❌ Failed to ingest")
