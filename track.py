# Result tracking: keep score on the value finder.
# Run `python track.py` once a day. For now it does step 1: snapshot.

import sqlite3
import sys
from datetime import datetime

from tools import find_value_bets

DB_FILE = "tracking.db"


def connect():
    """Open the database file (it's created the first time) and make sure
    the table exists."""
    db = sqlite3.connect(DB_FILE)
    db.execute("""
        CREATE TABLE IF NOT EXISTS prices (
            saved_at   TEXT,
            starts_utc TEXT,
            home_team  TEXT,
            away_team  TEXT,
            team       TEXT,
            bookmaker  TEXT,
            price      REAL,
            fair_odds  REAL,
            edge_pct   REAL,
            grade      TEXT,
            result     TEXT,  -- empty until settled, then 'won' or 'lost'
            -- The same price on the same game is only saved once (first sighting).
            UNIQUE (starts_utc, home_team, team, bookmaker)
        )
    """)
    return db


def snapshot():
    """Save every price the value finder currently flags."""
    found = find_value_bets(limit=None)
    if "error" in found:
        print("Couldn't get odds:", found["error"])
        return

    db = connect()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    added = 0
    for p in found["prices_above_fair"]:
        # INSERT OR IGNORE skips rows that break the UNIQUE rule (already saved).
        cursor = db.execute(
            "INSERT OR IGNORE INTO prices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
            (now, p["starts_utc"], p["home_team"], p["away_team"], p["team"],
             p["bookmaker"], p["price"], p["fair_odds"], p["edge_pct"], p["grade"]),
        )
        added += cursor.rowcount  # 1 if it was new, 0 if it was a repeat
    db.commit()
    db.close()

    flagged = len(found["prices_above_fair"])
    print(f"Snapshot: {flagged} prices above fair right now, {added} new saved "
          f"({flagged - added} already saved earlier).")


def show():
    """Print every saved price, so you can see what's in the database."""
    db = connect()
    rows = db.execute(
        "SELECT starts_utc, home_team, away_team, team, bookmaker, price, fair_odds, edge_pct, grade, result "
        "FROM prices ORDER BY starts_utc, team"
    ).fetchall()
    db.close()

    print(f"{len(rows)} saved prices:\n")
    print(f"{'Game start (UTC)':<18} {'Price is on (vs opponent)':<36} {'Bookmaker':<12} {'Price':>6} {'Fair':>6} {'Edge':>6} Grade  Result")
    for starts, home, away, team, book, price, fair, edge, grade, result in rows:
        # Show the team with its opponent, e.g. "Bucks (away at Celtics)".
        nickname = team.split()[-1]
        if team == home:
            matchup = f"{nickname} (home vs {away.split()[-1]})"
        else:
            matchup = f"{nickname} (away at {home.split()[-1]})"
        print(f"{starts[:16]:<18} {matchup:<36} {book:<12} {price:>6.2f} {fair:>6.2f} {edge:>5.1f}% {grade:^5}  {result or '-'}")


if __name__ == "__main__":
    # `python track.py` takes a snapshot; `python track.py show` lists what's saved.
    if len(sys.argv) > 1 and sys.argv[1] == "show":
        show()
    else:
        snapshot()
