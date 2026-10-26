# The agent loop: chat with Claude in the terminal. Claude can ask for
# one of our tools, our Python runs it, and the result goes back to Claude.

import json
from datetime import date

import anthropic
import requests
from dotenv import load_dotenv

from tools import find_value_bets, get_head_to_head, get_home_away_record, get_odds, get_recent_games

load_dotenv()
MODEL = "claude-haiku-5-5"  # cheapest model while testing

HELP_LINE = (
    "18+ only. Gambling Help Online: gamblinghelponline.org.au or 1800 858 858 (24/7, free). "
    "Self-exclude from all Australian bookmakers: betstop.gov.au."
)

SYSTEM_PROMPT = f"""You are an NBA odds and stats research assistant for Australian users. Today is {date.today().isoformat()}. Times are Sydney time.

You explain team form, head-to-head history, what bookmaker odds imply, and where a bookmaker's price is above the market's fair price (using the find_value_bets tool).

How to talk about prices:
- Describe prices; never tell the user what to do. Say "Neds' 9.25 on the Clippers is above the market's fair odds of 8.01 (edge +15.5%, grade C)", never "bet the Clippers", "take this", "lock", or "you should".
- Never suggest how much to stake, never build parlays or multis, and never promise or imply profit. Edge is a long-run average over many similar bets, not a prediction for one game.
- When you show a price above fair, always say: the grade and what lowered it, that odds may have moved since they were fetched, and that the fair price is only the market's view and can be wrong (especially for longshots).
- If asked "who should I bet on?" or "how much should I bet?", say plainly that you don't make picks or stake suggestions, then offer form, odds and any prices above fair as research.
- If the user mentions chasing losses, betting more than they can afford, or feeling out of control, stop the analysis and point them to the support services below.

Explaining:
- Many users are new to betting. When you use a term like implied chance, margin, fair odds, edge, grade or longshot, explain it in plain words the first time, using the numbers in your answer (e.g. "odds of 7.00 imply 1 / 7.00 = 14.3%").
- If someone asks what a term means, explain it simply with a small worked example. The page also has a "New to odds?" glossary they can open.

Data rules:
- Use the tools for every number. Never guess or use your own memory for scores, records or odds.
- Say where each number came from: game results come from balldontlie; odds come from The Odds API, with the bookmaker name and the time the odds were fetched.
- If data is missing or a tool returns an error, say so plainly. Don't fill the gap.
- Point out when games are from last season or the playoffs, since they may not reflect current form.
- Whenever you mention odds, prices or betting, end with this line exactly: "{HELP_LINE}"
"""

# 1. Describe the tool to Claude. Claude only ever sees this description,
#    never the Python code itself.
TOOLS = [
    {
        "name": "get_recent_games",
        "description": (
            "Get an NBA team's last n finished games: wins, losses, points scored, "
            "points allowed, and one line per game (date, W/L, our score first, "
            "'home vs' or 'away at', opponent). Can include last season's games if "
            "the new season has only just started."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "team": {
                    "type": "string",
                    "description": "Team name, city or abbreviation, e.g. 'Celtics', 'Boston' or 'BOS'.",
                },
                "n": {
                    "type": "integer",
                    "description": "How many recent games to include. Defaults to 5.",
                },
            },
            "required": ["team"],
        },
    },
    {
        "name": "get_home_away_record",
        "description": (
            "Get an NBA team's regular-season wins and losses at home and away for "
            "one season, with average points scored and allowed in each."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "team": {
                    "type": "string",
                    "description": "Team name, city or abbreviation, e.g. 'Celtics'.",
                },
                "season": {
                    "type": "integer",
                    "description": (
                        "Starting year of the season, e.g. 2025 for 2025-26. "
                        "Defaults to the current season. Only this season and last "
                        "season are available."
                    ),
                },
            },
            "required": ["team"],
        },
    },
    {
        "name": "get_head_to_head",
        "description": (
            "Get every game between two NBA teams this season and last season "
            "(regular season and playoffs), with each team's win count. Game lines "
            "are written from team_a's side."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "team_a": {"type": "string", "description": "First team, e.g. 'Celtics'."},
                "team_b": {"type": "string", "description": "Second team, e.g. '76ers'."},
            },
            "required": ["team_a", "team_b"],
        },
    },
    {
        "name": "get_odds",
        "description": (
            "Get head-to-head (who wins) decimal odds for upcoming NBA games from "
            "Australian bookmakers. For each bookmaker: the odds, the implied chance "
            "of each team winning (1 / odds), the bookmaker's margin (how far the two "
            "implied chances add up past 100%), and the home team's fair chance with "
            "the margin removed. Also gives the average fair chance across bookmakers. "
            "Games that have already started are left out. Odds can be up to an hour old. "
            "With a team, it checks the real schedule first and returns that team's next "
            "game; if odds_available is false, bookmakers haven't posted odds for that game "
            "yet. Say so, and don't describe any other game as the team's next game."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "team": {
                    "type": "string",
                    "description": "Optional. Only this team's next game. Leave out to get all upcoming games.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "find_value_bets",
        "description": (
            "Scan upcoming NBA games for bookmaker prices that are better than the market's "
            "fair price. For each bookmaker, the fair chance comes from all the OTHER "
            "bookmakers with their margin removed; edge = fair chance x price - 1. Returns up "
            "to 10 prices with a positive edge, best first, each with an A-F grade (A strongest), "
            "the fair odds, how many bookmakers were compared, and how much they disagree. Also "
            "returns the method and caveats, which you must pass on. An empty list means no "
            "bookmaker currently beats the market, which is common."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "team": {
                    "type": "string",
                    "description": "Optional. Only check this team's next game. Leave out to scan all upcoming games.",
                },
            },
            "required": [],
        },
    },
]


