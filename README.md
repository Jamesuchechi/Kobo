# Kobo — A Royalty Reconciliation Agent Built on DataHub

> Working name. Rename freely (`Kobo` = Nigerian currency subunit — money that's easy to lose track of, which is the whole point).

**Built for:** [Build with DataHub: The Agent Hackathon](https://datahub.com) — Open/Wildcard track (with strong overlap into "Agents That Do Real Work")

**One-line pitch:** Kobo is an AI agent that walks DataHub's lineage graph from a music usage event back to its rights holders, computes what *should* have been paid, flags what doesn't match what *was* paid, and writes its findings back into DataHub so the next person (or agent) inherits the investigation instead of starting from zero.

---

## The problem

Music royalties break down at the metadata layer, not the payment layer. A stream happens. A payout eventually gets calculated. Somewhere between those two events, ownership splits are wrong, a rights holder was never linked, a territory rule was missed, or two catalogs both claim the same track. Nobody notices until an artist asks why their statement looks off — and by then, tracing it back requires a human to manually reconstruct a chain of custody that should have been queryable the whole time.

This is a lineage problem wearing a finance costume. DataHub already solves lineage for data pipelines — tables, columns, transformations, ownership, quality signals. Kobo applies that same graph to a different supply chain: **track → rights holder → split → usage event → payout**.

## What it does

1. **Models the royalty domain in DataHub.** Tracks, rights holders, ownership splits, usage events, and payouts are ingested as real DataHub entities with lineage edges between them, plus structured properties carrying split percentages, territories, and license terms.
2. **Traces and reconciles.** The Kobo agent queries DataHub (via the MCP server) to walk the lineage graph for a given usage event, reconstruct the expected payout from the ownership/split metadata it finds, and compare that against what was actually paid.
3. **Explains, not just flags.** When it finds a mismatch, an LLM generates a plain-English explanation of what's wrong and what to check next — not just "amounts don't match."
4. **Writes back to the graph.** This is the part most agent demos skip. Kobo doesn't just read DataHub and print a report — it calls DataHub's mutation tools to tag the affected entities (`reconciliation:mismatch`), attach structured properties (expected amount, actual amount, delta, severity), and save a full explanation as a Context Document on the entity. The next agent or analyst who looks at that track inherits the investigation.
5. **Surfaces it in a dashboard.** A lightweight queue view shows every flagged track/event, links into DataHub's own lineage graph for the "how did we get here" trace, and lets a human confirm or dismiss.

## Why this fits the brief

| Judging criterion | How Kobo addresses it |
|---|---|
| **Use of DataHub** | Uses lineage traversal (not just search), structured properties as a real domain model, and mutation tools to write findings back — the explicit bonus behavior the rubric calls out |
| **Technical execution** | End-to-end: mock data → DataHub ingestion → agent reasoning → write-back → dashboard, all runnable locally |
| **Originality** | DataHub has never been pointed at royalty/rights reconciliation — this is a genuinely new domain application, not a rebuild of an existing DataHub feature |
| **Real-world usefulness** | Royalty mismatches and unclaimed/misattributed rights are a well-documented, expensive problem across the music industry — this is a real workflow a rights/royalty ops team would want |
| **Submission quality** | Clear README, architecture doc, sample flagged findings in `examples/`, <3 min demo video |

## Tech stack

- **DataHub Core** (self-hosted, via docker-compose) — the metadata graph
- **`mcp-server-datahub`** (open source, self-hosted) — MCP access layer for the agent
- **Python / FastAPI** — the reconciliation agent service
- **[uv](https://docs.astral.sh/uv/)** — Python dependency management and script running (`pyproject.toml`-based, no pip/venv wrangling)
- **OpenRouter** (LLM reasoning layer) — generates the plain-English mismatch explanations
- **React + Vite** — the reconciliation queue dashboard
- **PostgreSQL** — backing store for mock rights/royalty data before ingestion into DataHub

## Repository structure

```
kobo/
├── README.md
├── DOCUMENTATION.md
├── TODO.md
├── LICENSE                    # Apache 2.0
├── docker-compose.yml         # spins up DataHub Core locally
├── data/
│   ├── generate_mock_data.py  # tracks, rights holders, splits, usage events, payouts
│   └── seed/                  # generated CSVs/JSON used for ingestion
├── ingestion/
│   └── emit_to_datahub.py     # pushes mock domain model into DataHub via DataHub SDK
├── agent/
│   ├── main.py                 # FastAPI service entrypoint
│   ├── mcp_client.py            # wraps calls to mcp-server-datahub
│   ├── reconcile.py             # lineage traversal + mismatch detection
│   ├── explain.py               # LLM explanation generation (OpenRouter)
│   └── writeback.py             # tags / structured properties / document write-back
├── dashboard/
│   └── (React + Vite app)
├── examples/
│   └── sample_findings/        # pre-generated reconciliation findings for judges to inspect without running the app
└── docs/
    └── architecture-diagram.png
```

## Quickstart

DataHub deprecated hand-written root `docker-compose.yml` files in favor of the `datahub` CLI's own managed quickstart — see `scripts/setup_datahub.sh` for why. Everything below is wrapped in a `Makefile` so it's still a short list of commands. Python dependencies are managed with [uv](https://docs.astral.sh/uv/) rather than pip/venv — `uv sync` and `uv run` handle environment creation automatically, no activation step needed.

```bash
# 0. Install uv, if you don't already have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# 1. Copy and fill in environment config
cp .env.example .env

# 2. Start DataHub Core locally (installs deps + the datahub CLI via uv)
make up
# ... open http://localhost:9002 (datahub / datahub), then:
make token          # instructions to generate a Personal Access Token
#    -> paste the token into .env as DATAHUB_GMS_TOKEN

# 3. Generate mock data, register structured properties, and ingest -- in order
make setup
# (equivalent to: make mock-data && make register-properties && make ingest)

# 4. Start the self-hosted DataHub MCP server, pointed at local DataHub
DATAHUB_GMS_URL=http://localhost:8080 \
DATAHUB_GMS_TOKEN=<your-local-token> \
uvx mcp-server-datahub@latest

# 5. Run the reconciliation agent
uv run uvicorn agent.main:app --reload

# 6. Run the dashboard
cd dashboard && npm install && npm run dev
```

After step 3, open the DataHub UI and search for the `kobo-royalty-domain` tag — you should see all five entity types (tracks, rights_holders, ownership_splits, usage_events, payouts) with lineage connecting them: `rights_holder → ownership_split → track → usage_event → payout`.

Note: the DataHub CLI currently warns it's only actively tested up to Python 3.11. It ran fine under 3.12 in our testing, but if you hit CLI-specific issues, run `uv python pin 3.11 && uv sync` to pin the project to a tested version.

Full environment variable reference, the entity/lineage model, and step-by-step rationale are in [`DOCUMENTATION.md`](./DOCUMENTATION.md).

## Demo flow (what the video shows)

1. Open the DataHub UI — show the ingested tracks, rights holders, and lineage graph already populated
2. Trigger the Kobo agent against a batch of usage events
3. Watch it flag a mismatch, then flip to DataHub and show the tag, structured property, and Context Document that just got written onto that entity — proving the write-back actually happened, not just a local log
4. Open the dashboard, show the reconciliation queue, click into the flagged item, read the LLM's explanation
5. Click through to DataHub's native lineage view from the dashboard to show the full trace

## License

Apache 2.0 — see [`LICENSE`](./LICENSE). Detectable in the repository's About section per hackathon submission requirements.

## Roadmap beyond the hackathon

See the "Post-hackathon" section of [`TODO.md`](./TODO.md) for where this could go if it becomes the standalone startup: multi-territory rights conflict resolution, real ingestion connectors (not mock data), a proposal-based (not auto-applying) mutation mode so rights teams review before findings are committed, and integration with real royalty statement formats (CWR, DDEX).