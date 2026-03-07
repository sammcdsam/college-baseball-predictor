#!/usr/bin/env python3
"""
Claude's Parlay — AI-driven parlay builder.

Gathers game context, sends it to an AI session, gets back a reasoned parlay,
and records it in the database.

Usage:
    python3 scripts/run_clawd_parlay.py              # Today
    python3 scripts/run_clawd_parlay.py --date 2026-03-07
    python3 scripts/run_clawd_parlay.py --dry-run    # Don't save to DB
"""

import argparse
import json
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent
DB_PATH = PROJECT_DIR / 'data' / 'baseball.db'

sys.path.insert(0, str(PROJECT_DIR / 'scripts'))
from build_clawd_parlay_context import build_context, format_as_text


PARLAY_PROMPT = """You are building "Claude's Parlay" — a daily sports parlay bet on college baseball.

## Your Task
Analyze the games below and build a parlay with these constraints:
- **3 to 6 legs** (your choice based on the slate)
- **Minimum +1200 combined American odds**
- **$5 bet** (fun money, be creative)
- You can pick favorites OR underdogs — whatever you think is best value
- Each leg must use a real moneyline from the data provided
- No same-game parlays (each leg = different game)

## How to Think
- Look for VALUE, not just winners. A -400 favorite is boring and provides no value.
- Consider model disagreements — when the model says 80% but the line implies 60%, there's edge.
- Think about correlations — do your picks tell a story? (e.g., "cold weather day = unders")
- Factor in recent form, pitching matchups, home/away splits
- Don't just pick the 6 highest-probability games. Be thoughtful.
- Underdogs can be great parlay legs if the model sees value.

## Output Format
Return EXACTLY this JSON structure (no markdown fencing, no extra text before/after):
{
  "legs": [
    {
      "game_id": "YYYY-MM-DD_away_home",
      "pick": "Team Name",
      "side": "home" or "away",
      "odds": -150,
      "reasoning": "One sentence why this pick"
    }
  ],
  "overall_reasoning": "2-3 sentences explaining the parlay theme/thesis",
  "combined_odds_american": 1500,
  "confidence": "low/medium/high"
}

## Today's Games
{context}
"""


def get_today_cst():
    utc_now = datetime.now(timezone.utc)
    ct_offset = timedelta(hours=-5) if 3 <= utc_now.month <= 10 else timedelta(hours=-6)
    return (utc_now + ct_offset).strftime('%Y-%m-%d')