# 2. When Claude asks for a tool, this runs the matching Python function.
def run_tool(name, tool_input):
    try:
        if name == "get_recent_games":
            return get_recent_games(tool_input["team"], tool_input.get("n", 5))
        if name == "get_home_away_record":
            return get_home_away_record(tool_input["team"], tool_input.get("season"))
        if name == "get_head_to_head":
            return get_head_to_head(tool_input["team_a"], tool_input["team_b"])
        if name == "get_odds":
            return get_odds(tool_input.get("team"))
        if name == "find_value_bets":
            return find_value_bets(tool_input.get("team"))
        return {"error": f"Unknown tool: {name}"}
    # If a data API is down or slow, tell Claude instead of crashing the app.
    except (requests.ConnectionError, requests.Timeout):
        return {"error": "The data service couldn't be reached. It may be down; try again shortly."}
    except requests.HTTPError as e:
        return {"error": f"The data service returned an error ({e.response.status_code})."}
    except RuntimeError as e:  # e.g. rate limit still hit after retries
        return {"error": str(e)}


# 3. The loop. `messages` is the whole conversation so far: Claude has no
#    memory, so we send all of it every time.
def ask(messages):
    # Create the connection here rather than at the top of the file, so a key
    # added after the app started (e.g. in Streamlit's Secrets) is picked up.
    client = anthropic.Anthropic()
    while True:
        response = client.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )
        # Save Claude's turn (including any tool requests) into the history.
        messages.append({"role": "assistant", "content": response.content})

        # Claude didn't ask for a tool, so this is the final answer.
        if response.stop_reason != "tool_use":
            return "".join(b.text for b in response.content if b.type == "text")

        # Claude asked for one or more tools: run each one.
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                print(f"  [tool] {block.name}({block.input})")
                result = run_tool(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,  # ties this result to Claude's request
                    "content": json.dumps(result),
                    "is_error": "error" in result,
                })

        # Send the results back as the next message, then go round again.
        messages.append({"role": "user", "content": tool_results})


if __name__ == "__main__":
    print("NBA odds and stats research. Prices and probabilities, never picks or stake advice.")
    print(HELP_LINE)
    print("Type 'quit' to stop.\n")
    messages = []
    while True:
        question = input("You: ").strip()
        if question.lower() in ("quit", "exit"):
            break
        if not question:
            continue
        before = len(messages)
        messages.append({"role": "user", "content": question})
        try:
            print(f"\nClaude: {ask(messages)}\n")
        except anthropic.APIError as e:
            # Claude itself couldn't be reached (no credit, outage, etc.).
            # Undo this half-finished turn so the conversation stays valid.
            del messages[before:]
            print(f"\n[error] Couldn't reach Claude: {e.__class__.__name__}. Try again.\n")
