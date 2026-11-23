// Pain Radar, web version: the same pipeline as app.py, running in the browser.
// posts -> pre-filter (no AI) -> step 1: classification -> step 2: themes + product ideas -> report
// The OpenAI key is typed in by the user, stays in this browser and is sent only to api.openai.com.

const API_URL = "https://api.openai.com/v1/chat/completions";
const MIN_POST_LENGTH = 20;     // shorter posts ("lol same") carry no useful signal
const MIN_POSTS = 3;            // with fewer posts there is nothing "common" to find
const STEP1_MAX_TOKENS = 2000;  // ~35 tokens per post, enough for ~50 posts
const TIMEOUT_MS = 60000;       // stop waiting after 60 s
const MAX_RETRIES = 3;          // like the Python SDK: retry timeouts, network errors, 429 and 5xx
const KEY_STORAGE = "pain-radar-openai-key";
// Opened through server.py: the key lives in .env on the laptop and requests go to /api/chat.
// Opened on GitHub Pages: there is no server, so the visitor types their own key.
let serverMode = null;

const DEMO_POSTS = `Why does every professor require a different $200 textbook that we use for maybe three chapters? I spent over $600 this semester and half the books are still in plastic.

Course registration opened at 7am and by 7:02 every section of Intro to Stats was full. The portal kept crashing and now I might have to graduate a semester late.

Just passed my organic chemistry final!! Studied for weeks and it actually paid off. Celebrating with pizza tonight.

My roommate stays up until 4am gaming with his headset volume on max. I have 8am classes and I'm running on four hours of sleep every night.

Group project update: four people in the group, one person (me) did the whole presentation. The other three replied "looks good" an hour before the deadline.

Does anyone know if the library is open on Thanksgiving weekend? Want to get some reading done.

The required online homework platform costs $120 on top of the textbook. Paying extra just to submit assignments feels like a scam.

Tip for freshmen: the second floor of the engineering building has empty study rooms almost all day. Nobody seems to know about them.

lol same

The dorm walls are paper thin. I can hear my neighbors' entire phone calls and there is construction outside starting at 7am every day. I cannot focus or sleep.

I had to email my advisor four times to get approval for a class I need. The waitlist system doesn't tell you your position, so you just refresh and pray.

Shoutout to the campus coffee shop for the new oat milk latte. Best thing that happened this week.

Why is the used textbook buyback only $8 for a book I paid $180 for? The bookstore resells it for $150 the next semester.

Group projects are the worst. Nobody answers in the group chat, we can't find a time to meet, and everyone gets the same grade anyway.

Anyone want to join a pickup basketball game on Friday evening at the rec center? We need two more players.

Got assigned a lab section that overlaps with my job shift and there is no other open section. The registration office says there is nothing they can do.
`;

const $ = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
// Posts and model answers are inserted as text, never as HTML
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

// An error whose message is written for the user
class UserError extends Error {}

// ---------- Pre-filter (no AI) ----------
function splitPosts(text) {
  return text.split(/\n\s*\n/).map((post) => post.trim()).filter((post) => post.length >= MIN_POST_LENGTH);
}

// ---------- LLM helpers ----------
function parseJson(raw) {
  const match = (raw || "").match(/\{[\s\S]*\}/);  // from the first "{" to the last "}"
  if (!match) throw new SyntaxError("The model did not return JSON.");
  return JSON.parse(match[0]);                      // throws SyntaxError if the JSON is broken
}

// One HTTP request with a timeout. Retries what a retry can fix, then explains the problem.
async function callApi(body, key) {
  for (let attempt = 0; ; attempt++) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
    let response;
    try {
      response = await fetch(serverMode ? "api/chat" : API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(serverMode ? {} : { Authorization: `Bearer ${key}` }) },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
    } catch (err) {
      if (err.name === "AbortError") {  // timeout: retry, then explain
        if (attempt < MAX_RETRIES) { await sleep(500 * 2 ** attempt); continue; }
        throw new UserError("OpenAI did not answer within 60 seconds, four times in a row. Check your connection and retry.");
      }
      if (!navigator.onLine) throw new UserError("No internet connection. Connect and press Analyze again.");
      if (attempt < 1) { await sleep(500); continue; }  // one retry for a short network glitch
      if (serverMode) throw new UserError("Cannot reach the Pain Radar server on the laptop. Is server.py still running?");
      // OpenAI answers a rejected key (401) without CORS headers, so the browser only sees a failed request
      throw new UserError("OpenAI refused the request. Most likely the API key is wrong or revoked: check the key above.");
    } finally {
      clearTimeout(timer);
    }
    if (response.ok) return response.json();
    if ((response.status === 429 || response.status >= 500) && attempt < MAX_RETRIES) {
      await sleep(1000 * 2 ** attempt);
      continue;
    }
    const details = (await response.json().catch(() => ({}))).error?.message || response.statusText;
    if (response.status === 401) {
      throw new UserError(serverMode ? "The API key was rejected. Check OPENAI_API_KEY in .env on the laptop and restart server.py."
                                     : "The API key was rejected. Check the key in the field above.");
    }
    if (response.status === 429) throw new UserError("Rate limit or quota exceeded. Wait a minute or check your OpenAI billing.");
    if (response.status >= 500) throw new UserError(`OpenAI is not available right now (error ${response.status}). Try again in a minute. Details: ${details}`);
    throw new UserError(`OpenAI error ${response.status}. Check the model names in Settings. Details: ${details}`);
  }
}

