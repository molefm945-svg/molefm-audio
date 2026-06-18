# AGENTS.md — Mole FM Mission Briefing for Codex

> Read this file at the start of every task. It is the single source of truth.

## What is Mole FM?

Mole FM 94.5 is an AI-powered Haitian radio station serving the Haitian diaspora.
It runs 24/7 with hourly newscasts, 3x daily podcasts, and a live reader webapp.

**Owner:** molefm945@gmail.com
**Live site:** https://www.molefm.com (Vercel)
**Reader app:** https://molefm-reader.pplx.app
**GitHub repos:** molefm945-svg/molefm-site | molefm945-svg/molefm-audio

---

## Repository Structure

### molefm-site (the website — React + Vite + Vercel)
```
client/src/
  pages/        Home.tsx, Local.tsx, Podcasts.tsx, Music.tsx, Reader.tsx
  components/   GlobalDashbar.tsx, ShareSheet.tsx, MiniPlayer.tsx, ...
  lib/          api.ts
server/         Express API routes
deploy_vercel.py  ← deploy script (uses Vercel API token in env)
```

Build command: `npm run build` in repo root → produces `dist/public/` + `dist/api.cjs`
Deploy: `python3 deploy_vercel.py` (needs CUSTOM_CRED_API_VERCEL_COM env var)
Or: commit to GitHub and Vercel auto-deploys from main branch.

### molefm-audio (pipeline scripts + audio hosting)
```
pipeline/scripts/   All Python scripts (news_fetcher.py, podcast_generator.py, etc.)
pipeline/config/    sponsors.json, audio_registry.json
AGENTS.md           This file (copy kept here too)
audio/              Newscast MP3s (raw.githubusercontent.com URLs)
podcasts/           Podcast MP3s
public/radio/generated/latest-content-pack.json  ← content pack served to website
```

---

## Active Task Queue (check this before starting)

### TASK 1 — Source Attribution (IN PROGRESS, highest priority)
**Goal:** Every article card on molefm.com shows a link to the original article.

**Files to edit:**

**Step 1 — `pipeline/scripts/news_fetcher.py`**
Find `log_verification_run()` function (~line 398-415).
In the `"stories"` list dict, add these fields:
```python
"link":         s.get("link", ""),
"description":  s.get("description", "")[:200],
"pub_date":     s.get("pub_date", ""),
"source_url":   s.get("source_url", ""),
```
The `s` dict already has these fields from `fetch_rss()` — they are just not being saved to the log.

**Step 2 — `pipeline/scripts/content_pack_generator.py`**
Find `get_trilingual_articles()` function (~line 260-322).
In the `articles.append({...})` block, add:
```python
"link":        s.get("link", ""),
"source_url":  SOURCE_HOMEPAGES.get(s.get("source",""), ""),
"description": s.get("description", ""),
"pub_date":    s.get("pub_date", ""),
"all_sources": s.get("all_sources", [s.get("source","")]),
```
Add SOURCE_HOMEPAGES dict before the append block:
```python
SOURCE_HOMEPAGES = {
    "Le Nouvelliste": "https://lenouvelliste.com",
    "Radio Métropole": "https://metropole.ht",
    "Juno7": "https://juno7.ht",
    "Haiti24": "https://haiti24.net",
    "Rezo Nodwes": "https://rezonodwes.com",
    "Haiti Liberté": "https://haitiliberte.com",
    "Haiti Press Network": "https://hpnhaiti.com",
    "Haitian Times": "https://haitiantimes.com",
    "RFI Haïti": "https://www.rfi.fr/fr/tag/haïti",
    "BBC Afrique": "https://www.bbc.com/afrique",
}
```

**Step 3 — `client/src/pages/Home.tsx`**
- Add `link?: string; source_url?: string; description?: string;` to `TrilingualArticle` interface
- Add `ExternalLink` to the lucide-react import
- In `TrilingualArticleCard`, after the source name `<span>`, add:
```tsx
{(article.link || article.source_url) && (
  <a
    href={article.link || article.source_url || ""}
    target="_blank"
    rel="noopener noreferrer"
    onClick={e => e.stopPropagation()}
    style={{ display:"inline-flex", alignItems:"center", gap:3,
             fontSize:11, color:"#2563EB", fontWeight:600,
             textDecoration:"none", marginLeft:4 }}
  >
    <ExternalLink size={10} />
    {article.link ? "Lire l'article" : article.source}
  </a>
)}
```

**Step 4 — `client/src/pages/Local.tsx`**
Same pattern — add source link `<a>` tag to both featured card and article cards.
Use `ExternalLink` from lucide-react (already imported).
Use `a.link || a.source_url` as href.
Label: `{a.link ? "Lire" : "Source"}`

**Step 5 — Verify, build, commit**
```bash
cd molefm-site && npm run build
# Check for TypeScript errors — fix any before committing
git add -A && git commit -m "feat: source attribution — article links through pipeline to frontend"
git push
```

---

### TASK 2 — YouTube Pipeline (after Task 1)
Scripts already built at:
- `pipeline/scripts/video_generator.py`  
- `pipeline/scripts/youtube_optimizer.py`

