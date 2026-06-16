# Mole FM 94.5 — Codex/AI Agent Mission File

> This file is read by any AI agent (Perplexity Computer, OpenAI Codex, or any future LLM agent)
> working on the Mole FM pipeline. It defines purpose, rules, improvement targets, and safe boundaries.

---

## Mission

Mole FM 94.5 is an AI-powered Haitian news radio station serving the Haitian diaspora worldwide.
It runs 24/7, fully automated, at zero variable cost.

**Goal:** Become the #1 daily Haitian news podcast in French for the diaspora.
**Revenue target:** $1,000/day by Year 2 via blended model (sponsors + subscriptions + programmatic).

---

## The Pipeline (What You Are Running)

All files live under `/home/user/workspace/molefm/` (Perplexity workspace) and are backed up to:
`https://github.com/molefm945-svg/molefm-audio`

| Script | Purpose | Runs |
|--------|---------|------|
| `scripts/run_pipeline.py` | Master orchestrator: fetch → TTS → playlist → reader → GitHub → molefm.com | Hourly |
| `scripts/news_fetcher.py` | 12-source RSS fetcher with cross-source verification engine | Via pipeline |
| `scripts/podcast_generator.py` | 2-voice FR podcast, 18-22 min, The Daily × BBC format | 3x daily |
| `scripts/podcast_optimizer.py` | Daily quality analysis → patches for tomorrow | Daily 01:30 Haiti |
| `scripts/build_reader.py` | Builds trilingual karaoke reader (FR/EN/ES) | Via pipeline |
| `scripts/autosearch.py` | Karpathy RSS autodiscovery engine | Daily midnight Haiti |
| `scripts/tts_generator.py` | edge-tts zero-cost TTS (never switch to paid TTS) | Via pipeline |
| `scripts/github_uploader.py` | Pushes MP3s to GitHub for permanent public URLs | Via pipeline |
| `scripts/molefm_submitter.py` | Submits URLs to molefm.com admin via browser | Via pipeline |

---

## What Any Agent Can Improve Autonomously

No human approval needed for these changes:

1. **`news_fetcher.py`** — Add new verified RSS sources, improve dedup, tighten verification rules
2. **`podcast_generator.py`** — Improve dialogue quality, hook writing, act transitions, turn variety
3. **`podcast_optimizer.py`** — Add new quality metrics, improve patch generation logic
4. **`autosearch.py`** — Improve candidate scoring, RSS discovery patterns
5. **`tts_generator.py`** — Improve SSML prosody, pauses, emphasis (stay within edge-tts, no paid TTS)

**After any autonomous change:**
- Run the affected script with a test invocation to verify no errors
- Commit to git with message: `Agent: <what improved> — <metric targeted>`
- Log to `/home/user/workspace/molefm/research/codex_improvement_log.json`

---

## What Requires Human Approval (Never Change Without Asking)

- TTS voice assignments (brand identity — see Voice Table below)
- Sponsor configuration (`config/sponsors.json`)
- molefm.com admin credentials
- GitHub repo name or structure
- Any change to deploy_website or publish_website calls
- Adding paid APIs or services (cost discipline is critical — near-zero cost is required)

---

## Quality Standards (Non-Negotiable)

### News Standards
- All news in **French** (not Haitian Creole)
- Cross-source verification: high-stakes stories require 2+ independent sources
- Attribution in broadcast: "Selon Le Nouvelliste et Radio Métropole —"
- Never broadcast unverified deaths, arrests, coups, or political crises

### Podcast Standards (The Daily × BBC × Hugo Décrypte)
- Duration: **18-22 minutes** (~3,400-3,800 words at 170 wpm)
- Two voices: Denise (warm, curious) / Henri (analytical, contrarian)
- No turn under 12 words
- No filler responses: "parfait / absolument / exactement" are banned
- Cold hook first — never open with "Bonjour" or welcome preamble
- Quality flags that must be zero: MONOLOGUE_RISK, TOO_SHORT, TOO_LONG, ECHO_TURNS

### Audio Architecture (NEVER REGRESS)
- `index.html` must be under 1MB — audio is NEVER embedded as base64
- Audio served as separate MP3 files: `audio_fr.mp3`, `audio_en.mp3`, `audio_es.mp3`
- `const AUDIO_URLS={fr:"audio_fr.mp3",en:"audio_en.mp3",es:"audio_es.mp3"};` in index.html
- Speed control (`setSpeed()`) applies to both news audio AND `_podAudio`

---

## Voice Table (Never Change)

| Segment | Voice |
|---------|-------|
| Podcast Denise | fr-FR-DeniseNeural |
| Podcast Henri | fr-FR-HenriNeural |
| Hourly STATION_ID | fr-CA-ThierryNeural |
| Hourly NEWS/WEATHER/SPONSOR | fr-FR-DeniseNeural |
| Hourly SPORTS | fr-FR-HenriNeural |
| Hourly SIGN_OFF | fr-CA-SylvieNeural |

---

## News Source Network (12 Live Sources)

