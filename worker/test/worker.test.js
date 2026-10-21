import test from "node:test";
import assert from "node:assert/strict";
import worker, { parseLines, parseBrainstorm, validate, validateBrainstorm, buildMessages, buildBrainstorm, lastWord, modelText, _resetRate, corsHeaders } from "../src/index.js";
const ORIGIN = "https://christophbria-ship-it.github.io";
const env = (resp, opts = {}) => { const e = { ...opts, calls: 0 }; e.AI = { run: async (model, input) => { e.calls++; e.last = { model, input }; if (resp instanceof Error) throw resp; return typeof resp === "object" ? resp : { response: resp }; } }; return e; };
const req = (body, { origin = ORIGIN, method = "POST", path = "/lines", ip = "1.1.1.1" } = {}) =>
  new Request("https://rhymer-ai.example.workers.dev" + path, { method, headers: { "Content-Type": "application/json", ...(origin ? { Origin: origin } : {}), "CF-Connecting-IP": ip },
    body: method === "POST" ? (typeof body === "string" ? body : JSON.stringify(body)) : undefined });
const get = (path, body, opts = {}) => req(null, { ...opts, method: "GET", path: path + "?q=" + encodeURIComponent(JSON.stringify(body)) });
const LINES = '["The world is hushed and white below", "Our footprints fading as we go", "I feel the winter wind blow", "Your hand in mine, the embers glow", "Here are lines", "The world is hushed and white below"]';

