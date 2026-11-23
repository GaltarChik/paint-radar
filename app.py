"""Pain Radar: find the most common complaints in Reddit posts and suggest product ideas.
Run with:  streamlit run app.py"""

import json
import os
import re
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from openai import (APIConnectionError, APIStatusError, APITimeoutError, AuthenticationError,
                    OpenAI, RateLimitError)

import prompts

SAMPLE_FILE = Path(__file__).parent / "sample_posts.txt"
MIN_POST_LENGTH = 20  # shorter posts ("lol same") carry no useful signal
MIN_POSTS = 3  # with fewer posts there is nothing "common" to find
STEP1_MAX_TOKENS = 2000  # step 1 answer is ~35 tokens per post, so this is enough for ~50 posts

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
    """One Chat Completions call in JSON mode. Returns the answer as a Python dict.
    If the JSON is broken, asks the model once more; after a second failure raises ValueError."""
    for attempt in (1, 2):
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system_prompt},
                      {"role": "user", "content": user_prompt}],
            temperature=temperature, top_p=top_p, max_tokens=max_tokens,
            response_format={"type": "json_object"},  # the model must answer with a JSON object
        )
        if response.choices[0].finish_reason == "length":  # cut off: a retry would be cut off too
            raise ValueError("the answer was cut off by the max_tokens limit. "
                             "Increase Max tokens (step 2) or use fewer posts (step 1).")
        try:
            return parse_json(response.choices[0].message.content)
        except ValueError:
            if attempt == 2:
                raise ValueError("the model returned broken JSON twice. Please try again.")


# ---------- LLM step 1: classification ----------
def classify_posts(posts, model, few_shot):
    """Ask the model which posts describe a problem. Returns a list of dicts."""
    system_prompt = prompts.CLASSIFY_SYSTEM + (prompts.FEW_SHOT_EXAMPLES if few_shot else "")
    # temperature=0: classification has one right answer, so we want the most likely,
    # repeatable label (the same post gets the same label on every run)
    data = ask_llm(model, system_prompt, prompts.classify_user_prompt(posts),
                   temperature=0, max_tokens=STEP1_MAX_TOKENS)
    return data.get("results", [])


# ---------- LLM step 2: themes report ----------
def find_themes(problems, model, temperature, top_p, max_tokens, n_themes):
    """Group the problems into themes with product ideas. Returns (reasoning, themes)."""
    data = ask_llm(model, prompts.THEMES_SYSTEM, prompts.themes_user_prompt(problems, n_themes),
                   temperature, top_p, max_tokens)
    # the model does not always sort correctly, so we sort in code: most common theme first
    themes = sorted(data.get("themes", []), key=lambda t: t.get("count", 0), reverse=True)
    return data.get("reasoning", ""), themes


def make_report(themes, reasoning, n_posts, n_problems):
    """Build the report as Markdown text for the download button (settings included for experiments)."""
    lines = ["# Pain Radar report\n", f"Posts analyzed: {n_posts}, posts with a problem: {n_problems}\n",
             f"Settings: step 1 = {model_step1} ({technique}), step 2 = {model_step2}, "
             f"temperature = {temperature}, top_p = {top_p}, max_tokens = {max_tokens}\n"]
    for i, t in enumerate(themes, start=1):
        lines.append(f"## {i}. {t['name']} ({t['count']} posts)\n\n{t['description']}\n\n"
                     f"*Example:* {t['example_problem']}\n\n**Product idea:** {t['product_idea']}\n")
    lines.append(f"## How the model reasoned\n\n{reasoning}\n")
    return "\n".join(lines)


# ---------- Callbacks: they fill the text area before the page is redrawn ----------
def load_demo():
    st.session_state.posts_text = SAMPLE_FILE.read_text(encoding="utf-8")


def load_file():
    uploaded = st.session_state.uploaded_file
    if uploaded is not None:
        st.session_state.posts_text = uploaded.getvalue().decode("utf-8", errors="ignore")