// One Chat Completions call in JSON mode. Broken JSON: ask once more, then give up.
async function askLlm(key, model, systemPrompt, userPrompt, temperature = 0, topP = 1, maxTokens = 1000) {
  for (const attempt of [1, 2]) {
    const data = await callApi({
      model,
      messages: [{ role: "system", content: systemPrompt }, { role: "user", content: userPrompt }],
      temperature, top_p: topP, max_tokens: maxTokens,
      response_format: { type: "json_object" },  // the model must answer with a JSON object
    }, key);
    const choice = data.choices?.[0];
    if (choice?.finish_reason === "length") {  // cut off: a retry would be cut off too
      throw new UserError("The answer was cut off by the max_tokens limit. Increase Max tokens (step 2) or use fewer posts (step 1).");
    }
    try {
      return parseJson(choice?.message?.content);
    } catch {
      if (attempt === 2) throw new UserError("The model returned broken JSON twice. Please try again.");
    }
  }
}

// ---------- LLM step 1: classification ----------
async function classifyPosts(key, posts, s) {
  const systemPrompt = CLASSIFY_SYSTEM + (s.fewShot ? FEW_SHOT_EXAMPLES : "");
  // temperature 0: one right answer per post, and the same post gets the same label every run
  const data = await askLlm(key, s.model1, systemPrompt, classifyUserPrompt(posts), 0, 1, STEP1_MAX_TOKENS);
  return data.results || [];
}

// ---------- LLM step 2: themes report ----------
async function findThemes(key, problems, s) {
  const data = await askLlm(key, s.model2, THEMES_SYSTEM, themesUserPrompt(problems, s.nThemes), s.temperature, s.topP, s.maxTokens);
  // the model does not always sort correctly, so we sort in code: most common theme first
  const themes = [...(data.themes || [])].sort((a, b) => (b.count || 0) - (a.count || 0));
  return { reasoning: data.reasoning || "", themes };
}

function makeReport(themes, reasoning, nPosts, nProblems, s) {
  const lines = ["# Pain Radar report\n", `Posts analyzed: ${nPosts}, posts with a problem: ${nProblems}\n`,
    `Settings: step 1 = ${s.model1} (${s.fewShot ? "Few-shot" : "Zero-shot"}), step 2 = ${s.model2}, ` +
    `temperature = ${s.temperature}, top_p = ${s.topP}, max_tokens = ${s.maxTokens}\n`];
  themes.forEach((t, i) => lines.push(`## ${i + 1}. ${t.name} (${t.count} posts)\n\n${t.description}\n\n` +
    `*Example:* ${t.example_problem}\n\n**Product idea:** ${t.product_idea}\n`));
  lines.push(`## How the model reasoned\n\n${reasoning}\n`);
  return lines.join("\n");
}

// ---------- Interface ----------
function readSettings() {
  return {
    model1: $("model1").value.trim(), model2: $("model2").value.trim(),
    fewShot: $("few-shot").checked,
    temperature: Number($("temperature").value), topP: Number($("top-p").value),
    maxTokens: Number($("max-tokens").value), nThemes: Number($("n-themes").value),
  };
}

function showMessage(kind, text) {  // kind: error | warning | info
  $("message").innerHTML = `<div class="msg ${kind}" role="${kind === "error" ? "alert" : "status"}">${esc(text)}</div>`;
}

function setBusy(text) {
  $("analyze").disabled = Boolean(text);
  $("progress").hidden = !text;
  $("progress-text").textContent = text || "";
}

function updateCount() {
  const n = splitPosts($("posts").value).length;
  $("count").textContent = n === 1 ? "1 post ready" : `${n} posts ready`;
}

function renderStep1(posts, results, problems) {
  const byId = new Map(results.map((r) => [r.id, r]));
  const share = Math.round((problems.length / posts.length) * 100);
  $("metrics").innerHTML = `
    <div><span class="v">${posts.length}</span><span class="l">posts analyzed</span></div>
    <div><span class="v">${problems.length}</span><span class="l">with a problem</span></div>
    <div><span class="v">${share}%</span><span class="l">problem share</span></div>`;
  $("sheet").innerHTML = posts.map((post, i) => {
    const r = byId.get(i + 1);
    if (!r) throw new TypeError("missing id");
    const text = r.is_problem ? `<mark class="hl">${esc(post)}</mark>` : esc(post);
    const note = r.is_problem ? `<div class="note">${esc(r.problem)}</div>` : `<div class="note quiet">Not a problem</div>`;
    return `<li class="post"><p>${text}</p>${note}</li>`;
  }).join("");
}

