# Result tracking: keep score on the value finder.
# Run `python track.py` once a day: it settles finished games, then saves new prices.

import sqlite3
import sys
from datetime import datetime, timedelta, timezone

from tools import api_get, find_value_bets, get_all_teams

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


def team_from_odds_name(full_name):
    """The Odds API and balldontlie name teams differently ("Los Angeles Clippers"
    vs "LA Clippers"), so match on the short name they share ("Clippers")."""
    for team in get_all_teams():
        if team["name"] in full_name:
            return team
    return None


def settle():
    """Fill in 'won' or 'lost' for saved prices whose game has finished."""
    db = connect()
    # A game that started more than 4 hours ago should be over (they take ~2.5 hours).
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M:%SZ")
    # DISTINCT = one row per game, however many bookmakers we saved for it.
    games = db.execute(
        "SELECT DISTINCT starts_utc, home_team, away_team FROM prices "
        "WHERE result IS NULL AND starts_utc < ?",
        (cutoff,),
    ).fetchall()

    settled = 0
    for starts_utc, home_name, away_name in games:
        home = team_from_odds_name(home_name)
        if home is None:
            print(f"  Couldn't match '{home_name}' to a balldontlie team, skipping.")
            continue

        # Ask balldontlie for the home team's games around that date. The US date can
        # be a day behind the UTC date, so look at both days.
        start = datetime.fromisoformat(starts_utc.replace("Z", "+00:00"))
        found = api_get("/games", {
            "team_ids[]": home["id"],
            "start_date": (start - timedelta(days=1)).date().isoformat(),
            "end_date": start.date().isoformat(),
            "per_page": 10,
        })["data"]

        # Pick the home game that started within 6 hours of the time we saved.
        match = None
        for g in found:
            if g["home_team"]["id"] != home["id"] or not g.get("datetime"):
                continue
            tip_off = datetime.fromisoformat(g["datetime"].replace("Z", "+00:00"))
            if abs(tip_off - start) < timedelta(hours=6):
                match = g
        if match is None or match["status"] != "Final":
            continue  # not found, not finished or postponed: try again next run

        winner = home_name if match["home_team_score"] > match["visitor_team_score"] else away_name
        # Update every saved price on this game at once: rows on the winner 'won', the rest 'lost'.
        cursor = db.execute(
            "UPDATE prices SET result = CASE WHEN team = ? THEN 'won' ELSE 'lost' END "
            "WHERE starts_utc = ? AND home_team = ? AND result IS NULL",
            (winner, starts_utc, home_name),
        )
        settled += cursor.rowcount
        print(f"  {away_name} {match['visitor_team_score']} at {home_name} "
              f"{match['home_team_score']}: {cursor.rowcount} prices settled")

    db.commit()
    db.close()
    print(f"Settle: {len(games)} finished games to check, {settled} prices settled.")


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
    # `python track.py` settles finished games, then takes a snapshot.
    # `python track.py show` lists what's saved.
    if len(sys.argv) > 1 and sys.argv[1] == "show":
        show()
    else:
        settle()
        snapshot()
