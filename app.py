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

import prompts

SAMPLE_FILE = Path(__file__).parent / "sample_posts.txt"
MIN_POST_LENGTH = 20  # shorter posts ("lol same") carry no useful signal
# Step 1 answer is ~35 tokens per post, so 2000 tokens is enough for ~50 posts
STEP1_MAX_TOKENS = 2000

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


# ---------- LLM step 1: classification ----------

def classify_posts(posts, model, few_shot):
    """Ask the model which posts describe a problem. Returns a list of dicts."""
    system_prompt = prompts.CLASSIFY_SYSTEM + (prompts.FEW_SHOT_EXAMPLES if few_shot else "")
    # temperature=0: classification has one right answer, so we want the most likely,
    # repeatable label (the same post gets the same label on every run)
    data = ask_llm(model, system_prompt, prompts.classify_user_prompt(posts),
                   temperature=0, max_tokens=STEP1_MAX_TOKENS)
    return data.get("results", [])


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

st.sidebar.subheader("Step 1: classification")
technique = st.sidebar.radio("Prompting technique", ["Few-shot", "Zero-shot"], horizontal=True)
st.sidebar.caption("Few-shot adds 4 labelled examples to the prompt. Zero-shot uses instructions only.")

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

    if client is None:
        st.error("OPENAI_API_KEY is missing. Add it to the .env file.")
        st.stop()

    with st.spinner(f"Step 1: classifying posts with {model_step1} ({technique})..."):
        results = classify_posts(posts, model_step1, few_shot=(technique == "Few-shot"))

    st.subheader("Step 1: Classification")
    rows = [
        {
            "#": r["id"],
            "Post": posts[r["id"] - 1][:100] + "...",  # ids start at 1, Python lists at 0
            "Problem?": "✅" if r["is_problem"] else "—",
            "Problem": r.get("problem", ""),
        }
        for r in results
    ]
    st.dataframe(rows, hide_index=True, width="stretch")
