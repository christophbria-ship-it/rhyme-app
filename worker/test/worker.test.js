import test from "node:test";
import assert from "node:assert/strict";
import worker, { parseLines, validate, buildMessages, lastWord, _resetRate, corsHeaders } from "../src/index.js";
const ORIGIN = "https://christophbria-ship-it.github.io";
const env = (resp, opts = {}) => { const e = { ...opts }; e.AI = { run: async (model, input) => { e.last = { model, input }; if (resp instanceof Error) throw resp; return { response: resp }; } }; return e; };
const req = (body, { origin = ORIGIN, method = "POST", path = "/lines", ip = "1.1.1.1" } = {}) =>
  new Request("https://rhymer-ai.example.workers.dev" + path, { method, headers: { "Content-Type": "application/json", ...(origin ? { Origin: origin } : {}), "CF-Connecting-IP": ip },
    body: method === "POST" ? (typeof body === "string" ? body : JSON.stringify(body)) : undefined });
const LINES = '["The world is hushed and white below", "Our footprints fading as we go", "I feel the winter wind blow", "Your hand in mine, the embers glow", "Here are lines", "The world is hushed and white below"]';

test("happy path returns cleaned, deduped lines with CORS for the Pages origin", async () => {
  _resetRate(); const e = env(LINES);
  const r = await worker.fetch(req({ line: "walking through the falling snow", mood: "love", syllables: 8, rhymes: ["glow", "go"] }), e);
  assert.equal(r.status, 200); assert.equal(r.headers.get("Access-Control-Allow-Origin"), ORIGIN);
  const d = await r.json(); assert.deepEqual(d.lines, ["The world is hushed and white below", "Our footprints fading as we go", "I feel the winter wind blow", "Your hand in mine, the embers glow"]);
  assert.match(e.last.input.messages[1].content, /rhymes or near-rhymes with "snow"/); assert.match(e.last.input.messages[1].content, /about 8 syllables/);
  assert.match(e.last.input.messages[1].content, /glow, go/); assert.match(e.last.input.messages[1].content, /"love"/);
});
test("foreign origin and missing origin are rejected; preflight", async () => {
  _resetRate();
  assert.equal((await worker.fetch(req({ line: "x y" }, { origin: "https://evil.example" }), env(LINES))).status, 403);
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
    [{ line: "a", count: 20 }, 400], [{ line: "a", rhymes: ["<script>"] }, 400], [{ line: "a", context: "x".repeat(601) }, 400], ["not json", 400],
    [{ line: "a", exclude: Array(41).fill("x") }, 400], ["x".repeat(9000), 413]])
    assert.equal((await worker.fetch(req(b, { ip: "9.9.9." + code + Math.random() }), env(LINES))).status, code, JSON.stringify(b).slice(0, 40));
  assert.equal((await worker.fetch(req(null, { method: "GET" }), env(LINES))).status, 405);
  assert.equal((await worker.fetch(req(null, { method: "GET", path: "/health" }), env(LINES))).status, 200);
  assert.equal((await worker.fetch(req(null, { method: "GET", path: "/nope" }), env(LINES))).status, 404);
});
test("rate limiting per IP", async () => {
  _resetRate(); const codes = [];
  for (let i = 0; i < 14; i++) codes.push((await worker.fetch(req({ line: "falling snow" }, { ip: "7.7.7.7" }), env(LINES))).status);
  assert.deepEqual(codes.slice(0, 12), Array(12).fill(200)); assert.equal(codes[12], 429);
  assert.equal((await worker.fetch(req({ line: "falling snow" }, { ip: "8.8.8.8" }), env(LINES))).status, 200);
});
test("AI failures map to 502 / 429 quota", async () => {
  _resetRate();
  assert.equal((await worker.fetch(req({ line: "a b" }), env(new Error("boom")))).status, 502);
  assert.equal((await worker.fetch(req({ line: "a b" }), env(new Error("4006: you have used up your daily free allocation of 10,000 neurons")))).status, 429);
  assert.equal((await worker.fetch(req({ line: "a b" }), env("I cannot help with that."))).status, 200);
  assert.equal((await worker.fetch(req({ line: "a b" }), env(""))).status, 502);
});
test("parseLines handles numbered / prose output", () => {
  assert.deepEqual(parseLines('Sure! Here are some:\n1. "Under the moon we glow"\n2) Down the road we go\n- [Chorus]\n3. Down the road we go', "x"), ["Under the moon we glow", "Down the road we go"]);
  assert.equal(lastWord("Walking through the falling snow!"), "snow"); assert.equal(lastWord("rock'n'roll"), "rock'n'roll");
  assert.equal(validate({ line: "ok", exclude: ["a"], rhymes: ["go"], count: 8, syllables: 9, mood: "night", end_word: "snow" }), null);
  assert.equal(buildMessages({ line: "hi there" }).length, 2);
});
