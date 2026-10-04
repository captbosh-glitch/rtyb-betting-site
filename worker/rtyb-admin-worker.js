/**
 * Cloudflare Worker behind RTYB's Admin page (Matchups Tool + Results
 * Tool). Same shape as thebettorline's "Pull now" worker: the GitHub token
 * and the admin password both live as Worker secrets (`wrangler secret
 * put`, never in this file, never shipped to the browser) -- the static
 * admin page never sees either one, it only knows the password long enough
 * to send it in a header.
 *
 * Unlike the "Pull now" worker (which just fires a repository_dispatch and
 * lets a workflow do the real work), this one commits directly to small
 * JSON data files in the repo via GitHub's Contents API -- Save writes a
 * draft, Publish writes the file scripts/build_site.py actually merges
 * into the live site. Both are ordinary git commits on `main`, so your
 * existing refresh.yml push-trigger (once `data_admin/**` is added to its
 * paths list -- see the README note) picks them up and rebuilds within a
 * minute or two, same as any other change to template.html/scripts.
 *
 * Deploy:
 *   cd worker
 *   npm install -g wrangler      # if you don't have it
 *   wrangler secret put GITHUB_TOKEN      # fine-grained PAT, "Contents: write" only, scoped to this repo
 *   wrangler secret put ADMIN_SECRET      # the password the admin page prompts for
 *   wrangler secret put ANTHROPIC_API_KEY # only needed for the "Parse Odds Data with AI" field -- console.anthropic.com
 *   wrangler deploy
 * Then put the deployed URL into admin/index.html's WORKER_URL constant.
 *
 * Endpoints (all POST, all require header "X-Admin-Secret"):
 *   /matchups/save     body: {date, matchups: [{away,home,mlAway,mlHome,totalOver,totalUnder,bttsYes,bttsNo}, ...]}
 *   /matchups/publish   same body -- also writes data_admin/odds_overrides.json
 *   /matchups/parse      body: {date, text, games: [{away,home,awayName,homeName}, ...]} -- asks an LLM to pull
 *                         the six fields per matchup out of free-form pasted text; does NOT write anything,
 *                         just returns {ok, matchups} for the page to drop into the form
 *   /results/save       body: {date, results: [{away,home,awayScore,homeScore}, ...]}
 *   /results/publish    same body -- also writes data_admin/results_overrides.json
 */

const REPO_OWNER = "captbosh-glitch"; // TODO confirm this is the right GitHub org/user for this repo
const REPO_NAME = "rtyb-betting-site"; // TODO confirm this matches your actual repo name
const BRANCH = "main";

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*", // tighten to your site's origin once it has a custom domain, if you want
  "Access-Control-Allow-Headers": "Content-Type, X-Admin-Secret",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

function json(body, status) {
  return new Response(JSON.stringify(body), {
    status: status || 200,
    headers: { "Content-Type": "application/json", ...CORS_HEADERS },
  });
}

// --- base64 helpers (Workers don't have Node's Buffer) ---
function b64encode(str) {
  return btoa(unescape(encodeURIComponent(str)));
}
function b64decode(str) {
  return decodeURIComponent(escape(atob(str)));
}

async function ghRequest(env, path, options) {
  return fetch(`https://api.github.com/repos/${REPO_OWNER}/${REPO_NAME}/${path}`, {
    ...options,
    headers: {
      "Authorization": `Bearer ${env.GITHUB_TOKEN}`,
      "Accept": "application/vnd.github+json",
      "User-Agent": "rtyb-admin-worker",
      "X-GitHub-Api-Version": "2022-11-28",
      ...(options && options.headers),
    },
  });
}

// Read-modify-write a JSON file in the repo. `mutate(current)` gets the
// file's current parsed content (or {} if the file doesn't exist yet) and
// must return the new content to write. Returns {ok, status, detail}.
async function commitJsonFile(env, filePath, message, mutate) {
  const getResp = await ghRequest(env, `contents/${filePath}?ref=${BRANCH}`, { method: "GET" });

  let sha = undefined;
  let current = {};
  if (getResp.status === 200) {
    const info = await getResp.json();
    sha = info.sha;
    try {
      current = JSON.parse(b64decode(info.content.replace(/\n/g, "")));
    } catch {
      current = {};
    }
  } else if (getResp.status !== 404) {
    const text = await getResp.text();
    return { ok: false, status: getResp.status, detail: `GET ${filePath}: ${text.slice(0, 300)}` };
  }

  const updated = mutate(current);
  const putResp = await ghRequest(env, `contents/${filePath}`, {
    method: "PUT",
    body: JSON.stringify({
      message,
      content: b64encode(JSON.stringify(updated, null, 0)),
      branch: BRANCH,
      ...(sha ? { sha } : {}),
    }),
  });

  if (putResp.status === 200 || putResp.status === 201) {
    return { ok: true };
  }
  const text = await putResp.text();
  return { ok: false, status: putResp.status, detail: `PUT ${filePath}: ${text.slice(0, 300)}` };
}

function matchupKey(date, away, home) {
  return `${date}|${away}|${home}`;
}

