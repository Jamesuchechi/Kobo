#!/usr/bin/env python3
"""
data/generate_mock_data.py

Generates a mock music rights/royalty dataset for Kobo:
  - tracks
  - rights_holders
  - ownership_splits  (edges between tracks and rights_holders)
  - usage_events
  - payouts           (edges from usage_events)

The dataset is NOT random noise. It deliberately seeds five specific,
explainable reconciliation problems (see SCENARIOS below) so that when the
Kobo agent runs against this data, every mismatch it finds is a real,
demonstrable scenario worth showing in the demo video -- not an artifact of
randomness.

Everything else in the dataset is generated to be internally consistent and
"correct" (splits sum to 100%, payouts match expected values) so the seeded
scenarios stand out clearly against a clean baseline.

Usage:
    python3 data/generate_mock_data.py
    python3 data/generate_mock_data.py --seed 42 --tracks 80 --output-dir data/seed

Output:
    data/seed/tracks.csv
    data/seed/rights_holders.csv
    data/seed/ownership_splits.csv
    data/seed/usage_events.csv
    data/seed/payouts.csv
    data/seed/scenarios.json   <- documents exactly what was seeded and why,
                                  used by later phases to verify the agent
                                  finds precisely these cases.
"""

import argparse
import csv
import json
import os
import random
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# Reference data pools (fictional -- deliberately not real artists/labels)
# ---------------------------------------------------------------------------

ARTIST_FIRST = [
    "Ada", "Kwame", "Zainab", "Tobi", "Amara", "Chidi", "Folake", "Kofi",
    "Nneka", "Sena", "Yemi", "Abena", "Emeka", "Lindiwe", "Osaze", "Thandiwe",
    "Bayo", "Chiamaka", "Kesi", "Mmesoma",
]
ARTIST_SUFFIX = [
    "Wave", "Beats", "Sound", "Rhythm", "Vibe", "Groove", "Echo", "Pulse",
    "Motion", "Frequency",
]
TRACK_ADJECTIVES = [
    "Golden", "Midnight", "Electric", "Velvet", "Wild", "Sunlit", "Restless",
    "Silver", "Amber", "Distant", "Neon", "Quiet", "Burning", "Free",
]
TRACK_NOUNS = [
    "Skyline", "Harmattan", "Riverbend", "Lagos Nights", "Drumline",
    "Compass", "Horizon", "Highlife", "Savannah", "Static", "Afterglow",
    "Currents", "Signal", "Homecoming",
]
PUBLISHER_NAMES = [
    "Baobab Music Publishing", "Lagos Sound Rights", "Kente Sync Co.",
    "Harmattan Publishing Group", "Coastline Rights Collective",
    "Savannah Music Admin",
]
LABEL_NAMES = [
    "Palmwine Records", "Highlife Recordings", "Zenith Sound Label",
    "Delta Frequency Records", "Northbank Music",
]
TERRITORIES = ["US", "UK", "NG", "DE", "FR", "ZA", "GH", "CA"]
PLATFORMS = ["Spotify", "Apple Music", "Deezer", "Jamendo", "Boomplay", "Audiomack"]
RIGHT_TYPES = ["mechanical", "performance", "sync"]

# Per-unit payout rate (very rough, purely for internal consistency -- not
# modeled on any real DSP rate card).
PLATFORM_RATE_PER_UNIT = {
    "Spotify": 0.0038,
    "Apple Music": 0.0074,
    "Deezer": 0.0046,
    "Jamendo": 0.0012,
    "Boomplay": 0.0021,
    "Audiomack": 0.0018,
}


@dataclass
class Track:
    track_id: str
    isrc: str
    title: str
    primary_artist: str


@dataclass
class RightsHolder:
    holder_id: str
    name: str
    holder_type: str  # writer | publisher | label | performer
    payee_id: str