def call_ai(prompt, timeout=120):
    """Call the AI via openclaw system event and parse response."""
    # Use oracle CLI for a one-shot AI call
    cmd = [
        '/home/sam/.npm-global/bin/openclaw', 'oracle',
        '--engine', 'anthropic/claude-sonnet-4-20250514',
        '--prompt', prompt,
        '--max-tokens', '2000',
        '--json'
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            print(f"[Claude's Parlay] Oracle error: {result.stderr[:500]}")
            return None
        output = json.loads(result.stdout)
        return output.get('text', output.get('content', ''))
    except subprocess.TimeoutExpired:
        print("[Claude's Parlay] Oracle timed out")
        return None
    except Exception as e:
        print(f"[Claude's Parlay] Error: {e}")
        return None


def parse_parlay_response(text):
    """Parse JSON parlay from AI response."""
    if not text:
        return None

    # Try to find JSON in the response
    # First try: raw JSON
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # Second try: extract JSON block from markdown
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # Third try: find first { to last }
    start = text.find('{')
    end = text.rfind('}')
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    print(f"[Claude's Parlay] Could not parse AI response:\n{text[:500]}")
    return None


def validate_parlay(parlay, context_data):
    """Validate the AI's parlay against real game data."""
    if not parlay or 'legs' not in parlay:
        return False, "No legs in parlay"

    legs = parlay['legs']
    if len(legs) < 3 or len(legs) > 6:
        return False, f"Invalid leg count: {len(legs)} (need 3-6)"

    # Build lookup of valid games
    valid_games = {g['game_id']: g for g in context_data['games']}

    def ml_to_decimal(ml):
        return 1 + ml / 100 if ml > 0 else 1 + 100 / abs(ml)

    decimal_odds = 1.0
    used_games = set()

    for i, leg in enumerate(legs):
        gid = leg.get('game_id', '')
        if gid not in valid_games:
            return False, f"Leg {i+1}: game_id '{gid}' not found in today's games"
        if gid in used_games:
            return False, f"Leg {i+1}: duplicate game_id '{gid}'"
        used_games.add(gid)

        game = valid_games[gid]
        side = leg.get('side', '')
        if side == 'home':
            expected_ml = game['home_ml']
        elif side == 'away':
            expected_ml = game['away_ml']
        else:
            return False, f"Leg {i+1}: invalid side '{side}'"

        # Allow small discrepancy in odds (AI might round)
        leg_odds = leg.get('odds', 0)
        if abs(leg_odds - expected_ml) > 5:
            print(f"[Claude's Parlay] Warning: Leg {i+1} odds {leg_odds} vs actual {expected_ml}, using actual")
            leg['odds'] = expected_ml

        decimal_odds *= ml_to_decimal(leg['odds'])

    american = round((decimal_odds - 1) * 100) if decimal_odds > 2 else round(-100 / (decimal_odds - 1))

    if american < 1200:
        return False, f"Combined odds +{american} below +1200 minimum"

    # Update the parlay with verified odds
    parlay['combined_odds_american'] = american
    parlay['decimal_odds'] = round(decimal_odds, 4)
    parlay['bet_amount'] = 5
    parlay['payout'] = round(5 * decimal_odds, 2)

    return True, "Valid"


def save_parlay(parlay, date_str, dry_run=False):
    """Save Claude's Parlay to the database."""
    if dry_run:
        print(f"[DRY RUN] Would save Claude's Parlay: {len(parlay['legs'])} legs, +{parlay['combined_odds_american']}")
        return

    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row

    # Delete any existing Claude's Parlay for today
    conn.execute("DELETE FROM tracked_bets WHERE date = ? AND strategy = 'clawd_parlay'", (date_str,))

    conn.execute("""
        INSERT INTO tracked_bets (date, game_id, strategy, pick, bet_type, odds, stake, 
                                  model_prob, edge, notes, created_at)
        VALUES (?, ?, 'clawd_parlay', ?, 'PARLAY', ?, 5, ?, ?, ?, ?)
    """, (
        date_str,
        parlay['legs'][0]['game_id'],  # Primary game ID
        json.dumps([l['pick'] for l in parlay['legs']]),
        parlay['combined_odds_american'],
        parlay.get('model_prob', 0),
        0,
        json.dumps({
            'legs': parlay['legs'],
            'overall_reasoning': parlay.get('overall_reasoning', ''),
            'confidence': parlay.get('confidence', 'medium'),
            'num_legs': len(parlay['legs']),
            'decimal_odds': parlay.get('decimal_odds'),
            'payout': parlay.get('payout'),
        }),
        datetime.utcnow().isoformat()
    ))
    conn.commit()
    conn.close()
    print(f"[Claude's Parlay] Saved: {len(parlay['legs'])} legs, +{parlay['combined_odds_american']}, payout ${parlay['payout']}")


def main():
    parser = argparse.ArgumentParser(description="Claude's Parlay — AI-driven parlay builder")
    parser.add_argument('--date', '-d', help='Date (YYYY-MM-DD, default: today CST)')
    parser.add_argument('--dry-run', action='store_true', help='Preview only')
    parser.add_argument('--verbose', '-v', action='store_true')
    args = parser.parse_args()

    date_str = args.date or get_today_cst()
    print(f"[Claude's Parlay] Building for {date_str}")

    # Step 1: Gather context
    context_data = build_context(date_str)
    if not context_data or not context_data['games']:
        print("[Claude's Parlay] No games with odds available. Skipping.")
        return

    context_text = format_as_text(context_data)
    print(f"[Claude's Parlay] Found {context_data['num_games']} games with odds")

    # Step 2: Call AI
    prompt = PARLAY_PROMPT.replace('{context}', context_text)
    if args.verbose:
        print(f"[Claude's Parlay] Prompt length: {len(prompt)} chars")

    print("[Claude's Parlay] Asking the AI to build a parlay...")
    response = call_ai(prompt)

    if not response:
        print("[Claude's Parlay] No response from AI. Aborting.")
        return

    # Step 3: Parse response
    parlay = parse_parlay_response(response)
    if not parlay:
        print("[Claude's Parlay] Could not parse AI response. Aborting.")
        return

    # Step 4: Validate
    valid, msg = validate_parlay(parlay, context_data)
    if not valid:
        print(f"[Claude's Parlay] Validation failed: {msg}")
        print(f"[Claude's Parlay] Raw response:\n{response[:1000]}")
        return

    # Step 5: Display
    print(f"\n🎲 Claude's Parlay — {date_str}")
    print(f"Combined: +{parlay['combined_odds_american']} | $5 → ${parlay['payout']}")
    print(f"Confidence: {parlay.get('confidence', '?')}")
    print()
    for i, leg in enumerate(parlay['legs']):
        print(f"  Leg {i+1}: {leg['pick']} ({leg['odds']:+d}) — {leg['reasoning']}")
    print(f"\n  Thesis: {parlay.get('overall_reasoning', 'N/A')}")
    print()

    # Step 6: Save
    save_parlay(parlay, date_str, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
