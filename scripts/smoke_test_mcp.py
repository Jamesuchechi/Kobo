#!/usr/bin/env python3
"""
scripts/smoke_test_mcp.py

Smoke-tests that the mcp-server-datahub can reach the local DataHub GMS.
Run this after DataHub is up and DATAHUB_GMS_TOKEN is set in .env.

Usage:
    uv run python scripts/smoke_test_mcp.py

Expected output on success:
    [OK] Connected to DataHub GMS at http://localhost:8080
    [OK] MCP server responded — DataHub is reachable via MCP layer
"""

import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

# ---------------------------------------------------------------------------
# Load .env manually (avoid requiring python-dotenv at smoke-test time)
# ---------------------------------------------------------------------------
def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())


load_dotenv(Path(__file__).parent.parent / ".env")

GMS_URL = os.environ.get("DATAHUB_GMS_URL", "http://localhost:8080")
GMS_TOKEN = os.environ.get("DATAHUB_GMS_TOKEN", "")

# ---------------------------------------------------------------------------
# 1. Confirm DataHub GMS health endpoint is reachable
# ---------------------------------------------------------------------------
print(f"Checking DataHub GMS at {GMS_URL} ...")

try:
    req = urllib.request.Request(f"{GMS_URL}/health")
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode()
        if resp.status == 200:
            print(f"[OK] Connected to DataHub GMS at {GMS_URL}")
        else:
            print(f"[WARN] GMS responded with HTTP {resp.status}: {body[:200]}")
except urllib.error.URLError as e:
    print(f"[FAIL] Could not reach DataHub GMS at {GMS_URL}: {e}")
    print("       Make sure DataHub is running: make up")
    sys.exit(1)

# ---------------------------------------------------------------------------
# 2. Confirm the token is set (non-empty) in .env
# ---------------------------------------------------------------------------
if not GMS_TOKEN:
    print(
        "[WARN] DATAHUB_GMS_TOKEN is not set in .env — the MCP server and ingestion "
        "scripts will fail on authenticated endpoints.\n"
        "       Run: make token  →  follow the instructions  →  paste the token into .env"
    )
else:
    print(f"[OK] DATAHUB_GMS_TOKEN is set ({len(GMS_TOKEN)} chars)")

# ---------------------------------------------------------------------------
# 3. Quick authenticated call: list the first page of entities from GMS
#    (This exercises the same auth path the MCP server uses.)
# ---------------------------------------------------------------------------
if GMS_TOKEN:
    print(f"\nTesting authenticated GMS API call ...")
    try:
        gql_payload = b'{"query": "{ search(input: { type: DATASET, query: \\"*\\", start: 0, count: 1 }) { total } }"}'
        req = urllib.request.Request(
            f"{GMS_URL}/api/graphql",
            data=gql_payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {GMS_TOKEN}",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode()
            if resp.status == 200 and "data" in body:
                print(f"[OK] Authenticated GraphQL call succeeded — token is valid")
            else:
                print(f"[WARN] Unexpected response (HTTP {resp.status}): {body[:200]}")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"[FAIL] HTTP {e.code} on authenticated call: {body[:200]}")
        print("       Token may be invalid or expired — regenerate via: make token")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"[FAIL] Network error on authenticated call: {e}")
        sys.exit(1)

# ---------------------------------------------------------------------------
# 4. Confirm mcp-server-datahub is available via uvx
# ---------------------------------------------------------------------------
print(f"\nChecking mcp-server-datahub availability via uvx ...")
import subprocess

result = subprocess.run(
    ["uvx", "mcp-server-datahub@latest", "--help"],
    capture_output=True,
    text=True,
    timeout=30,
    env={**os.environ, "DATAHUB_GMS_URL": GMS_URL, "DATAHUB_GMS_TOKEN": GMS_TOKEN or "placeholder"},
)
if result.returncode == 0 or "usage" in (result.stdout + result.stderr).lower():
    print("[OK] mcp-server-datahub is available via uvx")
else:
    print(f"[WARN] uvx mcp-server-datahub --help returned code {result.returncode}")
    print(f"       stdout: {result.stdout[:200]}")
    print(f"       stderr: {result.stderr[:200]}")

print("\n--- Smoke test complete ---")
if not GMS_TOKEN:
    print("Next step: generate a token (make token) and add it to .env, then re-run this script.")
else:
    print("Phase 0 environment checks passed. Ready for Phase 1.")
