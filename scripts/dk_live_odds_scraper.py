#!/usr/bin/env python3
"""
DraftKings live in-play odds scraper for NCAA Baseball.

Scrapes the DK sportsbook page for live game odds, matches them to our
games, and stores snapshots in live_odds_snapshots for WP vs market comparison.

Usage: python3 scripts/dk_live_odds_scraper.py [--dry-run]
"""
import json
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent
DB_PATH = PROJECT_DIR / "data" / "baseball.db"
DK_URL = "https://sportsbook.draftkings.com/leagues/baseball/ncaa-baseball"

sys.path.insert(0, str(PROJECT_DIR / "scripts"))


def scrape_dk_page():
    """Launch headless browser and get page text."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(DK_URL, timeout=25000)
        time.sleep(5)

        # Scroll to load all content
        for i in range(15):
            page.evaluate(f'window.scrollTo(0, {(i + 1) * 800})')
            time.sleep(0.3)
        time.sleep(2)

        text = page.evaluate('() => document.body.innerText')
        browser.close()

    return text


def fix_int(s):
    """Parse integer with unicode minus signs."""
    return int(s.replace('\u2212', '-').replace('\u2013', '-'))


def parse_odds_from_text(text):
    """
    Parse DK page text into list of game dicts.
    
    DK format for live games:
        AwayTeam
        AwayScore          <- integer = live game
        AT
        HomeTeam
        HomeScore
        away_spread  away_spread_odds  O  total  over_odds  away_ml
        home_spread  home_spread_odds  U  total  under_odds home_ml
        InningText         <- e.g. "7th", "4th"
        More Bets

    DK format for scheduled games:
        AwayTeam
        AT
        HomeTeam
        away_spread  away_spread_odds  O  total  over_odds  away_ml
        home_spread  home_spread_odds  U  total  under_odds home_ml
        Today HH:MM AM/PM
        More Bets
    """
    games = []
    lines = text.split('\n')
    n = len(lines)

    i = 0
    while i < n:
        line = lines[i].strip()

        # Look for "AT" marker (the separator between away and home)
        if line != 'AT':
            i += 1
            continue

        # Found "AT" — look backward for away team (and possibly score)
        at_idx = i

        # Away team is 1 or 2 lines before AT
        # If line before AT is a number, it's a live score
        away_score = None
        if at_idx >= 2:
            maybe_score = lines[at_idx - 1].strip()
            try:
                away_score = int(maybe_score)
                away_team = lines[at_idx - 2].strip()
            except ValueError:
                away_team = lines[at_idx - 1].strip()

        elif at_idx >= 1:
            away_team = lines[at_idx - 1].strip()
        else:
            i += 1
            continue

        # Home team is right after AT
        if at_idx + 1 >= n:
            i += 1
            continue
        home_team = lines[at_idx + 1].strip()

        # Check for home score (next line after home team)
        home_score = None
        odds_start = at_idx + 2
        if at_idx + 2 < n:
            maybe_home_score = lines[at_idx + 2].strip()
            try:
                home_score = int(maybe_home_score)
                odds_start = at_idx + 3
            except ValueError:
                pass

        is_live = away_score is not None and home_score is not None

        # Skip non-team lines (navigation items, headers, etc.)
        skip_words = {'POPULAR', 'SPORT TEAMS', 'A-Z SPORTS', 'GAME LINES', 
                       'SPORTSBOOK', 'CASINO', 'HOME', 'MORE', 'Run Line',
                       'Total', 'Moneyline', 'Today', 'MLB', 'BASEBALL'}
        if away_team in skip_words or home_team in skip_words:
            i += 1
            continue

        # Parse odds lines after the matchup
        # Format: spread, spread_odds, O, total, over_odds, away_ml,
        #         spread, spread_odds, U, total, under_odds, home_ml
        away_spread = None
        away_spread_odds = None
        home_spread = None
        home_spread_odds = None
        over_under = None
        over_odds = None
        under_odds = None
        away_ml = None
        home_ml = None
        inning_text = None

        odds_tokens = []
        j = odds_start
        while j < min(odds_start + 20, n):
            val = lines[j].strip()
            if val == 'More Bets':
                # Check line before "More Bets" for inning or time
                if odds_tokens:
                    last = odds_tokens[-1]
                    if isinstance(last, str):
                        inning_text = last
                        odds_tokens.pop()
                break
            if val in ('O', 'U'):
                odds_tokens.append(val)
            else:
                # Try to parse as number
                try:
                    odds_tokens.append(fix_int(val))
                except ValueError:
                    # Could be spread like "+1.5" or time like "Today 7:00 PM"
                    spread_m = re.match(r'^([+-]?\d+\.5)$', val.replace('\u2212', '-'))
                    if spread_m:
                        odds_tokens.append(float(spread_m.group(1)))
                    elif re.match(r'^\d+\.5$', val):
                        odds_tokens.append(float(val))
                    else:
                        odds_tokens.append(val)
            j += 1

        # Parse the odds tokens
        # Expected pattern for each row:
        # [spread, spread_odds, 'O', total, over_odds, away_ml,
        #  spread, spread_odds, 'U', total, under_odds, home_ml]
        # Or with inning/time at end

        # Find O and U markers to split
        o_idx = None
        u_idx = None
        for k, tok in enumerate(odds_tokens):
            if tok == 'O' and o_idx is None:
                o_idx = k
            elif tok == 'U' and u_idx is None:
                u_idx = k

        if o_idx is not None and u_idx is not None:
            # Away line: tokens before O = [spread, spread_odds]
            pre_o = [t for t in odds_tokens[:o_idx] if isinstance(t, (int, float))]
            if len(pre_o) >= 2:
                away_spread = pre_o[0]
                away_spread_odds = pre_o[1]
            elif len(pre_o) == 1:
                away_spread = pre_o[0]

            # Between O and U: [total, over_odds, away_ml, spread, spread_odds]
            between = [t for t in odds_tokens[o_idx+1:u_idx] if isinstance(t, (int, float))]
            if len(between) >= 3:
                over_under = between[0]
                over_odds = between[1]
                away_ml = between[2]
                if len(between) >= 5:
                    home_spread = between[3]
                    home_spread_odds = between[4]

            # After U: [total, under_odds, home_ml, maybe inning/time string]
            after_u = [t for t in odds_tokens[u_idx+1:] if isinstance(t, (int, float))]
            if len(after_u) >= 3:
                # total again (skip), under_odds, home_ml
                under_odds = after_u[1]
                home_ml = after_u[2]
            elif len(after_u) >= 2:
                under_odds = after_u[0]
                home_ml = after_u[1]

            # Check for inning/time in remaining string tokens
            for tok in odds_tokens[u_idx+1:]:
                if isinstance(tok, str) and tok not in ('O', 'U'):
                    if re.match(r'^\d+(st|nd|rd|th)$', tok):
                        inning_text = tok
                        is_live = True
                    elif 'Today' in tok or 'Tomorrow' in tok:
                        inning_text = tok

        game = {
            "away": away_team,
            "home": home_team,
            "is_live": is_live,
            "inning": inning_text,
            "away_score": away_score,
            "home_score": home_score,
            "away_ml": away_ml if isinstance(away_ml, int) else None,
            "home_ml": home_ml if isinstance(home_ml, int) else None,
            "away_spread": away_spread if isinstance(away_spread, float) else None,
            "away_spread_odds": away_spread_odds if isinstance(away_spread_odds, int) else None,
            "home_spread": home_spread if isinstance(home_spread, float) else None,
            "home_spread_odds": home_spread_odds if isinstance(home_spread_odds, int) else None,
            "over_under": over_under if isinstance(over_under, (int, float)) else None,
            "over_odds": over_odds if isinstance(over_odds, int) else None,
            "under_odds": under_odds if isinstance(under_odds, int) else None,
        }

        if game["away_ml"] is not None or game["home_ml"] is not None:
            games.append(game)

        i = j + 1  # Skip past "More Bets"

    return games


def resolve_game_id(away_name, home_name, conn, date_str):
    """Try to match DK team names to our game IDs."""
    from team_resolver import TeamResolver
    resolver = TeamResolver()

    away_id = resolver.resolve(away_name)
    home_id = resolver.resolve(home_name)

    if away_id and home_id:
        row = conn.execute(
            "SELECT id FROM games WHERE date = ? AND "
            "((away_team_id = ? AND home_team_id = ?) OR (away_team_id = ? AND home_team_id = ?))",
            (date_str, away_id, home_id, home_id, away_id)
        ).fetchone()
        if row:
            return row[0] if isinstance(row, tuple) else row['id']

    # Fallback: single team match on in-progress games
    known_id = away_id or home_id
    if known_id:
        rows = conn.execute(
            "SELECT id FROM games WHERE date = ? AND (home_team_id = ? OR away_team_id = ?) "
            "AND status IN ('in-progress', 'scheduled')",
            (date_str, known_id, known_id)
        ).fetchall()
        if len(rows) == 1:
            return rows[0][0] if isinstance(rows[0], tuple) else rows[0]['id']

    return None


def store_snapshots(games, conn, date_str, dry_run=False):
    """Store live odds snapshots, enriched with current game state from our DB."""
    stored = 0

    for g in games:
        if not g.get("is_live"):
            continue

        game_id = resolve_game_id(g["away"], g["home"], conn, date_str)
        if not game_id:
            print(f"  ✗ Could not match: {g['away']} @ {g['home']}", file=sys.stderr)
            continue

        # Get current game state from our DB
        row = conn.execute(
            "SELECT home_score, away_score, inning_text, situation_json FROM games WHERE id = ?",
            (game_id,)
        ).fetchone()

        db_home_score = row['home_score'] if row else g.get("home_score")
        db_away_score = row['away_score'] if row else g.get("away_score")
        db_inning = row['inning_text'] if row else g.get("inning")

        # Calculate live WP from our model
        home_wp = calculate_live_wp(game_id, conn)

        marker = "LIVE" if g["is_live"] else "    "
        info = (f"  {marker} {game_id}: "
                f"ML {g.get('away_ml','?')}/{g.get('home_ml','?')}, "
                f"spread {g.get('away_spread','?')}, O/U {g.get('over_under','?')}, "
                f"score {db_away_score}-{db_home_score} {db_inning}, WP={home_wp}")

        if dry_run:
            print(f"  [DRY] {info}")
            continue

        conn.execute("""
            INSERT INTO live_odds_snapshots 
            (game_id, inning, home_score, away_score, home_ml, away_ml,
             home_spread, home_spread_odds, away_spread_odds,
             over_under, over_odds, under_odds, home_wp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            game_id,
            db_inning or g.get("inning"),
            db_home_score,
            db_away_score,
            g.get("home_ml"),
            g.get("away_ml"),
            g.get("home_spread"),
            g.get("home_spread_odds"),
            g.get("away_spread_odds"),
            g.get("over_under"),
            g.get("over_odds"),
            g.get("under_odds"),
            home_wp,
        ))
        stored += 1
        print(info)

    conn.commit()
    return stored


