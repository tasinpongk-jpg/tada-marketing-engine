/**
 * TADA marketing dashboard worker.
 *
 * Static assets served by the assets pipeline; one API route:
 *
 *   POST /api/chat   { messages: [{role, content}, ...] }
 *     -> { reply: "...", model: "..." }
 *
 * The assistant is grounded in the published content: every brand/*.md plus
 * the most recent reports, read back from the deployed assets so it answers
 * from exactly what the dashboard shows. Token-gated like the IS1 dashboard
 * (Authorization: Bearer <CHAT_TOKEN worker secret>). Inference: Cloudflare
 * Workers AI free-tier allocation.
 */

const CHAT_MODEL = "@cf/meta/llama-3.3-70b-instruct-fp8-fast";
const MAX_HISTORY = 12;
const MAX_USER_CHARS = 2000;
const MAX_DOC_CHARS = 3500;
const MAX_REPORTS = 6;

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/api/chat") {
      if (request.method !== "POST") {
        return json({ error: "POST only" }, 405);
      }
      try {
        return await handleChat(request, env, url.origin);
      } catch (e) {
        return json({ error: `chat failed: ${e.message}` }, 500);
      }
    }
    return env.ASSETS.fetch(request);
  },
};

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function authorized(request, env) {
  const header = request.headers.get("Authorization") || "";
  const token = header.replace(/^Bearer\s+/i, "").trim();
  return env.CHAT_TOKEN && token === env.CHAT_TOKEN;
}

async function loadText(env, origin, path) {
  const r = await env.ASSETS.fetch(new Request(`${origin}/content/${path}`));
  return r.ok ? r.text() : "";
}

async function buildContext(env, origin) {
  const mr = await env.ASSETS.fetch(new Request(`${origin}/content/manifest.json`));
  const m = mr.ok ? await mr.json() : { brand: [], reports: [] };
  const parts = [];
  for (const b of m.brand || []) {
    const text = await loadText(env, origin, `brand/${b.file}`);
    if (text) parts.push(`=== BRAND ASSET: ${b.file} ===\n${text.slice(0, MAX_DOC_CHARS)}`);
  }
  const recent = [...(m.reports || [])]
    .sort((a, b) => b.modified.localeCompare(a.modified))
    .slice(0, MAX_REPORTS);
  for (const r of recent) {
    const text = await loadText(env, origin, `reports/${r.file}`);
    if (text) parts.push(`=== REPORT (${r.modified}): ${r.file} ===\n${text.slice(0, MAX_DOC_CHARS)}`);
  }
  return parts.join("\n\n");
}

async function handleChat(request, env, origin) {
  if (!authorized(request, env)) return json({ error: "unauthorized" }, 401);
  const body = await request.json();
  const history = (body.messages || [])
    .filter((m) => m && (m.role === "user" || m.role === "assistant"))
    .slice(-MAX_HISTORY)
    .map((m) => ({ role: m.role, content: String(m.content).slice(0, MAX_USER_CHARS) }));
  if (!history.length) return json({ error: "no messages" }, 400);

  const system =
    "You are the marketing assistant on the TADA Thailand marketing " +
    "dashboard. TADA is the zero-commission ride-hailing challenger in " +
    "Bangkok (THB 20 flat fee, 0% driver commission) competing with Grab, " +
    "LINE MAN, Bolt and inDrive. Answer ONLY from the brand assets and " +
    "reports below — if the answer is not in them, say so plainly. Never " +
    "invent statistics. Reply in the language the user writes (Thai copy " +
    "should be casual ภาษาพูด). Any ad or broadcast copy you draft is a " +
    "DRAFT requiring human review. Be concise.\n\n" +
    (await buildContext(env, origin));

  const ai = await env.AI.run(CHAT_MODEL, {
    messages: [{ role: "system", content: system }, ...history],
    max_tokens: 800,
  });
  return json({ reply: (ai.response || "").trim(), model: CHAT_MODEL });
}