function validateMatchups(body) {
  if (!body || typeof body.date !== "string" || !Array.isArray(body.matchups)) return "expected {date, matchups: []}";
  for (const m of body.matchups) {
    if (!m || typeof m.away !== "string" || typeof m.home !== "string") return "each matchup needs away/home codes";
  }
  return null;
}

function validateResults(body) {
  if (!body || typeof body.date !== "string" || !Array.isArray(body.results)) return "expected {date, results: []}";
  for (const r of body.results) {
    if (!r || typeof r.away !== "string" || typeof r.home !== "string") return "each result needs away/home codes";
  }
  return null;
}

// Save: stash this day's edited field values as a draft, keyed by matchup,
// so reloading the admin page (or coming back tomorrow) shows what was
// last typed in, even before Publish.
async function saveMatchupsDraft(env, body) {
  return commitJsonFile(env, "data_admin/matchups_draft.json", `Admin: save matchups draft ${body.date}`, (current) => {
    const dayMap = {};
    body.matchups.forEach((m) => {
      dayMap[`${m.away}|${m.home}`] = {
        mlHome: m.mlHome ?? null, mlAway: m.mlAway ?? null,
        totalOver: m.totalOver ?? null, totalUnder: m.totalUnder ?? null,
        bttsYes: m.bttsYes ?? null, bttsNo: m.bttsNo ?? null,
      };
    });
    return { ...current, [body.date]: dayMap };
  });
}

// Publish: same draft write, PLUS pushing the odds live via
// data_admin/odds_overrides.json, in the exact shape build_site.py already
// expects from an odds source (ml / totals / btts_yes / btts_no) -- it
// applies this one AFTER the normal fetched-odds merge, so a published
// admin value always wins.
async function publishMatchups(env, body) {
  const draftResult = await saveMatchupsDraft(env, body);
  if (!draftResult.ok) return draftResult;

  return commitJsonFile(env, "data_admin/odds_overrides.json", `Admin: publish matchups ${body.date}`, (current) => {
    const next = { ...current };
    body.matchups.forEach((m) => {
      const key = matchupKey(body.date, m.away, m.home);
      const entry = {};
      if (m.mlAway != null && m.mlHome != null) {
        entry.ml = { [m.away]: m.mlAway, [m.home]: m.mlHome };
      }
      if (m.totalOver != null && m.totalUnder != null) {
        entry.totals = { "1.5": { over: m.totalOver, under: m.totalUnder } };
      }
      if (m.bttsYes != null) entry.btts_yes = m.bttsYes;
      if (m.bttsNo != null) entry.btts_no = m.bttsNo;
      next[key] = entry;
    });
    return next;
  });
}

async function saveResultsDraft(env, body) {
  return commitJsonFile(env, "data_admin/results_draft.json", `Admin: save results draft ${body.date}`, (current) => {
    const dayMap = {};
    body.results.forEach((r) => {
      dayMap[`${r.away}|${r.home}`] = { awayScore: r.awayScore ?? null, homeScore: r.homeScore ?? null };
    });
    return { ...current, [body.date]: dayMap };
  });
}

// Publish: writes data_admin/results_overrides.json keyed the same way as
// odds_overrides.json. build_site.py merges awayP1/homeP1 from here onto
// the matching game, overriding whatever the live NHL schedule fetch has
// (or filling it in early, before the live fetcher would otherwise have a
// 1st-period score) -- that's the whole point of entering it by hand.
async function publishResults(env, body) {
  const draftResult = await saveResultsDraft(env, body);
  if (!draftResult.ok) return draftResult;

  return commitJsonFile(env, "data_admin/results_overrides.json", `Admin: publish results ${body.date}`, (current) => {
    const next = { ...current };
    body.results.forEach((r) => {
      if (r.awayScore == null || r.homeScore == null) return; // incomplete row, skip rather than publish a half result
      const key = matchupKey(body.date, r.away, r.home);
      next[key] = { awayP1: r.awayScore, homeP1: r.homeScore };
    });
    return next;
  });
}

function validateParse(body) {
  if (!body || typeof body.date !== "string" || typeof body.text !== "string" || !Array.isArray(body.games)) {
    return "expected {date, text, games: []}";
  }
  if (!body.text.trim()) return "text is empty";
  for (const g of body.games) {
    if (!g || typeof g.away !== "string" || typeof g.home !== "string") return "each game needs away/home codes";
  }
  return null;
}

