# Kobo — Technical Documentation

This document covers the data model, architecture, MCP tool usage, and configuration in enough depth for a judge (or future contributor) to understand exactly how the system works and why each piece exists.

---

## 1. Problem framing, restated precisely

Given:
- A **usage event** (a stream, a play, a sync placement) tied to a track
- A set of **rights holders** with **ownership splits** on that track (percentages, territories, license terms)
- A **payout record** that was actually issued for that usage event

Kobo answers: *does the payout match what the ownership graph says it should be, and if not, why?*

This is deliberately framed as a **lineage + reconciliation** problem rather than a pure data-quality problem, because the interesting failure modes are relational: a track with two conflicting ownership claims, a rights holder who was never linked at all, a split that sums to 94% instead of 100%, a territory-specific license that doesn't cover where the play happened.

---

## 2. Data model

All entities are modeled as DataHub Datasets (the most general entity type DataHub ships with), connected via lineage edges, and enriched with **structured properties** — DataHub's typed metadata field mechanism — rather than shoving everything into free-text descriptions.

### 2.1 Entities

| Entity | DataHub representation | Key structured properties |
|---|---|---|
| `track` | Dataset | `isrc`, `title`, `primary_artist`, `total_split_pct` (should sum to 100) |
| `rights_holder` | Dataset (+ DataHub native Ownership) | `holder_type` (writer/publisher/label/performer), `payee_id` |
| `ownership_split` | Dataset, lineage edge between `track` and `rights_holder` | `split_pct`, `territory`, `right_type` (mechanical/performance/sync), `license_start`, `license_end` |
| `usage_event` | Dataset | `event_type` (stream/play/sync), `territory`, `platform`, `timestamp`, `unit_count` |
| `payout` | Dataset, lineage edge from `usage_event` | `amount_paid`, `payee_id`, `currency`, `statement_period` |

### 2.2 Lineage graph

```
track ──(ownership_split, N edges)──> rights_holder
  │
  └──(generates)──> usage_event ──(settled_by)──> payout
```

Kobo's core traversal, for any `usage_event`:
1. Follow the edge back to its `track`
2. Follow all `ownership_split` edges out of that `track` to enumerate rights holders, their percentages, territories, and right types
3. Filter splits to those valid for the event's territory and right type
4. Compute expected payout: `event_value × split_pct` per rights holder
5. Follow the edge forward from `usage_event` to its `payout` record(s)
6. Compare expected vs. actual per rights holder

### 2.3 Why structured properties instead of custom entity types

DataHub Core supports custom entity types, but that requires modifying and redeploying the metadata model (PDL schemas), which is out of scope for a 4-week build. Structured properties are a first-class, no-redeploy mechanism for typed metadata on standard entities, and the MCP server's `add_structured_properties` / `remove_structured_properties` tools operate on them directly — so this choice is also what keeps the whole ingestion and write-back pipeline usable purely through the MCP tool surface.

---

## 3. Architecture

```
┌─────────────────┐      ┌──────────────────┐      ┌────────────────────┐
│ Mock data        │─────▶│  DataHub Core     │◀────▶│ mcp-server-datahub │
│ generator        │      │  (docker-compose) │      │ (self-hosted)      │
└─────────────────┘      └──────────────────┘      └─────────┬──────────┘
                                                                │ MCP tool calls
                                                                ▼
                                                     ┌────────────────────┐
                                                     │  Kobo Agent         │
                                                     │  (FastAPI)          │
                                                     │  - reconcile.py     │
                                                     │  - explain.py (LLM) │
                                                     │  - writeback.py     │
                                                     └─────────┬──────────┘
                                                                │ REST
                                                                ▼
                                                     ┌────────────────────┐
                                                     │  Dashboard          │
                                                     │  (React + Vite)     │
                                                     └────────────────────┘
```

### 3.1 Ingestion (`ingestion/emit_to_datahub.py`)

Uses the DataHub Python SDK to emit metadata change proposals (MCPs — unrelated to Model Context Protocol, just an unfortunate acronym collision that's worth calling out in the demo video so judges aren't confused) for each entity and lineage edge generated by `data/generate_mock_data.py`. This runs once at setup and is idempotent — safe to re-run.

### 3.2 Agent (`agent/`)

