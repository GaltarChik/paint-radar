# 📡 Pain Radar

Paste Reddit posts and Pain Radar uses generative AI to find the most common complaints and suggest a product idea for each one.

*Individual project for the course "Intro to Generative AI".*

**Project site:** https://galtarchik.github.io/paint-radar/ · **Live app:** https://pain-radar.streamlit.app · **Code:** https://github.com/GaltarChik/paint-radar

## The problem

Founders, student unions and product teams want to know **what people actually complain about**. The answers are hidden in hundreds of forum posts mixed with jokes, good news and questions. Reading them all by hand is slow. Pain Radar takes raw posts, filters out the noise, groups the real complaints into themes, and turns every theme into a concrete product idea.

## How it works

```
posts ──► pre-filter (no AI) ──► LLM step 1: classification ──► LLM step 2: themes + product ideas ──► report
          split by blank line     gpt-4o-mini, temperature 0     gpt-4.1-mini, temperature 0.7
          drop posts < 20 chars   "is this post a problem?"      "analyst" role + chain-of-thought
```

1. **Pre-filter (no AI).** `split_posts()` splits the text at blank lines and drops posts shorter than 20 characters ("lol same"). This saves tokens on noise.
2. **Step 1: classification.** For each post the model answers in JSON whether it describes a problem and, if yes, writes the problem as one short neutral sentence.
3. **Step 2: themes report.** The problems only (not the whole posts) go to a stronger model. It groups them into themes, counts them and suggests a product idea for each theme.
4. **Report.** Metrics, a classification table, themes in expandable blocks, the model's reasoning, and a downloadable `.md` report.

### Two models

| Step | Model | Why |
|---|---|---|
| 1: classification | `gpt-4o-mini` | Many small yes/no decisions: a cheap, fast model is enough |
| 2: themes report | `gpt-4.1-mini` | One harder task (grouping + ideas): a stronger model pays off |

Both can be changed in the sidebar. Reasoning models (`gpt-5*`, o-series) are not used: they do not accept a custom `temperature` or `max_tokens`. The originally planned `gpt-4.1-nano` was retired by OpenAI (API returns 404), so it was replaced with `gpt-4o-mini`.

## Prompt engineering

All prompts live in [`prompts.py`](prompts.py).

| Technique | Where | What it does |
|---|---|---|
| **Zero-shot** | Step 1, `CLASSIFY_SYSTEM` | Instructions only: what counts as a problem and what does not |
| **Few-shot** | Step 1, `CLASSIFY_SYSTEM` + `FEW_SHOT_EXAMPLES` | The same instructions + 4 labelled examples (2 problems, 2 non-problems) |
| **Role / persona** | Step 2, `THEMES_SYSTEM` | "You are an experienced product analyst…": sets expertise and a practical tone |
| **Chain-of-thought** | Step 2, `themes_user_prompt()` | The model must fill `reasoning` *before* `themes`. JSON is generated in order, so the model really thinks first. The reasoning is shown in the UI ("How the model reasoned") |
| **Structured output (JSON)** | Both steps, `ask_llm()` | `response_format={"type": "json_object"}` + an exact format in the prompt, so the code can parse the answer |

