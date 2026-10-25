# The agent loop: chat with Claude in the terminal. Claude can ask for
# one of our tools, our Python runs it, and the result goes back to Claude.

import json
from datetime import date

import anthropic
import requests
from dotenv import load_dotenv

from tools import get_head_to_head, get_home_away_record, get_odds, get_recent_games

load_dotenv()
client = anthropic.Anthropic()
MODEL = "claude-haiku-5-5"  # cheapest model while testing

HELP_LINE = "18+ only. Gambling Help Online: gamblinghelponline.org.au or 1800 858 858 (24/7, free)."

SYSTEM_PROMPT = f"""You are an NBA research assistant for Australian users. Today is {date.today().isoformat()}. Times are Sydney time.

Your job is research only: explain team form, stats, head-to-head history, and what bookmaker odds imply.

Rules:
- Never recommend a bet, a pick, a stake, or say a team is "value" or "the play". If asked who to bet on, say politely that you only do research, then offer the relevant facts instead.
- Use the tools for every number. Never guess or use your own memory for scores, records or odds.
- Say where each number came from: game results come from balldontlie; odds come from The Odds API, with the bookmaker name and the time the odds were fetched.
- If data is missing or a tool returns an error, say so plainly. Don't fill the gap.
- Point out when games are from last season or the playoffs, since they may not reflect current form.
- Whenever you mention odds or betting, end with this line exactly: "{HELP_LINE}"
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
            "Games that have already started are left out. Odds can be up to an hour old."
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
    print("NBA research assistant. Research only, no betting tips.")
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
