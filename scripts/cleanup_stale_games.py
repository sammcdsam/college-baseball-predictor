#!/usr/bin/env python3
"""
Cleanup Stale In-Progress Games

Finds games stuck in 'in-progress' that are clearly over (stale for 3+ hours
with scores and a late-inning indicator) and finalizes them.

Safe for late-night West Coast games — uses staleness threshold, not clock time.
Only finalizes games that:
  1. Have been stale (no updates) for 3+ hours
  2. Have non-null scores
  3. Show a late-game inning indicator (End/Mid/Bot/Top 7th+, or "Final" stuck in text)

Designed to run at 11 PM CT and 2 AM CT to catch stragglers without waiting
until the next morning's full finalize_games.py run.

Usage:
    python3 scripts/cleanup_stale_games.py              # Auto-cleanup
    python3 scripts/cleanup_stale_games.py --dry-run    # Preview only
    python3 scripts/cleanup_stale_games.py --hours 4    # Custom staleness threshold
"""

import argparse
import re
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent
DB_PATH = PROJECT_DIR / 'data' / 'baseball.db'

# Minimum hours since last update before we consider a game "stale enough" to finalize
DEFAULT_STALE_HOURS = 3

# Inning patterns that indicate a game is likely over or very late
# We're generous here — if it's been 3+ hours with no update AND shows late innings, it's done
LATE_GAME_PATTERNS = [
    r'final',                    # "Final" or "Final/10" stuck in inning_text
    r'end\s+\d',                 # "End 9th", "End 7th", etc.
    r'(top|bot|mid)\s+(7|8|9|1[0-9])',  # 7th inning or later
]

LATE_GAME_RE = re.compile('|'.join(LATE_GAME_PATTERNS), re.IGNORECASE)


def get_connection():
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def find_stale_games(conn, stale_hours=DEFAULT_STALE_HOURS):
    """Find in-progress games that are stale and likely finished."""
    cutoff = (datetime.utcnow() - timedelta(hours=stale_hours)).isoformat()

    rows = conn.execute("""
        SELECT g.id, g.date, g.home_team_id, g.away_team_id,
               g.home_score, g.away_score, g.inning_text, g.updated_at,
               h.name as home_name, a.name as away_name,
               ROUND((julianday('now') - julianday(g.updated_at)) * 1440) as mins_stale
        FROM games g
        JOIN teams h ON g.home_team_id = h.id
        JOIN teams a ON g.away_team_id = a.id
        WHERE g.status = 'in-progress'
          AND g.updated_at < ?
          AND g.home_score IS NOT NULL
          AND g.away_score IS NOT NULL
          AND g.status_locked != 1
        ORDER BY g.updated_at ASC
    """, (cutoff,)).fetchall()

    stale = []
    for row in rows:
        inning = row['inning_text'] or ''
        if LATE_GAME_RE.search(inning):
            stale.append(dict(row))

    return stale


def determine_winner(game):
    """Determine winner_id from scores."""
    home_score = game['home_score'] or 0
    away_score = game['away_score'] or 0
    if home_score > away_score:
        return game['home_team_id']
    elif away_score > home_score:
        return game['away_team_id']
    return None  # Tie — shouldn't happen but don't guess


def finalize_stale_games(conn, games, dry_run=False):
    """Mark stale games as final."""
    finalized = 0
    for g in games:
        winner_id = determine_winner(g)
        hrs = g['mins_stale'] / 60

        print(f"  {'[DRY RUN] ' if dry_run else ''}Finalizing: {g['away_name']} {g['away_score']} @ "
              f"{g['home_name']} {g['home_score']} ({g['inning_text']}) — "
              f"stale {hrs:.1f}h → winner: {winner_id or 'TIE'}")

        if not dry_run:
            conn.execute("""
                UPDATE games
                SET status = 'final',
                    inning_text = 'Final',
                    winner_id = COALESCE(?, winner_id),
                    updated_at = ?
                WHERE id = ? AND status = 'in-progress'
            """, (winner_id, datetime.utcnow().isoformat(), g['id']))
            finalized += 1

    if not dry_run and finalized > 0:
        conn.commit()

    return finalized


def main():
    parser = argparse.ArgumentParser(description="Cleanup stale in-progress games")
    parser.add_argument('--dry-run', action='store_true', help='Preview without changing DB')
    parser.add_argument('--hours', type=float, default=DEFAULT_STALE_HOURS,
                        help=f'Staleness threshold in hours (default: {DEFAULT_STALE_HOURS})')
    args = parser.parse_args()

    conn = get_connection()

    print(f"Stale Game Cleanup (threshold: {args.hours}h)")
    print("=" * 50)

    stale = find_stale_games(conn, stale_hours=args.hours)

    if not stale:
        print("No stale in-progress games found. All clear.")
        conn.close()
        return

    print(f"Found {len(stale)} stale game(s):")
    count = finalize_stale_games(conn, stale, dry_run=args.dry_run)

    if args.dry_run:
        print(f"\n[DRY RUN] Would finalize {len(stale)} games.")
    else:
        print(f"\nFinalized {count} stale games.")

    conn.close()


if __name__ == '__main__':
    main()
