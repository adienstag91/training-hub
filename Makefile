.PHONY: setup db db-down db-reset db-psql test ingest webhook strava-auth publish

# Install Python dependencies
setup:
	pip install -r requirements.txt

# Start Postgres (applies schema.sql on first run)
db:
	docker compose up -d
	@echo "Postgres running on localhost:5434 (db=training_hub)"

# Stop Postgres (data persists)
db-down:
	docker compose stop

# Destroy and recreate the database (deletes all data)
db-reset:
	docker compose down -v
	docker compose up -d

# Open a psql shell
db-psql:
	docker compose exec postgres psql -U training_user -d training_hub

# Run the test suite
test:
	python -m pytest tests/ -v

# Ingest OTF emails from data/sample_data/otf/
ingest:
	python src/ingestion/ingest_otf_emails.py

# Run the Zapier/n8n webhook server (port 5000; expose with ngrok)
webhook:
	python src/webhook/webhook_server.py

# One-time Strava OAuth flow (saves tokens to .env)
strava-auth:
	python src/strava/strava_auth.py

# Publish all unpublished components to Strava
publish:
	python src/strava/publish_to_strava.py
