#!/bin/bash
# 1/6 Schedule + Finalize + Reconcile — 7:00 AM CT
# Merged from: 01_schedule_sync + 00_finalize_games + 01b_late_scores
set -euo pipefail
cd /home/sam/college-baseball-predictor
LOG="logs/cron/$(date +%Y-%m-%d)_01_schedule_and_finalize.log"
YESTERDAY=$(date -d yesterday +%Y-%m-%d)

echo "=== Schedule+Finalize $(date) ===" >> "$LOG"

echo "--- Step 1: Schedule Sync (today+next few days) ---" >> "$LOG"
python3 -u scripts/d1b_team_sync.py --delay 0.3 >> "$LOG" 2>&1

echo "--- Step 2: Finalize Yesterday ---" >> "$LOG"
python3 -u scripts/finalize_games.py --date "$YESTERDAY" --verbose >> "$LOG" 2>&1

echo "--- Step 3: Reconcile Yesterday's Orphans ---" >> "$LOG"
python3 -u scripts/reconcile_schedule.py --date "$YESTERDAY" >> "$LOG" 2>&1 || true

echo "--- Step 4: W-L Verification ---" >> "$LOG"
python3 -u scripts/verify_wl_records.py >> "$LOG" 2>&1 || true

echo "--- Verification ---" >> "$LOG"
python3 scripts/cron_verify_schedule.py >> "$LOG" 2>&1

echo "=== Done $(date) ===" >> "$LOG"
