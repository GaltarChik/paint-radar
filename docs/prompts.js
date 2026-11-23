// All prompts of the web version. They are a word-for-word copy of prompts.py,
// so the website and the Python app send exactly the same text to the model.
//
// Prompting techniques:
//   Step 1 (classification): zero-shot (CLASSIFY_SYSTEM), few-shot (+ FEW_SHOT_EXAMPLES)
//   Step 2 (themes report):  role / persona (THEMES_SYSTEM), chain-of-thought ("reasoning" before "themes")
//   Both steps:              structured output (a strict JSON format the code can parse)

// ---------- Step 1: classify each post ----------

const CLASSIFY_SYSTEM = `You are a careful annotator of posts from a student community on Reddit.
For each post decide whether the author describes a PROBLEM: a real pain, frustration or unmet need
that a product or service could help with.

Counts as a problem: complaints about costs, broken or slow systems, bad tools, lack of time or sleep,
conflicts with other people that keep happening. A complaint still counts when it is written
as a joke or as a question.
Does NOT count as a problem: good news, jokes with no complaint inside, tips, invitations to events,
simple questions that are easy to answer.

If a post is a problem, describe it in "problem" as one short neutral sentence (max 15 words)
that names the pain itself, not the author's emotions. If it is not a problem, use an empty string.
Answer only with JSON.`;

// 4 examples: 2 problems + 2 non-problems, not taken from the demo or experiment posts
const FEW_SHOT_EXAMPLES = `

Examples of correct answers:

Post: "The library printer has been 'temporarily out of order' since September, it's basically part of the campus tour now 😂"
Answer: {"is_problem": true, "problem": "The library printer has been broken for months."}

Post: "Finally submitted my thesis draft, going to sleep for a week!"
Answer: {"is_problem": false, "problem": ""}

Post: "Is it just me or does the campus shuttle never come on time? Waited 40 minutes again today."
Answer: {"is_problem": true, "problem": "The campus shuttle is often very late."}

Post: "Which dining hall has the best pancakes on Sunday mornings?"
Answer: {"is_problem": false, "problem": ""}`;

function classifyUserPrompt(posts) {
  const numbered = posts.map((post, i) => `[${i + 1}] ${post}`).join("\n\n");
  return `Classify every post below. Use the number in square brackets as "id".

${numbered}

Return JSON in exactly this format, with one entry for every post:
{"results": [{"id": 1, "is_problem": true, "problem": "short description"},
             {"id": 2, "is_problem": false, "problem": ""}]}`;
}

// ---------- Step 2: group problems into themes + product ideas ----------

// Role / persona: tells the model which expertise and point of view to use
const THEMES_SYSTEM = `You are an experienced product analyst. You study user complaints from online
communities, find the pains that many people share, and turn them into realistic product opportunities.
You are concrete and practical: no buzzwords, no vague advice. Answer only with JSON.`;

// Chain-of-thought: the "reasoning" field comes first, so the model thinks before it answers
function themesUserPrompt(problems, nThemes) {
  const numbered = problems.map((problem, i) => `${i + 1}. ${problem}`).join("\n");
  return `Here are ${problems.length} problems found in student posts:

${numbered}

Group these problems into ${nThemes} themes (fewer only if there are not enough different problems).

Think step by step first. In "reasoning" write 3-6 short sentences: which problems belong together
and why, and which theme is the most common. Only after that fill "themes".

For each theme:
- "name": 2-5 words
- "count": how many problems from the list belong to this theme
- "description": one sentence about the pain
- "example_problem": one problem from the list above, copied as written
- "product_idea": 1-2 sentences: a concrete product or service, who it is for, how it solves the pain

Sort themes by "count", largest first. Return JSON in exactly this format:
{"reasoning": "...", "themes": [{"name": "...", "count": 3, "description": "...",
  "example_problem": "...", "product_idea": "..."}]}`;
}
