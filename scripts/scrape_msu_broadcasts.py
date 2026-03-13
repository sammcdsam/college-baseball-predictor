#!/usr/bin/env python3
"""
Scrape broadcast info (Watch/Listen) for Mississippi State baseball games.

Primary source: hailstate.com/sports/baseball/schedule
  - ESPN Watch direct links (TV/streaming)
  - StatBroadcast broadcast links with VSN audio (?vislive=msst)

Stores results in `game_broadcasts` table.

Usage:
    python3 scripts/scrape_msu_broadcasts.py              # Upcoming games
    python3 scripts/scrape_msu_broadcasts.py --all         # Full season
    python3 scripts/scrape_msu_broadcasts.py --date 2026-03-14
"""

import argparse
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen, Request

PROJECT_DIR = Path(__file__).parent.parent
DB_PATH = PROJECT_DIR / 'data' / 'baseball.db'

MSU_TEAM_ID = 'mississippi-state'
HAILSTATE_SCHEDULE_URL = 'https://hailstate.com/sports/baseball/schedule'

# Patterns in the HailState schedule HTML
# ESPN: espn.com/watch/player/_/eventCalendarId/<id>?gameId=<id>
ESPN_WATCH_RE = re.compile(r'espn\.com/watch/player/_/eventCalendarId/\d+\?gameId=(\d+)')
# SB audio: statbroadcast.com/broadcast/?id=<sb_id>&vislive=msst
SB_AUDIO_RE = re.compile(r'statbroadcast\.com/broadcast/\?id=(\d+)&amp;vislive=msst')
# SB broadcast (non-audio): statbroadcast.com/broadcast/?id=<sb_id> (no vislive)
SB_BROADCAST_RE = re.compile(r'statbroadcast\.com/broadcast/\?id=(\d+)(?!&amp;vislive)')


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
            provider TEXT NOT NULL,
            url TEXT,
            espn_game_id TEXT,
            updated_at TEXT DEFAULT (datetime('now')),
            UNIQUE(game_id, team_id, broadcast_type, provider)
        )
    """)
    conn.commit()


def fetch_hailstate_schedule():
    """Fetch the HailState baseball schedule page."""
    req = Request(HAILSTATE_SCHEDULE_URL, headers={'User-Agent': 'Mozilla/5.0'})
    with urlopen(req, timeout=15) as resp:
        return resp.read().decode('utf-8', errors='replace')


def parse_broadcast_links(html):
    """Extract ESPN watch links and VSN audio links from HailState schedule.

    Returns:
        espn_links: dict of espn_game_id -> direct watch URL
        audio_links: dict of sb_event_id -> VSN audio URL
    """
    espn_links = {}
    for m in ESPN_WATCH_RE.finditer(html):
        game_id = m.group(1)
        full_url = f'https://www.espn.com/watch/player/_/eventCalendarId/{game_id}?gameId={game_id}'
        espn_links[game_id] = full_url

    audio_links = {}
    for m in SB_AUDIO_RE.finditer(html):
        sb_id = m.group(1)
        full_url = f'https://stats.statbroadcast.com/broadcast/?id={sb_id}&vislive=msst'
        audio_links[sb_id] = full_url

    return espn_links, audio_links


def match_to_games(conn, espn_links, audio_links):
    """Match ESPN and SB links to our game records.

    Returns list of (game_id, espn_game_id, watch_url, audio_url) tuples.
    """
    results = {}

    # Match ESPN game IDs to our games via game_broadcasts or ESPN schedule data
    for espn_gid, watch_url in espn_links.items():
        # Try matching via existing game_broadcasts entries
        row = conn.execute(
            "SELECT game_id FROM game_broadcasts WHERE espn_game_id = ? LIMIT 1",
            (espn_gid,)
        ).fetchone()
        if row:
            gid = row['game_id']
            if gid not in results:
                results[gid] = {'espn_game_id': espn_gid, 'watch_url': None, 'audio_url': None}
            results[gid]['watch_url'] = watch_url
            results[gid]['espn_game_id'] = espn_gid
            continue

        # No existing broadcast entry — skip (will be matched via SB events or
        # future runs after initial ESPN API scrape populates espn_game_id)
        pass

    # Match SB audio links to our games via statbroadcast_events
    for sb_id, audio_url in audio_links.items():
        row = conn.execute(
            "SELECT game_id FROM statbroadcast_events WHERE sb_event_id = ? LIMIT 1",
            (sb_id,)
        ).fetchone()
        if row:
            gid = row['game_id']
            if gid not in results:
                results[gid] = {'espn_game_id': None, 'watch_url': None, 'audio_url': None}
            results[gid]['audio_url'] = audio_url

    return results


def scrape_broadcasts(conn, target_date=None, all_games=False):
    """Scrape and store broadcast info for MSU games."""
    ensure_table(conn)

    print("Fetching hailstate.com schedule...")
    html = fetch_hailstate_schedule()
    espn_links, audio_links = parse_broadcast_links(html)
    print(f"  Found {len(espn_links)} ESPN watch links, {len(audio_links)} VSN audio links")

    game_broadcasts = match_to_games(conn, espn_links, audio_links)
    print(f"  Matched to {len(game_broadcasts)} games")

    today = datetime.now().strftime('%Y-%m-%d')
    inserted = 0

    for game_id, info in game_broadcasts.items():
        # Filter by date if needed
        game_date = game_id[:10]  # game IDs start with YYYY-MM-DD
        if target_date and game_date != target_date:
            continue
        if not all_games and not target_date and game_date < today:
            continue

        espn_gid = info['espn_game_id']

        # Get broadcast provider name from ESPN API data if available
        # For now infer from existing data or use generic names
        row = conn.execute(
            "SELECT provider FROM game_broadcasts WHERE game_id = ? AND broadcast_type IN ('tv','streaming') LIMIT 1",
            (game_id,)
        ).fetchone()
        tv_provider = row['provider'] if row else 'SEC Network+'

        # Store ESPN watch link (streaming/tv)
        if info['watch_url']:
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO game_broadcasts
                    (game_id, team_id, broadcast_type, provider, url, espn_game_id)
                    VALUES (?, ?, 'streaming', ?, ?, ?)
                """, (game_id, MSU_TEAM_ID, tv_provider, info['watch_url'], espn_gid))
                inserted += 1
            except Exception as e:
                print(f"  Error: {e}")

        # Store VSN audio link
        if info['audio_url']:
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO game_broadcasts
                    (game_id, team_id, broadcast_type, provider, url, espn_game_id)
                    VALUES (?, ?, 'radio', 'Varsity Sports Network', ?, ?)
                """, (game_id, MSU_TEAM_ID, info['audio_url'], espn_gid))
                inserted += 1
            except Exception as e:
                print(f"  Error: {e}")

    conn.commit()
    return inserted


def main():
    parser = argparse.ArgumentParser(description="Scrape MSU broadcast info")
    parser.add_argument('--date', help='Specific date (YYYY-MM-DD)')
    parser.add_argument('--all', action='store_true', help='All games (not just upcoming)')
    args = parser.parse_args()

    conn = get_connection()

    print("MSU Broadcast Scraper (hailstate.com)")
    print("=" * 45)

    inserted = scrape_broadcasts(conn, target_date=args.date, all_games=args.all)
    print(f"\nInserted/updated: {inserted}")

    # Show upcoming
    rows = conn.execute("""
        SELECT gb.game_id, gb.broadcast_type, gb.provider, gb.url,
               g.date
        FROM game_broadcasts gb
        JOIN games g ON gb.game_id = g.id
        WHERE gb.team_id = ?
        AND g.date >= ?
        ORDER BY g.date, CASE gb.broadcast_type
            WHEN 'tv' THEN 1 WHEN 'streaming' THEN 2 WHEN 'radio' THEN 3 ELSE 4 END
    """, (MSU_TEAM_ID, datetime.now().strftime('%Y-%m-%d'))).fetchall()

    if rows:
        print(f"\nUpcoming MSU broadcasts:")
        current_game = None
        for r in rows:
            if r['game_id'] != current_game:
                current_game = r['game_id']
                print(f"\n  {r['date']} — {r['game_id']}")
            icon = {'tv': '📺', 'streaming': '💻', 'radio': '📻'}.get(r['broadcast_type'], '📡')
            print(f"    {icon} {r['provider']}: {r['url']}")

    conn.close()


if __name__ == '__main__':
    main()
