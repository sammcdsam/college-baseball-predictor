#!/usr/bin/env python3
"""
Build context data for Claude's Parlay AI session.

Gathers all available game data for today (or specified date) and outputs
a formatted text block that can be fed to an AI session for parlay construction.

Usage:
    python3 scripts/build_clawd_parlay_context.py              # Today
    python3 scripts/build_clawd_parlay_context.py --date 2026-03-07
    python3 scripts/build_clawd_parlay_context.py --json       # Output as JSON
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent
DB_PATH = PROJECT_DIR / 'data' / 'baseball.db'


def get_db():
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def get_today_cst():
    utc_now = datetime.now(timezone.utc)
    ct_offset = timedelta(hours=-5) if 3 <= utc_now.month <= 10 else timedelta(hours=-6)
    return (utc_now + ct_offset).strftime('%Y-%m-%d')


def build_context(date_str=None):
    if date_str is None:
        date_str = get_today_cst()

    db = get_db()

    # Get all games with odds
    games = db.execute("""
        SELECT g.id, g.date, g.time, g.status,
               g.home_team_id, g.away_team_id,
               h.name as home_name, a.name as away_name,
               h.conference as home_conf, a.conference as away_conf,
               bl.home_ml, bl.away_ml, bl.over_under, bl.home_spread, bl.away_spread,
               mp.predicted_home_prob as meta_prob
        FROM games g
        JOIN teams h ON g.home_team_id = h.id
        JOIN teams a ON g.away_team_id = a.id
        LEFT JOIN betting_lines bl ON g.id = bl.game_id
        LEFT JOIN model_predictions mp ON g.id = mp.game_id AND mp.model_name = 'meta_ensemble'
        WHERE g.date = ? AND g.status = 'scheduled'
        AND bl.home_ml IS NOT NULL
        ORDER BY g.time, g.id
    """, (date_str,)).fetchall()

    if not games:
        return None

    # Get Elo ratings
    elo = {}
    for row in db.execute("SELECT team_id, rating, games_played FROM elo_ratings"):
        elo[row['team_id']] = {'rating': round(row['rating']), 'gp': row['games_played']}

    # Get team records (W-L)
    records = {}
    for row in db.execute("""
        SELECT t.id,
            SUM(CASE WHEN g.winner_id = t.id THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN g.status = 'final' AND g.winner_id IS NOT NULL AND g.winner_id != t.id THEN 1 ELSE 0 END) as losses
        FROM teams t
        JOIN games g ON (g.home_team_id = t.id OR g.away_team_id = t.id)
        WHERE g.status = 'final'
        GROUP BY t.id
    """):
        records[row['id']] = f"{row['wins']}-{row['losses']}"

    # Get recent form (last 5 games)
    recent_form = {}
    for row in db.execute("""
        SELECT t.id,
            GROUP_CONCAT(
                CASE WHEN g.winner_id = t.id THEN 'W' ELSE 'L' END, ''
            ) as form
        FROM teams t
        JOIN (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY CASE WHEN home_team_id <= away_team_id THEN home_team_id ELSE away_team_id END ||
                             CASE WHEN home_team_id <= away_team_id THEN away_team_id ELSE home_team_id END
                ORDER BY date DESC
            ) as rn
            FROM games WHERE status = 'final'
        ) g ON (g.home_team_id = t.id OR g.away_team_id = t.id)
        WHERE g.status = 'final'
        GROUP BY t.id
    """):
        form = row['form'] or ''
        recent_form[row['id']] = form[:5]  # Last 5

    # Get batting quality
    batting = {}
    for row in db.execute("SELECT team_id, lineup_avg, lineup_ops, lineup_woba, lineup_k_pct, lineup_bb_pct, hr_per_game FROM team_batting_quality"):
        batting[row['team_id']] = {
            'avg': row['lineup_avg'], 'ops': row['lineup_ops'], 'woba': row['lineup_woba'],
            'k_pct': row['lineup_k_pct'], 'bb_pct': row['lineup_bb_pct'], 'hr_pg': row['hr_per_game']
        }

    # Get pitching quality
    pitching = {}
    for row in db.execute("SELECT team_id, rotation_era, rotation_whip, rotation_k_per_9, bullpen_era, bullpen_whip FROM team_pitching_quality"):
        pitching[row['team_id']] = {
            'rot_era': row['rotation_era'], 'rot_whip': row['rotation_whip'],
            'rot_k9': row['rotation_k_per_9'], 'pen_era': row['bullpen_era'], 'pen_whip': row['bullpen_whip']
        }

    # Get pitching matchups (starters) with individual pitcher stats
    starters = {}
    for row in db.execute("""
        SELECT pm.game_id, pm.home_starter_name, pm.away_starter_name,
               pm.home_starter_id, pm.away_starter_id,
               hp.era as h_era, hp.whip as h_whip, hp.k_per_9 as h_k9,
               hp.innings_pitched as h_ip, hp.wins as h_w, hp.losses as h_l,
               hp.fip as h_fip, hp.team_id as h_pitcher_team,
               ap.era as a_era, ap.whip as a_whip, ap.k_per_9 as a_k9,
               ap.innings_pitched as a_ip, ap.wins as a_w, ap.losses as a_l,
               ap.fip as a_fip, ap.team_id as a_pitcher_team
        FROM pitching_matchups pm
        LEFT JOIN player_stats hp ON pm.home_starter_id = hp.id
        LEFT JOIN player_stats ap ON pm.away_starter_id = ap.id
        WHERE pm.game_id IN (
            SELECT id FROM games WHERE date = ? AND status = 'scheduled'
        )
    """, (date_str,)):
        starters[row['game_id']] = {
            'home_name': row['home_starter_name'],
            'away_name': row['away_starter_name'],
            'home_pitcher_team': row['h_pitcher_team'],
            'away_pitcher_team': row['a_pitcher_team'],
            'home_stats': {
                'era': row['h_era'], 'whip': row['h_whip'], 'k9': row['h_k9'],
                'ip': row['h_ip'], 'w': row['h_w'], 'l': row['h_l'], 'fip': row['h_fip']
            } if row['home_starter_name'] else None,
            'away_stats': {
                'era': row['a_era'], 'whip': row['a_whip'], 'k9': row['a_k9'],
                'ip': row['a_ip'], 'w': row['a_w'], 'l': row['a_l'], 'fip': row['a_fip']
            } if row['away_starter_name'] else None,
        }

    # Get weather
    weather = {}
    for row in db.execute("""
        SELECT game_id, temp_f, wind_speed_mph, wind_direction_deg, precip_prob_pct, is_dome
        FROM game_weather WHERE game_id IN (
            SELECT id FROM games WHERE date = ? AND status = 'scheduled'
        )
    """, (date_str,)):
        weather[row['game_id']] = {
            'temp': row['temp_f'], 'wind': row['wind_speed_mph'],
            'wind_dir': row['wind_direction_deg'], 'precip': row['precip_prob_pct'],
            'dome': bool(row['is_dome'])
        }

    # Get individual model predictions for richer context
    model_preds = {}
    for row in db.execute("""
        SELECT game_id, model_name, predicted_home_prob
        FROM model_predictions
        WHERE game_id IN (SELECT id FROM games WHERE date = ? AND status = 'scheduled')
        AND model_name IN ('elo', 'pear', 'quality', 'pitching_v3', 'nn_slim', 'meta_ensemble')
    """, (date_str,)):
        if row['game_id'] not in model_preds:
            model_preds[row['game_id']] = {}
        model_preds[row['game_id']][row['model_name']] = round(row['predicted_home_prob'], 3)

    # Build game entries
    game_entries = []
    for g in games:
        gid = g['id']
        home_id = g['home_team_id']
        away_id = g['away_team_id']

        entry = {
            'game_id': gid,
            'home': g['home_name'],
            'away': g['away_name'],
            'home_conf': g['home_conf'],
            'away_conf': g['away_conf'],
            'time': g['time'] or 'TBD',
            'home_ml': g['home_ml'],
            'away_ml': g['away_ml'],
            'over_under': g['over_under'],
            'meta_prob_home': round(g['meta_prob'], 3) if g['meta_prob'] else None,
            'home_record': records.get(home_id, '?'),
            'away_record': records.get(away_id, '?'),
            'home_elo': elo.get(home_id, {}).get('rating'),
            'away_elo': elo.get(away_id, {}).get('rating'),
            'home_form': recent_form.get(home_id, '?'),
            'away_form': recent_form.get(away_id, '?'),
            'starters': starters.get(gid),
            'weather': weather.get(gid),
            'home_batting': batting.get(home_id),
            'away_batting': batting.get(away_id),
            'home_pitching': pitching.get(home_id),
            'away_pitching': pitching.get(away_id),
            'model_predictions': model_preds.get(gid, {}),
        }
        game_entries.append(entry)

    db.close()

    return {
        'date': date_str,
        'num_games': len(game_entries),
        'games': game_entries
    }


def format_as_text(data):
    """Format context data as readable text for the AI session."""
    if not data:
        return "No games with odds available today."

    lines = [f"# Available Games for {data['date']} ({data['num_games']} games with odds)\n"]

    for g in data['games']:
        lines.append(f"## {g['away']} ({g['away_record']}) @ {g['home']} ({g['home_record']})")
        lines.append(f"   Time: {g['time']} | {g['away_conf']} vs {g['home_conf']}")
        lines.append(f"   Moneylines: {g['away']} {g['away_ml']:+d} | {g['home']} {g['home_ml']:+d}")
        if g['over_under']:
            lines.append(f"   Total: O/U {g['over_under']}")

        # Model predictions
        meta = g.get('meta_prob_home')
        if meta:
            home_pct = meta * 100
            away_pct = (1 - meta) * 100
            lines.append(f"   Meta Model: {g['home']} {home_pct:.1f}% | {g['away']} {away_pct:.1f}%")

        models = g.get('model_predictions', {})
        if models:
            model_parts = []
            for name in ['elo', 'pear', 'quality', 'pitching_v3', 'nn_slim']:
                if name in models:
                    model_parts.append(f"{name}={models[name]*100:.0f}%H")
            if model_parts:
                lines.append(f"   Individual Models (home%): {', '.join(model_parts)}")

        # Elo
        if g['home_elo'] and g['away_elo']:
            lines.append(f"   Elo: {g['home']} {g['home_elo']} | {g['away']} {g['away_elo']} (Δ{g['home_elo']-g['away_elo']:+d})")

        # Recent form
        lines.append(f"   Recent Form: {g['home']} [{g['home_form']}] | {g['away']} [{g['away_form']}]")

        # Starters (with individual stats)
        if g.get('starters'):
            s = g['starters']
            away_sp = s.get('away_name') or 'Unknown'
            home_sp = s.get('home_name') or 'Unknown'
            lines.append(f"   Probable Starters:")
            lines.append(f"     {g['away']} SP: {away_sp}")
            if s.get('away_stats') and s['away_stats'].get('era') is not None:
                ast = s['away_stats']
                parts = []
                if ast.get('era') is not None: parts.append(f"ERA {ast['era']:.2f}")
                if ast.get('whip') is not None: parts.append(f"WHIP {ast['whip']:.2f}")
                if ast.get('k9') is not None: parts.append(f"K/9 {ast['k9']:.1f}")
                if ast.get('ip') is not None: parts.append(f"IP {ast['ip']:.1f}")
                if ast.get('w') is not None and ast.get('l') is not None: parts.append(f"{ast['w']}-{ast['l']}")
                if ast.get('fip') is not None and ast['fip']: parts.append(f"FIP {ast['fip']:.2f}")
                if parts:
                    lines.append(f"       Stats: {' | '.join(parts)}")
            lines.append(f"     {g['home']} SP: {home_sp}")
            if s.get('home_stats') and s['home_stats'].get('era') is not None:
                hst = s['home_stats']
                parts = []
                if hst.get('era') is not None: parts.append(f"ERA {hst['era']:.2f}")
                if hst.get('whip') is not None: parts.append(f"WHIP {hst['whip']:.2f}")
                if hst.get('k9') is not None: parts.append(f"K/9 {hst['k9']:.1f}")
                if hst.get('ip') is not None: parts.append(f"IP {hst['ip']:.1f}")
                if hst.get('w') is not None and hst.get('l') is not None: parts.append(f"{hst['w']}-{hst['l']}")
                if hst.get('fip') is not None and hst['fip']: parts.append(f"FIP {hst['fip']:.2f}")
                if parts:
                    lines.append(f"       Stats: {' | '.join(parts)}")

        # Batting
        for side, key in [('home', g['home']), ('away', g['away'])]:
            bat = g.get(f'{side}_batting')
            if bat and bat.get('ops'):
                lines.append(f"   {key} Batting: AVG {bat['avg']:.3f} | OPS {bat['ops']:.3f} | wOBA {bat['woba']:.3f} | K% {bat['k_pct']:.1f} | BB% {bat['bb_pct']:.1f}")

        # Pitching
        for side, key in [('home', g['home']), ('away', g['away'])]:
            pit = g.get(f'{side}_pitching')
            if pit and pit.get('rot_era'):
                lines.append(f"   {key} Pitching: Rot ERA {pit['rot_era']:.2f} / WHIP {pit['rot_whip']:.2f} | Pen ERA {pit['pen_era']:.2f} / WHIP {pit['pen_whip']:.2f}")

        # Weather
        if g.get('weather'):
            w = g['weather']
            parts = []
            if w.get('dome'):
                parts.append("🏟️ Dome")
            else:
                if w.get('temp'): parts.append(f"{w['temp']:.0f}°F")
                if w.get('wind'): parts.append(f"Wind {w['wind']:.0f}mph ({w.get('wind_dir', '?')}°)")
                if w.get('precip'): parts.append(f"Precip {w['precip']:.0f}%")
            if parts:
                lines.append(f"   Weather: {' | '.join(parts)}")

        lines.append("")

    return '\n'.join(lines)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Build context for Claude's Parlay")
    parser.add_argument('--date', '-d', help='Date (YYYY-MM-DD, default: today CST)')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    args = parser.parse_args()

    data = build_context(args.date)

    if args.json:
        print(json.dumps(data, indent=2, default=str))
    else:
        print(format_as_text(data))
