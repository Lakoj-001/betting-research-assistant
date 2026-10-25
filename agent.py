# The agent loop: chat with Claude in the terminal. Claude can ask for
# get_recent_games, our Python runs it, and the result goes back to Claude.

import json
from datetime import date

import anthropic
from dotenv import load_dotenv

from tools import get_head_to_head, get_home_away_record, get_recent_games

load_dotenv()
client = anthropic.Anthropic()
MODEL = "claude-haiku-5-5"  # cheapest model while testing

SYSTEM_PROMPT = f"""You are an NBA research assistant. Today is {date.today().isoformat()}.
Answer questions using the tools to fetch real data. Don't guess numbers."""

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
]


# 2. When Claude asks for a tool, this runs the matching Python function.
def run_tool(name, tool_input):
    if name == "get_recent_games":
        return get_recent_games(tool_input["team"], tool_input.get("n", 5))
    if name == "get_home_away_record":
        return get_home_away_record(tool_input["team"], tool_input.get("season"))
    if name == "get_head_to_head":
        return get_head_to_head(tool_input["team_a"], tool_input["team_b"])
    return {"error": f"Unknown tool: {name}"}


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
    print("NBA research assistant. Type 'quit' to stop.\n")
    messages = []
    while True:
        question = input("You: ").strip()
        if question.lower() in ("quit", "exit"):
            break
        if not question:
            continue
        messages.append({"role": "user", "content": question})
        print(f"\nClaude: {ask(messages)}\n")