test("happy path returns cleaned, deduped lines with CORS for the Pages origin; prompt carries the craft rules", async () => {
  _resetRate(); const e = env(LINES);
  const r = await worker.fetch(req({ line: "walking through the falling snow", mood: "love", syllables: 8, count: 24, rhymes: ["glow", "go"], rhythm: "DUM-da DUM da DUM-da DUM",
    echo: { word: "falling", words: ["calling", "crawling"] } }), e);
  assert.equal(r.status, 200); assert.equal(r.headers.get("Access-Control-Allow-Origin"), ORIGIN); assert.equal(r.headers.get("Cache-Control"), "no-store");
  const d = await r.json(); assert.deepEqual(d.lines, ["The world is hushed and white below", "Our footprints fading as we go", "I feel the winter wind blow", "Your hand in mine, the embers glow"]);
  const u = e.last.input.messages[1].content;
  assert.match(u, /truly rhymes with "snow"/); assert.match(u, /8 syllables \(±1\)/); assert.match(u, /multi-syllable rhymes .* "falling snow"/);
  assert.match(u, /glow, go/); assert.match(u, /love/); assert.match(u, /calling, crawling/); assert.match(u, /DUM-da DUM/); assert.match(u, /Never end on filler/);
  assert.match(u, /Write 24 different/); assert.equal(e.last.model, "@cf/meta/llama-3.3-70b-instruct-fp8-fast");
});
test("GET ?q= is cacheable (Workers Cache) and repeats are served from the in-isolate memo without calling the model", async () => {
  _resetRate(); const e = env(LINES);
  const r1 = await worker.fetch(get("/lines", { line: "walking through the falling snow", count: 12 }), e);
  assert.equal(r1.status, 200); assert.match(r1.headers.get("Cache-Control"), /public, max-age=604800/);
  const r2 = await worker.fetch(get("/lines", { line: "walking through the falling snow", count: 12 }), e);
  assert.equal((await r2.json()).cached, true); assert.equal(e.calls, 1);
  assert.equal((await worker.fetch(req(null, { method: "GET" }), e)).status, 405);
  const bad = await worker.fetch(get("/lines", { line: "" }), e); assert.equal(bad.status, 400); assert.equal(bad.headers.get("Cache-Control"), "no-store");
});
test("brainstorm returns grouped, cleaned rhymes", async () => {
  _resetRate();
  const e = env('Sure! {"perfect":["glow","Flow","snow","<b>"],"multi":["let it go","below"],"slant":["cold"],"phrases":["white glow", 5, "' + "x".repeat(70) + '"]}');
  const r = await worker.fetch(get("/brainstorm", { word: "snow", mood: "night" }), e);
  assert.equal(r.status, 200); const d = await r.json();
  assert.deepEqual(d.perfect, ["glow", "flow", "b"]); assert.deepEqual(d.multi, ["let it go", "below"]); assert.deepEqual(d.slant, ["cold"]); assert.deepEqual(d.phrases, ["white glow"]);
  assert.match(e.last.input.messages[1].content, /Word: "snow"/); assert.match(e.last.input.messages[1].content, /night/);
  assert.equal((await worker.fetch(get("/brainstorm", { word: "Not A Word!" }), e)).status, 400);
  assert.equal((await worker.fetch(get("/brainstorm", { word: "snow" }), env("no json here"))).status, 502);
});
test("foreign origin and missing origin are rejected; preflight", async () => {
  _resetRate();
  assert.equal((await worker.fetch(req({ line: "x y" }, { origin: "https://evil.example" }), env(LINES))).status, 403);
  assert.equal((await worker.fetch(get("/lines", { line: "x y" }, { origin: "https://evil.example" }), env(LINES))).status, 403);
  assert.equal((await worker.fetch(req({ line: "x y" }, { origin: "" }), env(LINES))).status, 403);
  assert.equal((await worker.fetch(req({ line: "x y" }, { origin: "" }), Object.assign(env(LINES), { PROXY_KEY: "k" }))).status, 403);
  const pre = await worker.fetch(new Request("https://w/lines", { method: "OPTIONS", headers: { Origin: ORIGIN } }), env(LINES));
  assert.equal(pre.status, 204); assert.equal(pre.headers.get("Access-Control-Allow-Methods"), "POST, OPTIONS, GET");
  assert.equal((await worker.fetch(new Request("https://w/lines", { method: "OPTIONS", headers: { Origin: "https://evil.example" } }), env(LINES))).status, 403);
  assert.equal(corsHeaders("https://evil.example", {})["Access-Control-Allow-Origin"], undefined);
});
test("input validation and caps", async () => {
  _resetRate();
  for (const [b, code] of [[{}, 400], [{ line: "" }, 400], [{ line: "x".repeat(201) }, 400], [{ line: "a", mood: "bogus" }, 400],
    [{ line: "a", count: 31 }, 400], [{ line: "a", rhymes: ["<script>"] }, 400], [{ line: "a", context: "x".repeat(601) }, 400], ["not json", 400],
    [{ line: "a", exclude: Array(61).fill("x") }, 400], [{ line: "a", rhythm: "<x>" }, 400], [{ line: "a", echo: { word: "x", words: ["<"] } }, 400],
    [{ line: "a", seed: 5000 }, 400], ["x".repeat(13000), 413]])
    assert.equal((await worker.fetch(req(b, { ip: "9.9.9." + code + Math.random() }), env(LINES))).status, code, JSON.stringify(b).slice(0, 40));
  assert.equal((await worker.fetch(req(null, { method: "GET", path: "/health" }), env(LINES))).status, 200);
  assert.equal((await worker.fetch(req(null, { method: "GET", path: "/nope" }), env(LINES))).status, 404);
  assert.equal((await worker.fetch(req({ line: "a" }, { method: "PUT" }), env(LINES))).status, 405);
});
test("rate limiting per IP", async () => {
  _resetRate(); const codes = [];
  for (let i = 0; i < 22; i++) codes.push((await worker.fetch(req({ line: "falling snow " + i }, { ip: "7.7.7.7" }), env(LINES))).status);
  assert.deepEqual(codes.slice(0, 20), Array(20).fill(200)); assert.equal(codes[20], 429);
  assert.equal((await worker.fetch(req({ line: "falling snow" }, { ip: "8.8.8.8" }), env(LINES))).status, 200);
});
test("AI failures map to 502 / 429 quota", async () => {
  _resetRate();
  assert.equal((await worker.fetch(req({ line: "a b" }), env(new Error("boom")))).status, 502);
  assert.equal((await worker.fetch(req({ line: "a c" }), env(new Error("4006: you have used up your daily free allocation of 10,000 neurons")))).status, 429);
  assert.equal((await worker.fetch(req({ line: "a d" }), env("I cannot help with that."))).status, 200);
  assert.equal((await worker.fetch(req({ line: "a e" }), env(""))).status, 502);
});
test("parsers and model output shapes", () => {
  assert.deepEqual(parseLines('Sure! Here are some:\n1. "Under the moon we glow"\n2) Down the road we go\n- [Chorus]\n3. Down the road we go', "x"), ["Under the moon we glow", "Down the road we go"]);
  assert.equal(parseLines(JSON.stringify(Array.from({ length: 40 }, (_, i) => "line number " + i)), "x").length, 30);
  assert.equal(lastWord("Walking through the falling snow!"), "snow"); assert.equal(lastWord("rock'n'roll"), "rock'n'roll");
  assert.equal(validate({ line: "ok", exclude: ["a"], rhymes: ["go", "let it go"], count: 24, syllables: 9, mood: "night", end_word: "snow" }), null);
  assert.equal(validateBrainstorm({ word: "snow" }), null);
  assert.equal(buildMessages({ line: "hi there" }).length, 2); assert.equal(buildBrainstorm({ word: "snow" }).length, 2);
  assert.equal(modelText({ choices: [{ message: { content: "[\"a\"]" } }] }), "[\"a\"]");
  assert.equal(modelText({ output: [{ content: [{ type: "output_text", text: "hi" }] }] }), "hi");
  assert.deepEqual(parseBrainstorm('{"perfect":["a b c d e f g"]}', "x").perfect, []);
});
