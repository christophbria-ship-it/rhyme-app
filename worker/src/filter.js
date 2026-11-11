// Same rejection rules the in-browser verifier uses for AI output.
// A token must be a real CMUdict/WordNet word (worker/src/dict.js) or a function word.
// A rare or wrong-part-of-speech rhyme landing is rejected from WordNet frequency and POS
// (worker/src/lex.js). Kept in sync with engine.bad_ending and static/api-shim.js.
import { WORDS } from "./dict.js";
import { LEX } from "./lex.js";

const RARE_END = 3.8;
const DETS = new Set(["the", "a", "an", "my", "your", "his", "her", "our", "their", "this", "every", "each"]);
const WEAK_END = new Set("go show slow low woe so though tho".split(" "));
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
// Missing words are rare nouns and not adjectives: tow and woe need no entry.
function meta(word) {
  const flags = LEX.get(word);
  if (flags == null) return { noun: true, rare: true, adj: false };
  return { noun: (flags & 1) !== 0, rare: (flags & 2) !== 0, adj: (flags & 4) !== 0 };
}
function endingSlot(toks) {
  if (toks.length < 2) return null;
  if (DETS.has(toks[toks.length - 2])) return "det";
  if (!meta(toks[toks.length - 2]).adj) return null;
  let i = toks.length - 2;
  while (i >= 0 && meta(toks[i]).adj && !DETS.has(toks[i])) i--;
  if (i >= 0 && DETS.has(toks[i])) return "det-adj";
  return "adj";
}
export function isRealWord(w) { return WORDS.has(w); }
export function isForced(text, source = "") {
  const toks = wordTokens(text);
  const s = toks.join(" ");
  if (BAD_END.some(r => r.test(s))) return true;
  const slot = endingSlot(toks);
  if (!slot) return false;
  const end = toks[toks.length - 1];
  if (WEAK_END.has(end) && (slot === "adj" || slot === "det-adj")) return true;
  const m = meta(end);
  const allow = new Set(wordTokens(source));
  if (!m.noun && (slot === "det" || (m.rare && (slot === "adj" || slot === "det-adj")))) return true;
  if (m.noun && m.rare && (slot === "adj" || slot === "det-adj") && !allow.has(end)) return true;
  return false;
}
export function keepText(text, source = "") {
  const toks = wordTokens(text);
  if (!toks.length || isForced(text, source)) return false;
  return toks.every(isRealWord);
}
export function filterLines(lines, source = "") {
  const out = [];
  const seen = new Set();
  for (const line of lines || []) {
    const k = String(line).trim().toLowerCase();
    if (!k || seen.has(k) || !keepText(line, source)) continue;
    seen.add(k); out.push(line);
  }
  return out;
}
export function filterBrainstorm(groups, word = "") {
  const out = { perfect: [], multi: [], slant: [], phrases: [] };
  const seen = new Set();
  for (const k of Object.keys(out)) {
    for (const item of (groups && groups[k]) || []) {
      const s = String(item || "").trim();
      const key = s.toLowerCase();
      if (!s || seen.has(key) || !keepText(s, word)) continue;
      seen.add(key); out[k].push(s);
    }
  }
  return out;
}
