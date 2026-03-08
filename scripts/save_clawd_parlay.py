#!/usr/bin/env python3
"""
Save Claude's Parlay to the database.

Called by the AI session after it builds a parlay. Accepts JSON on stdin or as argument.

Usage:
    echo '{"legs": [...], "overall_reasoning": "...", "confidence": "medium"}' | python3 scripts/save_clawd_parlay.py
    python3 scripts/save_clawd_parlay.py --json '{"legs": [...]}'
    python3 scripts/save_clawd_parlay.py --dry-run --json '{"legs": [...]}'
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent
DB_PATH = PROJECT_DIR / 'data' / 'baseball.db'


def ml_to_decimal(ml):
    return 1 + ml / 100 if ml > 0 else 1 + 100 / abs(ml)


def get_today_cst():
    utc_now = datetime.now(timezone.utc)
    ct_offset = timedelta(hours=-5) if 3 <= utc_now.month <= 10 else timedelta(hours=-6)
    return (utc_now + ct_offset).strftime('%Y-%m-%d')


def validate_and_compute(parlay, date_str):
    """Validate parlay legs against real game data and compute odds."""
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row

    legs = parlay.get('legs', [])
    if not (3 <= len(legs) <= 6):
        return False, f"Need 3-6 legs, got {len(legs)}"

    decimal_odds = 1.0
    combined_prob = 1.0
    validated_legs = []

    for i, leg in enumerate(legs):
        gid = leg.get('game_id', '')
        side = leg.get('side', '')

        game = conn.execute("""
            SELECT g.id, g.home_team_id, g.away_team_id,
                   h.name as home_name, a.name as away_name,
                   bl.home_ml, bl.away_ml,
                   mp.predicted_home_prob as meta_prob
            FROM games g
            JOIN teams h ON g.home_team_id = h.id
            JOIN teams a ON g.away_team_id = a.id
            LEFT JOIN betting_lines bl ON g.id = bl.game_id
            LEFT JOIN model_predictions mp ON g.id = mp.game_id AND mp.model_name = 'meta_ensemble'
            WHERE g.id = ? AND g.status = 'scheduled'
        """, (gid,)).fetchone()

        if not game:
            return False, f"Leg {i+1}: game '{gid}' not found or not scheduled"

        if side == 'home':
            actual_ml = game['home_ml']
            pick_name = game['home_name']
            model_prob = game['meta_prob'] or 0.5
        elif side == 'away':
            actual_ml = game['away_ml']
            pick_name = game['away_name']
            model_prob = (1 - game['meta_prob']) if game['meta_prob'] else 0.5
        else:
            return False, f"Leg {i+1}: invalid side '{side}'"

        if actual_ml is None:
            return False, f"Leg {i+1}: no moneyline for {pick_name}"

        decimal_odds *= ml_to_decimal(actual_ml)
        combined_prob *= model_prob

        validated_legs.append({
            'game_id': gid,
            'pick': pick_name,
            'side': side,
            'odds': actual_ml,
            'model_prob': round(model_prob, 4),
            'reasoning': leg.get('reasoning', ''),
            'matchup': f"{game['away_name']} @ {game['home_name']}"
        })

    conn.close()

    american = round((decimal_odds - 1) * 100) if decimal_odds > 2 else round(-100 / (decimal_odds - 1))

    if american < 1200:
        return False, f"Combined odds +{american} below +1200 minimum"

    parlay['legs'] = validated_legs
    parlay['combined_odds_american'] = american
    parlay['decimal_odds'] = round(decimal_odds, 4)
    parlay['model_prob'] = round(combined_prob, 4)
    parlay['bet_amount'] = 5
    parlay['payout'] = round(5 * decimal_odds, 2)

    return True, "Valid"


def save_to_db(parlay, date_str):
    """Save to tracked_longshot_parlays table (NOT tracked_bets)."""
    conn = sqlite3.connect(str(DB_PATH), timeout=30)

    # Clean up any legacy entries in tracked_bets
    conn.execute("DELETE FROM tracked_bets WHERE date = ? AND pick_team_id = 'clawd_parlay'", (date_str,))

    # Save to the longshot parlays table where it belongs
    legs_json = json.dumps(parlay['legs'])
    conn.execute("""
        INSERT OR REPLACE INTO tracked_longshot_parlays 
        (date, legs_json, num_legs, american_odds, decimal_odds, model_prob, 
         bet_amount, payout, overall_reasoning, confidence, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 5, ?, ?, ?, ?)
    """, (
        date_str,
        legs_json,
        len(parlay['legs']),
        parlay['combined_odds_american'],
        parlay.get('decimal_odds'),
        parlay.get('model_prob', 0),
        parlay.get('payout'),
        parlay.get('overall_reasoning', ''),
        parlay.get('confidence', 'medium'),
        datetime.utcnow().isoformat()
    ))
    conn.commit()
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Save Claude's Parlay")
    parser.add_argument('--json', '-j', help='Parlay JSON string')
    parser.add_argument('--date', '-d', help='Date (default: today CST)')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    date_str = args.date or get_today_cst()

    if args.json:
        parlay = json.loads(args.json)
    else:
        parlay = json.loads(sys.stdin.read())

    valid, msg = validate_and_compute(parlay, date_str)
    if not valid:
        print(f"❌ Validation failed: {msg}")
        sys.exit(1)

    print(f"🎲 Claude's Parlay — {date_str}")
    print(f"   Combined: +{parlay['combined_odds_american']} | $5 → ${parlay['payout']}")
    print(f"   Model Prob: {parlay['model_prob']*100:.1f}% | Confidence: {parlay.get('confidence', '?')}")
    for i, leg in enumerate(parlay['legs']):
        print(f"   Leg {i+1}: {leg['pick']} ({leg['odds']:+d}) — {leg['reasoning']}")
    print(f"   Thesis: {parlay.get('overall_reasoning', 'N/A')}")

    if args.dry_run:
        print("\n[DRY RUN] Not saved.")
    else:
        save_to_db(parlay, date_str)
        print(f"\n✅ Saved to database (strategy=clawd_parlay)")


if __name__ == '__main__':
    main()
