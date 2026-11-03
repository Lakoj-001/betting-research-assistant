# The chat page. Run locally with:  streamlit run app.py
# Same agent loop as agent.py, with a web page instead of the terminal.

import os

import streamlit as st

# On Streamlit Cloud the keys live in the app's Secrets settings, not in .env.
# Copy them into the environment BEFORE importing agent/tools, because those
# read the keys when they're imported. Locally there are no secrets, so
# st.secrets raises an error and .env is used instead.
try:
    for key, value in st.secrets.items():
        os.environ.setdefault(key, str(value))
except Exception:
    pass

import anthropic  # noqa: E402

from agent import HELP_LINE, ask  # noqa: E402

MAX_QUESTIONS = 20  # per visitor session, so a public link can't run up the API bill

st.set_page_config(page_title="NBA Odds Research", page_icon="🏀")
st.title("🏀 NBA Odds Research")
st.caption(
    "Ask about team form, head-to-head records, what the odds imply, "
    "and which bookmaker prices beat the market's fair price."
)
st.info(
    "Prices and probabilities only: no picks, no stake advice, no guarantees. "
    f"An edge is a long-run average, not a prediction. {HELP_LINE}"
)

# Plain-English explanations for people new to odds, kept in GLOSSARY.md
# so the same text can be read on GitHub too.
with st.expander("📖 New to odds? What the terms mean"):
    with open("GLOSSARY.md", encoding="utf-8") as f:
        st.markdown(f.read())

# st.session_state survives between reruns of this script for one visitor.
# `messages` is the full history Claude sees (including tool calls);
# `chat` is just what we show on screen: (role, text, lookups used) per bubble.
if "messages" not in st.session_state:
    st.session_state.messages = []
    st.session_state.chat = []


def lookups_box_label(lookups):
    return f"Looked up {len(lookups)} source{'s' if len(lookups) != 1 else ''}"


for role, text, lookups in st.session_state.chat:
    with st.chat_message(role):
        if lookups:
            # Earlier answers: show their lookups folded shut.
            with st.expander(lookups_box_label(lookups)):
                for label in lookups:
                    st.markdown(f"🔎 {label}")
        st.markdown(text)

questions_asked = sum(1 for role, _, _ in st.session_state.chat if role == "user")
missing_keys = [
    k for k in ("ANTHROPIC_API_KEY", "BALLDONTLIE_API_KEY", "ODDS_API_KEY") if not os.getenv(k)
]

if missing_keys:
    # Happens when the keys haven't been added to the app's Secrets settings.
    st.error(
        f"Setup problem: missing {', '.join(missing_keys)}. Add them in Manage app → Settings → "
        'Secrets as NAME = "value" lines, then reboot the app.'
    )
elif questions_asked >= MAX_QUESTIONS:
    st.warning(f"You've reached the limit of {MAX_QUESTIONS} questions for this session. Refresh the page to start again.")
elif question := st.chat_input("e.g. Are any bookmakers pricing tonight's games above fair odds?"):
    st.session_state.chat.append(("user", question, []))
    with st.chat_message("user"):
        st.markdown(question)

    messages = st.session_state.messages
    before = len(messages)
    messages.append({"role": "user", "content": question})

    with st.chat_message("assistant"):
        # The lookups box: open with a spinner while working, folded shut later.
        status = st.status("Thinking...", expanded=True)
        answer_spot = st.empty()  # a spot we redraw each time new words arrive
        lookups = []
        streamed = {"text": ""}  # a dict so the callbacks below can change it

        def on_tool(label):
            lookups.append(label)
            status.update(label=f"Looking up: {label}")
            status.markdown(f"🔎 {label}")

        def on_text(text):
            if not streamed["text"]:
                status.update(expanded=False)  # the answer has started: fold the box shut
            streamed["text"] += text
            answer_spot.markdown(streamed["text"] + "▌")  # ▌ = a typing cursor

        try:
            answer = ask(messages, on_tool=on_tool, on_text=on_text)
        except anthropic.APIError as e:
            del messages[before:]  # undo the half-finished turn
            answer = f"Sorry, I couldn't reach Claude ({e.__class__.__name__}). Please try again."

        if lookups:
            status.update(label=lookups_box_label(lookups), state="complete", expanded=False)
        else:
            status.update(label="No lookups needed", state="complete", expanded=False)
        answer_spot.markdown(answer)  # final version, without the cursor
    st.session_state.chat.append(("assistant", answer, lookups))
