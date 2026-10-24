# The tools Claude will be able to call. Each one fetches real data
# and returns a plain Python dictionary.

import json
import os
from datetime import date, timedelta

import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("BALLDONTLIE_API_KEY")
BASE_URL = "https://api.balldontlie.io/v1"
TEAMS_FILE = "cache/teams.json"


def get_all_teams():
    """Return the list of NBA teams. Fetched once, then read from a file,
    because the free tier only allows 5 requests a minute."""
    if os.path.exists(TEAMS_FILE):
        with open(TEAMS_FILE) as f:
            return json.load(f)

    response = requests.get(f"{BASE_URL}/teams", headers={"Authorization": API_KEY})
    response.raise_for_status()
    # The list also has old teams that no longer exist. Current teams have IDs 1-30.
    teams = [t for t in response.json()["data"] if t["id"] <= 30]

    os.makedirs("cache", exist_ok=True)
    with open(TEAMS_FILE, "w") as f:
        json.dump(teams, f, indent=2)
    return teams


def find_team(name):
    """Turn a name like "celtics", "Boston" or "BOS" into a team dictionary.
    Returns None if nothing matches."""
    name = name.strip().lower()
    for team in get_all_teams():
        options = [team["full_name"], team["name"], team["city"], team["abbreviation"]]
        if name in [o.lower() for o in options]:
            return team
    return None


def fetch_finished_games(team_id, days_back=200):
    """Return a team's finished games from the last `days_back` days, oldest first."""
    start = date.today() - timedelta(days=days_back)
    response = requests.get(
        f"{BASE_URL}/games",
        headers={"Authorization": API_KEY},
        params={
            "team_ids[]": team_id,
            "start_date": start.isoformat(),
            "end_date": date.today().isoformat(),
            "per_page": 100,
        },
    )
    response.raise_for_status()
    games = [g for g in response.json()["data"] if g["status"] == "Final"]
    games.sort(key=lambda g: g["date"])
    return games


def get_recent_games(team, n=5):
    """Summarise a team's last n finished games: wins, losses,
    points scored and points allowed."""
    found = find_team(team)
    if found is None:
        return {"error": f"No NBA team found matching '{team}'."}

    games = fetch_finished_games(found["id"])[-n:]

    wins = 0
    losses = 0
    points_scored = 0
    points_allowed = 0
    results = []  # one short line per game, e.g. "2026-04-26 W 128-96 at PHI"

    for game in games:
        # 1-2. Were we home or away? That decides which score is ours.
        if game["home_team"]["id"] == found["id"]:
            us = game["home_team_score"]
            them = game["visitor_team_score"]
            opponent = game["visitor_team"]["abbreviation"]
            where = "vs"  # home game
        else:
            us = game["visitor_team_score"]
            them = game["home_team_score"]
            opponent = game["home_team"]["abbreviation"]
            where = "at"  # away game

        # 3. Win or loss (NBA games can't end in a draw).
        if us > them:
            wins += 1
            result = "W"
        else:
            losses += 1
            result = "L"

        # 4. Running totals.
        points_scored += us
        points_allowed += them

        # 5. One readable line per game, e.g. "2026-04-26 W 128-96 at PHI".
        results.append(f"{game['date']} {result} {us}-{them} {where} {opponent}")

    return {
        "team": found["full_name"],
        "games_counted": len(games),
        "wins": wins,
        "losses": losses,
        "points_scored": points_scored,
        "points_allowed": points_allowed,
        "games": results,
    }


if __name__ == "__main__":
    # Quick tests: run `python tools.py`
    for name in ["Celtics", "lakers", "DEN", "Celtcs"]:
        print(get_recent_games(name, 5))