@dataclass
class OwnershipSplit:
    split_id: str
    track_id: str
    holder_id: str
    split_pct: float
    territory: str  # "ALL" or a specific territory code
    right_type: str
    license_start: str
    license_end: str  # "" means open-ended


@dataclass
class UsageEvent:
    event_id: str
    track_id: str
    event_type: str  # stream | play | sync
    territory: str
    platform: str
    timestamp: str
    unit_count: int
    event_value: float


@dataclass
class Payout:
    payout_id: str
    usage_event_id: str
    payee_id: str
    amount_paid: float
    currency: str
    statement_period: str


@dataclass
class Scenario:
    scenario_id: str
    name: str
    track_id: str
    description: str
    expected_agent_finding: str


def make_isrc(rng: random.Random, idx: int) -> str:
    country = rng.choice(["US", "GB", "NG", "DE"])
    registrant = "".join(rng.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=3))
    year = rng.choice(["22", "23", "24", "25"])
    return f"{country}{registrant}{year}{idx:05d}"


def random_date(rng: random.Random, start: datetime, end: datetime) -> datetime:
    delta = end - start
    return start + timedelta(seconds=rng.randint(0, int(delta.total_seconds())))


def build_track(rng: random.Random, idx: int) -> Track:
    artist = f"{rng.choice(ARTIST_FIRST)} {rng.choice(ARTIST_SUFFIX)}"
    title = f"{rng.choice(TRACK_ADJECTIVES)} {rng.choice(TRACK_NOUNS)}"
    return Track(
        track_id=f"trk_{idx:04d}",
        isrc=make_isrc(rng, idx),
        title=title,
        primary_artist=artist,
    )


def build_rights_holder(rng: random.Random, idx: int, holder_type: str) -> RightsHolder:
    if holder_type == "publisher":
        name = rng.choice(PUBLISHER_NAMES)
    elif holder_type == "label":
        name = rng.choice(LABEL_NAMES)
    else:
        name = f"{rng.choice(ARTIST_FIRST)} {rng.choice(ARTIST_SUFFIX)}"
    return RightsHolder(
        holder_id=f"rh_{idx:04d}",
        name=name,
        holder_type=holder_type,
        payee_id=f"payee_{idx:04d}",
    )


def clean_splits_for_track(
    rng: random.Random,
    track: Track,
    holders: list,
    license_window: tuple,
) -> list:
    """Generate a correct, fully-summing split set for one track."""
    n_holders = rng.randint(2, 4)
    chosen = rng.sample(holders, k=min(n_holders, len(holders)))
    pct_left = 100.0
    splits = []
    for i, holder in enumerate(chosen):
        if i == len(chosen) - 1:
            pct = round(pct_left, 2)
        else:
            pct = round(rng.uniform(10, pct_left - 10 * (len(chosen) - i - 1)), 2)
            pct_left -= pct
        splits.append(
            OwnershipSplit(
                split_id=f"spl_{track.track_id}_{i}",
                track_id=track.track_id,
                holder_id=holder.holder_id,
                split_pct=pct,
                territory="ALL",
                right_type=rng.choice(RIGHT_TYPES),
                license_start=license_window[0].strftime("%Y-%m-%d"),
                license_end="",
            )
        )
    return splits