The sidebar switch **Few-shot / Zero-shot** runs step 1 with or without the examples, so both techniques can be compared on the same data (see [Experiments](#experiments)).

## Parameters

| Parameter | Step | Value | Why |
|---|---|---|---|
| `temperature` | 1 | **0** (fixed) | Classification has one right answer. We want the most likely label, and the same post should get the same label on every run |
| `max_tokens` | 1 | **2000** (fixed) | About 35 tokens per post, enough for about 50 posts |
| `temperature` | 2 | **0.7** (slider 0–1.5) | Product ideas need some creativity: at 0 they are generic, above about 1.0 they get long and less focused |
| `top_p` | 2 | **0.9** (slider) | Only the most likely words (90% of probability) are used, which cuts the tail of strange words |
| `max_tokens` | 2 | **1500** (slider) | Reasoning (about 250 tokens) + about 100 per theme, with a safe margin so the JSON is not cut off |
| Number of themes | 2 | **4** (slider 2–6) | Passed into the prompt |

The client is created with `timeout=60, max_retries=3`: the OpenAI SDK itself retries timeouts and rate-limit (429) errors.

## Error handling

| Situation | What happens |
|---|---|
| No API key | Checked before any request: "OPENAI_API_KEY is missing…" |
| Empty input / fewer than 3 posts | Checked before any request: warning with the rule |
| Invalid API key | `AuthenticationError` → "The API key was rejected…" |
| Rate limit / no quota | SDK retries 3×, then `RateLimitError` → "Rate limit or quota exceeded…" |
| Timeout / no internet | SDK retries 3×, then `APITimeoutError` / `APIConnectionError` → "Could not reach OpenAI…" |
| Wrong model name, other API errors | `APIStatusError` → error code + "Check the model names in the sidebar" |
| Broken JSON | `ask_llm()` asks the model **once more**, then shows an error |
| Answer cut off by `max_tokens` | Detected by `finish_reason == "length"` → "Increase Max tokens" (a retry would be cut off too) |
| JSON without the expected fields | "The model's answer has an unexpected structure…" |
| No problems found | Info message, step 2 is skipped |
| Model does not sort themes | Themes are sorted in code by `count` |

## Experiments

All runs: step 1 = `gpt-4o-mini`, step 2 = `gpt-4.1-mini`, November 2026. Every step-1 configuration was run twice.

### 1. Few-shot vs Zero-shot (step 1)

Two data sets:
- [`sample_posts.txt`](sample_posts.txt): 15 posts with clear cases (10 problems, 5 non-problems);
- [`experiment_posts.txt`](experiment_posts.txt): 6 **borderline** posts written to be hard. They include a complaint written as a joke, a complaint written as a question, and harmless posts that look similar.

**Prompt v1** (first version): the rule said *"jokes do not count as a problem"*, and all 4 few-shot examples were obvious cases.

| Data | Few-shot v1 | Zero-shot v1 |
|---|---|---|
| Demo (15 clear posts) | 15/15 | 15/15 |
| Borderline (6 posts) | 4/6 | 4/6 |

Both modes made the same mistakes. They labelled *"the dining hall served the same pasta five days in a row, at this point it's a tradition"* (a joke that is really a complaint) and *"the gym is always packed between 4 and 8pm?"* (a complaint written as a question) as **not** a problem. The few-shot examples did not help, because they covered only easy cases, and the rule "jokes are not problems" pushed the model the wrong way.

**Prompt v2**:
- the rule was clarified: *"A complaint still counts when it is written as a joke or as a question"*;
- the two problem examples were replaced with hard cases: a joking complaint about a broken printer and a complaint-question about a late shuttle.

| Data | Few-shot v2 | Zero-shot v2 |
|---|---|---|
| Demo (15 clear posts) | 15/15 | 15/15 |
| Borderline (6 posts) | **5/6** | **5/6** |

**Conclusions**
- Accuracy rose from 4/6 to 5/6, but **in both modes**. The real improvement came from the clearer **instruction**, not from the examples. For a model like `gpt-4o-mini`, a precise rule matters more than examples.
- Few-shot mostly changes the **style** of the output. With examples, problem descriptions were more neutral: 1 of 10 used emotional words vs 2 of 10 in zero-shot (for example *"Online homework platform adds extra costs."* vs *"High cost of online homework platform feels like a scam."*). Neutral descriptions are easier to group in step 2.
- The remaining error (the gym post) is genuinely ambiguous: the author already suggests a fix ("thinking of going at 6am"). Both modes label it "not a problem".
- With `temperature = 0` every configuration gave **identical labels in both runs**, so the comparison is reproducible.

### 2. Temperature in step 2

The same 10 problems were sent to step 2 twice at each temperature (`top_p = 0.9`, 4 themes):

| Temperature | What we saw |
|---|---|
| **0.0** | Both runs gave the same 4 themes with the same counts. Ideas differed only in a few words: even temperature 0 is not 100% deterministic |
| **0.7** | The themes changed between runs. The "lab overlaps with my job" problem was grouped once with *registration* and once with *living/scheduling*. Ideas became more varied (e.g. soundproofing + roommate mediation) |
| **1.3** | Longer, more detailed ideas with extra features. Still coherent thanks to `top_p = 0.9`, but less focused |

**Conclusion:** 0.7 is a good default. It gives varied, specific ideas without losing focus. Use 0 when you need a stable report to compare data sets.

### Reproduce

1. Run the app, upload `experiment_posts.txt` (or click **Load demo posts**) and press **Analyze** with **Few-shot**.
2. Switch to **Zero-shot** and press **Analyze** again, then compare the "Problem?" column.
3. For step 2, change **Temperature** and run several times. The downloaded `.md` report records all settings.

## How to run

Requirements: Python 3.10+ and an OpenAI API key.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env     # then put your key after OPENAI_API_KEY=
streamlit run app.py
```

The app opens at http://localhost:8501. Click **Load demo posts** → **Analyze**.

## Project structure

```
pain-radar/
├── app.py                # Streamlit interface + pipeline + error handling (< 200 lines)
├── prompts.py            # all prompts (zero-shot, few-shot, role, chain-of-thought)
├── sample_posts.txt      # 16 invented r/college-style posts (demo)
├── experiment_posts.txt  # 6 borderline posts for the Few-shot / Zero-shot experiment
├── requirements.txt
├── .env.example          # template; the real key lives only in .env (git-ignored)
├── .streamlit/config.toml  # app theme: paper, ink, highlighter yellow, red pen
├── README.md
└── docs/
    ├── index.html        # project site for GitHub Pages (HTML + CSS + JS, no build step)
    └── documentation.pdf
```

The app and the site share one visual idea: a printout marked with a highlighter, because marking complaints is exactly what step 1 does. The design rules came from the open-source [impeccable](https://github.com/pbakaus/impeccable) design skill, used as a reference.

All demo and experiment posts are invented. They are not real Reddit users' posts.
