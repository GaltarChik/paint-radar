"""All prompts of Pain Radar live here, so they are easy to read and show in the presentation.

Prompting techniques:
  Step 1 (classification)
  - zero-shot: instructions only (CLASSIFY_SYSTEM)
  - few-shot:  the same instructions + 4 labelled examples (FEW_SHOT_EXAMPLES)
  Step 2 (themes report)
  - role / persona: the model acts as an experienced product analyst (THEMES_SYSTEM)
  - chain-of-thought: the model must write "reasoning" BEFORE "themes" (themes_user_prompt)
  Both steps
  - structured output: a strict JSON format the code can parse
"""

# ---------- Step 1: classify each post ----------

CLASSIFY_SYSTEM = """You are a careful annotator of posts from a student community on Reddit.
For each post decide whether the author describes a PROBLEM: a real pain, frustration or unmet need
that a product or service could help with.

Counts as a problem: complaints about costs, broken or slow systems, bad tools, lack of time or sleep,
conflicts with other people that keep happening. A complaint still counts when it is written
as a joke or as a question.
Does NOT count as a problem: good news, jokes with no complaint inside, tips, invitations to events,
simple questions that are easy to answer.

If a post is a problem, describe it in "problem" as one short neutral sentence (max 15 words)
that names the pain itself, not the author's emotions. If it is not a problem, use an empty string.
Answer only with JSON."""

# 4 examples: 2 problems + 2 non-problems. They are NOT taken from the demo or experiment posts,
# so the model learns the rule, not the answers.
# v2: the problems are the HARD cases (a complaint as a joke, a complaint as a question), because
# with obvious examples (v1) few-shot was no better than zero-shot. See README "Experiments".
FEW_SHOT_EXAMPLES = """

Examples of correct answers:

Post: "The library printer has been 'temporarily out of order' since September, it's basically part of the campus tour now 😂"
Answer: {"is_problem": true, "problem": "The library printer has been broken for months."}

Post: "Finally submitted my thesis draft, going to sleep for a week!"
Answer: {"is_problem": false, "problem": ""}

Post: "Is it just me or does the campus shuttle never come on time? Waited 40 minutes again today."
Answer: {"is_problem": true, "problem": "The campus shuttle is often very late."}

Post: "Which dining hall has the best pancakes on Sunday mornings?"
Answer: {"is_problem": false, "problem": ""}"""


def classify_user_prompt(posts):
    """Numbered posts + the exact JSON format we expect back."""
    numbered = "\n\n".join(f"[{i}] {post}" for i, post in enumerate(posts, start=1))
    return f"""Classify every post below. Use the number in square brackets as "id".

{numbered}

Return JSON in exactly this format, with one entry for every post:
{{"results": [{{"id": 1, "is_problem": true, "problem": "short description"}},
             {{"id": 2, "is_problem": false, "problem": ""}}]}}"""


# ---------- Step 2: group problems into themes + product ideas ----------

# Role / persona: tells the model which expertise and point of view to use
THEMES_SYSTEM = """You are an experienced product analyst. You study user complaints from online
communities, find the pains that many people share, and turn them into realistic product opportunities.
You are concrete and practical: no buzzwords, no vague advice. Answer only with JSON."""


def themes_user_prompt(problems, n_themes):
    """Chain-of-thought: the "reasoning" field comes first, so the model thinks before it answers."""
    numbered = "\n".join(f"{i}. {problem}" for i, problem in enumerate(problems, start=1))
    return f"""Here are {len(problems)} problems found in student posts:

{numbered}

Group these problems into {n_themes} themes (fewer only if there are not enough different problems).

Think step by step first. In "reasoning" write 3-6 short sentences: which problems belong together
and why, and which theme is the most common. Only after that fill "themes".

For each theme:
- "name": 2-5 words
- "count": how many problems from the list belong to this theme
- "description": one sentence about the pain
- "example_problem": one problem from the list above, copied as written
- "product_idea": 1-2 sentences: a concrete product or service, who it is for, how it solves the pain

Sort themes by "count", largest first. Return JSON in exactly this format:
{{"reasoning": "...", "themes": [{{"name": "...", "count": 3, "description": "...",
  "example_problem": "...", "product_idea": "..."}}]}}"""
