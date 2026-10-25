# v1 ideas

Things noticed while building v0, roughly in priority order.

## Data
- **Injury reports and team news (RAG).** The biggest gap: form and odds without knowing who's injured is half the picture. Search recent news and feed the relevant bits to Claude. First step on the text RAG → voice RAG path.
- **Player stats and standings.** Needs balldontlie's paid tier. Unlocks "who's their top scorer this month?" and ladder questions.
- **Streaks and margins.** Longest winning streak, average winning margin and record in close games, all built from the game results we already have.
- **Odds history.** Save each odds fetch so the app can say "the Lakers have shortened from 1.55 to 1.40 since yesterday".

## Product
- **Show the tool calls in the chat page**, e.g. a small "Looked up: recent games (Celtics)" line, so users see where answers come from.
- **Streamed answers**, so text appears as it's written instead of after a pause.
- **Second sport (EPL)** using the same loop with different tools.

## Quality
- **Grow the test set to 25+ questions**, including the tricky ones v0 got wrong during the build (home vs away misreads, odds ranges).
- **Try a stronger model** for the final answer and compare eval scores and cost per question.
- **A shared cache** (e.g. a small database) so all visitors share one set of API calls instead of each server copy fetching its own.

## Before charging money or taking investment
- Check Australia's rules on gambling-related services and advertising with someone qualified.
- Proper usage limits and accounts instead of a per-session question cap.