// Asks Claude to pull the six odds fields per matchup out of whatever text
// was pasted in (a Google Sheets block, a picks message, anything). Doesn't
// touch the repo -- just returns parsed values for the admin page to drop
// into the Matchups Tool inputs, which are reviewed and Saved like any
// manual edit.
async function parseMatchupsWithAI(env, body) {
  if (!env.ANTHROPIC_API_KEY) {
    return { ok: false, status: 501, detail: "ANTHROPIC_API_KEY isn't set as a Worker secret yet -- wrangler secret put ANTHROPIC_API_KEY" };
  }

  const gameList = body.games
    .map((g) => `- away="${g.away}" (${g.awayName || g.away}), home="${g.home}" (${g.homeName || g.home})`)
    .join("\n");

  const prompt = `You extract 1st-period NHL betting odds from pasted text (it may be a spreadsheet dump, a picks/Discord message, or anything else) and match each game to one of the known matchups below.

Known matchups for ${body.date} (use these exact "away"/"home" codes in your output, don't invent new ones):
${gameList}

Pasted text:
"""
${body.text}
"""

For each matchup you can find odds for, extract:
- mlAway, mlHome: moneyline odds for the away/home team (e.g. -120, 135)
- totalOver, totalUnder: 1st-period Over/Under 1.5 goals odds
- bttsYes, bttsNo: Both Teams To Score odds

Rules:
- Only include a field if you actually found a number for it in the text -- use null, never guess or invent a value.
- Only include matchups from the known list above that you found data for. Skip matchups you can't find.
- Odds are plain numbers (no + sign in your output; negative numbers keep their -).
- Respond with ONLY a JSON object, no other text, no markdown fences, in this exact shape:
{"matchups": [{"away": "...", "home": "...", "mlAway": -120, "mlHome": 135, "totalOver": -130, "totalUnder": 100, "bttsYes": 155, "bttsNo": -205}]}`;

  let resp;
  try {
    resp = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-api-key": env.ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        // If a safety classifier declines the request, retry it server-side
        // on Anthropic's recommended fallback model instead of failing.
        "anthropic-beta": "server-side-fallback-2026-07-01",
      },
      body: JSON.stringify({
        model: "claude-sonnet-5-5",
        // Room for the model's thinking plus the JSON answer; a simple
        // extraction like this doesn't need deep reasoning, so effort is low.
        max_tokens: 16000,
        output_config: { effort: "low" },
        fallbacks: "default",
        messages: [{ role: "user", content: prompt }],
      }),
    });
  } catch (e) {
    return { ok: false, status: 502, detail: `Anthropic API request failed: ${e.message}` };
  }

  if (!resp.ok) {
    const text = await resp.text();
    return { ok: false, status: resp.status, detail: `Anthropic API: ${text.slice(0, 300)}` };
  }

  const data = await resp.json();
  if (data.stop_reason === "refusal") {
    return { ok: false, status: 502, detail: "The AI declined to parse this text -- try trimming it to just the odds, or enter them manually" };
  }
  if (data.stop_reason === "max_tokens") {
    return { ok: false, status: 502, detail: "The AI's response was cut off -- try pasting fewer games at once" };
  }
  // The response can start with thinking blocks; the answer is in the text block(s).
  const raw = (data.content || [])
    .filter((b) => b.type === "text")
    .map((b) => b.text)
    .join("");
  let parsed;
  try {
    // Strip accidental markdown fences just in case, then parse.
    const cleaned = raw.trim().replace(/^```(json)?/i, "").replace(/```$/, "").trim();
    parsed = JSON.parse(cleaned);
  } catch (e) {
    return { ok: false, status: 502, detail: `Couldn't parse the AI's response as JSON: ${raw.slice(0, 200)}` };
  }
  if (!parsed || !Array.isArray(parsed.matchups)) {
    return { ok: false, status: 502, detail: "AI response didn't contain a matchups array" };
  }
  return { ok: true, matchups: parsed.matchups };
}

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS_HEADERS });
    }
    if (request.method !== "POST") {
      return json({ ok: false, error: "Method not allowed" }, 405);
    }

    const providedSecret = request.headers.get("X-Admin-Secret") || "";
    if (!env.ADMIN_SECRET || providedSecret !== env.ADMIN_SECRET) {
      return json({ ok: false, error: "Unauthorized" }, 401);
    }

    let body;
    try {
      body = await request.json();
    } catch {
      return json({ ok: false, error: "Invalid JSON body" }, 400);
    }

    const url = new URL(request.url);
    let result;
    switch (url.pathname) {
      case "/matchups/save": {
        const err = validateMatchups(body);
        if (err) return json({ ok: false, error: err }, 400);
        result = await saveMatchupsDraft(env, body);
        break;
      }
      case "/matchups/publish": {
        const err = validateMatchups(body);
        if (err) return json({ ok: false, error: err }, 400);
        result = await publishMatchups(env, body);
        break;
      }
      case "/matchups/parse": {
        const err = validateParse(body);
        if (err) return json({ ok: false, error: err }, 400);
        const parseResult = await parseMatchupsWithAI(env, body);
        if (parseResult.ok) return json({ ok: true, matchups: parseResult.matchups });
        return json({ ok: false, error: parseResult.detail || "Parse failed", status: parseResult.status }, 502);
      }
      case "/results/save": {
        const err = validateResults(body);
        if (err) return json({ ok: false, error: err }, 400);
        result = await saveResultsDraft(env, body);
        break;
      }
      case "/results/publish": {
        const err = validateResults(body);
        if (err) return json({ ok: false, error: err }, 400);
        result = await publishResults(env, body);
        break;
      }
      default:
        return json({ ok: false, error: "Unknown endpoint" }, 404);
    }

    if (result.ok) return json({ ok: true });
    return json({ ok: false, error: result.detail || "GitHub commit failed", status: result.status }, 502);
  },
};
