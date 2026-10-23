# Script 2: fetch the Celtics' last 5 finished games and print the raw JSON.

import json
import os
from datetime import date, timedelta

import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("BALLDONTLIE_API_KEY")

CELTICS_ID = 2  # balldontlie's ID for the Boston Celtics

# The season only just started, so look back 200 days to also catch
# the end of last season. That way there are always at least 5 games.
start = date.today() - timedelta(days=200)

response = requests.get(
    "https://api.balldontlie.io/v1/games",
    headers={"Authorization": API_KEY},
    params={
        "team_ids[]": CELTICS_ID,
        "start_date": start.isoformat(),
        "end_date": date.today().isoformat(),
        "per_page": 100,
    },
)
response.raise_for_status()  # stop with an error if the request failed

games = response.json()["data"]

# Keep only games that have finished, then sort oldest to newest by date.
finished = [g for g in games if g["status"] == "Final"]
finished.sort(key=lambda g: g["date"])
last_5 = finished[-5:]

print(json.dumps(last_5, indent=2))
