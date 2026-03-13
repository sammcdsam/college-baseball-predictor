#!/usr/bin/env python3
"""
Scrape broadcast info (Watch/Listen) for Mississippi State baseball games.

Sources:
  - ESPN API: TV/streaming broadcast, WatchESPN links
  - Varsity Sports Network: Radio/audio (static URL pattern for MSU)

Stores results in `game_broadcasts` table and surfaces on game detail page.

Usage:
    python3 scripts/scrape_msu_broadcasts.py              # Upcoming games
    python3 scripts/scrape_msu_broadcasts.py --all         # Full season
    python3 scripts/scrape_msu_broadcasts.py --date 2026-03-14
"""

import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import urlopen, Request

PROJECT_DIR = Path(__file__).parent.parent
DB_PATH = PROJECT_DIR / 'data' / 'baseball.db'

MSU_TEAM_ID = 'mississippi-state'
MSU_ESPN_ID = '150'
ESPN_SCHEDULE_URL = f'https://site.api.espn.com/apis/site/v2/sports/baseball/college-baseball/teams/{MSU_ESPN_ID}/schedule'

# Varsity Sports Network — MSU's radio home
# oas-1176 is MSU's source feed page which shows all live/recent streams
VARSITY_NETWORK_URL = 'https://thevarsitynetwork.com/feed/source/oas-1176'


def get_connection():
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def ensure_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS game_broadcasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id TEXT NOT NULL,
            team_id TEXT NOT NULL,
            broadcast_type TEXT NOT NULL,  -- 'tv', 'streaming', 'radio'
            provider TEXT NOT NULL,        -- 'SEC Network', 'SECN+', 'Varsity Sports Network'
            url TEXT,                      -- watch/listen link
            espn_game_id TEXT,             -- ESPN's game ID for deep links
            updated_at TEXT DEFAULT (datetime('now')),
            UNIQUE(game_id, team_id, broadcast_type, provider)
        )
    """)
    conn.commit()


def fetch_espn_schedule(season=2026):
    """Fetch MSU schedule with broadcast data from ESPN API."""
    url = f"{ESPN_SCHEDULE_URL}?season={season}"
    req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def parse_espn_date(espn_date):
    """Convert ESPN UTC date string to YYYY-MM-DD in Central time."""
    # ESPN dates are like '2026-03-13T23:00Z'
    dt = datetime.strptime(espn_date.replace('Z', '+00:00').split('+')[0], '%Y-%m-%dT%H:%M')
    dt = dt.replace(tzinfo=timezone.utc)
    # Convert to Central (approximate — CST/CDT)
    ct_offset = timedelta(hours=-5)  # CDT during baseball season
    ct = dt + ct_offset
    return ct.strftime('%Y-%m-%d')


def match_espn_to_game(conn, espn_event, date_str):
    """Match an ESPN event to our games table for MSU."""
    comp = espn_event.get('competitions', [{}])[0]
    competitors = comp.get('competitors', [])

    # Find opponent
    for c in competitors:
        if c.get('team', {}).get('id') != MSU_ESPN_ID:
            opp_name = c.get('team', {}).get('location', '')
            opp_abbr = c.get('team', {}).get('abbreviation', '')

    # Try to find game in our DB
    rows = conn.execute("""
        SELECT id FROM games
        WHERE date = ?
        AND (home_team_id = ? OR away_team_id = ?)
        ORDER BY id
    """, (date_str, MSU_TEAM_ID, MSU_TEAM_ID)).fetchall()

    if len(rows) == 1:
        return rows[0]['id']
    elif len(rows) > 1:
        # Multiple games (doubleheader) — try to match by time
        return rows[0]['id']  # Best guess for now

    return None


def scrape_broadcasts(conn, target_date=None, all_games=False):
    """Scrape and store broadcast info for MSU games."""
    ensure_table(conn)

    data = fetch_espn_schedule()
    events = data.get('events', [])

    today = datetime.now().strftime('%Y-%m-%d')
    inserted = 0
    skipped = 0

    for event in events:
        espn_date = event.get('date', '')
        date_str = parse_espn_date(espn_date)

        # Filter by date
        if target_date and date_str != target_date:
            continue
        if not all_games and not target_date and date_str < today:
            continue

        espn_game_id = event.get('id')
        game_id = match_espn_to_game(conn, event, date_str)
        if not game_id:
            continue

        comp = event.get('competitions', [{}])[0]
        broadcasts = comp.get('broadcasts', [])
        links = event.get('links', [])

        # Build direct ESPN Watch URL from game ID
        # https://www.espn.com/watch/?gameId=<id> goes straight to the stream
        watch_url = f'https://www.espn.com/watch/?gameId={espn_game_id}' if espn_game_id else None

        # Store TV/Streaming broadcasts from ESPN
        for bc in broadcasts:
            bc_type_raw = bc.get('type', {}).get('shortName', '').lower()
            provider = bc.get('media', {}).get('shortName', '')

            if bc_type_raw == 'tv':
                bc_type = 'tv'
            elif bc_type_raw == 'streaming':
                bc_type = 'streaming'
            else:
                bc_type = bc_type_raw or 'streaming'

            try:
                conn.execute("""
                    INSERT OR REPLACE INTO game_broadcasts
                    (game_id, team_id, broadcast_type, provider, url, espn_game_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (game_id, MSU_TEAM_ID, bc_type, provider, watch_url, espn_game_id))
                inserted += 1
            except Exception as e:
                print(f"  Error inserting broadcast: {e}")
                skipped += 1

        # Always add Varsity Sports Network radio for MSU home games
        try:
            conn.execute("""
                INSERT OR REPLACE INTO game_broadcasts
                (game_id, team_id, broadcast_type, provider, url, espn_game_id)
                VALUES (?, ?, 'radio', 'Varsity Sports Network', ?, ?)
            """, (game_id, MSU_TEAM_ID, VARSITY_NETWORK_URL, espn_game_id))
            inserted += 1
        except Exception as e:
            skipped += 1

    conn.commit()
    return inserted, skipped


def main():
    parser = argparse.ArgumentParser(description="Scrape MSU broadcast info")
    parser.add_argument('--date', help='Specific date (YYYY-MM-DD)')
    parser.add_argument('--all', action='store_true', help='All games (not just upcoming)')
    args = parser.parse_args()

    conn = get_connection()

    print("MSU Broadcast Scraper")
    print("=" * 40)

    inserted, skipped = scrape_broadcasts(conn, target_date=args.date, all_games=args.all)
    print(f"Inserted/updated: {inserted}, skipped: {skipped}")

    # Show upcoming
    rows = conn.execute("""
        SELECT gb.game_id, gb.broadcast_type, gb.provider, gb.url,
               g.date, g.time
        FROM game_broadcasts gb
        JOIN games g ON gb.game_id = g.id
        WHERE gb.team_id = ?
        AND g.date >= ?
        ORDER BY g.date, gb.broadcast_type
    """, (MSU_TEAM_ID, datetime.now().strftime('%Y-%m-%d'))).fetchall()

    if rows:
        print(f"\nUpcoming MSU broadcasts:")
        current_game = None
        for r in rows:
            if r['game_id'] != current_game:
                current_game = r['game_id']
                print(f"\n  {r['date']} {r['time'] or ''} — {r['game_id']}")
            icon = {'tv': '📺', 'streaming': '💻', 'radio': '📻'}.get(r['broadcast_type'], '📡')
            print(f"    {icon} {r['provider']}: {r['url'] or 'no link'}")

    conn.close()


if __name__ == '__main__':
    main()
