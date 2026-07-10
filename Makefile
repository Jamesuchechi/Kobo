# Kobo — convenience commands
#
# These wrap scripts/setup_datahub.sh and the Python scripts so the
# quickstart in the README stays a short list of commands.

.PHONY: sync up down nuke token mock-data register-properties ingest setup smoke-test help

help:
	@echo "make sync                 # install/sync Python deps via uv"
	@echo "make up                   # start local DataHub Core"
	@echo "make down                 # stop DataHub (keep data)"
	@echo "make nuke                 # stop DataHub and wipe all data"
	@echo "make token                # instructions to generate a DataHub access token"
	@echo "make smoke-test           # confirm DataHub GMS is reachable and MCP server is available"
	@echo "make mock-data            # generate mock rights/royalty dataset"
	@echo "make register-properties  # register Kobo's structured property definitions"
	@echo "make ingest               # push mock data into DataHub (run register-properties first)"
	@echo "make setup                # mock-data + register-properties + ingest, in order"

sync:
	uv sync

up:
	./scripts/setup_datahub.sh up

down:
	./scripts/setup_datahub.sh down

nuke:
	./scripts/setup_datahub.sh nuke

token:
	./scripts/setup_datahub.sh token

smoke-test: sync
	uv run python scripts/smoke_test_mcp.py

mock-data: sync
	uv run python3 data/generate_mock_data.py

register-properties: sync
	uv run datahub properties upsert -f ingestion/structured_properties.yaml

ingest: sync
	uv run python3 ingestion/emit_to_datahub.py

setup: mock-data register-properties ingest

