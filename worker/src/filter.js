// Same rejection rules the in-browser verifier uses for AI output.
// A token must be a real CMUdict/WordNet word (worker/src/dict.js) or a function word.
// Forced endings are rejected even when every word is real.
import { WORDS } from "./dict.js";

const BAD_END = [
  /\b(?:through|in|on|over|under|about|as)\s+the\s+(?:woe|tow|slow|show|grow|flow)\b/,
  /\ball\s+about\s+the\s+[a-z]+\b/,
  /\blet\s+it\s+(?!go\b)[a-z]+\b/,
  /\bto\s+bestow\b/,
  /\b(?:forest|street|streets|footstep|footsteps)\s+(?:flow|tow|woe|grow)\b/,
  /\bthe\s+(?:tow|woe)\b/,
];

export function wordTokens(text) {
  return String(text || "").toLowerCase().match(/[a-z]+(?:'[a-z]+)?/g) || [];
}
export function isRealWord(w) { return WORDS.has(w); }
export function isForced(text) {
  const s = " " + wordTokens(text).join(" ") + " ";
  return BAD_END.some(r => r.test(s.trim()));
}
export function keepText(text) {
  const toks = wordTokens(text);
  if (!toks.length || isForced(text)) return false;
  return toks.every(isRealWord);
}
export function filterLines(lines) {
  const out = [];
  const seen = new Set();
  for (const line of lines || []) {
    const k = String(line).trim().toLowerCase();
    if (!k || seen.has(k) || !keepText(line)) continue;
    seen.add(k); out.push(line);
  }
  return out;
}
export function filterBrainstorm(groups) {
  const out = { perfect: [], multi: [], slant: [], phrases: [] };
  const seen = new Set();
  for (const k of Object.keys(out)) {
    for (const item of (groups && groups[k]) || []) {
      const s = String(item || "").trim();
      const key = s.toLowerCase();
      if (!s || seen.has(key) || !keepText(s)) continue;
      seen.add(key); out[k].push(s);
    }
  }
  return out;
}
