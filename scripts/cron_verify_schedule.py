#!/usr/bin/env python3
"""Simple verification output for schedule cron job."""
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / 'data' / 'baseball.db'

db = sqlite3.connect(str(DB_PATH))
today = datetime.now().strftime('%Y-%m-%d')
yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

for i in range(3):
    d = (datetime.now() + timedelta(days=i)).strftime('%Y-%m-%d')
    games = db.execute('SELECT COUNT(*) FROM games WHERE date=?', (d,)).fetchone()[0]
    print(f'{d}: {games} games')

final_y = db.execute('SELECT COUNT(*) FROM games WHERE date=? AND status="final"', (yesterday,)).fetchone()[0]
total_y = db.execute('SELECT COUNT(*) FROM games WHERE date=?', (yesterday,)).fetchone()[0]
left_y = db.execute('SELECT COUNT(*) FROM games WHERE date=? AND status NOT IN ("final","postponed","canceled")', (yesterday,)).fetchone()[0]
print(f'Yesterday final: {final_y}/{total_y} | unresolved: {left_y}')
