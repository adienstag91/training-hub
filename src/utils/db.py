"""Shared PostgreSQL connection helper for all Training Hub modules."""

import os
from pathlib import Path

import psycopg2

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass  # dotenv is a convenience, not a requirement


def get_db_connection():
    """Create a PostgreSQL connection.

    A single DATABASE_URL wins if set (what managed hosts inject); otherwise
    the discrete POSTGRES_* vars are used, with defaults matching
    docker-compose.yml (localhost:5434 / training_hub).
    """
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return psycopg2.connect(database_url)

    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5434")),
        database=os.getenv("POSTGRES_DB", "training_hub"),
        user=os.getenv("POSTGRES_USER", "training_user"),
        password=os.getenv("POSTGRES_PASSWORD", "training_pass"),
    )
