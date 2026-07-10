# Kobo — Build Plan

Target: submit before **Aug 10, 2026 @ 10:00pm GMT+1**. Working backward, treat Aug 3 as the real internal deadline so the last week is buffer for the demo video and README polish, not core feature work.

Each phase has a completion check at the end — don't move to the next phase until it passes. Phases are sequential but 6 and 7 can overlap if time is tight.

---

## Phase 0 — Environment & Repo Setup
- [ ] Create public GitHub repo, add Apache 2.0 `LICENSE` file at root (must be detectable in the About section per submission rules — verify it shows up before moving on)
- [ ] Scaffold repo structure as laid out in `README.md`
- [ ] Set up local DataHub Core via `docker-compose` (use DataHub's official quickstart compose file as a base)
- [ ] Confirm DataHub UI is reachable locally, generate a personal access token
- [ ] Install and smoke-test `mcp-server-datahub` locally (`uvx mcp-server-datahub@latest`) pointed at the local instance — confirm it connects with `DATAHUB_GMS_URL` / `DATAHUB_GMS_TOKEN`
- [ ] Confirm the MCP server is reachable from a basic Python script or from Claude Desktop/Claude Code as a sanity check

**Done when:** you can run `docker compose up`, open the DataHub UI, and have a working local MCP server talking to it.

---

## Phase 1 — Domain Model & Mock Data
- [ ] Define the entity schema exactly as in `DOCUMENTATION.md` §2 (track, rights_holder, ownership_split, usage_event, payout)
- [ ] Write `data/generate_mock_data.py`:
  - [ ] 50–100 tracks with ISRC-style IDs
  - [ ] Rights holders + splits, including intentionally broken cases (splits summing to <100%, missing links)
  - [ ] Seed at least 4 distinct, deliberate mismatch scenarios (see `DOCUMENTATION.md` §6) — write these down explicitly so you know exactly what the demo should surface later
  - [ ] Usage events across ≥3 territories and ≥2 platforms
  - [ ] Payout records, mostly correct, a few intentionally wrong to match seeded scenarios
- [ ] Output mock data to `data/seed/` as CSV or JSON

**Done when:** you have a data generation script that's re-runnable and produces the same seeded scenarios every time (fixed seed).

---

## Phase 2 — Ingestion into DataHub
- [ ] Write `ingestion/emit_to_datahub.py` using the DataHub Python SDK
- [ ] Emit each entity type as a Dataset with correct structured properties
- [ ] Emit lineage edges: `track → rights_holder` (via ownership_split), `usage_event → payout`
- [ ] Verify in the DataHub UI: browse to a track, confirm you can see its lineage graph and structured properties rendering correctly
- [ ] Make the script idempotent — re-running it shouldn't duplicate entities

**Done when:** every entity from Phase 1's mock data is visible and correctly linked in the DataHub UI, lineage graph included.

---

## Phase 3 — Agent: Read Path (Reconciliation Logic)
- [ ] Write `agent/mcp_client.py` — wrapper for all MCP tool calls used by the agent
- [ ] Write `agent/reconcile.py`:
  - [ ] Given a `usage_event` URN, traverse to its `track`
  - [ ] Enumerate ownership splits for that track, filtered by territory/right type
  - [ ] Compute expected payout per rights holder
  - [ ] Traverse forward to the actual `payout` record(s)
  - [ ] Compare expected vs. actual, produce a `Finding` object with severity and reasons
- [ ] Run against all 4+ seeded mismatch scenarios from Phase 1 — confirm every one is correctly detected
- [ ] Confirm it does NOT flag the correctly-paid usage events (false positive check)

**Done when:** running `reconcile.py` against the full mock dataset produces exactly the seeded mismatches, nothing more, nothing less.

---

## Phase 4 — Agent: Explanation Layer
- [ ] Write `agent/explain.py` — takes a `Finding`, calls OpenRouter, returns a short plain-English explanation + suggested next action
- [ ] Prompt-engineer this so explanations are specific (reference actual territory/split numbers) rather than generic ("there's a mismatch")
- [ ] Spot check explanations against all seeded scenarios — do they actually make sense to someone who didn't write the code?

**Done when:** every seeded mismatch produces a distinct, correct, specific explanation.

---

## Phase 5 — Agent: Write-Back
- [ ] Write `agent/writeback.py`:
  - [ ] `add_tags` for flagged tracks/events
  - [ ] `add_structured_properties` for expected/actual/delta/severity
  - [ ] `save_document` with the LLM explanation attached to the track
- [ ] Verify all three write-back types actually appear in the DataHub UI after running the agent (this is the single most important thing to get right for judging — it must be visibly true in the DataHub UI, not just logged in your terminal)
- [ ] (Stretch, time-permitting) Implement the alternate `WRITEBACK_MODE=proposal` path using `propose_lifecycle_stage` / `accept_or_reject_proposals`, and mention the tradeoff in the demo

**Done when:** after running the agent, you can open DataHub's UI, navigate to a flagged track with zero prior context, and see the tag, the structured properties, and the full explanation document — no other tool needed.

---

## Phase 6 — FastAPI Service
- [ ] Wrap `reconcile.py` + `explain.py` + `writeback.py` into a FastAPI service (`agent/main.py`)
- [ ] Endpoint: trigger a reconciliation run (batch, over all usage events or a filtered subset)
- [ ] Endpoint: fetch current findings (for the dashboard)
- [ ] Endpoint: confirm/dismiss a finding (writes back a status tag)
- [ ] Basic error handling — MCP calls failing shouldn't crash the whole batch run

**Done when:** you can trigger a full reconciliation run via a single API call and get findings back.

---

## Phase 7 — Dashboard
- [ ] Scaffold React + Vite app
- [ ] Queue view: list of findings sorted by severity/delta
- [ ] Detail view: expected vs. actual breakdown, LLM explanation, link out to DataHub's native lineage graph for that entity
- [ ] Confirm/dismiss action wired to the FastAPI endpoint
- [ ] Apply your usual design sensibility here — this is a real interface, not a bare table, and it's the first thing judges will actually look at

**Done when:** a judge could open the dashboard cold and understand what's flagged and why within 10 seconds.

---

## Phase 8 — Examples & Sample Outputs
- [ ] Populate `examples/sample_findings/` with the output of a full reconciliation run — raw JSON findings plus the LLM explanations, so a judge can evaluate quality without running anything
- [ ] Double check these examples match the 4+ seeded scenarios and read well on their own

**Done when:** someone could judge the quality of your agent's output from this folder alone, with the repo closed.

---

## Phase 9 — Documentation Pass
- [ ] Finalize `README.md` — confirm setup instructions work on a clean machine/VM, not just your own
- [ ] Finalize `DOCUMENTATION.md` — confirm it matches what you actually built (update anything that drifted during implementation)
- [ ] Confirm `LICENSE` is Apache 2.0 and visible in GitHub's About section
- [ ] Write the submission text description (features, functionality, technologies, data used) — can draw directly from README

**Done when:** a stranger could clone the repo and get it running using only the README.

---

## Phase 10 — Demo Video
- [ ] Script the <3 minute walkthrough (see "Demo flow" in README for the beat structure)
- [ ] Record: mock data + DataHub UI showing ingested lineage → trigger agent → show write-back live in DataHub UI → dashboard walkthrough → click into native lineage graph
- [ ] Upload to YouTube or Vimeo, set to public
- [ ] Watch it back once as if you're a judge who's never heard of this project — cut anything that doesn't land in the first 20 seconds

**Done when:** video is public, under 3 minutes, and clearly shows the project functioning end-to-end.

---

## Phase 11 — Submission
- [ ] Project URL (live demo or repo w/ setup instructions)
- [ ] Public repo URL, Apache 2.0 license confirmed visible
- [ ] Text description
- [ ] Demo video link
- [ ] Sample outputs folder linked/mentioned
- [ ] Opt in to the Most Valuable Feedback Survey Prize if you're completing it anyway — no reason to skip $50×10 odds
- [ ] Submit with time to spare — do not submit at 9:59pm on deadline day

**Done when:** submission is confirmed received.

---

## Post-hackathon (not required for submission, but worth capturing now while it's fresh)
- [ ] Replace mock data with a real ingestion path (CWR/DDEX format parsing)
- [ ] Default to `WRITEBACK_MODE=proposal` for any real deployment
- [ ] Push a custom DataHub entity type upstream instead of overloading Dataset + structured properties, if this becomes the actual startup
- [ ] Multi-territory conflict resolution logic (two rights holders both claiming the same split)
- [ ] This is close to a real MVP of the royalty reconciliation infra idea — revisit as the standalone startup direction once the hackathon is done