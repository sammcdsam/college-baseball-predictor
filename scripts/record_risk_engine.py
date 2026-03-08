#!/usr/bin/env python3
"""
Snapshot risk engine bets into risk_engine_bets table.

Run once in the morning pipeline AFTER odds are captured.
Bets are locked in and won't change for the rest of the day.

Usage: python3 scripts/record_risk_engine.py [--date YYYY-MM-DD] [--dry-run]
"""
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
import pytz

PROJECT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT / 'scripts'))

DB_PATH = PROJECT / 'data' / 'baseball.db'


def record_risk_bets(date_str=None, dry_run=False):
    from bet_selection_v2 import analyze_games

    if date_str is None:
        date_str = datetime.now(pytz.timezone('America/Chicago')).strftime('%Y-%m-%d')

    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row

    # Check if already recorded for today
    existing = conn.execute(
        "SELECT COUNT(*) as c FROM risk_engine_bets WHERE date = ?", (date_str,)
    ).fetchone()['c']
    if existing > 0:
        print(f"Risk engine already has {existing} bets for {date_str} — skipping")
        conn.close()
        return

    # Run the analysis
    result = analyze_games(date_str)
    if result.get('error'):
        print(f"Error: {result['error']}")
        conn.close()
        return

    bets = result.get('bets', [])
    rejections = result.get('rejections', [])

    print(f"Risk engine analysis for {date_str}: {len(bets)} bets, {len(rejections)} rejected")

    for b in bets:
        if dry_run:
            print(f"  [DRY] {b.get('pick_team', '?')} vs {b.get('opponent', '?')}: "
                  f"ML {b.get('moneyline')}, edge {b.get('edge', 0):.1f}%, "
                  f"stake ${b.get('stake', 100):.0f}")
            continue

        pick_side = 'home' if b.get('is_home') else 'away'
        stake = b.get('suggested_stake') or b.get('bet_amount') or 100
        conn.execute("""
            INSERT INTO risk_engine_bets 
            (game_id, date, type, pick_team_name, opponent_name, pick_side,
             moneyline, model_prob, edge, stake, risk_mode, risk_score, kelly_fraction)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            b.get('game_id'),
            date_str,
            b.get('type', 'ML'),
            b.get('pick_team_name', ''),
            b.get('opponent_name', ''),
            pick_side,
            b.get('moneyline'),
            b.get('model_prob'),
            b.get('edge'),
            stake,
            b.get('risk_mode', 'fixed'),
            b.get('risk_score'),
            b.get('kelly_fraction_used'),
        ))
        print(f"  Recorded: {b.get('pick_team_name', '?')} vs {b.get('opponent_name', '?')} "
              f"ML {b.get('moneyline')} edge {b.get('edge', 0):.1f}%")

    conn.commit()
    conn.close()
    print(f"Locked in {len(bets)} risk engine bets for {date_str}")


if __name__ == '__main__':
    dry = '--dry-run' in sys.argv
    date = None
    for arg in sys.argv[1:]:
        if arg.startswith('20'):
            date = arg
    record_risk_bets(date, dry_run=dry)
