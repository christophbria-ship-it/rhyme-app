# Rhymer — rhyming dictionary
Perfect, near, slant and multi-syllable rhymes for 251,317 words (125,938 CMUdict + 20,876 rule-derived inflections + 104,503 g2p_en-generated), with syllable / part-of-speech / popularity / length filters.
Data: CMU Pronouncing Dictionary, wordfreq 'large' English list + zipf frequencies, g2p_en (neural grapheme-to-phoneme), WordNet 3.0 (POS; inflected forms mapped to base forms).
Generated pronunciations are lower confidence (`conf`: dict > derived > g2p), ranked after dictionary words, and shown in italics.
`prepare_words.py` (needs `pip install wordfreq g2p_en`) regenerates `data/extra_words.tsv` and `data/zipf.tsv`; set `TARGET` for vocabulary size.

## Rhyme tiers
- **perfect**: identical sounds from the last stressed vowel; `matched_syllables` counts how far the match extends (multi-syllable).
- **near**: same vowels, consonants in the same family (voicing/manner), e.g. month → once.
- **slant**: same stressed vowel sequence with consonant similarity score ≥ 0.6 (last consonant per syllable: same=1, family=0.8, manner=0.6), or exact consonant skeleton (≥2 consonants). Unstressed-only tails are excluded.

## Run (server)
    python3 -m venv .venv && . .venv/bin/activate
    python build_index.py          # -> data/index.pkl
    WORKERS=4 python server.py 8765  # pre-fork workers, http://localhost:8765
API: `/api/rhymes?word=&syllables=1,2&pos=n,v,adj,adv&min_len=&max_len=&min_freq=&sort=score|freq|alpha|length&limit=`, `/api/suggest?q=`, `/api/health`

## Static build (GitHub Pages)
`python build_static.py` → `site/` (UI + 4 JSON data shards + in-browser engine `api-shim.js`, parity-tested against the Python engine).
`.github/workflows/pages.yml` builds and deploys it on push to `main` (Settings → Pages → Source: GitHub Actions).

## Tests
    pip install pytest playwright && python -m playwright install --with-deps chromium
    python -m pytest -v tests     # engine, API, UI (Playwright, 3 widths), static build parity
    python tests/stress.py         # 10k lookups + 2k HTTP @16 concurrency

## Installable app (PWA)
The static site ships `manifest.webmanifest`, icons (`static/icons/`, regenerate with `python tools/make_icons.py`), iOS meta tags and `sw.js`.
The service worker precaches the app shell + all data shards (works offline); its cache name is a content hash set by `build_static.py`, so each deploy installs a fresh cache and deletes the old one.
