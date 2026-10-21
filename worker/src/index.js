// Rhymer AI line writer — Cloudflare Worker using Workers AI.
// POST /lines {line, mood?, count?, syllables?, end_word?, rhymes?: [..], context?: "...", exclude?: [..]}
//   -> {lines: [...], model, ms}
// No secrets live in the client: the Workers AI binding (env.AI) is server-side only.
export const DEFAULT_MODEL = "@cf/meta/llama-3.1-8b-instruct-fp8";
export const LIMITS = { line: 200, context: 600, mood: 40, rhymes: 30, word: 24, exclude: 40, excludeLen: 200, bodyBytes: 8000 };
export const MOODS = ["any", "related", "love", "heartbreak", "night", "ocean", "nature", "weather", "city", "party", "money", "fire",
  "journey", "war", "faith", "time", "home", "food", "animals", "body", "music", "freedom", "hopeful", "dark", "nostalgic", "angry", "dreamy"];
const RATE = { perMinute: 12, perDay: 300 };
const hits = new Map(); // best-effort per-isolate limiter (plus optional RATE_LIMITER binding)

export function corsHeaders(origin, env) {
  const allowed = (env.ALLOWED_ORIGINS || "https://christophbria-ship-it.github.io").split(",").map(s => s.trim());
  const h = { "Vary": "Origin", "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store",
              "X-Content-Type-Options": "nosniff" };
  if (origin && allowed.includes(origin)) Object.assign(h, { "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Methods": "POST, OPTIONS, GET", "Access-Control-Allow-Headers": "Content-Type", "Access-Control-Max-Age": "86400" });
  return h;
}
const json = (status, body, headers) => new Response(JSON.stringify(body), { status, headers });

export function rateLimit(ip, now = Date.now()) {
  const rec = hits.get(ip) || { min: [], day: 0, dayStart: now };
  if (now - rec.dayStart > 86400000) { rec.day = 0; rec.dayStart = now; }
  rec.min = rec.min.filter(t => now - t < 60000);
  if (rec.min.length >= RATE.perMinute || rec.day >= RATE.perDay) { hits.set(ip, rec); return false; }
  rec.min.push(now); rec.day++; hits.set(ip, rec);
  if (hits.size > 5000) for (const k of hits.keys()) { hits.delete(k); if (hits.size < 4000) break; }
  return true;
}
export function _resetRate() { hits.clear(); }

const WORD = /^[a-z][a-z'\-]{0,23}$/;
export function validate(b) {
  if (!b || typeof b !== "object") return "body must be a JSON object";
  if (typeof b.line !== "string" || !b.line.trim()) return "'line' is required";
  if (b.line.length > LIMITS.line) return `'line' must be at most ${LIMITS.line} characters`;
  if (b.context != null && (typeof b.context !== "string" || b.context.length > LIMITS.context)) return `'context' must be a string of at most ${LIMITS.context} characters`;
  if (b.mood != null && (typeof b.mood !== "string" || !MOODS.includes(b.mood))) return "unknown 'mood'";
  if (b.count != null && !(Number.isInteger(b.count) && b.count >= 1 && b.count <= 8)) return "'count' must be 1-8";
  if (b.syllables != null && !(Number.isInteger(b.syllables) && b.syllables >= 1 && b.syllables <= 40)) return "'syllables' must be 1-40";
  if (b.end_word != null && (typeof b.end_word !== "string" || !WORD.test(b.end_word))) return "invalid 'end_word'";
  if (b.rhymes != null && (!Array.isArray(b.rhymes) || b.rhymes.length > LIMITS.rhymes || !b.rhymes.every(w => typeof w === "string" && WORD.test(w)))) return "invalid 'rhymes'";
  if (b.exclude != null && (!Array.isArray(b.exclude) || b.exclude.length > LIMITS.exclude || !b.exclude.every(s => typeof s === "string" && s.length <= LIMITS.excludeLen))) return "invalid 'exclude'";
  return null;
}

export function lastWord(line) { const m = line.toLowerCase().match(/[a-z][a-z']*(?:-[a-z']+)*/g); return m ? m[m.length - 1].replace(/^'+|'+$/g, "") : ""; }

