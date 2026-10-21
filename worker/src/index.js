// Rhymer AI — Cloudflare Worker using Workers AI.
//   GET|POST /lines       {line, mood?, count?(1-30), syllables?, end_word?, rhymes?, context?, exclude?, seed?}
//       -> {lines: [...up to 30 candidates], model, ms}          (the app re-scores them with its rhyme engine)
//   GET|POST /brainstorm  {word, mood?, context?}
//       -> {perfect: [...], multi: [...], slant: [...], phrases: [...], model, ms}
//   GET /health
// GET requests carry the JSON body in ?q= so identical requests are answered by Workers Cache (7 days) without
// running the model again; an in-isolate LRU catches repeats too. No secrets in the client: env.AI is server-side.
export const DEFAULT_MODEL = "@cf/meta/llama-3.3-70b-instruct-fp8-fast";
export const LIMITS = { line: 200, context: 600, mood: 40, rhymes: 40, word: 24, exclude: 60, excludeLen: 200, bodyBytes: 12000, count: 30 };
export const MOODS = ["any", "related", "love", "heartbreak", "night", "ocean", "nature", "weather", "city", "party", "money", "fire",
  "journey", "war", "faith", "time", "home", "food", "animals", "body", "music", "freedom", "hopeful", "dark", "nostalgic", "angry", "dreamy"];
const RATE = { perMinute: 20, perDay: 400 };
const CACHE_TTL = 604800;
const hits = new Map(); // best-effort per-isolate limiter (plus optional RATE_LIMITER binding)
const memo = new Map(); // tiny per-isolate LRU of model results