- **`mcp_client.py`** — thin wrapper around the running `mcp-server-datahub` instance. All read operations (search, lineage traversal, structured property lookups) and all write operations (tags, structured properties, documents) go through this one client so there's a single place that knows how to talk to DataHub.
- **`reconcile.py`** — implements the traversal and comparison logic described in §2.2. Produces a `Finding` object: `{ usage_event_urn, track_urn, expected: {...}, actual: {...}, delta, severity, reasons: [...] }`.
- **`explain.py`** — takes a `Finding` and calls an LLM (via OpenRouter) to turn the structured mismatch into a short, specific, human-readable explanation and a suggested next action (e.g. "check whether Rights Holder X's territory license was renewed for DE/AT/CH").
- **`writeback.py`** — for each `Finding` above a configurable severity threshold:
  - `add_tags(entity=track_urn, tags=["reconciliation:mismatch"])`
  - `add_structured_properties(entity=usage_event_urn, properties={expected_amount, actual_amount, delta, severity})`
  - `save_document(parent=track_urn, title=..., body=<LLM explanation>)`

  Note: DataHub's MCP server also exposes a **proposal-based mutation path** (`propose_lifecycle_stage`, `accept_or_reject_proposals`) for governed workflows where changes need human sign-off before committing. Kobo's default mode writes tags/properties/documents directly since it's read-only-adjacent (annotation, not deletion or financial action), but the architecture supports switching `writeback.py` to submit proposals instead — see `WRITEBACK_MODE` in configuration below. This is worth highlighting in the demo as the honest answer to "would you really let an agent auto-write findings in production?"

### 3.3 Dashboard (`dashboard/`)

Reads flagged findings back out of DataHub (via the same MCP client, or directly via DataHub's GraphQL API) and renders:
- A queue of flagged tracks/events, sorted by severity and delta
- Detail view per finding: expected vs. actual breakdown, the LLM explanation, and a deep link into DataHub's native lineage graph view for that entity
- A confirm/dismiss action that updates the tag (`reconciliation:confirmed` / `reconciliation:dismissed`) — this is itself another write-back, closing the loop that a human made a decision, which the next reconciliation run can read

---

## 4. MCP tools used

| Tool | Used for | Read/Write |
|---|---|---|
| `search` | Finding usage events / tracks to reconcile in a batch | Read |
| lineage traversal tools | Walking `usage_event → track → rights_holder` and `usage_event → payout` | Read |
| structured property lookup | Reading split %, territory, right type off `ownership_split` edges | Read |
| `add_tags` / `remove_tags` | Flagging/unflagging entities as mismatched | Write (mutation) |
| `add_structured_properties` | Attaching expected/actual/delta/severity to the usage event | Write (mutation) |
| `save_document` | Attaching the LLM-generated explanation as a Context Document | Write (document) |
| `propose_lifecycle_stage` / `accept_or_reject_proposals` | Optional governed write-back mode (see §3.2) | Write (proposal) |

---

## 5. Configuration

| Variable | Used by | Description |
|---|---|---|
| `DATAHUB_GMS_URL` | `mcp-server-datahub`, ingestion script | URL of local DataHub GMS, e.g. `http://localhost:8080` |
| `DATAHUB_GMS_TOKEN` | `mcp-server-datahub`, ingestion script | Personal access token generated from the local DataHub UI |
| `OPENROUTER_API_KEY` | `agent/explain.py` | LLM access for explanation generation |
| `MISMATCH_SEVERITY_THRESHOLD` | `agent/writeback.py` | Minimum delta (as % or absolute currency) before a finding is written back |
| `WRITEBACK_MODE` | `agent/writeback.py` | `direct` (default) or `proposal` — see §3.2 |
| `MOCK_DATA_SEED` | `data/generate_mock_data.py` | Seed for reproducible mock data generation |

---

## 6. Mock data generation strategy

Real royalty statement data (CWR/DDEX formats, actual DSP reporting) is not publicly available in a form usable for a hackathon demo, so `data/generate_mock_data.py` generates a small but structurally realistic dataset:
- ~50–100 tracks with realistic ISRC-style identifiers
- Rights holders with plausible splits (some intentionally summing to less than 100% to create real gaps)
- A handful of deliberately seeded mismatch scenarios: a missing rights holder link, an expired territory license still being paid against, a split that doesn't sum to 100%, and a duplicate/conflicting ownership claim on one track
- Usage events across multiple territories and platforms
- Payout records, most correct, several intentionally wrong to match the seeded scenarios above

This is deliberately not random-noise data — every mismatch the agent finds in the demo is a real, explainable scenario a rights/royalty team would actually encounter, which makes for a much stronger demo video than a pile of random numbers.

---

## 7. Known limitations (stated honestly for judges)

- Mock data only — no real DSP/PRO ingestion connector in this build (see roadmap in README)
- Structured properties are a reasonable stand-in for a purpose-built rights entity model, but a production version would likely push a custom entity type upstream to DataHub rather than overloading Dataset
- Direct write-back mode is fine for a hackathon demo; a real deployment would default to the proposal-based governed mode