export function buildMessages(b) {
  const n = b.count || 6, end = b.end_word || lastWord(b.line);
  const mood = b.mood && b.mood !== "any" && b.mood !== "related" ? ` The mood/theme is "${b.mood}".` : "";
  const syl = b.syllables ? ` about ${b.syllables} syllables each (similar length to the input line)` : " a similar length to the input line";
  const hints = b.rhymes && b.rhymes.length ? `\nGood rhymes for "${end}" to end lines with: ${b.rhymes.join(", ")}.` : "";
  const ctx = b.context ? `\nEarlier lyrics for context:\n${b.context}` : "";
  const avoid = b.exclude && b.exclude.length ? `\nDo not repeat any of these lines:\n${b.exclude.map(s => "- " + s).join("\n")}` : "";
  return [
    { role: "system", content: "You are a skilled songwriter helping write lyrics for Suno AI songs. You write natural, singable, " +
      "emotionally vivid lines in plain modern English. You never explain; you only output the requested JSON." },
    { role: "user", content: `Input lyric line: "${b.line.trim()}"${ctx}\n\nWrite ${n} different possible NEXT lines for this song.` +
      ` Each line must END with a word that rhymes or near-rhymes with "${end}", and have${syl}.${mood}` +
      ` Vary the imagery; no repeated endings; no numbering; no quotes around the lines; no [section tags].${hints}${avoid}\n\n` +
      `Reply with ONLY a JSON array of ${n} strings.` },
  ];
}

export function parseLines(text, input, exclude = []) {
  let arr = null;
  const m = String(text || "").match(/\[[\s\S]*\]/);
  if (m) { try { const j = JSON.parse(m[0]); if (Array.isArray(j)) arr = j.filter(x => typeof x === "string"); } catch (e) {} }
  if (!arr) arr = String(text || "").split(/\n+/);
  const seen = new Set([input, ...exclude].map(s => s.trim().toLowerCase()));
  const out = [];
  for (let s of arr) {
    s = s.replace(/^\s*(?:[-*•]|\d+[.):])\s*/, "").replace(/^["'“”‘’]+|["'“”‘’,]+$/g, "").replace(/\s+/g, " ").trim();
    if (!s || s.length > 140 || /^\[.*\]$/.test(s) || /^(here are|sure|okay)\b/i.test(s) || !/[a-z]/i.test(s)) continue;
    const k = s.toLowerCase(); if (seen.has(k)) continue; seen.add(k); out.push(s);
  }
  return out.slice(0, 8);
}

export default {
  async fetch(req, env, ctx) {
    const url = new URL(req.url), origin = req.headers.get("Origin") || "", h = corsHeaders(origin, env);
    const allowedOrigin = "Access-Control-Allow-Origin" in h;
    if (req.method === "OPTIONS") return new Response(null, { status: allowedOrigin ? 204 : 403, headers: h });
    if (url.pathname === "/health" && req.method === "GET") return json(200, { ok: true, model: env.MODEL || DEFAULT_MODEL }, h);
    if (url.pathname !== "/lines") return json(404, { error: "not found" }, h);
    if (req.method !== "POST") return json(405, { error: "use POST" }, h);
    // browsers always send Origin on cross-site POSTs; reject foreign origins (server-side proxies may send none + shared key)
    if (origin && !allowedOrigin) return json(403, { error: "origin not allowed" }, h);
    if (!origin && !(env.PROXY_KEY && req.headers.get("X-Rhymer-Key") === env.PROXY_KEY)) return json(403, { error: "origin required" }, h);
    const ip = req.headers.get("CF-Connecting-IP") || "anon";
    if (env.RATE_LIMITER) { const { success } = await env.RATE_LIMITER.limit({ key: ip }); if (!success) return json(429, { error: "rate limited, try again in a minute" }, h); }
    if (!rateLimit(ip)) return json(429, { error: "rate limited, try again in a minute" }, h);
    const raw = await req.text();
    if (raw.length > LIMITS.bodyBytes) return json(413, { error: "request too large" }, h);
    let b; try { b = JSON.parse(raw); } catch (e) { return json(400, { error: "invalid JSON" }, h); }
    const err = validate(b); if (err) return json(400, { error: err }, h);
    const t0 = Date.now(), model = env.MODEL || DEFAULT_MODEL;
    try {
      const r = await env.AI.run(model, { messages: buildMessages(b), max_tokens: 400, temperature: 0.9, top_p: 0.95 });
      const lines = parseLines(r && (r.response ?? r.result?.response), b.line, b.exclude || []);
      if (!lines.length) return json(502, { error: "model returned no usable lines" }, h);
      return json(200, { lines, model, ms: Date.now() - t0 }, h);
    } catch (e) {
      const quota = /quota|limit|neurons|4006|3036/i.test(String(e && e.message));
      return json(quota ? 429 : 502, { error: quota ? "daily AI quota reached, try again tomorrow" : "AI service error" }, h);
    }
  },
};