export function corsHeaders(origin, env) {
  const allowed = (env.ALLOWED_ORIGINS || "https://christophbria-ship-it.github.io").split(",").map(s => s.trim());
  const h = { "Vary": "Origin", "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" };
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
export function _resetRate() { hits.clear(); memo.clear(); }

const WORD = /^[a-z][a-z'\-]{0,23}$/;
const isStrArr = (a, n, len) => Array.isArray(a) && a.length <= n && a.every(s => typeof s === "string" && s.length <= len);
export function validate(b) {
  if (!b || typeof b !== "object" || Array.isArray(b)) return "body must be a JSON object";
  if (typeof b.line !== "string" || !b.line.trim()) return "'line' is required";
  if (b.line.length > LIMITS.line) return `'line' must be at most ${LIMITS.line} characters`;
  if (b.context != null && (typeof b.context !== "string" || b.context.length > LIMITS.context)) return `'context' must be a string of at most ${LIMITS.context} characters`;
  if (b.mood != null && (typeof b.mood !== "string" || !MOODS.includes(b.mood))) return "unknown 'mood'";
  if (b.count != null && !(Number.isInteger(b.count) && b.count >= 1 && b.count <= LIMITS.count)) return `'count' must be 1-${LIMITS.count}`;
  if (b.syllables != null && !(Number.isInteger(b.syllables) && b.syllables >= 1 && b.syllables <= 40)) return "'syllables' must be 1-40";
  if (b.end_word != null && (typeof b.end_word !== "string" || !WORD.test(b.end_word))) return "invalid 'end_word'";
  if (b.rhymes != null && !(isStrArr(b.rhymes, LIMITS.rhymes, 40) && b.rhymes.every(w => /^[a-z][a-z' \-]{0,39}$/.test(w)))) return "invalid 'rhymes'";
  if (b.exclude != null && !isStrArr(b.exclude, LIMITS.exclude, LIMITS.excludeLen)) return "invalid 'exclude'";
  if (b.seed != null && !(Number.isInteger(b.seed) && b.seed >= 0 && b.seed < 1000)) return "invalid 'seed'";
  if (b.judge != null && typeof b.judge !== "boolean") return "invalid 'judge'";
  if (b.rhythm != null && !(typeof b.rhythm === "string" && /^[A-Za-z \-]{1,160}$/.test(b.rhythm))) return "invalid 'rhythm'";
  if (b.echo != null && !(b.echo && typeof b.echo === "object" && typeof b.echo.word === "string" && WORD.test(b.echo.word) &&
      isStrArr(b.echo.words, 16, 24) && b.echo.words.every(w => WORD.test(w)))) return "invalid 'echo'";
  return null;
}
export function validateBrainstorm(b) {
  if (!b || typeof b !== "object" || Array.isArray(b)) return "body must be a JSON object";
  if (typeof b.word !== "string" || !WORD.test(b.word)) return "invalid 'word'";
  if (b.mood != null && (typeof b.mood !== "string" || !MOODS.includes(b.mood))) return "unknown 'mood'";
  if (b.context != null && (typeof b.context !== "string" || b.context.length > 300)) return "'context' must be a string of at most 300 characters";
  return null;
}

export function lastWord(line) { const m = line.toLowerCase().match(/[a-z][a-z']*(?:-[a-z']+)*/g); return m ? m[m.length - 1].replace(/^'+|'+$/g, "") : ""; }
const tailWords = (line, n) => (line.toLowerCase().match(/[a-z][a-z']*(?:-[a-z']+)*/g) || []).slice(-n).join(" ");
const CLICHES = "heart of gold, deep inside, end of time, set me free, shining star, burning bright, dreams come true, by my side, touch the sky, lost in your eyes, whispers in the wind, dance in the rain";

export function buildMessages(b) {
  const n = b.count || 6, end = b.end_word || lastWord(b.line), tail2 = tailWords(b.line, 2);
  const mood = b.mood && b.mood !== "any" && b.mood !== "related" ? `\nMood / theme: ${b.mood}.` : "";
  const syl = (b.syllables ? `HARD LIMIT ${Math.max(1, b.syllables - 1)}-${b.syllables + 1} syllables per line (the previous line has ${b.syllables}) — count them; longer lines are thrown away` : "the same number of syllables as the previous line (±1)") +
    (b.rhythm ? `; the previous line's stress pattern is ${b.rhythm}, so mirror its beat` : "");
  const hints = b.rhymes && b.rhymes.length ? `\nTrue rhymes for "${end}" that fit the theme (use only if they make sense, or find better ones): ${b.rhymes.join(", ")}.` : "";
  const echo = b.echo && b.echo.words && b.echo.words.length ? `\nWords with the same vowel sounds as "${b.echo.word}" — use them to build a multi-syllable rhyme on "${b.echo.word} ${end}" (e.g. "${b.echo.words[0]} <rhyme for ${end}>") or internal rhymes: ${b.echo.words.join(", ")}.` : "";
  const ctx = b.context ? `\nEarlier lyrics (for story and tone):\n${b.context}` : "";
  const avoid = b.exclude && b.exclude.length ? `\nAlready suggested — write different lines with different end words:\n${b.exclude.map(s => "- " + s).join("\n")}` : "";
  return [
    { role: "system", content: "You are a hit songwriter and rap ghostwriter writing lyrics for Suno AI songs (pop, hip-hop, R&B, rock, country). " +
      "Your lines are singable, concrete and fresh: vivid images, specific nouns, strong verbs, internal rhymes and multi-syllable end rhymes " +
      "like the best writers. The standard you write to (previous line -> next line):\n" +
      "\"I was raised behind a broken door\" -> \"slept through thunder on the kitchen floor\"\n" +
      "\"city lights are fading out of view\" -> \"every highway sign points back to you\"\n" +
      "\"we were dancing in the rain\" -> \"laughing at the hurricane\"\n" +
      "Every line is a complete, natural sentence a listener understands on first hearing. You never explain; you output only JSON." },
    { role: "user", content: `Previous lyric line: "${b.line.trim()}"${ctx}${mood}\n\nWrite ${n} different candidate NEXT lines.\n` +
      `1. END RHYME (most important): every line must END on a word or phrase that truly rhymes with "${end}" (same stressed vowel AND same ending sound). ` +
      `Best of all: multi-syllable rhymes that echo the vowel sounds of the last syllables "${tail2}" vowel for vowel. ` +
      `Never end on filler (though, so, too, oh, yeah, it, now, then), never end on "${end}" itself, and don't reuse an end word. ` +
      `Never force a rhyme: every line must make sense and sound like something a real artist would sing. ` +
      `Work backwards: choose a strong rhyme word or phrase first, then build the whole line so it lands there naturally and grammatically ` +
      `(a noun after "the/a/my", a verb where a verb belongs; e.g. for "drum": "till the feeling in my chest goes numb" — never nonsense like "snapping to the succumb").\n` +
      `2. RHYTHM: ${syl}, natural stress, easy to sing.\n` +
      `3. CRAFT: concrete imagery (sights, sounds, textures, places, objects), active verbs, an internal rhyme or assonance chain where it flows. ` +
      `No clichés (${CLICHES}).\n4. VARIETY: mix angles — a story detail, a feeling, an image, a punchline or twist. No two lines alike.${hints}${echo}${avoid}\n\n` +
      `Reply with ONLY a JSON array of ${n} strings.` },
  ];
}
export function buildJudge(b, lines) {
  return [
    { role: "system", content: "You are a strict, experienced lyric editor at a major label. You output only JSON." },
    { role: "user", content: `Previous lyric line: "${b.line.trim()}"\nCandidate next lines:\n${lines.map((l, i) => `${i + 1}. ${l}`).join("\n")}\n\n` +
      `Score each candidate 0-10 as a next line a top songwriter would keep. Be harsh: most candidates deserve 3-6; 9-10 only for lines good enough for a hit record. ` +
      `Check: it makes literal or poetic sense, grammar is natural (no missing words, no odd word order), ` +
      `the final rhyme word lands naturally (forced, odd or nonsense rhyme words like "kneading bread with hands of dough" score 0-3), ` +
      `vivid and fresh imagery scores higher, clichés lower. Reply with ONLY a JSON array of ${lines.length} integers in the same order.` },
  ];
}
export function parseJudge(text, n) {
  const m = String(text || "").match(/\[[\s\S]*?\]/); if (!m) return null;
  let a; try { a = JSON.parse(m[0]); } catch (e) { return null; }
  if (!Array.isArray(a) || a.length !== n || !a.every(x => typeof x === "number" && isFinite(x))) return null;
  return a.map(x => Math.max(0, Math.min(10, Math.round(x))));
}
export function buildBrainstorm(b) {
  const mood = b.mood && b.mood !== "any" && b.mood !== "related" ? ` Mood / theme: ${b.mood}.` : "";
  const ctx = b.context ? ` Context: "${b.context}".` : "";
  return [
    { role: "system", content: "You are a rhyming dictionary with a hit songwriter's and rapper's ear. You output only JSON." },
    { role: "user", content: `Word: "${b.word}".${mood}${ctx}\nBrainstorm the rhymes a skilled rapper or pop songwriter would reach for with "${b.word}", ` +
      `favouring words connected to its meaning, imagery and emotions. Return one JSON object with these keys:\n` +
      `"perfect": 30 single words that perfectly rhyme with "${b.word}" (same stressed vowel and same ending sound),\n` +
      `"multi": 20 multi-syllable or compound rhymes — longer words or 2-3 word phrases whose final syllables rhyme with "${b.word}" (e.g. for "snow": "let it go", "below", "overflow"),\n` +
      `"slant": 20 slant / assonance rhymes (same stressed vowel, similar ending),\n` +
      `"phrases": 30 vivid 2-5 word lyric phrases that END with a rhyme for "${b.word}" and evoke its theme.\n` +
      `Lowercase, no explanations, ONLY the JSON object.` },
  ];
}

export function modelText(r) {
  if (!r) return "";
  if (typeof r === "string") return r;
  if (typeof r.response === "string") return r.response;
  if (r.response && typeof r.response === "object") return JSON.stringify(r.response);
  if (r.choices && r.choices[0]) return (r.choices[0].message && r.choices[0].message.content) || r.choices[0].text || "";
  if (Array.isArray(r.output)) return r.output.flatMap(o => (o.content || []).filter(c => c.type === "output_text").map(c => c.text)).join("\n");
  if (r.result) return modelText(r.result);
  return "";
}
const clean = s => s.replace(/^\s*(?:[-*•]|\d+[.):])\s*/, "").replace(/^["'“”‘’]+|["'“”‘’,]+$/g, "").replace(/\s+/g, " ").trim();
export function parseLines(text, input, exclude = [], max = LIMITS.count) {
  let arr = null;
  const m = String(text || "").match(/\[[\s\S]*\]/);
  if (m) { try { const j = JSON.parse(m[0]); if (Array.isArray(j)) arr = j.filter(x => typeof x === "string"); } catch (e) {} }
  if (!arr) arr = String(text || "").split(/\n+/);
  const seen = new Set([input, ...exclude].map(s => s.trim().toLowerCase()));
  const out = [];
  for (let s of arr) {
    s = clean(s);
    if (!s || s.length > 140 || /^\[.*\]$/.test(s) || /^(here are|sure|okay)\b/i.test(s) || !/[a-z]/i.test(s)) continue;
    const k = s.toLowerCase(); if (seen.has(k)) continue; seen.add(k); out.push(s);
  }
  return out.slice(0, max);
}
export function parseBrainstorm(text, word) {
  const out = { perfect: [], multi: [], slant: [], phrases: [] };
  const m = String(text || "").match(/\{[\s\S]*\}/); let j = null;
  if (m) { try { j = JSON.parse(m[0]); } catch (e) { j = null; } }
  if (!j || typeof j !== "object") return out;
  const seen = new Set([word]); let total = 0;
  for (const k of Object.keys(out)) {
    const arr = Array.isArray(j[k]) ? j[k] : [];
    for (let s of arr) {
      if (typeof s !== "string") continue;
      s = clean(s).toLowerCase().replace(/[^a-z' \-]/g, "").replace(/\s+/g, " ").trim();
      if (!s || s.length > 60 || s.split(" ").length > 6 || seen.has(s) || total >= 190) continue;
      seen.add(s); out[k].push(s); total++;
    }
  }
  return out;
}

async function readBody(req, url) {
  if (req.method === "GET") { const q = url.searchParams.get("q"); if (q == null) return [400, "missing ?q="]; if (q.length > LIMITS.bodyBytes) return [413]; return [0, q]; }
  const raw = await req.text(); if (raw.length > LIMITS.bodyBytes) return [413]; return [0, raw];
}
async function runModel(env, model, messages, max_tokens, temperature) {
  const input = { messages, max_tokens, temperature, top_p: 0.95 };
  if (/gpt-oss/.test(model)) input.reasoning = { effort: "low" };
  return modelText(await env.AI.run(model, input));
}

export default {
  async fetch(req, env, ctx) {
    const url = new URL(req.url), origin = req.headers.get("Origin") || "", h = corsHeaders(origin, env);
    const allowedOrigin = "Access-Control-Allow-Origin" in h;
    if (req.method === "OPTIONS") return new Response(null, { status: allowedOrigin ? 204 : 403, headers: h });
    const model = env.MODEL || DEFAULT_MODEL;
    if (url.pathname === "/health" && req.method === "GET") return json(200, { ok: true, model }, h);
    const kind = url.pathname === "/lines" ? "lines" : url.pathname === "/brainstorm" ? "brainstorm" : null;
    if (!kind) return json(404, { error: "not found" }, h);
    if (req.method !== "POST" && req.method !== "GET") return json(405, { error: "use GET or POST" }, h);
    if (req.method === "GET" && !url.searchParams.has("q")) return json(405, { error: "use POST, or GET with ?q=" }, h);
    // browsers always send Origin on cross-site requests; reject foreign origins (server-side proxies may send none + shared key)
    if (origin && !allowedOrigin) return json(403, { error: "origin not allowed" }, h);
    if (!origin && !(env.PROXY_KEY && req.headers.get("X-Rhymer-Key") === env.PROXY_KEY)) return json(403, { error: "origin required" }, h);
    const [bad, raw] = await readBody(req, url);
    if (bad === 413) return json(413, { error: "request too large" }, h);
    if (bad) return json(bad, { error: raw }, h);
    let b; try { b = JSON.parse(raw); } catch (e) { return json(400, { error: "invalid JSON" }, h); }
    const err = kind === "lines" ? validate(b) : validateBrainstorm(b); if (err) return json(400, { error: err }, h);
    const key = kind + ":" + JSON.stringify(b);
    const cacheable = req.method === "GET";
    const okHeaders = cacheable ? { ...h, "Cache-Control": `public, max-age=${CACHE_TTL}` } : h;
    if (memo.has(key)) { const v = memo.get(key); memo.delete(key); memo.set(key, v); return json(200, { ...v, cached: true }, okHeaders); }
    const ip = req.headers.get("CF-Connecting-IP") || "anon";
    if (env.RATE_LIMITER) { const { success } = await env.RATE_LIMITER.limit({ key: ip }); if (!success) return json(429, { error: "rate limited, try again in a minute" }, h); }
    if (!rateLimit(ip)) return json(429, { error: "rate limited, try again in a minute" }, h);
    const t0 = Date.now();
    try {
      let body;
      if (kind === "lines") {
        const n = b.count || 6;
        const text = await runModel(env, model, buildMessages(b), Math.min(1600, 120 + n * 34), 0.85 + 0.01 * ((b.seed || 0) % 10));
        const lines = parseLines(text, b.line, b.exclude || []);
        if (!lines.length) return json(502, { error: "model returned no usable lines" }, h);
        body = { lines, model };
        // editor pass: the model is a better judge than writer — score sense / naturalness of every candidate (cheap: ~4 tokens per line)
        if (b.judge !== false && lines.length >= 2) {
          try { const sense = parseJudge(await runModel(env, model, buildJudge(b, lines), 20 + 5 * lines.length, 0), lines.length); if (sense) body.sense = sense; } catch (e) { /* non-fatal */ }
        }
      } else {
        const text = await runModel(env, model, buildBrainstorm(b), 1400, 0.7);
        const r = parseBrainstorm(text, b.word);
        if (!Object.values(r).some(a => a.length)) return json(502, { error: "model returned no usable rhymes" }, h);
        body = { ...r, model };
      }
      memo.set(key, body); if (memo.size > 300) memo.delete(memo.keys().next().value);
      return json(200, { ...body, ms: Date.now() - t0 }, okHeaders);
    } catch (e) {
      const quota = /quota|limit|neurons|4006|3036/i.test(String(e && e.message));
      return json(quota ? 429 : 502, { error: quota ? "daily AI quota reached, try again tomorrow" : "AI service error" }, h);
    }
  },
};
