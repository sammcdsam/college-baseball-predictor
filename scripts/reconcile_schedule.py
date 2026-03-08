#!/usr/bin/env python3
"""Reconcile scheduled games against ESPN team schedules.

For games that should have happened but are still 'scheduled':
1. Check ESPN team schedule API
2. If game not on ESPN → mark as canceled
3. If game on ESPN with different date → could be rescheduled (log for manual review)

Usage:
    python scripts/reconcile_schedule.py              # Reconcile yesterday's orphans
    python scripts/reconcile_schedule.py --all-past   # Reconcile ALL past orphans
    python scripts/reconcile_schedule.py --dry-run    # Preview only
"""
import argparse
import sqlite3
import requests
import time
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / 'data' / 'baseball.db'


def get_espn_schedule(espn_id: str, timeout=10) -> dict:
    """Fetch team schedule from ESPN API. Returns {date: [games]}."""
    url = f'https://site.api.espn.com/apis/site/v2/sports/baseball/college-baseball/teams/{espn_id}/schedule'
    try:
        r = requests.get(url, timeout=timeout)
        if r.status_code != 200:
            return {}
        data = r.json()
        
        schedule = {}
        for ev in data.get('events', []):
            date = ev.get('date', '')[:10]  # YYYY-MM-DD
            comps = ev.get('competitions', [{}])
            if not comps:
                continue
            c = comps[0]
            status = c.get('status', {}).get('type', {}).get('name', '')
            teams = c.get('competitors', [])
            opponents = [t['team'].get('displayName', '') for t in teams]
            
            if date not in schedule:
                schedule[date] = []
            schedule[date].append({
                'opponents': opponents,
                'status': status,
            })
        return schedule
    except Exception as e:
        print(f"ESPN API error for team {espn_id}: {e}")
        return {}


def reconcile_game(conn, game_id: str, home_id: str, away_id: str, game_date: str,
                   espn_schedules: dict, dry_run=False) -> str:
    """Check if game exists on ESPN. Returns action taken."""
    # Get ESPN schedules for both teams
    home_sched = espn_schedules.get(home_id, {})
    away_sched = espn_schedules.get(away_id, {})
    
    # Check if game date exists on either team's schedule
    home_games = home_sched.get(game_date, [])
    away_games = away_sched.get(game_date, [])
    
    # Look for the matchup
    home_name = conn.execute("SELECT name FROM teams WHERE id = ?", (home_id,)).fetchone()
    away_name = conn.execute("SELECT name FROM teams WHERE id = ?", (away_id,)).fetchone()
    home_name = home_name[0] if home_name else home_id
    away_name = away_name[0] if away_name else away_id
    
    found = False
    for g in home_games + away_games:
        opponents = [o.lower() for o in g['opponents']]
        if (home_name.lower()[:8] in str(opponents) or 
            away_name.lower()[:8] in str(opponents)):
            found = True
            break
    
    if found:
        return 'exists'
    
    # Game not found on ESPN — likely canceled/never scheduled
    if not dry_run:
        conn.execute("""
            UPDATE games SET status = 'canceled', 
                             updated_at = datetime('now')
            WHERE id = ? AND status = 'scheduled'
        """, (game_id,))
        conn.commit()
    return 'canceled'


def main():
    parser = argparse.ArgumentParser(description="Reconcile scheduled games with ESPN")
    parser.add_argument('--all-past', action='store_true', help='Reconcile all past orphans')
    parser.add_argument('--date', help='Specific date to reconcile (YYYY-MM-DD)')
    parser.add_argument('--dry-run', action='store_true', help='Preview only')
    parser.add_argument('--delay', type=float, default=0.3, help='Delay between ESPN requests')
    args = parser.parse_args()
    
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    
    today = datetime.now().strftime('%Y-%m-%d')
    
    # Determine which games to check
    if args.date:
        date_clause = f"date = '{args.date}'"
    elif args.all_past:
        date_clause = f"date < '{today}'"
    else:
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        date_clause = f"date = '{yesterday}'"
    
    orphans = conn.execute(f"""
        SELECT id, date, home_team_id, away_team_id
        FROM games
        WHERE status = 'scheduled' AND {date_clause}
        ORDER BY date
    """).fetchall()
    
    print(f"Found {len(orphans)} orphaned scheduled games")
    if not orphans:
        return
    
    # Collect unique teams that need ESPN schedule lookup
    teams_to_check = set()
    for g in orphans:
        teams_to_check.add(g['home_team_id'])
        teams_to_check.add(g['away_team_id'])
    
    print(f"Need ESPN schedules for {len(teams_to_check)} teams")
    
    # Get ESPN IDs
    team_espn_ids = {}
    for row in conn.execute("SELECT id, espn_id FROM teams WHERE espn_id IS NOT NULL"):
        team_espn_ids[row['id']] = row['espn_id']
    
    # Fetch ESPN schedules (with delay to be polite)
    espn_schedules = {}
    fetched = 0
    for team_id in teams_to_check:
        espn_id = team_espn_ids.get(team_id)
        if not espn_id:
            continue
        if espn_id in [espn_schedules.get(t, {}).get('_espn_id') for t in espn_schedules]:
            continue  # Already fetched
            
        sched = get_espn_schedule(espn_id)
        espn_schedules[team_id] = sched
        fetched += 1
        if fetched % 10 == 0:
            print(f"  Fetched {fetched} ESPN schedules...")
        time.sleep(args.delay)
    
    print(f"Fetched {fetched} ESPN schedules")
    
    # Reconcile each orphan
    canceled = 0
    exists = 0
    for g in orphans:
        action = reconcile_game(
            conn, g['id'], g['home_team_id'], g['away_team_id'], g['date'],
            espn_schedules, dry_run=args.dry_run
        )
        if action == 'canceled':
            canceled += 1
            print(f"  {'[DRY RUN] ' if args.dry_run else ''}Canceled: {g['id']}")
        else:
            exists += 1
    
    print(f"\nSummary: {canceled} canceled, {exists} verified on ESPN")
    if args.dry_run:
        print("(Dry run — no changes made)")


if __name__ == '__main__':
    main()
