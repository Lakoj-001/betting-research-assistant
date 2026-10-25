# The tools Claude will be able to call. Each one fetches real data
# and returns a plain Python dictionary.

import json
import os
import time
from datetime import date

import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("BALLDONTLIE_API_KEY")
BASE_URL = "https://api.balldontlie.io/v1"
TEAMS_FILE = "cache/teams.json"


def api_get(path, params=None):
    """GET from balldontlie. If we hit the 5-requests-a-minute limit
    (status 429), wait and try again instead of crashing."""
    for attempt in range(4):
        response = requests.get(
            f"{BASE_URL}{path}", headers={"Authorization": API_KEY}, params=params, timeout=15
        )
        if response.status_code != 429:
            response.raise_for_status()
            return response.json()
        print(f"  [rate limit] waiting 20s before retrying ({attempt + 1}/4)...")
        time.sleep(20)
    raise RuntimeError("balldontlie rate limit: still blocked after 4 tries.")


def get_all_teams():
    """Return the list of NBA teams. Fetched once, then read from a file,
    because the free tier only allows 5 requests a minute."""
    if os.path.exists(TEAMS_FILE):
        with open(TEAMS_FILE) as f:
            return json.load(f)

    # The list also has old teams that no longer exist. Current teams have IDs 1-30.
    teams = [t for t in api_get("/teams")["data"] if t["id"] <= 30]

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


def current_season():
    """NBA seasons start in October and are named by their starting year,
    so October 2026 to June 2027 is season 2026."""
    today = date.today()
    return today.year if today.month >= 10 else today.year - 1


def fetch_finished_games(team_id):
    """Return a team's finished games from this season and last season, oldest first.
    Results are saved to a file for the rest of the day, so asking about the
    same team again doesn't use up the 5-requests-a-minute limit."""
    cache_file = f"cache/games_{team_id}_{date.today().isoformat()}.json"
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            return json.load(f)

    season = current_season()
    games = []
    cursor = None
    # The API gives at most 100 games per page, so keep asking for the
    # next page until there isn't one.
    while True:
        params = {
            "team_ids[]": team_id,
            "seasons[]": [season - 1, season],
            "per_page": 100,
        }
        if cursor:
            params["cursor"] = cursor
        body = api_get("/games", params)
        games += body["data"]
        cursor = body.get("meta", {}).get("next_cursor")
        if not cursor:
            break

    games = [g for g in games if g["status"] == "Final"]
    games.sort(key=lambda g: g["date"])

    os.makedirs("cache", exist_ok=True)
    with open(cache_file, "w") as f:
        json.dump(games, f)
    return games


def team_view(game, team_id):
    """Look at one game from one team's side: our score, their score, who
    the opponent was, home or away, and win or loss."""
    if game["home_team"]["id"] == team_id:
        us = game["home_team_score"]
        them = game["visitor_team_score"]
        opponent = game["visitor_team"]
        home = True
    else:
        us = game["visitor_team_score"]
        them = game["home_team_score"]
        opponent = game["home_team"]
        home = False
    return {
        "date": game["date"],
        "us": us,
        "them": them,
        "opponent": opponent,
        "home": home,
        "won": us > them,  # NBA games can't end in a draw
        "playoffs": game["postseason"],
    }


def describe(view):
    """One readable line per game, e.g. "2026-04-26 W 128-96 away at PHI (playoffs)"."""
    result = "W" if view["won"] else "L"
    where = "home vs" if view["home"] else "away at"
    line = f"{view['date']} {result} {view['us']}-{view['them']} {where} {view['opponent']['abbreviation']}"
    if view["playoffs"]:
        line += " (playoffs)"
    return line


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
    results = []

    for game in games:
        view = team_view(game, found["id"])
        if view["won"]:
            wins += 1
        else:
            losses += 1
        points_scored += view["us"]
        points_allowed += view["them"]
        results.append(describe(view))

    return {
        "team": found["full_name"],
        "games_counted": len(games),
        "wins": wins,
        "losses": losses,
        "points_scored": points_scored,
        "points_allowed": points_allowed,
        "games": results,
    }


def get_home_away_record(team, season=None):
    """A team's wins and losses at home and away for one season
    (regular season only), with average points in each."""
    found = find_team(team)
    if found is None:
        return {"error": f"No NBA team found matching '{team}'."}
    if season is None:
        season = current_season()

    totals = {
        "home": {"wins": 0, "losses": 0, "points_scored": 0, "points_allowed": 0},
        "away": {"wins": 0, "losses": 0, "points_scored": 0, "points_allowed": 0},
    }
    for game in fetch_finished_games(found["id"]):
        if game["season"] != season or game["postseason"]:
            continue
        view = team_view(game, found["id"])
        side = totals["home"] if view["home"] else totals["away"]
        side["wins" if view["won"] else "losses"] += 1
        side["points_scored"] += view["us"]
        side["points_allowed"] += view["them"]

    # Turn point totals into per-game averages, which are easier to compare.
    for side in totals.values():
        played = side["wins"] + side["losses"]
        side["games"] = played
        side["avg_scored"] = round(side.pop("points_scored") / played, 1) if played else None
        side["avg_allowed"] = round(side.pop("points_allowed") / played, 1) if played else None

    return {
        "team": found["full_name"],
        "season": f"{season}-{str(season + 1)[2:]}",
        "home": totals["home"],
        "away": totals["away"],
    }


def get_head_to_head(team_a, team_b):
    """Every game between two teams this season and last season,
    with the overall record from team_a's side."""
    a = find_team(team_a)
    b = find_team(team_b)
    if a is None:
        return {"error": f"No NBA team found matching '{team_a}'."}
    if b is None:
        return {"error": f"No NBA team found matching '{team_b}'."}
    if a["id"] == b["id"]:
        return {"error": "Those are the same team. Head-to-head needs two different teams."}

    a_wins = 0
    b_wins = 0
    results = []
    for game in fetch_finished_games(a["id"]):
        view = team_view(game, a["id"])
        if view["opponent"]["id"] != b["id"]:
            continue
        if view["won"]:
            a_wins += 1
        else:
            b_wins += 1
        results.append(describe(view))

    return {
        "team_a": a["full_name"],
        "team_b": b["full_name"],
        "games_counted": len(results),
        "team_a_wins": a_wins,
        "team_b_wins": b_wins,
        "games": results,  # written from team_a's side
    }


if __name__ == "__main__":
    # Quick tests: run `python tools.py`
    for name in ["Celtics", "lakers", "DEN", "Celtcs"]:
        print(get_recent_games(name, 5))
    print(get_home_away_record("Celtics", 2025))
    print(get_head_to_head("Celtics", "76ers"))