**Tier 1 (Primary Haitian Press):**
- Le Nouvelliste: `https://lenouvelliste.com/feed`
- Radio Métropole: `https://metropole.ht/feed/`
- Juno7: `https://juno7.ht/feed`
- Haiti24: `https://haiti24.net/feed`
- Rezo Nodwes: `https://rezonodwes.com/feed/`
- Haiti Liberté: `https://haitiliberte.com/feed/`
- Haiti Press Network: `https://hpnhaiti.com/feed/`
- Haiti Express Sports: `https://www.haitiexpress.net/category/sports/feed/`
- Bonpounou Sports: `https://www.bonpounou.com/news/rss/category/sports`

**Tier 2 (International/Diaspora):**
- Haitian Times: `https://haitiantimes.com/feed/`
- RFI Haïti: `https://www.rfi.fr/fr/tag/ha%C3%AFti/rss` ← Use this URL (old one is 404)
- BBC Afrique: `https://feeds.bbci.co.uk/afrique/rss.xml`

**Dead feeds (never re-add):** IciHaiti (404), AyiboPost (malformed XML), Haiti Libre (403)

---

## Autoresearch Loop (Karpathy Pattern)

The self-improvement loop runs weekly:

1. Read `research/episode_quality_log.json` — find lowest-scoring metric over last 7 episodes
2. Research best broadcast journalism practice for that metric (web search)
3. Write a targeted patch to the relevant script
4. Test: run `python3 scripts/podcast_generator.py fr test` — verify no errors
5. Log to `research/codex_improvement_log.json`:
   ```json
   {"date": "...", "metric_improved": "...", "change": "...", "expected_impact": "..."}
   ```
6. Commit: `git commit -m "Agent: <metric> improvement — <one-line description>"`

**Target metrics in priority order:**
1. Episode engagement hook strength (cold hook quality score)
2. Turn variety (word count variance across turns)
3. Diaspora relevance score (% of stories with direct diaspora angle)
4. Source diversity (% of broadcasts with multi-source confirmed stories)
5. Weather accuracy (correct city forecasts)

---

## Revenue Roadmap (Context for Decision-Making)

| Timeline | Monthly Revenue | Key Actions |
|----------|----------------|-------------|
| Month 1-3 | $500-$2,500 | Land 2 more direct sponsors, launch WhatsApp digest |
| Month 4-6 | $2,500-$8,000 | Spotify/Apple distribution live, grow to 5K listeners |
| Month 7-12 | $8,000-$20,000 | Programmatic ads (Acast), WhatsApp subscription tier |
| Year 2-3 | $30,000+/mo | $1K/day achievable |

**Fastest path to first $1K/month:**
1. Mathurin Beach Resort sponsor (active) — estimated $500-1,500/mo
2. Second direct sponsor pitch (target: MonCash, CAM Transfer, or diaspora real estate)
3. WhatsApp digest: 500 subscribers × $4/mo = $2,000/mo

**WhatsApp economics (highest ROI at early scale):**
- 40-70% open rates vs email's 20-30%
- 2 sponsors × $500/send × 8 sends/month = $8,000/mo at 5K subscribers

---

## Recovery Instructions (If Workspace Resets)

If the Perplexity workspace is ever cleared, restore the full pipeline in 5 steps:

```bash
# 1. Clone the backup repo
git clone https://github.com/molefm945-svg/molefm-audio.git
cd molefm-audio

# 2. Copy scripts to workspace
cp -r pipeline/scripts /home/user/workspace/molefm/scripts
cp -r pipeline/config  /home/user/workspace/molefm/config

# 3. Install dependencies
pip install edge-tts feedparser requests mutagen playwright -q
python3 -m playwright install chromium --with-deps

# 4. Test the pipeline
python3 /home/user/workspace/molefm/scripts/run_pipeline.py

# 5. Restore scheduled crons (see pipeline/CRONS.md for IDs and schedules)
```

Full documentation: `pipeline/AGENTS.md` (this file)
Cron reference: `pipeline/CRONS.md`
Skill reference: Load `molefm-ops` in Perplexity Computer

---

## Codex CLI Integration (Optional Enhancement)

If using OpenAI Codex CLI for code improvements:

```bash
# Install
npm install -g @openai/codex

# Run autonomous improvement (non-interactive, safe for cron)
codex exec --approval-mode full-auto \
  "Read /home/user/workspace/molefm/AGENTS.md and \
   /home/user/workspace/molefm/research/episode_quality_log.json. \
   Find the lowest quality metric. Improve the relevant script. \
   Test it. Commit the change."

# For Mole FM specifically — you need Codex for:
# - Deep rewrites of 600+ line scripts (podcast_generator.py)
# - Adding new dialogue patterns from broadcast research
# - Refactoring build_reader.py for performance
```

**Codex does NOT handle:** web search, deployments, browser automation, notifications, cron management.
**Perplexity Computer handles all of those** — Codex is a specialist consultant, not the primary brain.

---

## Contact / Owner

- **Email:** molefm945@gmail.com
- **GitHub:** molefm945-svg
- **Live reader:** https://molefm-reader.pplx.app
- **molefm.com admin:** https://www.molefm.com/admin/radio (password: see config)
- **Primary AI brain:** Perplexity Computer (scheduled crons, memory, deployments)
