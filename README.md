# Pain Radar

Paste posts from Reddit (or any forum) and Pain Radar finds what people complain about most, groups the complaints into themes and suggests a product idea for each one.

*Individual project for the course "Intro to Generative AI".* Full documentation (prompting techniques, parameters, error handling, experiments): [docs/documentation.pdf](docs/documentation.pdf).

## How it works

```
posts ──► pre-filter (no AI) ──► step 1: classification ──► step 2: themes + product ideas ──► report
```

1. **Pre-filter.** The text is split into posts at blank lines; posts shorter than 20 characters are dropped.
2. **Step 1: classification** (`gpt-4o-mini`, temperature 0). The model decides for every post whether it is a complaint and sums it up in one sentence. Few-shot or zero-shot, switchable.
3. **Step 2: themes** (`gpt-4.1-mini`, temperature 0.7). The model, acting as a product analyst, first writes its reasoning, then groups the complaints into themes and proposes a product for each.
4. **Report.** Metrics, a table of posts, ranked themes with product ideas, the model's reasoning and a Markdown export.

All prompts are in [`prompts.py`](prompts.py). Models and parameters can be changed in the sidebar.

## Run locally

Requirements: Python 3.10+ and an OpenAI API key.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env     # then put your key after OPENAI_API_KEY=
streamlit run app.py
```

The app opens at http://localhost:8501. Click **Load demo posts**, then **Analyze**.

### Web version

The same program also runs as a web page (`docs/`). To open it with the key from `.env`:

```powershell
python server.py           # this computer: http://localhost:8000
python server.py --share   # also other computers in the same Wi-Fi
```

The key stays in `.env` on your computer; the browser never sees it. Stop the server with `Ctrl+C`.