# ---------- The whole AI pipeline (uses the sidebar settings defined below) ----------
def run_analysis(posts):
    with st.spinner(f"Step 1: classifying posts with {model_step1} ({technique})..."):
        results = classify_posts(posts, model_step1, few_shot=(technique == "Few-shot"))
    problems = [r["problem"] for r in results if r["is_problem"]]

    col1, col2, col3 = st.columns(3)
    col1.metric("Posts analyzed", len(posts), help=f"Posts shorter than {MIN_POST_LENGTH} characters are skipped")
    col2.metric("Posts with a problem", len(problems))
    col3.metric("Problem share", f"{len(problems) / len(posts):.0%}")

    st.subheader("Step 1: Classification")
    rows = [{"#": r["id"], "Post": posts[r["id"] - 1][:100] + "...",  # ids start at 1, lists at 0
             "Problem?": "✅" if r["is_problem"] else "—", "Problem": r.get("problem", "")}
            for r in results]
    st.dataframe(rows, hide_index=True, width="stretch")
    if not problems:
        st.info("No problems found in these posts, so there is nothing to group.")
        return

    with st.spinner(f"Step 2: grouping {len(problems)} problems into themes with {model_step2}..."):
        reasoning, themes = find_themes(problems, model_step2, temperature, top_p, max_tokens, n_themes)

    st.subheader("Step 2: Top problems and product ideas")
    for i, theme in enumerate(themes, start=1):
        with st.expander(f"{i}. {theme['name']} ({theme['count']} posts)", expanded=(i == 1)):
            st.write(theme["description"])
            st.markdown(f"**Example:** *{theme['example_problem']}*")
            st.success(f"💡 **Product idea:** {theme['product_idea']}")
    with st.expander("🧠 How the model reasoned"):
        st.write(reasoning)
    # on_click="ignore": downloading does not rerun the app, so the results stay on screen
    st.download_button("⬇️ Download report (.md)", make_report(themes, reasoning, len(posts), len(problems)),
                       file_name="pain_radar_report.md", mime="text/markdown", on_click="ignore")


# ---------- Sidebar: settings ----------
st.set_page_config(page_title="Pain Radar", page_icon="📡")
st.sidebar.header("Settings")
# Two models: a cheap, fast one for many small decisions, a stronger one for the final report
model_step1 = st.sidebar.text_input("Model for step 1 (classification)", "gpt-4o-mini")
model_step2 = st.sidebar.text_input("Model for step 2 (themes report)", "gpt-4.1-mini")

st.sidebar.subheader("Step 1: classification")
technique = st.sidebar.radio("Prompting technique", ["Few-shot", "Zero-shot"], horizontal=True)
st.sidebar.caption("Few-shot adds 4 labelled examples to the prompt. Zero-shot uses instructions only.")

st.sidebar.subheader("Step 2: themes report")
temperature = st.sidebar.slider("Temperature", 0.0, 1.5, 0.7, 0.1, help="Higher = more varied product ideas")
top_p = st.sidebar.slider("Top-p", 0.1, 1.0, 0.9, 0.05, help="Ignore the least likely 10% of words")
max_tokens = st.sidebar.slider("Max tokens", 300, 3000, 1500, 100, help="Length limit of the report")
n_themes = st.sidebar.slider("Number of themes", 2, 6, 4)

# ---------- Main page ----------
st.title("📡 Pain Radar")
st.write("Paste Reddit posts (one post per paragraph, separated by a blank line). Pain Radar finds what "
         "people complain about most and suggests a product idea for each problem.")

col_demo, col_file = st.columns(2)
col_demo.button("Load demo posts", on_click=load_demo)
col_file.file_uploader("…or upload a .txt file", type=["txt"], key="uploaded_file", on_change=load_file)
st.text_area("Posts", key="posts_text", height=300, placeholder="Paste posts here...")

if st.button("Analyze", type="primary"):
    posts = split_posts(st.session_state.posts_text)
    # Checks BEFORE calling the API: they cost nothing and give the clearest message
    if client is None:
        st.error("🔑 OPENAI_API_KEY is missing. Copy .env.example to .env and add your key.")
    elif len(posts) < MIN_POSTS:
        st.warning(f"Found {len(posts)} posts. Pain Radar needs at least {MIN_POSTS} posts "
                   f"(separated by a blank line, each at least {MIN_POST_LENGTH} characters).")
    else:
        try:
            run_analysis(posts)
        # Errors from the OpenAI SDK (it has already retried timeouts and 429 three times)
        except AuthenticationError:
            st.error("🔑 The API key was rejected. Check OPENAI_API_KEY in the .env file.")
        except RateLimitError:
            st.error("⏳ Rate limit or quota exceeded. Wait a minute or check your OpenAI billing.")
        except (APITimeoutError, APIConnectionError):
            st.error("🌐 Could not reach OpenAI (timeout or no internet). Check your connection and retry.")
        except APIStatusError as e:  # any other API error, e.g. 404 = wrong model name
            st.error(f"⚠️ OpenAI error {e.status_code}. Check the model names in the sidebar. Details: {e.message}")
        # Errors in the model's answer
        except ValueError as e:
            st.error(f"🧩 Could not read the model's answer: {e}")
        except (KeyError, IndexError, TypeError):
            st.error("🧩 The model's answer has an unexpected structure. Please try again.")