Add a GitHub Actions workflow `.github/workflows/youtube_video.yml` that:
1. Triggers on `push` to `audio/*.mp3`
2. Runs `pip install pillow numpy` 
3. Runs `python3 pipeline/scripts/video_generator.py --file <new_mp3>`
4. Runs `python3 pipeline/scripts/youtube_optimizer.py`
5. Commits the generated MP4 + metadata JSON to `videos/queue/`

---

### TASK 3 — Podcast source notes in description (after Task 1)
In `pipeline/scripts/podcast_generator.py`, find the episode description string
(~line 750-755). Add source attribution lines:
```python
_source_lines = "\n".join(
    f"  • {sn} ({SOURCE_URLS.get(sn, 'https://www.molefm.com')})"
    for sn in _source_names
) if _source_names else "  • Sources vérifiées (voir molefm.com)"
_desc = (
    f"Émission quotidienne Mole FM — {now.strftime('%d %B %Y')}.\n"
    f"Analyse approfondie des actualités d'Haïti avec Denise et Henri.\n"
    f"Format : The Daily × BBC Global News × Hugo Décrypte.\n"
    f"Durée : {mins}m{secs:02d}s\n\n"
    f"Sources & Références :\n{_source_lines}\n\n"
    f"Mole FM 94.5 — La radio haïtienne qui informe. molefm.com"
)
```

---

## Critical Rules — Never Break These

1. **TTS voices are FIXED** — never change them:
   - Podcast Denise: `fr-FR-DeniseNeural`
   - Podcast Henri: `fr-FR-HenriNeural`  
   - Station ID: `fr-CA-ThierryNeural`
   - Sign-off: `fr-CA-SylvieNeural`

2. **Audio is NEVER base64 in HTML** — always separate .mp3 files.
   Index.html must stay under 1MB.

3. **Only Mathurin Beach Resort** is active in `config/sponsors.json`.
   Do not remove inactive sponsors from the JSON.

4. **Lenordstar URL**: always `https://lenordstar.com` — never www.lenordstar.com

5. **vercel.ts must never import `registerRoutes`** — causes setInterval crash.

6. **edge-tts rate**: only `+X%` format — never `-X%`.

7. **All news must be in French** — do not add Haitian Creole to the broadcast script.

8. **Verification engine must not be bypassed** — never lower confidence thresholds.

9. **Cost = zero or near-zero** — never add paid APIs (ElevenLabs, AWS Polly, etc.)
   without explicit owner approval.

10. **always commit after completing a task** — the pipeline reads from GitHub.

---

## Tech Stack

| Layer | Tech |
|-------|------|
| Frontend | React + Vite + TypeScript + TailwindCSS + Wouter |
| Backend | Express.js (Vercel serverless via api.cjs) |
| TTS | edge-tts (Python, zero cost) |
| Video | FFmpeg + Pillow + numpy (zero cost) |
| Audio hosting | GitHub raw URLs (free) |
| Deploy | Vercel (molefm-site) + pplx.app (reader) |
| Pipeline | Python 3.11, runs on Perplexity Computer sandbox |

---

## Key URLs

- Vercel Team: `team_M5rY0i0dRk5V1ybICaNgODFX`
- Vercel Project: `prj_uxsmXdONT9JB2hXgwCWpo7nyjRjw`
- Content pack: `https://raw.githubusercontent.com/molefm945-svg/molefm-audio/main/public/radio/generated/latest-content-pack.json`
- Stream: `https://stream.zeno.fm/0r0xa792kwzuv`
- Mathurin Beach Resort: `https://wa.me/50938554309?text=Bonjour+Mathurin+Beach+Resort`

---

## Completed Work (do not redo)

- ✅ GlobalDashbar (ticker + category pills + Haiti live bar) — sticky on all pages
- ✅ ShareSheet (WhatsApp/FB/X/Telegram/SMS/copy) — on MiniPlayer + article cards
- ✅ Nouvèl Lokal page — category filter, featured card, confidence badges
- ✅ Biography podcast (`biography_podcast.py`) — daily "Dans la Vie de..."
- ✅ QA subagents (`qa_subagents.py`) — 4-agent quality orchestra
- ✅ AutoSearch (`autosearch.py`) — Karpathy RSS discovery
- ✅ Podcast optimizer (`podcast_optimizer.py`) — daily quality analysis
- ✅ Video generator (`video_generator.py`) — YouTube MP4 from newscast
- ✅ YouTube optimizer (`youtube_optimizer.py`) — SEO titles, descriptions, compliance

---

## How to Run the Pipeline Manually

```bash
# Full pipeline
python3 pipeline/scripts/run_pipeline.py

# Just generate a podcast
python3 pipeline/scripts/podcast_generator.py fr midi

# Generate a YouTube video from latest newscast
python3 pipeline/scripts/video_generator.py

# Generate YouTube metadata
python3 pipeline/scripts/youtube_optimizer.py

# AutoSearch new RSS sources
python3 pipeline/scripts/autosearch.py
```
