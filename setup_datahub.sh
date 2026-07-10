#!/usr/bin/env bash
#
# scripts/setup_datahub.sh
#
# Brings up a local DataHub Core instance for Kobo development/demo purposes.
#
# Why this script exists instead of a hand-written docker-compose.yml:
# DataHub's own docs explicitly note that the legacy root-level docker-compose*.yml
# files have been removed from the project. The maintained path is the `datahub`
# CLI's `docker quickstart` command, which downloads and manages a versioned,
# multi-service compose stack (GMS, MySQL, OpenSearch, Kafka, frontend) on our
# behalf. Hand-rolling that stack ourselves would mean re-solving a problem
# DataHub already solves, and re-breaking it every time they change a service
# version. This script just wraps their supported entrypoint with the specific
# flags Kobo needs (predictable ports, a pinned version, local secrets) so setup
# is still a single command.
#
# This project uses uv for Python dependency management. `uv sync` installs
# acryl-datahub (which provides the `datahub` CLI) into a project-local venv,
# and `uv run` executes commands inside it -- no global pip installs, no venv
# activation required.
#
# Note: the DataHub CLI's own version check currently warns it hasn't been
# actively tested past Python 3.11. It has run fine under 3.12 in testing here,
# but if you hit CLI-specific issues, pin the project to 3.11 with
# `uv python pin 3.11` and re-run `uv sync`.
#
# Usage:
#   ./scripts/setup_datahub.sh up        # start DataHub locally
#   ./scripts/setup_datahub.sh down      # stop DataHub, keep data
#   ./scripts/setup_datahub.sh nuke      # stop DataHub, wipe all data/volumes
#   ./scripts/setup_datahub.sh token     # print instructions to generate a PAT
#
set -euo pipefail

# Pin a specific DataHub CLI/image version rather than "latest" so the demo
# behaves identically for judges as it did when you recorded it.
DATAHUB_VERSION="${DATAHUB_VERSION:-v1.5.0}"
GMS_PORT="${DATAHUB_MAPPED_GMS_PORT:-8080}"
FRONTEND_PORT="${DATAHUB_MAPPED_FRONTEND_PORT:-9002}"

command_exists() { command -v "$1" >/dev/null 2>&1; }

ensure_uv() {
  if command_exists uv; then
    return
  fi
  echo "ERROR: uv is required and was not found on PATH." >&2
  echo "Install it with: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
  echo "(or see https://docs.astral.sh/uv/getting-started/installation/ for other platforms)" >&2
  exit 1
}

ensure_deps() {
  echo "Syncing Python dependencies via uv..."
  uv sync
}

ensure_docker() {
  if ! command_exists docker; then
    echo "ERROR: Docker is required and was not found on PATH. Install Docker Desktop first." >&2
    exit 1
  fi
  if ! docker info >/dev/null 2>&1; then
    echo "ERROR: Docker daemon does not appear to be running. Start Docker Desktop and re-run." >&2
    exit 1
  fi
}

cmd_up() {
  ensure_docker
  ensure_uv
  ensure_deps

  echo ""
  echo "Starting DataHub Core (version ${DATAHUB_VERSION})..."
  echo "GMS will be mapped to port ${GMS_PORT}, frontend to port ${FRONTEND_PORT}."
  echo ""

  DATAHUB_MAPPED_GMS_PORT="${GMS_PORT}" \
  DATAHUB_MAPPED_FRONTEND_PORT="${FRONTEND_PORT}" \
    uv run datahub docker quickstart --version "${DATAHUB_VERSION}"

  echo ""
  echo "DataHub should now be reachable at:"
  echo "  UI:  http://localhost:${FRONTEND_PORT}  (login: datahub / datahub)"
  echo "  GMS: http://localhost:${GMS_PORT}"
  echo ""
  echo "Next: run './scripts/setup_datahub.sh token' for how to generate a"
  echo "personal access token, then set DATAHUB_GMS_URL and DATAHUB_GMS_TOKEN"
  echo "in your .env file before running the ingestion script."
}

cmd_down() {
  ensure_uv
  echo "Stopping DataHub containers (data volumes are preserved)..."
  docker compose -p datahub stop
}

cmd_nuke() {
  ensure_uv
  echo "This will permanently delete all local DataHub data. Ctrl+C to cancel."
  sleep 3
  uv run datahub docker nuke
}

cmd_token() {
  cat <<'EOF'

To generate a Personal Access Token for use by the ingestion script and the
DataHub MCP server:

  1. Open http://localhost:9002 and log in (datahub / datahub)
  2. Go to Settings -> Access Tokens -> Generate New Token
  3. Copy the token and set it as DATAHUB_GMS_TOKEN in your .env file
     (see .env.example at the repo root)

Note: on first run, DataHub generates a random token-signing key and salt,
saved to ~/.datahub/quickstart/.local-secrets.env, and reuses them on
subsequent runs. If you ever run './scripts/setup_datahub.sh nuke' and start
fresh, previously issued tokens will stop working and need to be regenerated.

EOF
}

case "${1:-}" in
  up)    cmd_up ;;
  down)  cmd_down ;;
  nuke)  cmd_nuke ;;
  token) cmd_token ;;
  *)
    echo "Usage: $0 {up|down|nuke|token}"
    exit 1
    ;;
esac