def generate(seed: int, n_tracks: int, output_dir: str) -> None:
    rng = random.Random(seed)

    license_start_window = datetime(2020, 1, 1)
    license_end_window = datetime(2026, 1, 1)
    event_window_start = datetime(2025, 6, 1)
    event_window_end = datetime(2026, 6, 1)

    tracks: list = []
    rights_holders: list = []
    splits: list = []
    usage_events: list = []
    payouts: list = []
    scenarios: list = []

    # --- Rights holder pool (shared across tracks, like real catalogs) ---
    for i in range(1, 26):
        holder_type = rng.choice(["writer", "publisher", "label", "performer"])
        rights_holders.append(build_rights_holder(rng, i, holder_type))

    # --- Tracks ---
    for i in range(1, n_tracks + 1):
        tracks.append(build_track(rng, i))

    # Reserve track_ids 1-5 for deliberate scenarios; the rest are "clean".
    scenario_track_ids = {t.track_id for t in tracks[:5]}

    event_counter = 1
    payout_counter = 1

    for track in tracks:
        license_window = (
            random_date(rng, license_start_window, datetime(2021, 1, 1)),
            None,
        )

        # -------------------------------------------------------------
        # SCENARIO 1: incomplete_split -- splits sum to < 100%
        # -------------------------------------------------------------
        if track.track_id == tracks[0].track_id:
            chosen = rng.sample(rights_holders, k=2)
            track_splits = [
                OwnershipSplit(
                    split_id=f"spl_{track.track_id}_0",
                    track_id=track.track_id,
                    holder_id=chosen[0].holder_id,
                    split_pct=60.0,
                    territory="ALL",
                    right_type="mechanical",
                    license_start=license_window[0].strftime("%Y-%m-%d"),
                    license_end="",
                ),
                OwnershipSplit(
                    split_id=f"spl_{track.track_id}_1",
                    track_id=track.track_id,
                    holder_id=chosen[1].holder_id,
                    split_pct=34.0,  # sums to 94%, missing 6% -- unaccounted rights holder
                    territory="ALL",
                    right_type="mechanical",
                    license_start=license_window[0].strftime("%Y-%m-%d"),
                    license_end="",
                ),
            ]
            splits.extend(track_splits)
            scenarios.append(
                Scenario(
                    scenario_id="scenario_1",
                    name="incomplete_split",
                    track_id=track.track_id,
                    description=(
                        "Ownership splits for this track sum to 94%, not 100%. "
                        "6% of rights are unaccounted for -- a rights holder was "
                        "likely never linked to this track."
                    ),
                    expected_agent_finding=(
                        "Agent should detect total_split_pct < 100 for this track "
                        "and flag the gap percentage."
                    ),
                )
            )

        # -------------------------------------------------------------
        # SCENARIO 2: duplicate_claim -- splits sum to > 100% (conflict)
        # -------------------------------------------------------------
        elif track.track_id == tracks[1].track_id:
            chosen = rng.sample(rights_holders, k=2)
            track_splits = [
                OwnershipSplit(
                    split_id=f"spl_{track.track_id}_0",
                    track_id=track.track_id,
                    holder_id=chosen[0].holder_id,
                    split_pct=100.0,
                    territory="ALL",
                    right_type="performance",
                    license_start=license_window[0].strftime("%Y-%m-%d"),
                    license_end="",
                ),
                OwnershipSplit(
                    split_id=f"spl_{track.track_id}_1",
                    track_id=track.track_id,
                    holder_id=chosen[1].holder_id,
                    split_pct=60.0,  # overlapping claim -- sums to 160%
                    territory="ALL",
                    right_type="performance",
                    license_start=license_window[0].strftime("%Y-%m-%d"),
                    license_end="",
                ),
            ]
            splits.extend(track_splits)
            scenarios.append(
                Scenario(
                    scenario_id="scenario_2",
                    name="duplicate_claim",
                    track_id=track.track_id,
                    description=(
                        "Two rights holders both claim performance rights on this "
                        "track with overlapping territory/right_type, summing to "
                        "160%. Likely a duplicate or conflicting ownership claim."
                    ),
                    expected_agent_finding=(
                        "Agent should detect total_split_pct > 100 for the same "
                        "territory/right_type combination and flag both holders."
                    ),
                )
            )

        # -------------------------------------------------------------
        # SCENARIO 3: expired_license -- usage event postdates license_end
        # -------------------------------------------------------------
        elif track.track_id == tracks[2].track_id:
            expired_end = datetime(2025, 3, 1)
            chosen = rng.sample(rights_holders, k=2)
            track_splits = clean_splits_for_track(rng, track, chosen, license_window)
            for s in track_splits:
                s.license_end = expired_end.strftime("%Y-%m-%d")
            splits.extend(track_splits)
            scenarios.append(
                Scenario(
                    scenario_id="scenario_3",
                    name="expired_license",
                    track_id=track.track_id,
                    description=(
                        "All ownership splits on this track have a license_end "
                        "of 2025-03-01, but a usage event (and matching payout) "
                        "was recorded after that date."
                    ),
                    expected_agent_finding=(
                        "Agent should detect a usage_event timestamp after the "
                        "relevant split's license_end and flag the payout as "
                        "issued against an expired license."
                    ),
                )
            )

        # -------------------------------------------------------------
        # SCENARIO 4: territory_mismatch -- split only covers one territory,
        # usage happened in a different one, but payout was still issued
        # -------------------------------------------------------------
        elif track.track_id == tracks[3].track_id:
            chosen = rng.sample(rights_holders, k=2)
            track_splits = [
                OwnershipSplit(
                    split_id=f"spl_{track.track_id}_0",
                    track_id=track.track_id,
                    holder_id=chosen[0].holder_id,
                    split_pct=100.0,
                    territory="US",  # only licensed for US
                    right_type="mechanical",
                    license_start=license_window[0].strftime("%Y-%m-%d"),
                    license_end="",
                ),
            ]
            splits.extend(track_splits)
            scenarios.append(
                Scenario(
                    scenario_id="scenario_4",
                    name="territory_mismatch",
                    track_id=track.track_id,
                    description=(
                        "This track's only ownership split is licensed for "
                        "territory=US. A usage event occurred in DE and was "
                        "still paid out, with no matching territory split."
                    ),
                    expected_agent_finding=(
                        "Agent should find no matching split for the event's "
                        "territory and flag the payout as unsupported by any "
                        "valid ownership split."
                    ),
                )
            )

        # -------------------------------------------------------------
        # SCENARIO 5: missing_rights_holder -- payout goes to a payee_id
        # not present among the track's rights holders at all
        # -------------------------------------------------------------
        elif track.track_id == tracks[4].track_id:
            chosen = rng.sample(rights_holders, k=2)
            track_splits = clean_splits_for_track(rng, track, chosen, license_window)
            splits.extend(track_splits)
            scenarios.append(
                Scenario(
                    scenario_id="scenario_5",
                    name="missing_rights_holder",
                    track_id=track.track_id,
                    description=(
                        "This track's splits are complete and sum to 100%, but "
                        "a payout was issued to a payee_id that does not match "
                        "any rights holder linked to this track."
                    ),
                    expected_agent_finding=(
                        "Agent should find a payout whose payee_id does not "
                        "resolve to any of the track's linked rights holders."
                    ),
                )
            )

        # -------------------------------------------------------------
        # Everything else: clean, correctly-summing splits
        # -------------------------------------------------------------
        else:
            chosen = rng.sample(rights_holders, k=rng.randint(2, 4))
            track_splits = clean_splits_for_track(rng, track, chosen, license_window)
            splits.extend(track_splits)

        # -----------------------------------------------------------------
        # Usage events + payouts for this track
        # -----------------------------------------------------------------
        n_events = rng.randint(1, 3) if track.track_id in scenario_track_ids else rng.randint(1, 5)
        track_splits_all = [s for s in splits if s.track_id == track.track_id]

        for _ in range(n_events):
            platform = rng.choice(PLATFORMS)
            territory = rng.choice(TERRITORIES)
            unit_count = rng.randint(500, 250_000)
            rate = PLATFORM_RATE_PER_UNIT[platform]
            event_value = round(unit_count * rate, 2)

            if track.track_id == tracks[2].track_id:
                # Scenario 3: force this event to occur AFTER the expired license
                ts = random_date(rng, datetime(2025, 4, 1), event_window_end)
            elif track.track_id == tracks[3].track_id:
                # Scenario 4: force this event into a non-licensed territory
                territory = "DE"
                ts = random_date(rng, event_window_start, event_window_end)
            else:
                ts = random_date(rng, event_window_start, event_window_end)

            event = UsageEvent(
                event_id=f"evt_{event_counter:06d}",
                track_id=track.track_id,
                event_type=rng.choice(["stream", "play", "sync"]),
                territory=territory,
                platform=platform,
                timestamp=ts.strftime("%Y-%m-%dT%H:%M:%S"),
                unit_count=unit_count,
                event_value=event_value,
            )
            usage_events.append(event)
            event_counter += 1

            # Determine payout recipients
            if track.track_id == tracks[4].track_id:
                # Scenario 5: pay out to a payee_id NOT among this track's holders
                stray_holder = rng.choice(
                    [h for h in rights_holders if h.holder_id not in {s.holder_id for s in track_splits_all}]
                )
                payouts.append(
                    Payout(
                        payout_id=f"pay_{payout_counter:06d}",
                        usage_event_id=event.event_id,
                        payee_id=stray_holder.payee_id,
                        amount_paid=event_value,
                        currency="USD",
                        statement_period=ts.strftime("%Y-%m"),
                    )
                )
                payout_counter += 1
            else:
                relevant_splits = [
                    s for s in track_splits_all
                    if s.territory in ("ALL", territory)
                ]
                for split in relevant_splits:
                    holder = next(h for h in rights_holders if h.holder_id == split.holder_id)
                    amount = round(event_value * (split.split_pct / 100.0), 2)
                    payouts.append(
                        Payout(
                            payout_id=f"pay_{payout_counter:06d}",
                            usage_event_id=event.event_id,
                            payee_id=holder.payee_id,
                            amount_paid=amount,
                            currency="USD",
                            statement_period=ts.strftime("%Y-%m"),
                        )
                    )
                    payout_counter += 1

    # -----------------------------------------------------------------
    # Write output
    # -----------------------------------------------------------------
    os.makedirs(output_dir, exist_ok=True)

    _write_csv(os.path.join(output_dir, "tracks.csv"), tracks)
    _write_csv(os.path.join(output_dir, "rights_holders.csv"), rights_holders)
    _write_csv(os.path.join(output_dir, "ownership_splits.csv"), splits)
    _write_csv(os.path.join(output_dir, "usage_events.csv"), usage_events)
    _write_csv(os.path.join(output_dir, "payouts.csv"), payouts)

    with open(os.path.join(output_dir, "scenarios.json"), "w") as f:
        json.dump([asdict(s) for s in scenarios], f, indent=2)

    print(f"Generated {len(tracks)} tracks, {len(rights_holders)} rights holders, "
          f"{len(splits)} ownership splits, {len(usage_events)} usage events, "
          f"{len(payouts)} payouts.")
    print(f"Seeded {len(scenarios)} deliberate reconciliation scenarios -- "
          f"see {output_dir}/scenarios.json for details.")
    print(f"Output written to: {output_dir}/")


def _write_csv(path: str, rows: list) -> None:
    if not rows:
        return
    fieldnames = list(asdict(rows[0]).keys())
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def main():
    parser = argparse.ArgumentParser(description="Generate mock Kobo rights/royalty data")
    parser.add_argument("--seed", type=int, default=int(os.environ.get("MOCK_DATA_SEED", 42)))
    parser.add_argument("--tracks", type=int, default=80, help="Number of tracks to generate (min 5)")
    parser.add_argument("--output-dir", type=str, default="data/seed")
    args = parser.parse_args()

    if args.tracks < 5:
        raise SystemExit("--tracks must be at least 5 (the first 5 are reserved for seeded scenarios)")

    generate(seed=args.seed, n_tracks=args.tracks, output_dir=args.output_dir)


if __name__ == "__main__":
    main()