function renderStep2(themes, reasoning) {
  const max = Math.max(1, ...themes.map((t) => t.count || 0));
  $("themes").innerHTML = themes.map((t, i) => `
    <details class="theme" ${i === 0 ? "open" : ""}>
      <summary><span class="t-name">${i + 1}. ${esc(t.name)}</span>
        <span class="t-count"><span class="t-bar" style="width:${Math.round(((t.count || 0) / max) * 100)}%"></span>${esc(t.count)} posts</span></summary>
      <p>${esc(t.description)}</p>
      <p class="example"><span>Example</span> ${esc(t.example_problem)}</p>
      <p class="idea"><span>Product idea</span> <mark class="hl">${esc(t.product_idea)}</mark></p>
    </details>`).join("");
  $("reasoning").textContent = reasoning;
}

async function analyze() {
  $("message").innerHTML = "";
  $("results").hidden = true;
  $("step2").hidden = true;
  const key = $("api-key").value.trim();
  const posts = splitPosts($("posts").value);
  const s = readSettings();
  // Checks BEFORE calling the API: they cost nothing and give the clearest message
  if (serverMode && !serverMode.hasKey) return showMessage("error", "OPENAI_API_KEY is missing in .env on the laptop. Add it and restart server.py.");
  if (!serverMode && !key) return showMessage("error", "Paste your OpenAI API key above first. It stays in this browser.");
  if (posts.length < MIN_POSTS) {
    return showMessage("warning", `Found ${posts.length} posts. Pain Radar needs at least ${MIN_POSTS} posts ` +
      `(separated by a blank line, each at least ${MIN_POST_LENGTH} characters).`);
  }
  if (!serverMode) saveKey();
  try {
    setBusy(`Step 1 of 2: reading ${posts.length} posts with ${s.model1} (${s.fewShot ? "few-shot" : "zero-shot"})…`);
    const results = await classifyPosts(key, posts, s);
    const problems = results.filter((r) => r.is_problem).map((r) => r.problem);
    renderStep1(posts, results, problems);
    $("results").hidden = false;
    if (!problems.length) return showMessage("info", "No problems found in these posts, so there is nothing to group.");

    setBusy(`Step 2 of 2: grouping ${problems.length} problems into themes with ${s.model2}…`);
    const { reasoning, themes } = await findThemes(key, problems, s);
    renderStep2(themes, reasoning);
    $("step2").hidden = false;
    $("download").onclick = () => download(makeReport(themes, reasoning, posts.length, problems.length, s));
    $("results").scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  } catch (err) {
    showMessage("error", err instanceof UserError ? err.message : "The model's answer has an unexpected structure. Please try again.");
  } finally {
    setBusy("");
  }
}

function download(text) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/markdown" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: "pain_radar_report.md" });
  a.click();
  URL.revokeObjectURL(url);
}

// The key is remembered only if the user ticks the box, and only in this browser (localStorage)
function saveKey() {
  try {
    if ($("remember").checked) localStorage.setItem(KEY_STORAGE, $("api-key").value.trim());
    else localStorage.removeItem(KEY_STORAGE);
  } catch { /* storage blocked: the key simply is not remembered */ }
}

function init() {
  // Is the page served by server.py? Then hide the key field: the key stays in .env on the laptop.
  fetch("api/config").then((r) => (r.ok ? r.json() : null)).then((config) => {
    if (!config?.server) return;
    serverMode = { hasKey: config.has_key };
    $("key-field").hidden = true;
    $("server-note").hidden = false;
  }).catch(() => { /* GitHub Pages or a local file: the visitor types the key */ });

  try {
    const saved = localStorage.getItem(KEY_STORAGE);
    if (saved) { $("api-key").value = saved; $("remember").checked = true; }
  } catch { /* storage blocked */ }

  $("demo").addEventListener("click", () => { $("posts").value = DEMO_POSTS; updateCount(); });
  $("file").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (file) { $("posts").value = await file.text(); updateCount(); }
    e.target.value = "";
  });
  $("posts").addEventListener("input", updateCount);
  $("remember").addEventListener("change", saveKey);
  $("show-key").addEventListener("click", () => {
    const shown = $("api-key").type === "text";
    $("api-key").type = shown ? "password" : "text";
    $("show-key").textContent = shown ? "Show" : "Hide";
  });
  for (const id of ["temperature", "top-p", "max-tokens", "n-themes"]) {  // live values next to the sliders
    const update = () => { $(`${id}-value`).textContent = $(id).value; };
    $(id).addEventListener("input", update);
    update();
  }
  $("form").addEventListener("submit", (e) => { e.preventDefault(); analyze(); });
  updateCount();
}

init();
