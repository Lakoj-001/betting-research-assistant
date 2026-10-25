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

st.set_page_config(page_title="NBA Research Assistant", page_icon="🏀")
st.title("🏀 NBA Research Assistant")
st.caption("Ask about team form, head-to-head records, home/away splits and what tonight's odds imply.")
st.info(f"Research only, no betting tips. {HELP_LINE}")

# st.session_state survives between reruns of this script for one visitor.
# `messages` is the full history Claude sees (including tool calls);
# `chat` is just the text bubbles we show on screen.
if "messages" not in st.session_state:
    st.session_state.messages = []
    st.session_state.chat = []

for role, text in st.session_state.chat:
    with st.chat_message(role):
        st.markdown(text)

questions_asked = sum(1 for role, _ in st.session_state.chat if role == "user")

if questions_asked >= MAX_QUESTIONS:
    st.warning(f"You've reached the limit of {MAX_QUESTIONS} questions for this session. Refresh the page to start again.")
elif question := st.chat_input("e.g. How have the Celtics gone in their last 5 games?"):
    st.session_state.chat.append(("user", question))
    with st.chat_message("user"):
        st.markdown(question)

    messages = st.session_state.messages
    before = len(messages)
    messages.append({"role": "user", "content": question})

    with st.chat_message("assistant"):
        with st.spinner("Looking up the data..."):
            try:
                answer = ask(messages)
            except anthropic.APIError as e:
                del messages[before:]  # undo the half-finished turn
                answer = f"Sorry, I couldn't reach Claude ({e.__class__.__name__}). Please try again."
        st.markdown(answer)
    st.session_state.chat.append(("assistant", answer))
