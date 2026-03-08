#!/bin/bash
# DK Live Odds scraper — runs every 5 minutes during game hours
# Captures live in-play odds and our WP model for comparison

cd /home/sam/college-baseball-predictor

# Only run during game hours (10 AM - 11 PM CT)
HOUR=$(date +%H)
if [ "$HOUR" -lt 10 ] || [ "$HOUR" -ge 23 ]; then
    exit 0
fi

# Check if any games are currently in-progress
LIVE_COUNT=$(sqlite3 data/baseball.db "SELECT COUNT(*) FROM games WHERE date = date('now') AND status = 'in-progress';")
if [ "$LIVE_COUNT" -eq 0 ]; then
    exit 0
fi

python3 scripts/dk_live_odds_scraper.py >> logs/cron/$(date +%Y-%m-%d)_dk_live_odds.log 2>&1
