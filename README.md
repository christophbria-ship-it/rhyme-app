# Rhymer — rhyming dictionary
Perfect, near, slant and multi-syllable rhymes for 125,938 CMUdict words, with syllable / part-of-speech / popularity / length filters.
Data: CMU Pronouncing Dictionary, WordNet 3.0 (POS; inflected forms mapped to base forms), OpenSubtitles 50k frequency list (hermitdave/FrequencyWords).

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