def main():
    dry_run = "--dry-run" in sys.argv

    from datetime import date
    today = date.today().isoformat()

    print(f"DK Live Odds Scraper — {today}")
    print("Launching headless browser...")

    text = scrape_dk_page()
    print(f"Page text: {len(text)} chars")

    games = parse_odds_from_text(text)
    live_games = [g for g in games if g.get("is_live")]
    sched_games = [g for g in games if not g.get("is_live")]

    print(f"Parsed: {len(games)} games ({len(live_games)} live, {len(sched_games)} scheduled)")

    for g in games:
        marker = "🔴" if g["is_live"] else "  "
        score = f"{g.get('away_score','')}-{g.get('home_score','')}" if g["is_live"] else ""
        print(f"  {marker} {g['away']} @ {g['home']} {score} "
              f"ML: {g.get('away_ml','?')}/{g.get('home_ml','?')} "
              f"O/U: {g.get('over_under','?')} "
              f"[{g.get('inning','')}]")

    if not live_games:
        print("\nNo live games with odds to store.")
        return

    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    stored = store_snapshots(live_games, conn, today, dry_run=dry_run)
    conn.close()

    print(f"\nStored {stored} live odds snapshots.")


if __name__ == "__main__":
    main()


def calculate_live_wp(game_id, conn):
    """Calculate live win probability for a game using our WP model."""
    try:
        sys.path.insert(0, str(PROJECT_DIR))
        from models.win_probability import WinProbabilityModel

        row = conn.execute(
            "SELECT home_score, away_score, situation_json, "
            "home_team_id, away_team_id FROM games WHERE id = ?",
            (game_id,)
        ).fetchone()
        if not row or not row['situation_json']:
            return None

        sit = json.loads(row['situation_json']) if isinstance(row['situation_json'], str) else row['situation_json']

        home_score = row['home_score'] or 0
        away_score = row['away_score'] or 0
        inning = sit.get('sb_inning') or sit.get('inning', 1)
        inning_half = sit.get('sb_inning_half', 'top')
        outs = sit.get('sb_outs', 0)
        on_first = sit.get('sb_on_first', False)
        on_second = sit.get('sb_on_second', False)
        on_third = sit.get('sb_on_third', False)

        wp = WinProbabilityModel()
        prob = wp.calculate(
            home_score=home_score,
            away_score=away_score,
            inning=inning,
            inning_half=inning_half,
            outs=outs,
            on_first=on_first,
            on_second=on_second,
            on_third=on_third,
            home_team_id=row['home_team_id'],
            away_team_id=row['away_team_id'],
        )
        return prob
    except Exception as e:
        print(f"  WP calc error for {game_id}: {e}", file=sys.stderr)
        return None
