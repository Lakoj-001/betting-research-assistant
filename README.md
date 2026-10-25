# 🏀 NBA Research Assistant

A chat app where you ask about NBA teams and Claude answers from real data it fetches itself: recent form, home and away records, head-to-head history, and what bookmaker odds imply.

**Try it:** LINK_GOES_HERE

![Screenshot of the chat page](screenshot.png)

> **Research only.** It explains form, stats and what the odds imply. It never tells you what to bet on.
> 18+ only. Gambling Help Online: [gamblinghelponline.org.au](https://www.gamblinghelponline.org.au) or 1800 858 858 (24/7, free).

## Example questions

- "How have the Celtics gone in their last 5 games?"
- "Were the Lakers better at home or away last season?"
- "Who won the Celtics vs 76ers playoff series last season?"
- "What are the odds for the Lakers' next game, and what chance do they give each team?"

## How the agent loop works

Claude never calls the stats or odds APIs itself. It asks for a tool, the Python code runs it, and the result goes back to Claude until it can answer.

1. Your question goes to Claude, along with a description of each tool (never the code itself).
2. If Claude needs data, it replies with a tool request instead of an answer, e.g. `get_recent_games(team="Celtics", n=5)`.
3. The Python code runs that function, which calls the real API, and sends the result back to Claude.
4. Steps 2 and 3 repeat until Claude has what it needs, which can mean several tools for one question.
5. Claude replies without a tool request, and that reply is the answer shown to you.

Claude has no memory between requests, so the whole conversation is sent every time. That's how follow-up questions like "and at home?" work.

## Tools

| Tool | What it does | Data |
|---|---|---|
| `get_recent_games` | Last n games: wins, losses, points for and against | [balldontlie](https://www.balldontlie.io) |
| `get_home_away_record` | One season's record and average points at home vs away | balldontlie |
| `get_head_to_head` | Every game between two teams, this season and last | balldontlie |
| `get_odds` | Upcoming games' odds from Australian bookmakers, turned into implied chances, with the bookmaker's margin | [The Odds API](https://the-odds-api.com) |

**Odds to chance:** decimal odds of 2.50 imply 1 ÷ 2.50 = 40%. The two teams' chances add up to a bit over 100%, and the extra is the bookmaker's margin. The app also shows each team's "fair" chance with the margin removed.

## Guardrails

- The system prompt allows research only, with no picks, stakes or "value" calls, and politely declines "who should I bet on?".
- Every number comes from a tool and names its source. Claude says when data is missing instead of guessing.
- Typos, unknown teams, an API being down and rate limits all return clear messages instead of crashing.
- Each visitor gets 20 questions per session, which keeps API costs in check.

## Evals

`evals.py` asks 10 questions with answers worked out from the data and checks every reply: the right numbers, the right tools called, no betting picks, and the help line shown where it should be. **Current result: 10/10.** Full answers are in [eval_results.md](eval_results.md).

## Run it yourself

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env        # then add your three API keys
python agent.py               # terminal chat
streamlit run app.py          # web chat page
python evals.py               # run the test set
```

Keys needed: [Anthropic](https://console.anthropic.com), [balldontlie](https://app.balldontlie.io) (free tier) and [The Odds API](https://the-odds-api.com) (free tier, 500 credits a month).

## Files

| File | Purpose |
|---|---|
| `tools.py` | Fetches the data and does the counting and maths |
| `agent.py` | Tool descriptions, system prompt, the agent loop, and a terminal chat |
| `app.py` | Streamlit chat page |
| `evals.py` | The 10-question test set |

Built with Python, the [Claude API](https://docs.claude.com) and [Streamlit](https://streamlit.io).
