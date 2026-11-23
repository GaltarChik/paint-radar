"""Pain Radar: find the most common complaints in Reddit posts and suggest product ideas.

Run with:  streamlit run app.py
"""

import json
import os
import re
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

SAMPLE_FILE = Path(__file__).parent / "sample_posts.txt"
MIN_POST_LENGTH = 20  # shorter posts ("lol same") carry no useful signal

load_dotenv(Path(__file__).parent / ".env")  # reads OPENAI_API_KEY from .env next to app.py
API_KEY = os.getenv("OPENAI_API_KEY")
# timeout: stop waiting after 60 s; max_retries: the SDK itself retries timeouts and 429 (rate limit)
client = OpenAI(api_key=API_KEY, timeout=60, max_retries=3) if API_KEY else None


# ---------- Pre-filter (no AI) ----------

def split_posts(text):
    """Split raw text into posts (separated by a blank line) and drop very short ones."""
    chunks = re.split(r"\n\s*\n", text)  # a blank line may contain spaces or \r
    posts = [chunk.strip() for chunk in chunks]
    return [post for post in posts if len(post) >= MIN_POST_LENGTH]


# ---------- LLM helpers ----------

def parse_json(raw):
    """Extract a JSON object even if the model wrapped it in ```json ... ``` fences."""
    match = re.search(r"\{.*\}", raw or "", re.DOTALL)  # from the first "{" to the last "}"
    if not match:
        raise ValueError("The model did not return JSON.")
    return json.loads(match.group(0))  # raises ValueError if the JSON is broken


def ask_llm(model, system_prompt, user_prompt, temperature=0.0, top_p=1.0, max_tokens=1000):
    """One Chat Completions call in JSON mode. Returns the answer as a Python dict."""
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},  # the model must answer with a JSON object
    )
    return parse_json(response.choices[0].message.content)


# ---------- Callbacks: they fill the text area before the page is redrawn ----------

def load_demo():
    st.session_state.posts_text = SAMPLE_FILE.read_text(encoding="utf-8")


def load_file():
    uploaded = st.session_state.uploaded_file
    if uploaded is not None:
        st.session_state.posts_text = uploaded.getvalue().decode("utf-8", errors="ignore")


# ---------- Sidebar: settings ----------

st.set_page_config(page_title="Pain Radar", page_icon="📡")
st.sidebar.header("Settings")
# Two models: a cheap, fast one for many small decisions, a stronger one for the final report
model_step1 = st.sidebar.text_input("Model for step 1 (classification)", "gpt-4o-mini")
model_step2 = st.sidebar.text_input("Model for step 2 (themes report)", "gpt-4.1-mini")

# TEMPORARY (stage 2): check that both models answer. Will be removed later.
if st.sidebar.button("Test API connection"):
    if client is None:
        st.sidebar.error("OPENAI_API_KEY is missing. Add it to the .env file.")
    else:
        for model in (model_step1, model_step2):
            answer = ask_llm(model, "You answer in JSON.", 'Return exactly {"status": "ok"}.', max_tokens=20)
            st.sidebar.success(f"{model}: {answer}")

# ---------- Main page ----------

st.title("📡 Pain Radar")
st.write(
    "Paste Reddit posts (one post per paragraph, separated by a blank line). "
    "Pain Radar finds what people complain about most and suggests a product idea for each problem."
)

col_demo, col_file = st.columns(2)
col_demo.button("Load demo posts", on_click=load_demo)
col_file.file_uploader("…or upload a .txt file", type=["txt"], key="uploaded_file", on_change=load_file)

st.text_area("Posts", key="posts_text", height=300, placeholder="Paste posts here...")

if st.button("Analyze", type="primary"):
    posts = split_posts(st.session_state.posts_text)
    st.success(f"Found {len(posts)} posts (posts shorter than {MIN_POST_LENGTH} characters are skipped).")
