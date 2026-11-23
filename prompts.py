"""All prompts of Pain Radar live here, so they are easy to read and show in the presentation.

Prompting techniques used in step 1 (classification):
  - zero-shot: instructions only (CLASSIFY_SYSTEM)
  - few-shot:  the same instructions + 4 labelled examples (FEW_SHOT_EXAMPLES)
  - structured output: a strict JSON format the code can parse
"""

# ---------- Step 1: classify each post ----------

CLASSIFY_SYSTEM = """You are a careful annotator of posts from a student community on Reddit.
For each post decide whether the author describes a PROBLEM: a real pain, frustration or unmet need
that a product or service could help with.

Counts as a problem: complaints about costs, broken or slow systems, bad tools, lack of time or sleep,
conflicts with other people that keep happening.
Does NOT count as a problem: good news, jokes, tips, invitations to events,
simple questions that are easy to answer.

If a post is a problem, describe it in "problem" as one short neutral sentence (max 15 words)
that names the pain itself, not the author's emotions. If it is not a problem, use an empty string.
Answer only with JSON."""

# 4 examples: 2 problems + 2 non-problems. They are NOT taken from the demo posts,
# so the model learns the rule, not the answers.
FEW_SHOT_EXAMPLES = """

Examples of correct answers:

Post: "The campus wifi drops every time I join a Zoom lecture. I already missed two quizzes because of it."
Answer: {"is_problem": true, "problem": "Campus wifi is unreliable during online lectures."}

Post: "Finally submitted my thesis draft, going to sleep for a week!"
Answer: {"is_problem": false, "problem": ""}

Post: "A parking permit costs $400 a year and there are still no free spots after 9am."
Answer: {"is_problem": true, "problem": "Campus parking is expensive and always full."}

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
